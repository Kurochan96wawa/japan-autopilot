# -*- coding: utf-8 -*-
"""無人で出せる信頼シグナル（透明性ベースのE-E-A-T）。
- アフィリ/外部の収益リンクに rel="sponsored nofollow noopener" を自動付与（Google公式の要件）。
- 各記事に“正直な”透明性ノート（AI生成・最終更新日・公式確認の促し）。
- Organization JSON-LD（任意で発行責任者Personを env から1回だけ付与。架空の人間著者は作らない）。
- /how-we-make-guides.html の本文（実際のパイプラインを誇張せず説明）。

重要（是々非々）: レポートの「公式ソースと自動照合済み」バッジは、現状システムが
実際にはやっていないため過大広告になる。透明性＝正直さの原則に従い、
“AI生成・最終更新日・公式で要確認”という実態どおりの文言にしている。
将来 検証KB（Living Content）を実装したら表現を強化できる。
"""
from __future__ import annotations
import os
import re
import json
import datetime

# BASE_CSS に連結して使う追加スタイル
EEAT_CSS = (
    ".verify{font-size:.82rem;color:var(--muted);background:var(--soft);"
    "border:1px solid #ffe0ee;border-radius:12px;padding:11px 15px;margin:1.8em 0}"
    ".verify a{color:inherit;text-decoration:underline}"
    ".related{margin:2.2em 0 0;padding-top:1.2em;border-top:1px solid #eee}"
    ".related h2{font-size:1.1rem;margin:0 0 .5em}"
    ".related ul{margin:0;padding-left:1.1em}"
    ".related li{margin:.25em 0}"
)


def trust_note(verified_at: str = None) -> str:
    """正直な透明性ノート（記事末）。AI生成と最終更新日を明示し、公式確認を促す。"""
    verified_at = verified_at or datetime.date.today().isoformat()
    return (
        "<div class=\"verify\">This guide is written with AI and edited for clarity. "
        f"Last updated: {verified_at}. Prices, opening hours and rules change often — "
        "please confirm details on the official site before you travel. "
        "<a href=\"/how-we-make-guides.html\">How we make these guides &rarr;</a></div>"
    )


def org_jsonld(base: str) -> str:
    """Organization JSON-LD。PUBLISHER_SAMEAS が設定された時だけ発行責任者(Person)を1回付与。"""
    base = (base or "").rstrip("/")
    org = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": "littletabi",
        "url": base,
        "logo": base + "/img/logo.png",
        "description": "AI-assisted, regularly updated family travel guides for visiting Japan with kids.",
    }
    same = [u.strip() for u in os.environ.get("PUBLISHER_SAMEAS", "").split(",") if u.strip()]
    if same:
        org["publisher"] = {
            "@type": "Person",
            "name": os.environ.get("PUBLISHER_NAME", "Editor"),
            "url": base + "/about.html",
            "sameAs": same,
        }
    return ("<script type=\"application/ld+json\">"
            + json.dumps(org, ensure_ascii=False) + "</script>\n")


# 収益（アフィリ）リンクと判定するドメイン断片
AFFILIATE_HINTS = (
    "tp.media", "tpembars", "klook.com", "affiliate.klook", "agoda.com",
    "booking.com", "getyourguide.com", "viator.com", "amazon.", "amzn.",
)


def add_rel_to_affiliates(html: str) -> str:
    """<a> のうちアフィリ系ドメインで rel 未指定/不足のものに sponsored を付与（冪等）。"""
    if not html:
        return html

    def repl(m):
        tag = m.group(0)
        low = tag.lower()
        if not any(d in low for d in AFFILIATE_HINTS):
            return tag
        if "rel=" in low:
            # 既存 rel に sponsored が無ければ補う
            if "sponsored" in low:
                return tag
            return re.sub(r'(?i)rel=("|\')(.*?)\1',
                          lambda r: f'rel="{r.group(2)} sponsored nofollow"', tag, count=1)
        return tag[:-1] + ' rel="sponsored nofollow noopener">'

    return re.sub(r"<a\b[^>]*>", repl, html)


# /how-we-make-guides.html の本文（実態どおり・誇張しない）
HOW_WE_MAKE = (
    "<h1>How We Make These Guides</h1>"
    "<p>We are upfront about how littletabi works. Our guides are produced with AI and "
    "an automated quality process, then published. We do <strong>not</strong> claim to have "
    "personally visited every place, and we do not invent first-hand stories. Instead we focus "
    "on being clear, useful and honest, and on keeping information current.</p>"
    "<ul>"
    "<li><strong>Sourced from public information.</strong> Guidance draws on publicly available "
    "information about transport, food, baby gear, accommodation and attractions in Japan.</li>"
    "<li><strong>Automated quality checks.</strong> Each draft is scored by an AI rubric for "
    "usefulness, structure and clarity; low-scoring drafts are regenerated or held back, not published.</li>"
    "<li><strong>Freshness.</strong> Every guide shows a last-updated date, and we revise guides over time.</li>"
    "<li><strong>Always confirm the specifics.</strong> Prices, opening hours and rules change. "
    "We ask you to verify time-sensitive details on official sites before you travel.</li>"
    "<li><strong>Honest monetisation.</strong> Some links are affiliate links, clearly disclosed, "
    "and marked with rel=\"sponsored\". They never change what we recommend. "
    "See our <a href=\"/disclosure.html\">Affiliate Disclosure</a>.</li>"
    "</ul>"
    "<p>If you spot anything out of date or incorrect, please <a href=\"/contact.html\">tell us</a> — "
    "corrections make these guides better for the next family.</p>"
)
