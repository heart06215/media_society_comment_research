# -*- coding: utf-8 -*-
"""Prepare a self-contained EdgeOne Makers deployment.

This script is intentionally simple and deterministic:
  front/                 -> public/             (static pages + assets)
  data/*.json (selected) -> cloud-functions/data (read-only research snapshot)
  comment_graph.py       -> cloud-functions/     (helper module)
  rag_knowledge.py       -> cloud-functions/     (helper module)

Run it after changing the frontend or the research snapshot:
    python scripts/prepare_edgeone.py

The generated public/ and cloud-functions/data/ directories are committed so
EdgeOne can deploy them directly without running a build step.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "front"
PUBLIC = ROOT / "public"
FUNCTIONS = ROOT / "cloud-functions"
FUNCTION_DATA = FUNCTIONS / "data"
DATA = ROOT / "data"


def _copy_file(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_glob(src_dir: Path, pattern: str, dst_dir: Path) -> None:
    if not src_dir.exists():
        return
    dst_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(src_dir.glob(pattern)):
        if path.is_file():
            shutil.copy2(path, dst_dir / path.name)


def _public_config() -> dict:
    cfg = {}
    for name in ("config.example.json", "config.json"):
        path = DATA / name
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig") as fh:
            values = json.load(fh)
        if name == "config.example.json":
            values.pop("api_key", None)
        cfg.update(values)
    cfg.pop("api_key", None)
    return cfg


def main() -> None:
    # Check the two exact generated targets before any recursive replacement.
    for target in (PUBLIC, FUNCTION_DATA):
        resolved = target.resolve()
        if not resolved.is_relative_to(ROOT.resolve()) or resolved not in (
                ROOT.resolve() / "public", ROOT.resolve() / "cloud-functions" / "data"):
            raise ValueError(f"Unsafe generated directory: {resolved}")
    # 1. Static site
    shutil.rmtree(PUBLIC, ignore_errors=True)
    shutil.copytree(FRONT, PUBLIC)
    landing = PUBLIC / "landing.html"
    if landing.exists():
        shutil.copy2(landing, PUBLIC / "index.html")

    # 2. Function-local read-only data snapshot
    shutil.rmtree(FUNCTION_DATA, ignore_errors=True)
    (FUNCTION_DATA / "crawled").mkdir(parents=True, exist_ok=True)
    (FUNCTION_DATA / "analysis").mkdir(parents=True, exist_ok=True)
    (FUNCTION_DATA / "labels").mkdir(parents=True, exist_ok=True)

    _copy_glob(DATA / "crawled", "*.json", FUNCTION_DATA / "crawled")
    _copy_glob(DATA / "analysis", "*_analyzed.json", FUNCTION_DATA / "analysis")
    _copy_file(DATA / "analysis" / "benchmark_report.json", FUNCTION_DATA / "analysis" / "benchmark_report.json")
    _copy_file(DATA / "evaluation" / "method_targets.json", FUNCTION_DATA / "evaluation" / "method_targets.json")
    _copy_file(DATA / "labels" / "anchors.json", FUNCTION_DATA / "labels" / "anchors.json")
    for name in ("slang_dict.json", "rag_knowledge.json", "config.example.json"):
        _copy_file(DATA / name, FUNCTION_DATA / name)

    with (FUNCTION_DATA / "config.public.json").open("w", encoding="utf-8") as fh:
        json.dump(_public_config(), fh, ensure_ascii=False, indent=2)

    # 3. Stdlib-only helper modules used by the EdgeOne API
    _copy_file(ROOT / "comment_graph.py", FUNCTIONS / "comment_graph.py")
    _copy_file(ROOT / "rag_knowledge.py", FUNCTIONS / "rag_knowledge.py")
    _copy_file(ROOT / "research_reports.py", FUNCTIONS / "research_reports.py")
    _copy_file(ROOT / "agent_runtime.py", FUNCTIONS / "agent_runtime.py")

    print("public/:", len([p for p in PUBLIC.rglob("*") if p.is_file()]), "files")
    print("cloud-functions/data/:", len([p for p in FUNCTION_DATA.rglob("*") if p.is_file()]), "files")
    print("static entry:", "public/index.html")


if __name__ == "__main__":
    main()
