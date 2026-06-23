from __future__ import annotations

import json
from utils import clamp

ACTIVITY_TYPES = {"work_deep", "work_light", "sales", "customer_support", "meeting", "learning", "planning", "rest", "personal", "sleep"}
INTENSITIES = {"none", "light", "normal", "high"}


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.removeprefix("json").strip()
    return json.loads(text)


def validate_and_normalize(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("AI output must be a JSON object")
    data.setdefault("employees", [])
    data.setdefault("events", [])
    data.setdefault("company_effects", {})
    if len(data["employees"]) != 3:
        raise ValueError("AI output must include exactly 3 employees")
    for emp in data["employees"]:
        if emp.get("id") not in {"001", "002", "003"}:
            raise ValueError("Unknown employee id")
        if emp.get("activity_type") not in ACTIVITY_TYPES:
            emp["activity_type"] = "planning"
        if emp.get("intensity") not in INTENSITIES:
            emp["intensity"] = "normal"
        emp["hours_used"] = min(4.0, max(0.0, float(emp.get("hours_used", 0))))
        effects = emp.setdefault("effects", {})
        for key in ["fatigue_delta", "motivation_delta", "cash_delta", "bank_balance_delta", "company_cash_delta", "company_preparation_fund_delta", "reputation_delta", "project_progress_delta"]:
            effects[key] = clamp(effects.get(key, 0), -100, 100) if "cash" not in key and "fund" not in key and "bank" not in key else int(effects.get(key, 0))
        emp.setdefault("skill_deltas", {})
    ce = data["company_effects"]
    for key in ["company_cash_delta", "preparation_fund_delta", "monthly_sales_delta", "monthly_expense_delta", "reputation_delta", "lead_delta", "project_delta"]:
        ce[key] = int(ce.get(key, 0))
    return data
