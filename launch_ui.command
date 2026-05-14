#!/bin/bash
# AI Dialogue UI launcher (double-click to start)
# 初回起動時は依存パッケージを自動インストール

set -e
cd "$(dirname "$0")"

# Find Python 3
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

# Check / install streamlit
if ! "$PYTHON_BIN" -c "import streamlit" >/dev/null 2>&1; then
    echo "📦 初回起動: 依存パッケージをインストールします..."
    "$PYTHON_BIN" -m pip install -r requirements.txt
fi

echo "🎙 AI Dialogue を起動します..."
echo "   ブラウザが自動で開きます。終了するには Ctrl+C。"
echo ""

"$PYTHON_BIN" -m streamlit run app.py
