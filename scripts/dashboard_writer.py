from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

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
        employee_name = employee.get("name") or employee.get("employee_name") or employee.get("id", "社員")
        actions = employee.get("actions") or [employee]
        action_texts = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            action_name = str(action.get("name") or "").strip()
            details = str(action.get("details") or action.get("description") or action.get("outcome") or "").strip()
            text = "：".join(part for part in [action_name, details] if part) or action.get("title")
            if text:
                action_texts.append(text)
        if action_texts:
            lines.append(f"{employee_name}：{action_texts[0]}")
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


def _parse_log_datetime(text: str, path: Path) -> datetime:
    match = re.search(r"# シミュレーションログ (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})", text)
    if match:
        try:
            return datetime.strptime(" ".join(match.groups()), "%Y-%m-%d %H:%M")
        except ValueError:
            pass
    try:
        return datetime.strptime(f"{path.parent.name} {path.stem}", "%Y-%m-%d %H%M")
    except ValueError:
        return datetime.fromtimestamp(path.stat().st_mtime)


def _first_event_reason(ai: dict[str, Any]) -> str:
    for event in ai.get("events", []) or []:
        if event.get("reason"):
            return str(event["reason"])
        if event.get("details"):
            return str(event["details"])
    important = ai.get("important_event", {}) if isinstance(ai.get("important_event"), dict) else {}
    return str(important.get("summary") or ai.get("turn", {}).get("summary") or "このターンの会社状況と担当役割に基づいて実行。")


def _next_impact(ai: dict[str, Any]) -> str:
    focus = ai.get("next_company_focus")
    if isinstance(focus, list):
        text = " / ".join(str(item) for item in focus if str(item).strip())
    else:
        text = str(focus or "")
    return text or "次回ターンの判断材料として継続参照。"


def _employee_action_history() -> dict[str, list[dict[str, str]]]:
    """Read Markdown logs and return employee actions newest first.

    Missing, malformed, or non-JSON logs are skipped so dashboard generation never
    blocks the scheduled simulation flow.
    """
    history: dict[str, list[dict[str, str]]] = {}
    for log_file in sorted((ROOT / "logs").glob("*/*.md")):
        text = read(log_file)
        ai = _load_ai_from_log(log_file)
        if not ai:
            continue
        executed_at = _parse_log_datetime(text, log_file)
        reason = _first_event_reason(ai)
        next_impact = _next_impact(ai)
        for employee in ai.get("employees", []) or []:
            emp_id = str(employee.get("id", "")).strip()
            if not emp_id:
                continue
            actions = employee.get("actions") or [employee]
            for action in actions:
                if not isinstance(action, dict):
                    continue
                name = str(action.get("name") or "").strip()
                details = str(action.get("details") or action.get("description") or action.get("outcome") or "").strip()
                description = "：".join(part for part in [name, details] if part) or action.get("title") or action.get("type") or "行動内容なし"
                outcome = action.get("outcome") or action.get("result") or "成果の記録なし"
                history.setdefault(emp_id, []).append({
                    "executed_at": executed_at.strftime("%Y-%m-%d %H:%M JST"),
                    "sort_key": executed_at.isoformat(),
                    "action": str(description),
                    "reason": reason,
                    "outcome": str(outcome),
                    "next_impact": next_impact,
                })
    for entries in history.values():
        entries.sort(key=lambda item: item["sort_key"], reverse=True)
    return history


def _render_action_list(entries: list[dict[str, str]], esc: Callable[[Any], str]) -> str:
    if not entries:
        return '<p class="empty">行動履歴はまだ記録されていません。</p>'
    return "".join(
        '<article class="history-item">'
        f'<h3>{esc(entry["executed_at"])}</h3>'
        '<dl>'
        f'<dt>行動内容</dt><dd>{esc(entry["action"])}</dd>'
        f'<dt>判断理由</dt><dd>{esc(entry["reason"])}</dd>'
        f'<dt>成果</dt><dd>{esc(entry["outcome"])}</dd>'
        f'<dt>次回への影響</dt><dd>{esc(entry["next_impact"])}</dd>'
        '</dl></article>'
        for entry in entries
    )


def _employee_details(updated: dict[str, Any] | None) -> list[dict[str, Any]]:
    by_id = {e["id"]: dict(e) for e in updated["employees"]} if updated and updated.get("employees") else {}
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
    if isinstance(value, int):
        return f"起業後{abs(value)}日" if value < 0 else f"{value}日"
    text = str(value)
    match = re.fullmatch(r"-(\d+)日?", text)
    return f"起業後{match.group(1)}日" if match else text


def _focus_warning(focus: str, company_cash_text: str) -> str:
    cash = int(re.sub(r"\D", "", company_cash_text) or 0)
    amounts = [int(m.replace(",", "")) for m in re.findall(r"(\d{1,3}(?:,\d{3})+)円", focus)]
    if cash and any(amount != cash for amount in amounts):
        return f"（注意：現在の会社資金は{company_cash_text}です。注力事項内の金額表現と矛盾する可能性があります）"
    return ""


