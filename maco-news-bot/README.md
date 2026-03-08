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

## 推送格式
默认开启**汇总模式**（避免刷屏）：
- 一条消息内汇总多条新闻
- 按标签分组：A股 / 美股 / 黄金 / 原油 / 加密 / 汇率债券 / 综合
- 每组展示最多 3 条
- 结尾附“重点解读”

如果关闭汇总模式，也支持逐条推送：
- 标签
- 来源
- 中文标题
- 中文摘要
- 影响资产
- 影响方向
- 一句话解读
- 原文链接

## 可选项
- `MAX_ITEMS=8`：每次最多推送条数
- `TRANSLATE_TO_ZH=1`：是否翻译为中文（默认开启）
- `REQUEST_TIMEOUT=20`：Telegram 请求超时秒数
- `DIGEST_MODE=1`：是否启用汇总模式（默认开启）
- `DIGEST_TITLE="宏观新闻汇总"`：汇总消息标题
