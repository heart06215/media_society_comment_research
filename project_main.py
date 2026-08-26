# -*- coding: utf-8 -*-
"""破妄 · 主入口 (fire CLI)
用法：
  python project_main.py --mode crawl          # 爬取两视频评论
  python project_main.py --mode analyze        # 用锚定集+大模型分析全量评论
  python project_main.py --mode export         # 导出微调数据集
  python project_main.py --mode serve          # 启动 Web 平台
  python project_main.py --mode stats          # 打印数据统计
"""
import os
import json
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import comment_crawler
import sentiment_analyze as sa
import export_finetune

CONFIG = sa.load_project_config()

PROJECT_CONFIG = {
    "crawled_dir": os.path.join(BASE_DIR, "data", "crawled"),
    "analysis_dir": os.path.join(BASE_DIR, "data", "analysis"),
    "anchors_path": os.path.join(BASE_DIR, "data", "labels", "anchors.json"),
    "videos": CONFIG.get("videos", []),
}


def _anchors_for(bvid):
    p = PROJECT_CONFIG["anchors_path"]
    if not os.path.exists(p):
        return []
    d = json.load(open(p, encoding="utf-8"))
    return [a for a in d.get("anchors", []) if a.get("bvid") == bvid]


def run(mode="stats", bvid="", limit=0):
    if mode == "crawl":
        c = comment_crawler.CommentCrawler(PROJECT_CONFIG["crawled_dir"])
        targets = [bvid] if bvid else [v["bvid"] for v in PROJECT_CONFIG["videos"]]
        for bv in targets:
            comment_crawler.crawl_video(c, bv, month_points=None)
    elif mode == "analyze":
        targets = [bvid] if bvid else [v["bvid"] for v in PROJECT_CONFIG["videos"]]
        for bv in targets:
            anchors = _anchors_for(bv)
            if not anchors:
                print(f"[{bv}] 无锚定集，跳过(请先在前端标注)")
                continue
            retriever = sa.AnchorRetriever([{"text": a["text"], "category": a["category"]} for a in anchors])
            corpus = json.load(open(os.path.join(PROJECT_CONFIG["crawled_dir"], f"{bv}.json"), encoding="utf-8"))
            items = [{"rpid": c["rpid"], "bvid": c["bvid"], "text": c["text"],
                      "ctime": c.get("ctime"), "like": c.get("like", 0)} for c in corpus.get("comments", [])]
            if limit:
                items = items[:limit]
            analyzer = sa.SentimentAnalyzer({"analysis_dir": PROJECT_CONFIG["analysis_dir"], "tag": f"{bv}_analyzed"})
            rows = analyzer.classify_many(items, retriever, concurrency=CONFIG.get("concurrency", 12))
            agg = sa.aggregate(rows, corpus.get("meta", {}))
            agg["_rows"] = rows
            out = os.path.join(PROJECT_CONFIG["analysis_dir"], f"{bv}_analyzed.json")
            with open(out, "w", encoding="utf-8") as f:
                json.dump(agg, f, ensure_ascii=False, indent=1)
            print(f"[{bv}] 分析完成 {len(rows)} 条 -> {out}")
    elif mode == "export":
        export_finetune.export()
    elif mode == "dedup":
        targets = [bvid] if bvid else [v["bvid"] for v in PROJECT_CONFIG["videos"]]
        for bv in targets:
            comment_crawler.dedup_corpus(bv, PROJECT_CONFIG["crawled_dir"])
    elif mode == "serve":
        from app import app
        port = int(os.environ.get("PORT", 5000))
        print(f"破妄平台: http://localhost:{port}")
        app.run(host="127.0.0.1", port=port, threaded=True)
    elif mode == "stats":
        print("=" * 40)
        for v in PROJECT_CONFIG["videos"]:
            bv = v["bvid"]
            corpus = os.path.join(PROJECT_CONFIG["crawled_dir"], f"{bv}.json")
            if os.path.exists(corpus):
                d = json.load(open(corpus, encoding="utf-8"))
                print(f"[{v['name']}] 语料 {d.get('count', 0)} 条 | 锚定 {len(_anchors_for(bv))} 条")
            a = os.path.join(PROJECT_CONFIG["analysis_dir"], f"{bv}_analyzed.json")
            if os.path.exists(a):
                ag = json.load(open(a, encoding="utf-8"))
                print(f"    分析: {ag.get('total', 0)} 条, 分布 {ag.get('category_count', {})}")
        print("=" * 40)


if __name__ == "__main__":
    import fire
    fire.Fire(run)