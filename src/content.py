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
    # タイトル見出しがページ<h1>と重複する事故をならす（先頭の<h2>/<h3>が記事タイトルそのものなら落とす）
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

WRITING RULES (critical for quality):
- Output PURE HTML only. NEVER use Markdown: no **bold**, no ## headings, no "- " bullets, no backticks. Use <strong>, <em>, <h2>/<h3>, <ul><li>, <table> instead. Any asterisks or hashes are a defect.
- Do NOT repeat the article title as a heading at the start. The page template already shows the title as <h1>. Begin directly with the hook paragraph.
- Open with a 2-3 sentence HOOK naming the reader's specific worry, then promise the answer. NO generic openers (never start with "Planning a trip to Japan involves...") and NO fluffy conclusions (never end with "With a little preparation...").
- Every section must contain at least one concrete specific (a name, number, price in yen, minutes, kg, station, or rule). Delete any sentence with no specific.
- Near the top include a short TL;DR <ul> (3-5 bullets). Include at least one HTML <table> for comparison or quick-reference, but keep tables compact (3-5 rows, 2-4 columns) and genuinely scannable — never a giant data dump. Put nuance in prose, not the table.
- Include an <h2>FAQ</h2> with 5-8 real questions parents search, each with a concise answer. The FAQ and a final one-sentence practical takeaway MUST be present and complete.
- Where an affiliate offer above is genuinely relevant, insert ONE natural CTA link using its exact token, e.g. <a href='{{aff_ID}}'>book family-friendly experiences</a>. Max 3 links total. Do not invent links that aren't listed.
- If you give a price or opening hours, append "(as of 2026, confirm on the official site)".
- NEVER write internal notes, TODOs, editorial scaffolding, or placeholder text (e.g. "(placeholder for ...)", "TODO", "insert link here"). The article must read as clean finished prose for parents.

Produce a JSON object with EXACTLY these fields:
{{
  "article_title": "<SEO title, <=60 chars>",
  "article_html": "<clean HTML body (NO markdown). 1100-1800 words. Start with the hook (do NOT repeat the title). Then a TL;DR <ul>, then sections each with at least one concrete specific, at least one compact HTML <table>, one natural affiliate CTA where relevant, and an <h2>FAQ</h2> with 5-8 <h3> questions. End with one practical takeaway sentence. Use <a href='{{aff_ID}}'>anchor</a> for affiliate links, max 3.>",
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
            m0 = live[0]
            cta = (
                '<p style="background:#fff0f6;border:1px solid #ffe0ee;border-radius:12px;'
                'padding:14px 16px;margin:1.6em 0">'
                f'<a href="{m0["url"]}" rel="nofollow sponsored noopener" target="_blank">'
                f'<strong>{m0.get("cta", "See family-friendly options")} →</strong></a></p>'
            )
            if "<h2>FAQ" in html_now:
                data["article_html"] = html_now.replace("<h2>FAQ", cta + "<h2>FAQ", 1)
            else:
                data["article_html"] = html_now + cta

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
