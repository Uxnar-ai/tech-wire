# tech wire · 技术资讯聚合

> Hacker News、Lobsters、arXiv cs.AI 三源聚合，每 30 分钟同步，带按天存档与关键词热度。

[English](README.en.md) | 中文

## 这是什么

三个源各用一个官方接口：HN 走 Algolia 的 `search?tags=front_page`（一次拿全，避免逐条请求），Lobsters 走 `hottest.json`，arXiv 走官方 Atom 查询。每个域名每轮只发一个请求，源之间留 1.2 秒间隔——比看一次网页还轻。结果落 SQLite，`first_seen == last_seen` 判定 NEW，首页只显示 3 小时内活跃的条目。第二天起这些条目不会消失：`/day/<日期>` 把同一天首次入库的全部条目按分数排好，`/topics` 统计最近七天标题里的高频词。

## 功能

- 三个源全部走官方 JSON / Atom 接口，不解析 HTML、不碰反爬
- 每域名每轮 1 个请求，源间隔 1.2 秒，30 分钟一轮
- SQLite 增量存储，NEW 标记靠首次见到与最后见到的时间比对
- 按天存档 `/day/<日期>`，同日入库的条目按分数排好，可前后翻页
- `/topics` 用纯本地词频统计最近七天的高频词，不调用任何模型
- 单源失败不影响其余两栏，失败信息显示在页脚

## 技术栈

Python 3.12 · Flask 3.1 · SQLite · requests

## 运行

```bash
pip install -r requirements.txt
python app.py
```

## 关于

本项目属于「auto-lab」每日自主实验系列——由 [Nix](https://github.com/Uxnar-ai) 在自建服务器上自动生成、部署并维护。

代码中的 `<SERVER_IP>`、`<LOCAL_PATH>` 等占位符是发布时的脱敏处理，实际运行请替换为你自己的值。仓库内不含任何真实凭据、内网地址或私人信息。

## 许可

MIT
