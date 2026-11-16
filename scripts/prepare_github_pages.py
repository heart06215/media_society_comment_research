"""Build the allowlisted public Pages artifact, without backend/history/config.

Only the generated .tmp-pages-site directory is published to the demo repository.
The primary project repository keeps the complete code and development history.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".tmp-pages-site"
BASE = "/powang-demo/"
BLOCKED = {"uname", "ip", "uid", "mid", "avatar", "cookie", "api_key", "password", "authorization"}
COMMENT_FIELDS = {"rpid", "bvid", "text", "ctime", "like", "category", "confidence", "reason", "slang_tags"}


def public_value(value):
    if isinstance(value, dict):
        return {key: public_value(item) for key, item in value.items() if key.lower() not in BLOCKED}
    if isinstance(value, list):
        return [public_value(item) for item in value]
    return value


def write_json(name: str, value) -> None:
    path = OUTPUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(public_value(value), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def load(path: str):
    return json.loads((ROOT / "data" / path).read_text(encoding="utf-8-sig"))


def rewrite_reference(match: re.Match) -> str:
    attr, quote, value = match.groups()
    path = re.sub(r"^/(comments|insight|label)(?=$|[?#])", r"/\1.html", value)
    if path == "/":
        path = "/index.html"
    return attr + quote + BASE + path.lstrip("/") + quote


def main() -> None:
    resolved = OUTPUT.resolve()
    if resolved != ROOT.resolve() / ".tmp-pages-site":
        raise ValueError("Unexpected Pages output directory")
    # Preserve the deployment checkout's own history between repeated builds.
    OUTPUT.mkdir(exist_ok=True)
    for item in OUTPUT.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    for source in (ROOT / "front").iterdir():
        if not source.is_file() or source.suffix not in {".html", ".css", ".js", ".svg"}:
            continue
        text = source.read_text(encoding="utf-8")
        text = re.sub(r'''((?:href|src)=)(["'])(/(?!/)[^"']*)["']''', rewrite_reference, text)
        if source.suffix == ".html":
            text = text.replace('<head>', '<head>\n<script src="' + BASE + 'pages-runtime.js"></script>', 1)
        if source.name == "workspace.js":
            text = text.replace('const home = location.pathname === "/";', 'const routePath = location.pathname.replace("' + BASE + '", "/").replace(/\\.html$/, "");\n  const home = routePath === "/" || routePath === "/index";')
            text = text.replace('location.pathname.startsWith(', 'routePath.startsWith(')
        (OUTPUT / source.name).write_text(text, encoding="utf-8")
    shutil.copy2(OUTPUT / "landing.html", OUTPUT / "index.html")
    shutil.copy2(ROOT / "scripts" / "pages-runtime.js", OUTPUT / "pages-runtime.js")
    (OUTPUT / ".nojekyll").touch()

    config = load("config.example.json")
    analyses, comments, videos = {}, {}, []
    anchors = load("labels/anchors.json")["anchors"]
    for video in config["videos"]:
        bvid = video["bvid"]
        corpus = load(f"crawled/{bvid}.json")
        analysis = load(f"analysis/{bvid}_analyzed.json")
        analyzed = {str(row["rpid"]): row for row in analysis["_rows"]}
        comments[bvid] = [{key: value for key, value in {**row, **analyzed.get(str(row["rpid"]), {})}.items() if key in COMMENT_FIELDS} for row in corpus["comments"]]
        analyses[bvid] = {key: value for key, value in analysis.items() if key != "_rows"}
        videos.append({**video, "title": corpus["meta"].get("title", ""), "corpus_count": len(comments[bvid]), "anchor_count": sum(row["bvid"] == bvid for row in anchors), "analyzed": True, "analysis": analysis["category_count"], "top_slang": analysis["top_slang"], "trend": analysis["trend"], "representative": analysis["representative"]})
    import sys
    sys.path.insert(0, str(ROOT))
    import research_reports
    report = research_reports.build_report(ROOT / "data", config)
    write_json("data/site.json", {"videos": videos, "analyses": analyses, "comments": comments, "anchors": [{key: value for key, value in row.items() if key in COMMENT_FIELDS} for row in anchors], "report": report})

    # Generate the exact graph response used by the live project, without model calls.
    import app
    client = app.app.test_client()
    for limit in (240, 520):
        response = client.get(f"/api/graph?comments={limit}")
        if response.status_code != 200:
            raise RuntimeError("Could not generate graph snapshot")
        write_json(f"data/graph-{limit}.json", response.get_json())

    for bvid in ("", *(video["bvid"] for video in videos)):
        for fmt in ("zip", "csv", "json", "md"):
            content, _, _ = research_reports.create_export(ROOT / "data", config, fmt, bvid)
            path = OUTPUT / "downloads" / bvid / ("research." + fmt)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    source_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    write_json("deployment-manifest.json", {"source_commit": source_commit, "mode": "read-only", "comment_count": sum(map(len, comments.values())), "anchor_count": len(anchors), "excluded_fields": sorted(BLOCKED)})
    (OUTPUT / "README.md").write_text("# 破妄 · 公开演示\n\nhttps://heart06215.github.io/powang-demo/\n\n此仓库仅存放公开演示的前端和授权研究数据。完整项目、后端与开发历史见[源码仓库](https://github.com/heart06215/media_society_comment_research)。\n\n支持评论筛选、社区对比、关系图谱及研究报告下载。实时问答与服务端标注在完整版本运行。\n", encoding="utf-8")
    print(f"Pages artifact: {OUTPUT}")
    print(f"Public comments: {sum(map(len, comments.values()))}; anchors: {len(anchors)}")


if __name__ == "__main__":
    main()
