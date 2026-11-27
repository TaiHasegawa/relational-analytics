#!/usr/bin/env bash
# relana セットアップ（macOS / Linux）
# 実体は scripts/setup.py。ここは Python を探して渡すだけ。
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for cand in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c 'import sys;sys.exit(0 if sys.version_info>=(3,11) else 1)' 2>/dev/null; then
      exec "$cand" "$ROOT/scripts/setup.py"
    fi
  fi
done
cat <<'MSG'

■ セットアップを中断しました
Python 3.11 以上が見つかりませんでした。

  macOS:
    1. https://www.python.org/downloads/ を開く
    2. 大きな「Download Python」ボタンを押す
    3. ダウンロードされたファイルを開いて、画面の指示どおりに進める
    4. 終わったら、このファイルをもう一度実行する

  Ubuntu / Debian:
    sudo apt install python3 python3-venv python3-pip

MSG
exit 1
