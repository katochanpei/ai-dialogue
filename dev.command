#!/bin/bash
# ローカル開発サーバ起動（ファイル保存で即リロード）
# ダブルクリックで起動可能。
#
# Run-on-save 有効なので app.py を編集→保存するだけで
# ブラウザが自動で更新される。

set -e
cd "$(dirname "$0")"

# Python 3 を探す
PYTHON_BIN=""
for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "❌ Python 3 が見つかりません。"
    echo "   https://www.python.org/downloads/ からインストールしてください。"
    read -n 1 -s -r -p "Enter to close..."
    exit 1
fi

# streamlit がなければインストール
if ! "$PYTHON_BIN" -c "import streamlit" >/dev/null 2>&1; then
    echo "📦 初回起動: 依存パッケージをインストールします..."
    "$PYTHON_BIN" -m pip install -r requirements.txt
fi

PORT=8502

# 既に同ポートで動いてる Streamlit があれば kill する
EXISTING_PIDS=$(lsof -ti :$PORT 2>/dev/null || true)
if [ -n "$EXISTING_PIDS" ]; then
    echo "♻️  ポート $PORT で動いてる古いプロセスを終了します: $EXISTING_PIDS"
    kill -9 $EXISTING_PIDS 2>/dev/null || true
    sleep 1
fi

echo "🔧 開発モードで AI議論 を起動します..."
echo "   ・app.py を保存するたびにブラウザが自動更新されます。"
echo "   ・終了するには Ctrl+C。"
echo "   ・URL: http://localhost:$PORT"
echo ""

# Run on save 有効、自動でブラウザ開く
"$PYTHON_BIN" -m streamlit run app.py \
    --server.runOnSave true \
    --server.headless false \
    --server.port $PORT
