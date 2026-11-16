# -*- coding: utf-8 -*-
"""破妄 · 表4 四方法对照实验脚本
论文 4.2 节协议：对人工锚定集(金标)分别以四种模式分类，产出 Accuracy / Macro-F1 / 水军Recall。
  dict          基线-词典      本地规则+情感词典打分，不消耗API
  llm_zeroshot  零样本LLM      glm-4-flash 直接分类，无参照、无RAG
  rag           检索式参考+RAG  本文阶段一方案(锚定检索Top-6 + RAG注入，排除自身泄漏)
  finetune      微调LLM        使用 config.fine_tuned_model(为空则跳过)
用法：
  python benchmark_methods.py --selftest=true            # 词典分类器自检(无API)
  python benchmark_methods.py --methods dict             # 仅词典基线
  python benchmark_methods.py                            # 默认离线三档看板记录
产出：默认三档记录写入 benchmark_report.json；旧四方法实验写入 benchmark_legacy_report.json。
"""
import os
import re
import sys
import json
import asyncio
from datetime import datetime
from collections import Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from langchain_core.prompts import ChatPromptTemplate

import sentiment_analyze as sa

CATEGORIES = sa.CATEGORIES
ANCHORS_PATH = os.path.join(BASE_DIR, "data", "labels", "anchors.json")
REPORT_PATH = os.path.join(BASE_DIR, "data", "analysis", "benchmark_legacy_report.json")

# ---------- 零样本提示词(仅六分类定义，无词典/无参照/无RAG) ----------
ZS_SYSTEM = """你是一名资深的互联网社区评论情感分析专家。
你的任务：把每条B站评论严格归入六类之一。

六分类定义：
- 赞美：对视频内容/演唱者/游戏/作品表达明确喜爱、支持、肯定、夸赞、感动。
- 贬低：对内容或主体表达不满、批评、嘲讽、贬低、质疑(如指责假唱/修音/质量差)。
- 水军（组织化刷评）：疑似组织化评论刷取、模板化控评或重复传播的文本特征；不能推断付费身份，仅提及“水军”不是该标签的依据。
- 无意义：纯表情、单字灌水(哈哈哈哈/前排/来了/沙发)、抢楼占位、无意义刷屏口号，以及"关注我/加V领福利"式显性引流广告。
- 社区对骂：评论者之间的互相攻击、拉踩、站队对线、人身攻击、群体嘲讽；矛头指向其他用户或群体。
- 中立：客观陈述事实、提问求证、补充信息、中性讨论，没有明确褒贬情绪，也不是灌水或广告。

注意：
- 严格六分类，每条必属其一，不要输出六类之外。
- 输出严格 JSON。"""

ZS_USER_TMPL = """请对下面这条B站评论进行分类。

【待分类评论】：
「{text}」

请输出 JSON，格式：{{"category": "赞美|贬低|水军|无意义|社区对骂|中立", "confidence": 0.0~1.0, "reason": "一句话归因", "slang_tags": []}}"""

# ---------- 基线-词典：网络用语词典 + 通用情感词表 打分 ----------
AD_RE = re.compile(r"(关注我|点关注|加V|＋V|加微信|私信|主页领|领福利|粉丝群|接推广|接广告|代拍|代抽|出售|出租|扫码)")
WATER_RE = re.compile(r"(水军|买评|刷评|刷好评|控好评|复制粘贴|复制走|一模一样|文案一样|都是同一|同一话术|话术)")
PRAISE_GENERIC = ["好听", "牛", "厉害", "喜欢", "爱了", "爱", "帅", "美", "支持", "感动",
                  "温柔", "天籁", "精彩", "完美", "惊艳", "绝了", "棒", "可爱", "心动",
                  "上头", "无敌", "神了", "期待", "加油", "舒服", "好棒", "好美"]
DEROG_GENERIC = ["难听", "垃圾", "差评", "失望", "退钱", "跑调", "不行", "太差", "恶心",
                 "讨厌", "划水", "下头", "刺耳", "车祸", "水货", "没实力", "假唱"]


class DictBaseline:
    """词典基线：显性引流>水军信号>情感打分>无意义噪声。规则有意简单，作为对照下界。"""

    def __init__(self):
        slang = json.load(open(os.path.join(BASE_DIR, "data", "slang_dict.json"), encoding="utf-8"))
        self.praise = [e["term"] for e in slang["entries"] if e.get("sentiment") == "赞美"] + PRAISE_GENERIC
        self.derog = [e["term"] for e in slang["entries"] if e.get("sentiment") == "贬低"] + DEROG_GENERIC
        self.noise = [e["term"] for e in slang["entries"] if e.get("sentiment") == "无意义"]
        self.water = [e["term"] for e in slang["entries"] if e.get("sentiment") == "水军"]

    def classify(self, text):
        t = text or ""
        if AD_RE.search(t):
            return "无意义"
        if WATER_RE.search(t) or any(w in t for w in self.water):
            return "水军"
        score = sum(t.count(w) for w in self.praise) - sum(t.count(w) for w in self.derog)
        if score > 0:
            return "赞美"
        if score < 0:
            return "贬低"
        if any(w in t for w in self.noise):
            return "无意义"
        return "无意义"


