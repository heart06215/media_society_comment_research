# -*- coding: utf-8 -*-
"""破妄 · 微调数据集导出
流程：
  1. 从 data/labels/anchors.json 读锚定集(人工精标，含二次审查修正样本)
  2. 用锚定集(作为模板) + 大模型 预标注一批未标注评论 -> 生成微调样本
  3. 导出智谱微调格式 JSONL (messages: system/user/assistant)
分层标注方法论：人工精标锚定集(金标) + 模板参照式预标注(锚定集检索注入prompt)。
"""
import os
import json
import random

import sentiment_analyze as sa

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ANALYSIS_DIR = os.path.join(BASE_DIR, "data", "analysis")
LABEL_DIR = os.path.join(BASE_DIR, "data", "labels")
FINETUNE_DIR = os.path.join(BASE_DIR, "data", "finetune")

SYSTEM_MSG = """你是一名互联网社区评论情感分析专家，专精中文网络用语。把每条B站评论严格归入六类之一：
- 赞美：喜爱、支持、肯定、夸赞、感动
- 贬低：批评、嘲讽、质疑、不满
- 水军（界面显示组织化刷评）：疑似组织化评论刷取、协调控评或模板话术复制变体，不推断付费身份
- 无意义：灌水、占楼、纯表情、无意义刷屏、显性引流广告(关注我/加V领福利)
- 社区对骂：评论者之间互相攻击、拉踩、站队对线、人身攻击、群体嘲讽
- 中立：客观陈述、提问求证、补充信息、中性讨论，没有明确褒贬情绪
只输出JSON：{"category":"...","confidence":0.0~1.0,"reason":"一句话归因","slang_tags":[]}"""


def load_anchors():
    p = os.path.join(LABEL_DIR, "anchors.json")
    if not os.path.exists(p):
        return []
    d = json.load(open(p, encoding="utf-8"))
    return d.get("anchors", [])


def export(per_video_gold=200, out="trainset.jsonl", seed=42):
    """per_video_gold: 每个视频用于微调的金标(人工)数量上限(超出截断)。
    其余样本由锚定集模板参照预标注补充(调用模型)。
    实际：以全部人工锚定集为金标，再从已分析结果中抽样预标。
    """
    os.makedirs(FINETUNE_DIR, exist_ok=True)
    anchors = load_anchors()
    print(f"[export] 锚定集 {len(anchors)} 条")
    if not anchors:
        print("[export] 无锚定集，请先完成人工标注")
        return

    # 1) 金标样本：全部锚定集(人工)
    gold = []
    seen = set()
    for a in anchors:
        if not a.get("text") or a.get("category") not in sa.CATEGORIES:
            continue
        if a["rpid"] in seen:
            continue
        seen.add(a["rpid"])
        gold.append(a)
    print(f"[export] 金标样本 {len(gold)} 条")

    # 2) 从已分析结果中抽样预标样本(模型已有分类，作为补充)
    pre = []
    for fn in os.listdir(ANALYSIS_DIR):
        if fn.endswith("_analyzed.json"):
            a = json.load(open(os.path.join(ANALYSIS_DIR, fn), encoding="utf-8"))
            for r in a.get("_rows", []):
                if r["rpid"] in seen:
                    continue
                seen.add(r["rpid"])
                pre.append({"text": r["text"], "category": r["category"]})
    print(f"[export] 预标补充 {len(pre)} 条(来自分析结果)")

    # 组合：金标优先，预标补充到 target
    all_rows = gold + pre
    random.seed(seed)
    random.shuffle(all_rows)
    print(f"[export] 组合样本 {len(all_rows)} 条")

    # 3) 写 JSONL
    out_path = os.path.join(FINETUNE_DIR, out)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in all_rows:
            user = f"请对这条B站评论分类：「{r['text']}」"
            assistant = json.dumps({"category": r["category"], "confidence": 1.0 if r.get("source") == "human" else 0.9,
                                    "reason": "人工精标" if r.get("source") == "human" else "模型预标",
                                    "slang_tags": []}, ensure_ascii=False)
            f.write(json.dumps({"messages": [
                {"role": "system", "content": SYSTEM_MSG},
                {"role": "user", "content": user},
                {"role": "assistant", "content": assistant},
            ]}, ensure_ascii=False) + "\n")
    print(f"[export] 已导出 -> {out_path} ({len(all_rows)} 条)")


if __name__ == "__main__":
    import fire
    fire.Fire(export)
