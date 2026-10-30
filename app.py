# -*- coding: utf-8 -*-
"""破妄 · Flask 后端
职责：
  1. 服务包豪斯前端页面(front/*.html)
  2. 数据API：视频信息、语料、分析结果
  3. 标注/审查API：锚定集管理、二次审查、触发分析
架构沿用参考项目：static_folder=None 手动发页面 + no-store 缓存头 + {success, data|error} 契约。
"""
import os
import json
import random
import threading
import traceback
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

import sentiment_analyze as sa
import agent_chat
import comment_graph as cg

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONT_DIR = os.path.join(BASE_DIR, "front")
DATA_DIR = os.path.join(BASE_DIR, "data")
CRAWLED_DIR = os.path.join(DATA_DIR, "crawled")
ANALYSIS_DIR = os.path.join(DATA_DIR, "analysis")
LABEL_DIR = os.path.join(DATA_DIR, "labels")
ANCHORS_PATH = os.path.join(LABEL_DIR, "anchors.json")

_AGENT = None
# 分析任务表：bvid -> {status: running|done|error, done, total, error}
# 与 jsonl 断点文件共同支撑 /api/analyze/status 的运行中进度查询
_ANALYSIS_JOBS = {}


def _get_agent():
    global _AGENT
    if _AGENT is None:
        _AGENT = agent_chat.build_agent()
    return _AGENT

for _d in (FRONT_DIR, DATA_DIR, ANALYSIS_DIR, LABEL_DIR):
    os.makedirs(_d, exist_ok=True)

app = Flask(__name__, static_folder=None, template_folder=None)
CORS(app)

CFG = sa.load_project_config()
CATEGORIES = sa.CATEGORIES
CAT_COLORS = {"赞美": "#2743FF", "贬低": "#F22560", "水军": "#FFD400", "无意义": "#707A8E",
              "社区对骂": "#6E1EFF", "中立": "#00A88F"}


# ---------- 基础工具 ----------
def ok(data=None, **kw):
    body = {"success": True, "data": data or {}}
    body.update(kw)
    return jsonify(body)


def err(message, code=400):
    return jsonify({"success": False, "error": message}), code


def _read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def _videos():
    return CFG.get("videos", [])


def _corpus(bvid):
    return _read_json(os.path.join(CRAWLED_DIR, f"{bvid}.json"), {"comments": []})


def _analyzed(bvid):
    return _read_json(os.path.join(ANALYSIS_DIR, f"{bvid}_analyzed.json"))


# ---------- 锚定集 ----------
def _load_anchors():
    d = _read_json(ANCHORS_PATH, {"anchors": []})
    return d.get("anchors", [])


def _save_anchors(anchors):
    _write_json(ANCHORS_PATH, {"anchors": anchors, "updated_at": datetime.now().isoformat()})


# ---------- 页面路由 ----------
@app.route("/")
def page_landing():
    return _page("landing.html")


@app.route("/comments")
def page_comments():
    return _page("comments.html")


@app.route("/insight")
@app.route("/insight.html")
def page_insight():
    return _page("insight.html")


@app.route("/label")
def page_label():
    return _page("label.html")


def _page(name):
    path = os.path.join(FRONT_DIR, name)
    if not os.path.exists(path):
        return err("页面不存在", 404)
    r = Response(open(path, "r", encoding="utf-8").read(), mimetype="text/html; charset=utf-8")
    r.headers["Cache-Control"] = "no-store"
    return r


@app.route("/<path:filename>")
def front_static(filename):
    """前端静态资源(css/js)，限定在 front/ 目录内，防路径穿越"""
    safe = os.path.normpath(filename)
    if ".." in safe or os.path.isabs(safe):
        return err("非法路径", 400)
    path = os.path.join(FRONT_DIR, safe)
    if not os.path.isfile(path):
        return err("资源不存在", 404)
    ext = os.path.splitext(path)[1].lower()
    mime = {".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8",
            ".png": "image/png", ".jpg": "image/jpeg", ".svg": "image/svg+xml", ".ico": "image/x-icon"}.get(ext)
    if not mime:
        return err("不支持的资源类型", 400)
    r = Response(open(path, "rb").read(), mimetype=mime)
    r.headers["Cache-Control"] = "no-store"
    return r


