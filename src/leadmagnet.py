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
from .leadmagnet_pdf import build_pdf

# 既存のお問い合わせフォームと同じ公開キー（クライアントHTMLに埋め込む前提の公開値）。
WEB3FORMS_KEY = "e0c3512d-69a9-46e8-94a3-61bd2e94bd8b"

PDF_REL = "downloads/japan-with-kids-checklist.pdf"
THANKS_SLUG = "get-the-japan-checklist"

# サンクスページから案内する人気ガイド（実在slug）。
_POPULAR = [
    ("japan-family-itinerary-tokyo-kyoto-osaka-with-young-children", "Tokyo–Kyoto–Osaka itinerary with young kids"),
    ("diapers-formula-baby-gear-in-japan-what-to-pack-buy", "Where to buy diapers & formula in Japan"),
    ("best-family-hotels-tokyo-connecting-rooms", "Best family hotels in Tokyo (compared)"),
    ("japan-public-transport-with-kids-fares-strollers-facilities", "Getting around Japan with kids"),
]


# ---------------- PDF ----------------
def _form_widget(base: str) -> str:
    """メール登録フォーム（Kit/ConvertKit フォーム 9651205 に直結）。
    ダブルオプトイン→確認後に get-the-japan-checklist へリダイレクト（Kit側設定）。
    ck.5.js が非同期でインライン成功表示を担う。base は将来用に残す。"""
    inp = ("width:100%;border:1px solid #ececf1;border-radius:10px;"
           "padding:9px 11px;font:inherit;margin:0")
    btn = ("background:#b8005a;color:#fff;border:0;border-radius:10px;"
           "padding:9px 12px;font-weight:700;cursor:pointer")
    return (
        '<script async src="https://f.convertkit.com/ckjs/ck.5.js"></script>'
        '<div class="widget" id="lead-form-widget" style="background:#fff0f6;border-color:#ffe0ee">'
        '<h4>Free: Japan-with-kids checklist</h4>'
        '<p style="color:#6b7280;font-size:.9rem;margin:.2em 0 .7em">'
        'A pre-departure checklist + a 7-day Tokyo itinerary (PDF). No spam &mdash; unsubscribe anytime.</p>'
        '<form action="https://app.kit.com/forms/9651205/subscriptions" method="post" '
        'class="seva-form formkit-form" data-sv-form="9651205" data-uid="f5350a8d30" '
        'data-format="inline" data-version="5" '
        'style="display:flex;flex-direction:column;gap:8px">'
        f'<input type="email" name="email_address" required placeholder="Your email" style="{inp}">'
        f'<button type="submit" data-element="submit" style="{btn}">Send me the checklist</button>'
        '</form></div>'
    )

def inject_forms(base: str) -> int:
    """docs配下の全ページのサイドバー(aside.side)に登録フォームを冪等注入/更新。
    旧ウィジェット（Web3Forms版）は丸ごと最新（Kit）へ置換する。"""
    widget = _form_widget(base)
    n = 0
    skip = {f"{THANKS_SLUG}.html"}
    old_re = re.compile(
        r'(?:<script async src="https://f.convertkit.com[^"]*"></script>)?'
        r'<div class="widget" id="lead-form-widget".*?</form></div>', re.S)
    for path in SITE_DIR.glob("*.html"):
        if path.name in skip:
            continue
        try:
            html = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "app.kit.com/forms/9651205" in html:
            continue  # 既に最新（Kit）＝冪等スキップ
        if 'id="lead-form-widget"' in html:
            new_html = old_re.sub(lambda _m: widget, html, count=1)
            if new_html != html:
                path.write_text(new_html, encoding="utf-8")
                n += 1
            continue
        if '<aside class="side">' not in html:
            continue
        anchor = '<div class="widget about">'
        idx = html.find(anchor)
        if idx >= 0:
            nxt = html.find('<div class="widget', idx + len(anchor))
            insert_at = nxt if nxt >= 0 else html.find('</aside>', idx)
            html = html[:insert_at] + widget + html[insert_at:]
        else:
            html = html.replace('<aside class="side">', '<aside class="side">' + widget, 1)
        path.write_text(html, encoding="utf-8")
        n += 1
    log.info("リード登録フォーム注入/更新: %dページ", n)
    return n


# ---------------- サンクス／ダウンロードページ ----------------
def build_thanks(base: str) -> None:
    pdf_url = f"{base}/{PDF_REL}?v=20260716"
    pop = "".join(
        f'<li><a href="/{s}">{t}</a></li>' for s, t in _POPULAR
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
        '<p><a class="brand" href="/">little<b>tabi</b></a></p>'
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
        '<p><a href="/">&larr; Back to all guides</a></p>'
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
