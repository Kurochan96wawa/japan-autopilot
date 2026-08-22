"""施策07: 独自データ可視化（無人・外部依存ゼロ・LLM不要）。

“AIが書ける独自性”として、他サイトが持たない自作の図を関連記事に埋め込む。
数値はAIに捏造させず、安定した事実データをハードコード（誠実＆正確）。描画は
純SVG（matplotlib等の重い依存なし）。記事HTMLに冪等で注入し、被引用/被リンク・
滞在時間を狙う独自性シグナルにする。

実行: extras ワークフローの task=dataviz から `python -m src.dataviz`。
注意: 既存記事HTMLへ直接注入する。冪等（id重複チェック）。regen で本文が作り直された
      場合は再実行すればまた入る（無害）。
"""
from __future__ import annotations
from .util import SITE_DIR, log


# ---- データ（事実・安定。出典はキャプションに明記）----
# 日本の紙おむつは概ね体重(kg)でサイズ分け（メーカー間でほぼ共通の目安）。
_DIAPER_ROWS = [
    ("Newborn (NB)", 0, 5),
    ("S", 4, 8),
    ("M", 6, 11),
    ("L", 9, 14),
    ("XL / Big", 12, 17),
    ("XXL / Big+", 15, 28),
]
# 東京の月別 平年気温（最高/最低・℃, 気象庁平年値の概数）。子連れの渡航時期選びに有用。
_TOKYO_TEMP_ROWS = [
    ("Jan", 2, 10), ("Feb", 3, 11), ("Mar", 5, 14), ("Apr", 10, 19),
    ("May", 15, 23), ("Jun", 19, 26), ("Jul", 23, 30), ("Aug", 24, 31),
    ("Sep", 21, 27), ("Oct", 15, 22), ("Nov", 9, 17), ("Dec", 4, 12),
]


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _range_chart(fig_id: str, title: str, unit: str, rows, axis_min: float,
                 axis_max: float, caption: str, note: str,
                 highlight=lambda lo, hi: False) -> str:
    """水平レンジバー・チャートを純SVGで返す（site CSSに依存しない自己完結スタイル）。
    rows=[(label, low, high)]。highlight(lo,hi)=True の行を強調色にする。"""
    W = 680
    pad_l, pad_r, pad_t, pad_b = 130, 24, 14, 30
    row_h, gap = 26, 10
    plot_w = W - pad_l - pad_r
    n = len(rows)
    H = pad_t + n * (row_h + gap) + pad_b + 4

    def x(v):
        v = max(axis_min, min(axis_max, v))
        return pad_l + (v - axis_min) / (axis_max - axis_min) * plot_w

    parts = [
        f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="-apple-system,Segoe UI,Roboto,sans-serif" role="img" '
        f'aria-label="{_esc(title)}">',
        f'<text x="{pad_l}" y="11" font-size="13" font-weight="700" fill="#1f2937">{_esc(title)}</text>',
    ]
    # 縦グリッド＋目盛
    ticks = 5
    for i in range(ticks + 1):
        val = axis_min + (axis_max - axis_min) * i / ticks
        gx = x(val)
        parts.append(f'<line x1="{gx:.1f}" y1="{pad_t+4}" x2="{gx:.1f}" y2="{H-pad_b}" '
                     f'stroke="#eee" stroke-width="1"/>')
        parts.append(f'<text x="{gx:.1f}" y="{H-pad_b+16}" font-size="10" fill="#9aa0aa" '
                     f'text-anchor="middle">{val:g}</text>')
    # バー
    for i, (label, lo, hi) in enumerate(rows):
        y = pad_t + 8 + i * (row_h + gap)
        x0, x1 = x(lo), x(hi)
        color = "#b8005a" if highlight(lo, hi) else "#f4a6c6"
        parts.append(f'<rect x="{x0:.1f}" y="{y:.1f}" width="{max(2,x1-x0):.1f}" height="{row_h-8}" '
                     f'rx="5" fill="{color}"/>')
        parts.append(f'<text x="{pad_l-10}" y="{y+row_h-12:.1f}" font-size="11.5" fill="#1f2937" '
                     f'text-anchor="end">{_esc(label)}</text>')
        parts.append(f'<text x="{x1+6:.1f}" y="{y+row_h-12:.1f}" font-size="10.5" fill="#6b7280">'
                     f'{lo:g}–{hi:g}</text>')
    parts.append(f'<text x="{pad_l+plot_w/2:.1f}" y="{H-2}" font-size="10" fill="#9aa0aa" '
                 f'text-anchor="middle">{_esc(unit)}</text>')
    parts.append('</svg>')
    svg = "".join(parts)

    return (
        f'<figure id="{fig_id}" class="dataviz" style="margin:1.8em 0;padding:14px 16px;'
        f'border:1px solid #ececf1;border-radius:14px;background:#fffdfb">'
        f'{svg}'
        f'<figcaption style="font-size:.78rem;color:#9aa0aa;margin-top:.5em">'
        f'{_esc(caption)} <span style="color:#b8b8c0">· {_esc(note)}</span></figcaption>'
        f'</figure>'
    )


