from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.openai_client import call_openai
from scripts.state_loader import load_state
from scripts.state_writer import apply_turn, phase_info, write_state
from scripts.utils import ROOT, now_jst, read, write
from scripts.validators import parse_json, validate_and_normalize


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    import os
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def recent_logs(limit: int = 3) -> str:
    files = sorted((ROOT / "logs").glob("*/*.md"))[-limit:]
    return "\n\n".join(read(p)[:1200] for p in files)


def build_prompt(state: dict, now) -> tuple[str, bool]:
    company = state["company"]
    phase_jp, days = phase_info(company, now)
    phase = "pre_launch" if days > 0 else "launch_day" if days == 0 else "post_launch"
    important = phase == "launch_day" or company.get("legal_form") == "未定" and days <= 1
    prompt_file = "pre_launch_turn_prompt.md" if phase == "pre_launch" else "normal_turn_prompt.md"
    payload = {
        "simulation_phase": phase,
        "days_until_launch": days,
        "launch_date": company["launch_date"],
        "current_datetime": now.isoformat(),
        "turn_length_hours": 4,
        "company_identity": {
            "company_name": "ファントム",
            "legal_name": company["legal_name"],
            "legal_form": company["legal_form"],
            "representative": "佐藤 直樹",
            "legal_form_decision_required_by_launch": True,
        },
        "company_money": {
            "company_cash": company["company_cash"],
            "preparation_fund": company["preparation_fund"],
            "monthly_sales": company["monthly_sales"],
            "monthly_expense": company["monthly_expense"],
            "reputation": company["reputation"],
        },
        "employees": state["employees"],
        "constraints": [
            "会社名はファントムで固定",
            "正式名称と法人形態は未定なら代表が判断する",
            "起業前は正式受注と売上を原則発生させない",
            "個人資金から会社資金への移動はpersonal_fund_to_companyイベント必須",
            "JSONのみを返す",
        ],
    }
    if phase == "launch_day" and company["legal_form"] == "未定":
        payload["required_event"] = "legal_form_decisionを必ず含め、起業イベントを記録する"
    prompt = "\n\n".join([
        read(ROOT / "prompts" / prompt_file),
        read(ROOT / "prompts/important_event_prompt.md"),
        "# AI入力用current_state.md\n" + state["current_state_md"],
        "# 直近ログ（最大3件）\n" + recent_logs(),
        "# 構造化入力\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```",
        "# 出力形式\n通常ターンJSON形式で返すこと。turn, employees, company_effects, events, important_event, next_company_focusを含めること。",
    ])
    return prompt, important


def log_error(now, message: str) -> None:
    path = ROOT / f"logs/{now:%Y-%m-%d}/{now:%H%M}_error.md"
    write(path, f"# シミュレーションエラー {now:%Y-%m-%d %H:%M} JST\n\n```text\n{message}\n```\n")


def update_daily_summary(now, log_path: Path) -> None:
    if now.hour != 23:
        return
    summary = read(ROOT / "data/memory/daily_summaries.md")
    summary += f"\n## {now:%Y-%m-%d}\n\n- 当日の最新ログ：{log_path.as_posix()}\n- 詳細要約は今後の拡張でAI要約に置き換える。\n"
    write(ROOT / "data/memory/daily_summaries.md", summary)


def main() -> int:
    load_env_file(ROOT / ".env")
    now = now_jst()
    state = load_state()
    prompt, important = build_prompt(state, now)
    last_error = None
    for _ in range(2):
        try:
            raw = call_openai(prompt, important=important)
            ai = validate_and_normalize(parse_json(raw))
            updated = apply_turn(state, ai, now)
            log_path = write_state(updated, now)
            update_daily_summary(now, log_path)
            return 0
        except Exception as exc:  # log without corrupting state
            last_error = exc
            prompt += f"\n前回エラー：{exc}\nJSONのみを正しい形式で返してください。"
    log_error(now, str(last_error))
    return 1


if __name__ == "__main__":
    sys.exit(main())
