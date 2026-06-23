from __future__ import annotations

import os


def call_openai(prompt: str, important: bool = False) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    from openai import OpenAI

    model = os.getenv("OPENAI_MODEL_IMPORTANT" if important else "OPENAI_MODEL_NORMAL") or ("gpt-4.1" if important else "gpt-4.1-mini")
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        input=prompt,
        text={"format": {"type": "json_object"}},
    )
    return response.output_text
