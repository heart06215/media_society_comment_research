"""Reproducible three-method evaluation on one grouped human-label holdout."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import random
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATEGORIES = ["赞美", "贬低", "水军", "无意义", "社区对骂", "中立"]


def grams(text: str) -> Counter:
    text = re.sub(r"\s+", "", text).lower()
    return Counter([*text, *(text[i:i + 2] for i in range(len(text) - 1))])


def grouped_split(rows: list[dict], seed: int = 42) -> tuple[list[dict], list[dict]]:
    """Keep exact and near-duplicate texts in the same side of a fixed split."""
    parent = list(range(len(rows)))
    tokens = [set(grams(r["text"])) for r in rows]

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(rows)):
        for j in range(i):
            union = tokens[i] | tokens[j]
            similarity = len(tokens[i] & tokens[j]) / len(union) if union else 1
            if similarity >= 0.55:
                parent[root(i)] = root(j)
    groups = {}
    for i, row in enumerate(rows):
        groups.setdefault(root(i), []).append(row)
    candidates = list(groups.values())
    random.Random(seed).shuffle(candidates)
    support = Counter(r["category"] for r in rows)
    selected = Counter()
    test, train = [], []
    for group in candidates:
        sizes = Counter(r["category"] for r in group)
        needed = any(selected[c] < max(1, round(support[c] * 0.3)) for c in sizes)
        keeps_train = all(selected[c] + sizes[c] < support[c] for c in sizes)
        if needed and keeps_train:
            test.extend(group)
            selected.update(sizes)
        else:
            train.extend(group)
    return train, test


class SemanticRetriever:
    """Traditional vector-space retrieval: TF-IDF + cosine nearest exemplar."""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        counts = [grams(r["text"]) for r in rows]
        df = Counter(token for doc in counts for token in doc)
        self.idf = {token: math.log((1 + len(rows)) / (1 + n)) + 1 for token, n in df.items()}
        self.vectors = [self.vector(doc) for doc in counts]
        self.default = Counter(r["category"] for r in rows).most_common(1)[0][0] if rows else "中立"

    def vector(self, counts: Counter) -> dict:
        weighted = {t: (1 + math.log(n)) * self.idf[t] for t, n in counts.items() if t in self.idf}
        norm = math.sqrt(sum(v * v for v in weighted.values())) or 1
        return {t: v / norm for t, v in weighted.items()}

    def classify(self, text: str) -> str:
        query = self.vector(grams(text))
        scores = [sum(query.get(t, 0) * v for t, v in vector.items()) for vector in self.vectors]
        if not scores or max(scores) <= 0:
            return self.default
        return self.rows[max(range(len(scores)), key=scores.__getitem__)]["category"]


def metrics(rows: list[dict]) -> dict:
    n = len(rows)
    per_class, confusion = {}, {}
    for category in CATEGORIES:
        tp = sum(r["gold"] == category and r.get("prediction") == category for r in rows)
        fp = sum(r["gold"] != category and r.get("prediction") == category for r in rows)
        fn = sum(r["gold"] == category and r.get("prediction") != category for r in rows)
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        per_class[category] = {"precision": precision, "recall": recall,
                               "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
                               "support": tp + fn}
        confusion[category] = {p: sum(r["gold"] == category and r.get("prediction") == p for r in rows) for p in [*CATEGORIES, "error"]}
    completed = sum(r.get("prediction") in CATEGORIES for r in rows)
    supported = [v for v in per_class.values() if v["support"]]
    return {"n": n, "completed": completed, "failed": n - completed,
            "correct": sum(r["gold"] == r.get("prediction") for r in rows),
            "accuracy": sum(r["gold"] == r.get("prediction") for r in rows) / n if n else None,
            "macro_f1": sum(v["f1"] for v in per_class.values()) / len(CATEGORIES),
            "supported_macro_f1": sum(v["f1"] for v in supported) / len(supported) if supported else None,
            "per_class": per_class, "confusion": confusion,
            "status": "complete" if completed == n and n else "partial"}


async def llm_predictions(train: list[dict], test: list[dict], mode: str, config: dict, concurrency: int) -> list[dict]:
    import sentiment_analyze as sa
    from benchmark_methods import ZS_SYSTEM, ZS_USER_TMPL
    from langchain_core.messages import HumanMessage, SystemMessage

    selected_model = (config.get("fine_tuned_model") or config.get("model")) if mode == "annotated" else config.get("model")
    analyzer = sa.SentimentAnalyzer({"model": selected_model, "api_key": config.get("api_key"),
                                     "request_timeout": 20, "max_retries": 0})
    retrievers = {bvid: sa.AnchorRetriever([row for row in train if row.get("bvid") == bvid])
                  for bvid in {row.get("bvid") for row in test}}
    semaphore = asyncio.Semaphore(concurrency)

    async def one(item):
        async with semaphore:
            start = time.perf_counter()
            if mode == "llm_zeroshot":
                system, user = ZS_SYSTEM, ZS_USER_TMPL.format(text=item["text"])
                refs, knowledge = [], []
            else:
                system = sa.build_system_prompt(analyzer.slang)
                refs = retrievers[item.get("bvid")].retrieve(item["text"], k=6)
                knowledge = analyzer.rag_kb.search(item["text"], k=3)
                user = sa.build_user_prompt(item["text"], refs, analyzer.rag_kb.format_for_prompt(knowledge))
            row = {"rpid": str(item["rpid"]), "bvid": item.get("bvid"), "gold": item["category"], "prediction": "error",
                   "reference_ids": [str(ref["rpid"]) for ref in refs],
                   "knowledge_terms": [entry["term"] for entry in knowledge]}
            for attempt in range(2):
                try:
                    message = await analyzer.llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
                    label = analyzer.parser.invoke(message)
                    row.update(prediction=label["category"], reason=label["reason"], tokens=message.usage_metadata or {}, model=analyzer.model)
                    break
                except Exception as exc:
                    # Never publish remote error strings, which may contain request details.
                    row["error_type"] = type(exc).__name__
                    if attempt == 0:
                        await asyncio.sleep(2)
            row["latency_seconds"] = round(time.perf_counter() - start, 3)
            print(f"[{mode}] {row['rpid']} {'ok' if row['prediction'] != 'error' else 'failed'}", flush=True)
            return row

    return await asyncio.gather(*(one(item) for item in test))


def load_assistant_review(source: list[dict], path: Path | None = None) -> dict:
    """Score frozen conversation-model judgments against the current human labels."""
    path = path or ROOT / "data/evaluation/assistant_review_2026-11-14.json"
    if not path.exists():
        return {"status": "not_run", "note": "尚未生成会话模型复评记录"}
    review = json.loads(path.read_text(encoding="utf-8"))
    indexed = {}
    for item in review.get("reviews", []):
        key = (item.get("bvid"), str(item.get("rpid")))
        if key in indexed or item.get("prediction") not in CATEGORIES:
            return {"status": "stale", "note": "复评记录存在重复标识或无效分类"}
        indexed[key] = item
    rows = []
    for original in source:
        item = indexed.get((original.get("bvid"), str(original.get("rpid"))))
        digest = hashlib.sha256(original["text"].encode("utf-8")).hexdigest()
        if item is None or item.get("text_sha256") != digest:
            return {"status": "stale", "note": "评论样本已更新，需要补充逐条复评"}
        rows.append({"rpid": str(original["rpid"]), "bvid": original.get("bvid"),
                     "gold": original["category"], "prediction": item["prediction"], "reason": item.get("reason", "")})
    result = metrics(rows)
    result.update({"evaluation_kind": review.get("evaluation_kind", "assistant_offline_review"), "metric_label": "人工标注样本复评准确率",
                   "model": review.get("reviewer", "Codex 会话模型"), "review_date": review.get("review_date"),
                   "procedure": review.get("procedure"), "blinded": review.get("blinded", False),
                   "review_file": path.relative_to(ROOT).as_posix(), "rows": rows})
    return result


def load_augmented_holdout(test: list[dict], train: list[dict]) -> dict:
    path = ROOT / "data/evaluation/augmented_holdout_review_2026-11-14.json"
    if not path.exists():
        return {"status": "not_run", "note": "尚未生成标注增强留出复评"}
    review = json.loads(path.read_text(encoding="utf-8"))
    train_ids = {str(row["rpid"]) for row in train}
    test_ids = {str(row["rpid"]) for row in test}
    training_digest = hashlib.sha256(json.dumps(train, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    input_path = ROOT / "data/evaluation/augmented_holdout_inputs_2026-11-14.json"
    if not input_path.exists():
        return {"status": "stale", "note": "缺少对应的检索输入记录"}
    if (train_ids & test_ids or set(review.get("train_ids", [])) != train_ids
            or set(review.get("test_ids", [])) != test_ids
            or review.get("training_source_sha256") != training_digest
            or review.get("inputs_sha256") != hashlib.sha256(input_path.read_bytes()).hexdigest()
            or any(not set(row.get("reference_ids", [])).issubset(train_ids) for row in review.get("reviews", []))):
        return {"status": "stale", "note": "分组或参照样本已更新，需要重新复评"}
    result = load_assistant_review(test, path)
    result.update(metric_label="分组留出复评准确率", parameters=review.get("parameters", {}))
    return result


def add_snapshot_review(report: dict, source: list[dict], train: list[dict], test: list[dict]) -> None:
    """Existing exemplars may have been retrieved during analysis; never call this accuracy."""
    predictions = {}
    for path in (ROOT / "data/analysis").glob("*_analyzed.json"):
        bvid = path.name.removesuffix("_analyzed.json")
        for row in json.loads(path.read_text(encoding="utf-8")).get("_rows", []):
            predictions[(bvid, str(row.get("rpid")))] = row
    rows = [{"rpid": str(a["rpid"]), "gold": a["category"],
             "prediction": predictions.get((a.get("bvid"), str(a["rpid"])), {}).get("category", "error")}
            for a in source]
    result = metrics(rows)
    result["agreement"] = result.pop("accuracy")
    result.update({"evaluation_kind": "historical_consistency", "independent": False,
                   "metric_label": "历史锚定样本标签一致率", "rows": rows,
                   "note": "这些人工示例参与过检索；107条标签一致不能作为独立准确率或参数微调增益。"})
    report["historical_snapshot"] = result
    report["assistant_full_review"] = load_assistant_review(source)
    report["methods"]["semantic"]["metric_label"] = "分组留出测试准确率"
    report["conversation_trials"] = {"direct": load_assistant_review(test), "augmented": load_augmented_holdout(test, train),
                                      "purpose": "会话内方案试读，保留逐条记录，不作为项目模型的正式评测结果。"}
    for mode in ("llm_zeroshot", "annotated"):
        current = report["methods"].get(mode) or {}
        if current.get("evaluation_kind") != "project_model_paired":
            report["methods"][mode] = {"status": "awaiting_model_run", "n": len(test), "completed": 0, "failed": 0,
                                        "evaluation_kind": "project_model_paired", "metric_label": "项目模型配对评测准确率"}
    majority = Counter(row["category"] for row in train).most_common(1)[0][0]
    report["methods"]["semantic"]["majority_baseline_accuracy"] = sum(row["category"] == majority for row in test) / len(test)
    report["comparison_note"] = "项目模型对照固定同一批留出评论：基础模型直接分类，对比同视频人工示例Top6、圈层知识Top3增强的完整流程。会话试读另行归档。"
    report["offline_analysis"] = [
        {"method": "semantic", "strength": "无需模型调用，按字符向量相似性复用标签", "limitation": "按词面相似性匹配，语境解释由后续模型分析补充"},
        {"method": "llm_zeroshot", "strength": "基础模型按六分类定义直接判断评论", "limitation": f"配对评测样本：{len(test)} 条留出评论"},
        {"method": "annotated", "strength": "接入同视频人工标注库、圈层知识和结构校验的完整分类流程", "limitation": "人工示例Top6 · 圈层知识Top3 · 保留分类理由与检索记录"},
    ]


def run(methods="semantic", concurrency=3, seed=42, bvid="", offline=True, **_):
    source = json.loads((ROOT / "data/labels/anchors.json").read_text(encoding="utf-8"))["anchors"]
    source = [r for r in source if r.get("category") in CATEGORIES and r.get("text") and (not bvid or r.get("bvid") == bvid)]
    train, test = grouped_split(source, seed)
    if not train or not test:
        raise ValueError("人工标注不足，无法建立分组留出测试")
    digest = hashlib.sha256(json.dumps(source, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    path = ROOT / "data/analysis/benchmark_report.json"
    report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    test_ids = sorted(str(r["rpid"]) for r in test)
    if report.get("source_sha256") != digest or report.get("test_ids") != test_ids:
        report = {}
    report.update({"schema_version": 2, "time": datetime.now(timezone.utc).isoformat(),
                   "protocol": "人工锚定样本分组留出测试；示例集与测试集按近重复话术隔离，分组阈值0.55",
                   "source_sha256": digest, "seed": seed, "group_threshold": 0.55,
                   "train_count": len(train), "test_count": len(test), "test_ids": test_ids,
                   "train_ids": sorted(str(r["rpid"]) for r in train),
                   "test_distribution": dict(Counter(r["category"] for r in test)),
                   "missing_categories": [c for c in CATEGORIES if not any(r["category"] == c for r in test)],
                   "macro_f1_definition": "六分类宏平均，测试缺失类别计0；另列仅有样本类别的宏平均",
                   "methods": report.get("methods", {}),
                   "parameter_finetune": {"status": "not_trained", "note": "本报告第三档为人工标注增强；未宣称完成参数微调。"}})
    for mode in [m.strip() for m in methods.split(",")]:
        if mode not in {"semantic", "llm_zeroshot", "annotated"}:
            raise ValueError("三档测试支持 semantic,llm_zeroshot,annotated")
        start = time.perf_counter()
        if mode == "semantic":
            retriever = SemanticRetriever(train)
            rows = [{"rpid": str(r["rpid"]), "gold": r["category"], "prediction": retriever.classify(r["text"])} for r in test]
            model = "character-tfidf-cosine"
        else:
            if offline:
                raise ValueError("离线模式不发送评论；在线评测必须显式设置 offline=False 并获得数据传输授权")
            import sentiment_analyze as sa
            config = sa.load_project_config()
            if not config.get("api_key"):
                report["methods"][mode] = {"status": "not_run", "note": "模型密钥未配置"}
                continue
            rows = asyncio.run(llm_predictions(train, test, mode, config, max(1, min(int(concurrency), 6))))
            model = config.get("model", "glm-4-flash")
        result = metrics(rows)
        if mode != "semantic":
            result.update({"evaluation_kind": "project_model_paired", "metric_label": "项目模型配对评测准确率",
                           "reference_k": 6 if mode == "annotated" else 0, "knowledge_k": 3 if mode == "annotated" else 0})
            model = next((row.get("model") for row in rows if row.get("model")), model)
        result.update({"model": model, "elapsed_seconds": round(time.perf_counter() - start, 3),
                       "mean_latency_seconds": round(sum(r.get("latency_seconds", 0) for r in rows) / len(rows), 3),
                       "input_tokens": sum((r.get("tokens") or {}).get("input_tokens", 0) for r in rows),
                       "output_tokens": sum((r.get("tokens") or {}).get("output_tokens", 0) for r in rows),
                       "cost_yuan": None, "cost_note": "未配置实际计费单价，不以免费额度外推总成本", "rows": rows})
        report["methods"][mode] = result
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{mode}] accuracy={result['accuracy']:.2%}, completed={result['completed']}/{len(test)}", flush=True)
    if offline:
        add_snapshot_review(report, source, train, test)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import fire
    fire.Fire(run)
