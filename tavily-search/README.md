# tavily-search

本地 Tavily 搜索小工具。

## 用法
```bash
cd /Users/jinxu/.openclaw/workspace】/tavily-search
python3 -m venv .venv
source .venv/bin/activate
pip install -U -r requirements.txt
source .env
python search_tavily.py "特朗普 最新 表态 市场 影响"
```

## 说明
- `.env` 中保存 Tavily API key
- 输出为 Tavily 原始 JSON 结果
