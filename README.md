# AI Dialogue (Gemini × Gemini)

Gemini を2役で動かして、勝手に議論させる自律対話システム。
3人目の Gemini がファシリテーター（論点整理＆合意判定）を担当。

## ファイル構成

```
ai_dialogue/
├── .env                # GEMINI_API_KEY
├── personas.py         # キャラ定義（12種＋カスタム）
├── dialogue_core.py    # 対話エンジン（イベントジェネレータ）
├── dialogue.py         # CLI 入口
├── app.py              # Streamlit UI 入口
├── launch_ui.command   # ダブルクリック起動（Mac）
├── requirements.txt
└── logs/               # 会話ログ（自動生成）
```

## セットアップ

```bash
cd /Users/katoutatsurou/Claude作業フォルダ/ai_dialogue
pip install -r requirements.txt
```

`.env` に `GEMINI_API_KEY` が設定されていることを確認。

## 起動方法

### 1. Streamlit UI（推奨）

```bash
streamlit run app.py
```

または `launch_ui.command` をダブルクリック（Mac）。
初回はパッケージを自動インストールしてからブラウザを開く。

UI で操作できること:
- お題入力
- キャラA / キャラB を独立に選択（12種＋カスタム）
- パラメータ調整（往復数 / 介入間隔 / 遅延）
- リアルタイム会話表示
- 過去ログ閲覧・ダウンロード

### 2. CLI

```bash
# 対話入力 or デフォルトお題
python dialogue.py

# お題指定
python dialogue.py "リモートワークは生産性を上げるか"

# キャラ指定
python dialogue.py "お題" --persona-a engineer --persona-b child

# キャラ一覧
python dialogue.py --list-personas

# パラメータ調整
python dialogue.py "お題" --rounds 10 --interval 2 --delay 1
```

## キャラ一覧

| キー | キャラ |
|---|---|
| `ideaman` | 💡 アイデアマン |
| `tsukkomi` | 🔍 ツッコミ役 |
| `optimist` | 😎 楽観派 |
| `pessimist` | 😟 悲観派 |
| `engineer` | ⚙️ エンジニア |
| `designer` | 🎨 デザイナー |
| `executive` | 👔 経営者 |
| `frontline` | 🧑‍💻 現場担当 |
| `child` | 🧒 子供視点 |
| `scholar` | 🧑‍🎓 学者 |
| `sales` | 💼 営業 |
| `villain` | 🦹 悪役視点 |
| `custom` | ✏️ カスタム（UI でプロンプト入力） |

新しいキャラを足したい場合は `personas.py` に追記。

## 動作概要

```
[お題]
  ↓
キャラA → 提案
  ↓
キャラB → 反論・懸念
  ↓
判定Gemini → 合意した？ → YES なら終了
  ↓ NO
3往復ごとに 🎤 ファシリテーターGemini が論点整理
  ↓
ループ（最大 rounds 回）
```

## ログ

`logs/YYYY-MM-DD_HHMMSS_dialogue.md` に自動保存。
UI からはサイドバーで過去ログを選んで閲覧、ダウンロード可。

## モデル

`gemini-2.0-flash`（無料枠 1500RPD で複数人共有でも余裕）。
変更は `dialogue_core.py` の `MODEL` 定数。

## Streamlit Cloud にデプロイ（チーム共有）

1. **GitHub リポを Streamlit Cloud に接続**
   - https://share.streamlit.io にログイン（GitHubアカウントで）
   - 「New app」→ `katochanpei/ai-dialogue` を選択
   - Branch: `main` / Main file path: `app.py`

2. **Secrets を設定**
   - アプリ詳細画面の「Settings」→「Secrets」
   - 以下を貼り付け（実値に置き換え）:
     ```toml
     GEMINI_API_KEY = "AIza..."
     APP_PASSWORD = "<set-app-password-here>"
     MULTI_USER_MODE = "true"
     ```
   - `MULTI_USER_MODE = "true"` 必須（過去ログがユーザー間で見えるのを防ぐ）

3. **Deploy** をクリック
   - 数分で `https://<app-name>.streamlit.app` が発行される

4. **同僚に共有**
   - URL とパスワードを伝える
   - 同僚は URL 開く → パスワード入力 → 即使える

## トラブルシューティング

- `google.genai` import error → `pip install -r requirements.txt`
- `429 RESOURCE_EXHAUSTED` → rate limit。`--delay 5` などに上げる
- 何も喋らない → APIキー誤り or 期限切れ。`.env` を確認
- Streamlit でブラウザが開かない → 出力された `http://localhost:8501` を手動で開く
