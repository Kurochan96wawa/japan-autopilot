"""施策13: マネーページ（比較・ベスト◯◯）の自動生成（無人）。

情報記事ではなく“予約直結”の高CVページ。比較表＋複数アフィリCTAを中心に組み、
情報記事から内部送客する。slugは固定なのでURLが安定し、毎回上書き再生成できる。

設計のキモ:
  * 生成は llm.py のマルチプロバイダ（GitHub Models中心・無料）。
  * 生成物は critic.gate（QAゲート）を通す＝AI丸出し/具体性不足/壊れHTMLを無人で是正。
  * 描画は site.render_article を再利用＝内部リンク/JSON-LD/透明性/rel=sponsored/ヒーロー画像
    まで既存テンプレの全部入りになり、トップ/ハブ/サイトマップにも自動で載る。
  * 既存の大きいファイル(content.py/main.py/site.py)は触らない。`python -m src.moneypages` 単独実行。

実行: GitHub Actions の extras ワークフローから `python -m src.moneypages`。
"""
from __future__ import annotations
import json
import re

from .util import load_settings, load_affiliates, log
from .llm import generate
from . import site, images, critic
from .state import load_state, save_state, record_post


# マネーページ定義。aff_ids は config/affiliates.yaml の program id。
_PAGES = [
    {
        "slug": "best-family-hotels-tokyo-connecting-rooms",
        "title_hint": "Best Family Hotels in Tokyo: Connecting Rooms & Kitchenettes (2026)",
        "primary_keyword": "best family hotels tokyo",
        "board_hint": "Where to Stay in Japan with Kids",
        "aff_ids": ["hotels", "experiences"],
        "brief": ("Compare the best TYPES of Tokyo stays for families with young kids: "
                  "hotels with connecting rooms, apartment/kitchenette hotels (cook for picky "
                  "eaters), hotels near a major JR/metro hub, and stays near Tokyo Disney Resort. "
                  "Cover rough nightly price bands in yen, what makes each good/bad for kids "
                  "(space, laundry, breakfast, cribs, stroller access), and who each suits."),
    },
    {
        "slug": "japan-esim-for-families-compared",
        "title_hint": "Best eSIM for Families Visiting Japan (2026 Comparison)",
        "primary_keyword": "japan esim family",
        "board_hint": "Japan Trip Planning for Families",
        "aff_ids": ["esim"],
        "brief": ("Compare eSIM/data options for a FAMILY visiting Japan: how much data parents "
                  "actually use (maps, translation, kids' videos), hotspot/tethering to share with "
                  "the family's other phones/tablet, validity in days, rough price, and how easy "
                  "setup is for a non-techy parent. Include a clear recommendation by trip length."),
    },
    {
        "slug": "tokyo-disneyland-vs-disneysea-young-kids",
        "title_hint": "Tokyo Disneyland vs DisneySea with Young Kids: Which Park? (2026)",
        "primary_keyword": "tokyo disneyland vs disneysea kids",
        "board_hint": "Things to Do in Japan with Kids",
        "aff_ids": ["experiences", "regional_pass"],
        "brief": ("Help parents of toddlers/under-8s pick between Tokyo Disneyland and DisneySea: "
                  "number of rides with no/low height limit, baby facilities (nursing rooms, "
                  "stroller rental), shade/heat, walking distance, crowds, and a simple one-day "
                  "plan for each with a young child. End with a clear pick by child age."),
    },
]

_FIELDS = ["article_title", "article_html", "meta_description", "pin_title",
           "pin_description", "threads_text", "image_query", "overlay_text"]
_SCHEMA = {"type": "object",
           "properties": {f: {"type": "string"} for f in _FIELDS},
           "required": _FIELDS, "propertyOrdering": _FIELDS}


def _extract_json(text):
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        mm = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
        if mm:
            return json.loads(mm.group(0))
        raise


def _programs_for(spec, aff) -> list:
    by_id = {p.get("id"): p for p in aff.get("programs", [])}
    out = []
    for i in spec["aff_ids"]:
        p = by_id.get(i)
        if p and p.get("url") and "REPLACE_WITH" not in p["url"] and "example.com" not in p["url"]:
            out.append(p)
    return out


