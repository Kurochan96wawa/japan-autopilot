"""ネタ（トピック）生成。成果データを踏まえてSEO/検索意図の強いネタを量産し、
state の topics_queue に貯める。"""
from __future__ import annotations
from .util import load_settings, log
from .llm import generate


def refill_topics(state: dict) -> dict:
    cfg = load_settings()
    niche = cfg["niche"]
    buffer = cfg["llm"]["max_topics_buffer"]
    queue = state.setdefault("topics_queue", [])
    if len(queue) >= buffer:
        log.info("topics_queue 十分 (%d件)。スキップ。", len(queue))
        return state

    strat = state.get("strategy", {})
    boost = strat.get("boost_keywords", [])
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
        for it in ideas:
            if isinstance(it, dict) and it.get("topic"):
                queue.append(it)
        log.info("ネタを %d 件追加。queue=%d", len(ideas), len(queue))
    except Exception as e:
        log.error("ネタ生成失敗: %s", e)
    return state


def pop_topic(state: dict):
    queue = state.get("topics_queue", [])
    if not queue:
        return None
    return queue.pop(0)