def write_dashboard(updated: dict[str, Any] | None = None, now: datetime | None = None, log_path: Path | None = None) -> None:
    log_path = log_path or _latest_log_path()
    now = now or (_parse_log_datetime(read(log_path), log_path) if log_path else datetime.now())
    ai = dict(updated.get("ai", {})) if updated and updated.get("ai") else _load_ai_from_log(log_path)
    company = _company_details(updated)
    employees = _employee_details(updated)
    histories = _employee_action_history()
    summary = _action_lines(ai)
    focus_value = ai.get("next_company_focus") or _bullet(read(ROOT / "data/current_state.md"), "次の注力事項", "起業準備を継続する")
    focus_items = focus_value if isinstance(focus_value, list) else [str(focus_value)]
    focus = " / ".join(str(item) for item in focus_items if str(item).strip()) or "起業準備を継続する"
    focus_warning = _focus_warning(focus, company["company_cash"])
    if focus_warning:
        focus = f"{focus} {focus_warning}"
    log_rel = log_path.relative_to(ROOT).as_posix() if log_path else "logs/"
    latest_log = read(log_path) if log_path else ""
    ai_json = json.dumps(ai, ensure_ascii=False, indent=2) if ai else "最新AI出力はまだありません。"

    md = ["# ファントム ダッシュボード", "", "## 現在状況", "", f"- 最終更新：{now:%Y-%m-%d %H:%M} JST", f"- フェーズ：{company['phase']}", f"- 起業日まで：{_days_text(company['days_until_launch'])}", f"- 会社名：{company['company_name']}", f"- 正式名称：{company['legal_name']}", f"- 法人形態：{company['legal_form']}", f"- 会社資金：{company['company_cash']}", f"- 起業準備金：{company['preparation_fund']}", f"- 今月売上：{company['monthly_sales']}", f"- 今月費用：{company['monthly_expense']}", f"- 評判：{company['reputation']}", "", "## 社員状態", "", "| 社員 | 役割 | 疲労 | 意欲 | 所持金 | 預金 | 現在の方向性 |", "|---|---|---:|---:|---:|---:|---|"]
    for e in employees:
        md.append(f"| {e['name']} | {e['role']} | {e['fatigue']} | {e['motivation']} | {e['cash_text']} | {e['bank_text']} | {e['current_task']} |")
    md += ["", "## 直近ターン要約", ""] + [f"- {line}" for line in summary] + ["", "## 次の注力事項", "", f"- {focus}", "", "<details>", "<summary>会社詳細</summary>", "", "- [会社情報](./data/company.md)", f"- 資金状況：会社資金 {company['company_cash']} / 起業準備金 {company['preparation_fund']}", f"- 法人形態の状態：{company['legal_form']}", "", "</details>", "", "<details>", "<summary>社員詳細</summary>", ""]
    for e in employees:
        md.append(f"- [{e['name']}](./{e['path']}) / [行動履歴](./docs/employees/{e['id']}.html)：前回行動「{e['last_action']}」 / 現在タスク「{e['current_task']}」")
    md += ["", "</details>", "", "<details>", "<summary>最新ログ</summary>", "", f"- [最新ログ](./{log_rel})", "- 最新AI出力の要約：", *[f"  - {line}" for line in summary], "", "</details>", "", "## リンク", "", "- [現在状態](./data/current_state.md)", "- [会社情報](./data/company.md)", "- [佐藤 直樹](./data/employees/001_ceo.md)", "- [高橋 美咲](./data/employees/002_ai_flow_designer.md)", "- [田中 蓮](./data/employees/003_automation_engineer.md)", "- [ログ](./logs/)", "- [HTML版](./docs/index.html)", ""]
    write(ROOT / "DASHBOARD.md", "\n".join(md))

    def esc(v: Any) -> str:
        return html.escape(str(v), quote=True)

    cards_parts = []
    for e in employees:
        recent = histories.get(e["id"], [])[:3]
        recent_html = "".join(f'<li><time>{esc(item["executed_at"])}</time><br>{esc(item["action"])}</li>' for item in recent) or '<li class="empty">行動履歴はまだありません。</li>'
        cards_parts.append(f"""<article class=\"card employee-card\"><h3>{esc(e['name'])}</h3><p>{esc(e['age'])}歳 / {esc(e['role'])}</p><p>疲労 {e['fatigue']}</p><div class=\"meter\"><span style=\"width: {max(0, min(100, e['fatigue']))}%\"></span></div><p>意欲 {e['motivation']}</p><div class=\"meter motivation\"><span style=\"width: {max(0, min(100, e['motivation']))}%\"></span></div><p>所持金：{esc(e['cash_text'])}<br>預金：{esc(e['bank_text'])}</p><p>前回の行動：{esc(e['last_action'])}</p><p>現在タスク：{esc(e['current_task'])}</p><h4>直近の行動</h4><ul class=\"recent-actions\">{recent_html}</ul><p><a class=\"history-link\" href=\"employees/{esc(e['id'])}.html\">行動履歴を見る</a></p></article>""")
    cards = "".join(cards_parts)
    style = """body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f6f8fa;color:#24292f}header{background:#1f2937;color:white;padding:24px 16px}main{max-width:980px;margin:auto;padding:16px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}.card,details{background:white;border:1px solid #d0d7de;border-radius:12px;padding:16px;margin:12px 0;box-shadow:0 1px 2px #0001}.metric{display:grid;grid-template-columns:1fr 1fr;gap:8px}.meter{height:10px;background:#eaeef2;border-radius:999px;overflow:hidden}.meter span{display:block;height:100%;background:#fb7185}.meter.motivation span{background:#22c55e}pre{white-space:pre-wrap;overflow:auto;background:#f6f8fa;padding:12px;border-radius:8px}a{color:#0969da}.employee-card h4{margin-bottom:6px}.recent-actions{padding-left:18px}.recent-actions li{margin:6px 0}.recent-actions time{font-size:.85em;color:#57606a}.history-link{font-weight:700}.empty{color:#57606a}@media(max-width:600px){header{padding:18px 12px}main{padding:10px}.metric{grid-template-columns:1fr}}"""
    html_doc = f"""<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>ファントム Dashboard</title><style>{style}</style></head><body><header><h1>ファントム Dashboard</h1><p>最終更新日時：{esc(now.strftime('%Y-%m-%d %H:%M JST'))}</p><p>現在フェーズ：{esc(company['phase'])} / 起業日まで：{esc(_days_text(company['days_until_launch']))}</p></header><main><section class=\"card\"><h2>現在状況</h2><div class=\"metric\"><div>会社名：{esc(company['company_name'])}</div><div>正式名称：{esc(company['legal_name'])}</div><div>法人形態：{esc(company['legal_form'])}</div><div>会社資金：{esc(company['company_cash'])}</div><div>起業準備金：{esc(company['preparation_fund'])}</div><div>今月売上：{esc(company['monthly_sales'])}</div><div>今月費用：{esc(company['monthly_expense'])}</div><div>評判：{esc(company['reputation'])}</div></div></section><section><h2>社員カード</h2><div class=\"grid\">{cards}</div></section><section class=\"card\"><h2>直近ターン要約</h2><ul>{''.join(f'<li>{esc(s)}</li>' for s in summary)}</ul><h2>次の注力事項</h2><p>{esc(focus)}</p></section><details><summary>会社詳細</summary><p>会社情報はこのページ内の現在状況に要約しています。</p><p>資金状況：会社資金 {esc(company['company_cash'])} / 起業準備金 {esc(company['preparation_fund'])}</p><p>法人形態：{esc(company['legal_form'])}</p></details><details><summary>社員詳細</summary><ul>{''.join(f'<li>{esc(e["name"])}：{esc(e["last_action"])} / {esc(e["current_task"])}</li>' for e in employees)}</ul></details><details><summary>最新AI出力</summary><pre>{esc(ai_json)}</pre></details><details><summary>最新ログ本文</summary><p>最新ログ本文はこのページ内にHTMLエスケープして抜粋表示しています。</p><pre>{esc(latest_log[:6000])}</pre></details><details><summary>資金状況</summary><p>会社資金：{esc(company['company_cash'])}<br>起業準備金：{esc(company['preparation_fund'])}<br>今月売上：{esc(company['monthly_sales'])}<br>今月費用：{esc(company['monthly_expense'])}</p></details><details><summary>公開時の注記</summary><p>このHTMLはGitHub Pagesの/docs配下で単体表示できるよう、社員別行動履歴ページも/docs配下に生成します。</p></details></main></body></html>"""

    employees_dir = ROOT / "docs/employees"
    for e in employees:
        entries = histories.get(e["id"], [])
        page_style = """body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f6f8fa;color:#24292f}header{background:#1f2937;color:white;padding:24px 16px}header a{color:#bfdbfe}main{max-width:980px;margin:auto;padding:16px}.card,.history-item{background:white;border:1px solid #d0d7de;border-radius:12px;padding:16px;margin:12px 0;box-shadow:0 1px 2px #0001}a{color:#0969da}.history-item h3{margin-top:0}.history-item dl{display:grid;grid-template-columns:8.5em 1fr;gap:8px 12px}.history-item dt{font-weight:700;color:#57606a}.history-item dd{margin:0}.empty{color:#57606a}@media(max-width:600px){header{padding:18px 12px}main{padding:10px}.history-item dl{grid-template-columns:1fr}}"""
        page = f"""<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>{esc(e['name'])} 行動履歴 - ファントム</title><style>{page_style}</style></head><body><header><h1>{esc(e['name'])} 行動履歴</h1><p>{esc(e['role'])}</p><p><a href=\"../index.html\">ダッシュボードに戻る</a></p></header><main><section class=\"card\"><h2>社員概要</h2><p>{esc(e['age'])}歳 / 疲労 {e['fatigue']} / 意欲 {e['motivation']}</p><p>所持金：{esc(e['cash_text'])}<br>預金：{esc(e['bank_text'])}</p></section><section><h2>行動ログ</h2>{_render_action_list(entries, esc)}</section></main></body></html>"""
        write(employees_dir / f"{e['id']}.html", page)

    write(ROOT / "docs/index.html", html_doc)
