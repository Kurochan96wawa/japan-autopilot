"""ネタ（トピック）生成。成果データを踏まえてSEO/検索意図の強いネタを量産し、
state の topics_queue に貯める。"""
from __future__ import annotations
from .util import load_settings, log
from .llm import generate
import difflib
import re

# 生成前dedupe（3-3）: タイトルの類似で近似重複トピックを生成前に弾く。標準ライブラリのみ。
_TITLE_STOP = {"the", "a", "an", "in", "on", "at", "for", "with", "and", "to", "of", "your", "you",
               "japan", "japanese", "kids", "kid", "child", "children", "family", "families",
               "travel", "travelling", "traveling", "trip", "guide", "tips", "best", "how", "what",
               "is", "are", "2026", "2025"}


def _title_tokens(t):
    toks = re.findall(r"[a-z0-9]+", (t or "").lower())
    return {w for w in toks if len(w) > 2 and w not in _TITLE_STOP}


# ── 復旧スプリントC (2026-08-21): 概念レベルの重複ガード ───────────────────────
# 2026年8月、上のタイトル類似判定(Jaccard>=0.55 / SequenceMatcher>=0.78)を通り抜けて
# 「医療・健康」6本、「旅館」3本、「パッキング」2本の近接重複が量産された。実測すると
# この11本は1本も弾かれない（_selftest 参照）。原因は、言い換えが効くと表層トークンが
# ほとんど重ならないこと（"child sick" と "family healthcare" と "medical care" は
# 同じ検索意図なのに共通語が無い）。
# そこで表層語を「概念」に正規化してから比較する層を足す。LLM不要・決定的。
_CONCEPT_SYNONYMS = {
    # 医療・健康
    "sick": "health", "illness": "health", "ill": "health", "medical": "health",
    "medicine": "health", "healthcare": "health", "health": "health", "clinic": "health",
    "clinics": "health", "doctor": "health", "doctors": "health", "hospital": "health",
    "hospitals": "health", "pharmacy": "health", "pharmacies": "health",
    "emergency": "health", "emergencies": "health", "fever": "health",
    "care": "health", "treatment": "health", "prescription": "health",
    # 宿・旅館
    "ryokan": "ryokan", "inn": "ryokan", "inns": "ryokan", "onsen": "onsen",
    "hotel": "hotel", "hotels": "hotel", "accommodation": "hotel", "stay": "stay",
    "stays": "stay", "staying": "stay",
    # 荷造り
    "packing": "packing", "pack": "packing", "checklist": "packing",
    "essentials": "packing", "luggage": "luggage", "baggage": "luggage",
    # 乳幼児用品
    "diaper": "babygear", "diapers": "babygear", "nappy": "babygear",
    "nappies": "babygear", "formula": "babygear", "wipes": "babygear",
    "gear": "babygear", "buy": "buy", "buying": "buy", "bought": "buy",
    "shopping": "buy", "purchase": "buy",
    "stroller": "stroller", "strollers": "stroller", "buggy": "stroller",
    "carrier": "carrier", "carriers": "carrier",
    # 移動
    "transport": "transport", "transit": "transport", "subway": "transport",
    "train": "train", "trains": "train", "shinkansen": "shinkansen",
    "rail": "rail", "jr": "rail", "fare": "fare", "fares": "fare",
    # 通信
    "esim": "esim", "esims": "esim", "sim": "esim", "wifi": "esim",
    "connected": "esim", "connectivity": "esim",
    # 食
    "allergy": "allergy", "allergies": "allergy", "sushi": "sushi", "ramen": "ramen",
    "konbini": "konbini", "meals": "food", "eating": "food", "food": "food",
}
# 概念比較で無視する汎用語（サイト全体でほぼ全記事に出るため識別力が無い）。
_CONCEPT_STOP = _TITLE_STOP | {
    "ultimate", "essential", "practical", "need", "know", "parent", "parents",
    "seasonal", "complete", "everything", "things", "guide", "guides", "must",
    "access", "accessing", "navigating", "navigate", "friendly", "proven",
    "should", "when", "where", "why", "who", "get", "gets", "got", "make",
    "making", "use", "using", "into", "from", "about", "over", "under", "day",
    "days", "year", "years", "top", "new", "your", "our", "all", "any", "not",
}