@app.route("/health")
def health():
    return ok({"status": "ok", "anchors": len(_load_anchors())})


# ---------- 数据 API ----------
# 语料热词缓存：bvid -> (语料文件mtime, 结果)
_TOPSLANG_CACHE = {}


def _load_lexicon_terms():
    """合并网络用语词典与RAG知识库的 词条+别名(去重保序)，供语料词频统计"""
    terms = []
    for name in ("slang_dict.json", "rag_knowledge.json"):
        d = _read_json(os.path.join(DATA_DIR, name), {})
        for e in d.get("entries", []):
            t = (e.get("term") or "").strip()
            if t:
                terms.append(t)
            for a in e.get("aliases") or []:
                a = (a or "").strip()
                if a:
                    terms.append(a)
    seen, out = set(), []
    for t in terms:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out


def _corpus_top_slang(bvid, k=60):
    """未分析时的热词数据源：对爬取语料按词典命中频次统计热词(带mtime缓存)"""
    corpus_path = os.path.join(CRAWLED_DIR, f"{bvid}.json")
    try:
        mtime = os.path.getmtime(corpus_path)
    except OSError:
        return []
    hit = _TOPSLANG_CACHE.get(bvid)
    if hit and hit[0] == mtime:
        return hit[1]
    terms = _load_lexicon_terms()
    texts = [c.get("text") or "" for c in _corpus(bvid).get("comments", [])]
    # 大小写无关合并计数(yyds/YYDS 视为同一词)，展示名取先出现者
    scores, display = {}, {}
    for t in terms:
        key = t.lower()
        display.setdefault(key, t)
        n = sum(text.count(t) for text in texts)
        if n:
            scores[key] = scores.get(key, 0) + n
    counts = [{"term": display[key], "count": n} for key, n in scores.items() if n >= 1]
    counts.sort(key=lambda x: x["count"], reverse=True)
    top = counts[:k]
    _TOPSLANG_CACHE[bvid] = (mtime, top)
    return top


@app.route("/api/videos")
def api_videos():
    result = []
    for v in _videos():
        meta = _corpus(v["bvid"]).get("meta", {})
        analyzed = _analyzed(v["bvid"])
        result.append({
            **v,
            "title": meta.get("title", ""),
            "owner": meta.get("owner", ""),
            "pubdate": meta.get("pubdate"),
            "reply_count": meta.get("reply_count", 0),
            "corpus_count": _corpus(v["bvid"]).get("count", 0),
            "anchor_count": sum(1 for a in _load_anchors() if a.get("bvid") == v["bvid"]),
            "analyzed": bool(analyzed),
            "analysis": analyzed.get("category_count") if analyzed else None,
            "top_slang": (analyzed or {}).get("top_slang") or _corpus_top_slang(v["bvid"]),
            "trend": analyzed.get("trend", []) if analyzed else [],
            "representative": analyzed.get("representative", {}) if analyzed else {},
        })
    return ok({"videos": result})


@app.route("/api/analysis/<bvid>")
def api_analysis(bvid):
    a = _analyzed(bvid)
    if not a:
        return err("该视频尚未分析", 404)
    return ok(a)


@app.route("/api/corpus/<bvid>")
def api_corpus(bvid):
    """语料分页。query: page,size,order=ctime|like"""
    corpus = _corpus(bvid)
    comments = list(corpus.get("comments", []))
    order = request.args.get("order", "ctime")
    if order == "like":
        comments.sort(key=lambda c: c.get("like", 0), reverse=True)
    else:
        comments.sort(key=lambda c: c.get("ctime", 0), reverse=True)
    page = int(request.args.get("page", 1))
    size = min(int(request.args.get("size", 50)), 200)
    start = (page - 1) * size
    return ok({
        "meta": corpus.get("meta", {}),
        "total": len(comments),
        "page": page,
        "size": size,
        "items": comments[start:start + size],
    })


