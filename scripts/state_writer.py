from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from state_loader import EMPLOYEE_FILES
from utils import ROOT, JST, clamp, int_to_yen, read, replace_bullet, write
from dashboard_writer import write_dashboard


def phase_info(company: dict, now) -> tuple[str, int]:
    launch = datetime.fromisoformat(company["launch_date"]).date()
    days = (launch - now.date()).days
    if days > 0:
        return "起業前", days
    if days == 0:
        return "起業日", 0
    return "起業後", abs(days)


def launch_days_text(phase: str, days: int) -> str:
    if phase == "起業後":
        return f"起業後{days}日"
    if phase == "起業日":
        return "起業日"
    return f"{days}日"


def action_description(action: dict) -> str:
    actions = action.get("actions")
    if isinstance(actions, list) and actions:
        parts = []
        for item in actions:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            details = str(item.get("details") or item.get("description") or item.get("outcome") or "").strip()
            text = "：".join(part for part in [name, details] if part)
            if text:
                parts.append(text)
        if parts:
            return " / ".join(parts)
    return str(action.get("title") or action.get("description") or action.get("name") or "")


def apply_legal_decision(company: dict, ai: dict) -> None:
    candidates = []
    important = ai.get("important_event")
    if isinstance(important, dict):
        candidates.append(important)
    candidates.extend(event for event in ai.get("events", []) if isinstance(event, dict))

    for event in candidates:
        decision = event.get("decision") if isinstance(event.get("decision"), dict) else {}
        text = " ".join(str(event.get(key, "")) for key in ("type", "title", "summary", "details", "reason"))
        legal_name = decision.get("legal_name")
        legal_form = decision.get("legal_form")
        if not legal_name and "合同会社ファントム" in text:
            legal_name = "合同会社ファントム"
        if not legal_form and ("合同会社" in text or (isinstance(legal_name, str) and legal_name.startswith("合同会社"))):
            legal_form = "合同会社"
        if legal_name:
            company["legal_name"] = legal_name
        if legal_form:
            company["legal_form"] = legal_form


def apply_turn(state: dict, ai: dict, now) -> dict:
    company = dict(state["company"])
    employees = {e["id"]: dict(e) for e in state["employees"]}
    phase, days = phase_info(company, now)

    ce = ai.get("company_effects", {})
    company["company_cash"] = max(0, company["company_cash"] + ce.get("company_cash_delta", 0))
    company["preparation_fund"] = max(0, company["preparation_fund"] + ce.get("preparation_fund_delta", 0))
    if phase == "起業前" and ce.get("monthly_sales_delta", 0) > 0:
        ce["monthly_sales_delta"] = 0
    company["monthly_sales"] = max(0, company["monthly_sales"] + ce.get("monthly_sales_delta", 0))
    company["monthly_expense"] = max(0, company["monthly_expense"] + ce.get("monthly_expense_delta", 0))
    company["reputation"] = clamp(company["reputation"] + ce.get("reputation_delta", 0), 0, 100)

    for action in ai.get("employees", []):
        emp = employees[action["id"]]
        effects = action.get("effects", {})
        fatigue_delta = effects.get("fatigue_delta", 0)
        if action.get("activity_type") in {"rest", "sleep"}:
            fatigue_delta = min(fatigue_delta, -3)
        if action.get("intensity") == "high":
            fatigue_delta = max(fatigue_delta, 6)
        emp["fatigue"] = clamp(emp["fatigue"] + fatigue_delta, 0, 100)
        emp["motivation"] = clamp(emp["motivation"] + effects.get("motivation_delta", 0), 0, 100)
        emp["cash_on_hand"] = max(0, emp["cash_on_hand"] + effects.get("cash_delta", 0))
        emp["bank_balance"] = max(0, emp["bank_balance"] + effects.get("bank_balance_delta", 0))
        emp["last_action"] = action_description(action)
        emp["current_task"] = action.get("next_hint", "")

    apply_legal_decision(company, ai)

    for event in ai.get("events", []):
        if event.get("type") == "legal_form_decision":
            decision = event.get("decision", {})
            if decision.get("decision_maker") == "佐藤 直樹":
                company["legal_name"] = decision.get("legal_name", company["legal_name"])
                company["legal_form"] = decision.get("legal_form", company["legal_form"])
        if event.get("type") == "personal_fund_to_company":
            transfer = event.get("money_transfer", {})
            emp_id = str(transfer.get("from", "")).replace("employee:", "")
            amount = max(0, int(transfer.get("amount", 0)))
            if emp_id in employees and amount:
                source = transfer.get("source", "預金")
                emp = employees[emp_id]
                if source == "所持金":
                    moved = min(amount, emp["cash_on_hand"])
                    emp["cash_on_hand"] -= moved
                else:
                    moved = min(amount, emp["bank_balance"])
                    emp["bank_balance"] -= moved
                emp["contribution_total"] += moved
                company["preparation_fund"] += moved

    company["phase"] = phase
    company["days_until_launch"] = days
    return {"company": company, "employees": list(employees.values()), "ai": ai}


