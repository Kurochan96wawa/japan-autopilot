"""施策14: メール基盤＋リードマグネット（無人・新規アカウント不要）。

既存のWeb3Formsフォーム基盤（お問い合わせで使用中の公開キー）を再利用し、
  1) リードマグネットPDF（出発前チェックリスト＋7日東京モデル旅程）を reportlab で生成、
  2) 全記事＋トップのサイドバーに“メール登録フォーム widget”を冪等で注入、
  3) 送信後に着地する サンクス／ダウンロードページ を生成する。
送信内容は運営者のメールに届く（Web3Forms）。将来ESP(Kit/MailerLite等)へ差し替え可能。

実行: extras ワークフロー task=leadmagnet（即時）。日次でも復元したい場合は daily.yml に
      `python -m src.leadmagnet` を1ステップ足す（regenで本文が作り直されてもフォームが戻る）。
注意: 既存記事HTMLへ直接注入（冪等）。サンクスページは byline 入りなので _migrate_legacy に潰されない。
"""
from __future__ import annotations
import os
import re

from .util import load_settings, SITE_DIR, log

# 既存のお問い合わせフォームと同じ公開キー（クライアントHTMLに埋め込む前提の公開値）。
WEB3FORMS_KEY = "e0c3512d-69a9-46e8-94a3-61bd2e94bd8b"

PDF_REL = "downloads/japan-with-kids-checklist.pdf"
THANKS_SLUG = "get-the-japan-checklist"

# サンクスページから案内する人気ガイド（実在slug）。
_POPULAR = [
    ("japan-family-itinerary-tokyo-kyoto-osaka-with-young-children", "Tokyo–Kyoto–Osaka itinerary with young kids"),
    ("diapers-formula-in-japan-brands-sizes-where-to-buy", "Where to buy diapers & formula in Japan"),
    ("best-family-hotels-tokyo-connecting-rooms", "Best family hotels in Tokyo (compared)"),
    ("japan-public-transport-with-kids-fares-strollers-tips", "Getting around Japan with kids"),
]