@app.route("/api/agent/chat", methods=["POST"])
def api_agent_chat():
    """AI 洞察问答：LangChain Agent 查询分析结果"""
    body = request.get_json(force=True) or {}
    question = (body.get("question") or "").strip()
    if not question:
        return err("缺少问题")
    try:
        ex = _get_agent()
        from langchain_core.messages import HumanMessage
        result = ex.invoke({"messages": [HumanMessage(content=question)]})
        msgs = result.get("messages", [])
        answer = msgs[-1].content if msgs else str(result)
        return ok({"answer": answer})
    except Exception as e:
        traceback.print_exc()
        return err(f"Agent 调用失败: {str(e)[:200]}", 500)


@app.route("/api/comments")
def api_comments():
    """带分类的评论列表。query: bvid, page,size,order=ctime|like,category,q
    合并原始语料与分析结果(逐条分类)；分类/关键词筛选在分页前完成，
    因此 total 始终是筛选后的总数，供无限下拉判断是否还有下一页。
    """
    bvid = request.args.get("bvid")
    corpus = _corpus(bvid)
    analyzed = _analyzed(bvid)
    by_rpid = {}
    if analyzed and analyzed.get("_rows"):
        for r in analyzed["_rows"]:
            by_rpid[r["rpid"]] = r
    comments = list(corpus.get("comments", []))
    order = request.args.get("order", "ctime")
    if order == "like":
        comments.sort(key=lambda c: c.get("like", 0), reverse=True)
    else:
        comments.sort(key=lambda c: c.get("ctime", 0), reverse=True)

    category = (request.args.get("category") or "").strip()
    if category in ("all", "全部"):
        category = ""
    q = (request.args.get("q") or "").strip().lower()

    merged = []
    for c in comments:
        a = by_rpid.get(c.get("rpid"), {})
        cat = a.get("category", "")
        if category and cat != category:
            continue
        if q and q not in (c.get("text") or "").lower():
            continue
        merged.append({
            **c,
            "category": cat,
            "confidence": a.get("confidence", 0),
            "reason": a.get("reason", ""),
            "slang_tags": a.get("slang_tags") or [],
        })

    page = max(1, int(request.args.get("page", 1)))
    size = min(max(1, int(request.args.get("size", 50))), 200)
    start = (page - 1) * size
    return ok({
        "meta": corpus.get("meta", {}), "total": len(merged),
        "page": page, "size": size, "items": merged[start:start + size],
        "analyzed": bool(analyzed),
    })


# ---------- 标注/审查 API ----------
def _norm_bigrams(text):
    """归一化文本的字符bigram集合(去标点/空白)，用于近似去重"""
    import re as _re
    t = _re.sub(r"[\s\W_]+", "", text or "")
    if len(t) < 2:
        return {t} if t else set()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / (len(a) + len(b) - inter)