def _concepts(t):
    """タイトルを概念集合に正規化する（年・括弧・ブランド接尾辞を落としてから写像）。"""
    s = re.sub(r"\(.*?\)", " ", (t or "").lower())
    s = re.sub(r"\|.*$", " ", s)
    s = re.sub(r"\b(19|20)\d{2}\b", " ", s)
    out = set()
    for w in re.findall(r"[a-z]+", s):
        if len(w) <= 2 or w in _CONCEPT_STOP:
            continue
        out.add(_CONCEPT_SYNONYMS.get(w, w))
    return out


def _concept_overlap(a, b):
    ca, cb = _concepts(a), _concepts(b)
    if not ca or not cb:
        return 0.0, 0
    inter = ca & cb
    return len(inter) / len(ca | cb), len(inter)


def _too_similar(a, b):
    ta, tb = _title_tokens(a), _title_tokens(b)
    if ta and tb:
        jac = len(ta & tb) / len(ta | tb)
        if jac >= 0.55:
            return True
    if difflib.SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio() >= 0.78:
        return True
    # 概念レベル: 同じ主題を言い換えただけのトピックをここで棄却する。
    #   ・概念Jaccard >= 0.60           → 主題がほぼ一致
    #   ・共通概念2つ以上 かつ >= 0.40  → 主題＋切り口が一致
    jac_c, inter = _concept_overlap(a, b)
    return jac_c >= 0.60 or (inter >= 2 and jac_c >= 0.40)


def _dup_of(topic, existing):
    for e in existing:
        if e and _too_similar(topic, e):
            return e
    return None


def mine_question_keywords(max_n: int = 12) -> list:
    """Googleオートコンプリートから実際に検索されている長尾“質問”を機械収集（無料・鍵不要）。
    競合ゼロの長尾は被リンク無しでも上位を取りやすい。生成プロンプトの優先キーワードに供給する。
    ネットワーク失敗時も空リストを返し、ネタ生成は止めない（fail closed）。"""
    import requests
    seeds = ["japan with kids", "tokyo with a toddler", "japan with a baby",
             "how to travel japan with kids", "what to pack japan with kids",
             "is japan good with kids", "kyoto with kids", "stroller in japan",
             "japan family itinerary", "can you take a baby to japan"]
    qwords = ("how", "what", "can", "do", "does", "is", "are", "when", "where",
              "with kids", "with a baby", "toddler", "stroller", "baby")
    seen, out = set(), []
    for s in seeds:
        try:
            r = requests.get("https://suggestqueries.google.com/complete/search",
                             params={"client": "firefox", "q": s}, timeout=8)
            data = r.json()
            sugg = data[1] if isinstance(data, list) and len(data) > 1 else []
        except Exception:
            continue
        for q in sugg:
            ql = str(q).lower().strip()
            if ql and ql not in seen and any(w in ql for w in qwords):
                seen.add(ql)
                out.append(str(q).strip())
    log.info("ideas: autocompleteから質問キーワード %d件を収集", len(out))
    return out[:max_n]


