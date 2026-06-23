"""オーケストレーター。GitHub Actionsから呼ばれる入口。
  python -m src.main daily    → 日次: 新規記事Pin + 既存記事の再Pin(Fresh Pins) + 任意でIG/Threads
  python -m src.main improve  → 週次: 成果集計→戦略更新→shadowban監視
  python -m src.main dry      → APIに投げず動作確認（生成とサイトのみ）

全工程に guards.py の安全装置を通す（落とし穴対策。詳細 PITFALLS.md）。
"""
from __future__ import annotations
import sys
from .util import load_settings, load_affiliates, ensure_dirs, log
from .state import load_state, save_state, record_post, now_iso
from . import ideas, content as content_mod, images, site, guards
from . import publish_pinterest as pin
from . import publish_threads as threads
from . import publish_instagram as insta
from . import analytics


def _recent_image_hashes(state, limit=40):
    hashes = []
    for p in state.get("posted", [])[-limit:]:
        for h in p.get("img_hashes", []):
            hashes.append(h)
    return hashes


def _recent_descriptions(state, limit=40):
    return [p.get("last_pin_desc", "") for p in state.get("posted", [])[-limit:] if p.get("last_pin_desc")]


def _build_quality_content(topic, cfg, state):
    """品質ゲート付きでコンテンツ生成。薄ければ1回だけ作り直す。
    生成/解析エラーは握りつぶしてNone（1本の失敗で全体を落とさない）。"""
    try:
        c = content_mod.build_content(topic)
    except Exception as e:
        log.error("コンテンツ生成エラー(スキップ): %s / %s", topic.get("topic"), e)
        return None
    guards.add_llm_calls(state, 1)
    ok, why = guards.quality_ok(c, cfg)
    risky = guards.risky_phrases(c.get("article_html", "")) if cfg["safety"]["block_risky_phrases"] else []
    if (not ok or risky) and cfg["llm"].get("quality_self_check", True):
        log.warning("品質NG(%s)/リスク%s → 1回だけ作り直し", why, risky)
        try:
            c = content_mod.build_content(topic)
        except Exception as e:
            log.error("再生成エラー(初回採用): %s", e)
        guards.add_llm_calls(state, 1)
        ok, why = guards.quality_ok(c, cfg)
        risky = guards.risky_phrases(c.get("article_html", "")) if cfg["safety"]["block_risky_phrases"] else []
    if not ok:
        log.error("品質基準を満たせず破棄: %s (%s)", topic.get("topic"), why)
        return None
    if risky:
        # リスク表現(価格/営業時間等)は理想的には避けたいが、旅行記事では頻出。
        # 破棄せず警告のみ（記事ゼロを防ぐ）。古い情報の最終チェックは月次の目視で。
        log.warning("リスク表現あり(掲載は継続): %s / %s", topic.get("topic"), risky)
    return c


def _new_articles(state, cfg, aff, board_cache, base_url, dry, cap):
    n_threads = cfg["schedule"]["threads_per_day"]
    n_insta = cfg["schedule"]["instagram_per_day"]
    aff_tags = aff.get("affiliate_hashtags", "")
    jitter = cfg["safety"]["jitter_pct"]
    interval = cfg["schedule"]["min_post_interval_min"]
    recent_imgs = _recent_image_hashes(state)
    made = 0
    for i in range(cap):
        if not guards.budget_ok(state, cfg):
            break
        topic = ideas.pop_topic(state)
        if not topic:
            log.info("ネタ切れ。新規作成を終了。")
            break
        c = _build_quality_content(topic, cfg, state)
        if not c:
            continue
        slug = site.slugify(c["article_title"])
        img = images.make_pin_image(slug, c.get("overlay_text", ""),
                                    c.get("image_query", "Japan family"), variant=0)
        # 重複画像チェック（似すぎなら別variantで作り直し）
        if guards.image_too_similar(img["path"], recent_imgs):
            log.warning("画像が既存と類似 → variant1で作り直し")
            img = images.make_pin_image(slug, c.get("overlay_text", ""), c.get("image_query", "Japan"), variant=1)
        ih = guards.ahash(img["path"]); recent_imgs.append(ih)
        image_url = f"{base_url}/{img['rel']}"
        canonical = site.render_article(c, img["rel"], img["credit"], slug)

        rec = {
            "topic": c["topic"], "slug": slug, "article_title": c["article_title"],
            "primary_keyword": c["primary_keyword"], "image_query": c.get("image_query", ""),
            "board_hint": c.get("board_hint", ""), "affiliates_used": c["affiliates_used"],
            "has_affiliate": c.get("has_affiliate", False), "url": canonical,
            "pins_count": 0, "image_variants": [img["rel"]], "img_hashes": [ih],
            "last_pin_desc": c["pin_description"], "repin_times": [],
        }

        if dry:
            log.info("[dry] Pin/IG/Threadsスキップ: %s", c["article_title"])
            rec["pins_count"] = 1
            record_post(state, rec); made += 1
            continue

        try:
            if cfg["pinterest"]["enabled"]:
                board_id = pin.pick_board(c, cfg, board_cache)
                tags = aff_tags if rec["has_affiliate"] else ""
                created = pin.create_pin(c, image_url, canonical, board_id, extra_tags=tags)
                rec["pinterest_pin_id"] = created.get("id"); rec["pins_count"] = 1
        except Exception as e:
            log.error("Pinterest投稿エラー: %s", e)
        try:
            if cfg["instagram"]["enabled"] and i < n_insta:
                cap_txt = f'{c["pin_title"]}\n\nFull guide → link in bio. {aff_tags if rec["has_affiliate"] else ""}'
                insta.post_image(image_url, cap_txt)
        except Exception as e:
            log.error("Instagram投稿エラー: %s", e)
        try:
            if cfg["threads"]["enabled"] and i < n_threads:
                threads.post_text(c["threads_text"], canonical)
        except Exception as e:
            log.error("Threads投稿エラー: %s", e)

        record_post(state, rec); made += 1
        if i < cap - 1:
            guards.jitter_sleep(interval, jitter)
    return made


