"""防御層(guards): ネット上で報告されている自動運用の典型的な落とし穴を潰すための関数群。
各関数は main から呼ばれ、危険な投稿を未然に止める／安全側に倒す。

カバーする落とし穴（詳細は PITFALLS.md）:
  - 投稿しすぎ／速すぎ（Pinterest: 1日5〜15, 1時間25〜30が上限の目安）
  - 機械的な等間隔投稿（人間らしくジッターを入れる）
  - 重複コンテンツ（同一/類似画像・説明文・同一URL連投）
  - 死んだリンク／薄い記事（shadowban・Google低品質判定の主因）
  - 古くなる情報（価格・営業時間など）の混入
  - shadowban（インプレッション急落）の見逃し
  - LLM/APIのコスト暴走
"""
from __future__ import annotations
import re
import time
import random
import hashlib
import datetime as dt
import requests
from PIL import Image
from .util import log


# ---------- レート制御 ----------
def posts_today(state: dict) -> int:
    today = dt.date.today().isoformat()
    n = 0
    for p in state.get("posted", []):
        for ts in [p.get("posted_at", "")] + p.get("repin_times", []):
            if ts.startswith(today):
                n += 1
    return n


def daily_cap_remaining(state: dict, cfg: dict) -> int:
    hard = cfg["safety"]["max_pins_per_day_hard"]
    return max(0, hard - posts_today(state))


def jitter_sleep(base_min: int, jitter_pct: int):
    """等間隔を避けて人間らしくする。base_min分 ± jitter_pct%。"""
    base = base_min * 60
    delta = base * (jitter_pct / 100.0)
    secs = max(60, base + random.uniform(-delta, delta))
    log.info("ジッター待機: %.1f分", secs / 60)
    time.sleep(secs)


# ---------- 重複検出 ----------
def ahash(path: str) -> str:
    """簡易perceptual hash（8x8平均）。類似画像の連投を検出。"""
    try:
        img = Image.open(path).convert("L").resize((8, 8))
        px = list(img.getdata())
        avg = sum(px) / len(px)
        bits = "".join("1" if p > avg else "0" for p in px)
        return f"{int(bits, 2):016x}"
    except Exception:
        return hashlib.md5(path.encode()).hexdigest()[:16]


def _hamming(a: str, b: str) -> int:
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except Exception:
        return 64


def image_too_similar(path: str, recent_hashes: list[str], threshold: int = 6) -> bool:
    h = ahash(path)
    return any(_hamming(h, r) <= threshold for r in recent_hashes)


def text_too_similar(text: str, recent: list[str], threshold: float = 0.85) -> bool:
    """Jaccard類似でほぼ同一の説明文を弾く。"""
    def toks(s): return set(re.findall(r"\w+", s.lower()))
    t = toks(text)
    if not t:
        return False
    for r in recent:
        rt = toks(r)
        if not rt:
            continue
        j = len(t & rt) / len(t | rt)
        if j >= threshold:
            return True
    return False


def can_repin(rec: dict, cfg: dict) -> bool:
    """同一URLの再Pinは一定日数あける（連投によるspam判定回避）。"""
    min_days = cfg["safety"]["min_days_between_repins"]
    times = rec.get("repin_times", []) + [rec.get("posted_at", "")]
    times = [t for t in times if t]
    if not times:
        return True
    last = max(times)
    try:
        last_d = dt.datetime.fromisoformat(last).date()
    except Exception:
        return True
    return (dt.date.today() - last_d).days >= min_days


# ---------- 品質ゲート（薄い記事＝Google低品質/Pinterest不信の主因）----------
def quality_ok(content: dict, cfg: dict) -> tuple[bool, str]:
    body = re.sub(r"<[^>]+>", " ", content.get("article_html", ""))
    words = len(body.split())
    minw = cfg["safety"]["min_article_words"]
    if words < minw:
        return False, f"記事が薄い({words}語 < {minw})"
    if content.get("article_html", "").count("<h2") < 1:
        return False, "見出し(h2)が無い"
    if not content.get("pin_title") or not content.get("pin_description"):
        return False, "Pin文面が欠落"
    return True, "ok"


