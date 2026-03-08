#!/usr/bin/env python3
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from email.utils import parsedate_to_datetime

import feedparser
import requests
from deep_translator import GoogleTranslator
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
CHAT_ID = os.getenv("TG_CHAT_ID", "")
MAX_ITEMS = int(os.getenv("MAX_ITEMS", "8"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
DIGEST_TITLE = os.getenv("DIGEST_TITLE", "宏观新闻汇总")
SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "90"))
FINAL_TRANSLATE_TO_ZH = os.getenv("FINAL_TRANSLATE_TO_ZH", "1") == "1"

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "news_state.json"
FEEDS_FILE = BASE_DIR / "feeds.json"

translator = GoogleTranslator(source="auto", target="zh-CN")

session = requests.Session()
retry = Retry(total=2, connect=2, read=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
session.mount("http://", HTTPAdapter(max_retries=retry))
session.mount("https://", HTTPAdapter(max_retries=retry))

TAG_RULES = [
    ("A股", ["china", "pboc", "stimulus", "yuan", "credit", "property", "beijing", "shanghai", "shenzhen", "中概"]),
    ("美股", ["us stocks", "wall street", "nasdaq", "s&p", "dow", "fed", "treasury"]),
    ("黄金", ["gold", "bullion"]),
    ("原油", ["oil", "crude", "opec"]),
    ("加密", ["bitcoin", "btc", "ethereum", "eth", "crypto"]),
    ("汇率债券", ["treasury", "yield", "bond", "dollar", "fx", "yen", "euro"]),
]

POSITIVE_HINTS = ["cut", "easing", "stimulus", "cooling", "decline", "support", "boost", "record inflow", "deal", "rebound"]
NEGATIVE_HINTS = ["hike", "hotter", "surge", "warning", "sanction", "tariff", "selloff", "drop", "tightening", "war", "slump"]


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_sent():
    return set(load_json(STATE_FILE, []))


def save_sent(sent):
    save_json(STATE_FILE, list(sent)[-5000:])


def load_feeds():
    return load_json(FEEDS_FILE, [])


def clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def maybe_translate(text: str) -> str:
    text = clean_text(text)
    if not text or not FINAL_TRANSLATE_TO_ZH:
        return text
    try:
        return translator.translate(text[:3500])
    except Exception:
        return text


def send(msg: str):
    if not BOT_TOKEN or not CHAT_ID:
        raise SystemExit("请先设置环境变量 TG_BOT_TOKEN 和 TG_CHAT_ID")
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = session.post(url, json={"chat_id": CHAT_ID, "text": msg[:4000]}, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()


def parse_dt(text: str):
    if not text:
        return None
    try:
        return parsedate_to_datetime(text)
    except Exception:
        return None


def infer_direction(text: str):
    hay = (text or "").lower()
    score = 0
    for hint in POSITIVE_HINTS:
        if hint in hay:
            score += 1
    for hint in NEGATIVE_HINTS:
        if hint in hay:
            score -= 1
    if score >= 2:
        return "Risk-on / bullish"
    if score <= -2:
        return "Risk-off / bearish"
    return "Neutral / mixed"


def infer_tags(text: str):
    hay = (text or "").lower()
    tags = []
    for tag, keywords in TAG_RULES:
        if any(keyword in hay for keyword in keywords):
            tags.append(tag)
    return tags or ["综合"]


def collect_items(sent):
    items = []
    feeds = load_feeds()
    for feed in feeds:
        try:
            parsed = feedparser.parse(feed["url"])
        except Exception as ex:
            print(f"feed parse failed: {feed.get('name', feed['url'])}: {ex}")
            continue
        source_name = feed.get("name", feed["url"])
        for e in parsed.entries[:15]:
            uid = getattr(e, "id", "") or getattr(e, "link", "") or (
                getattr(e, "title", "") + str(getattr(e, "published", ""))
            )
            if not uid or uid in sent:
                continue
            title = clean_text(getattr(e, "title", ""))
            summary = clean_text(getattr(e, "summary", "") or getattr(e, "description", "") or "")
            if len(summary) > SUMMARY_MAX_CHARS:
                summary = summary[:SUMMARY_MAX_CHARS] + "..."
            published = getattr(e, "published", "")
            dt = parse_dt(published)
            text = f"{title} {summary}"
            items.append(
                {
                    "uid": uid,
                    "source": source_name,
                    "title": title,
                    "summary": summary,
                    "link": getattr(e, "link", ""),
                    "published": published,
                    "published_ts": dt.timestamp() if dt else 0,
                    "direction": infer_direction(text),
                    "tags": infer_tags(text),
                }
            )
    items.sort(key=lambda x: x.get("published_ts", 0), reverse=True)
    return items[:MAX_ITEMS]


def build_english_digest(items):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    grouped = defaultdict(list)
    for item in items:
        for tag in item["tags"]:
            grouped[tag].append(item)

    parts = [f"[{DIGEST_TITLE}]", f"Time: {now}", f"Total new items: {len(items)}", ""]
    for tag in ["A股", "美股", "黄金", "原油", "加密", "汇率债券", "综合"]:
        if tag not in grouped:
            continue
        parts.append(f"# {tag}")
        for idx, item in enumerate(grouped[tag][:3], start=1):
            bullet = f"{idx}. {item['title']}"
            if item['summary']:
                bullet += f" | {item['summary']}"
            bullet += f" | {item['direction']}"
            parts.append(bullet)
        parts.append("")

    parts.append("Key takeaways:")
    top = items[:3]
    for item in top:
        parts.append(f"- {'/'.join(item['tags'])}: {item['direction']} based on headline flow.")

    parts.append("")
    parts.append("Please translate the above macro digest into concise Chinese for a trader. Keep structure, keep tags, and write market impact in Chinese.")
    return "\n".join(parts)[:3600]


def main():
    sent = load_sent()
    items = collect_items(sent)
    if not items:
        print("pushed 0 new items")
        return

    english_digest = build_english_digest(items)
    final_text = maybe_translate(english_digest)
    send(final_text)

    for item in items:
        sent.add(item["uid"])
    save_sent(sent)
    print(f"pushed digest with {len(items)} items")


if __name__ == "__main__":
    main()