def _repin_existing(state, cfg, aff, board_cache, base_url, dry, cap):
    max_pins = cfg["pinterest"]["fresh_pins"]["max_pins_per_article"]
    aff_tags = aff.get("affiliate_hashtags", "")
    jitter = cfg["safety"]["jitter_pct"]
    interval = cfg["schedule"]["min_post_interval_min"]
    recent_imgs = _recent_image_hashes(state)
    recent_desc = _recent_descriptions(state)
    candidates = [p for p in state.get("posted", [])
                  if p.get("pins_count", 1) < max_pins and p.get("slug")
                  and guards.can_repin(p, cfg)]   # 同一URLの間隔ガード
    candidates.sort(key=lambda p: p.get("pins_count", 1))
    made = 0
    picked = candidates[:cap]
    for i, rec in enumerate(picked):
        if not guards.budget_ok(state, cfg):
            break
        variant = rec.get("pins_count", 1)
        fresh = content_mod.fresh_pin_copy(rec["topic"], rec.get("primary_keyword", ""), variant)
        guards.add_llm_calls(state, 1)
        # 説明文が既存と酷似なら使わない
        if guards.text_too_similar(fresh.get("pin_description", ""), recent_desc):
            log.warning("再Pin説明文が酷似 → スキップ: %s", rec["slug"]); continue
        img = images.make_pin_image(rec["slug"], fresh.get("overlay_text", ""),
                                    fresh.get("image_query") or rec.get("image_query", "Japan"),
                                    variant=variant)
        if guards.image_too_similar(img["path"], recent_imgs):
            log.warning("再Pin画像が類似 → スキップ: %s", rec["slug"]); continue
        ih = guards.ahash(img["path"]); recent_imgs.append(ih)
        recent_desc.append(fresh.get("pin_description", ""))
        image_url = f"{base_url}/{img['rel']}"
        rec.setdefault("image_variants", []).append(img["rel"])
        rec.setdefault("img_hashes", []).append(ih)

        if dry:
            log.info("[dry] 再Pinスキップ: %s (v%d)", rec["article_title"], variant)
            rec["pins_count"] = rec.get("pins_count", 1) + 1
            rec.setdefault("repin_times", []).append(now_iso()); made += 1
            continue
        try:
            content_like = {"pin_title": fresh["pin_title"], "pin_description": fresh["pin_description"]}
            board_id = pin.pick_board(rec, cfg, board_cache)
            tags = aff_tags if rec.get("has_affiliate") else ""
            pin.create_pin(content_like, image_url, rec["url"], board_id, extra_tags=tags)
            rec["pins_count"] = rec.get("pins_count", 1) + 1
            rec.setdefault("repin_times", []).append(now_iso())
            rec["last_pin_desc"] = fresh.get("pin_description", ""); made += 1
        except Exception as e:
            log.error("再Pinエラー: %s", e)
        if i < len(picked) - 1:
            guards.jitter_sleep(interval, jitter)
    return made


def run_daily(dry: bool = False) -> None:
    cfg = load_settings(); aff = load_affiliates()
    ensure_dirs(); state = load_state()
    guards.ensure_account_start(state)

    # shadowban検知中は投稿停止（回復まで安全側に）
    if guards.shadowban_paused(state, cfg):
        log.error("shadowban疑いで投稿停止中。weekly改善での回復待ち。")
        save_state(state); return
    if not guards.budget_ok(state, cfg):
        save_state(state); return

    ideas.refill_topics(state); guards.add_llm_calls(state, 1)
    base_url = cfg["site"]["base_url"].rstrip("/")
    board_cache: dict = {}
    new_cap, repin_cap = guards.effective_caps(state, cfg)

    new_n = _new_articles(state, cfg, aff, board_cache, base_url, dry, new_cap)
    repin_n = _repin_existing(state, cfg, aff, board_cache, base_url, dry, repin_cap)

    site.rebuild_index(state); save_state(state)
    log.info("日次完了: 新規%d / 再Pin%d (今日の累計=%d)",
             new_n, repin_n, guards.posts_today(state))


def run_improve() -> None:
    cfg = load_settings(); ensure_dirs(); state = load_state()
    rows = analytics.collect_metrics(state)
    if guards.detect_shadowban(rows, state):
        state.setdefault("performance", {})["shadowban_paused"] = True
    else:
        state.setdefault("performance", {})["shadowban_paused"] = False
    analytics.update_strategy(state); guards.add_llm_calls(state, 1)
    ideas.refill_topics(state); guards.add_llm_calls(state, 1)
    save_state(state); log.info("週次改善完了")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if mode == "daily":
        run_daily(dry=False)
    elif mode == "dry":
        run_daily(dry=True)
    elif mode == "improve":
        run_improve()
    else:
        print("usage: python -m src.main [daily|dry|improve]")
        sys.exit(1)
