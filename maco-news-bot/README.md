# maco-news-bot

自动抓取宏观新闻，并以中文摘要推送到 Telegram。

## 文件
- `news_push_cn.py`：主脚本
- `requirements.txt`：依赖
- `news_state.json`：已发送去重状态（运行后自动生成）

## 安装
```bash
cd /Users/jinxu/.openclaw/workspace】/maco-news-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip -r requirements.txt
```

## 环境变量
```bash
export TG_BOT_TOKEN="你的_bot_token"
export TG_CHAT_ID="你的_chat_id"
```

## 手动测试
```bash
cd /Users/jinxu/.openclaw/workspace】/maco-news-bot
source .venv/bin/activate
python news_push_cn.py
```

## 定时运行（每15分钟）
```bash
crontab -e
```
加入：
```cron
*/15 * * * * cd /Users/jinxu/.openclaw/workspace】/maco-news-bot && TG_BOT_TOKEN="你的_bot_token" TG_CHAT_ID="你的_chat_id" /Users/jinxu/.openclaw/workspace】/maco-news-bot/.venv/bin/python news_push_cn.py >> /Users/jinxu/.openclaw/workspace】/maco-news-bot/news.log 2>&1
```

## 可选项
- `MAX_ITEMS=8`：每次最多推送条数
- `TRANSLATE_TO_ZH=1`：是否翻译为中文（默认开启）