@app.route("/api/label/queue")
def api_label_queue():
    """待标注队列：按视频，从语料中选未被标注的评论。
    先做近重复过滤(内容相似的刷屏评论不进人工标注列表)，再按长度分层保证多样性。
    query: bvid, size(默认100)
    """
    bvid = request.args.get("bvid")
    size = int(request.args.get("size", 100))
    anchors = _load_anchors()
    labeled = {a["rpid"] for a in anchors if a.get("bvid") == bvid}
    corpus = _corpus(bvid).get("comments", [])
    pool = [c for c in corpus if c.get("rpid") not in labeled and c.get("text")]

    # ---- 近重复过滤(强化)：保证人工标注样本两两互不相似 ----
    # 查重基准 = 已人工标注的锚定样本 + 本次已保留样本，全量比较(无窗口)；
    # 另设归一化bigram集合指纹做精确重复快筛(刷屏模板瞬间跳过)。
    LIMIT_SIMILAR = 0.55
    random.shuffle(pool)
    seen_sets, seen_norms = [], set()
    for a in anchors:
        if a.get("bvid") != bvid:
            continue
        bg = _norm_bigrams(a.get("text", ""))
        if bg:
            seen_sets.append(bg)
            seen_norms.add("".join(sorted(bg)))
    diverse = []
    for c in pool:
        bg = _norm_bigrams(c["text"])
        if not bg:
            continue
        key = "".join(sorted(bg))
        if key in seen_norms:
            continue
        dup = any(_jaccard(bg, s) >= LIMIT_SIMILAR for s in seen_sets)
        if dup:
            continue
        seen_sets.append(bg)
        seen_norms.add(key)
        diverse.append(c)
        if len(diverse) >= max(size * 4, 400):
            break
    pool = diverse

    if not pool:
        return ok({"bvid": bvid, "labeled": len(labeled), "total_pool": 0, "items": []})
    # 分层：按文本长度分3层，各层内部随机
    short, mid, long_ = [], [], []
    for c in pool:
        L = len(c["text"])
        if L <= 12:
            short.append(c)
        elif L <= 40:
            mid.append(c)
        else:
            long_.append(c)
    parts = []
    if size <= 100:
        n_s, n_m, n_l = int(size * 0.25), int(size * 0.45), size - int(size * 0.25) - int(size * 0.45)
    else:
        n_s, n_m, n_l = size // 3, size // 3, size - 2 * (size // 3)
    for grp, n in ((short, n_s), (mid, n_m), (long_, n_l)):
        random.shuffle(grp)
        parts.extend(grp[:n])
    random.shuffle(parts)
    return ok({
        "bvid": bvid,
        "labeled": len(labeled),
        "total_pool": len(pool),
        "items": [{"rpid": c["rpid"], "bvid": c["bvid"], "text": c["text"], "ctime": c.get("ctime"), "like": c.get("like", 0)} for c in parts],
    })


@app.route("/api/anchors", methods=["GET"])
def api_anchors_get():
    anchors = _load_anchors()
    by_video = {}
    for a in anchors:
        by_video.setdefault(a.get("bvid"), []).append(a)
    return ok({
        "anchors": anchors,
        "by_video": by_video,
        "count": len(anchors),
        "count_per_video": {bvid: len(items) for bvid, items in by_video.items()},
    })


@app.route("/api/anchors", methods=["POST"])
def api_anchors_post():
    """保存标注。body: {items: [{rpid,bvid,text,category}]} 可批量。
    也可传 single_item 单条。相同 rpid 覆盖(支持修正)。
    """
    body = request.get_json(force=True) or {}
    items = body.get("items") or ([body["item"]] if body.get("item") else [])
    if not items:
        return err("没有标注内容")
    anchors = _load_anchors()
    by_rpid = {a["rpid"]: a for a in anchors}
    added = 0
    for it in items:
        cat = it.get("category")
        if cat not in CATEGORIES or not it.get("rpid") or not it.get("text"):
            continue
        prev = by_rpid.get(it["rpid"])
        by_rpid[it["rpid"]] = {
            "rpid": it["rpid"], "bvid": it.get("bvid"), "text": it["text"],
            "category": cat, "source": "human",
            "corrected": bool(prev and prev.get("category") != cat),
            "updated_at": datetime.now().isoformat(),
        }
        added += 1
    _save_anchors(list(by_rpid.values()))
    return ok({"added": added, "count": len(by_rpid)})


@app.route("/api/anchors/delete", methods=["POST"])
def api_anchors_delete():
    body = request.get_json(force=True) or {}
    rpid = body.get("rpid")
    if not rpid:
        return err("缺少 rpid")
    anchors = _load_anchors()
    anchors = [a for a in anchors if a["rpid"] != rpid]
    _save_anchors(anchors)
    return ok({"count": len(anchors)})


