"""記事本文 + Pin/Threads用コピーを生成。アフィリリンクを文脈マッチで挿入。"""
from __future__ import annotations
from .util import load_settings, load_affiliates, log
from .llm import generate
from .jp_research import gather_japanese_context


def _match_affiliates(topic: str, keyword: str) -> list[dict]:
    aff = load_affiliates()
    cfg = load_settings()
    text = f"{topic} {keyword}".lower()
    check = cfg.get("safety", {}).get("check_affiliate_links", True)
    matched = []
    for p in aff.get("programs", []):
        if any(k.lower() in text for k in p.get("keywords", [])):
            url = p.get("url", "")
            # 未設定(placeholder)や死んだリンクは記事に入れない（赤信号回避）
            if check and ("REPLACE_WITH" in url or "example.com" in url):
                continue
            matched.append(p)
    # 最大3件に絞る（過剰なリンクはスパム判定/UX悪化）
    return matched[:3]


def build_content(topic_item: dict) -> dict:
    cfg = load_settings()
    niche = cfg["niche"]
    aff = load_affiliates()
    topic = topic_item["topic"]
    keyword = topic_item.get("primary_keyword", topic)
    matched = _match_affiliates(topic, keyword)
    jp = gather_japanese_context(topic, keyword)
    jp_block = ""
    if jp.get("facts"):
        jp_block = (
            "\n\nJAPANESE-SOURCE FACTS (rarely available in English - translate & synthesise "
            "ACCURATELY in your own words; DO NOT copy verbatim; weave these concrete specifics in; "
            "if you give a price or opening hours, add: as of 2026, confirm on the official site):\n"
            + jp["facts"]
        )

    aff_block = "\n".join(
        f'- {m["name"]}: CTA "{m["cta"]}" (url placeholder: {{aff_{m["id"]}}})'
        for m in matched
    ) or "None — write a pure informational article with no product links."

    prompt = f"""Write content for the topic: "{topic}".
Niche: {niche['name']}. Audience: {niche['audience']}. Tone: {niche['tone']}.
Persona of reader: {niche.get('persona', '')}
Positioning (how we beat big media): {niche.get('positioning', '')}
Language: {niche['language']}.{jp_block}

Editorial rules (MUST follow):
{chr(10).join("- " + r for r in niche['editorial_rules'])}

You may naturally reference these affiliate offers where genuinely helpful
(use the exact placeholder tokens for URLs):
{aff_block}

Produce a JSON object with EXACTLY these fields:
{{
  "article_title": "<SEO title, <=60 chars>",
  "article_html": "<clean HTML body: <h2>/<p>/<ul>. 900-1500 words, accurate, useful. Insert affiliate CTAs as <a href='{{aff_ID}}'>anchor</a> only where natural, max 3.>",
  "meta_description": "<=155 chars",
  "pin_title": "<catchy but honest, <=100 chars>",
  "pin_description": "<keyword-rich, 2-3 sentences, <=480 chars, no hashtag spam, max 3 relevant hashtags>",
  "threads_text": "<=480 chars, conversational, ends with a soft pointer to the full guide>",
  "image_query": "<2-4 word Pexels search query for a great matching Japan photo>",
  "overlay_text": "<short punchy text to put on the pin image, <=40 chars>"
}}
Return ONLY the JSON."""

    data = generate(prompt, as_json=True)

    # プレースホルダを実リンクに置換（未設定ならリンクを除去）
    def replace_links(s: str) -> str:
        for m in matched:
            token = f'{{aff_{m["id"]}}}'
            url = m.get("url", "")
            if url and "REPLACE_WITH" not in url:
                s = s.replace(token, url)
            else:
                # 未承認リンクは # にして無効化（記事は壊さない）
                s = s.replace(token, "#")
        return s

    for k in ("article_html", "threads_text", "pin_description"):
        if k in data and isinstance(data[k], str):
            data[k] = replace_links(data[k])

    data["disclosure"] = aff.get("disclosure", "")
    data["jp_sources"] = jp.get("sources", [])
    data["topic"] = topic
    data["primary_keyword"] = keyword
    data["board_hint"] = topic_item.get("board_hint", "")
    data["affiliates_used"] = [m["id"] for m in matched]
    data["has_affiliate"] = bool(matched)
    log.info("コンテンツ生成完了: %s (aff=%s)", topic, data["affiliates_used"])
    return data


def fresh_pin_copy(topic: str, primary_keyword: str, variant: int) -> dict:
    """既存記事を再Pinするとき用の“新しい文面・新しい画像クエリ”を生成。
    同じ記事でも切り口を変えることで Fresh Pin として扱われる。"""
    cfg = load_settings()
    niche = cfg["niche"]
    prompt = f"""For an existing article about "{topic}" (keyword: {primary_keyword}),
write a FRESH Pinterest pin (angle #{variant + 1}, different hook from previous pins).
Niche: {niche['name']}. Audience: {niche['audience']}. Tone: {niche['tone']}.
Return ONLY JSON:
{{"pin_title": "<=100 chars, new angle>",
  "pin_description": "<keyword-rich, 2-3 sentences, <=480 chars, max 3 hashtags>",
  "overlay_text": "<=40 chars punchy text for the image>",
  "image_query": "<2-4 word Pexels query, different scene if possible>"}}"""
    try:
        d = generate(prompt, as_json=True)
        return d
    except Exception as e:
        log.error("fresh_pin_copy失敗: %s", e)
        return {"pin_title": topic, "pin_description": topic,
                "overlay_text": topic[:40], "image_query": "Japan family travel"}
