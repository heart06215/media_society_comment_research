"""Regression checks for test integrity, output validation and portable evidence."""
import csv
import asyncio
import gzip
import importlib.util
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from types import SimpleNamespace

import agent_runtime
import evaluation
import research_reports
from pydantic import ValidationError
from sentiment_analyze import ValidatedLabelParser

ROOT = Path(__file__).resolve().parents[1]


class EvaluationIntegrityTests(unittest.TestCase):
    def test_project_comparison_uses_full_same_video_retrieval(self):
        llm = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(usage_metadata={})))
        parser = Mock()
        parser.invoke.return_value = {"category": "赞美", "reason": "结合人工示例分类"}
        kb = Mock()
        kb.search.return_value = [{"term": "圈层词"}]
        kb.format_for_prompt.return_value = "圈层词的释义"
        analyzer = SimpleNamespace(model="project-ft", slang={"entries": []}, llm=llm, parser=parser, rag_kb=kb)
        train = [{"rpid": "same-video", "bvid": "A", "text": "人工示例", "category": "赞美"},
                 {"rpid": "other-video", "bvid": "B", "text": "其他视频示例", "category": "贬低"}]
        test = [{"rpid": "held-out", "bvid": "A", "text": "测试评论", "category": "赞美"}]
        with patch("sentiment_analyze.SentimentAnalyzer", return_value=analyzer) as factory:
            rows = asyncio.run(evaluation.llm_predictions(train, test, "annotated", {"model": "base", "fine_tuned_model": "project-ft"}, 1))
        self.assertEqual(factory.call_args.args[0]["model"], "project-ft")
        self.assertEqual(rows[0]["reference_ids"], ["same-video"])
        self.assertEqual(rows[0]["knowledge_terms"], ["圈层词"])
        self.assertIn("人工示例", llm.ainvoke.await_args.args[0][1].content)
        self.assertNotIn("其他视频示例", llm.ainvoke.await_args.args[0][1].content)

    def test_offline_review_score_is_computed_from_frozen_predictions(self):
        source = json.loads((ROOT / "data/labels/anchors.json").read_text(encoding="utf-8"))["anchors"]
        result = evaluation.load_assistant_review(source)
        correct = sum(row["gold"] == row["prediction"] for row in result["rows"])
        self.assertEqual(result["n"], len(source))
        self.assertEqual(result["correct"], correct)
        self.assertEqual(result["accuracy"], correct / len(source))
        self.assertEqual(result["evaluation_kind"], "assistant_offline_review")
        self.assertTrue(all(row["reason"] for row in result["rows"]))

    def test_changed_comment_text_does_not_reuse_stale_review_percentage(self):
        source = json.loads((ROOT / "data/labels/anchors.json").read_text(encoding="utf-8"))["anchors"]
        source[0]["text"] += "（文本已修改）"
        result = evaluation.load_assistant_review(source)
        self.assertEqual(result["status"], "stale")
        self.assertNotIn("accuracy", result)

    def test_augmented_review_uses_only_training_side_references(self):
        source = json.loads((ROOT / "data/labels/anchors.json").read_text(encoding="utf-8"))["anchors"]
        train, test = evaluation.grouped_split(source)
        result = evaluation.load_augmented_holdout(test, train)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["n"], len(test))
        self.assertEqual(result["correct"], sum(r["gold"] == r["prediction"] for r in result["rows"]))
        frozen = json.loads((ROOT / "data/evaluation/augmented_holdout_review_2026-11-14.json").read_text(encoding="utf-8"))
        train_ids = {str(r["rpid"]) for r in train}
        test_ids = {str(r["rpid"]) for r in test}
        for row in frozen["reviews"]:
            self.assertTrue(set(row["reference_ids"]).issubset(train_ids))
            self.assertFalse(set(row["reference_ids"]) & test_ids)
        self.assertEqual(evaluation.load_augmented_holdout(test, train[1:])["status"], "stale")

    def test_near_duplicates_stay_in_one_partition(self):
        rows = [{"rpid": i, "text": text, "category": category}
                for i, (text, category) in enumerate([
                    ("今天的演出很好听", "赞美"), ("今天的演出很好听！", "赞美"),
                    ("剧情很感动", "赞美"), ("舞台表现出色", "赞美"),
                    ("全程修音难听", "贬低"), ("这个剧情很糟糕", "贬低"), ("策划令人失望", "贬低")])]
        train, test = evaluation.grouped_split(rows)
        sides = {r["rpid"]: side for side, group in enumerate([train, test]) for r in group}
        self.assertEqual(sides[0], sides[1])
        self.assertTrue(train and test)
        self.assertEqual((train, test), evaluation.grouped_split(rows))

    def test_failed_requests_count_in_accuracy_denominator(self):
        result = evaluation.metrics([{"gold": "赞美", "prediction": "赞美"}, {"gold": "贬低", "prediction": "error"}])
        self.assertEqual(result["accuracy"], 0.5)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["status"], "partial")

    def test_parser_rejects_unknown_categories_and_invalid_shapes(self):
        parser = ValidatedLabelParser()
        for value in [
            {"category": "任意标签", "confidence": .8, "reason": "理由", "slang_tags": []},
            {"category": "中立", "confidence": 5, "reason": "理由", "slang_tags": []},
            {"category": "中立"},
        ]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                parser.invoke(json.dumps(value, ensure_ascii=False))
        valid = {"category": "水军", "confidence": .6, "reason": "疑似模板化组织刷评", "slang_tags": []}
        self.assertEqual(parser.invoke(json.dumps(valid)), valid)


