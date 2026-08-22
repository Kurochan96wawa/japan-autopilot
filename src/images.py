"""Pin画像の生成。無料運用: Pexels実写を取得し、Pillowでタイトル帯を載せて
Pinterest推奨の縦長(2:3)に仕上げる。Pexelsキーが無ければ単色背景にフォールバック。

★Fresh Pins対策:
  同一記事(URL)に何度もPinするとき、毎回「別の写真・別の帯デザイン」で画像を作る。
  variant 番号でPexels候補プールから違う写真を選び、帯の位置/色も変える。
  → Pinterestの重複コンテンツ判定(shadowban)を回避し、露出を最大化する。

★本文画像:
  記事本文に差し込む横長(16:9)の実写も Pexels から取得（帯なし・自然な写真）。
  ヒーロー画像と被らないよう skip 枚目以降から選ぶ。
"""
from __future__ import annotations
import json
import os
import pathlib
import io
import textwrap
import requests
from PIL import Image, ImageDraw, ImageFont
from .util import load_settings, log, SITE_DIR

# 帯デザインのバリエーション（variantごとに切替）
_OVERLAY_STYLES = [
    {"pos": "bottom", "rgba": (0, 0, 0, 140), "fg": (255, 255, 255)},
    {"pos": "top",    "rgba": (183, 0, 90, 160), "fg": (255, 255, 255)},
    {"pos": "bottom", "rgba": (20, 40, 80, 165), "fg": (255, 255, 255)},
    {"pos": "center", "rgba": (0, 0, 0, 120), "fg": (255, 255, 255)},
]


# ============================================================
# Phase 2-3: 画像の都市整合（Pexelsクエリに Japan/都市 を必ず含め、
# altが記事の都市と矛盾する写真は後回し=汎用/中立を優先）。
# ============================================================
_JP_CITIES = {
    "tokyo", "kyoto", "osaka", "nara", "yokohama", "nagoya", "hiroshima",
    "fukuoka", "sapporo", "hokkaido", "okinawa", "kobe", "kanazawa", "hakone",
    "nikko", "shizuoka", "okazaki", "hachioji", "kamakura", "kawasaki",
    "chiba", "saitama", "sendai", "nagano", "dotonbori", "shinjuku", "shibuya",
    "asakusa", "arashiyama",
}
_CITY_ALIASES = {
    "dotonbori": "osaka", "shinjuku": "tokyo", "shibuya": "tokyo",
    "asakusa": "tokyo", "arashiyama": "kyoto", "hachioji": "tokyo",
    "kawasaki": "tokyo", "yokohama": "tokyo",
}


# ============================================================
# 使用済み写真の永続記録（run跨ぎの重複防止）
# ============================================================
# 2026-08-22 実測: docs/img に バイト単位で同一の写真が20グループ（最大5記事で同じ1枚）。
# 原因は fetch_body_images に重複回避が無く、Pexelsの検索結果から機械的に
# photos[skip:skip+n] を取っていたこと。近いクエリの記事同士で同じ写真が当たる。
# reimage 側の _take_photo は1run内でしか効かないため、日次生成の積み重ねは防げなかった。
# 使用済みIDをファイルに残し、run を跨いでも同じ写真を選ばないようにする。
_USED_PHOTOS_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "used_photos.json"
_USED_MAX = 4000          # 際限なく増えないよう古いものから捨てる


def load_used_photo_ids() -> list:
    try:
        data = json.loads(_USED_PHOTOS_PATH.read_text(encoding="utf-8"))
        ids = data.get("ids", [])
        return [int(i) for i in ids if str(i).isdigit()]
    except Exception:
        return []          # 壊れていても止めない（fail open: 重複するだけで害は小さい）


