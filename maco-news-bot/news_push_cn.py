#!/usr/bin/env python3
import json
import os
import re
import time
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
TRANSLATE_TO_ZH = os.getenv("TRANSLATE_TO_ZH", "1") == "1"
TRANSLATE_SUMMARY = os.getenv("TRANSLATE_SUMMARY", "0") == "1"
SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "90"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
DIGEST_MODE = os.getenv("DIGEST_MODE", "1") == "1"
DIGEST_TITLE = os.getenv("DIGEST_TITLE", "宏观新闻汇总")

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "news_state.json"
FEEDS_FILE = BASE_DIR / "feeds.json"

translator = GoogleTranslator(source="auto", target="zh-CN")

session = requests.Session()
retry = Retry(total=2, connect=2, read=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
session.mount("http://", HTTPAdapter(max_retries=retry))
session.mount("https://", HTTPAdapter(max_retries=retry))

KEYWORD_RULES = [
    {
        "keywords": ["fed", "federal reserve", "rate hike", "rate cut", "powell", "美联储", "降息", "加息"],
        "asset": "A股/港股/美股/黄金/美元/加密",
        "bull": "降息预期升温通常利多风险资产与黄金，利空美元。",
        "bear": "加息或鹰派表态通常压制风险资产，利多美元。",
    },
    {
        "keywords": ["cpi", "ppi", "inflation", "通胀", "物价"],
        "asset": "股市/债市/黄金/美元",
        "bull": "通胀回落通常利多股市与债市，也有利于降息预期交易。",
        "bear": "通胀超预期通常打压股市，强化高利率预期。",
    },
    {
        "keywords": ["nonfarm", "payrolls", "unemployment", "就业", "失业率", "非农"],
        "asset": "美股/美元/黄金/加密",
        "bull": "就业温和走弱有时利多降息预期交易。",
        "bear": "就业过热通常强化高利率预期。",
    },
    {
        "keywords": ["oil", "opec", "crude", "原油", "opec+"],
        "asset": "原油/通胀链/A股周期股",
        "bull": "供给收缩或油价上行利多油气链。",
        "bear": "需求走弱或增产预期利空油价。",
    },
    {
        "keywords": ["tariff", "sanction", "trade war", "制裁", "关税", "贸易"],
        "asset": "A股出口链/全球股市/大宗商品",
        "bull": "缓和信号利多风险偏好。",
        "bear": "摩擦升级通常压制风险偏好。",
    },
    {
        "keywords": ["china", "pboc", "刺激", "社融", "信贷", "人民币", "央行"],
        "asset": "A股/港股/人民币/地产链",
        "bull": "宽信用、稳增长、刺激政策通常利多A股和港股。",
        "bear": "弱于预期的数据或收紧信号通常偏空。",
    },
    {
        "keywords": ["bitcoin", "btc", "ethereum", "eth", "crypto", "加密", "比特币", "以太坊"],
        "asset": "加密货币/美股风险偏好",
        "bull": "ETF流入、宽松预期、监管友好通常利多加密。",
        "bear": "监管收紧、美元走强或风险偏好下降通常利空加密。",
    },
]

TAG_RULES = [
    ("A股", ["a股", "china", "pboc", "社融", "信贷", "人民币", "地产", "刺激", "央行", "沪深", "中概"]),
    ("美股", ["us stocks", "wall street", "nasdaq", "s&p", "dow", "美股", "标普", "纳指"]),
    ("黄金", ["gold", "黄金", "bullion"]),
    ("原油", ["oil", "crude", "opec", "原油", "opec+"]),
    ("加密", ["bitcoin", "btc", "ethereum", "eth", "crypto", "加密", "比特币", "以太坊"]),
    ("汇率债券", ["treasury", "yield", "bond", "dollar", "fx", "汇率", "债", "美债", "美元"]),
]

POSITIVE_HINTS = ["cut", "easing", "stimulus", "cooling", "decline", "support", "boost", "record inflow", "宽松", "刺激", "回落", "支持", "提振", "改善", "下降"]
NEGATIVE_HINTS = ["hike", "hotter", "surge", "warning", "sanction", "tariff", "selloff", "drop", "tightening", "加息", "制裁", "关税", "下滑", "走弱", "紧缩", "上升"]


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


def zh(text: str, lang: str = "auto", allow_summary_translate: bool = True) -> str:
    text = clean_text(text)
    if not text:
        return ""
    if not TRANSLATE_TO_ZH or lang.lower().startswith("zh"):
        return text
    if not allow_summary_translate:
        return text
    try:
        short_text = text[:600]
        return translator.translate(short_text)
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


def infer_impact(text: str):
    haystack = (text or "").lower()
    matched_assets = []
    views = []
    score = 0

    for rule in KEYWORD_RULES:
        if any(keyword.lower() in haystack for keyword in rule["keywords"]):
            matched_assets.append(rule["asset"])
            views.append(f"若偏鸽/偏暖：{rule['bull']}")
            views.append(f"若偏鹰/偏冷：{rule['bear']}")

    for hint in POSITIVE_HINTS:
        if hint.lower() in haystack:
            score += 1
    for hint in NEGATIVE_HINTS:
        if hint.lower() in haystack:
            score -= 1

    if score >= 2:
        direction = "偏利多风险资产"
    elif score <= -2:
        direction = "偏利空风险资产"
    else:
        direction = "中性，需结合正文判断"

    assets = "；".join(dict.fromkeys(matched_assets)) if matched_assets else "A股/港股/美股/黄金/原油/加密"
    conclusion = views[:2] if views else ["需要结合新闻正文进一步判断对市场的实际影响。"]
    return assets, direction, conclusion


def infer_tags(text: str):
    haystack = (text or "").lower()
    tags = []
    for tag, keywords in TAG_RULES:
        if any(keyword.lower() in haystack for keyword in keywords):
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
        lang = feed.get("lang", "auto")
        for e in parsed.entries[:15]:
            uid = getattr(e, "id", "") or getattr(e, "link", "") or (
                getattr(e, "title", "") + str(getattr(e, "published", ""))
            )
            if not uid or uid in sent:
                continue
            title = clean_text(getattr(e, "title", ""))
            summary = clean_text(getattr(e, "summary", "") or getattr(e, "description", "") or "")
            summary_short = summary[:SUMMARY_MAX_CHARS]
            link = getattr(e, "link", "")
            published = getattr(e, "published", "")
            published_dt = parse_dt(published)
            if title:
                title_cn = zh(title, lang, allow_summary_translate=True)
                summary_text = zh(summary_short, lang, allow_summary_translate=TRANSLATE_SUMMARY)
                text_for_analysis = f"{title_cn} {summary_text}"
                assets, direction, conclusion = infer_impact(text_for_analysis)
                tags = infer_tags(text_for_analysis)
                items.append(
                    {
                        "uid": uid,
                        "title": title_cn or title,
                        "summary": summary_text,
                        "link": link,
                        "published": published,
                        "published_ts": published_dt.timestamp() if published_dt else 0,
                        "source": source_name,
                        "assets": assets,
                        "direction": direction,
                        "conclusion": conclusion,
                        "tags": tags,
                    }
                )
    items.sort(key=lambda x: x.get("published_ts", 0), reverse=True)
    return items


def format_single_message(item):
    summary_cn = item["summary"]
    if len(summary_cn) > 180:
        summary_cn = summary_cn[:180] + "…"

    parts = [
        "【宏观新闻】",
        f"标签：{' / '.join(item['tags'])}",
        f"来源：{item['source']}",
        f"标题：{item['title']}",
    ]
    if summary_cn:
        parts.append(f"摘要：{summary_cn}")
    parts.append(f"影响资产：{item['assets']}")
    parts.append(f"影响方向：{item['direction']}")
    parts.append(f"一句话解读：{item['conclusion'][0]}")
    if len(item["conclusion"]) > 1:
        parts.append(f"补充：{item['conclusion'][1]}")
    if item["published"]:
        parts.append(f"时间：{item['published']}")
    if item["link"]:
        parts.append(f"链接：{item['link']}")
    return "\n".join(parts)


def build_digest(items):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    grouped = defaultdict(list)
    for item in items:
        for tag in item["tags"]:
            grouped[tag].append(item)

    parts = [f"【{DIGEST_TITLE}】", f"时间：{now}", f"共 {len(items)} 条新消息"]
    for tag in ["A股", "美股", "黄金", "原油", "加密", "汇率债券", "综合"]:
        if tag not in grouped:
            continue
        parts.append("")
        parts.append(f"# {tag}")
        for idx, item in enumerate(grouped[tag][:3], start=1):
            summary = item["summary"]
            if len(summary) > 60:
                summary = summary[:60] + "…"
            bullet = f"{idx}. {item['title']}"
            if summary:
                bullet += f"｜{summary}"
            bullet += f"｜{item['direction']}"
            parts.append(bullet)

    parts.append("")
    parts.append("重点解读：")
    for item in items[:3]:
        parts.append(f"- {' / '.join(item['tags'])}：{item['conclusion'][0]}")

    text = "\n".join(parts)
    return text[:3900]


def main():
    sent = load_sent()
    items = collect_items(sent)[:MAX_ITEMS]
    if not items:
        print("pushed 0 new items")
        return

    if DIGEST_MODE:
        try:
            send(build_digest(items))
            for item in items:
                sent.add(item["uid"])
            save_sent(sent)
            print(f"pushed digest with {len(items)} items")
            return
        except Exception as ex:
            print("digest send failed:", ex)

    pushed = 0
    for item in items:
        try:
            send(format_single_message(item))
            sent.add(item["uid"])
            pushed += 1
            time.sleep(1.0)
        except Exception as ex:
            print("send failed:", ex)

    save_sent(sent)
    print(f"pushed {pushed} new items")


if __name__ == "__main__":
    main()
