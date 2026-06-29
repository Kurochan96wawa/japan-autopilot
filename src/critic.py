"""施策01: マルチエージェントQAゲート（人間レビューの無人置換）。

生成済み記事を“別役割のAI批評者”が審査し、機械チェック＋自己採点ルーブリックでは
拾いきれない次を検出する:
  ① AI丸出しの定型句（コーポレート・フィラー）
  ② 具体性の欠如（名前/数値/円/分/kg/駅 などの欠落）
  ③ YMYL（安全・健康・お金）の危うい断定
  ④ 壊れたHTML（h3の入れ子・表の不正タグ・Markdown漏れ）
  ⑤（任意）渡された一次ソース事実と矛盾する記述

verdict=revise の場合は同じ呼び出しで修正版HTMLを受け取り、本文を差し替える（自動修正）。
verdict=reject は破棄。全工程が generate() 経由＝無人。llm.py のマルチプロバイダ・
フォールバック前提なので、レート制限/コストに強い（GitHub Models 中心で無料）。
"""
from __future__ import annotations
from .llm import generate
from .util import load_settings, log

# 機械検出する“AI丸出し/ブローシャー定型句”。検出したら critic に必ず直させる。
_BANNED = [
    "the logistics of managing", "can feel daunting", "significantly ease",
    "navigating the nuances", "understanding the nuances", "a key consideration",
    "with careful planning", "ease your travel preparations",
    "in today's fast-paced world", "when it comes to", "it is important to note",
    "a myriad of", "rest assured", "look no further", "the world of",
]

_CRITIC_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},        # pass | revise | reject
        "score": {"type": "integer"},
        "issues": {"type": "array", "items": {"type": "string"}},
        "revised_html": {"type": "string"},
    },
    "required": ["verdict", "score", "issues", "revised_html"],
    "propertyOrdering": ["verdict", "score", "issues", "revised_html"],
}


def _mechanical_flags(html: str) -> list:
    low = (html or "").lower()
    hits = [p for p in _BANNED if p in low]
    if "**" in (html or "") or "\n##" in (html or ""):
        hits.append("markdown leakage (** or ##)")
    if "<h3><h3" in (html or "").replace(" ", ""):
        hits.append("nested <h3><h3>")
    return hits


def review(content: dict, facts: str = "") -> dict:
    """記事を審査し {verdict, score, issues, revised_html} を返す。
    critic自体が失敗したら pass 扱い（1本の審査失敗で公開を止めない）。"""
    title = content.get("article_title", "")
    html = content.get("article_html", "")
    if not html:
        return {"verdict": "reject", "score": 0, "issues": ["empty article_html"], "revised_html": ""}

    banned = _mechanical_flags(html)
    facts_block = ""
    if facts:
        facts_block = (
            "\n\nVERIFIED SOURCE FACTS (Japanese primary sources; treat as ground truth. "
            "Flag any claim that contradicts these or any price/hour with no support):\n" + facts[:4000]
        )
    banned_line = ("\n8. These banned phrases were detected and MUST be removed/rewritten: "
                   + ", ".join(banned)) if banned else ""

    prompt = f"""You are a STRICT editorial fact-checker and quality critic for a family-travel site about Japan (visiting Japan with kids). Review the article below as an adversarial reviewer would — harsh but fair. Your job is to catch what a lazy AI writer leaves behind.

TITLE: {title}

ARTICLE HTML:
{html}{facts_block}

Check for:
1. AI-tell / corporate filler (e.g. "the logistics of managing", "can feel daunting", "a key consideration", "navigating the nuances"). These MUST be removed and rewritten in a warm, concrete, human voice.
2. Vague claims with NO concrete specific. Every section needs at least one real specific (a name, number, yen price, minutes, kg, station name, or rule).
3. YMYL safety: any health / allergy / medical / water-or-heat safety claim must be non-alarming, non-definitive, and tell readers to consult a doctor or official guidance for their child.
4. Prices or opening hours stated as fact WITHOUT a "(as of 2026, confirm on the official site)" style hedge.
5. The opening must be answer-first: the first 1-2 sentences directly answer the title question (no generic "Planning a trip to Japan..." preamble).
6. Thin/generic content any brochure could contain; missing TL;DR list, comparison table, or FAQ.
7. Broken HTML: nested headings like <h3><h3>, stray </li> inside tables, leftover Markdown (** or ##).{banned_line}

Decide a verdict:
- "pass": genuinely clean, specific, warm, safe. No meaningful issues.
- "revise": good bones but has fixable issues (filler, vagueness, missing hedge, broken HTML). PROVIDE a fully corrected revised_html.
- "reject": fundamentally thin, generic, or unsalvageable.

When revising: keep the SAME structure and length range (1100-1800 words), keep every <a href='...'> affiliate link EXACTLY as-is (do not invent or drop links), keep the TL;DR list, tables and the <h2>FAQ</h2> with <h3> questions. Output PURE HTML only (no Markdown, no ** or ##). Make the voice warm, witty and human, every section concrete.

Return ONLY a JSON object:
{{"verdict":"pass|revise|reject","score":<0-100>,"issues":["short issue",...],"revised_html":"<full corrected HTML if verdict=revise, else empty string>"}}"""

    try:
        r = generate(prompt, as_json=True, schema=_CRITIC_SCHEMA)
    except Exception as e:
        log.error("critic失敗(公開は継続): %s", e)
        return {"verdict": "pass", "score": 0, "issues": [f"critic-error:{e}"], "revised_html": ""}
    if not isinstance(r, dict):
        return {"verdict": "pass", "score": 0, "issues": ["bad-critic-output"], "revised_html": ""}
    r.setdefault("verdict", "pass")
    r.setdefault("score", 0)
    r.setdefault("issues", [])
    r.setdefault("revised_html", "")
    return r


def gate(content: dict, cfg: dict, facts: str = "") -> tuple:
    """審査して (ok: bool, content: dict, report: dict) を返す。
      * verdict=revise かつ妥当な修正HTMLがあれば本文を差し替えて ok=True
      * verdict=reject、または score が min_score 未満なら ok=False（破棄）
      * critic無効/失敗時は素通し（公開を止めない＝記事ゼロを防ぐ）
    """
    qc = cfg.get("critic", {}) if isinstance(cfg, dict) else {}
    if not qc.get("enabled", True):
        return True, content, {"verdict": "skipped"}

    rep = review(content, facts)
    verdict = (rep.get("verdict") or "pass").lower()

    if verdict == "reject":
        log.error("QAゲート reject: %s issues=%s", content.get("article_title"), rep.get("issues"))
        return False, content, rep

    if verdict == "revise":
        new_html = (rep.get("revised_html") or "").strip()
        orig = content.get("article_html", "")
        # 壊れた短文で本文を潰さないよう、十分な長さのHTMLが返った時だけ差し替える
        if "<" in new_html and len(new_html) > max(400, len(orig) // 2):
            content = dict(content)
            content["article_html"] = new_html
            content["_critic_revised"] = True
            log.info("QAゲート revise→自動修正: %s (issues=%d)",
                     content.get("article_title"), len(rep.get("issues", [])))
        else:
            log.warning("QAゲート revise指示だが修正HTMLが不十分→原文採用: %s",
                        content.get("article_title"))

    min_score = int(qc.get("min_score", 0) or 0)
    score = int(rep.get("score", 0) or 0)
    if min_score and score and score < min_score:
        log.error("QAゲート score %d < %d → 破棄: %s", score, min_score, content.get("article_title"))
        return False, content, rep

    content = dict(content)
    content["critic_score"] = rep.get("score")
    return True, content, rep
