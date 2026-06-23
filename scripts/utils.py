from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[1]


def now_jst() -> datetime:
    return datetime.now(JST)


def clamp(value: int | float, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


def yen_to_int(text: str, default: int = 0) -> int:
    match = re.search(r"(-?[\d,]+)円", text)
    if not match:
        return default
    return int(match.group(1).replace(",", ""))


def int_to_yen(value: int) -> str:
    return f"{int(value):,}円"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def replace_bullet(content: str, label: str, value: str) -> str:
    pattern = re.compile(rf"^- {re.escape(label)}：.*$", re.MULTILINE)
    line = f"- {label}：{value}"
    return pattern.sub(line, content) if pattern.search(content) else content + "\n" + line + "\n"