# ---------- 古くなる情報・誇大表現のサニタイズ ----------
_RISKY = [
    (re.compile(r"¥\s?\d[\d,]{2,}|\$\s?\d+|\d+\s?(yen|usd)", re.I), "具体的な価格"),
    (re.compile(r"\b(open|closes?|hours?)\b.*\b\d{1,2}\s?(am|pm|:\d{2})", re.I), "具体的な営業時間"),
    (re.compile(r"\b(guaranteed?|100%|best ever|never fails)\b", re.I), "誇大表現"),
]


def risky_phrases(text: str) -> list[str]:
    found = []
    for rx, label in _RISKY:
        if rx.search(text or ""):
            found.append(label)
    return found


# ---------- リンク死活（死んだ/リダイレクトのアフィリは赤信号）----------
def link_alive(url: str, timeout: int = 15) -> bool:
    if not url or url.startswith("#") or "REPLACE_WITH" in url or "example.com" in url:
        return False
    try:
        r = requests.head(url, allow_redirects=True, timeout=timeout)
        if r.status_code >= 400:
            r = requests.get(url, timeout=timeout, stream=True)
        return r.status_code < 400
    except Exception as e:
        log.warning("リンク死活NG %s: %s", url, e)
        return False


# ---------- shadowban検知（インプレッション急落を見張る）----------
def detect_shadowban(metrics_rows: list[dict], state: dict) -> bool:
    """直近のインプレッション合計が、ベースラインの30%未満なら警告。"""
    total = sum(r.get("impressions", 0) for r in metrics_rows)
    perf = state.setdefault("performance", {})
    baseline = perf.get("impression_baseline", 0)
    if baseline and total < baseline * 0.3 and baseline > 50:
        log.error("⚠️ shadowban疑い: imp=%d (baseline=%d)", total, baseline)
        return True
    # ベースラインを緩やかに更新（指数移動平均）
    perf["impression_baseline"] = int((baseline * 0.7 + total * 0.3) if baseline else total)
    return False


# ---------- LLM/APIコスト管理 ----------
def usage_this_month(state: dict) -> dict:
    month = dt.date.today().strftime("%Y-%m")
    u = state.setdefault("usage", {})
    if u.get("month") != month:
        u.update({"month": month, "llm_calls": 0})
    return u


def budget_ok(state: dict, cfg: dict) -> bool:
    u = usage_this_month(state)
    cap = cfg["safety"]["monthly_llm_call_cap"]
    if u["llm_calls"] >= cap:
        log.error("⚠️ 月間LLM呼び出し上限(%d)到達。今月はこれ以上生成しない。", cap)
        return False
    return True


def add_llm_calls(state: dict, n: int):
    usage_this_month(state)["llm_calls"] += n


# ---------- ウォームアップ（新規アカの初動は控えめに）----------
def ensure_account_start(state: dict) -> str:
    s = state.setdefault("safety_state", {})
    if not s.get("started"):
        s["started"] = dt.date.today().isoformat()
    return s["started"]


def in_warmup(state: dict, cfg: dict) -> bool:
    start = ensure_account_start(state)
    try:
        d = dt.date.fromisoformat(start)
    except Exception:
        return False
    weeks = cfg["safety"]["warmup_weeks"]
    return (dt.date.today() - d).days < weeks * 7


def effective_caps(state: dict, cfg: dict) -> tuple[int, int]:
    """(新規Pin上限, 再Pin上限) を返す。ウォームアップ中と1日ハード上限を反映。"""
    new_cap = cfg["schedule"]["pins_per_day"]
    repin_cap = cfg["schedule"]["repins_per_day"]
    if in_warmup(state, cfg):
        wp = cfg["safety"]["warmup_pins_per_day"]
        new_cap = min(new_cap, wp)
        repin_cap = min(repin_cap, max(0, wp - new_cap))
        log.info("ウォームアップ中: 新規上限=%d 再Pin上限=%d", new_cap, repin_cap)
    remaining = daily_cap_remaining(state, cfg)
    new_cap = min(new_cap, remaining)
    repin_cap = min(repin_cap, max(0, remaining - new_cap))
    return new_cap, repin_cap


def shadowban_paused(state: dict, cfg: dict) -> bool:
    if not cfg["safety"].get("pause_on_shadowban", True):
        return False
    return bool(state.get("performance", {}).get("shadowban_paused"))