def write_state(updated: dict, now) -> Path:
    company = updated["company"]
    phase = company["phase"]
    days = company["days_until_launch"]
    cpath = ROOT / "data/company.md"
    content = read(cpath)
    for label, value in [
        ("正式名称", company["legal_name"]), ("法人形態", company["legal_form"]), ("フェーズ", phase),
        ("現在日", now.strftime("%Y-%m-%d")), ("起業日まで", launch_days_text(phase, days)), ("会社資金", int_to_yen(company["company_cash"])),
        ("起業準備金", int_to_yen(company["preparation_fund"])), ("今月売上", int_to_yen(company["monthly_sales"])),
        ("今月費用", int_to_yen(company["monthly_expense"])), ("評判", str(company["reputation"])),
    ]:
        content = replace_bullet(content, label, value)
    write(cpath, content)

    for emp in updated["employees"]:
        econtent = read(EMPLOYEE_FILES[emp["id"]])
        for label, value in [("疲労", str(emp["fatigue"])), ("モチベーション", str(emp["motivation"])), ("所持金", int_to_yen(emp["cash_on_hand"])), ("預金額", int_to_yen(emp["bank_balance"])), ("会社への拠出累計", int_to_yen(emp["contribution_total"])), ("前回の行動", emp.get("last_action", "なし")), ("現在のタスク", emp.get("current_task", "なし"))]:
            econtent = replace_bullet(econtent, label, value)
        write(EMPLOYEE_FILES[emp["id"]], econtent)

    current = render_current_state(updated, now)
    write(ROOT / "data/current_state.md", current)
    log_path = write_log(updated, now, current)
    append_events(updated, now)
    write_dashboard(updated, now, log_path)
    return log_path


def render_current_state(updated: dict, now) -> str:
    c = updated["company"]
    lines = ["# 現在状態", "", "## 現在日時", "", f"- 現在日時：{now:%Y-%m-%d %H:%M} JST", f"- フェーズ：{c['phase']}", f"- 起業日まで：{launch_days_text(c['phase'], c['days_until_launch'])}", "", "## 会社基本情報", "", f"- 会社名：ファントム", f"- 正式名称：{c['legal_name']}", f"- 法人形態：{c['legal_form']}", f"- 評判：{c['reputation']}", "", "## 会社資金", "", f"- 会社資金：{int_to_yen(c['company_cash'])}", f"- 起業準備金：{int_to_yen(c['preparation_fund'])}", f"- 今月売上：{int_to_yen(c['monthly_sales'])}", f"- 今月費用：{int_to_yen(c['monthly_expense'])}", "", "## 案件状況", "", "- 進行中案件：data/projects.mdを参照", "- 緊急課題：法人形態、営業準備、初期サービス設計", "", "## 社員状態", ""]
    for e in updated["employees"]:
        lines.append(f"- {e['id']} {e['name']}：{e['age']}歳 / 疲労{e['fatigue']} / 意欲{e['motivation']} / 所持金{int_to_yen(e['cash_on_hand'])} / 預金{int_to_yen(e['bank_balance'])}")
    lines += ["", "## 直近の流れ", "", f"- {updated['ai'].get('turn', {}).get('summary', 'AIターンを実行')}", "", "## 次の注力事項", "", f"- {updated['ai'].get('next_company_focus', '次回ターンで起業準備を継続する')}"]
    return "\n".join(lines) + "\n"


def write_log(updated: dict, now, current: str) -> Path:
    path = ROOT / f"logs/{now:%Y-%m-%d}/{now:%H%M}.md"
    ai = updated["ai"]
    body = [f"# シミュレーションログ {now:%Y-%m-%d %H:%M} JST", "", "## AIの行動判断", "", "```json", json.dumps(ai, ensure_ascii=False, indent=2), "```", "", "## 更新後の会社状態", "", f"- フェーズ：{updated['company']['phase']}", f"- 正式名称：{updated['company']['legal_name']}", f"- 法人形態：{updated['company']['legal_form']}", f"- 会社資金：{int_to_yen(updated['company']['company_cash'])}", f"- 起業準備金：{int_to_yen(updated['company']['preparation_fund'])}", "", "## 更新後の社員状態", ""]
    for e in updated["employees"]:
        body.append(f"- {e['id']} {e['name']}：疲労{e['fatigue']} / 意欲{e['motivation']} / 所持金{int_to_yen(e['cash_on_hand'])} / 預金{int_to_yen(e['bank_balance'])}")
    body += ["", "## 入力に使ったcurrent_stateの要約", "", current[:1200]]
    write(path, "\n".join(body) + "\n")
    return path


def append_events(updated: dict, now) -> None:
    events = updated["ai"].get("events", [])
    if not events:
        return
    path = ROOT / "data/events.md"
    content = read(path)
    for event in events:
        content += f"\n- {now:%Y-%m-%d %H:%M}：{event.get('title', event.get('type', 'event'))} - {event.get('details', '')}"
    write(path, content + "\n")
