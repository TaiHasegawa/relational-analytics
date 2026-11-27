#!/usr/bin/env python3
"""relana セットアップ（Windows / macOS / Linux 共通）。

標準ライブラリだけで動くので、どの環境・どのエージェントからでも
    python3 scripts/setup.py
の1コマンドで同じ結果になる。
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IS_WIN = os.name == "nt"
VENV = ROOT / ".venv"
VPY = VENV / ("Scripts/python.exe" if IS_WIN else "bin/python")
VRELANA = VENV / ("Scripts/relana.exe" if IS_WIN else "bin/relana")

C = {"b": "", "g": "", "y": "", "r": "", "x": ""}
if sys.stdout.isatty() and not IS_WIN:
    C = {"b": "\033[1m", "g": "\033[32m", "y": "\033[33m", "r": "\033[31m", "x": "\033[0m"}


def step(msg: str) -> None:
    print(f"\n{C['b']}{msg}{C['x']}")


def ok(msg: str) -> None:
    print(f"{C['g']}✓{C['x']} {msg}")


def die(msg: str) -> None:
    print(f"\n{C['r']}■ セットアップを中断しました{C['x']}\n{msg}\n")
    sys.exit(1)


BANNER = """
  relana — 組織のリレーショナル分析
  ────────────────────────────────
  会議の予定から「誰と誰がつながっているか」を分析します。
  このセットアップは数分で終わります。
"""

PYTHON_HELP = {
    "darwin": """Python 3.11 以上が必要です。

  1. https://www.python.org/downloads/ を開く
  2. 大きな「Download Python」ボタンを押す
  3. ダウンロードされたファイルを開き、画面の指示どおりに進める
  4. 終わったら、もう一度このセットアップを実行する""",
    "win32": """Python 3.11 以上が必要です。

  1. https://www.python.org/downloads/ を開く
  2. 大きな「Download Python」ボタンを押す
  3. インストーラの最初の画面で
     ★「Add python.exe to PATH」に必ずチェックを入れる★
  4. 「Install Now」を押す
  5. 終わったら、もう一度このセットアップを実行する""",
}


def main() -> None:
    print(BANNER)

    step("1/4  Python を確認しています")
    if sys.version_info < (3, 11):
        die(
            PYTHON_HELP.get(sys.platform, "Python 3.11 以上が必要です。")
            + f"\n\n  （いま使われているのは {sys.version.split()[0]} です）"
        )
    ok(f"Python {sys.version.split()[0]} を使います")

    step("2/4  専用の作業環境をつくっています")
    if VPY.exists():
        ok("すでにあるものを使います")
    else:
        try:
            venv.EnvBuilder(with_pip=True, clear=True).create(VENV)
        except Exception as e:  # noqa: BLE001
            die(
                "作業環境の作成に失敗しました。\n\n"
                "  Ubuntu / Debian をお使いの場合は、次を実行してからもう一度:\n"
                "    sudo apt install python3-venv\n\n"
                f"  詳細: {e}"
            )
        ok("作成しました（このフォルダの .venv の中。消しても作り直せます）")

    step("3/4  必要な部品をインターネットから取得しています（1〜3分かかります）")
    run([str(VPY), "-m", "pip", "install", "--quiet", "--upgrade", "pip"], check=False)
    res = run([str(VPY), "-m", "pip", "install", "--quiet", "-e", str(ROOT)], check=False)
    if res.returncode != 0:
        die(
            "部品の取得に失敗しました。\n\n"
            "  ネットワークに接続されているか確認して、もう一度お試しください。\n"
            "  社内ネットワークでプロキシをお使いの場合は、情報システム部門にご相談ください。\n\n"
            "  詳細:\n"
            + "\n".join("    " + line for line in (res.stderr or "").splitlines()[-20:])
        )
    ok("完了しました")

    step("4/4  サンプルデータで動かしてみます")
    print("（架空の100名の会社のデータです。あなたの会社のデータはまだ使いません）\n")
    if subprocess.run([str(VRELANA), "demo", "--no-open"], cwd=ROOT).returncode != 0:
        die("分析の実行に失敗しました。このメッセージごと開発者にお知らせください。")

    report = ROOT / "snapshots" / "demo" / "report" / "index.html"
    step("セットアップが完了しました")
    print(f"\n  {C['b']}レポートができました{C['x']}\n    {report}\n")
    try:
        import webbrowser

        if webbrowser.open(report.as_uri()):
            ok("ブラウザで開きました")
    except Exception:  # noqa: BLE001
        pass

    print(f"\n  {C['b']}次にやること{C['x']}")
    print("    自社のデータで分析するには、お使いのエージェントにこう頼んでください:\n")
    print("      「relana で自社のカレンダーを分析して」\n")
    print("    AGENTS.md に手順が書いてあるので、エージェントが読んで進めてくれます。\n")


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=check)


if __name__ == "__main__":
    main()
