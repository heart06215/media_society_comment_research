"""Audit the built or live public demo, without sending any model requests.

Requires Playwright and a browser (Edge on Windows, Chromium elsewhere).
Run prepare_github_pages.py first, then: python tests/check_review_ui.py
Use --base-url https://heart06215.github.io/powang-demo/ to audit publication.
Screenshots stay in ignored .tmp-submission-audit; --save-doc-assets refreshes
the three actual interface images used by the submission documents.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".tmp-submission-audit"
FORBIDDEN = ("设计目标", "待实测", "等待实测", "目标准确率")


def normalized(text: str) -> str:
    return re.sub(r"\s+", "", text)


class SnapshotHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        return super().translate_path(path.removeprefix("/powang-demo"))

    def log_message(self, *args) -> None:
        pass

    def copyfile(self, source, output) -> None:
        try:
            super().copyfile(source, output)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            pass


def audit(base: str, save_doc_assets: bool) -> None:
    OUTPUT.mkdir(exist_ok=True)
    results = []
    registration_path = ROOT / "output/submission-local/registration.json"
    registration = json.loads(registration_path.read_text(encoding="utf-8")) if registration_path.exists() else {}
    personal_names = registration.get("members", []) + registration.get("advisors", [])
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="msedge" if sys.platform == "win32" else None)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        errors, requests = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda request: requests.append(request.url))
        page.emulate_media(reduced_motion="reduce")

        def privacy() -> None:
            body = page.locator("body").inner_text()
            assert not any(name in body for name in personal_names), "Personal signature appeared on the public page"

        page.goto(base)
        page.wait_for_selector("#homeTitle")
        privacy()
        assert "CHENGMING" not in page.locator("body").inner_text()
        for width in (1440, 1024, 390, 320):
            page.set_viewport_size({"width": width, "height": 1000})
            metrics = page.locator("#homeTitle").evaluate("""e => {
              const r=e.getBoundingClientRect(), p=e.closest('.home-hero').getBoundingClientRect(), s=getComputedStyle(e);
              return {offset:Math.abs(r.x+r.width/2-p.x-p.width/2),color:s.color,stroke:s.webkitTextStrokeWidth};
            }""")
            assert metrics["offset"] < 1 and metrics["color"] == "rgba(0, 0, 0, 0)" and metrics["stroke"] == "2px", (width, metrics)
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1"), ("home overflow", width)
        page.set_viewport_size({"width": 1440, "height": 1000})
        page.screenshot(path=str(OUTPUT / "home.png"))
        if save_doc_assets:
            page.screenshot(path=str(ROOT / "docs/assets/technical.home.jpg"), type="jpeg", quality=85)
        results.append("centered outlined title, no pinyin, four viewport widths")
        page.get_by_role("button", name="切换深色模式").click()
        assert page.locator("#homeTitle").evaluate("e=>getComputedStyle(e).color") == "rgba(0, 0, 0, 0)"
        page.screenshot(path=str(OUTPUT / "home-dark.png"))
        page.get_by_role("button", name="切换浅色模式").click()
        for width in (1440, 1024, 390, 320):
            page.set_viewport_size({"width": width, "height": 1000})
            page.locator("#economy").scroll_into_view_if_needed()
            boxes = page.locator("#gdpDonut").evaluate("""e=>{
              const outer=e.getBoundingClientRect();return [...e.querySelectorAll('.donut-center > *')].map(child=>{
                const b=child.getBoundingClientRect();return [b.left-outer.left,outer.right-b.right,b.top-outer.top,outer.bottom-b.bottom];
              });
            }""")
            assert all(min(box) >= 20 for box in boxes), ("donut text overlap", width, boxes)
        page.set_viewport_size({"width": 1440, "height": 1000})
        results.append("dark theme and donut text clear at four viewport widths")

        navigation = page.locator("#workbenchNavigation")
        navigation.locator("summary").focus()
        page.keyboard.press("Enter")
        assert navigation.evaluate("e=>e.open")
        assert navigation.get_by_role("link", name="评论证据库", exact=True).is_visible()
        page.locator(".platform-portability .action").click()
        page.wait_for_url("**/workbench.html")
        assert page.locator(".workbench-card").count() == 4
        results.append("bottom CTA and expandable data-workbench navigation")

        requests.clear()
        page.goto(base + "insight.html")
        page.wait_for_function("document.querySelectorAll('#overview .stat-cell').length===6")
        page.wait_for_selector("#pie1 canvas")
        assert not any("data/comments-" in url or "data/graph-" in url or "data/site.json" in url or "jsdelivr" in url for url in requests), requests
        privacy()
        if save_doc_assets:
            page.screenshot(path=str(ROOT / "docs/assets/technical.insight.jpg"), type="jpeg", quality=85)
        page.wait_for_selector(".finetune-scan")
        evaluation = page.locator("#evaluation")
        assert not any(word in evaluation.inner_text() for word in FORBIDDEN), "Obsolete evaluation state on dashboard"
        expected = {"semantic": "31.25%", "llm_zeroshot": "70%", "annotated": "90%"}
        labels = {"semantic": "传统语义检索", "llm_zeroshot": "大模型直判", "annotated": "微调标注模型"}
        assert page.locator(".finetune-scan tbody tr").count() == 3
        for method, value in expected.items():
            card = page.locator(".method-" + method)
            assert normalized(card.locator(".accuracy-value").inner_text()) == "约" + value, method
            assert card.locator(".evaluation-status").inner_text() == "实测结果", method
            assert card.locator(".accuracy-qualifier").evaluate("e=>parseFloat(getComputedStyle(e).fontSize)") < card.locator(".accuracy-value > span").evaluate("e=>parseFloat(getComputedStyle(e).fontSize)"), method
            row = page.locator(".finetune-scan tbody tr").filter(has=page.locator("th", has_text=labels[method]))
            cell = normalized(row.locator("td").last.inner_text())
            assert cell == ("约" if method != "semantic" else "") + value + "（实测）", (method, cell)
            page.locator(".evaluation-method").select_option(method)
            if method != "semantic":
                assert "约" + value + "（实测）" in normalized(page.locator(".evaluation-class-body").inner_text()), method
            assert not any(word in evaluation.inner_text() for word in FORBIDDEN), method
        page.locator(".evaluation-method").select_option("annotated")
        evaluation.evaluate("e=>e.scrollIntoView({block:'start',behavior:'instant'})")
        page.screenshot(path=str(OUTPUT / "methods.png"))
        if save_doc_assets:
            page.screenshot(path=str(ROOT / "docs/assets/technical.methods.jpg"), type="jpeg", quality=85)
        results.append("all three cards, all three table rows, all dropdown methods, small approx prefix")
        results.append("small initial payloads, local charts, deferred comments and graph")

        for extension in ("md", "json", "zip"):
            response = context.request.get(base + "downloads/research." + extension)
            assert response.ok, extension
            if extension == "json":
                report = response.json()["report"]
                for method, value in (("llm_zeroshot", .7), ("annotated", .9)):
                    row = next(item for item in report["methods"] if item["id"] == method)
                    assert row["status"] == "complete" and row["target"] is None
                    assert row["reported_result"]["accuracy"] == value and row["reported_result"]["source"]
                continue
            text = response.text() if extension == "md" else zipfile.ZipFile(io.BytesIO(response.body())).read("report.md").decode("utf-8")
            assert "约70%（实测）" in text and "约90%（实测）" in text, extension
            assert not any(word in text for word in FORBIDDEN), extension
        results.append("Markdown, JSON and ZIP exports match both measured records")

        page.locator("#qa").evaluate("e=>e.scrollIntoView({block:'start',behavior:'instant'})")
        assert "标注" not in page.locator("#chatLog").inner_text()
        assert "立法与执法辅助" in page.locator("#qa").inner_text()
        assert page.locator(".hint-q").count() == 6
        page.evaluate("""() => {
          const original=window.fetch; window.__modelRequests=0;
          window.fetch=(input, options)=>{
            if(String(input).includes('/api/agent/chat')) {
              window.__modelRequests++;
              return Promise.resolve(new Response(JSON.stringify({success:false,error:'blocked by UI audit'}),{status:403}));
            }
            return original(input, options);
          };
        }""")
        page.locator(".hint-q").first.click()
        assert "执法核查" in page.locator("#chatQ").input_value()
        assert page.locator("#chatLog .msg").count() == 1 and page.evaluate("window.__modelRequests") == 0
        results.append("reviewer-oriented welcome, six legislative/enforcement prompts, no setup or model request")

        assert page.get_by_role("heading", name="代表性评论", exact=True).count() == 0
        entry = page.locator("#commentEvidenceLink")
        expected_video = entry.get_attribute("href").split("bvid=")[1]
        entry.click()
        page.wait_for_function("document.querySelectorAll('.c-cell').length>=96")
        assert page.locator("#videoSel").input_value() == expected_video
        page.emulate_media(reduced_motion="no-preference")
        page.reload()
        page.wait_for_function("document.querySelectorAll('.c-cell').length>=96")
        page.locator(".c-cell").nth(70).scroll_into_view_if_needed()
        assert page.locator(".swarm-overlay,.swarm-build").count() == 0
        page.locator('.filter-bar .f-cat[data-c="水军"]').click()
        page.wait_for_function("document.querySelectorAll('.c-cell').length>0 && [...document.querySelectorAll('.c-cell .badge')].every(e=>e.textContent==='组织化刷评')")
        assert page.locator(".swarm-overlay,.swarm-build").count() == 0
        page.locator(".c-cell").first.click()
        assert page.locator("#detailDialog").evaluate("e=>e.open")
        page.keyboard.press("Escape")
        privacy()
        results.append("evidence entry preserves video; scroll, filter and detail dialog work without Swarm")
        assert not errors, errors
        browser.close()
    print(json.dumps({"result": "PASS", "checks": results, "console_errors": errors}, ensure_ascii=False), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--save-doc-assets", action="store_true")
    args = parser.parse_args()
    server = None
    if args.base_url:
        base = args.base_url.rstrip("/") + "/"
    else:
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SnapshotHandler, directory=str(ROOT / ".tmp-pages-site")))
        Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}/powang-demo/"
    try:
        audit(base, args.save_doc_assets)
    finally:
        if server:
            server.shutdown()


if __name__ == "__main__":
    main()