@app.route("/api/review/queue")
def api_review_queue():
    """二次审查队列：从已分析结果中取大模型分类，供人工确认/修正。
    query: bvid, category(可选过滤), size
    """
    bvid = request.args.get("bvid")
    size = int(request.args.get("size", 50))
    cat_filter = request.args.get("category", "")
    analyzed = _analyzed(bvid)
    if not analyzed:
        return err("该视频尚未分析", 404)
    # 已人工修正的 rpid
    anchors = {a["rpid"] for a in _load_anchors() if a.get("bvid") == bvid}
    rows = []
    for r in analyzed.get("_rows", []):
        if r.get("rpid") in anchors:
            continue  # 已人工确认过的不再进审查队列
        if cat_filter and r.get("category") != cat_filter:
            continue
        rows.append(r)
    random.seed(11)
    random.shuffle(rows)
    return ok({
        "bvid": bvid, "total": len(rows),
        "items": [{"rpid": r["rpid"], "text": r["text"], "model_category": r.get("category"),
                   "confidence": r.get("confidence"), "reason": r.get("reason"), "like": r.get("like")} for r in rows[:size]],
    })


@app.route("/api/review", methods=["POST"])
def api_review_post():
    """二次审查提交：用户对大模型分类的评论给出最终判定。
    body: {items: [{rpid,bvid,text,model_category,final_category}]}
    修正/确认的评论均写入锚定集(提升后续分类)。
    """
    body = request.get_json(force=True) or {}
    items = body.get("items") or ([body["item"]] if body.get("item") else [])
    if not items:
        return err("没有审查内容")
    anchors = _load_anchors()
    by_rpid = {a["rpid"]: a for a in anchors}
    added = 0
    for it in items:
        final = it.get("final_category") or it.get("category")
        if final not in CATEGORIES or not it.get("rpid") or not it.get("text"):
            continue
        prev = by_rpid.get(it["rpid"])
        by_rpid[it["rpid"]] = {
            "rpid": it["rpid"], "bvid": it.get("bvid"), "text": it["text"],
            "category": final, "source": "review",
            "model_category": it.get("model_category"),
            "corrected": bool(prev and prev.get("category") != final),
            "updated_at": datetime.now().isoformat(),
        }
        added += 1
    _save_anchors(list(by_rpid.values()))
    return ok({"added": added, "count": len(by_rpid)})


# ---------- 触发分析 ----------
def _run_analysis(bvid, model_override="", progress_cb=None):
    anchors = _load_anchors()
    anchors_for_bvid = [a for a in anchors if a.get("bvid") == bvid]
    if not anchors_for_bvid:
        raise RuntimeError(f"该视频({bvid})还没有人工标注锚定集")
    retriever = sa.AnchorRetriever(
        [{"text": a["text"], "category": a["category"]} for a in anchors_for_bvid])
    corpus = _corpus(bvid)
    items = [{
        "rpid": c["rpid"], "bvid": c["bvid"], "text": c["text"],
        "ctime": c.get("ctime"), "like": c.get("like", 0),
    } for c in corpus.get("comments", []) if c.get("text")]
    cfg = {"analysis_dir": ANALYSIS_DIR, "tag": f"{bvid}_analyzed"}
    analyzer = sa.SentimentAnalyzer(cfg)
    if model_override:
        analyzer.model = model_override
    rows = analyzer.classify_many(items, retriever, concurrency=CFG.get("concurrency", 6))
    # 把逐条结果附加进聚合
    agg = sa.aggregate(rows, corpus.get("meta", {}))
    agg["_rows"] = rows
    out = os.path.join(ANALYSIS_DIR, f"{bvid}_analyzed.json")
    _write_json(out, agg)
    return agg


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """触发分析。body: {bvid, model_override?}
    说明：使用当前锚定集 + 微调后模型(或 glm-4-flash) 分析该视频全量评论。
    耗时较长，前端轮询 /api/analyze/status 获取进度。
    """
    body = request.get_json(force=True) or {}
    bvid = body.get("bvid")
    if not bvid:
        return err("缺少 bvid")
    model_override = body.get("model") or ""

    total = sum(1 for c in _corpus(bvid).get("comments", []) if c.get("text"))
    job = {"status": "running", "bvid": bvid, "done": 0, "total": total, "error": ""}
    _ANALYSIS_JOBS[bvid] = job

    def worker():
        try:
            agg = _run_analysis(bvid, model_override=model_override)
            job["status"] = "done"
            job["done"] = agg.get("total", 0)
            job["count"] = agg.get("total", 0)
            job["category_count"] = agg.get("category_count")
        except Exception as e:
            job["status"] = "error"
            job["error"] = str(e)
            traceback.print_exc()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return ok({"bvid": bvid, "status": "started"})