def _inject(slug: str, fig_id: str, fig_html: str) -> bool:
    """docs/<slug>.html に図を冪等で注入。既に同じidがあればスキップ。
    FAQの直前、無ければ bottom 開示の直前に入れる。成功=True。"""
    path = SITE_DIR / f"{slug}.html"
    if not path.exists():
        return False
    try:
        html = path.read_text(encoding="utf-8")
    except Exception:
        return False
    if f'id="{fig_id}"' in html:
        return False  # 冪等
    import re
    m = re.search(r"<h2[^>]*>\s*FAQ", html, re.I)
    if m:
        html = html[:m.start()] + fig_html + html[m.start():]
    elif '<div class="disc bottom"' in html:
        html = html.replace('<div class="disc bottom"', fig_html + '<div class="disc bottom"', 1)
    elif "</article>" in html:
        html = html.replace("</article>", fig_html + "</article>", 1)
    else:
        return False
    path.write_text(html, encoding="utf-8")
    log.info("dataviz注入: %s ← %s", slug, fig_id)
    return True


# 図の定義: どの記事候補に・どの図を入れるか。最初に存在した候補1つに入れる。
def _figures() -> list:
    diaper_fig = _range_chart(
        "fig-diaper-sizes", "Japanese diaper sizes by baby weight", "weight in kilograms (kg)",
        _DIAPER_ROWS, 0, 30,
        "Japanese diapers (Merries, Moony, Pampers Japan, GOO.N) are sized mainly by weight.",
        "Approximate, typical ranges — confirm the exact kg range on each pack.",
    )
    temp_fig = _range_chart(
        "fig-tokyo-temps", "Tokyo monthly temperatures (daily low–high)", "temperature in °C",
        _TOKYO_TEMP_ROWS, -5, 35,
        "Comfortable family-travel months sit roughly in the 10–25°C band (spring & autumn).",
        "Approx. climate normals · °C — plan for heat in Jul–Aug and cold in Jan–Feb.",
        highlight=lambda lo, hi: lo >= 10 and hi <= 26,
    )
    return [
        (["diapers-formula-in-japan-brands-sizes-where-to-buy",
          "diapers-formula-baby-gear-in-japan-what-to-pack-buy"], "fig-diaper-sizes", diaper_fig),
        (["beat-the-heat-japan-summer-with-kids-safety-guide",
          "japan-family-itinerary-tokyo-kyoto-osaka-with-young-children",
          "best-time-to-visit-japan-with-kids-season-by-season"], "fig-tokyo-temps", temp_fig),
    ]


def run() -> int:
    made = 0
    for candidates, fig_id, fig_html in _figures():
        for slug in candidates:
            if _inject(slug, fig_id, fig_html):
                made += 1
                break  # 1図につき最初に存在した記事1本だけに入れる
    log.info("dataviz完了: %d図を注入", made)
    return made


def main() -> None:
    try:
        run()
    except Exception as e:
        log.error("dataviz実行失敗: %s", e)


if __name__ == "__main__":
    main()
