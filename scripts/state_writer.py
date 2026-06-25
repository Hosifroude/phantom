from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from scripts.state_loader import EMPLOYEE_FILES
from scripts.utils import ROOT, clamp, int_to_yen, read, replace_bullet, write


def phase_info(company: dict, now) -> tuple[str, int]:
    launch = datetime.fromisoformat(company["launch_date"]).date()
    days = (launch - now.date()).days
    if days > 0:
        return "起業前", days
    if days == 0:
        return "起業日", 0
    return "起業後", days


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
        company["company_cash"] = max(0, company["company_cash"] + effects.get("company_cash_delta", 0))
        company["preparation_fund"] = max(0, company["preparation_fund"] + effects.get("company_preparation_fund_delta", 0))
        company["reputation"] = clamp(company["reputation"] + effects.get("reputation_delta", 0), 0, 100)
        emp["last_action"] = action.get("title", "")
        emp["current_task"] = action.get("next_hint", "")

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
        ("現在日", now.strftime("%Y-%m-%d")), ("起業日まで", f"{days}日"), ("会社資金", int_to_yen(company["company_cash"])),
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
    return log_path


def render_current_state(updated: dict, now) -> str:
    c = updated["company"]
    lines = ["# 現在状態", "", "## 現在日時", "", f"- 現在日時：{now:%Y-%m-%d %H:%M} JST", f"- フェーズ：{c['phase']}", f"- 起業日まで：{c['days_until_launch']}日", "", "## 会社基本情報", "", f"- 会社名：ファントム", f"- 正式名称：{c['legal_name']}", f"- 法人形態：{c['legal_form']}", f"- 評判：{c['reputation']}", "", "## 会社資金", "", f"- 会社資金：{int_to_yen(c['company_cash'])}", f"- 起業準備金：{int_to_yen(c['preparation_fund'])}", f"- 今月売上：{int_to_yen(c['monthly_sales'])}", f"- 今月費用：{int_to_yen(c['monthly_expense'])}", "", "## 案件状況", "", "- 進行中案件：data/projects.mdを参照", "- 緊急課題：法人形態、営業準備、初期サービス設計", "", "## 社員状態", ""]
    for e in updated["employees"]:
        lines.append(f"- {e['id']} {e['name']}：{e['age']}歳 / 疲労{e['fatigue']} / 意欲{e['motivation']} / 所持金{int_to_yen(e['cash_on_hand'])} / 預金{int_to_yen(e['bank_balance'])}")
    lines += ["", "## 直近の流れ", "", f"- {updated['ai'].get('turn', {}).get('summary', 'AIターンを実行')}", "", "## 次の注力事項", "", f"- {updated['ai'].get('next_company_focus', '次回ターンで起業準備を継続する')}"]
    return "\n".join(lines) + "\n"


def write_log(updated: dict, now, current: str) -> Path:
    path = ROOT / f"logs/{now:%Y-%m-%d}/{now:%H%M}.md"
    ai = updated["ai"]
    body = [
        f"# シミュレーションログ {now:%Y-%m-%d %H:%M} JST",
        "",
        "## 実行日時",
        "",
        f"- {now:%Y-%m-%d %H:%M} JST",
        "",
        "## 入力に使ったcurrent_stateの要約",
        "",
        current[:1200],
        "",
        "## AI出力",
        "",
        "```json",
        json.dumps(ai, ensure_ascii=False, indent=2),
        "```",
        "",
        "## 社員ごとの行動",
        "",
    ]
    for action in ai.get("employees", []):
        body.append(
            f"- {action.get('id')}：{action.get('title', '')} / {action.get('activity_type', '')} / "
            f"{action.get('hours_used', 0)}時間 / 結果：{action.get('result', '')}"
        )
    body += [
        "",
        "## 会社への影響・会社資金への影響",
        "",
        "```json",
        json.dumps(ai.get("company_effects", {}), ensure_ascii=False, indent=2),
        "```",
        "",
        "## 社員個人資金への影響",
        "",
    ]
    for action in ai.get("employees", []):
        effects = action.get("effects", {})
        body.append(
            f"- {action.get('id')}：所持金差分 {int_to_yen(effects.get('cash_delta', 0))} / "
            f"預金差分 {int_to_yen(effects.get('bank_balance_delta', 0))}"
        )
    body += ["", "## イベント・法人形態に関する判断", ""]
    if ai.get("events"):
        for event in ai.get("events", []):
            body.append(f"- {event.get('type', '')}：{event.get('title', '')} - {event.get('details', '')}")
    else:
        body.append("- なし")
    body += [
        "",
        "## 更新後の会社状態",
        "",
        f"- フェーズ：{updated['company']['phase']}",
        f"- 正式名称：{updated['company']['legal_name']}",
        f"- 法人形態：{updated['company']['legal_form']}",
        f"- 会社資金：{int_to_yen(updated['company']['company_cash'])}",
        f"- 起業準備金：{int_to_yen(updated['company']['preparation_fund'])}",
        "",
        "## 更新後の社員状態",
        "",
    ]
    for e in updated["employees"]:
        body.append(f"- {e['id']} {e['name']}：疲労{e['fatigue']} / 意欲{e['motivation']} / 所持金{int_to_yen(e['cash_on_hand'])} / 預金{int_to_yen(e['bank_balance'])}")
    body += ["", "## エラー内容", "", "- なし"]
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
