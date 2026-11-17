"""Public research reports and portable review datasets; shared by both servers."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

CATEGORY_LABELS = {"水军": "组织化刷评"}
METHODS = (
    ("semantic", "传统语义检索", "字符 TF-IDF 向量与人工示例的余弦近邻分类"),
    ("llm_zeroshot", "大模型", "基础模型按六分类定义直接判断评论"),
    ("annotated", "我们的微调标注大模型", "人工标注库Top6 + 圈层知识Top3 + 结构校验"),
)


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_report(data_dir: Path, config: dict | None = None) -> dict:
    """Only publish explicitly allowed model settings, never credentials."""
    config = config or {}
    anchors = read_json(data_dir / "labels" / "anchors.json", {}).get("anchors", [])
    analyses = [read_json(p, {}) for p in sorted((data_dir / "analysis").glob("*_analyzed.json"))]
    benchmark = read_json(data_dir / "analysis" / "benchmark_report.json", {})
    design_targets = read_json(data_dir / "evaluation" / "method_targets.json", {}).get("targets", {})
    reported_results = read_json(data_dir / "evaluation" / "reported_results.json", {}).get("methods", {})
    counts = Counter(a.get("category") for a in anchors)
    categories = ["赞美", "贬低", "水军", "无意义", "社区对骂", "中立"]
    methods = []
    for key, name, description in METHODS:
        result = (benchmark.get("methods") or {}).get(key)
        if key == "llm_zeroshot" and result and result.get("evaluation_kind") == "assistant_offline_review":
            description = "本次会话模型逐条解读评论，对照人工标签计分"
        if key == "annotated" and result and result.get("evaluation_kind") == "assistant_augmented_holdout":
            description = "会话模型 + Top3人工示例检索 + Top3圈层知识"
        target = design_targets.get(key, {})
        target_value = target.get("accuracy")
        target_record = ({"accuracy": target_value, "metric_kind": "design_target", "label": "目标准确率"}
                         if type(target_value) in (int, float) and 0 <= target_value <= 1 else None)
        reported = reported_results.get(key)
        if not (isinstance(reported, dict) and reported.get("status") == "complete"
                and type(reported.get("accuracy")) in (int, float)
                and 0 <= reported["accuracy"] <= 1 and reported.get("source")):
            reported = None
        method_status = reported["status"] if reported else (result or {}).get("status", "not_run")
        methods.append({"id": key, "name": name, "description": description, "target": target_record,
                        "reported_result": reported,
                        "status": method_status,
                        "result": result})
    ft = benchmark.get("parameter_finetune") or {}
    has_ft = bool(config.get("fine_tuned_model"))
    return {
        "schema_version": 1,
        "sample_count": sum(a.get("total", 0) for a in analyses),
        "video_count": len(analyses), "anchor_count": len(anchors),
        "anchor_distribution": [{"category": c, "label": CATEGORY_LABELS.get(c, c), "count": counts[c]} for c in categories],
        "missing_categories": [CATEGORY_LABELS.get(c, c) for c in categories if not counts[c]],
        "methods": methods, "benchmark": benchmark,
        "finetune": {
            "base_model": config.get("model", "glm-4-flash"),
            "model_configured": has_ft,
            "status": "evaluated" if ft.get("status") == "complete" else "configured" if has_ft else "not_trained",
            "training_record_available": bool(ft.get("training_record")),
            "result": ft or None,
            "current_approach": "人工标注示例检索与领域知识增强（上下文学习）",
            "note": "参数微调需要真实训练记录、模型标识和独立测试结果；当前标注增强结果不作为参数微调增益。",
        },
        "category_note": "组织化刷评标注疑似模板化、协调刷取或重复传播的文本特征；历史内部键为水军，不认定付费身份或违法事实。",
        "boundary": "测试指标只代表所列人工样本与划分；模型自报置信度和标签覆盖率均不是准确率。未覆盖的类别不能据此评价。",
    }


def evidence_rows(data_dir: Path, bvid: str = "") -> list[dict]:
    anchors = read_json(data_dir / "labels" / "anchors.json", {}).get("anchors", [])
    gold = {(a.get("bvid"), str(a.get("rpid"))): a for a in anchors}
    result = []
    for path in sorted((data_dir / "analysis").glob("*_analyzed.json")):
        video_id = path.name.removesuffix("_analyzed.json")
        if bvid and bvid != video_id:
            continue
        for row in read_json(path, {}).get("_rows", []):
            human = gold.get((video_id, str(row.get("rpid"))))
            category = row.get("category", "")
            result.append({
                "bvid": video_id, "rpid": str(row.get("rpid", "")),
                "source_url": f"https://www.bilibili.com/video/{video_id}/#reply{row.get('rpid', '')}",
                "text": row.get("text", ""), "ctime": row.get("ctime"),
                "model_category": CATEGORY_LABELS.get(category, category),
                "model_category_key": category, "model_reason": row.get("reason", ""),
                "model_confidence": row.get("confidence"),
                "human_category": CATEGORY_LABELS.get(human.get("category"), human.get("category")) if human else "",
                "human_label_available": bool(human), "second_review_category": "", "second_review_note": "",
            })
    return result


def report_markdown(report: dict, rows: list[dict]) -> str:
    lines = ["# 澄明 · 评论分析与二次审查报告", "",
             f"导出时间：{datetime.now(timezone.utc).isoformat()}",
             f"本次导出 {len(rows)} 条评论；研究快照共 {report['sample_count']} 条、{report['anchor_count']} 条人工标注。", "",
             "## 研究用途", "用于二次审查、研究复现及立法研究材料数据集。模型标签作为研究线索，人工结论应结合原文语境和其他证据。", "",
             "## 三档方法测试与历史回看", "| 方法 | 指标 | 数值 | 完成/样本 |", "| --- | --- | --- | --- |"]
    for method in report["methods"]:
        reported = method.get("reported_result")
        if reported:
            lines.append(f"| {method['name']} | {reported['metric_label']} | 约{reported['accuracy']:.0%}（实测） | — |")
            continue
        r = method.get("result") or {}
        metric = r.get("accuracy", r.get("agreement"))
        value = f"{metric:.2%}" if metric is not None else "未测试"
        lines.append(f"| {method['name']} | {r.get('metric_label', '无独立结果')} | {value} | {r.get('completed', 0)}/{r.get('n', 0)} |")
    targets = [method for method in report["methods"] if method.get("target") and not method.get("reported_result")]
    if targets:
        lines += ["", "## 方案目标", "| 方法 | 目标准确率 |", "| --- | --- |"]
        for method in targets:
            lines.append(f"| {method['name']} | 约 {method['target']['accuracy']:.0%} |")
    reported = [method for method in report["methods"] if method.get("reported_result")]
    if reported:
        lines += ["", "## 外部测试记录"]
        for method in reported:
            record = method["reported_result"]
            lines.append(f"- {method['name']}：约{record['accuracy']:.0%}（实测）。记录来源：{record['source']}；登记日期：{record.get('reported_date', '')}。")
    benchmark = report.get("benchmark") or {}
    lines += ["", f"测试协议：{benchmark.get('protocol', '尚未运行独立分组测试')}", benchmark.get("comparison_note", ""),
              "项目模型的正式对照采用完整分类流程；会话内试读记录保存在 benchmark.json 的 conversation_trials。",
              "107条历史样本的回看结果保存在 benchmark.json 的 historical_snapshot，完整普通模型复评保存在 assistant_full_review。",
              f"缺少人工标注的类别：{'、'.join(report['missing_categories']) or '无'}。", report["boundary"], "",
              "## 微调情况", f"当前方式：{report['finetune']['current_approach']}。",
              f"参数微调状态：{report['finetune']['status']}。", report["finetune"]["note"], "",
              "## 二次审查说明", "comments.csv 保留原文、视频与评论标识、来源链接、模型理由和已有人工标签；二次审查结论与说明列留空供审查人员填写。",
              "不导出昵称、IP 地区或密钥。尚未人工标注的记录不得作为人工金标使用。", report["category_note"]]
    return "\n".join(lines) + "\n"


def create_export(data_dir: Path, config: dict, fmt: str = "zip", bvid: str = "") -> tuple[bytes, str, str]:
    if fmt not in {"zip", "json", "csv", "md"}:
        raise ValueError("不支持的导出格式")
    report = build_report(data_dir, config)
    rows = evidence_rows(data_dir, bvid)
    if bvid and not rows:
        raise ValueError("该视频没有可导出的分析记录")
    manifest = {"schema_version": 1, "record_count": len(rows), "scope": bvid or "all",
                "usage": "二次审查与立法研究材料数据集", "human_gold": False,
                "note": "模型标签与人工标签分别保留；尚未完成二次审查。"}
    csv_buffer = io.StringIO(newline="")
    if rows:
        writer = csv.DictWriter(csv_buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        # Spreadsheet viewers must treat comment text as data, never formulas.
        for row in rows:
            writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r")) else v for k, v in row.items()})
    csv_bytes = csv_buffer.getvalue().encode("utf-8-sig")
    markdown = report_markdown(report, rows).encode("utf-8")
    json_bytes = json.dumps({"manifest": manifest, "report": report, "comments": rows}, ensure_ascii=False, indent=2).encode("utf-8")
    stem = "chengming-research-" + (bvid or "all")
    if fmt == "json":
        return json_bytes, "application/json; charset=utf-8", stem + ".json"
    if fmt == "csv":
        return csv_bytes, "text/csv; charset=utf-8", stem + ".csv"
    if fmt == "md":
        return markdown, "text/markdown; charset=utf-8", stem + ".md"
    output = io.BytesIO()
    manifest["comments_sha256"] = hashlib.sha256(csv_bytes).hexdigest()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.md", markdown)
        archive.writestr("comments.csv", csv_bytes)
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("benchmark.json", json.dumps(report["benchmark"], ensure_ascii=False, indent=2))
    return output.getvalue(), "application/zip", stem + ".zip"
