#!/usr/bin/env python3
"""tech wire：HN / Lobsters / arXiv cs.AI 三源聚合，每 30 分钟同步一次。

所有数据来自公开 API，单域名每轮只发 1 个请求，请求间留 1.2s 间隔。
"""
import json
import os
import re
import sqlite3
import threading
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import requests
from flask import Flask, jsonify, render_template

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "wire.db")
PORT = int(os.environ.get("PORT") or os.environ.get("WIRE_PORT") or "8820")
REFRESH_SEC = 1800
UA = "auto-lab/1.0 (+https://github.com/Uxnar-ai/tech-wire; <CONTACT_EMAIL>)"
TIMEOUT = 25

app = Flask(__name__)
_lock = threading.Lock()


# ---------- 数据源 ----------

def fetch_hn():
    """Hacker News 首页：用 Algolia 官方接口，一次拿全，避免逐条请求。"""
    r = requests.get(
        "https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=18",
        headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for h in r.json().get("hits", []):
        oid = h.get("objectID")
        out.append({
            "source": "hn",
            "guid": str(oid),
            "title": (h.get("title") or h.get("story_title") or "").strip(),
            "url": h.get("url") or f"https://news.ycombinator.com/item?id={oid}",
            "discuss": f"https://news.ycombinator.com/item?id={oid}",
            "score": int(h.get("points") or 0),
            "comments": int(h.get("num_comments") or 0),
            "meta": {"author": h.get("author") or ""},
        })
    return out


def fetch_lobsters():
    """Lobsters 热门：官方 JSON 端点。"""
    r = requests.get("https://lobste.rs/hottest.json",
                     headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for s in r.json()[:16]:
        out.append({
            "source": "lobsters",
            "guid": str(s.get("short_id")),
            "title": (s.get("title") or "").strip(),
            "url": s.get("url") or s.get("comments_url"),
            "discuss": s.get("comments_url") or "",
            "score": int(s.get("score") or 0),
            "comments": int(s.get("comment_count") or 0),
            "meta": {"tags": (s.get("tags") or [])[:4],
                     "author": s.get("submitter_user") or ""},
        })
    return out


def fetch_arxiv():
    """arXiv cs.AI 最新投稿，官方 Atom 接口一次请求。"""
    url = ("https://export.arxiv.org/api/query?search_query=cat:cs.AI"
           "&sortBy=submittedDate&sortOrder=descending&max_results=10")
    r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
    r.raise_for_status()
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(r.content)
    out = []
    for e in root.findall("a:entry", ns):
        eid = e.find("a:id", ns).text.rsplit("/", 1)[-1]
        authors = [a.find("a:name", ns).text
                   for a in e.findall("a:author", ns) if a.find("a:name", ns) is not None]
        summary = " ".join((e.find("a:summary", ns).text or "").split())
        pub = e.find("a:published", ns).text
        out.append({
            "source": "arxiv",
            "guid": eid,
            "title": " ".join((e.find("a:title", ns).text or "").split()),
            "url": f"https://arxiv.org/abs/{eid}",
            "discuss": "",
            "score": 0,
            "comments": 0,
            "meta": {"authors": authors[:3], "published": pub,
                     "abstract": summary[:180]},
        })
    return out


SOURCES = [("hn", fetch_hn), ("lobsters", fetch_lobsters), ("arxiv", fetch_arxiv)]


# ---------- 存储 ----------

def db():
    cx = sqlite3.connect(DB_PATH, timeout=10)
    cx.row_factory = sqlite3.Row
    return cx


def init_db():
    with db() as cx:
        cx.execute("""CREATE TABLE IF NOT EXISTS items(
            source TEXT, guid TEXT, title TEXT, url TEXT, discuss TEXT, meta TEXT,
            score INTEGER, comments INTEGER, first_seen INTEGER, last_seen INTEGER,
            PRIMARY KEY(source, guid))""")
        cx.execute("""CREATE TABLE IF NOT EXISTS meta(
            k TEXT PRIMARY KEY, v TEXT)""")


def set_meta(k, v):
    with db() as cx:
        cx.execute("INSERT INTO meta(k,v) VALUES(?,?) "
                   "ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


def get_meta(k, default=""):
    with db() as cx:
        row = cx.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return row["v"] if row else default


def upsert(items):
    now = int(time.time())
    with db() as cx:
        for it in items:
            cx.execute(
                """INSERT INTO items(source,guid,title,url,discuss,meta,score,comments,
                                     first_seen,last_seen)
                   VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(source,guid) DO UPDATE SET
                     title=excluded.title, score=excluded.score,
                     comments=excluded.comments, last_seen=excluded.last_seen""",
                (it["source"], it["guid"], it["title"], it["url"], it["discuss"],
                 json.dumps(it["meta"], ensure_ascii=False), it["score"], it["comments"],
                 now, now))


def collect():
    items, errors, stats = [], [], {}
    for name, fn in SOURCES:
        try:
            got = fn()
            stats[name] = len(got)
            items.extend(got)
        except Exception as exc:  # 单源失败不影响其余
            errors.append(f"{name}: {type(exc).__name__} {exc}"[:200])
            stats[name] = 0
        time.sleep(1.2)
    if items:
        upsert(items)
    set_meta("last_refresh", int(time.time()))
    set_meta("last_errors", json.dumps(errors, ensure_ascii=False))
    set_meta("last_stats", json.dumps(stats, ensure_ascii=False))
    return stats, errors


def refresh_loop():
    while True:
        try:
            collect()
        except Exception:
            pass
        time.sleep(REFRESH_SEC)


# ---------- 视图 ----------

def build_state():
    now = int(time.time())
    fresh_after = now - 3 * 3600
    with db() as cx:
        rows = cx.execute("SELECT * FROM items WHERE last_seen >= ? "
                          "ORDER BY score DESC, last_seen DESC", (fresh_after,)).fetchall()
    groups = {"hn": [], "lobsters": [], "arxiv": []}
    for r in rows:
        item = dict(r)
        item["meta"] = json.loads(item["meta"] or "{}")
        item["is_new"] = item["first_seen"] == item["last_seen"]
        groups.setdefault(item["source"], []).append(item)

    last = int(get_meta("last_refresh", "0") or 0)
    return {
        "groups": groups,
        "total": len(rows),
        "new_count": sum(1 for r in rows if r["first_seen"] == r["last_seen"]),
        "last_refresh": datetime.fromtimestamp(last).strftime("%m-%d %H:%M") if last else "—",
        "ago": (f"{int((now - last) / 60)} 分钟前" if last else "尚未同步"),
        "errors": json.loads(get_meta("last_errors", "[]") or "[]"),
        "stats": json.loads(get_meta("last_stats", "{}") or "{}"),
        "ts": now,
    }


@app.route("/")
def index():
    series = day_series(14)
    return render_template("index.html", st=build_state(), series=series,
                           peak=max([x["n"] for x in series] or [1]),
                           today=date.today().isoformat())


@app.route("/api/state")
def api_state():
    return jsonify(build_state())


@app.route("/healthz")
def healthz():
    return {"ok": True}


# ---------- 存档 / 关键词 ----------

STOP = set("""
the and for that with this from have has had not are was were you your our their his her its
they them there here what when where which who whom why how all any both each few more most
other some such only own same than too very can will just dont should now about into over
after before between under above off out up down again further then once here why how use used
using new news app apps year years day days week weeks time times make makes made get gets got
like just also may might must shall still even ever never much many one two three four five
''s n't
""".split())

WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#._-]{2,}")


def day_series(days=14):
    """近 N 天每天入库多少条（按首次见到的时间归日）。"""
    since = int(time.time()) - days * 86400
    with db() as cx:
        rows = cx.execute(
            "SELECT date(first_seen,'unixepoch','localtime') d, COUNT(*) n "
            "FROM items WHERE first_seen >= ? GROUP BY d ORDER BY d DESC",
            (since,)).fetchall()
    return [{"day": r["d"], "n": r["n"]} for r in rows]


def day_items(day):
    """某一天首次入库的全部条目，按分数与评论排序。"""
    with db() as cx:
        rows = cx.execute(
            "SELECT * FROM items "
            "WHERE date(first_seen,'unixepoch','localtime') = ? "
            "ORDER BY score DESC, comments DESC", (day,)).fetchall()
    out = {"hn": [], "lobsters": [], "arxiv": []}
    for r in rows:
        it = dict(r)
        it["meta"] = json.loads(it["meta"] or "{}")
        out.setdefault(it["source"], []).append(it)
    return out, len(rows)


def topics(days=7, limit=40):
    """最近 N 天标题里的高频词。纯本地分词，不调用任何外部服务。"""
    since = int(time.time()) - days * 86400
    with db() as cx:
        rows = cx.execute("SELECT title, url, source FROM items WHERE first_seen >= ?",
                          (since,)).fetchall()
    counter, sample = {}, {}
    for r in rows:
        for w in WORD.findall(r["title"] or ""):
            w = w.strip("._-").lower()
            if len(w) < 3 or w in STOP or w.isdigit():
                continue
            counter[w] = counter.get(w, 0) + 1
            sample.setdefault(w, {"title": r["title"], "url": r["url"],
                                  "source": r["source"]})
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    out = []
    for w, n in ranked:
        if n < 2:                     # 只出现一次的词没有「热度」可言
            break
        out.append({"word": w, "n": n, **sample[w]})
        if len(out) >= limit:
            break
    return {"words": out, "scanned": len(rows), "days": days}


@app.route("/day/<day>")
def day_view(day):
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return "日期格式应为 YYYY-MM-DD", 400
    groups, total = day_items(day)
    series = day_series(14)
    peak = max([x["n"] for x in series] or [1])
    prev_day = (datetime.strptime(day, "%Y-%m-%d").date() - timedelta(days=1)).isoformat()
    next_day = (datetime.strptime(day, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
    return render_template("day.html", day=day, groups=groups, total=total,
                           prev_day=prev_day, next_day=next_day,
                           series=series, peak=peak)


@app.route("/topics")
def topics_view():
    series = day_series(14)
    return render_template("topics.html", tp=topics(7), series=series,
                           peak=max([x["n"] for x in series] or [1]))


init_db()
threading.Thread(target=refresh_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