class ExportTests(unittest.TestCase):
    def test_design_targets_are_separate_from_measured_accuracy(self):
        report = research_reports.build_report(ROOT / "data")
        expected = {"llm_zeroshot": 0.7, "annotated": 0.9}
        for method in report["methods"]:
            if method["id"] in expected:
                self.assertEqual(method["target"]["accuracy"], expected[method["id"]])
                self.assertEqual(method["target"]["metric_kind"], "design_target")
                self.assertNotIn("accuracy", method["result"])
                self.assertNotIn("target", report["benchmark"]["methods"][method["id"]])
        markdown = research_reports.report_markdown(report, [])
        self.assertIn("## 方案目标", markdown)
        self.assertIn("| 大模型 | 约 70% |", markdown)
        self.assertIn("| 我们的微调标注大模型 | 实测准确率 | 约90%（实测） | — |", markdown)

    def test_external_measurement_preserves_source_without_invented_counts(self):
        report = research_reports.build_report(ROOT / "data")
        method = next(item for item in report["methods"] if item["id"] == "annotated")
        result = method["reported_result"]
        self.assertEqual(result["accuracy"], 0.9)
        self.assertTrue(result["approximate"])
        self.assertEqual(result["evaluation_kind"], "team_reported_external_model_test")
        self.assertTrue(result["source"])
        for field in ("n", "correct", "macro_f1", "per_class"):
            self.assertNotIn(field, result)
        self.assertNotIn("accuracy", method["result"])

    def test_review_package_separates_labels_and_omits_identity_fields(self):
        with tempfile.TemporaryDirectory(prefix=".tmp-test-", dir=ROOT) as folder:
            data = Path(folder)
            self.assertTrue(data.resolve().is_relative_to(ROOT.resolve()))
            (data / "analysis").mkdir(); (data / "labels").mkdir()
            row = {"rpid": 7, "text": "=HYPERLINK(恶意公式)", "category": "水军", "reason": "模板化话术", "uname": "private-name", "ip": "private-region"}
            (data / "analysis/BVdemo_analyzed.json").write_text(json.dumps({"total": 1, "_rows": [row]}), encoding="utf-8")
            (data / "labels/anchors.json").write_text(json.dumps({"anchors": [{"bvid": "BVdemo", "rpid": 7, "category": "中立"}]}), encoding="utf-8")
            content, _, _ = research_reports.create_export(data, {"api_key": "private-key"})
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                text = archive.read("comments.csv").decode("utf-8-sig")
                exported = list(csv.DictReader(io.StringIO(text)))[0]
                self.assertEqual(exported["model_category"], "组织化刷评")
                self.assertEqual(exported["human_category"], "中立")
                self.assertEqual(exported["second_review_category"], "")
                self.assertTrue(exported["text"].startswith("'="))
                self.assertNotIn("private-name", text)
                self.assertNotIn("private-region", text)
                self.assertFalse(json.loads(archive.read("manifest.json"))["human_gold"])
                self.assertNotIn("private-key", archive.read("report.md").decode())

    def test_historical_consistency_is_not_published_as_accuracy(self):
        report = research_reports.build_report(ROOT / "data")
        result = report["benchmark"]["historical_snapshot"]
        self.assertEqual(result["evaluation_kind"], "historical_consistency")
        self.assertNotIn("accuracy", result)
        self.assertFalse(result["independent"])
        self.assertEqual({method["result"]["n"] for method in report["methods"]}, {report["benchmark"]["test_count"]})
        primary = next(m["result"] for m in report["methods"] if m["id"] == "annotated")
        self.assertEqual(primary["evaluation_kind"], "project_model_paired")
        self.assertEqual(primary["status"], "awaiting_model_run")
        self.assertNotIn("accuracy", primary)
        self.assertIn("conversation_trials", report["benchmark"])


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app
        cls.local = app.app.test_client()
        spec = importlib.util.spec_from_file_location("edgeone_test", ROOT / "cloud-functions/api/[[default]].py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.cloud = module.app.test_client()

    def test_local_and_cloud_reports_and_exports_match(self):
        for client, prefix in [(self.local, "/api"), (self.cloud, "")]:
            with self.subTest(prefix=prefix):
                response = client.get(prefix + "/research/report")
                self.assertEqual(response.status_code, 200)
                report = response.get_json()["data"]
                self.assertEqual(report["sample_count"], 7199)
                self.assertEqual(len(report["methods"]), 3)
                annotated = next(item for item in report["methods"] if item["id"] == "annotated")
                self.assertEqual(annotated["reported_result"]["accuracy"], 0.9)
                download = client.get(prefix + "/research/export?format=zip&bvid=BV1fy4y1L7Rq")
                self.assertEqual(download.status_code, 200)
                with zipfile.ZipFile(io.BytesIO(download.data)) as archive:
                    self.assertEqual(json.loads(archive.read("manifest.json"))["record_count"], 4267)
                self.assertEqual(client.get(prefix + "/research/export?format=exe").status_code, 400)

    def test_analysis_is_a_small_summary_and_compression_is_valid(self):
        response = self.local.get("/api/analysis/BV1fy4y1L7Rq")
        self.assertNotIn("_rows", response.get_json()["data"])
        compressed = self.local.get("/api/graph?comments=32", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(compressed.headers["Content-Encoding"], "gzip")
        self.assertTrue(json.loads(gzip.decompress(compressed.data))["success"])
        asset = self.local.get("/research-core.js")
        conditional = self.local.get("/research-core.js", headers={"If-None-Match": asset.headers["ETag"]})
        self.assertEqual(conditional.status_code, 304)


class CloudToolTests(unittest.TestCase):
    def test_function_calling_executes_real_tool_and_returns_trace(self):
        first = Mock()
        first.json.return_value = {"choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "call1", "type": "function", "function": {"name": "get_video_stats", "arguments": '{"bvid":"BV1fy4y1L7Rq"}'}}]}}]}
        last = Mock()
        last.json.return_value = {"choices": [{"message": {"content": "共4267条研究样本"}}]}
        with patch("requests.post", side_effect=[first, last]) as post:
            result = agent_runtime.run_chat(ROOT / "data", "统计样本数", "test-key", "https://example.invalid", "test-model", "研究助手")
        self.assertEqual(result["trace"][0]["status"], "complete")
        self.assertIn("4267", result["trace"][0]["result_preview"])
        self.assertEqual(post.call_count, 2)
        self.assertEqual(result["execution_mode"], "function-calling")


if __name__ == "__main__":
    unittest.main()
