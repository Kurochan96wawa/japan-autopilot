"""記事本文 + Pin/Threads用コピーを生成。アフィリリンクを文脈マッチで挿入。"""
from __future__ import annotations
import re
from .util import load_settings, load_affiliates, log
from .llm import generate
from .jp_research import gather_japanese_context

# 記事生成の構造化出力スキーマ（geminiのcontrolled generation用）。
# これを使うと長いHTMLを含んでもAPI側で必ず妥当なJSONにエスケープされ、パース失敗が消える。
_CONTENT_FIELDS = [
    "article_title", "article_html", "meta_description", "pin_title",
    "pin_description", "threads_text", "image_query", "overlay_text",
]
_CONTENT_SCHEMA = {
    "type": "object",
    "properties": {f: {"type": "string"} for f in _CONTENT_FIELDS},
    "required": _CONTENT_FIELDS,
    "propertyOrdering": _CONTENT_FIELDS,
}


def _strip_markdown(html: str) -> str:
    """LLMがHTMLに混ぜがちなMarkdown記法を除去/HTMLへ正規化（**bold**等のAI丸出しを消す）。"""
    if not html:
        return html
    # コードフェンス```を除去
    html = re.sub(r"```[a-zA-Z]*\n?", "", html)
    # **bold** / __bold__ → <strong>
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html, flags=re.S)
    html = re.sub(r"__(.+?)__", r"<strong>\1</strong>", html, flags=re.S)
    # 行頭の見出し記法 ##... を除去（HTMLの<h2>を使うべき）
    html = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", html)
    # 残った孤立アスタリスク/見出し記号を掃除
    html = html.replace("**", "")
    return html.strip()


def _dedupe_title_heading(html: str, title: str) -> str:
    """本文先頭の見出しがページタイトルと実質同じなら除去（h1/h2重複のAI臭対策）。"""
    if not html or not title:
        return html
    norm = lambda s: re.sub(r"[^a-z0-9]+", "", s.lower())
    m = re.match(r"\s*<h([1-3])>(.*?)</h\1>", html, flags=re.S)
    if m and norm(m.group(2)) and norm(m.group(2)) == norm(title):
        return html[m.end():].lstrip()
    return html


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


def _default_program(aff: dict) -> list[dict]:
    """文脈一致が無くても収益機会を取りこぼさないためのデフォルトCTA。
    experiences（Klookの体験・実在リンク）を1つだけ使う。無効なら空。"""
    for p in aff.get("programs", []):
        if p.get("id") == "experiences":
            url = p.get("url", "")
            if url and "REPLACE_WITH" not in url and "example.com" not in url:
                return [p]
    return []


def build_content(topic_item: dict, research: bool = True) -> dict:
    """research=False のとき日本語ソースのグラウンディング検索を省く。
    一括再生成(regen)などで free-tier の 429 連発を避け、API呼び出しを約半減する。
    グラウンディングは“あれば嬉しい”補助情報なので、無くても記事は成立する。"""
    cfg = load_settings()
    niche = cfg["niche"]
    aff = load_affiliates()
    topic = topic_item["topic"]
    keyword = topic_item.get("primary_keyword", topic)
    matched = _match_affiliates(topic, keyword)
    # どの記事も最低1つは自然なCTAが入るように（モネタイズの取りこぼし防止）
    if not matched:
        matched = _default_program(aff)
    jp = gather_japanese_context(topic, keyword) if research else {"facts": "", "sources": []}
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

VOICE & PERSONALITY (this is the most important rule — most AI travel articles read like a
robot reciting a brochure; yours must NOT):
- Write like a warm, funny friend who happens to be a parent and knows Japan. Natural second-person "you" voice. Vary sentence length — some short. Punchy.
- Land the occasional light, knowing joke about real family-travel moments: the 4am jet-lagged toddler, snacks as a bargaining currency, the stroller-vs-carrier debate, a meltdown in front of a vending machine, "are we there yet" on the Shinkansen. Humour should be gentle, relatable and quick — never snarky, never mean, never forced, and never more than a sentence.
- Stay honest: do NOT fabricate first-person experiences or claim "we visited/tested". Keep the warmth in second person ("Picture your 3-year-old...") and wry observation, not invented anecdotes.
- KILL corporate filler. Banned phrases: "the logistics of managing", "can feel daunting", "Understanding ... can significantly ease", "navigating the nuances", "a key consideration", "with careful planning", "ease your travel preparations". If a sentence could appear in any generic brochure, rewrite it with a concrete detail or delete it.

