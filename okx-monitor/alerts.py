from __future__ import annotations

from typing import Optional


def near(a: float, b: float, pct: float = 0.003) -> bool:
    if not a or not b:
        return False
    return abs(a - b) / b <= pct


def build_alert(inst_id: str, last: float, plan: dict) -> Optional[str]:
    long_trigger = plan.get("trigger_long")
    short_trigger = plan.get("trigger_short")
    signal = plan.get("signal")

    if long_trigger and last >= long_trigger:
        return (
            f"{inst_id} 触发多头条件\n"
            f"- 现价：{last:.2f}\n"
            f"- 多头触发位：{long_trigger:.2f}\n"
            f"- 当前信号：{signal}\n"
            f"- 建议：若量能继续配合，可等回踩确认后跟进。"
        )

    if short_trigger and last <= short_trigger:
        return (
            f"{inst_id} 触发空头条件\n"
            f"- 现价：{last:.2f}\n"
            f"- 空头触发位：{short_trigger:.2f}\n"
            f"- 当前信号：{signal}\n"
            f"- 建议：若反抽无力，可按破位思路看空。"
        )

    if long_trigger and near(last, long_trigger):
        return (
            f"{inst_id} 接近多头触发位\n"
            f"- 现价：{last:.2f}\n"
            f"- 多头触发位：{long_trigger:.2f}\n"
            f"- 当前信号：{signal}\n"
            f"- 建议：盯量能与假突破。"
        )

    if short_trigger and near(last, short_trigger):
        return (
            f"{inst_id} 接近空头触发位\n"
            f"- 现价：{last:.2f}\n"
            f"- 空头触发位：{short_trigger:.2f}\n"
            f"- 当前信号：{signal}\n"
            f"- 建议：盯反抽强度与破位有效性。"
        )

    return None
