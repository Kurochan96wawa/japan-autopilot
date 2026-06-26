"""LLMラッパー。Gemini(無料枠) / OpenAI / Anthropic を切り替え可能。
JSON出力を要求して構造化データで受け取る設計。
"""
from __future__ import annotations
import json
import os
import re
import time
import random
import requests
from .util import load_settings, log

# Geminiは429(レート/クォータ)が出やすいので、別の無料モデルへ順に切替える
# 2026年現行の無料枠モデル（2.0/1.5系は終了済み）。flash-latestは最新flashへのエイリアス。
# ※ gemini-3-flash は存在せず404を返すためフォールバックから除外（枠の浪費＆遅延の原因だった）。
_GEMINI_FALLBACKS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest"]


def _retry_429(fn, attempts: int = 6):
    """429/503を指数バックオフ+ジッターでリトライ。日次バッチなので待ってOK。
    無料枠はRPM上限に当たりやすいので、試行回数・待ち時間を長めに取って取りこぼしを減らす。"""
    last = None
    for i in range(attempts):
        try:
            return fn()
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            last = e
            if code in (429, 503) and i < attempts - 1:
                wait = min(90, 8 * (2 ** i)) + random.uniform(0, 4)
                log.warning("LLM %s。%.0f秒待って再試行(%d/%d)", code, wait, i + 1, attempts)
                time.sleep(wait)
                continue
            raise
    raise last


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


def _gemini(prompt: str, model: str, json_mode: bool = True, schema: dict | None = None) -> str:
    key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if json_mode:
        # JSON強制モード。HTMLを含む長い応答でもAPI側でエスケープを保証させ、パース失敗を防ぐ。
        # maxOutputTokensは思考トークン＋本文(1100-1800語)＋FAQで枯渇しない余裕値に（8192では本文が途中切断していた）。
        gc = {"responseMimeType": "application/json", "maxOutputTokens": 24576}
        if schema:
            # 構造化出力（controlled generation）。スキーマに沿った“必ず妥当なJSON”が返る。
            gc["responseSchema"] = schema
        body["generationConfig"] = gc
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


def generate(prompt: str, as_json: bool = True, schema: dict | None = None):
    """プロンプトを投げて文字列 or JSON(dict/list)を返す。
    429対策: 指数バックオフでリトライし、geminiは別の無料モデルへ順にフォールバック。
    schema を渡すと（geminiのみ）構造化出力で“必ず妥当なJSON”を返させる。"""
    cfg = load_settings()["llm"]
    provider = cfg["provider"]
    model = cfg["model"]
    log.info("LLM呼び出し: provider=%s model=%s", provider, model)

    if provider == "gemini":
        # 設定モデルを先頭に、重複を除いたフォールバック順を作る
        models = [model] + [m for m in _GEMINI_FALLBACKS if m != model]
        last = None
        for m in models:
            try:
                out = _retry_429(lambda m=m: _gemini(prompt, m, as_json, schema))
                if m != model:
                    log.warning("geminiモデルを %s にフォールバックして成功", m)
                return _extract_json(out) if as_json else out
            except requests.HTTPError as e:
                last = e
                log.warning("geminiモデル %s 失敗(%s)。次を試す",
                            m, getattr(e.response, "status_code", "?"))
                continue
        raise last
    elif provider == "openai":
        out = _retry_429(lambda: _openai(prompt, model))
    elif provider == "anthropic":
        out = _retry_429(lambda: _anthropic(prompt, model))
    else:
        raise ValueError(f"不明なLLMプロバイダ: {provider}")
    return _extract_json(out) if as_json else out


def _gemini_grounded(prompt: str, model: str) -> dict:
    key = os.environ["GEMINI_API_KEY"]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {"contents": [{"parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]}
    r = requests.post(url, json=body, timeout=120)
    r.raise_for_status()
    data = r.json()
    cand = data["candidates"][0]
    parts = cand.get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    sources = []
    for ch in cand.get("groundingMetadata", {}).get("groundingChunks", []):
        web = ch.get("web", {})
        if web.get("uri"):
            sources.append({"name": web.get("title", ""), "url": web["uri"]})
    return {"text": text, "sources": sources}


def generate_grounded(prompt: str) -> dict:
    """Google search grounding for Japanese sources. Returns {text, sources}; raises on failure."""
    cfg = load_settings()["llm"]
    model = cfg.get("grounding_model", cfg.get("model", "gemini-2.5-flash"))
    models = [model] + [m for m in _GEMINI_FALLBACKS if m != model]
    last = None
    for m in models:
        try:
            return _retry_429(lambda m=m: _gemini_grounded(prompt, m))
        except requests.HTTPError as e:
            last = e
            log.warning("grounded %s failed (%s)", m, getattr(e.response, "status_code", "?"))
            continue
    raise last if last else RuntimeError("grounding failed")