def _analysis_progress(bvid):
    """从断点 jsonl 统计已完成条数(批量落盘，非逐条实时)"""
    p = os.path.join(ANALYSIS_DIR, f"{bvid}_analyzed.jsonl")
    n = 0
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if line.strip():
                    n += 1
    return n


@app.route("/api/analyze/status", methods=["GET"])
def api_analyze_status():
    bvid = request.args.get("bvid")
    job = _ANALYSIS_JOBS.get(bvid)
    a = _analyzed(bvid)
    if job and job["status"] == "running":
        done = _analysis_progress(bvid)
        total = job.get("total", 0)
        return ok({"status": "running", "done": done, "total": total,
                   "progress": round(done / total, 4) if total else 0})
    if job and job["status"] == "error" and not a:
        return ok({"status": "error", "error": job.get("error", "分析失败")})
    if a:
        return ok({"status": "done", "total": a.get("total", 0), "category_count": a.get("category_count")})
    return ok({"status": "idle"})


@app.route("/api/categories")
def api_categories():
    return ok({"categories": CATEGORIES, "colors": CAT_COLORS})


# ---------- 关系图谱 ----------
_GRAPH_TERM_LIMIT = 24
_GRAPH_COMMENT_DEFAULT = 520
_GRAPH_COMMENT_MAX = 1400
_GRAPH_SIM_THRESHOLD = 0.35
_GRAPH_CACHE = {}


def _analyzed_comment_categories(bvid):
    """读取模型逐条分类的断点文件(data/analysis/{bvid}_analyzed.jsonl)，供评论节点着色。"""
    path = os.path.join(ANALYSIS_DIR, f"{bvid}_analyzed.jsonl")
    out = {}
    if not os.path.exists(path):
        return out
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("category") in CATEGORIES and row.get("rpid") is not None:
                    out[str(row["rpid"])] = row["category"]
    except OSError:
        return out
    return out


def _term_node_index(idx, by_id):
    """词条/别名 -> 图谱词条节点。未进入图谱的词典词条仍保留情感，用于评论归类投票。"""
    out = {}
    for key, rec in idx.items():
        node_id = f"term:{key}" if f"term:{key}" in by_id else ""
        info = {"term": rec.get("term") or key, "sentiment": rec.get("sentiment") or "",
                "node_id": node_id}
        for name in [rec.get("term") or ""] + list(rec.get("aliases") or []):
            name = (name or "").strip().lower()
            if name:
                out.setdefault(name, info)
    return out


def _graph_cache_key(limit):
    paths = [os.path.join(CRAWLED_DIR, f"{v['bvid']}.json") for v in _videos()]
    paths += [os.path.join(ANALYSIS_DIR, f"{v['bvid']}_analyzed.jsonl") for v in _videos()]
    paths += [os.path.join(DATA_DIR, n) for n in ("slang_dict.json", "rag_knowledge.json")]
    stamp = []
    for p in paths:
        try:
            stamp.append(os.path.getmtime(p))
        except OSError:
            stamp.append(0)
    return (limit, tuple(stamp))


