# -*- coding: utf-8 -*-
"""澄明 · 网络用语RAG检索模块
构建网络用语知识库(含"砌墙"等梗)的检索索引，按评论相关词条检索并注入prompt，
实现检索增强生成(RAG)，提升网络用语特化分类能力。
检索策略：关键词命中(term/alias/example) + 字符bigram相似度近邻，Top-K。
"""
import os
import json
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KB_PATH = os.path.join(BASE_DIR, "data", "rag_knowledge.json")


def _ngrams(text, n=2):
    text = re.sub(r"\s+", "", text or "")
    if len(text) < n:
        return [text] if text else []
    return [text[i:i + n] for i in range(len(text) - n + 1)]


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


class SlangKnowledgeBase:
    """网络用语RAG知识库：索引 + 检索"""

    def __init__(self, path=KB_PATH):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.entries = data.get("entries", [])
        for e in self.entries:
            e["_keys"] = {e.get("term", ""), *e.get("aliases", [])}
            e["_hit"] = {e.get("term", ""), *e.get("aliases", [])} | set(e.get("examples", []))
            e["_ngrams"] = _ngrams(e.get("meaning", "")) + _ngrams(e.get("term", ""))

    def search(self, text, k=3):
        """检索与评论相关的网络用语词条(命中的+相似的)"""
        text = text or ""
        hits, scored = [], []
        for e in self.entries:
            # 1) 关键词命中(词条/别名/示例 出现在评论中)
            if any(word and word in text for word in e["_hit"] if word):
                hits.append(e)
            else:
                # 2) 语义近邻(基于词条含义的字符相似)
                scored.append((e, _jaccard(_ngrams(text), e["_ngrams"])))
        scored.sort(key=lambda x: x[1], reverse=True)
        # 命中的优先，再补相似度高的
        picked = hits[:k]
        for e, s in scored:
            if len(picked) >= k:
                break
            if e not in picked and s >= 0.15:
                picked.append(e)
        # 返回去掉内部字段的干净副本
        return [{k: v for k, v in e.items() if not k.startswith("_")} for e in picked]

    def format_for_prompt(self, items):
        lines = []
        for e in items:
            lines.append(f"- {e.get('term')}: {e.get('meaning')}(倾向:{e.get('sentiment','中性')})")
        return "\n".join(lines)


def make_kb():
    return SlangKnowledgeBase()


if __name__ == "__main__":
    kb = make_kb()
    for q in ["当砌则砌！🔨🧱当砌则砌！", "这修音假唱实锤", "太好听了yyds封神"]:
        hits = kb.search(q, k=3)
        print(f"Q: {q}")
        for e in hits:
            print("   ", e["term"], "-", e["meaning"])
