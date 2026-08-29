# 语料近重复相似度实算：验证不同 Jaccard 阈值下的近重复规模
# 用法：python check_similarity.py
import json
import os
from collections import OrderedDict

BASE = os.path.dirname(os.path.abspath(__file__))
THRESHOLDS = [0.5, 0.6, 0.7, 0.8, 0.9]


def bigrams(s):
    s = "".join(ch for ch in s if not ch.isspace())
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def load(path):
    d = json.load(open(path, encoding="utf-8"))
    return d.get("comments", [])


def analyze(name, comments):
    comments = [c for c in comments if (c.get("text") or "").strip()]
    sets = [bigrams(c["text"]) for c in comments]
    sizes = [len(s) for s in sets]
    likes = [c.get("like") or 0 for c in comments]
    n = len(sets)
    print(f"\n===== {name} | 有效评论 {n} 条 =====")

    # 1) 每条评论与全语料（同视频内）的最大相似度分布
    maxsim = [0.0] * n
    for i in range(n):
        Ai, si = sets[i], sizes[i]
        if si == 0:
            continue
        for j in range(i + 1, n):
            sj = sizes[j]
            if sj == 0:
                continue
            mn, mx = (si, sj) if si <= sj else (sj, si)
            if mn / mx < THRESHOLDS[0]:  # Jaccard 上界不足，剪枝
                continue
            inter = len(Ai & sets[j])
            if inter == 0:
                continue
            J = inter / (si + sj - inter)
            if J > maxsim[i]:
                maxsim[i] = J
            if J > maxsim[j]:
                maxsim[j] = J
    for t in THRESHOLDS:
        share = sum(1 for m in maxsim if m >= t)
        print(f"  与任一其他评论相似度 J>={t:.1f} 的评论: {share} 条 ({share / n * 100:.1f}%)")

    # 2) 贪心聚类去重率 D(t)：按点赞降序，簇内保留最高赞代表
    order = sorted(range(n), key=lambda k: -likes[k])
    for t in THRESHOLDS:
        kept = []
        kept_sets = []
        removed = 0
        for idx in order:
            A, sz = sets[idx], sizes[idx]
            if sz == 0:
                removed += 1
                continue
            dup = False
            for B, bsz in zip(kept_sets, [sizes[k] for k in kept]):
                mn, mx = (sz, bsz) if sz <= bsz else (bsz, sz)
                if mn / mx < t:
                    continue
                inter = len(A & B)
                if inter and inter / (sz + bsz - inter) >= t:
                    dup = True
                    break
            if dup:
                removed += 1
            else:
                kept.append(idx)
                kept_sets.append(A)
        D = removed / n * 100
        print(f"  贪心去重 D(t={t:.1f}): 去除 {removed} 条, 去重率 {D:.1f}%")


if __name__ == "__main__":
    for bv, label in [("BV1fy4y1L7Rq", "二游《明日方舟》PV"), ("BV1h1kcBfEuJ", "饭圈TF家族音乐会")]:
        analyze(label, load(os.path.join(BASE, "data", "crawled", f"{bv}.json")))
