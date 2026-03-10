from __future__ import annotations


def fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def build_symbol_report(inst_id: str, ticker: dict, trend_4h: dict, trend_1d: dict, plan_4h: dict):
    lines = [
        f"{inst_id}",
        f"- 现价：{fmt(ticker.get('last'))}",
        f"- 4H：{trend_4h.get('bias')} | MA20={fmt(trend_4h.get('ma20'))} | MA60={fmt(trend_4h.get('ma60'))}",
        f"- 1D：{trend_1d.get('bias')} | MA20={fmt(trend_1d.get('ma20'))} | MA60={fmt(trend_1d.get('ma60'))}",
        f"- 4H 多头触发：{fmt(plan_4h.get('trigger_long'))}",
        f"- 4H 空头触发：{fmt(plan_4h.get('trigger_short'))}",
        f"- 多头止损参考：{fmt(plan_4h.get('stop_long'))}",
        f"- 空头止损参考：{fmt(plan_4h.get('stop_short'))}",
    ]
    return "\n".join(lines)


def build_report(items: list[str]):
    header = "OKX 行情策略简报\n"
    return header + "\n\n".join(items)
