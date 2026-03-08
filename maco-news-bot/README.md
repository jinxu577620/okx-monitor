# maco-news-bot

自动抓取宏观新闻，并以中文摘要 + 市场影响判断推送到 Telegram。

## 文件
- `news_push_cn.py`：主脚本
- `feeds.json`：新闻源配置（可自行增删）
- `requirements.txt`：依赖
- `news_state.json`：已发送去重状态（运行后自动生成）

## 当前内置新闻源
- Reuters World
- Reuters Business
- WSJ Markets
- 华尔街见闻热门（RSSHub）
- 财新最新（RSSHub）

> 说明：部分 RSSHub 源偶尔可能抽风，脚本不会因此中断；你后面可以直接编辑 `feeds.json` 替换源。

## 安装
```bash
cd /Users/jinxu/.openclaw/workspace】/maco-news-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip -r requirements.txt
```

## 环境变量
你现在已经可以直接用项目里的 `.env`：
```bash
source .env
```

如果要手动覆盖，也可以：
```bash
export TG_BOT_TOKEN="你的_bot_token"
export TG_CHAT_ID="你的_chat_id"
```

## 手动测试
```bash
cd /Users/jinxu/.openclaw/workspace】/maco-news-bot
source .venv/bin/activate
source .env
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

## 推送格式
默认采用 **B2 模式**：
- 先抓多条英文新闻
- 先在本地生成一条英文汇总
- 最后只对这条汇总做一次中文翻译
- 再发送到 Telegram

这样可以显著减少翻译请求次数，提升稳定性。

## 可选项
- `MAX_ITEMS=8`：每次最多推送条数
- `FINAL_TRANSLATE_TO_ZH=1`：是否只翻译最终汇总（默认开启）
- `SUMMARY_MAX_CHARS=90`：单条摘要截断长度
- `REQUEST_TIMEOUT=20`：Telegram 请求超时秒数
- `DIGEST_TITLE="宏观新闻汇总"`：汇总消息标题