def build_money_page(spec: dict) -> dict | None:
    cfg = load_settings()
    niche = cfg["niche"]
    aff = load_affiliates()
    progs = _programs_for(spec, aff)
    aff_block = "\n".join(
        f'- {p["name"]}: CTA "{p["cta"]}" (use token {{aff_{p["id"]}}})' for p in progs
    ) or "None."

    prompt = f"""Write a high-converting COMPARISON / "best of" buyer's guide for parents visiting Japan with kids.

PAGE: {spec['title_hint']}
PRIMARY KEYWORD: {spec['primary_keyword']}
WHAT TO COMPARE: {spec['brief']}
Audience: {niche['audience']}. Voice: warm, witty, human friend who is a parent and knows Japan — never robotic, never clickbait. Honest: never claim to have personally stayed/tested; compare options fairly.

Affiliate offers you SHOULD link (use the exact token for the URL; 2-4 links total, placed where genuinely helpful):
{aff_block}

STRUCTURE (must follow — this is a money page, comparison is the point):
- Answer-first opening: in the first 1-2 sentences give the quick verdict/recommendation a busy parent can act on. One short warm touch after. No generic "Planning a trip..." preamble.
- A "<strong>Quick picks</strong>" TL;DR <ul> (3-5 bullets: best overall / best budget / best for X).
- ONE clear, scannable HTML <table> comparing the options across 3-5 columns (e.g. option, rough price in yen, best for, kid/family notes). Compact, real specifics (yen, minutes, ages), no giant dumps.
- A short section per option with concrete pros/cons and ONE natural affiliate CTA where relevant, e.g. <a href='{{aff_hotels}}'>find family rooms in Tokyo</a>.
- If you give prices/hours, add "(as of 2026, confirm on the official site)".
- An <h2>FAQ</h2> with 5-7 real parent questions + concise answers.
- End with a one-sentence clear recommendation.
PURE HTML only (no markdown, no ** or ##). 1000-1500 words. Do not repeat the page title as an <h1> (the template adds it).

Return ONLY a JSON object with EXACTLY these fields:
{{"article_title": "<=60 chars, include 2026 if natural>",
 "article_html": "<the full comparison page HTML per the structure above>",
 "meta_description": "<=155 chars",
 "pin_title": "<=100 chars, honest>",
 "pin_description": "<=480 chars, keyword-rich, max 3 hashtags>",
 "threads_text": "<=480 chars, soft pointer to the guide>",
 "image_query": "<2-4 word Pexels query>",
 "overlay_text": "<=40 chars punchy pin text>"}}"""

    data = generate(prompt, as_json=True, schema=_SCHEMA)
    if isinstance(data, str):
        data = _extract_json(data)

    # トークン→実URL（content.py と同じ作法）。rel=sponsored は site側で自動付与。
    for p in progs:
        token = f'{{aff_{p["id"]}}}'
        for k in ("article_html", "threads_text", "pin_description"):
            if isinstance(data.get(k), str):
                data[k] = data[k].replace(token, p["url"])
    # 未解決トークンが残ったら # で無効化（壊さない）
    data["article_html"] = re.sub(r"\{aff_[a-z_]+\}", "#", data.get("article_html", ""))

    data["disclosure"] = aff.get("disclosure", "")
    data["board_hint"] = spec["board_hint"]
    data["topic"] = spec["title_hint"]
    data["primary_keyword"] = spec["primary_keyword"]
    data["affiliates_used"] = [p["id"] for p in progs]
    data["has_affiliate"] = bool(progs)
    data["jp_facts"] = ""
    return data


def generate_all() -> int:
    state = load_state()
    made = 0
    existing = {p.get("slug") for p in state.get("posted", [])}
    for spec in _PAGES:
        slug = spec["slug"]
        try:
            c = build_money_page(spec)
        except Exception as e:
            log.error("マネーページ生成失敗(スキップ) %s: %s", slug, e)
            continue
        # QAゲート（無人の品質是正）。reject時はスキップして既存を壊さない。
        try:
            ok, c, _ = critic.gate(c, load_settings(), "")
            if not ok:
                log.warning("マネーページQAゲート非承認→スキップ: %s", slug)
                continue
        except Exception as e:
            log.error("マネーページQAゲート例外(原文採用) %s: %s", slug, e)

        try:
            img = images.make_pin_image(slug, c.get("overlay_text", ""),
                                        c.get("image_query", "Tokyo family travel"), variant=0)
        except Exception as e:
            log.error("マネーページ画像生成失敗(無画像で続行) %s: %s", slug, e)
            img = {"rel": f"img/{slug}.jpg", "credit": {}}
        try:
            canonical = site.render_article(c, img["rel"], img.get("credit", {}), slug)
        except Exception as e:
            log.error("マネーページ描画失敗(スキップ) %s: %s", slug, e)
            continue

        rec = {
            "topic": c["topic"], "slug": slug, "article_title": c["article_title"],
            "primary_keyword": c["primary_keyword"], "image_query": c.get("image_query", ""),
            "board_hint": c.get("board_hint", ""), "affiliates_used": c["affiliates_used"],
            "has_affiliate": c.get("has_affiliate", False), "url": canonical,
            "pins_count": 0, "image_variants": [img["rel"]], "img_hashes": [],
            "last_pin_desc": c.get("pin_description", ""), "repin_times": [],
            "is_money_page": True,
            "quality_score": c.get("critic_score"),
        }
        if slug in existing:
            # 既存recを上書き更新（重複登録を避ける）
            for p in state.get("posted", []):
                if p.get("slug") == slug:
                    p.update(rec)
                    break
        else:
            record_post(state, rec)
        made += 1
        log.info("マネーページ生成: %s", slug)

    site.rebuild_index(state)
    save_state(state)
    log.info("マネーページ完了: %d件", made)
    return made


def main() -> None:
    try:
        generate_all()
    except Exception as e:
        log.error("マネーページ実行失敗: %s", e)


if __name__ == "__main__":
    main()
