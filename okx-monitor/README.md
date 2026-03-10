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