# ---------------- PDF ----------------
def build_pdf(path) -> bool:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                        ListFlowable, ListItem, HRFlowable)
    except Exception as e:
        log.error("reportlab未導入のためPDF生成スキップ: %s", e)
        return False

    accent = colors.HexColor("#b8005a")
    ink = colors.HexColor("#1f2937")
    muted = colors.HexColor("#6b7280")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=accent, fontSize=22, spaceAfter=4, leading=26)
    sub = ParagraphStyle("sub", parent=ss["Normal"], textColor=muted, fontSize=10.5, spaceAfter=14)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=ink, fontSize=13.5, spaceBefore=12, spaceAfter=4)
    body = ParagraphStyle("body", parent=ss["Normal"], textColor=ink, fontSize=10.3, leading=15)
    item = ParagraphStyle("item", parent=body, leftIndent=2)
    foot = ParagraphStyle("foot", parent=ss["Normal"], textColor=muted, fontSize=8)

    def checklist(items):
        return ListFlowable(
            [ListItem(Paragraph(t, item), value="☐", leftIndent=14) for t in items],
            bulletType="bullet", start="☐", bulletColor=accent, bulletFontSize=11,
        )

    story = []
    story.append(Paragraph("Japan With Kids", h1))
    story.append(Paragraph("Pre-Departure Checklist &amp; a 7-Day Tokyo Itinerary &middot; a free guide from littletabi.com", sub))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#ffe0ee")))

    story.append(Paragraph("Pre-departure checklist", h2))
    story.append(Paragraph("Documents &amp; money", body))
    story.append(checklist([
        "Passports valid 6+ months; check if your nationality needs a visa",
        "Print/screenshot hotel bookings, flights and any pre-booked tickets",
        "A little cash in yen for day one (many small shops are cash-only)",
        "Travel/health insurance that covers your kids",
        "An IC card plan (Suica/PASMO/ICOCA) for easy train tap-and-go",
    ]))
    story.append(Paragraph("Health &amp; safety", body))
    story.append(checklist([
        "Any regular medicines (in original packaging) + a small first-aid kit",
        "Your child's usual fever/pain medicine — brands differ in Japan",
        "Note the nearest clinic/pharmacy to your hotel; save emergency 119",
        "For allergies: a translated allergy card to show at restaurants",
    ]))
    story.append(Paragraph("Packing for kids", body))
    story.append(checklist([
        "A day or two of diapers/formula (then buy locally — it's everywhere)",
        "Lightweight, foldable stroller or a carrier for crowded stations",
        "Snacks for the plane and the inevitable 'are we there yet' moments",
        "Refillable water bottles; a change of clothes in your day bag",
    ]))
    story.append(Paragraph("Tech &amp; connectivity", body))
    story.append(checklist([
        "An eSIM or pocket Wi-Fi sorted before you land (maps + translation)",
        "Offline maps downloaded; Google Translate language pack saved",
        "Power bank + the right plug (Japan is Type A, 100V)",
    ]))

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("A simple 7-day Tokyo itinerary (with young kids)", h2))
    itin = [
        ("Day 1 — Arrive &amp; settle", "Land, grab IC cards, check in, gentle stroll + konbini dinner. Early night to beat jet lag."),
        ("Day 2 — Asakusa &amp; river", "Senso-ji, snacks on Nakamise, then an easy Sumida River boat. Stroller-friendly and visual for kids."),
        ("Day 3 — Ueno", "Ueno Zoo + a wide park to run around. Pick one museum only; leave buffer for naps."),
        ("Day 4 — teamLab + bay", "Book teamLab tickets ahead. Afternoon by the bay; keep it light after a big morning."),
        ("Day 5 — Disney or DisneySea", "One park, one day. Rent a stroller at the gate, plan around a midday rest."),
        ("Day 6 — Shibuya/Harajuku slow day", "Crossing, a themed cafe, gacha machines. Short hops; lots of snack breaks."),
        ("Day 7 — Flex &amp; fly", "Buffer for a meltdown-free morning, last-minute shopping, head to the airport early."),
    ]
    for t, d in itin:
        story.append(Paragraph("<b>%s.</b> %s" % (t, d), body))
        story.append(Spacer(1, 2))

    story.append(Spacer(1, 5 * mm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#ffe0ee")))
    story.append(Paragraph(
        "Made with care by littletabi.com — honest, practical guides for families visiting Japan, "
        "written with AI and an automated quality process. Prices, hours and rules change: please "
        "confirm details on official sites before you travel. © 2026 littletabi.", foot))

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        SimpleDocTemplate(str(path), pagesize=A4,
                          topMargin=18 * mm, bottomMargin=16 * mm,
                          leftMargin=18 * mm, rightMargin=18 * mm,
                          title="Japan With Kids — Checklist & Itinerary",
                          author="littletabi.com").build(story)
        log.info("リードマグネットPDF生成: %s", path)
        return True
    except Exception as e:
        log.error("PDF生成失敗: %s", e)
        return False


# ---------------- フォーム widget（サイドバー注入用）----------------
def _form_widget(base: str) -> str:
    thanks = f"{base}/{THANKS_SLUG}.html"
    inp = ("width:100%;border:1px solid #ececf1;border-radius:10px;"
           "padding:9px 11px;font:inherit;margin:0")
    btn = ("background:#b8005a;color:#fff;border:0;border-radius:10px;"
           "padding:9px 12px;font-weight:700;cursor:pointer")
    return (
        '<div class="widget" id="lead-form-widget" style="background:#fff0f6;border-color:#ffe0ee">'
        '<h4>Free: Japan-with-kids checklist</h4>'
        '<p style="color:#6b7280;font-size:.9rem;margin:.2em 0 .7em">'
        'A pre-departure checklist + a 7-day Tokyo itinerary (PDF). No spam — unsubscribe anytime.</p>'
        '<form action="https://api.web3forms.com/submit" method="POST" '
        'style="display:flex;flex-direction:column;gap:8px">'
        f'<input type="hidden" name="access_key" value="{WEB3FORMS_KEY}">'
        '<input type="hidden" name="subject" value="New checklist signup — littletabi">'
        '<input type="hidden" name="from_name" value="littletabi lead magnet">'
        f'<input type="hidden" name="redirect" value="{thanks}">'
        '<input type="checkbox" name="botcheck" style="display:none" tabindex="-1" autocomplete="off">'
        f'<input type="email" name="email" required placeholder="Your email" style="{inp}">'
        f'<button type="submit" style="{btn}">Send me the checklist</button>'
        '</form></div>'
    )


def inject_forms(base: str) -> int:
    """docs配下の全ページのサイドバー(aside.side)に登録フォームを冪等注入。"""
    widget = _form_widget(base)
    n = 0
    skip = {f"{THANKS_SLUG}.html"}
    for path in SITE_DIR.glob("*.html"):
        if path.name in skip:
            continue
        try:
            html = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if 'id="lead-form-widget"' in html or '<aside class="side">' not in html:
            continue
        # About widgetの直後に入れる（無ければ aside 先頭）
        anchor = '<div class="widget about">'
        idx = html.find(anchor)
        if idx >= 0:
            end = html.find('</div>', idx)
            # aboutウィジェットは入れ子pがあるので、ウィジェット閉じを探す（次の<div class="widget"）
            nxt = html.find('<div class="widget', idx + len(anchor))
            insert_at = nxt if nxt >= 0 else html.find('</aside>', idx)
            html = html[:insert_at] + widget + html[insert_at:]
        else:
            html = html.replace('<aside class="side">', '<aside class="side">' + widget, 1)
        path.write_text(html, encoding="utf-8")
        n += 1
    log.info("リード登録フォーム注入: %dページ", n)
    return n


# ---------------- サンクス／ダウンロードページ ----------------
def build_thanks(base: str) -> None:
    pdf_url = f"{base}/{PDF_REL}"
    pop = "".join(
        f'<li><a href="/{s}.html">{t}</a></li>' for s, t in _POPULAR
    )
    inner = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Your Japan-with-kids checklist | littletabi</title>'
        '<meta name="robots" content="noindex">'
        '<style>body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#1f2937;'
        'background:#fffdfb;margin:0;line-height:1.7}a{color:#b8005a}'
        '.wrap{max-width:680px;margin:0 auto;padding:24px 20px}'
        '.brand{font-weight:800;font-size:1.3rem;color:#1f2937;text-decoration:none}.brand b{color:#b8005a}'
        '.btn{display:inline-block;background:#b8005a;color:#fff;padding:13px 22px;border-radius:12px;'
        'font-weight:700;text-decoration:none;margin:8px 0 4px}'
        '.card{background:#fff;border:1px solid #ececf1;border-radius:16px;padding:22px 24px;margin:18px 0}'
        '.byline{font-size:.84rem;color:#6b7280}</style></head><body>'
        '<div class="wrap">'
        '<p><a class="brand" href="/index.html">little<b>tabi</b></a></p>'
        '<article class="post">'
        '<h1>Thank you — here is your checklist!</h1>'
        '<p class="byline">By the littletabi editors</p>'
        '<div class="card">'
        '<p>Your free <strong>Japan With Kids: Pre-Departure Checklist &amp; 7-Day Tokyo Itinerary</strong> '
        'is ready. Tap below to open or save the PDF.</p>'
        f'<a class="btn" href="{pdf_url}" download>Download the PDF &darr;</a>'
        '<p class="byline">If the download didn\'t start, '
        f'<a href="{pdf_url}">click here</a>.</p>'
        '</div>'
        '<h2>Read next</h2><ul>' + pop + '</ul>'
        '<p><a href="/index.html">&larr; Back to all guides</a></p>'
        '</article></div></body></html>'
    )
    (SITE_DIR / f"{THANKS_SLUG}.html").write_text(inner, encoding="utf-8")
    log.info("サンクス/ダウンロードページ生成: %s.html", THANKS_SLUG)


def run() -> None:
    cfg = load_settings()
    base = cfg["site"]["base_url"].rstrip("/")
    build_pdf(SITE_DIR / PDF_REL)
    build_thanks(base)
    inject_forms(base)
    log.info("リードマグネット設置 完了")


def main() -> None:
    try:
        run()
    except Exception as e:
        log.error("リードマグネット実行失敗: %s", e)


if __name__ == "__main__":
    main()