# Phase 3-7: 新規生成をカバレッジの穴に寄せる優先トピック（指示書 §3-7 の優先順）。
# これらを topics_queue の先頭へ入れ、穴が埋まったら通常のLLM生成にフォールバックする。
_PRIORITY_GAP_TOPICS = [
    {"topic": "Ghibli Museum & Ghibli Park with Kids: Tickets, Timed Entry & What to Expect",
     "primary_keyword": "Ghibli Museum with kids", "board_hint": "Tokyo with Kids"},
    {"topic": "Flying to Japan with Kids: Narita & Haneda Airport Arrival Guide for Families",
     "primary_keyword": "Narita Haneda airport with kids", "board_hint": "Japan with kids"},
    {"topic": "When Your Child Gets Sick in Japan: Pharmacies, Clinics & Travel Insurance for Families",
     "primary_keyword": "child sick in Japan pharmacy clinic insurance", "board_hint": "Japan with kids"},
    {"topic": "Best Family Hotels in Kyoto (2026): Connecting Rooms & Kid-Friendly Stays",
     "primary_keyword": "family hotels Kyoto connecting rooms", "board_hint": "Accommodation Japan"},
    {"topic": "Best Family Hotels in Osaka (2026): Where to Stay with Kids",
     "primary_keyword": "family hotels Osaka kids", "board_hint": "Accommodation Japan"},
    {"topic": "teamLab Planets & Borderless with Kids: A Family Visitor Guide",
     "primary_keyword": "teamLab with kids", "board_hint": "Tokyo with Kids"},
    {"topic": "KidZania Tokyo with Kids: Is It Worth It? A Parent Guide",
     "primary_keyword": "KidZania Tokyo with kids", "board_hint": "Tokyo with Kids"},
    {"topic": "Ueno Zoo with Kids: Pandas, Practical Tips & Nearby Family Spots",
     "primary_keyword": "Ueno Zoo with kids pandas", "board_hint": "Tokyo with Kids"},
    {"topic": "Cherry Blossom Season in Japan with Kids: Family-Friendly Hanami Spots & Tips",
     "primary_keyword": "cherry blossom Japan with kids hanami", "board_hint": "Seasonal Japan"},
    {"topic": "Winter in Japan with Kids: Snow Play, Staying Warm & Family Activities",
     "primary_keyword": "winter Japan with kids snow", "board_hint": "Seasonal Japan"},
]


def _ensure_priority_topics(state: dict, queue: list) -> None:
    """Phase 3-7: 未投稿・未キューの穴トピックをキュー先頭へ(優先順維持)。
    YMYL(子どもの病気/保険)は intent_validator / 週次レビューで人間確認される。"""
    seen = ([str(p.get("article_title", "")) for p in state.get("posted", [])]
            + [str(p.get("topic", "")) for p in state.get("posted", [])]
            + [str(q.get("topic", "")) for q in queue])
    for t in reversed(_PRIORITY_GAP_TOPICS):
        title = t["topic"]
        if any(_too_similar(title, s) for s in seen):
            continue
        queue.insert(0, dict(t))
        seen.insert(0, title)


def refill_topics(state: dict) -> dict:
    cfg = load_settings()
    niche = cfg["niche"]
    buffer = cfg["llm"]["max_topics_buffer"]
    queue = state.setdefault("topics_queue", [])
    _ensure_priority_topics(state, queue)  # Phase 3-7: カバレッジの穴を優先
    if len(queue) >= buffer:
        log.info("topics_queue 十分 (%d件)。スキップ。", len(queue))
        return state

    strat = state.get("strategy", {})
    boost = (strat.get("boost_keywords", []) or []) + mine_question_keywords()
    avoid = strat.get("avoid_keywords", [])
    posted_titles = [p.get("topic", "") for p in state.get("posted", [])][-100:]

    need = buffer - len(queue)
    prompt = f"""You are a content strategist for a Pinterest + Threads account in the niche:
"{niche['name']}" for audience: {niche['audience']}.
Tone: {niche['tone']}.

Generate {need} NEW, specific, search-driven content ideas that foreign travelers
actually search for. Each must be evergreen (not date-bound) and genuinely useful.

Rules:
{chr(10).join("- " + r for r in niche['editorial_rules'])}
- Prioritize these high-performing keywords if natural: {boost or "none yet"}
- Avoid these underperforming themes: {avoid or "none"}
- Do NOT repeat these already-used topics: {posted_titles}

Return ONLY a JSON array. Each item:
{{"topic": "<concise title>", "search_intent": "<what the user wants>",
  "primary_keyword": "<main keyword>", "board_hint": "<which board it fits>"}}"""

    try:
        ideas = generate(prompt, as_json=True)
        if isinstance(ideas, dict):
            ideas = ideas.get("ideas") or list(ideas.values())
        existing = ([str(p.get("topic", "")) for p in state.get("posted", [])]
                    + [str(p.get("article_title", "")) for p in state.get("posted", [])]
                    + [str(q.get("topic", "")) for q in queue])
        added = 0
        for it in ideas:
            if not (isinstance(it, dict) and it.get("topic")):
                continue
            dup = _dup_of(it["topic"], existing)
            if dup:
                log.info("ideas: 生成前dedupeで破棄 '%s'（類似: '%s'）", it["topic"], dup)
                continue
            queue.append(it)
            existing.append(it["topic"])  # 同一バッチ内の相互照合
            added += 1
        log.info("ネタを %d 件追加（dedupe後）。queue=%d", added, len(queue))
    except Exception as e:
        log.error("ネタ生成失敗: %s", e)
    return state