# ---------- 评测 ----------
def _load_anchor_groups(bvid=""):
    if not os.path.exists(ANCHORS_PATH):
        return {}
    d = json.load(open(ANCHORS_PATH, encoding="utf-8"))
    groups = {}
    for a in d.get("anchors", []):
        if a.get("text") and a.get("category") in CATEGORIES:
            if bvid and a.get("bvid") != bvid:
                continue
            groups.setdefault(a.get("bvid"), []).append(a)
    return groups


def _metrics(pairs):
    """pairs: [(gold, pred)] -> Accuracy / Macro-F1 / 水军Recall / 混淆矩阵"""
    n = len(pairs)
    acc = sum(1 for g, p in pairs if g == p) / n if n else 0.0
    per, f1s, conf = {}, {}, {}
    for c in CATEGORIES:
        tp = sum(1 for g, p in pairs if p == c and g == c)
        fp = sum(1 for g, p in pairs if p == c and g != c)
        fn = sum(1 for g, p in pairs if p != c and g == c)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per[c] = {"precision": round(prec, 4), "recall": round(rec, 4),
                  "f1": round(f1, 4), "support": sum(1 for g, _ in pairs if g == c)}
        f1s[c] = f1
        conf[c] = {p: sum(1 for g, pp in pairs if g == c and pp == p) for p in CATEGORIES}
    macro_f1 = sum(f1s.values()) / len(CATEGORIES)
    return {"n": n, "accuracy": round(acc, 4), "macro_f1": round(macro_f1, 4),
            "shuij_recall": per["水军"]["recall"], "per_class": per, "confusion": conf}


async def _llm_rows(analyzer, retriever, items, concurrency, mode):
    """mode: llm_zeroshot(无参照无RAG) / rag(检索式参考+RAG, 排除自身) / finetune(微调模型+同链路)"""
    if mode == "llm_zeroshot":
        chain = (ChatPromptTemplate.from_messages([("system", ZS_SYSTEM), ("human", "{input}")])
                 | analyzer.llm | analyzer.parser)
    else:
        chain = analyzer.chain
    sem = asyncio.Semaphore(concurrency)
    rows = []
    n_done = 0

    async def one(it):
        nonlocal n_done
        async with sem:
            if mode == "llm_zeroshot":
                user = ZS_USER_TMPL.format(text=it["text"])
            else:
                refs = retriever.retrieve(it["text"], k=6, exclude_text=it["text"])
                rag_items = analyzer.rag_kb.search(it["text"], k=3)
                rag_lines = analyzer.rag_kb.format_for_prompt(rag_items)
                user = sa.build_user_prompt(it["text"], refs, rag_lines=rag_lines)
            res = None
            for _ in range(4):
                try:
                    res = await chain.ainvoke({"input": user})
                    break
                except Exception as e:
                    wait = analyzer._handle_rate(str(e), it["rpid"])
                    if wait is not None:
                        print(f"[rate] {it['rpid']} 限流，等待{wait}s", flush=True)
                        await asyncio.sleep(wait)
                        continue
                    print(f"[err] {it['rpid']}: {str(e)[:120]}", flush=True)
                    break
            if res:
                cat = res.get("category", "中立")
                if cat not in CATEGORIES:
                    cat = "中立"
                rows.append({"rpid": it["rpid"], "bvid": it["bvid"], "text": it["text"],
                             "gold": it["category"], "category": cat,
                             "confidence": float(res.get("confidence", 0) or 0)})
                n_done += 1

    for i in range(0, len(items), concurrency):
        batch = items[i:i + concurrency]
        await asyncio.gather(*[one(x) for x in batch])
        print(f"[{mode}] 进度 {n_done}/{len(items)}", flush=True)
    return rows


def _table_row(name, m, note=""):
    if m is None:
        return f"| {name} | — | — | — | {note} |"
    return (f"| {name} | {m['accuracy']:.4f} | {m['macro_f1']:.4f} | {m['shuij_recall']:.4f} | {note} |")


def _selftest():
    db = DictBaseline()
    cases = [
        ("哈哈哈哈哈哈！", "无意义"),
        ("前排", "无意义"),
        ("关注我主页领福利", "无意义"),
        ("yyds！唱功绝绝子", "赞美"),
        ("全程修音对嘴，难听", "贬低"),
        ("控评也太明显了，全是复制粘贴", "水军"),
        ("今天天气不错", "无意义"),
    ]
    bad = 0
    for text, want in cases:
        got = db.classify(text)
        mark = "OK " if got == want else "FAIL"
        if got != want:
            bad += 1
        print(f"[{mark}] 「{text}」 -> {got} (期望 {want})")
    print("词典分类器自检:", "通过" if bad == 0 else f"{bad} 例失败")
    return bad == 0


