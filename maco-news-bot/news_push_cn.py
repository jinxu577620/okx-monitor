#!/usr/bin/env python3
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
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
MORNING_TITLE = os.getenv("MORNING_TITLE", "宏观晨报")
EVENING_TITLE = os.getenv("EVENING_TITLE", "宏观晚报")
SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "90"))
FINAL_TRANSLATE_TO_ZH = os.getenv("FINAL_TRANSLATE_TO_ZH", "1") == "1"

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "news_state.json"
WINDOW_STATE_FILE = BASE_DIR / "window_state.json"
FEEDS_FILE = BASE_DIR / "feeds.json"

translator = GoogleTranslator(source="auto", target="zh-CN")

session = requests.Session()
retry = Retry(total=2, connect=2, read=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
session.mount("http://", HTTPAdapter(max_retries=retry))
session.mount("https://", HTTPAdapter(max_retries=retry))

TAG_RULES = [
    ("特朗普", ["trump", "donald trump", "特朗普"]),
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


def load_window_state():
    return load_json(WINDOW_STATE_FILE, {})


def save_window_state(state):
    save_json(WINDOW_STATE_FILE, state)


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
        return translator.translate(text[:500])
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
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            return dt
        return dt.astimezone().replace(tzinfo=None)
    except Exception:
        return None


def infer_direction_score(text: str):
    hay = (text or "").lower()
    score = 0
    for hint in POSITIVE_HINTS:
        if hint in hay:
            score += 1
    for hint in NEGATIVE_HINTS:
        if hint in hay:
            score -= 1
    return score


def infer_direction_label(score: int):
    if score >= 2:
        return "偏多"
    if score <= -2:
        return "偏空"
    return "中性"


def infer_tags(text: str):
    hay = (text or "").lower()
    tags = []
    for tag, keywords in TAG_RULES:
        if any(keyword in hay for keyword in keywords):
            tags.append(tag)
    return tags or ["综合"]


def collect_all_items():
    items = []
    feeds = load_feeds()
    for feed in feeds:
        try:
            parsed = feedparser.parse(feed["url"])
        except Exception as ex:
            print(f"feed parse failed: {feed.get('name', feed['url'])}: {ex}")
            continue
        source_name = feed.get("name", feed["url"])
        for e in parsed.entries[:20]:
            uid = getattr(e, "id", "") or getattr(e, "link", "") or (
                getattr(e, "title", "") + str(getattr(e, "published", ""))
            )
            if not uid:
                continue
            title = clean_text(getattr(e, "title", ""))
            summary = clean_text(getattr(e, "summary", "") or getattr(e, "description", "") or "")
            if len(summary) > SUMMARY_MAX_CHARS:
                summary = summary[:SUMMARY_MAX_CHARS] + "..."
            published = getattr(e, "published", "")
            dt = parse_dt(published)
            text = f"{title} {summary}"
            score = infer_direction_score(text)
            items.append(
                {
                    "uid": uid,
                    "source": source_name,
                    "title": title,
                    "summary": summary,
                    "link": getattr(e, "link", ""),
                    "published": published,
                    "published_ts": dt.timestamp() if dt else 0,
                    "published_dt": dt.isoformat() if dt else "",
                    "direction_score": score,
                    "direction": infer_direction_label(score),
                    "tags": infer_tags(text),
                }
            )
    items.sort(key=lambda x: x.get("published_ts", 0), reverse=True)
    return items


def current_digest_title(now: datetime) -> str:
    hour = now.hour
    if 5 <= hour < 12:
        return MORNING_TITLE
    if 18 <= hour < 24:
        return EVENING_TITLE
    return DIGEST_TITLE


def current_window(now: datetime):
    hour = now.hour
    if 5 <= hour < 12:
        start = (now - timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
        end = now.replace(hour=8, minute=0, second=0, microsecond=0)
        return "morning", start, end, MORNING_TITLE
    if 18 <= hour < 24:
        start = now.replace(hour=8, minute=0, second=0, microsecond=0)
        end = now.replace(hour=20, minute=0, second=0, microsecond=0)
        return "evening", start, end, EVENING_TITLE
    start = now - timedelta(hours=12)
    end = now
    return "rolling", start, end, DIGEST_TITLE


def zh_short(text: str) -> str:
    text = clean_text(text)
    if not text:
        return ""
    if not FINAL_TRANSLATE_TO_ZH:
        return text
    return maybe_translate(text)


def summarize_tag(grouped, tag):
    if tag not in grouped or not grouped[tag]:
        return "暂无明显新增驱动"
    scores = sum(item["direction_score"] for item in grouped[tag][:3])
    if scores >= 2:
        return "短线偏多，关注情绪延续"
    if scores <= -2:
        return "短线偏空，注意回撤压力"
    return "多空交织，观察后续发酵"


def build_fixed_chinese_digest(items, title):
    grouped = defaultdict(list)
    for item in items:
        for tag in item["tags"]:
            grouped[tag].append(item)

    trump_items = [item for item in items if "特朗普" in item["tags"]]
    other_items = [item for item in items if "特朗普" not in item["tags"]]
    top_items = (trump_items + other_items)[:3]
    quick_items = items[:5]
    total_score = sum(item["direction_score"] for item in items)
    if total_score >= 3:
        overall = "整体偏多，风险偏好略有抬升。"
    elif total_score <= -3:
        overall = "整体偏空，短线注意避险情绪。"
    else:
        overall = "整体偏中性，重点看后续催化是否扩散。"

    lines = [title, ""]
    lines.append("今日最重要3条")
    for i, item in enumerate(top_items, 1):
        lines.append(f"- {i}. [{'/'.join(item['tags'])}] {zh_short(item['title'])}")
    lines.append("")

    lines.append("市场影响")
    if grouped.get('特朗普'):
        lines.append("- 特朗普：相关表态已触发优先关注，注意对美股、美元、黄金与加密情绪的扰动。")
    lines.append(f"- A股：{summarize_tag(grouped, 'A股')}")
    lines.append(f"- 美股：{summarize_tag(grouped, '美股')}")
    lines.append(f"- 黄金：{summarize_tag(grouped, '黄金')}")
    lines.append(f"- 原油：{summarize_tag(grouped, '原油')}")
    lines.append(f"- 加密：{summarize_tag(grouped, '加密')}")
    lines.append("")

    lines.append("简讯速览")
    for item in quick_items:
        lines.append(f"- [{'/'.join(item['tags'])}] {zh_short(item['title'])}（{item['direction']}）")
    lines.append("")

    lines.append("一句话总结")
    lines.append(f"- {overall}")
    return "\n".join(lines)


def select_window_items(items, start, end):
    start_ts = start.timestamp()
    end_ts = end.timestamp()
    picked = [i for i in items if i.get("published_ts", 0) and start_ts <= i["published_ts"] <= end_ts]
    return picked[:MAX_ITEMS]


def main():
    now = datetime.now()
    window_key, start, end, title = current_window(now)
    all_items = collect_all_items()
    items = select_window_items(all_items, start, end)

    if not items and window_key == "morning":
        items = all_items[:MAX_ITEMS]
    elif not items and window_key == "evening":
        items = all_items[:MAX_ITEMS]

    if not items:
        print("pushed 0 new items")
        return

    window_state = load_window_state()
    state_key = f"{window_key}:{start.strftime('%Y%m%d%H%M')}-{end.strftime('%Y%m%d%H%M')}"
    if window_state.get(window_key) == state_key:
        print(f"already sent for {state_key}")
        return

    final_text = build_fixed_chinese_digest(items, title)
    send(final_text)

    sent = load_sent()
    for item in items:
        sent.add(item["uid"])
    save_sent(sent)

    window_state[window_key] = state_key
    save_window_state(window_state)
    print(f"pushed digest with {len(items)} items for {state_key}")


if __name__ == "__main__":
    main()