def pop_topic(state: dict):
    queue = state.get("topics_queue", [])
    if not queue:
        return None
    return queue.pop(0)


# 品質ゲートで破棄されたトピックは pop 済みなので、そのままだと永久に失われる。
# failed_attempts を数えつつ queue の先頭へ戻し、MAX_TOPIC_ATTEMPTS 回失敗した
# ものだけを捨てる（作り直しの無限ループとネタ切れの両方を防ぐ）。
MAX_TOPIC_ATTEMPTS = 2


def requeue_topic(state: dict, topic, max_attempts: int = MAX_TOPIC_ATTEMPTS) -> bool:
    """破棄されたトピックを queue の先頭へ戻す。戻したら True、見切って捨てたら False。"""
    if not isinstance(topic, dict) or not topic.get("topic"):
        return False
    t = dict(topic)
    n = int(t.get("failed_attempts") or 0) + 1
    t["failed_attempts"] = n
    if n >= max_attempts:
        log.error("トピックが%d回失敗 → 再キューせず破棄: %s", n, t.get("topic"))
        return False
    state.setdefault("topics_queue", []).insert(0, t)
    log.warning("トピックを再キュー（失敗%d/%d回）: %s", n, max_attempts, t.get("topic"))
    return True


# ── 重複ガードの回帰テスト（外部依存なし。`python -m src.ideas --selftest`） ──
# 素材はすべて実在のタイトル。DUP_GROUPS は 2026年8月に実際に量産されてしまった
# 近接重複（＝旧ガードが1本も弾けなかったもの）、DISTINCT は統合後も併存させたい記事。
_SELFTEST_DUP_GROUPS = [
    ["Japan Healthcare for Kids: Clinics, Pharmacies & Emergencies 2026",
     "Family Healthcare in Japan: What to Do for Kids (2026 Guide)",
     "Accessing Medical Care in Japan for Families (2026): What Parents Need to Know",
     "Child Gets Sick in Japan (2026): A Practical Parent's Guide",
     "Family Health Emergencies in Japan: A 2026 Parent's Guide",
     "Child Sick in Japan? Essential Medical Guide for Families (2026)"],
    ["Ryokan Stays with Kids in Japan: Family Inns & Etiquette (2026)",
     "Ryokan with Kids: Family Stays in Japan (2026 Guide)",
     "Staying in a Ryokan with Kids in Japan (2026)"],
    ["Japan Packing List for Families (2026): Kids' Travel Essentials",
     "Japan with Kids (2026): The Ultimate Seasonal Packing List"],
    ["Buying Baby Diapers, Wipes and Formula in Japan (2026)",
     "Diapers, Formula & Baby Gear in Japan: What to Pack & Buy",
     "Diapers & Formula in Japan: Brands, Sizes & Where to Buy"],
    ["Japan Public Transport with Kids: Fares, Strollers & Facilities",
     "Japan Public Transport with Kids: IC Cards & Strollers (2026)"],
]
_SELFTEST_DISTINCT = [
    "Kid-Friendly Sushi in Japan: A Guide for Young Palates",
    "Child-Friendly Ramen in Japan: Broth Types & Spots",
    "Budget-Friendly Family Meals in Japan (2026)",
    "Kid-Friendly Japanese Meals: Navigating Picky Eaters",
    "Japan Konbini Snacks for Picky Eaters: Kid-Approved",
    "Navigating Food Allergies in Japan with Kids: A Guide",
    "Japan eSIM for Families Compared",
    "Beat Jet Lag with Kids in Japan: Proven Travel Strategies",
    "Beat the Heat: Japan Summer with Kids Safety Guide",
    "Nara Deer Park with Kids: Safety & Fun Tips for Families",
    "Kyoto with a Stroller: Accessible Routes & Kid-Friendly Spots",
    "Stroller-Friendly Tokyo: Navigating the City with Kids",
    "Baby Carriers in Japan: Your Essential Guide for Family Travel",
    "Renting a Car in Japan with Car Seats: Family Travel Guide",
    "Japan Rail Pass with Kids: Is It Worth It for Families?",
    "Shinkansen Oversized Baggage Rules for Families in 2026",
    "Family Onsen Japan: Private Baths & Kid-Friendly Guide",
    "Best Family Hotels in Tokyo with Connecting Rooms",
    "Tokyo Disneyland vs DisneySea for Young Kids",
    "Universal Studios Japan with Kids: Maximizing Family Fun",
    "Japanese Phrases for Families: Essential Travel Guide",
    "Japan Money Guide for Families: Cash, Cards & Budgeting",
]


