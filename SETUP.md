# セットアップ手順（これだけやれば全自動になる）

所要時間: 初回90〜120分くらい。技術知識はほぼ不要。詰まったらClaude Codeに
「SETUP.mdのStep Xで詰まった」と聞けばこのリポジトリを見て助けてくれる。

> 💡 **Claude Codeの使い方**: このフォルダで `claude` を起動し、
> 「READMEとSETUPを読んで、セットアップを順番に手伝って」と頼めば対話で進められる。

---

## Step 0. 全体の流れ
1. GitHubにリポジトリを置く
2. 各サービスのアカウント＆APIキーを取る
3. GitHub Secrets にキーを登録
4. 設定ファイルを自分用に編集
5. GitHub Pages を有効化
6. テスト実行 → 放置

---

## Step 1. GitHubリポジトリを作る
1. GitHubで **New repository** → 名前は `japan-autopilot`（任意）→ **Private** 推奨
2. このフォルダの中身を全部push（Claude Codeに「このフォルダをこのリポジトリにpushして」でOK）

---

## Step 2. LLMキーを取る（予算重視 = Gemini無料枠）
- **推奨: Google Gemini** … https://aistudio.google.com/ → "Get API key"。無料枠で十分回せる。
  - 取得した `GEMINI_API_KEY` を控える。
- 代替: OpenAI / Anthropic（`config/settings.yaml` の `llm.provider` を変更）。

## Step 3. 画像キー（無料）= Pexels
- https://www.pexels.com/api/ で無料登録 → `PEXELS_API_KEY` を控える。
- ※キー無しでも動く（単色背景にタイトルを載せたPinになる）。実写の方が成果は出る。

## Step 4. Pinterest API（主軸・重要）
1. Pinterestの**ビジネスアカウント**を作る（無料。個人→ビジネス転換でOK）
2. https://developers.pinterest.com/ でアプリ登録
3. OAuthで **access token** を発行（スコープ: `boards:read/write`, `pins:read/write`, `user_accounts:read`）
4. `PINTEREST_ACCESS_TOKEN` を控える
> ⚠️ 最初は **Trial access**。本番運用には**アプリ審査(Standard access)申請**が必要なことが多い。
> 詳細と回避策は CAVEATS.md。

## Step 5. Threads API（補助）
1. Meta開発者登録 https://developers.facebook.com/
2. Threads用アプリを作成 → Threads API を追加
3. 自分のThreadsアカウントを連携し、long-lived access token と user id を取得
4. `THREADS_ACCESS_TOKEN` と `THREADS_USER_ID` を控える
> ⚠️ Threadsは投稿間隔5分以上必須。本ツールはsettingsで制御済み。

## Step 6. GitHub Secrets に登録
リポジトリ → **Settings → Secrets and variables → Actions → New repository secret**
で以下を登録（持っているものだけでOK）:

| Secret名 | 中身 |
|---|---|
| `GEMINI_API_KEY` | Step2 |
| `PEXELS_API_KEY` | Step3 |
| `PINTEREST_ACCESS_TOKEN` | Step4 |
| `THREADS_ACCESS_TOKEN` | Step5 |
| `THREADS_USER_ID` | Step5 |

## Step 7. 設定ファイルを編集
- `config/settings.yaml`
  - `site.base_url` を `https://あなたのGitHubユーザー名.github.io/japan-autopilot` に
  - `schedule.pins_per_day` は最初は **2〜3** に（いきなり大量投稿はスパム判定リスク。CAVEATS参照）
- `config/affiliates.yaml`
  - 各 `url` を自分のアフィリリンクに置換（未登録のものは placeholder のままで自動的に無効化される）

## Step 8. GitHub Pages を有効化
1. Settings → **Pages**
2. Source: **Deploy from a branch** → Branch: `main` / folder: `/site` を選択 → Save
3. 数分後 `https://<ユーザー名>.github.io/japan-autopilot/` が公開される

## Step 9. テスト実行
1. **Actions** タブ → `daily-post` → **Run workflow**（手動実行）
2. ログが緑になればOK。Pinterest/Threadsに投稿され、`site/` に記事が増える
3. 失敗したらログを見る（Claude Codeに貼れば原因を特定してくれる）

## Step 10. 放置
- 以後 `daily.yml` の cron（毎朝）で自動投稿、`weekly-improve.yml` で週次改善が回る。
- あなたの作業は「アフィリ報酬の受け取り」と「たまに成果を眺める」だけ。

---

## アフィリエイトプログラム登録（収益の源泉。早めに）
役立つ＆審査が通りやすい主なもの:
- **eSIM**: Airalo / Saily などのアフィリプログラム
- **鉄道/ツアー**: Klook、GetYourGuide、Voyagin（パートナープログラム）
- **宿**: Booking.com アフィリエイトパートナー、Agoda
- **物販**: Amazonアソシエイト（各国。米国向けなら amazon.com associates）
登録→承認後、`config/affiliates.yaml` のURLを差し替えるだけで記事に自動反映される。
