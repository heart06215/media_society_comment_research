# -*- coding: utf-8 -*-
"""澄明 · B站评论爬虫
基于 bilibili-API-collect 公开接口文档改造：
  - 主评论：GET https://api.bilibili.com/x/v2/reply/main?type=1&oid={aid}&mode={m}&next={cursor}
    mode=2 时间正序(游标近似条数偏移) / mode=3 热度排序
  - 子评论：GET /x/v2/reply/reply?type=1&oid={aid}&root={rpid}
工程要点：登录Cookie(buvid3+SESSDATA)、慢速限速、412风控退避、断点续采(JSONL)、时间分层采样。

安全提示：请使用登录态 Cookie（data/cookie.txt，绝不提交/不进文档），避免匿名IP被B站风控。
"""
import os
import json
import time
import random
import re
import requests
from datetime import datetime

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

API_REPLY_MAIN = "https://api.bilibili.com/x/v2/reply/main"
API_REPLY_REPLY = "https://api.bilibili.com/x/v2/reply/reply"
API_VIEW = "https://api.bilibili.com/x/web-interface/view"

CATEGORIES = ["赞美", "贬低", "水军", "无意义", "社区对骂", "中立"]


class CommentCrawler:
    def __init__(self, out_dir, cookie_path=None,
                 min_interval=3.0, max_interval=6.0, max_retry=5):
        self.out_dir = out_dir
        os.makedirs(out_dir, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.bilibili.com/",
        })
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.max_retry = max_retry
        self._time_probe_dead = False  # B站限制主评论游标翻页时置位，避免每月份点空转二分
        self._load_cookie(cookie_path)
        self._bootstrap()

    # ---------- Cookie 与基础请求 ----------
    def _load_cookie(self, cookie_path):
        # cookie_path 缺省用项目 data/cookie.txt
        if not cookie_path:
            base = os.path.dirname(os.path.abspath(__file__))
            cookie_path = os.path.join(base, "data", "cookie.txt")
        if os.path.exists(cookie_path):
            with open(cookie_path, "r", encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip().lstrip("\ufeff")
                    if not line:
                        continue
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip()
                    if not k or not v:
                        continue
                    self.session.cookies.set(k, v)

    def _bootstrap(self):
        # 无 buvid3 时从首页引导
        try:
            self.session.get("https://www.bilibili.com/", timeout=15)
        except Exception as e:
            print("[warn] 首页引导失败:", e)
        self._sleep(1.5)

    def _sleep(self, base=None):
        lo, hi = self.min_interval, self.max_interval
        if base:
            lo, hi = base, base + 2
        time.sleep(random.uniform(lo, hi))

    def _get(self, url, params, no_retry_codes=()):
        for attempt in range(1, self.max_retry + 1):
            try:
                r = self.session.get(url, params=params, timeout=20)
                if r.status_code == 412 or (r.status_code == 200 and "code" in r.text and r.json().get("code") == -412):
                    wait = random.uniform(40, 80)
                    print(f"[risk] 风控412，等待 {wait:.0f}s (尝试 {attempt}/{self.max_retry})")
                    time.sleep(wait)
                    continue
                if r.status_code != 200:
                    self._sleep(5)
                    continue
                data = r.json()
                if data.get("code") == 0:
                    return data
                if data.get("code") in no_retry_codes:
                    print(f"[api] code={data.get('code')} msg={data.get('message')} (终态，跳过重试)")
                    return None
                print(f"[api] code={data.get('code')} msg={data.get('message')} (尝试 {attempt})")
                self._sleep(3)
            except requests.RequestException as e:
                print(f"[net] {e}，重试")
                self._sleep(3)
        return None

    # ---------- 视频信息 ----------
    def get_video_info(self, bvid):
        d = self._get(API_VIEW, {"bvid": bvid})
        if not d:
            return None
        st = d["data"]
        return {
            "bvid": bvid,
            "aid": st["aid"],
            "title": st.get("title", ""),
            "owner": st.get("owner", {}).get("name", ""),
            "pubdate": st.get("pubdate"),
            "reply_count": st.get("stat", {}).get("reply", 0),
        }

    # ---------- 评论抓取 ----------
    def _fetch_main(self, aid, mode, cursor):
        d = self._get(API_REPLY_MAIN, {
            "type": 1, "oid": aid, "mode": mode, "next": cursor,
            "plat": 1, "seek_rpid": "", "web_location": 1315873,
        })
        if not d:
            return None, None
        return d["data"].get("replies") or [], d["data"].get("cursor", {}).get("next")

    def _fetch_reply(self, aid, root, page):
        d = self._get(API_REPLY_REPLY, {
            "type": 1, "oid": aid, "root": root, "ps": 20, "pn": page,
        }, no_retry_codes=(12006,))  # 12006=评论不存在/已删除，终态无需重试
        if not d:
            return None
        return d["data"].get("replies") or []

    def _norm(self, c, layer, bvid):
        content = c.get("content", {})
        member = c.get("member", {})
        return {
            "rpid": c.get("rpid"),
            "bvid": bvid,
            "layer": layer,
            "text": content.get("message", ""),
            "ctime": c.get("ctime"),
            "like": c.get("like", 0),
            "uname": member.get("uname", ""),
            "level": member.get("level", 0),
            "ip": member.get("ip_agent", ""),
            "root": c.get("root"),
            "rcount": c.get("rcount", 0),
            "category": "",
        }

    def _save(self, bvid, rows):
        """追加 JSONL，去重；返回新增条数"""
        path = os.path.join(self.out_dir, f"{bvid}.jsonl")
        seen = set()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            seen.add(json.loads(line).get("rpid"))
                        except Exception:
                            pass
        new_rows = [r for r in rows if r.get("rpid") not in seen and r.get("text")]
        with open(path, "a", encoding="utf-8") as f:
            for r in new_rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return len(new_rows)

    def _count_existing(self, bvid):
        path = os.path.join(self.out_dir, f"{bvid}.jsonl")
        if not os.path.exists(path):
            return 0
        n = 0
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
        return n

    # ---------- 采样策略 ----------
    def crawl_hot(self, bvid, pages=30):
        """热度排序 mode=3 采样：高赞评论，时间分布较广"""
        info = self.get_video_info(bvid)
        if not info:
            return
        aid = info["aid"]
        cursor = 0
        rows = []
        got = 0
        for _ in range(pages):
            if got >= pages * 20:
                break
            replies, cursor = self._fetch_main(aid, 3, cursor)
            if not replies:
                print(f"[{bvid}] 热度层提前结束(第{_}页)")
                break
            rows += [self._norm(c, "hot", bvid) for c in replies]
            got += len(replies)
            self._sleep()
            if not cursor:
                break
        added = self._save(bvid, rows)
        print(f"[{bvid}] 热度层: 抓{got}条(新增{added})")

    def _probe_time(self, aid, cursor):
        replies, _ = self._fetch_main(aid, 2, cursor)
        self._sleep(1.2)   # 探测节流：二分会连续请求，务必放慢避免风控
        if not replies:
            return None
        return replies[0]["ctime"]

    def _find_cursor_for_ts(self, aid, target_ts, lo, hi, depth=0):
        """在游标[lo,hi]间二分找 ctime 接近 target_ts 的游标。
        mode=2 语义：next 越大 -> 时间越新(单调)。
        注意：B站已限制主评论游标翻页(任意数字next返回空)，探测失败即置位
        _time_probe_dead，本次会话内不再对后续月份点做无效二分。
        """
        if depth > 18 or lo > hi:
            return None
        mid = (lo + hi) // 2
        ct = self._probe_time(aid, mid)
        if ct is None:
            self._time_probe_dead = True
            return None
        if abs(ct - target_ts) < 3 * 86400:
            return mid
        if ct > target_ts:
            return self._find_cursor_for_ts(aid, target_ts, lo, mid - 1, depth + 1)
        return self._find_cursor_for_ts(aid, target_ts, mid + 1, hi, depth + 1)

    def crawl_time_slices(self, bvid, slices=None, per_slice=3, month_points=None):
        """mode=2 时间采样。
        month_points: [(年,月),...] 目标月份，None 时按视频生命周期自动生成(每年均分)。
        slices: 直接给定游标列表时使用(跳过探测)。
        """
        info = self.get_video_info(bvid)
        if not info:
            return
        aid = info["aid"]
        total = info.get("reply_count") or 0
        print(f"[{bvid}] {info['title']} 评论{total}条")

        if slices:
            cursors = slices
        elif self._time_probe_dead:
            print(f"[{bvid}] 时间层游标探测失效(B站限制主评论翻页)，仅从最新游标采样")
            cursors = [0]
        else:
            if not month_points:
                month_points = self._auto_months(info.get("pubdate") or 0, time.time(), step_months=3)
            print(f"[{bvid}] 目标月份: {month_points}")
            cursors = [0]  # 最新入口
            for y, m in month_points:
                target = datetime(y, m, 15).timestamp()
                lo, hi = 1, max(1, total)
                cur = self._find_cursor_for_ts(aid, target, lo, hi)
                if cur is not None:
                    cursors.append(cur)
        print(f"[{bvid}] 采样游标数: {len(cursors)}")

        for cur in cursors:
            got = 0
            for _ in range(per_slice):
                replies, _ = self._fetch_main(aid, 2, cur)
                if not replies:
                    break
                rows = [self._norm(c, "time_slice", bvid) for c in replies]
                self._save(bvid, rows)
                t = datetime.fromtimestamp(replies[0]["ctime"]).strftime("%Y-%m-%d")
                got += len(rows)
                self._sleep()
                cur += 1  # 顺延一游标取下一页
            print(f"[{bvid}] 时间层点(游标{cur}): 抓{got}条", flush=True)

    def _auto_months(self, pub, now, step_months=3):
        months = []
        p = datetime.fromtimestamp(pub)
        n = datetime.fromtimestamp(now)
        y, m = p.year, p.month
        while (y, m) <= (n.year, n.month):
            months.append((y, m))
            m += step_months
            if m > 12:
                m -= 12
                y += 1
        return months

    def crawl_replies_for_main(self, bvid, main_rpids=None, max_replies=60, roots=80, pages=5):
        """对若干主楼抓子评论(pn分页，B站限制主评论翻页后的主要增量通道)。
        roots 未指定时从已有语料挑子评论数最多的主楼，优先挖大热评楼。
        """
        info = self.get_video_info(bvid)
        if not info:
            return
        aid = info["aid"]
        # 若无指定主楼，从已有 jsonl 里挑子评论数最多的主楼
        if not main_rpids:
            main_rpids = self._pick_roots(bvid, roots)
        total = 0
        for rpid in main_rpids:
            rows = []
            for pn in range(1, pages + 1):
                replies = self._fetch_reply(aid, rpid, pn)
                if not replies:
                    break
                rows += [self._norm(c, "sub", bvid) for c in replies]
                self._sleep()
                if len(rows) >= max_replies:
                    break
            if rows:
                total += self._save(bvid, rows)
        print(f"[{bvid}] 子评论层: 新增{total}条", flush=True)

    def _pick_roots(self, bvid, n, min_rcount=2):
        path = os.path.join(self.out_dir, f"{bvid}.jsonl")
        roots = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                        if r.get("rcount", 0) >= min_rcount and r.get("root") == 0:
                            roots.append((r.get("rcount", 0), r["rpid"]))
                    except Exception:
                        continue
        roots.sort(reverse=True)  # 子评论数多的主楼优先，单位请求产出更高
        return [rp for _, rp in roots[:n]]

    def to_json(self, bvid):
        path = os.path.join(self.out_dir, f"{bvid}.jsonl")
        rows, seen = [], set()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                        if r.get("rpid") and r["rpid"] not in seen:
                            seen.add(r["rpid"])
                            rows.append(r)
                    except Exception:
                        continue
        info = self.get_video_info(bvid)
        out = {
            "meta": info or {"bvid": bvid},
            "count": len(rows),
            "comments": rows,
        }
        out_path = os.path.join(self.out_dir, f"{bvid}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(f"[{bvid}] 合并完成: {len(rows)}条 -> {out_path}")
        return out_path


def crawl_video(crawler, bvid, target_count=5000, slices=None, month_points=None, hot_pages=60):
    info = crawler.get_video_info(bvid)
    if not info:
        print(f"[{bvid}] 获取信息失败，跳过")
        return
    print(f"===== 开始爬取 {bvid}: {info['title']} =====")
    crawler.crawl_time_slices(bvid, slices=slices, per_slice=3, month_points=month_points)
    crawler.crawl_hot(bvid, pages=hot_pages)
    # 主评论翻页已被B站限制(仅最新/热度各3条可达)，子评论层为增量主力
    crawler.crawl_replies_for_main(bvid, roots=80, max_replies=60, pages=5)
    crawler.to_json(bvid)
    print(f"[{bvid}] 当前累计: {crawler._count_existing(bvid)}条")


# ---------- 语料级近重复清洗 ----------
def _cb_ngrams(text, n=2):
    t = re.sub(r"[\s\W_]+", "", text or "")
    if len(t) < n:
        return {t} if t else set()
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def _cb_jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def dedup_corpus(bvid, out_dir, threshold=0.7):
    """去除语料中高度相似的刷屏评论(同一人连发/复制粘贴模板)。
    保留每个相似簇中点赞最高的一条，写回 .json 与 .jsonl。
    threshold: bigram-jaccard >= 此值视为重复。0.7 只去真重复/微变体，保留差异评论。
    """
    path = os.path.join(out_dir, f"{bvid}.json")
    if not os.path.exists(path):
        print(f"[dedup] {bvid} 无语料文件")
        return 0, 0
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    comments = d.get("comments", [])
    # 按点赞降序，簇代表取高赞
    comments.sort(key=lambda c: c.get("like", 0), reverse=True)
    kept, kept_sets = [], []
    removed = 0
    for c in comments:
        bg = _cb_ngrams(c.get("text", ""))
        if not bg:
            removed += 1
            continue
        # 与已保留样本比较(全量O(n^2)，n~3k可接受)
        if any(_cb_jaccard(bg, s) >= threshold for s in kept_sets):
            removed += 1
            continue
        kept_sets.append(bg)
        kept.append(c)
    d["comments"] = kept
    d["count"] = len(kept)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    # 同步 jsonl(只留去重后集合)
    jsonl = os.path.join(out_dir, f"{bvid}.jsonl")
    with open(jsonl, "w", encoding="utf-8") as f:
        for c in kept:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"[dedup] {bvid}: {len(comments)} -> {len(kept)} (去除 {removed} 条近重复)")
    return len(comments), len(kept)


if __name__ == "__main__":
    import fire

    def run(bvid, out_dir="data/crawled", count=5000, dedup=False, threshold=0.7):
        c = CommentCrawler(out_dir)
        if dedup:
            dedup_corpus(bvid, out_dir, threshold=float(threshold))
            return
        crawl_video(c, bvid, target_count=count)

    fire.Fire(run)