def _slang_index():
    """合并网络用语词典与RAG知识库：小写词条 -> 情感/释义/别名/示例"""
    idx = {}
    for name in ("slang_dict.json", "rag_knowledge.json"):
        for e in _read_json(os.path.join(DATA_DIR, name), {}).get("entries", []):
            term = (e.get("term") or "").strip()
            if not term:
                continue
            rec = idx.setdefault(term.lower(), {"term": term, "sentiment": "", "meaning": "",
                                                "note": "", "aliases": [], "examples": []})
            rec["sentiment"] = rec["sentiment"] or (e.get("sentiment") or "")
            rec["meaning"] = rec["meaning"] or (e.get("meaning") or "")
            rec["note"] = rec["note"] or (e.get("note") or "")
            for a in e.get("aliases") or []:
                if a and a not in rec["aliases"]:
                    rec["aliases"].append(a)
            for x in e.get("examples") or []:
                if x and x not in rec["examples"]:
                    rec["examples"].append(x)
    return idx


@app.route("/api/graph")
def api_graph():
    """首页关系图谱：视频 → 网络用语 → 评论，两个视频作为左右总节点。

    query.comments: 每个视频注入的评论节点上限(0 关闭评论层)，默认 520。
    评论层边：视频→评论(归属)、评论→词条(提及)、评论↔评论(字符 bigram Jaccard 相似)。
    情感类别/社区不再作为大节点出现，只保留为评论颜色与筛选依据。
    """
    try:
        limit = int(request.args.get("comments", _GRAPH_COMMENT_DEFAULT))
    except ValueError:
        limit = _GRAPH_COMMENT_DEFAULT
    limit = max(0, min(limit, _GRAPH_COMMENT_MAX))

    cache_key = _graph_cache_key(limit)
    if cache_key in _GRAPH_CACHE:
        return ok(_GRAPH_CACHE[cache_key])

    idx = _slang_index()
    nodes, by_id, edges = [], {}, []

    def add(nid, label, kind, weight, extra=None):
        n = by_id.get(nid)
        if n is None:
            n = {"id": nid, "label": label, "kind": kind, "weight": 0, "degree": 0}
            if extra:
                n.update(extra)
            by_id[nid] = n
            nodes.append(n)
        n["weight"] += max(0, weight or 0)
        return n

    term_recs = {}
    video_ctx = []
    for v in _videos():
        bvid = v["bvid"]
        corpus = _corpus(bvid)
        meta = corpus.get("meta", {})
        analyzed = _analyzed(bvid) or {}
        count = corpus.get("count") or len(corpus.get("comments", []))
        vid_id = f"vid:{bvid}"
        add(vid_id, v.get("name") or bvid, "video", count, {
            "bvid": bvid, "community": v["community"], "community_full": v.get("community_full", ""),
            "color": v.get("color", ""),
            "title": meta.get("title", ""), "owner": meta.get("owner", ""),
            "reply_count": meta.get("reply_count", 0),
            "anchor_count": sum(1 for a in _load_anchors() if a.get("bvid") == bvid),
            "analyzed": bool(analyzed),
        })

        for w in (analyzed.get("top_slang") or _corpus_top_slang(bvid))[:_GRAPH_TERM_LIMIT]:
            term = (w.get("term") or "").strip()
            if not term:
                continue
            key, n = term.lower(), int(w.get("count") or 0)
            rec = idx.get(key, {})
            t = term_recs.setdefault(key, {
                "label": rec.get("term") or term,
                "sentiment": rec.get("sentiment") or "未收录",
                "meaning": rec.get("meaning") or "",
                "note": rec.get("note") or "",
                "aliases": rec.get("aliases") or [],
                "examples": (rec.get("examples") or [])[:2],
                "count": 0, "videos": [],
            })
            t["count"] += n
            if v.get("name") and v["name"] not in t["videos"]:
                t["videos"].append(v["name"])
            add(f"term:{key}", t["label"], "term", n)
            edges.append({"source": vid_id, "target": f"term:{key}", "relation": "出现", "weight": n, "pending": False})

        video_ctx.append((v, vid_id, corpus, analyzed))

    for key, t in term_recs.items():
        by_id[f"term:{key}"].update({
            "sentiment": t["sentiment"], "meaning": t["meaning"], "note": t["note"],
            "aliases": t["aliases"], "examples": t["examples"],
            "videos": t["videos"], "count": t["count"]})

    # ---- 评论层：把爬取语料中的真实评论注入图谱 ----
    comment_stats = {"comments": 0, "sim_edges": 0, "mention_edges": 0,
                     "near_dup_nodes": 0, "corpus_near_dup": 0, "corpus_unique": 0,
                     "avg_sim": 0, "max_sim": 0,
                     "comment_corpus": 0, "threshold": _GRAPH_SIM_THRESHOLD}
    if limit:
        term_index = _term_node_index(idx, by_id)
        sim_sum, sim_n, max_sum = 0.0, 0, 0.0
        for v, vid_id, corpus, analyzed in video_ctx:
            bvid = v["bvid"]
            layer = cg.build_comment_layer(
                corpus.get("comments", []), video_id=vid_id, bvid=bvid,
                community=v["community"], color=v.get("color", ""),
                term_index=term_index, quota=limit,
                threshold=_GRAPH_SIM_THRESHOLD,
                analyzed_categories=_analyzed_comment_categories(bvid),
                rng_seed=20261022 + sum(ord(ch) for ch in bvid))
            for n in layer["nodes"]:
                n.setdefault("degree", 0)
                by_id[n["id"]] = n
                nodes.append(n)
            edges.extend(layer["edges"])
            s = layer["stats"]
            comment_stats["comments"] += s["sampled"]
            comment_stats["sim_edges"] += s["sim_edges"]
            comment_stats["mention_edges"] += s.get("mention_edges", 0)
            comment_stats["near_dup_nodes"] += s["linked"]
            comment_stats["corpus_near_dup"] += s.get("corpus_linked", 0)
            comment_stats["corpus_unique"] += s.get("unique", 0)
            comment_stats["comment_corpus"] += s["raw"]
            sim_sum += s["avg_sim"] * s["sim_edges"]
            sim_n += s["sim_edges"]
            max_sum = max(max_sum, s["max_sim"])
        comment_stats["avg_sim"] = round(sim_sum / max(1, sim_n), 3)
        comment_stats["max_sim"] = round(max_sum, 3)

    for e in edges:
        by_id[e["source"]]["degree"] += 1
        by_id[e["target"]]["degree"] += 1

    payload = {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "nodes": len(nodes), "edges": len(edges), "terms": len(term_recs),
            "videos": len(video_ctx), "corpus": sum(n["weight"] for n in nodes if n["kind"] == "video"),
            "analyzed": sum(1 for n in nodes if n["kind"] == "video" and n.get("analyzed")),
            **comment_stats,
        },
    }
    _GRAPH_CACHE[cache_key] = payload
    while len(_GRAPH_CACHE) > 4:
        _GRAPH_CACHE.pop(next(iter(_GRAPH_CACHE)))
    return ok(payload)


@app.route("/api/rag/search")
def api_rag_search():
    """网络用语RAG知识库检索。query: q, k"""
    q = request.args.get("q", "")
    k = int(request.args.get("k", 6))
    from rag_knowledge import make_kb
    kb = make_kb()
    hits = kb.search(q, k=k)
    return ok({"query": q, "items": hits})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"破妄 · 评论情感分析平台 http://localhost:{port}")
    app.run(host="127.0.0.1", port=port, debug=True, threaded=True)
