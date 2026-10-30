# -*- coding: utf-8 -*-
"""破妄 · 评论层知识图谱构建

把 data/crawled 下的真实评论注入关系图谱：
  1. 文本归一化 + 精确去重，按"相似度富集 + 高赞 + 分层随机"抽样；
  2. 用字符 bigram Jaccard 核对评论相似度，超过阈值的两条评论建"文本相似"边；
  3. 评论命中网络用语词典时，向对应词条节点建"提及"边；
  4. 用命中的词典情感投票给出可解释的初始分类（前端标注为"词典推断"）。

抽样与建边都在本模块内完成，app.py 只负责并入社区/视频/词条/类别节点。
"""
import datetime
import random
import re
from collections import Counter, defaultdict

CATEGORIES = ("赞美", "贬低", "水军", "无意义", "社区对骂", "中立")


def _norm(text):
    return re.sub(r"\s+", "", (text or "")).lower()


def _bigrams(text):
    s = _norm(text)
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _short(text, n=38):
    t = re.sub(r"\s+", " ", (text or "")).strip()
    return t if len(t) <= n else t[:n] + "…"


def _similarity_degrees(bgs, threshold, posting_cap=2600):
    """用倒排索引统计每条评论在阈值以上的相似邻居数。

    只做候选对生成，避免全量 O(n^2) 集合运算；超高频 bigram 截断以保证响应时间。
    """
    inv = defaultdict(list)
    for i, bg in enumerate(bgs):
        for g in bg:
            inv[g].append(i)
    degs = [0] * len(bgs)
    for i, A in enumerate(bgs):
        if not A:
            continue
        cnt = Counter()
        for g in A:
            pl = inv[g]
            if len(pl) > posting_cap:
                continue
            for j in pl:
                if j > i:
                    cnt[j] += 1
        for j, inter in cnt.items():
            B = bgs[j]
            union = len(A) + len(B) - inter
            if union and inter / union >= threshold:
                degs[i] += 1
                degs[j] += 1
    return degs


def _pick_comments(comments, quota, threshold, rng):
    """抽样：优先相似簇成员，其次高赞，最后分层随机补足。"""
    best = {}
    for c in comments:
        text = (c.get("text") or "").strip()
        key = _norm(text)
        if len(key) < 2:
            continue
        old = best.get(key)
        if old is None or (c.get("like") or 0) > (old.get("like") or 0):
            best[key] = c
    uniq = list(best.values())
    if not uniq:
        return [], [], [], []
    bgs = [_bigrams(c.get("text", "")) for c in uniq]
    degs = _similarity_degrees(bgs, threshold)

    def like(i):
        return int(uniq[i].get("like") or 0)

    linked = [i for i, d in enumerate(degs) if d > 0]
    linked.sort(key=lambda i: (-degs[i], -like(i)))
    n_linked = min(len(linked), int(quota * 0.58))
    picked = linked[:n_linked]
    picked_set = set(picked)

    rest = [i for i in range(len(uniq)) if i not in picked_set]
    hot = sorted(rest, key=lambda i: -like(i))[:int(quota * 0.24)]
    picked.extend(hot)
    picked_set.update(hot)

    rest = [i for i in range(len(uniq)) if i not in picked_set]
    rng.shuffle(rest)
    picked.extend(rest[:max(0, quota - len(picked))])
    return uniq, bgs, picked, degs


def _term_matches(text, term_index):
    """返回评论命中的 (命中词, 词条记录)，按 term/alias 子串匹配并去重。

    单字词(水/典/乐/唐…)只在短评论里生效，避免"音乐""经典"这类普通词误命中。
    """
    low = _norm(text)
    if not low:
        return []
    hits, seen = [], set()
    for name, rec in term_index.items():
        if not name or name not in low:
            continue
        if len(name) < 2 and len(low) > 8:
            continue
        rid = rec.get("node_id") or rec.get("term")
        if rid not in seen:
            seen.add(rid)
            hits.append((name, rec))
    hits.sort(key=lambda x: (len(x[0]) >= 2, len(x[0])), reverse=True)
    return hits


