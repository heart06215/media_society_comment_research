# -*- coding: utf-8 -*-
"""破妄 · LangChain 洞察 Agent (langchain 1.x / langgraph)
给 AI 问答页提供"数据洞察"能力：查询各视频分析结果，回答统计/对比/趋势/代表性评论类问题。
工具函数直接读本地分析JSON；agent 负责理解意图 + 组织回答。
默认模型 glm-4-flash(免费)，可切微调后模型。
"""
import os
import json

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage

import sentiment_analyze as sa
from rag_knowledge import make_kb, SlangKnowledgeBase

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ANALYSIS_DIR = os.path.join(BASE_DIR, "data", "analysis")
CATEGORIES = sa.CATEGORIES
CFG = sa.load_project_config()
_KB = None


def _kb():
    global _KB
    if _KB is None:
        _KB = make_kb()
    return _KB


def _load_analysis(bvid):
    p = os.path.join(ANALYSIS_DIR, f"{bvid}_analyzed.json")
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8"))


def _all_analyses():
    out = {}
    for fn in os.listdir(ANALYSIS_DIR):
        if fn.endswith("_analyzed.json"):
            bvid = fn.replace("_analyzed.json", "")
            out[bvid] = json.load(open(os.path.join(ANALYSIS_DIR, fn), encoding="utf-8"))
    return out


@tool
def get_video_stats(bvid: str) -> str:
    """获取某个视频的六分类统计(赞美/贬低/水军/无意义/社区对骂/中立数量与占比)。bvid 如 BV1fy4y1L7Rq。"""
    a = _load_analysis(bvid)
    if not a:
        return f"视频 {bvid} 尚未分析"
    return json.dumps({"bvid": bvid, "total": a.get("total"), "count": a.get("category_count"),
                       "ratio": a.get("category_ratio")}, ensure_ascii=False)


@tool
def get_trend(bvid: str) -> str:
    """获取某视频按月的时间趋势(每月各分类数量)。"""
    a = _load_analysis(bvid)
    if not a:
        return f"视频 {bvid} 尚未分析"
    return json.dumps(a.get("trend", []), ensure_ascii=False)


@tool
def get_top_slang(bvid: str) -> str:
    """获取某视频高频网络用语(前20)及各分类下的热词。"""
    a = _load_analysis(bvid)
    if not a:
        return f"视频 {bvid} 尚未分析"
    return json.dumps({"top": a.get("top_slang", []), "by_cat": a.get("slang_by_category", {})}, ensure_ascii=False)


@tool
def get_representative(bvid: str, category: str) -> str:
    """获取某视频指定分类(赞美/贬低/水军/无意义/社区对骂/中立)的代表性评论原文。"""
    a = _load_analysis(bvid)
    if not a:
        return f"视频 {bvid} 尚未分析"
    reps = (a.get("representative") or {}).get(category, [])
    return json.dumps([{"text": r["text"], "confidence": r.get("confidence")} for r in reps[:5]], ensure_ascii=False)


@tool
def compare_videos() -> str:
    """对比所有已分析视频的分类统计。"""
    out = {}
    for bvid, a in _all_analyses().items():
        out[bvid] = {"total": a.get("total"), "count": a.get("category_count"), "ratio": a.get("category_ratio")}
    return json.dumps(out, ensure_ascii=False)


@tool
def search_slang(query: str) -> str:
    """检索网络用语RAG知识库：查询某个网络用语/梗的含义、情感倾向、示例。"""
    hits = _kb().search(query, k=5)
    if not hits:
        return "知识库中未找到相关网络用语"
    return json.dumps([{"term": e["term"], "meaning": e.get("meaning"), "sentiment": e.get("sentiment"),
                        "examples": e.get("examples", [])} for e in hits], ensure_ascii=False)


def build_agent(model=None, api_key=None):
    model = model or CFG.get("fine_tuned_model") or CFG.get("model", "glm-4-flash")
    api_key = api_key or CFG.get("api_key", "")
    llm = ChatOpenAI(model=model, api_key=api_key,
                     base_url=CFG.get("base_url", "https://open.bigmodel.cn/api/paas/v4/"),
                     temperature=0.2, request_timeout=90)
    tools = [get_video_stats, get_trend, get_top_slang, get_representative, compare_videos, search_slang]
    sys_prompt = ("你是'破妄'评论情感分析系统的 AI 分析师。数据来源是 B 站评论六分类(赞美/贬低/水军/无意义/社区对骂/中立)分析结果。"
                  "回答用户关于评论情感的问题，用中文、简洁、给出关键数字。若数据缺失请如实说明。")
    return create_agent(model=llm, tools=tools, system_prompt=sys_prompt)


if __name__ == "__main__":
    import fire

    def ask(question, model="", api_key=""):
        agent = build_agent(model=model, api_key=api_key)
        result = agent.invoke({"messages": [HumanMessage(content=question)]})
        # 兼容不同返回结构
        msgs = result.get("messages", [])
        if msgs:
            print(msgs[-1].content)
        else:
            print(result)

    fire.Fire(ask)