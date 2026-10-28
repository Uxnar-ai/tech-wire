# tech wire — tech news aggregator

> Hacker News, Lobsters and arXiv cs.AI aggregated into one page with daily archives and keyword trends, refreshed every 30 minutes using official APIs only.

English | [中文](README.md)

## What it is

Each source uses exactly one official endpoint: HN through Algolia's `search?tags=front_page` (everything in one call instead of per-item requests), Lobsters through `hottest.json`, arXiv through its Atom API. One request per domain per cycle, with 1.2s between sources — lighter than loading the site once in a browser. Results land in SQLite, `first_seen == last_seen` marks a story as NEW, and the front page shows only items active in the last 3 hours. Nothing is thrown away afterwards: `/day/<date>` lists everything first seen that day, ranked by score, and `/topics` counts the most frequent words in the last seven days of headlines.

## Features

- All three sources use official JSON / Atom endpoints — no HTML scraping, no anti-bot evasion
- One request per domain per cycle, 1.2s apart, every 30 minutes
- Incremental SQLite storage; NEW is derived from first-seen vs last-seen
- Daily archive at `/day/<date>`, ranked by score, with previous/next navigation
- `/topics` ranks the week's most frequent headline words with plain local counting — no model calls
- A failing source never breaks the other columns — errors surface in the footer

## Stack

Python 3.12 · Flask 3.1 · SQLite · requests

## Run

```bash
pip install -r requirements.txt
python app.py
```

## About

Part of the **auto-lab** series — small projects written, deployed and maintained automatically by [Nix](https://github.com/Uxnar-ai) on a self-hosted server.

Placeholders such as `<SERVER_IP>` and `<LOCAL_PATH>` are sanitised values applied at publish time. This repository contains no credentials, internal addresses or personal data.

## License

MIT
