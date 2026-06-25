from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))

from state_writer import apply_turn
from validators import validate_and_normalize


def _employee(emp_id: str, **overrides) -> dict:
    employee = {
        "id": emp_id,
        "activity_type": "planning",
        "intensity": "normal",
        "actions": [
            {"duration_hours": 1.5},
            {"duration_hours": 1},
            {"duration_hours": 0.5},
            {"duration_hours": 1},
        ],
        "hours_used": 0,
        "effects": {"fatigue_delta": 0, "motivation_delta": 0},
    }
    employee.update(overrides)
    return employee


def _ai(employee: dict) -> dict:
    return {
        "employees": [
            employee,
            _employee("002", status_change={"fatigue_delta": 0, "motivation_delta": 0}),
            _employee("003", status_change={"fatigue_delta": 0, "motivation_delta": 0}),
        ],
        "events": [],
        "company_effects": {},
    }


def _state() -> dict:
    return {
        "company": {
            "launch_date": "2026-06-30",
            "company_cash": 0,
            "preparation_fund": 0,
            "monthly_sales": 0,
            "monthly_expense": 0,
            "reputation": 50,
            "legal_name": "未定",
            "legal_form": "未定",
        },
        "employees": [
            {"id": "001", "name": "佐藤 直樹", "age": 38, "fatigue": 10, "motivation": 75, "cash_on_hand": 0, "bank_balance": 0, "contribution_total": 0},
            {"id": "002", "name": "高橋 美咲", "age": 32, "fatigue": 8, "motivation": 72, "cash_on_hand": 0, "bank_balance": 0, "contribution_total": 0},
            {"id": "003", "name": "田中 蓮", "age": 29, "fatigue": 12, "motivation": 78, "cash_on_hand": 0, "bank_balance": 0, "contribution_total": 0},
        ],
    }


def test_status_change_delta_and_hours_are_applied():
    ai = validate_and_normalize(_ai(_employee("001", status_change={"fatigue_delta": -2, "motivation_delta": 1})))
    emp = ai["employees"][0]
    assert emp["effects"]["fatigue_delta"] == -2
    assert emp["effects"]["motivation_delta"] == 1
    assert emp["hours_used"] == 4.0

    updated = apply_turn(_state(), ai, datetime(2026, 6, 25, tzinfo=timezone.utc))
    updated_emp = next(e for e in updated["employees"] if e["id"] == "001")
    assert updated_emp["fatigue"] == 8
    assert updated_emp["motivation"] == 76


def test_status_change_legacy_keys_are_applied():
    ai = validate_and_normalize(_ai(_employee("001", status_change={"fatigue": -2, "motivation": 1})))
    emp = ai["employees"][0]
    assert emp["effects"]["fatigue_delta"] == -2
    assert emp["effects"]["motivation_delta"] == 1


def test_nonzero_effects_take_priority_and_hours_are_clamped():
    ai = validate_and_normalize(_ai(_employee("001", hours_used=0, effects={"fatigue_delta": 3, "motivation_delta": -1}, status_change={"fatigue_delta": -2, "motivation_delta": 1}, actions=[{"duration_hours": 3}, {"duration_hours": 3}])))
    emp = ai["employees"][0]
    assert emp["effects"]["fatigue_delta"] == 3
    assert emp["effects"]["motivation_delta"] == -1
    assert emp["hours_used"] == 4.0
