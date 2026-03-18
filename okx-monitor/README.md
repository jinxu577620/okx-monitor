# okx-monitor

用于接入 OKX V5 公共行情，生成加密货币 4H / 1D 级别的监控与策略建议。

## V1 目标
- 接入 OKX 公共 REST / WebSocket（先不使用私钥）
- 关注 BTC / ETH（后续可扩展）
- 获取 4H / 1D K 线
- 生成中文策略摘要：趋势、支撑/压力、多空触发位、风险提示
- 后续可接 Telegram 推送

## 目录
- `config.py`：配置项
- `okx_public.py`：OKX 公共 REST 客户端
- `strategy.py`：指标与策略判断
- `report.py`：中文简报生成
- `main.py`：主入口
- `requirements.txt`：依赖

## 当前阶段
当前仅做公共行情监控，不接账户、不下单。
后续顺序建议：
1. 公共行情监控
2. 只读账户监控
3. 模拟盘
4. 小仓位实盘

## 现在可直接使用的脚本
- `python3 live_card.py`：输出实时策略卡片
- `python3 push_live_card.py`：把实时策略卡片推送到 Telegram
- `python3 check_alerts.py`：检查是否接近/触发关键位
- `python3 push_alerts.py`：只有出现关键信号时才推送到 Telegram

## 自动推送
当前提供两种 `launchd` 方案：

### 1）整卡定时推送
- 配置文件：`com.jinxu.okx-monitor.live.plist`
- 安装脚本：`install_launchd.sh`
- 默认频率：每 1 小时推送一次

### 2）有信号才推送（推荐）
- 配置文件：`com.jinxu.okx-monitor.alerts.plist`
- 安装脚本：`install_alerts_launchd.sh`
- 默认检查频率：每 15 分钟检查一次
- 实际推送规则：**只有接近/触发关键位才发送**，并带重复去重

默认复用：`/Users/jinxu/.openclaw/workspace】/maco-news-bot/.env` 中的 `TG_BOT_TOKEN` 与 `TG_CHAT_ID`

安装有信号才推：
```bash
cd /Users/jinxu/.openclaw/workspace】/okx-monitor
chmod +x install_alerts_launchd.sh
./install_alerts_launchd.sh
```