def build_comment_layer(comments, *, video_id, bvid, community, color,
                        term_index=None, quota=520, threshold=0.35,
                        max_sim_per_node=6, analyzed_categories=None,
                        rng_seed=20261022):
    """构建单个视频的评论节点与三类边。

    term_index: {小写词条/别名: {"node_id": "term:xx", "term": "...", "sentiment": "..."}}
    analyzed_categories: {rpid: 类别}，有模型标注时优先使用。
    """
    term_index = term_index or {}
    analyzed_categories = analyzed_categories or {}
    rng = random.Random(rng_seed)
    uniq, bgs, picked, corpus_deg = _pick_comments(comments, quota, threshold, rng)
    if not picked:
        return {"nodes": [], "edges": [], "stats": {
            "raw": len(comments), "unique": len(uniq), "sampled": 0,
            "linked": 0, "corpus_linked": 0, "sim_edges": 0, "threshold": threshold,
            "avg_sim": 0, "max_sim": 0}}

    picked.sort(key=lambda i: -int(uniq[i].get("like") or 0))
    sel_bgs = [bgs[i] for i in picked]
    sel = [uniq[i] for i in picked]

    # ---- 相似边：选中的评论两两复算，按相似度从高到低限量建边 ----
    pair_sims = []
    for a in range(len(sel)):
        A = sel_bgs[a]
        if not A:
            continue
        for b in range(a + 1, len(sel)):
            B = sel_bgs[b]
            if not B:
                continue
            mn, mx = (len(A), len(B)) if len(A) <= len(B) else (len(B), len(A))
            if mn / mx < threshold:
                continue
            s = _jaccard(A, B)
            if s >= threshold:
                pair_sims.append((s, a, b))
    pair_sims.sort(reverse=True)

    edges = []
    sims_by = defaultdict(list)
    sim_deg = [0] * len(sel)
    sim_total = 0.0
    max_sim = 0.0
    sim_added = 0
    for s, a, b in pair_sims:
        if sim_deg[a] >= max_sim_per_node or sim_deg[b] >= max_sim_per_node:
            continue
        sim_deg[a] += 1
        sim_deg[b] += 1
        sim_total += s
        sim_added += 1
        max_sim = max(max_sim, s)
        sid = f"cmt:{bvid}:{sel[a].get('rpid')}"
        tid = f"cmt:{bvid}:{sel[b].get('rpid')}"
        edges.append({
            "source": sid, "target": tid, "relation": "文本相似",
            "weight": round(s, 3), "sim": round(s, 3), "layer": "sim", "pending": False,
        })
        sims_by[a].append([b, round(s, 3)])
        sims_by[b].append([a, round(s, 3)])

    # ---- 评论节点 ----
    nodes = []
    for pos, c in enumerate(sel):
        text = (c.get("text") or "").strip()
        rpid = c.get("rpid")
        cid = f"cmt:{bvid}:{rpid}"
        hits = _term_matches(text, term_index)
        node_terms = []
        for hit_name, rec in hits:
            tid = rec.get("node_id")
            if tid and tid not in [t["id"] for t in node_terms]:
                node_terms.append({"id": tid, "label": rec.get("term") or tid[5:],
                                   "sentiment": rec.get("sentiment") or ""})
            if len(node_terms) >= 4:
                break

        # 词典情感投票；模型标注优先。多字词权重 2、单字词权重 1，至少 2 分才归类
        cat, source = "", ""
        model_cat = analyzed_categories.get(str(rpid))
        if model_cat in CATEGORIES:
            cat, source = model_cat, "模型"
        else:
            votes = Counter()
            for hit_name, rec in hits:
                s = rec.get("sentiment")
                if s in CATEGORIES:
                    votes[s] += 2 if len(hit_name) >= 2 else 1
            if votes:
                cand, score = votes.most_common(1)[0]
                if score >= 2:
                    cat, source = cand, "词典推断"

        month = ""
        ctime = c.get("ctime")
        if ctime:
            try:
                month = datetime.datetime.fromtimestamp(ctime).strftime("%Y-%m")
            except (ValueError, OSError, OverflowError):
                month = ""

        sims = sorted(sims_by.get(pos, []), key=lambda x: -x[1])[:4]
        local_max = max([x[1] for x in sims], default=0.0)
        nodes.append({
            "id": cid, "label": _short(text), "kind": "comment",
            "weight": int(c.get("like") or 0) + 1,
            "text": text[:180], "like": int(c.get("like") or 0),
            "rcount": int(c.get("rcount") or 0), "ctime": ctime, "month": month,
            "bvid": bvid, "vid": video_id, "community": community, "color": color,
            "category": cat, "category_source": source,
            "terms": node_terms, "sim_degree": sim_deg[pos], "max_sim": local_max,
            "sims": [{"id": f"cmt:{bvid}:{sel[b].get('rpid')}", "sim": s,
                      "label": _short(sel[b].get("text"), 26)} for b, s in sims],
        })

    # ---- 边：视频→评论、评论→词条 ----
    mention_edges = 0
    for pos, n in enumerate(nodes):
        edges.append({"source": video_id, "target": n["id"], "relation": "评论",
                      "weight": 1, "layer": "comment", "pending": False})
        for t in n["terms"]:
            edges.append({"source": n["id"], "target": t["id"], "relation": "提及",
                          "weight": 1, "layer": "mention", "pending": False})
            mention_edges += 1

    linked_nodes = sum(1 for d in sim_deg if d > 0)
    return {"nodes": nodes, "edges": edges, "stats": {
        "raw": len(comments), "unique": len(uniq), "sampled": len(nodes),
        "linked": linked_nodes, "corpus_linked": sum(1 for d in corpus_deg if d > 0),
        "sim_edges": len([e for e in edges if e["layer"] == "sim"]),
        "mention_edges": mention_edges, "threshold": threshold,
        "avg_sim": round(sim_total / max(1, sim_added), 3),
        "max_sim": round(max_sim, 3),
    }}