def save_used_photo_ids(ids) -> None:
    try:
        seq = [int(i) for i in ids][-_USED_MAX:]
        _USED_PHOTOS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _USED_PHOTOS_PATH.write_text(
            json.dumps({"ids": seq}, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log.error("used_photos保存失敗: %s", e)


def _drop_used(photos: list, used: set) -> list:
    """既に使った写真を候補から除く。全部使用済みなら元のまま返す（画像ゼロを避ける）。"""
    fresh = [p for p in photos if p.get("id") not in used]
    return fresh if fresh else photos


def _cities_in(text: str) -> set:
    t = (text or "").lower()
    return {_CITY_ALIASES.get(c, c) for c in _JP_CITIES if c in t}


def _ensure_japan(query: str) -> str:
    q = (query or "").strip() or "Japan family travel children"
    if "japan" not in q.lower():
        q = q + " Japan"
    return q


def _photo_conflicts(photo: dict, want: set) -> bool:
    """写真altが『記事の都市ではない』日本の都市のみを指すなら True（=場所違い）。"""
    found = _cities_in(photo.get("alt") or "")
    if not found or not want:
        return False
    return found.isdisjoint(want)


def _rank_photos(photos: list, want: set) -> list:
    """記事都市と矛盾しない写真を前に、矛盾する写真を後ろに（順序維持）。"""
    if not want:
        return photos
    good = [p for p in photos if not _photo_conflicts(p, want)]
    bad = [p for p in photos if _photo_conflicts(p, want)]
    return good + bad


def _pexels_photos(query: str, pool: int, orientation: str = "portrait") -> list[dict]:
    query = _ensure_japan(query)
    key = os.environ.get("PEXELS_API_KEY")
    if not key:
        return []
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": key},
            params={"query": query, "orientation": orientation, "per_page": pool},
            timeout=60,
        )
        r.raise_for_status()
        return r.json().get("photos", [])
    except Exception as e:
        log.error("Pexels取得失敗: %s", e)
        return []


def _download(url: str, w: int, h: int) -> Image.Image:
    b = requests.get(url, timeout=60).content
    img = Image.open(io.BytesIO(b)).convert("RGB")
    return _cover_crop(img, w, h)


def _cover_crop(img: Image.Image, w: int, h: int) -> Image.Image:
    src_ratio = img.width / img.height
    dst_ratio = w / h
    if src_ratio > dst_ratio:
        new_h, new_w = h, int(h * src_ratio)
    else:
        new_w, new_h = w, int(w / src_ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left, top = (new_w - w) // 2, (new_h - h) // 2
    return img.crop((left, top, left + w, top + h))


def _font(size: int):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def make_pin_image(slug: str, overlay_text: str, image_query: str, variant: int = 0) -> dict:
    """variant を変えると別写真・別デザインのFresh Pin画像になる。"""
    cfg = load_settings()["images"]
    w, h = cfg["pin_width"], cfg["pin_height"]
    pool = cfg.get("pexels_pool", 10)
    credit = {"photographer": "", "url": ""}

    photos = _pexels_photos(image_query, pool) if cfg["source"] == "pexels" else []
    photos = _rank_photos(photos, _cities_in(image_query + " " + slug))
    if photos:
        # variantごとに違う写真を選ぶ（候補が尽きたら巡回）
        p = photos[variant % len(photos)]
        try:
            base = _download(p["src"]["large2x"], w, h)
            credit = {"photographer": p.get("photographer", ""), "url": p.get("url", "")}
        except Exception as e:
            log.error("画像DL失敗→単色背景: %s", e)
            base = Image.new("RGB", (w, h), (38, 50, 71))
    else:
        base = Image.new("RGB", (w, h), (38, 50, 71))

    if cfg.get("overlay") and overlay_text:
        style = _OVERLAY_STYLES[variant % len(_OVERLAY_STYLES)]
        draw = ImageDraw.Draw(base, "RGBA")
        band_h = int(h * 0.30)
        if style["pos"] == "top":
            y0, y1 = 0, band_h
        elif style["pos"] == "center":
            y0, y1 = (h - band_h) // 2, (h + band_h) // 2
        else:
            y0, y1 = h - band_h, h
        draw.rectangle([0, y0, w, y1], fill=style["rgba"])
        font = _font(int(w * 0.072))
        wrapped = textwrap.fill(overlay_text, width=18)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=8)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (w - tw) // 2
        y = y0 + (band_h - th) // 2
        draw.multiline_text((x, y), wrapped, font=font, fill=style["fg"],
                            spacing=8, align="center")

    img_dir = SITE_DIR / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{slug}.jpg" if variant == 0 else f"{slug}-v{variant}.jpg"
    out_path = img_dir / fname
    base.save(out_path, "JPEG", quality=88)
    log.info("Pin画像生成: %s (variant=%d)", fname, variant)
    return {"path": str(out_path), "rel": f"img/{fname}", "credit": credit}


def fetch_body_images(query: str, slug: str, n: int = 2, skip: int = 1) -> list[dict]:
    """記事本文に差し込む横長(16:9)の実写を n 枚取得して保存（帯なし・自然な写真）。
    skip 枚目以降から選び、冒頭ヒーロー画像と被らないようにする。
    返り値: [{rel, photographer, url, alt}]。Pexels無効/失敗時は空リスト。"""
    cfg = load_settings()["images"]
    if cfg.get("source") != "pexels" or n <= 0:
        return []
    photos = _pexels_photos(query, n + skip + 4, orientation="landscape")
    if not photos:
        return []
    photos = _rank_photos(photos, _cities_in(query + " " + slug))
    used_seq = load_used_photo_ids()
    used = set(used_seq)
    photos = _drop_used(photos, used)          # run跨ぎで同じ写真を選ばない
    img_dir = SITE_DIR / "img"
    img_dir.mkdir(parents=True, exist_ok=True)
    out: list[dict] = []
    for idx, p in enumerate(photos[skip:skip + n]):
        try:
            src = p.get("src", {})
            url = src.get("large") or src.get("large2x") or src.get("original")
            base = _download(url, 1200, 675)  # 16:9
            fname = f"{slug}-body{idx + 1}.jpg"
            base.save(img_dir / fname, "JPEG", quality=86)
            if p.get("id") is not None:
                used_seq.append(p["id"])
            out.append({
                "rel": f"img/{fname}",
                "photographer": p.get("photographer", ""),
                "url": p.get("url", ""),
                "alt": p.get("alt") or query,
            })
        except Exception as e:
            log.error("本文画像DL失敗: %s", e)
    save_used_photo_ids(used_seq)
    log.info("本文画像 %d枚生成: %s（使用済み写真 %d件を記録）", len(out), slug, len(used_seq))
    return out
