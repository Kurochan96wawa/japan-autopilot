"""LLMラッパー。Gemini(無料枠) / OpenAI / Anthropic を切り替え可能。
JSON出力を要求して構造化データで受け取る設計。
"""
from __future__ import annotations
import json
import os
import re
import requests
from .util import load_settings, log


def _extract_json(text: str):
    """LLM出力からJSON部分を頑健に抜き出す。"""
    text = text.strip()
    # ```json ... ``` を剥がす
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 最初の { か [ から最後の } か ] までを試す
        m = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def _gemini(prompt: str, model: str) -> str:
    key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    r = requests.post(url, json=body, timeout=120)
    r.raise_for_status()
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _openai(prompt: str, model: str) -> str:
    key = os.environ["OPENAI_API_KEY"]
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _anthropic(prompt: str, model: str) -> str:
    key = os.environ["ANTHROPIC_API_KEY"]
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
        json={"model": model, "max_tokens": 4000,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"]


def generate(prompt: str, as_json: bool = True):
    """プロンプトを投げて文字列 or JSON(dict/list)を返す。"""
    cfg = load_settings()["llm"]
    provider = cfg["provider"]
    model = cfg["model"]
    log.info("LLM呼び出し: provider=%s model=%s", provider, model)
    if provider == "gemini":
        out = _gemini(prompt, model)
    elif provider == "openai":
        out = _openai(prompt, model)
    elif provider == "anthropic":
        out = _anthropic(prompt, model)
    else:
        raise ValueError(f"不明なLLMプロバイダ: {provider}")
    return _extract_json(out) if as_json else out
