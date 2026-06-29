"""オーケストレーター。GitHub Actionsから呼ばれる入口。
  python -m src.main daily    → 日次: 新規記事Pin + 既存記事の再Pin(Fresh Pins) + 任意でIG/Threads
  python -m src.main improve  → 週次: 成果集計→戦略更新→週次PDCA(GA4×Pinterest)→shadowban監視
  python -m src.main dry      → APIに投げず動作確認（生成とサイトのみ）
  python -m src.main regen    → 既存記事を現行プロンプト/テンプレで再生成（URL維持・SNS投稿なし）
  python -m src.main rebuild  → LLM不要。サイト再生成＋既存ページへSEO/EEATバックフィルのみ反映

全工程に guards.py の安全装置を通す（落とし穴対策。詳細 PITFALLS.md）。
"""
from __future__ import annotations
import sys
import time
from .util import load_settings, load_affiliates, ensure_dirs, log
from .state import load_state, save_state, record_post, now_iso
from . import ideas, content as content_mod, images, site, guards, rubric, critic
from . import indexnow
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


def _grade_content(topic, cfg, state):
    """1回の生成＋全ゲート評価をまとめて行う。
    返り値: (content, ok, why, risky, score_ok, report)
      ok       … guards.quality_ok（語数/h2など機械チェック）
      risky    … 価格/営業時間/誇大表現の検出（block_risky_phrases時のみ）
      score_ok … AI自己採点ルーブリックが基準点以上か（②）
    生成自体が失敗したら例外を投げる（呼び出し側でNone化）。"""
    rub = cfg.get("quality_rubric", {})
    use_rubric = rub.get("enabled", True)
    min_score = int(rub.get("min_score", 70))

    c = content_mod.build_content(topic)
    guards.add_llm_calls(state, 1)
    ok, why = guards.quality_ok(c, cfg)
    risky = guards.risky_phrases(c.get("article_html", "")) if cfg["safety"]["block_risky_phrases"] else []

    score_ok, rep = True, {}
    if use_rubric and ok:
        # 機械チェックを通った時だけ採点（採点LLM呼び出しの無駄打ちを避ける）
        score_ok, rep = rubric.passes(c, min_score)
        guards.add_llm_calls(state, 1)
    return c, ok, why, risky, score_ok, rep


def _build_quality_content(topic, cfg, state):
    """品質ゲート付きでコンテンツ生成。機械チェック＋AI自己採点(②)で基準未満なら
    1回だけ作り直し、それでも未満なら公開保留(=None)で破棄する。
    生成/解析エラーは握りつぶしてNone（1本の失敗で全体を落とさない）。"""
    rub = cfg.get("quality_rubric", {})
    use_rubric = rub.get("enabled", True)
    min_score = int(rub.get("min_score", 70))

    try:
        c, ok, why, risky, score_ok, rep = _grade_content(topic, cfg, state)
    except Exception as e:
        log.error("コンテンツ生成エラー(スキップ): %s / %s", topic.get("topic"), e)
        return None

    if (not ok or risky or not score_ok) and cfg["llm"].get("quality_self_check", True):
        log.warning("品質NG(ok=%s why=%s risky=%s rubric=%s/%d) → 1回だけ作り直し",
                    ok, why, risky, rep.get("total"), min_score)
        try:
            c, ok, why, risky, score_ok, rep = _grade_content(topic, cfg, state)
        except Exception as e:
            log.error("再生成エラー(初回採用): %s", e)

    if not ok:
        log.error("品質基準を満たせず破棄: %s (%s)", topic.get("topic"), why)
        return None
    if use_rubric and not score_ok:
        # ②ルーブリック2回連続で基準未満 → 公開保留（薄い/AI丸出し記事の流出を止める）
        log.error("ルーブリック%d点未満で公開保留(破棄): %s (total=%s, issues=%s)",
                  min_score, topic.get("topic"), rep.get("total"), rep.get("issues"))
        return None
    if risky:
        # リスク表現(価格/営業時間等)は理想的には避けたいが、旅行記事では頻出。
        # 破棄せず警告のみ（記事ゼロを防ぐ）。古い情報の最終チェックは月次の目視で。
        log.warning("リスク表現あり(掲載は継続): %s / %s", topic.get("topic"), risky)
    # 施策01: マルチエージェントQAゲート。別役割AIが相互批評＋一次ソース事実照合し、
    # revise→自動修正 / reject・低スコア→破棄。例外時は素通し（記事ゼロを防ぐ）。
    try:
        gate_ok, c, crep = critic.gate(c, cfg, c.get("jp_facts", ""))
        guards.add_llm_calls(state, 1)
        if not gate_ok:
            log.error("QAゲートで非承認→破棄: %s (issues=%s)",
                      topic.get("topic"), crep.get("issues"))
            return None
    except Exception as e:
        log.error("QAゲート例外(掲載は継続): %s", e)
    if rep:
        c["quality_score"] = rep.get("total")
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
            "quality_score": c.get("quality_score"),
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
    # ④週次PDCAで needs_refresh が付いたFixableを優先、次にpins_countの少ない順
    candidates.sort(key=lambda p: (not p.get("needs_refresh", False), p.get("pins_count", 1)))
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
            rec["needs_refresh"] = False
            continue
        try:
            content_like = {"pin_title": fresh["pin_title"], "pin_description": fresh["pin_description"]}
            board_id = pin.pick_board(rec, cfg, board_cache)
            tags = aff_tags if rec.get("has_affiliate") else ""
            pin.create_pin(content_like, image_url, rec["url"], board_id, extra_tags=tags)
            rec["pins_count"] = rec.get("pins_count", 1) + 1
            rec.setdefault("repin_times", []).append(now_iso())
            rec["last_pin_desc"] = fresh.get("pin_description", ""); made += 1
            rec["needs_refresh"] = False   # テコ入れ済みなのでフラグを下ろす
        except Exception as e:
            log.error("再Pinエラー: %s", e)
        if i < len(picked) - 1:
            guards.jitter_sleep(interval, jitter)
    return made


def _ping_indexnow(state, cfg, all_urls: bool = False) -> None:
    """Bing等へ新規/更新URLを即時通知（Googleは非対応のためsitemapに任せる）。失敗は無視。"""
    try:
        base = cfg["site"]["base_url"].rstrip("/")
        posts = [p for p in stat
