"""日本語の信頼できる一次情報を集めて英語記事の根拠にする（ハイブリッド: 無料キュレーション→不足時グラウンディング）。
嘘の体験は作らない。事実を英訳・統合し、出典を残す。逐語コピーはしない。"""
from __future__ import annotations
import re
from pathlib import Path
import requests
import yaml
from .util import load_settings, log
from .llm import generate_grounded

_CFG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load_sources() -> dict:
    p = _CFG_DIR / "jp_sources.yaml"
    if not p.exists():
        return {"categories": []}
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {"categories": []}
    except Exception as e:
        log.warning("jp_sources.yaml load failed: %s", e)
        return {"categories": []}


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|nav|header|footer)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def _fetch(url: str, timeout: int = 20) -> str:
    try:
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent": "Mozilla/5.0 (littletabi research)"})
        r.raise_for_status()
        return _strip_html(r.text)[:3500]
    except Exception as e:
        log.warning("jp fetch failed %s: %s", url, e)
        return ""


def _pick(topic: str, keyword: str, data: dict, limit: int = 3) -> list:
    text = f"{topic} {keyword}".lower()
    out, seen = [], set()
    for cat in data.get("categories", []):
        if any(k.lower() in text for k in cat.get("match", [])):
            for s in cat.get("sources", []):
                u = s.get("url")
                if u and u not in seen:
                    seen.add(u)
                    out.append(s)
    return out[:limit]


def _research_prompt(topic: str, keyword: str) -> str:
    return (
        f'Research for an English guide about "{topic}" (keyword: {keyword}) for foreign '
        "parents visiting Japan. Search AUTHORITATIVE JAPANESE-LANGUAGE sources (official, "
        "government/municipal, major operators) and extract concrete, practical specifics that "
        "are typically NOT available in English: prices in yen, opening hours, nursing rooms / "
        "diaper-changing facilities, stroller access and rental, child fares, reservation steps, "
        "allergy-labelling rules, etc. Prefer Japanese-only pages; skip pages that already have an "
        "English version. Give each fact as a short bullet with its source URL. Summarise; do not "
        "copy long passages."
    )


def gather_japanese_context(topic: str, keyword: str) -> dict:
    """Return Japanese-source facts and citations: {"facts": str, "sources": [..]}"""
    cfg = load_settings()
    jr = cfg.get("jp_research", {}) or {}
    if not jr.get("enabled", True):
        return {"facts": "", "sources": []}
    parts, used = [], []
    for s in _pick(topic, keyword, _load_sources()):
        body = _fetch(s["url"])
        if len(body) > 200:
            parts.append(f'[Source: {s.get("name", "")} - {s["url"]}]\n{body}')
            used.append({"name": s.get("name", ""), "url": s["url"]})
    min_curated = jr.get("min_curated_sources", 2)
    if len(parts) < min_curated and jr.get("use_grounding", True):
        try:
            g = generate_grounded(_research_prompt(topic, keyword))
            if g.get("text"):
                parts.append("[Grounded Japanese web research]\n" + g["text"])
                used.extend(g.get("sources", []))
        except Exception as e:
            log.warning("jp grounding failed (continue): %s", e)
    facts = "\n\n".join(parts)[:8000]
    seen, src = set(), []
    for s in used:
        u = s.get("url")
        if u and u not in seen:
            seen.add(u)
            src.append(s)
    log.info("JP sources: facts=%d chars / %d citations (topic=%s)", len(facts), len(src), topic)
    return {"facts": facts, "sources": src}
