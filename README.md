# 🇯🇵 japan-autopilot

外国人の親向け「**子連れ日本旅行ガイド（英語）**」を **Pinterest（主軸）+ Instagram（任意補助）**
に全自動で投稿し、**アフィリエイト収益**を狙う完全自動化ツール。
※ニッチは `config/settings.yaml` の1か所で変更可能。

> 外部AIレビューを受けた戦略の是々非々と改良点は **[STRATEGY-REVIEW.md](./STRATEGY-REVIEW.md)** 参照。

GitHub Actions(無料枠)で**クラウド常駐**するので、**あなたのPCは一切動かさなくていい**。
一度セットアップすれば、毎日「ネタ出し→記事生成→画像作成→投稿→（週次で）成果分析→戦略改善」が
無人で回り続ける。

---

## なぜこの構成なのか（2026年6月時点の調査結論）

| 候補 | 判定 | 理由 |
|---|---|---|
| **Pinterest** | ✅ 主軸 | 公式API無料 / アフィリリンク直貼りOK / 検索エンジン型で投稿が**長期間流入し続ける** / 日本人の英語参入がほぼ無い**穴場** |
| **Instagram** | ✅ 任意補助 | 公式API無料 / Pinの縦長画像を**そのまま流用**でき視覚ジャンルと好相性。1日25件上限・Business連携必須 |
| Threads | ⚪ 既定OFF | Pinterest(計画)とThreads(会話)は利用モードが違い**導線ミスマッチ**。使うなら設定で1に |
| X(Twitter) | ❌ 除外 | 2026年2月に無料枠廃止→従量課金。**URL付き投稿1件$0.20**でアフィリと最悪相性 |
| YouTube/AI動画 | ❌ 除外 | 2026年に「量産AI/再利用コンテンツ」収益化停止が激増。全自動はBANリスク大 |

**ジャンル**: 訪日インバウンドは2025年に過去最高4,268万人・消費9.5兆円。「日本旅行全般」は大手に
勝てないため**「子連れ日本旅行」に特化**（長尾の親向けクエリを狙う）。倫理的にも家族の役に立ち、
ホテル/ツアー/旅グッズとアフィリ相性が良く、実写写真も揃えやすい。

> ⚠️ **正直な前提**: 「プラットフォーム広告収入」はPinterest/Threadsとも日本/自動運用には
> 実質配られない。**現実的な主収益はアフィリエイト**。詳細は [CAVEATS.md](./CAVEATS.md)。

---

## 仕組み（全体像）

```
 [GitHub Actions cron] ──毎日──► src/main.py daily
        │
        ├─ 1. ideas.py     : 成果を踏まえてネタ量産（LLM）
        ├─ 2. content.py   : 記事本文＋Pin/Threadsコピー生成＋アフィリ自動挿入（LLM）
        ├─ 3. images.py    : Pexis実写＋テキスト帯で縦長Pin画像を生成（無料）
        ├─ 4. site.py      : GitHub Pagesに記事ページを生成（Pinの飛び先）
        ├─ 5. publish_pinterest.py : Pin作成（公式API v5）
        ├─ 6. publish_threads.py   : Threads投稿（公式API）
        └─ 7. state.json を更新してcommit（＝ツールの記憶）

 [GitHub Actions cron] ──毎週──► src/main.py improve
        └─ analytics.py : Pin成果を集計→LLMが戦略(伸ばす/避けるテーマ)を更新→自己改善
```

「あなたがやること = お金まわりの手続き（アフィリ登録など）だけ」にするのが目標。
セットアップ手順は **[SETUP.md](./SETUP.md)** に全部書いてある。

---

## クイックスタート

1. このリポジトリを自分のGitHubに置く（private推奨）
2. [SETUP.md](./SETUP.md) に沿って各APIキーを取得し、GitHub Secrets に登録
3. `config/settings.yaml` と `config/affiliates.yaml` を自分用に編集
4. GitHub Pages を有効化（Settings → Pages → ブランチ`main` / フォルダ`/docs` を公開）
5. Actions タブで `daily-post` を **手動実行(workflow_dispatch)** してテスト
6. 問題なければ放置。毎日自動で動く

## ローカル動作確認

```bash
pip install -r requirements.txt
cp .env.example .env   # キーを書き込む
PYTHONPATH=. python -m src.main dry   # APIに投げず生成だけ確認
PYTHONPATH=. python -m src.main daily # 本番（実際に投稿される）
```

## 設定ファイル
- `config/settings.yaml` … ジャンル/言語/投稿数/スケジュール/ボード
- `config/affiliates.yaml` … 自分のアフィリリンク（最初は空でも動く）

## 🛡 安全装置（自動運用の落とし穴対策）
ネット上で報告される典型的な失敗（投稿しすぎ/重複/薄い記事/死リンク/トークン失効/
サイレント故障など）を体系的に潰す防御層を内蔵（`src/guards.py`, `src/tokens.py`）。
- 1日上限・ウォームアップ・投稿間隔ジッターで**BAN確率を下げる**
- perceptual hash/類似文検出で**重複コンテンツを自動回避**
- 品質ゲート（最低文字数・リスク表現フィルタ）で**薄い/古くなる記事を破棄**
- トークン**自動更新**、失敗時は**GitHub Issueで通知**、shadowban検知で**自動停止**
- LLM月間上限で**コスト暴走防止**（既定は実質¥0運用）

対策の全対応表 → **[PITFALLS.md](./PITFALLS.md)**
> ※「完全無欠」は存在しない（規約は変わる/BAN対策は確率を下げるもの）。最後の保険は「月10分の目視」。

## 💰 コスト
既定構成は**実質¥0**で回る（GitHub/Gemini/Pexels/各SNS APIすべて無料枠）。
**月1,000円**は上位LLMへの一時切替や無料枠超過のバッファ。詳細は [CAVEATS.md](./CAVEATS.md) の「4. コスト」。

## ⚠️ 必読
運用前に必ず **[CAVEATS.md](./CAVEATS.md)**（BANリスク・規約・コスト・収益の現実）と
**[PITFALLS.md](./PITFALLS.md)**（落とし穴と対策の対応表）を読むこと。
