# -*- coding: utf-8 -*-
"""破妄 · 锚定集检索式评论分类引擎
方法论：
  1. 锚定集(anchors)：人工精标样本(两视频各100条起,可随时扩充)，作为所有评论的分类依赖模板。
  2. 检索式参照：每条待分类评论与锚定集做文本相似度检索，取最相近的 Top-K 条注入 prompt，
     让模型"参照模板"归类 -> 网络用语特化的可解释落地。
  3. LangChain + 智谱GLM(OpenAI兼容) 结构化输出：{category, confidence, reason, slang_tags}
  4. 断点续采(按批落盘) + 聚合统计。
四分类：赞美 / 贬低 / 水军 / 无意义。网络用语词典来自 data/slang_dict.json。
默认模型 glm-4-flash(免费)，连续限流自动降级 glm-4-flash-250414。
"""
import os
import json
import re
import random
import asyncio
from datetime import datetime
from collections import Counter

from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

CATEGORIES = ["赞美", "贬低", "水军", "无意义"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_project_config():
    """从 data/config.json 读取项目配置(API Key 等)，不进文档/不提交。utf-8-sig 兼容带BOM文件"""
    p = os.path.join(BASE_DIR, "data", "config.json")
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return {}


# ---------- 结构化输出模型 ----------
class CommentLabel(BaseModel):
    category: str = Field(description="四分类之一：赞美/贬低/水军/无意义")
    confidence: float = Field(description="置信度 0~1")
    reason: str = Field(description="一句话归因(中文,30字内)")
    slang_tags: list = Field(description="评论中出现的网络用语词列表，无则空数组")


# ---------- 文本相似度检索 ----------
def _ngrams(text, n=2):
    text = re.sub(r"\s+", "", text or "")
    if len(text) < n:
        return [text]
    return [text[i:i + n] for i in range(len(text) - n + 1)]


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


class AnchorRetriever:
    """从锚定集检索与待分类评论最相似的 Top-K 样本"""

    def __init__(self, anchors):
        self.anchors = anchors  # list of {text, category}
        self._by_cat = {}
        for a in anchors:
            self._by_cat.setdefault(a["category"], []).append(a)

    def retrieve(self, text, k=6, min_score=0.0, exclude_text=None):
        """按字符bigram jaccard 相似度取 Top-K，倾向各分类均衡。
        exclude_text: 评测锚定集自身时排除完全相同的样本，防止金标泄漏。
        """
        ng = _ngrams(text)
        scored = [(a, _jaccard(ng, _ngrams(a["text"]))) for a in self.anchors
                  if exclude_text is None or a["text"] != exclude_text]
        scored.sort(key=lambda x: x[1], reverse=True)
        picked = [a for a, s in scored[:k] if s >= min_score]
        return picked


# ---------- 提示词构建 ----------
def build_system_prompt(slang_dict):
    slang_lines = []
    for e in slang_dict.get("entries", []):
        slang_lines.append(f"- {e['term']}: {e.get('meaning','')}(倾向:{e.get('sentiment','中性')})")
    slang_block = "\n".join(slang_lines[:80])
    return f"""你是一名资深的互联网社区评论情感分析专家，专精中文网络用语与B站饭圈/游戏社区文化。
你的任务：把每条B站评论严格归入四类之一。

四分类定义：
- 赞美：对视频内容/演唱者/游戏/作品表达明确喜爱、支持、肯定、夸赞、感动。
- 贬低：对内容或主体表达不满、批评、嘲讽、贬低、质疑(如指责假唱/修音/质量差)。
- 水军：被购买的评论——伪装成真实用户发布的付费夸赞或付费差评(组织化控评、模板化夸赞/抹黑话术及其复制粘贴变体)。
- 无意义：纯表情、单字灌水(哈哈哈哈/前排/来了/沙发)、抢楼占位、与视频内容无关的闲聊，以及"关注我/加V领福利"式显性引流广告。

网络用语参考词典(部分)：
{slang_block}

注意：
- 严格四分类，每条必属其一，不要输出四类之外。
- 无相近模板时若确实无法判断，选择最接近的一类并降低置信度。
- 输出严格 JSON。"""


def build_user_prompt(text, refs, rag_lines=None):
    ref_lines = []
    for i, a in enumerate(refs, 1):
        ref_lines.append(f"{i}. 评论：「{a['text']}」 -> {a['category']}")
    ref_block = "\n".join(ref_lines) if ref_lines else "(无相近参照模板)"
    rag_block = "\n".join(rag_lines) if rag_lines else "(无相关网络用语知识)"
    return f"""请对下面这条B站评论进行分类。

【相近参照样本】(这些是已被人工确认的同类评论，请参照它们的归类习惯)：
{ref_block}

【网络用语知识库】(检索到的相关网络用语，用于理解评论里的梗)：
{rag_block}

【待分类评论】：
「{text}」

请输出 JSON，格式：{{"category": "赞美|贬低|水军|无意义", "confidence": 0.0~1.0, "reason": "一句话归因", "slang_tags": ["出现的网络用语词"]}}"""


# ---------- 分类引擎 ----------
class SentimentAnalyzer:
    def __init__(self, config):
        cfg = load_project_config()
        self.config = config
        self.api_key = config.get("api_key") or cfg.get("api_key", "")
        self.model = config.get("model") or cfg.get("fine_tuned_model") or cfg.get("model", "glm-4-flash")
        self.fallback_model = cfg.get("fallback_model", "glm-4-flash-250414")
        self.base_url = config.get("base_url") or cfg.get("base_url", "https://open.bigmodel.cn/api/paas/v4/")
        self.out_dir = config.get("analysis_dir", os.path.join(BASE_DIR, "data", "analysis"))
        self.slang = json.load(open(os.path.join(BASE_DIR, "data", "slang_dict.json"), encoding="utf-8"))
        from rag_knowledge import make_kb
        self.rag_kb = make_kb()  # 网络用语RAG知识库，检索时注入prompt
        os.makedirs(self.out_dir, exist_ok=True)
        self.llm = self._make_llm(self.model)
        self.parser = JsonOutputParser(pydantic_object=CommentLabel)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", build_system_prompt(self.slang)),
            ("human", "{input}"),
        ])
        self.chain = self.prompt | self.llm | self.parser
        self._rate_strikes = 0

    def _make_llm(self, model):
        return ChatOpenAI(
            model=model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=0.1,
            max_tokens=300,
            request_timeout=90,
        )

    def _handle_rate(self, msg, rpid):
        """连续触发限流时自动降级到备用模型"""
        if "429" not in msg and "1305" not in msg and "rate" not in msg.lower():
            return None
        self._rate_strikes += 1
        if self._rate_strikes >= 3 and self.llm.model_name != self.fallback_model:
            print(f"[model] {rpid} 连续限流，降级 {self.model} -> {self.fallback_model}", flush=True)
            self.llm = self._make_llm(self.fallback_model)
            self.chain = self.prompt | self.llm | self.parser
            self._rate_strikes = 0
        return 5 + self._rate_strikes * 2

    # ---------- 批量分类 ----------
    def classify_many(self, items, retriever, concurrency=8, save_every=20, resume=True):
        """items: list of {rpid, text, ...}
        并发调用，每批落盘。resume=True 时跳过已分析过的 rpid。
        """
        done_path = os.path.join(self.out_dir, self.config.get("tag", "result") + ".jsonl")
        seen = set()
        if resume and os.path.exists(done_path):
            with open(done_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            seen.add(json.loads(line).get("rpid"))
                        except Exception:
                            pass
        todo = [it for it in items if it.get("rpid") not in seen]
        print(f"[classify] 待分析 {len(todo)} 条 (已跳过 {len(items)-len(todo)})", flush=True)

        async def worker():
            sem = asyncio.Semaphore(concurrency)
            buffer = []
            n_done = 0

            async def one(it):
                nonlocal n_done
                async with sem:
                    refs = retriever.retrieve(it["text"], k=6)
                    rag_items = self.rag_kb.search(it["text"], k=3)
                    rag_lines = self.rag_kb.format_for_prompt(rag_items)
                    user = build_user_prompt(it["text"], refs, rag_lines=rag_lines)
                    row = None
                    for attempt in range(4):
                        try:
                            res = await self.chain.ainvoke({"input": user})
                            cat = res.get("category", "无意义")
                            if cat not in CATEGORIES:
                                cat = "无意义"
                            conf = float(res.get("confidence", 0.0) or 0.0)
                            conf = max(0.0, min(1.0, conf))
                            slang = res.get("slang_tags") or []
                            if isinstance(slang, str):
                                slang = [slang]
                            row = {
                                "rpid": it["rpid"],
                                "bvid": it.get("bvid"),
                                "text": it["text"],
                                "ctime": it.get("ctime"),
                                "like": it.get("like", 0),
                                "category": cat,
                                "confidence": conf,
                                "reason": res.get("reason", ""),
                                "slang_tags": slang,
                            }
                            break
                        except Exception as e:
                            msg = str(e)
                            wait = self._handle_rate(msg, it["rpid"])
                            if wait is not None:
                                print(f"[rate] {it['rpid']} 触发限流，等待{wait}s 重试", flush=True)
                                await asyncio.sleep(wait)
                                continue
                            print(f"[err] {it['rpid']}: {msg[:120]}", flush=True)
                            break
                    if row:
                        buffer.append(row)
                        n_done += 1

            for i in range(0, len(todo), concurrency):
                batch = todo[i:i + concurrency]
                await asyncio.gather(*[one(it) for it in batch])
                if len(buffer) >= save_every:
                    self._append(done_path, buffer)
                    print(f"[classify] 已保存 {len(buffer)} 条 (累计{n_done}/{len(todo)})", flush=True)
                    buffer.clear()
            if buffer:
                self._append(done_path, buffer)
                print(f"[classify] 已保存最后 {len(buffer)} 条", flush=True)

        asyncio.run(worker())
        return self._read_all(done_path)

    @staticmethod
    def _append(path, rows):
        with open(path, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    @staticmethod
    def _read_all(path):
        rows = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
        return rows


# ---------- 聚合统计 ----------
def aggregate(rows, video_meta=None):
    """把逐条分类结果聚合成分析JSON，供前端看板使用"""
    total = len(rows)
    cat_count = Counter(r["category"] for r in rows)
    monthly = {}
    for r in rows:
        if r.get("ctime"):
            key = datetime.fromtimestamp(r["ctime"]).strftime("%Y-%m")
            monthly.setdefault(key, Counter())[r["category"]] += 1
    trend = []
    for k in sorted(monthly):
        trend.append({"month": k, **{c: monthly[k][c] for c in CATEGORIES}})
    slang_count = Counter()
    slang_by_cat = {c: Counter() for c in CATEGORIES}
    for r in rows:
        for t in r.get("slang_tags") or []:
            t = (t or "").strip()
            if t:
                slang_count[t] += 1
                slang_by_cat[r["category"]][t] += 1
    top_slang = [{"term": t, "count": n} for t, n in slang_count.most_common(30)]
    representative = {}
    for c in CATEGORIES:
        pool = [r for r in rows if r["category"] == c]
        pool.sort(key=lambda r: r.get("confidence", 0), reverse=True)
        representative[c] = pool[:5]
    shui = [r for r in rows if r["category"] == "水军"]
    shui.sort(key=lambda r: r.get("confidence", 0), reverse=True)
    graph = build_attitude_graph(rows, max_nodes=120)
    return {
        "meta": video_meta or {},
        "total": total,
        "category_count": {c: cat_count.get(c, 0) for c in CATEGORIES},
        "category_ratio": {c: round(cat_count.get(c, 0) / total, 4) if total else 0 for c in CATEGORIES},
        "trend": trend,
        "top_slang": top_slang,
        "slang_by_category": {c: [{"term": t, "count": n} for t, n in slang_by_cat[c].most_common(15)] for c in CATEGORIES},
        "representative": {c: representative[c] for c in CATEGORIES},
        "shui_shu_highlights": shui[:10],
        "attitude_graph": graph,
    }


def build_attitude_graph(rows, max_nodes=140, max_edges=500):
    """评论态度节点关系图 v2
    节点：按 (点赞 + 含网络用语加成 + 置信度) 打分，四分类配额选取，近重复文本去重。
    边：共享网络用语(权重2/个) 或 文本bigram相似>=0.45(sim*10)；跨类共享梗的边尤其有洞察价值。
    节点字段附月份，供前端提示时间分布。
    """
    if not rows:
        return {"nodes": [], "links": []}
    from collections import defaultdict

    def score(r):
        return (r.get("like", 0) + (30 if r.get("slang_tags") else 0)
                + r.get("confidence", 0) * 20)

    by_cat = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)
    picked = []
    per = max(1, max_nodes // 4)
    for c in CATEGORIES:
        pool = sorted(by_cat.get(c, []), key=score, reverse=True)
        taken = 0
        cat_sets = []
        for r in pool:
            if taken >= per:
                break
            bg = _ngrams(r.get("text", ""))
            dup = any(_jaccard(bg, s) >= 0.6 for s in cat_sets[-120:])
            if dup or not (r.get("text") or "").strip():
                continue
            cat_sets.append(bg)
            picked.append(r)
            taken += 1
    picked = picked[:max_nodes]
    nodes = []
    for i, r in enumerate(picked):
        month = ""
        if r.get("ctime"):
            month = datetime.fromtimestamp(r["ctime"]).strftime("%Y-%m")
        nodes.append({
            "id": str(i), "rpid": r["rpid"], "category": r.get("category"),
            "value": r.get("like", 0) + 1, "confidence": round(r.get("confidence", 0), 2),
            "text": (r.get("text") or "")[:60], "slang_tags": r.get("slang_tags", []),
            "month": month,
        })
    # 边：共享网络用语 或 高文本相似
    links = []
    seen_edges = set()
    ngs = [_ngrams(n["text"]) for n in nodes]
    tags = [set(t for t in n["slang_tags"] if t) for n in nodes]
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            if len(links) >= max_edges:
                break
            shared = len(tags[i] & tags[j])
            sim = _jaccard(ngs[i], ngs[j])
            weight = shared * 2 + sim * 10
            if weight >= 0.45:
                key = (nodes[i]["id"], nodes[j]["id"])
                if key not in seen_edges:
                    seen_edges.add(key)
                    cross = nodes[i]["category"] != nodes[j]["category"]
                    links.append({"source": nodes[i]["id"], "target": nodes[j]["id"],
                                  "value": round(weight, 2), "cross": cross})
    return {"nodes": nodes, "links": links}


# ---------- CLI ----------
def load_anchors(path):
    data = json.load(open(path, encoding="utf-8"))
    anchors = []
    if isinstance(data, list):
        anchors = [{"text": a.get("text"), "category": a.get("category")} for a in data if a.get("text") and a.get("category")]
    elif isinstance(data, dict) and "anchors" in data:
        anchors = [{"text": a.get("text"), "category": a.get("category")} for a in data["anchors"] if a.get("text") and a.get("category")]
    return anchors


def load_corpus(crawled_json):
    data = json.load(open(crawled_json, encoding="utf-8"))
    items = []
    for c in data.get("comments", []):
        items.append({
            "rpid": c.get("rpid"),
            "bvid": c.get("bvid"),
            "text": c.get("text", ""),
            "ctime": c.get("ctime"),
            "like": c.get("like", 0),
        })
    return items, data.get("meta", {})


if __name__ == "__main__":
    import fire

    def run(anchors_path, bvid, crawled_dir="data/crawled", analysis_dir="data/analysis",
            api_key="", model="", tag="", concurrency=8, limit=0):
        """对单个视频的全量评论分类。tag 缺省用 bvid。"""
        import os as _os
        base = _os.path.dirname(_os.path.abspath(__file__))
        anchors = load_anchors(_os.path.join(base, anchors_path))
        print(f"[anchors] 载入锚定集 {len(anchors)} 条")
        crawled_json = _os.path.join(base, crawled_dir, f"{bvid}.json")
        items, meta = load_corpus(crawled_json)
        if limit:
            random.seed(42)
            items = random.sample(items, min(limit, len(items)))
        print(f"[corpus] 载入评论 {len(items)} 条")
        config = {
            "api_key": api_key, "model": model,
            "analysis_dir": _os.path.join(base, analysis_dir),
            "tag": tag or bvid,
        }
        analyzer = SentimentAnalyzer(config)
        retriever = AnchorRetriever(anchors)
        rows = analyzer.classify_many(items, retriever, concurrency=concurrency)
        print(f"[classify] 完成 {len(rows)} 条")
        agg = aggregate(rows, meta)
        out = _os.path.join(config["analysis_dir"], f"{tag or bvid}_analyzed.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(agg, f, ensure_ascii=False, indent=1)
        print(f"[analysis] 聚合完成 -> {out}")
        print("  分类分布:", agg["category_count"])

    fire.Fire(run)