def _selftest_requeue(fails: list) -> None:
    """破棄トピックの再キュー: 1回目は先頭へ戻り、2回目で捨てられること。"""
    st = {"topics_queue": [{"topic": "B"}]}
    t = {"topic": "A", "primary_keyword": "a"}

    if not requeue_topic(st, t):
        fails.append("1回目の失敗で再キューされなかった")
    q = st["topics_queue"]
    if not q or q[0].get("topic") != "A":
        fails.append("再キューしたトピックが先頭に入っていない")
    elif q[0].get("failed_attempts") != 1:
        fails.append("failed_attempts が 1 になっていない")
    if len(q) != 2 or q[-1].get("topic") != "B":
        fails.append("既存キューが壊れた")
    if t.get("failed_attempts") is not None:
        fails.append("元の dict を破壊的に書き換えている")

    again = pop_topic(st)
    if requeue_topic(st, again):
        fails.append("2回目の失敗でも再キューされてしまった")
    if any(x.get("topic") == "A" for x in st["topics_queue"]):
        fails.append("2回失敗したトピックが queue に残っている")
    if requeue_topic(st, None) or requeue_topic(st, {"topic": ""}):
        fails.append("不正なトピックを再キューしてしまった")


def _selftest() -> int:
    fails = []
    _selftest_requeue(fails)
    for group in _SELFTEST_DUP_GROUPS:
        kept = []
        for title in group:
            dup = _dup_of(title, kept)
            if kept and dup is None:
                fails.append("重複を取りこぼした: " + title)
            if dup is None:
                kept.append(title)
    for i, a in enumerate(_SELFTEST_DISTINCT):
        for b in _SELFTEST_DISTINCT[i + 1:]:
            if _too_similar(a, b):
                fails.append("別トピックを誤って重複判定: " + a + " || " + b)
    for line in fails:
        print("selftest FAIL:", line)
    if fails:
        print("ideas selftest: %d 件失敗" % len(fails))
        return 1
    print("ideas selftest: 重複%d群を全て検出 / 別トピック%d本で誤検出ゼロ / 再キュー OK"
          % (len(_SELFTEST_DUP_GROUPS), len(_SELFTEST_DISTINCT)))
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(_selftest() if "--selftest" in _sys.argv else 0)
