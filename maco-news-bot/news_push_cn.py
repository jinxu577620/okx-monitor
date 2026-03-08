#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path

import feedparser
import requests
from deep_translator import GoogleTranslator

BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
CHAT_ID = os.getenv("TG_CHAT_ID", "")
MAX_ITEMS = int(os.getenv("MAX_ITEMS", "8"))
TRANSLATE_TO_ZH = os.getenv("TRANSLATE_TO_ZH", "1") == "1"

FEEDS = [
    "https://rsshub.app/reuters/world",
    "https://rsshub.app/reuters/business",
]

STATE_FILE = Path("news_state.json")


def load_sent():
    if not STATE_FILE.exists():
        return set()
    try:
        return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_sent(sent):
    STATE_FILE.write_text(
        json.dumps(list(sent)[-5000:], ensure_ascii=False),
        encoding="utf-8",
    )


translator = GoogleTranslator(source="auto", target="zh-CN")


def zh(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if not TRANSLATE_TO_ZH:
        return text
    try:
        return translator.translate(text)
    except Exception:
        return text


def send(msg: str):
    if not BOT_TOKEN or not CHAT_ID:
        raise SystemExit("请先设置环境变量 TG_BOT_TOKEN 和 TG_CHAT_ID")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": msg[:4000]}, timeout=20)
    r.raise_for_status()


def collect_items(sent):
    items = []
    for feed in FEEDS:
        parsed = feedparser.parse(feed)
        for e in parsed.entries[:30]:
            uid = getattr(e, "id", "") or getattr(e, "link", "") or (
                getattr(e, "title", "") + str(getattr(e, "published", ""))
            )
            if not uid or uid in sent:
                continue
            title = getattr(e, "title", "").strip()
            summary = getattr(e, "summary", "") or getattr(e, "description", "") or ""
            link = getattr(e, "link", "")
            published = getattr(e, "published", "")
            if title:
                items.append(
                    {
                        "uid": uid,
                        "title": title,
                        "summary": summary,
                        "link": link,
                        "published": published,
                    }
                )
    return items


def format_message(item):
    title_cn = zh(item["title"])
    summary_cn = zh(item["summary"])
    summary_cn = summary_cn.replace("\n", " ").strip()
    if len(summary_cn) > 220:
        summary_cn = summary_cn[:220] + "…"

    parts = [
        "【宏观快讯】",
        f"标题：{title_cn or item['title']}",
    ]
    if summary_cn:
        parts.append(f"摘要：{summary_cn}")
    if item["published"]:
        parts.append(f"时间：{item['published']}")
    if item["link"]:
        parts.append(f"链接：{item['link']}")
    return "\n".join(parts)


def main():
    sent = load_sent()
    items = collect_items(sent)
    pushed = 0

    for item in items[:MAX_ITEMS]:
        try:
            send(format_message(item))
            sent.add(item["uid"])
            pushed += 1
            time.sleep(1.0)
        except Exception as ex:
            print("send failed:", ex)

    save_sent(sent)
    print(f"pushed {pushed} new items")


if __name__ == "__main__":
    main()
