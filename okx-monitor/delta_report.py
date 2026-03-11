from __future__ import annotations

from pathlib import Path
import json

STATE_PATH = Path(__file__).resolve().parent / "state.json"


def load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def rank_changes(symbol_payloads: list[dict]) -> list[dict]:
    ranked = []
    for payload in symbol_payloads:
        inst_id = payload["inst_id"]
        decision = payload["decision"]
        plan_4h = payload["plan_4h"]
        state = payload.get("state", {})
        history = state.get("history", [])
        prev_last = history[-2]["last"] if len(history) >= 2 and history[-2].get("last") else None
        last = payload["ticker"].get("last")
        price_change = None
        if prev_last and last:
            price_change = ((last - prev_last) / prev_last) * 100

        score = abs(decision.get("weighted_score", 0))
        if price_change is not None:
            score += abs(price_change)
        oi_delta = plan_4h.get("oi_delta_pct")
        if oi_delta is not None:
            score += abs(oi_delta) * 0.5

        ranked.append(
            {
                "inst_id": inst_id,
                "score": round(score, 2),
                "price_change_pct": price_change,
                "signal": decision.get("signal"),
                "summary": plan_4h.get("summary"),
                "plan_4h": plan_4h,
            }
        )
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked


def build_delta_report(symbol_payloads: list[dict]) -> str:
    ranked = rank_changes(symbol_payloads)
    focus = ranked[:2]
    avoid = ranked[-1] if ranked else None

    lines = ["加密晨报", "", "今日变化重点"]
    for item in focus:
        pct = item["price_change_pct"]
        pct_text = f"{pct:.2f}%" if pct is not None else "-"
        lines.append(f"- {item['inst_id']}：权重信号={item['signal']}，短时变化={pct_text}，结论：{item['summary']}")

    lines.append("")
    lines.append("今日优先级")
    for idx, item in enumerate(focus, start=1):
        lines.append(f"- 重点关注{idx}：{item['inst_id']}")
    if avoid:
        lines.append(f"- 暂时靠后：{avoid['inst_id']}")

    lines.append("")
    lines.append("操作建议")
    for item in focus:
        plan = item["plan_4h"]
        lines.append(f"- {item['inst_id']} 多：开仓 {plan.get('trigger_long')} / 止盈 {plan.get('tp1_long')}、{plan.get('tp2_long')} / 止损 {plan.get('stop_long')}")
        lines.append(f"- {item['inst_id']} 空：开仓 {plan.get('trigger_short')} / 止盈 {plan.get('tp1_short')}、{plan.get('tp2_short')} / 止损 {plan.get('stop_short')}")

    return "\n".join(lines)
