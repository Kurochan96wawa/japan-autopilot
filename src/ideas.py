"""ネタ（トピック）生成。成果データを踏まえてSEO/検索意図の強いネタを量産し、
state の topics_queue に貯める。"""
from __future__ import annotations
from .util import load_settings, log
from .llm import generate
import difflib
import re

# 生成前dedupe（3-3）: タイトルの類似で近似重複トピックを生成前に弾く。標準ライブラリのみ。
_TITLE_STOP = {"the", "a", "an", "in", "on", "at", "for", "with", "and", "to", "of", "your", "you",
               "japan", "japanese", "kids", "kid", "child", "children", "family", "families",
               "travel", "travelling", "traveling", "trip", "guide", "tips", "best", "how", "what",
               "is", "are", "2026", "2025"}


def _title_tokens(t):
    toks = re.findall(r"[a-z0-9]+", (t or "").lower())
    return {w for w in toks if len(w) > 2 and w not in _TITLE_STOP}


def _too_similar(a, b):
    ta, tb = _title_tokens(a), _title_tokens(b)
    if ta and tb:
        jac = len(ta & tb) / len(ta | tb)
        if jac >= 0.55:
            return True
    return difflib.SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio() >= 0.78


def _dup_of(topic, existing):
    for e in existing:
        if e and _too_similar(topic, e):
            return e
    return None


def mine_question_keywords(max_n: int = 12) -> list:
    """Googleオートコンプリートから実際に検索されている長尾“質問”を機械収集（無料・鍵不要）。
    競合ゼロの長尾は被リンク無しでも上位を取りやすい。生成プロンプトの優先キーワードに供給する。
    ネットワーク失敗時も空リストを返し、ネタ生成は止めない（fail closed）。"""
    import requests
    seeds = ["japan with kids", "tokyo with a toddler", "japan with a baby",
             "how to travel japan with kids", "what to pack japan with kids",
             "is japan good with kids", "kyoto with kids", "stroller in japan",
             "japan family itinerary", "can you take a baby to japan"]
    qwords = ("how", "what", "can", "do", "does", "is", "are", "when", "where",
              "with kids", "with a baby", "toddler", "stroller", "baby")
    seen, out = set(), []
    for s in seeds:
        try:
            r = requests.get("https://suggestqueries.google.com/complete/search",
                             params={"client": "firefox", "q": s}, timeout=8)
            data = r.json()
            sugg = data[1] if isinstance(data, list) and len(data) > 1 else []
        except Exception:
            continue
        for q in sugg:
            ql = str(q).lower().strip()
            if ql and ql not in seen and any(w in ql for w in qwords):
                seen.add(ql)
                out.append(str(q).strip())
    log.info("ideas: autocompleteから質問キーワード %d件を収集", len(out))
    return out[:max_n]


def refill_topics(state: dict) -> dict:
    cfg = load_settings()
    niche = cfg["niche"]
    buffer = cfg["llm"]["max_topics_buffer"]
    queue = state.setdefault("topics_queue", [])
    if len(queue) >= buffer:
        log.info("topics_queue 十分 (%d件)。スキップ。", len(queue))
        return state

    strat = state.get("strategy", {})
    boost = (strat.get("boost_keywords", []) or []) + mine_question_keywords()
    avoid = strat.get("avoid_keywords", [])
    posted_titles = [p.get("topic", "") for p in state.get("posted", [])][-100:]

    need = buffer - len(queue)
    prompt = f"""You are a content strategist for a Pinterest + Threads account in the niche:
"{niche['name']}" for audience: {niche['audience']}.
Tone: {niche['tone']}.

Generate {need} NEW, specific, search-driven content ideas that foreign travelers
actually search for. Each must be evergreen (not date-bound) and genuinely useful.

Rules:
{chr(10).join("- " + r for r in niche['editorial_rules'])}
- Prioritize these high-performing keywords if natural: {boost or "none yet"}
- Avoid these underperforming themes: {avoid or "none"}
- Do NOT repeat these already-used topics: {posted_titles}

Return ONLY a JSON array. Each item:
{{"topic": "<concise title>", "search_intent": "<what the user wants>",
  "primary_keyword": "<main keyword>", "board_hint": "<which board it fits>"}}"""

    try:
        ideas = generate(prompt, as_json=True)
        if isinstance(ideas, dict):
            ideas = ideas.get("ideas") or list(ideas.values())
        existing = ([str(p.get("topic", "")) for p in state.get("posted", [])]
                    + [str(p.get("article_title", "")) for p in state.get("posted", [])]
                    + [str(q.get("topic", "")) for q in queue])
        added = 0
        for it in ideas:
            if not (isinstance(it, dict) and it.get("topic")):
                continue
            dup = _dup_of(it["topic"], existing)
            if dup:
                log.info("ideas: 生成前dedupeで破棄 '%s'（類似: '%s'）", it["topic"], dup)
                continue
            queue.append(it)
            existing.append(it["topic"])  # 同一バッチ内の相互照合
            added += 1
        log.info("ネタを %d 件追加（dedupe後）。queue=%d", added, len(queue))
    except Exception as e:
        log.error("ネタ生成失敗: %s", e)
    return state


def pop_topic(state: dict):
    queue = state.get("topics_queue", [])
    if not queue:
        return None
    return queue.pop(0)
