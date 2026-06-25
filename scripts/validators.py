from __future__ import annotations

import json
from scripts.utils import clamp

ACTIVITY_TYPES = {"work_deep", "work_light", "sales", "customer_support", "meeting", "learning", "planning", "rest", "personal", "sleep"}
INTENSITIES = {"none", "light", "normal", "high"}
REQUIRED_TOP_LEVEL = {"turn", "employees", "company_effects", "events", "important_event", "next_company_focus"}
REQUIRED_TURN = {"datetime", "turn_length_hours", "simulation_phase", "days_until_launch", "summary"}
REQUIRED_EMPLOYEE = {"id", "activity_type", "worked", "intensity", "hours_used", "title", "reason", "result", "effects", "skill_deltas", "next_hint"}
EFFECT_KEYS = ["fatigue_delta", "motivation_delta", "cash_delta", "bank_balance_delta", "company_cash_delta", "company_preparation_fund_delta", "reputation_delta", "project_progress_delta"]
COMPANY_EFFECT_KEYS = ["company_cash_delta", "preparation_fund_delta", "monthly_sales_delta", "monthly_expense_delta", "reputation_delta", "lead_delta", "project_delta"]


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json").strip()
    return json.loads(text)


def _require_keys(obj: dict, required: set[str], label: str) -> None:
    missing = sorted(required - set(obj))
    if missing:
        raise ValueError(f"{label} missing required keys: {', '.join(missing)}")


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def validate_and_normalize(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("AI output must be a JSON object")
    _require_keys(data, REQUIRED_TOP_LEVEL, "AI output")
    if not isinstance(data["turn"], dict):
        raise ValueError("turn must be an object")
    _require_keys(data["turn"], REQUIRED_TURN, "turn")
    if data["turn"].get("simulation_phase") not in {"pre_launch", "launch_day", "post_launch"}:
        raise ValueError("turn.simulation_phase is invalid")
    data["turn"]["turn_length_hours"] = min(4, max(0, _as_int(data["turn"].get("turn_length_hours"), 4)))
    data["turn"]["days_until_launch"] = _as_int(data["turn"].get("days_until_launch"), 0)

    if not isinstance(data["employees"], list) or len(data["employees"]) != 3:
        raise ValueError("AI output must include exactly 3 employees")
    seen_ids: set[str] = set()
    for emp in data["employees"]:
        if not isinstance(emp, dict):
            raise ValueError("employee entries must be objects")
        _require_keys(emp, REQUIRED_EMPLOYEE, "employee")
        emp_id = emp.get("id")
        if emp_id not in {"001", "002", "003"}:
            raise ValueError("Unknown employee id")
        if emp_id in seen_ids:
            raise ValueError("Duplicate employee id")
        seen_ids.add(emp_id)
        if emp.get("activity_type") not in ACTIVITY_TYPES:
            emp["activity_type"] = "planning"
        if emp.get("intensity") not in INTENSITIES:
            emp["intensity"] = "normal"
        emp["worked"] = bool(emp.get("worked"))
        emp["hours_used"] = min(4.0, max(0.0, float(emp.get("hours_used", 0))))
        if not isinstance(emp["effects"], dict):
            raise ValueError("employee.effects must be an object")
        for key in EFFECT_KEYS:
            if key in {"fatigue_delta", "motivation_delta", "reputation_delta", "project_progress_delta"}:
                emp["effects"][key] = clamp(_as_int(emp["effects"].get(key), 0), -100, 100)
            else:
                emp["effects"][key] = _as_int(emp["effects"].get(key), 0)
        if not isinstance(emp["skill_deltas"], dict):
            raise ValueError("employee.skill_deltas must be an object")
        for key, value in list(emp["skill_deltas"].items()):
            emp["skill_deltas"][key] = clamp(_as_int(value), -100, 100)

    if not isinstance(data["company_effects"], dict):
        raise ValueError("company_effects must be an object")
    for key in COMPANY_EFFECT_KEYS:
        if key == "reputation_delta":
            data["company_effects"][key] = clamp(_as_int(data["company_effects"].get(key), 0), -100, 100)
        else:
            data["company_effects"][key] = _as_int(data["company_effects"].get(key), 0)
    if not isinstance(data["events"], list):
        raise ValueError("events must be a list")
    return data