WRITING RULES (critical for quality):
- Output PURE HTML only. NEVER use Markdown: no **bold**, no ## headings, no "- " bullets, no backticks. Use <strong>, <em>, <h2>/<h3>, <ul><li>, <table> instead. Any asterisks or hashes are a defect.
- Do NOT repeat the article title as a heading at the start. The page template already shows the title as <h1>. Begin directly with the hook paragraph.
- ANSWER-FIRST opening (critical for AI search / AI Overviews): the first 1-2 sentences must directly and completely answer the main question in the title, in plain terms a busy parent (or an AI assistant quoting you) can lift verbatim. You may add ONE short, warm, slightly funny touch right after — but the direct answer comes first, not after a scene-setting hook. NO generic openers (never start with "Planning a trip to Japan involves..." or "When planning a family trip..."), NO definitions, NO fluffy conclusions.
- Every section must contain at least one concrete specific (a name, number, price in yen, minutes, kg, station, or rule). Delete any sentence with no specific.
- Near the top include a short TL;DR <ul> (3-5 bullets). Include at least one HTML <table> for comparison or quick-reference, but keep tables compact (3-5 rows, 2-4 columns) and genuinely scannable — never a giant data dump. Put nuance in prose, not the table.
- Include an <h2>FAQ</h2> with 5-8 real questions parents search, each with a concise answer. The FAQ and a final one-sentence practical takeaway MUST be present and complete.
- Where an affiliate offer above is genuinely relevant, insert ONE natural CTA link using its exact token, e.g. <a href='{{aff_ID}}'>rent a stroller in Japan</a>. Max 3 links total. Make the anchor text genuinely helpful, not "click here". Do not invent links that aren't listed.
- If you give a price or opening hours, append "(as of 2026, confirm on the official site)".
- YMYL safety: for any health, safety, medical or allergy guidance (allergies, illness, heat/water safety, medication), be careful and non-alarming, avoid definitive medical claims, and tell readers to consult a doctor or official guidance for their child's specific situation.
- NEVER write internal notes, TODOs, editorial scaffolding, or placeholder text (e.g. "(placeholder for ...)", "TODO", "insert link here"). The article must read as clean finished prose for parents.

Produce a JSON object with EXACTLY these fields:
{{
  "article_title": "<SEO title, <=60 chars. Include the year 2026 where it fits naturally (e.g. '...in 2026' or '(2026)'), since current-year signals lift AI-search citations. Don't force it if it makes the title clunky.>",
  "article_html": "<clean HTML body (NO markdown), in a warm/witty/human voice (NOT robotic). 1100-1800 words. Start with an answer-first opening: directly answer the title question in the first 1-2 sentences, then one quick warm/funny touch (do NOT repeat the title). Then a TL;DR <ul>, then sections each with at least one concrete specific, at least one compact HTML <table>, one natural affiliate CTA where relevant, and an <h2>FAQ</h2> with 5-8 <h3> questions. End with one practical takeaway sentence. Use <a href='{{aff_ID}}'>anchor</a> for affiliate links, max 3.>",
  "meta_description": "<=155 chars",
  "pin_title": "<catchy but honest, <=100 chars>",
  "pin_description": "<keyword-rich, 2-3 sentences, <=480 chars, no hashtag spam, max 3 relevant hashtags>",
  "threads_text": "<=480 chars, conversational, ends with a soft pointer to the full guide>",
  "image_query": "<2-4 word Pexels search query for a great matching Japan photo>",
  "overlay_text": "<short punchy text to put on the pin image, <=40 chars>"
}}
Return ONLY the JSON."""

    data = generate(prompt, as_json=True, schema=_CONTENT_SCHEMA)

    # AI丸出しのMarkdown混入を除去し、タイトル重複見出しをならす
    if isinstance(data.get("article_html"), str):
        data["article_html"] = _strip_markdown(data["article_html"])
        data["article_html"] = _dedupe_title_heading(data["article_html"], data.get("article_title", ""))

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

    # アフィリリンクが本文に1つも入らなかった場合、確実に自然なCTAを1つ付ける（収益機会の取りこぼし防止）
    if matched:
        html_now = data.get("article_html", "")
        live = [m for m in matched if m.get("url") and "REPLACE_WITH" not in m["url"]]
        has_link = any(m["url"] in html_now for m in live)
        if live and not has_link:
        
