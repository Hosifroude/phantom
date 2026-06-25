from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from state_loader import EMPLOYEE_FILES
from utils import ROOT, int_to_yen, read, write


def _bullet(content: str, label: str, default: str = "") -> str:
    match = re.search(rf"^- {re.escape(label)}：(.+)$", content, re.MULTILINE)
    return match.group(1).strip() if match else default


def _latest_log_path() -> Path | None:
    files = sorted((ROOT / "logs").glob("*/*.md"))
    return files[-1] if files else None


def _action_lines(ai: dict[str, Any], limit: int = 5) -> list[str]:
    lines: list[str] = []
    for employee in ai.get("employees", []):
        name = employee.get("name") or employee.get("employee_name") or employee.get("id", "社員")
        actions = employee.get("actions") or [employee]
        action_texts = []
        for action in actions:
            text = action.get("outcome") or action.get("description") or action.get("title")
            if text:
                action_texts.append(text)
        if action_texts:
            lines.append(f"{name}：{action_texts[0]}")
    if not lines:
        summary = ai.get("turn", {}).get("summary")
        if summary and summary != "AIターンを実行":
            lines.append(summary)
    focus = ai.get("next_company_focus")
    if focus and len(lines) < 3:
        lines.append(f"次の注力：{focus}")
    return lines[:limit] or ["最新ログから具体的な行動要約を取得できませんでした"]


def _load_ai_from_log(log_path: Path | None) -> dict[str, Any]:
    if not log_path:
        return {}
    text = read(log_path)
    match = re.search(r"```json\n(.*?)\n```", text, re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(1))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _employee_details(updated: dict[str, Any] | None) -> list[dict[str, Any]]:
    if updated and updated.get("employees"):
        by_id = {e["id"]: dict(e) for e in updated["employees"]}
    else:
        by_id = {}
    details = []
    for emp_id, path in EMPLOYEE_FILES.items():
        content = read(path)
        emp = by_id.get(emp_id, {})
        details.append({
            "id": emp_id,
            "name": emp.get("name") or _bullet(content, "氏名"),
            "age": emp.get("age") or _bullet(content, "年齢", "0歳").replace("歳", ""),
            "role": emp.get("role") or _bullet(content, "役割"),
            "fatigue": int(emp.get("fatigue", _bullet(content, "疲労", "0")) or 0),
            "motivation": int(emp.get("motivation", _bullet(content, "モチベーション", "0")) or 0),
            "cash_on_hand": emp.get("cash_on_hand"),
            "cash_text": int_to_yen(emp["cash_on_hand"]) if "cash_on_hand" in emp else _bullet(content, "所持金", "0円"),
            "bank_text": int_to_yen(emp["bank_balance"]) if "bank_balance" in emp else _bullet(content, "預金額", "0円"),
            "last_action": emp.get("last_action") or _bullet(content, "前回の行動", "なし"),
            "current_task": emp.get("current_task") or _bullet(content, "現在のタスク", "なし"),
            "path": path.relative_to(ROOT).as_posix(),
        })
    return details


def _company_details(updated: dict[str, Any] | None) -> dict[str, Any]:
    content = read(ROOT / "data/company.md")
    c = dict(updated.get("company", {})) if updated else {}
    return {
        "company_name": c.get("company_name") or _bullet(content, "会社名", "ファントム"),
        "legal_name": c.get("legal_name") or _bullet(content, "正式名称", "未定"),
        "legal_form": c.get("legal_form") or _bullet(content, "法人形態", "未定"),
        "phase": c.get("phase") or _bullet(content, "フェーズ", "起業前"),
        "days_until_launch": c.get("days_until_launch") if "days_until_launch" in c else _bullet(content, "起業日まで", ""),
        "company_cash": int_to_yen(c["company_cash"]) if "company_cash" in c else _bullet(content, "会社資金", "0円"),
        "preparation_fund": int_to_yen(c["preparation_fund"]) if "preparation_fund" in c else _bullet(content, "起業準備金", "0円"),
        "monthly_sales": int_to_yen(c["monthly_sales"]) if "monthly_sales" in c else _bullet(content, "今月売上", "0円"),
        "monthly_expense": int_to_yen(c["monthly_expense"]) if "monthly_expense" in c else _bullet(content, "今月費用", "0円"),
        "reputation": c.get("reputation") if "reputation" in c else _bullet(content, "評判", "0"),
    }


