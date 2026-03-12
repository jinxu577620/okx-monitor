#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import requests

API_URL = "https://api.tavily.com/search"


def main():
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise SystemExit("缺少 TAVILY_API_KEY")

    query = " ".join(sys.argv[1:]).strip()
    if not query:
        raise SystemExit("用法: python search_tavily.py <query>")

    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "advanced",
        "max_results": 5,
        "include_answer": True,
        "include_raw_content": False,
    }

    resp = requests.post(API_URL, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
