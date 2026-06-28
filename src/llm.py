"""LLMラッパー：マルチプロバイダ・フォールバック（OpenAI互換中心 + Gemini native）。

1次プロバイダが 429/エラー/JSON崩れ なら自動で次プロバイダへ切替。単一プロバイダ
(Gemini)依存を解消し、無料枠が枯れても止まらない。GitHub Models は GitHub Actions の
GITHUB_TOKEN（models:read 権限）でそのまま使えるため、ユーザーの追加鍵なしで1次に置ける。

呼び出し側I/Fは従来どおり:
  generate(prompt, as_json=True, schema=None) -> str | dict | list
  generate_grounded(prompt) -> {"text": ..., "sources": [...]}   # Geminiのgoogle_search限定

設計（レート制限対策の要点）:
  * 1プロバイダあたりの試行は MAX_RETRIES=2 まで。429は即離脱して次プロバイダへ。
  * 指数バックオフは廃止（固定 RETRY_WAIT 秒）。枯れた枠を叩き続けて1日分を自焼するのを防ぐ。
  * 鍵が無いプロバイダは自動スキップ＝設定だけ用意しておけば、後で鍵を足すと自動で有効化。
"""
from __future__ import annotations
import json
import os
import re
import time
import requests
from .util import load_settings, log

# プロバイダ定義。key_env のいずれかが環境にあれば有効、無ければ自動スキップ。
# openai=True は OpenAI互換 /chat/completions。max_out は無料枠の出力上限の目安。
_PROVIDERS = {
    "github": {  # GitHub Models（無料）。Actions内は GITHUB_TOKEN(models:read)で動く＝鍵不要
        "url": "https://models.github.ai/inference/chat/completions",
        "model": "openai/gpt-4o-mini",
        "key_env": ["GITHUB_MODELS_TOKEN", "GITHUB_TOKEN"],
        "openai": True, "max_out": 4000,
    },
    "groq": {  # Groq（無料 1,000 RPD・爆速）。要 GROQ_API_KEY
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": "llama-3.3-70b-versatile",
        "key_env": ["GROQ_API_KEY"], "openai": True, "max_out": 8000,
    },
    "deepseek": {  # DeepSeek（激安・高品質）。要 DEEPSEEK_API_KEY
        "url": "https://api.deepseek.com/v1/chat/completions",
        "model": "deepseek-chat",
        "key_env": ["DEEPSEEK_API_KEY"], "openai": True, "max_out": 8000,
    },
    "openai": {  # OpenAI（任意）。要 OPENAI_API_KEY
        "url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
        "key_env": ["OPENAI_API_KEY"], "openai": True, "max_out": 8000,
    },
    "anthropic": {  # Anthropic（任意・messages API）。要 ANTHROPIC_API_KEY
        "url": "https://api.anthropic.com/v1/messages",
        "model": "claude-3-5-haiku-latest",
        "key_env": ["ANTHROPIC_API_KEY"], "openai": False, "anthropic": True, "max_out": 4096,
    },
    "gemini": {  # Gemini（native）。schema(controlled generation)対応・出力窓が大きい
        "model": "gemini-2.5-flash",
        "key_env": ["GEMINI_API_KEY"], "openai": False, "max_out": 24576,
    },
}

# Gemini モデルのフォールバック（429/404 時に順に試す）。
_GEMINI_FALLBACKS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-flash-latest"]

# 既定のフォールバック順。鍵が無いものは自動スキップ。settings.yaml の llm.providers で上書き可。
_DEFAULT_CHAIN = ["github", "gemini", "groq", "deepseek"]

MAX_RETRIES = 2     # 1プロバイダあたりの試行回数（リトライ嵐を防ぐ）
RETRY_WAIT = 8      # 秒・固定待ち（指数バックオフは廃止＝枠の自焼を防ぐ）


def _settings_llm() -> dict:
    try:
        return load_settings().get("llm", {}) or {}
    except Exception:
        return {}


def _key_for(p: dict):
    for env in p.get("key_env", []):
        v = os.environ.get(env)
        if v:
            return v
    return None


def _model_for(name: str, p: dict, cfg: dict) -> str:
    # settings.yaml の llm.models.<name> で個別上書き可。gemini は llm.model も尊重。
    ov = (cfg.get("models") or {}).get(name)
    if ov:
        return ov
    if name == "gemini":
        return cfg.get("model", p["model"])
    if name == "github" and cfg.get("github_model"):
        return cfg["github_model"]
    return p["model"]


def _extract_json(text: str):
    """LLM出力からJSON部分を頑健に抜き出す。崩れていれば例外（→次プロバイダ）。"""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def _is_429(e) -> bool:
    code = getattr(getattr(e, "response", None), "status_code", None)
    return code == 429 or " 429" in f" {e}"