def run(methods="semantic", bvid="", concurrency=3, limit=0, selftest=False):
    """表4 对照实验。锚定集(data/labels/anchors.json)为金标；--methods 逗号分隔选择方法。"""
    if selftest:
        ok = _selftest()
        sys.exit(0 if ok else 1)

    if methods == "semantic":
        from evaluation import run as run_dashboard_evaluation
        return run_dashboard_evaluation(methods=methods, bvid=bvid, concurrency=concurrency)
    method_list = [m.strip() for m in methods.split(",") if m.strip()]
    groups = _load_anchor_groups(bvid)
    total = sum(len(v) for v in groups.values())
    if not total:
        print("锚定集为空：请先在前端 /label 页完成人工标注(每视频100条)后运行本脚本。")
        print("可先执行 --selftest=true 验证词典基线分类器(无需标注)。")
        sys.exit(1)
    print(f"[anchors] 金标锚定样本 {total} 条 ({', '.join(f'{k}:{len(v)}' for k, v in groups.items())})")

    cfg = sa.load_project_config()
    report = {"time": datetime.now().isoformat(), "anchors": total,
              "methods": {}, "per_video": {}}
    items_all = []
    for bv, arr in groups.items():
        pool = arr if not limit else arr[:limit]
        items_all.extend([{"rpid": a["rpid"], "bvid": bv, "text": a["text"], "category": a["category"]} for a in pool])

    def eval_pairs(pred_rows):
        pairs = [(r["gold"], r["category"]) for r in pred_rows]
        return _metrics(pairs)

    # ---- 基线-词典(本地) ----
    if "dict" in method_list:
        db = DictBaseline()
        rows = [{**it, "gold": it["category"], "category": db.classify(it["text"])} for it in items_all]
        report["methods"]["dict"] = eval_pairs(rows)
        report["per_video"]["dict"] = {}
        for bv, arr in groups.items():
            sub = [{"category": db.classify(a["text"]), "gold": a["category"]} for a in arr]
            report["per_video"]["dict"][bv] = eval_pairs(sub)
        print("[dict] 词典基线完成")

    # ---- LLM 系列共用底座 ----
    llm_methods = [m for m in ("llm_zeroshot", "rag", "finetune") if m in method_list]
    analyzer = None
    if llm_methods:
        analyzer = sa.SentimentAnalyzer({"analysis_dir": os.path.join(BASE_DIR, "data", "analysis"),
                                         "tag": "benchmark"})

    for mode in llm_methods:
        if mode == "finetune":
            ft = cfg.get("fine_tuned_model") or ""
            if not ft:
                report["methods"]["finetune"] = None
                print("[finetune] config.fine_tuned_model 为空，跳过(完成智谱SFT并回填模型ID后重跑)")
                continue
            analyzer.model = ft
            analyzer.llm = analyzer._make_llm(ft)
            analyzer.chain = analyzer.prompt | analyzer.llm | analyzer.parser
        all_rows = []
        for bv, arr in groups.items():
            items = [{"rpid": a["rpid"], "bvid": bv, "text": a["text"], "category": a["category"]}
                     for a in (arr if not limit else arr[:limit])]
            retriever = sa.AnchorRetriever([{"text": a["text"], "category": a["category"]} for a in arr])
            rows = asyncio.run(_llm_rows(analyzer, retriever, items, concurrency, mode))
            all_rows.extend(rows)
            report["per_video"].setdefault(mode, {})[bv] = eval_pairs(rows)
        report["methods"][mode] = eval_pairs(all_rows)
        label = {"llm_zeroshot": "零样本", "rag": "检索式+RAG", "finetune": f"微调({analyzer.model})"}[mode]
        print(f"[{mode}] {label}完成，覆盖 {report['methods'][mode]['n']}/{total}")

    # ---- 汇总输出(表4格式) ----
    names = {"dict": "基线-词典", "llm_zeroshot": "零样本LLM",
             "rag": "检索式参考+RAG", "finetune": "微调LLM"}
    lines = ["| 方法 | Accuracy | Macro-F1 | 水军Recall |", "|---|---|---|---|"]
    for key in ("dict", "llm_zeroshot", "rag", "finetune"):
        if key not in method_list and key not in report["methods"]:
            continue
        m = report["methods"].get(key)
        note = "待回填 config.fine_tuned_model 后重跑" if (key == "finetune" and m is None) else ""
        lines.append(_table_row(names[key], m, note))
    if report["methods"].get("rag") and report["methods"].get("finetune"):
        gain = round(report["methods"]["finetune"]["accuracy"] - report["methods"]["rag"]["accuracy"], 4)
        report["finetune_gain"] = gain
        lines.append(f"\n微调增益(微调Accuracy − 检索式+RAG Accuracy)：{gain:+.4f}")
    table = "\n".join(lines)
    print("\n=== 表4 对照实验结果(对锚定集) ===")
    print(table)

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"\n[report] 已写入 {REPORT_PATH}")


if __name__ == "__main__":
    import fire
    fire.Fire(run)
