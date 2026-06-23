from __future__ import annotations

import re
from pathlib import Path
from scripts.utils import ROOT, read, yen_to_int

EMPLOYEE_FILES = {
    "001": ROOT / "data/employees/001_ceo.md",
    "002": ROOT / "data/employees/002_ai_flow_designer.md",
    "003": ROOT / "data/employees/003_automation_engineer.md",
}


def bullet(content: str, label: str, default: str = "") -> str:
    m = re.search(rf"^- {re.escape(label)}：(.+)$", content, re.MULTILINE)
    return m.group(1).strip() if m else default


def load_employee(emp_id: str) -> dict:
    content = read(EMPLOYEE_FILES[emp_id])
    return {
        "id": emp_id,
        "name": bullet(content, "氏名"),
        "age": int(bullet(content, "年齢", "0歳").replace("歳", "")),
        "role": bullet(content, "役割"),
        "status": bullet(content, "状態", "通常"),
        "fatigue": int(bullet(content, "疲労", "0")),
        "motivation": int(bullet(content, "モチベーション", "0")),
        "cash_on_hand": yen_to_int(f"{bullet(content, '所持金', '0円')}", 0),
        "bank_balance": yen_to_int(f"{bullet(content, '預金額', '0円')}", 0),
        "contribution_total": yen_to_int(f"{bullet(content, '会社への拠出累計', '0円')}", 0),
        "salary_total": yen_to_int(f"{bullet(content, '会社からの給与累計', '0円')}", 0),
    }


def load_company() -> dict:
    content = read(ROOT / "data/company.md")
    return {
        "company_name": bullet(content, "会社名", "ファントム"),
        "legal_name": bullet(content, "正式名称", "未定"),
        "legal_form": bullet(content, "法人形態", "未定"),
        "representative": bullet(content, "代表者", "佐藤 直樹"),
        "phase": bullet(content, "フェーズ", "起業前"),
        "launch_date": bullet(content, "起業予定日", "2026-06-30"),
        "company_cash": yen_to_int(bullet(content, "会社資金", "0円")),
        "preparation_fund": yen_to_int(bullet(content, "起業準備金", "0円")),
        "monthly_sales": yen_to_int(bullet(content, "今月売上", "0円")),
        "monthly_expense": yen_to_int(bullet(content, "今月費用", "0円")),
        "reputation": int(bullet(content, "評判", "50")),
    }


def load_state() -> dict:
    return {
        "company": load_company(),
        "employees": [load_employee(i) for i in EMPLOYEE_FILES],
        "current_state_md": read(ROOT / "data/current_state.md"),
    }