# ---- OpenAI互換 /chat/completions ----
def _openai_chat(p, key, model, prompt, as_json, max_out) -> str:
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": max_out,
    }
    if as_json:
        body["response_format"] = {"type": "json_object"}
    r = requests.post(p["url"], headers=headers, json=body, timeout=120)
    if r.status_code == 400 and as_json:
        # response_format 非対応モデルは指定を外して再試行（プロンプト側でJSON強制済み）
        body.pop("response_format", None)
        r = requests.post(p["url"], headers=headers, json=body, timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# ---- Anthropic messages ----
def _anthropic_chat(p, key, model, prompt, max_out) -> str:
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
               "Content-Type": "application/json"}
    body = {"model": model, "max_tokens": max_out,
            "messages": [{"role": "user", "content": prompt}]}
    r = requests.post(p["url"], headers=headers, json=body, timeout=120)
    r.raise_for_status()
    return r.json()["content"][0]["text"]


# ---- Gemini native（schema=controlled generation 対応） ----
def _gemini(prompt, model, as_json, schema, max_out) -> str:
    key = os.environ["GEMINI_API_KEY"]
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if as_json:
        gc = {"responseMimeType": "application/json", "maxOutputTokens": max_out}
        if schema:
            gc["responseSchema"] = schema
        body["generationConfig"] = gc
    r = requests.post(url, json=body, timeout=120)
    r.raise_for_status()
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _try_provider(name, prompt, as_json, schema):
    """1プロバイダを最大MAX_RETRIES試す。429は即離脱（次プロバイダへ）。
    返り値: (結果 or None, エラー or 'no-key' or None)。"""
    cfg = _settings_llm()
    p = _PROVIDERS[name]
    key = _key_for(p)
    if not key:
        log.info("LLM %s: 鍵未設定→スキップ", name)
        return None, "no-key"
    model = _model_for(name, p, cfg)
    max_out = p.get("max_out", 4000)
    retries = int(cfg.get("max_retries", MAX_RETRIES))
    wait = int(cfg.get("retry_wait_sec", RETRY_WAIT))
    last = None
    for attempt in range(retries):
        try:
            if p.get("anthropic"):
                out = _anthropic_chat(p, key, model, prompt, max_out)
            elif p["openai"]:
                out = _openai_chat(p, key, model, prompt, as_json, max_out)
            else:
                # gemini: モデル別フォールバックも内包
                models = [model] + [m for m in _GEMINI_FALLBACKS if m != model]
                g_last, out = None, None
                for gm in models:
                    try:
                        out = _gemini(prompt, gm, as_json, schema, max_out)
                        break
                    except requests.HTTPError as ge:
                        g_last = ge
                        if _is_429(ge):
                            continue   # 次のgeminiモデルへ
                        raise
                if out is None:
                    raise g_last or RuntimeError("gemini all models failed")
            return (_extract_json(out) if as_json else out), None
        except Exception as e:
            last = e
            if _is_429(e):
                log.warning("LLM %s: 429（枠切れ）→次プロバイダ", name)
                break   # このプロバイダは枯渇。即離脱。
            if attempt < retries - 1:
                log.warning("LLM %s: 失敗(%s) %ds後に再試行", name, str(e)[:80], wait)
                time.sleep(wait)
            else:
                log.warning("LLM %s: 失敗(%s)→次プロバイダ", name, str(e)[:80])
    return None, last


def generate(prompt: str, as_json: bool = True, schema=None):
    """プロンプトを投げ、文字列 or JSON(dict/list)を返す。
    複数プロバイダを順に試し、429/失敗/JSON崩れなら自動で次へフォールバックする。"""
    cfg = _settings_llm()
    # providers未指定なら既定チェーン（脱Gemini：github→gemini→groq→deepseek）。
    # これで settings.yaml を触らずとも multi-provider が有効になる。
    chain = cfg.get("providers") or _DEFAULT_CHAIN
    # gemini を最終保険として必ず含める（大きな出力窓＋schema対応）。重複除去・順序維持。
    chain = list(chain) + ["gemini"]
    seen = set()
    chain = [c for c in chain if c in _PROVIDERS and not (c in seen or seen.add(c))]
    log.info("LLM呼び出し: chain=%s as_json=%s", chain, as_json)
    last = None
    for name in chain:
        out, err = _try_provider(name, prompt, as_json, schema)
        if out is not None:
            return out
        if err and err != "no-key":
            last = err
    raise RuntimeError(f"全LLMプロバイダ失敗: {last}")


# ---- Grounding（Gemini google_search 限定）----
def _gemini_grounded(prompt, model) -> dict:
    key = os.environ["GEMINI_API_KEY"]
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}]}
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
    """日本語ソースのグラウンディング（Gemini限定）。失敗時は例外（呼び出し側でtry）。
    GEMINI_API_KEY が無ければグラウンディング無効として例外。"""
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("grounding unavailable: no GEMINI_API_KEY")
    cfg = _settings_llm()
    base = cfg.get("grounding_model", cfg.get("model", "gemini-2.5-flash"))
    models = [base] + [m for m in _GEMINI_FALLBACKS if m != base]
    retries = int(cfg.get("max_retries", MAX_RETRIES))
    wait = int(cfg.get("retry_wait_sec", RETRY_WAIT))
    last = None
    for m in models:
        for attempt in range(retries):
            try:
                return _gemini_grounded(prompt, m)
            except Exception as e:
                last = e
                if _is_429(e):
                    break   # 次モデルへ
                if attempt < retries - 1:
                    time.sleep(wait)
    raise last or RuntimeError("grounding failed")