def _days_text(value: Any) -> str:
    return f"{value}日" if isinstance(value, int) else str(value)


def write_dashboard(updated: dict[str, Any] | None = None, now: datetime | None = None, log_path: Path | None = None) -> None:
    now = now or datetime.now()
    log_path = log_path or _latest_log_path()
    ai = dict(updated.get("ai", {})) if updated and updated.get("ai") else _load_ai_from_log(log_path)
    company = _company_details(updated)
    employees = _employee_details(updated)
    summary = _action_lines(ai)
    focus_value = ai.get("next_company_focus") or _bullet(read(ROOT / "data/current_state.md"), "次の注力事項", "起業準備を継続する")
    focus_items = focus_value if isinstance(focus_value, list) else [str(focus_value)]
    focus = " / ".join(str(item) for item in focus_items if str(item).strip()) or "起業準備を継続する"
    log_rel = log_path.relative_to(ROOT).as_posix() if log_path else "logs/"
    latest_log = read(log_path) if log_path else ""
    ai_json = json.dumps(ai, ensure_ascii=False, indent=2) if ai else "最新AI出力はまだありません。"

    md = ["# ファントム ダッシュボード", "", "## 現在状況", "", f"- 最終更新：{now:%Y-%m-%d %H:%M} JST", f"- フェーズ：{company['phase']}", f"- 起業日まで：{_days_text(company['days_until_launch'])}", f"- 会社名：{company['company_name']}", f"- 正式名称：{company['legal_name']}", f"- 法人形態：{company['legal_form']}", f"- 会社資金：{company['company_cash']}", f"- 起業準備金：{company['preparation_fund']}", f"- 今月売上：{company['monthly_sales']}", f"- 今月費用：{company['monthly_expense']}", f"- 評判：{company['reputation']}", "", "## 社員状態", "", "| 社員 | 役割 | 疲労 | 意欲 | 所持金 | 預金 | 現在の方向性 |", "|---|---|---:|---:|---:|---:|---|"]
    for e in employees:
        md.append(f"| {e['name']} | {e['role']} | {e['fatigue']} | {e['motivation']} | {e['cash_text']} | {e['bank_text']} | {e['current_task']} |")
    md += ["", "## 直近ターン要約", ""] + [f"- {line}" for line in summary] + ["", "## 次の注力事項", "", f"- {focus}", "", "<details>", "<summary>会社詳細</summary>", "", "- [会社情報](./data/company.md)", f"- 資金状況：会社資金 {company['company_cash']} / 起業準備金 {company['preparation_fund']}", f"- 法人形態の状態：{company['legal_form']}", "", "</details>", "", "<details>", "<summary>社員詳細</summary>", ""]
    for e in employees:
        md.append(f"- [{e['name']}](./{e['path']})：前回行動「{e['last_action']}」 / 現在タスク「{e['current_task']}」")
    md += ["", "</details>", "", "<details>", "<summary>最新ログ</summary>", "", f"- [最新ログ](./{log_rel})", "- 最新AI出力の要約：", *[f"  - {line}" for line in summary], "", "</details>", "", "## リンク", "", "- [現在状態](./data/current_state.md)", "- [会社情報](./data/company.md)", "- [佐藤 直樹](./data/employees/001_ceo.md)", "- [高橋 美咲](./data/employees/002_ai_flow_designer.md)", "- [田中 蓮](./data/employees/003_automation_engineer.md)", "- [ログ](./logs/)", "- [HTML版](./docs/index.html)", ""]
    write(ROOT / "DASHBOARD.md", "\n".join(md))

    def esc(v: Any) -> str:
        return html.escape(str(v), quote=True)
    cards = "".join(f"""<article class=\"card\"><h3>{esc(e['name'])}</h3><p>{esc(e['age'])}歳 / {esc(e['role'])}</p><p>疲労 {e['fatigue']}</p><div class=\"meter\"><span style=\"width: {max(0, min(100, e['fatigue']))}%\"></span></div><p>意欲 {e['motivation']}</p><div class=\"meter motivation\"><span style=\"width: {max(0, min(100, e['motivation']))}%\"></span></div><p>所持金：{esc(e['cash_text'])}<br>預金：{esc(e['bank_text'])}</p><p>前回の行動：{esc(e['last_action'])}</p><p>現在タスク：{esc(e['current_task'])}</p></article>""" for e in employees)
    html_doc = f"""<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>ファントム Dashboard</title><style>body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f6f8fa;color:#24292f}}header{{background:#1f2937;color:white;padding:24px 16px}}main{{max-width:980px;margin:auto;padding:16px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}}.card,details{{background:white;border:1px solid #d0d7de;border-radius:12px;padding:16px;margin:12px 0;box-shadow:0 1px 2px #0001}}.metric{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}.meter{{height:10px;background:#eaeef2;border-radius:999px;overflow:hidden}}.meter span{{display:block;height:100%;background:#fb7185}}.meter.motivation span{{background:#22c55e}}pre{{white-space:pre-wrap;overflow:auto;background:#f6f8fa;padding:12px;border-radius:8px}}a{{color:#0969da}}@media(max-width:600px){{header{{padding:18px 12px}}main{{padding:10px}}.metric{{grid-template-columns:1fr}}}}</style></head><body><header><h1>ファントム Dashboard</h1><p>最終更新日時：{esc(now.strftime('%Y-%m-%d %H:%M JST'))}</p><p>現在フェーズ：{esc(company['phase'])} / 起業日まで：{esc(_days_text(company['days_until_launch']))}</p></header><main><section class=\"card\"><h2>現在状況</h2><div class=\"metric\"><div>会社名：{esc(company['company_name'])}</div><div>正式名称：{esc(company['legal_name'])}</div><div>法人形態：{esc(company['legal_form'])}</div><div>会社資金：{esc(company['company_cash'])}</div><div>起業準備金：{esc(company['preparation_fund'])}</div><div>今月売上：{esc(company['monthly_sales'])}</div><div>今月費用：{esc(company['monthly_expense'])}</div><div>評判：{esc(company['reputation'])}</div></div></section><section><h2>社員カード</h2><div class=\"grid\">{cards}</div></section><section class=\"card\"><h2>直近ターン要約</h2><ul>{''.join(f'<li>{esc(s)}</li>' for s in summary)}</ul><h2>次の注力事項</h2><p>{esc(focus)}</p></section><details><summary>会社詳細</summary><p>会社情報：<a href=\"../data/company.md\">company.md</a></p><p>資金状況：会社資金 {esc(company['company_cash'])} / 起業準備金 {esc(company['preparation_fund'])}</p><p>法人形態：{esc(company['legal_form'])}</p></details><details><summary>社員詳細</summary><ul>{''.join(f'<li><a href="../{esc(e["path"])}">{esc(e["name"])}</a>：{esc(e["last_action"])} / {esc(e["current_task"])}</li>' for e in employees)}</ul></details><details><summary>最新AI出力</summary><pre>{esc(ai_json)}</pre></details><details><summary>最新ログ本文</summary><p><a href=\"../{esc(log_rel)}\">最新ログ</a></p><pre>{esc(latest_log[:6000])}</pre></details><details><summary>資金状況</summary><p>会社資金：{esc(company['company_cash'])}<br>起業準備金：{esc(company['preparation_fund'])}<br>今月売上：{esc(company['monthly_sales'])}<br>今月費用：{esc(company['monthly_expense'])}</p></details><details><summary>リンク集</summary><p><a href=\"../data/current_state.md\">current_state.md</a><br><a href=\"../data/company.md\">company.md</a><br><a href=\"../data/employees/001_ceo.md\">佐藤 直樹</a><br><a href=\"../data/employees/002_ai_flow_designer.md\">高橋 美咲</a><br><a href=\"../data/employees/003_automation_engineer.md\">田中 蓮</a><br><a href=\"../logs/\">logs</a></p></details></main></body></html>"""
    write(ROOT / "docs/index.html", html_doc)
