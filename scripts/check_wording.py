#!/usr/bin/env python3
"""レポートの文章を機械的に点検する。

注意書きを書くだけでは守られない（実測で学んだ教訓）。
機械的なチェックに変える。

    python scripts/check_wording.py                  # 既定の対象を点検
    python scripts/check_wording.py path.html ...    # 対象を指定
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_TARGETS = [
    "src/relana/report/html.py",
    "src/relana/report/svg.py",
    "src/relana/core/metrics",
    "src/relana/core/reliability.py",
    "snapshots",
]

# 参考: https://speakerdeck.com/nasuvitz/ai-kusai-bunshou-toha-nanina-no-ka
RULES: list[tuple[str, list[str], str]] = [
    (
        "比喩的動詞・抽象語",
        [
            "滞留", "手が届く", "壁が厚い", "埋め尽く", "縛られ", "支えてい",
            "流れが切れ", "光を当て", "浮かび上が", "寄り添", "紐解", "腹落ち",
            "輪郭", "地図", "羅針", "橋渡しし", "土台とな", "鍵を握",
        ],
        "何が起きるのかを、数値か具体的な動作で書く",
    ),
    (
        "対比・否定・留保から始める",
        [
            "ではなく、", "とは限りません", "わけではあり", "だけでは",
            "重要なのは", "大事なのは", "本質は", "むしろ",
        ],
        "主文を先に書く。否定で始めず、何がどうなのかを直接書く",
    ),
    (
        "曖昧な名詞化・ぼかし",
        [
            "可能性があります。", "傾向として", "参考程度", "起点として",
            "棚卸し", "複線化", "工夫が要", "最適化", "見える化",
            "検討が必要", "示唆して", "考えられます。", "一助",
        ],
        "誰が何をするのかを書く。数値で言えるものは数値で書く",
    ),
    (
        "対句・体言止めで印象づける",
        ["——", "。そして、", "のではない。", "ことである。"],
        "飾りを外し、主語と動作を書く",
    ),
    (
        "判断を読者に丸投げ",
        ["ご確認ください。", "ご判断ください。", "お使いください。", "注視"],
        "誰に何を確認するのかを書く",
    ),
    (
        "観測していないことを書いている",
        [
            "共通の知人", "知り合い", "仲が良い", "信頼関係", "親しい",
            "コミュニケーション量", "会話量", "交流が活発",
        ],
        "会議に同席したかどうかしか観測していない。同席の事実で書く",
    ),
    (
        "利用者が読めない用語",
        [
            "ノード", "エッジ", "被覆率", "閾値", "単一障害点", "関節点",
            "有向グラフ", "無向グラフ", "次数", "パーセンタイル", "正規化",
            "代替可能性", "代替率", "タコつぼ",
        ],
        "人事担当者が読む言葉に直す。図の部品なら「丸」「線」、"
        "統計の語なら何を数えたかで書く",
    ),
    (
        "どれが・誰がを書いていない",
        [
            "2つ以上に分かれ", "複数の部門に分かれ", "一部の部門",
            "一部のメンバー", "いくつかの集団に分かれ", "複数に分断",
        ],
        "分かれる集団の氏名または部門の内訳を書く",
    ),
]

# person_id をそのまま画面に出していないか。氏名に直してから出す。
ID_IN_TEXT = re.compile(r"[（(]\s*(?:u_\d+|ext:[^\s）)]+)")


def readable_text(path: Path, text: str) -> str:
    """利用者に届く文字列だけを残す。

    docstring とコメントは開発者向けであり、この規約の対象外。
    対象にすると偽陽性が増え、本来直すべき箇所が埋もれる。
    """
    if path.suffix == ".html":
        return re.sub(r"<[^>]+>", " ", text)
    if path.suffix != ".py":
        return text

    def blank(m: "re.Match[str]") -> str:
        return "\n" * m.group(0).count("\n")

    text = re.sub(re.escape('"""') + r"(?:.|\n)*?" + re.escape('"""'), blank, text)
    text = re.sub(re.escape("'''") + r"(?:.|\n)*?" + re.escape("'''"), blank, text)
    return "\n".join(re.sub(r"#.*$", "", ln) for ln in text.split("\n"))


def targets(argv: list[str]) -> list[Path]:
    raw = argv or DEFAULT_TARGETS
    out: list[Path] = []
    for t in raw:
        p = (ROOT / t) if not Path(t).is_absolute() else Path(t)
        if p.is_dir():
            out += [q for q in p.rglob("*") if q.suffix in {".py", ".html", ".md"}]
        elif p.exists():
            out.append(p)
    return out


def main(argv: list[str]) -> int:
    files = targets(argv)
    if not files:
        print("点検対象が見つかりませんでした。")
        return 2

    total = 0
    for path in files:
        text = readable_text(path, path.read_text(encoding="utf-8", errors="ignore"))
        hits: list[tuple[str, str, str, int]] = []
        for name, words, advice in RULES:
            for w in words:
                for m in re.finditer(re.escape(w), text):
                    line = text.count("\n", 0, m.start()) + 1
                    hits.append((name, w, advice, line))
        for m in ID_IN_TEXT.finditer(text):
            hits.append((
                "内部IDを画面に出している",
                m.group(0).strip(),
                "person_id ではなく display_name を出す",
                text.count("\n", 0, m.start()) + 1,
            ))
        if hits:
            total += len(hits)
            print(f"\n{path.relative_to(ROOT)}")
            for name, w, advice, line in hits:
                print(f"  {line:5d}  [{name}] 「{w}」")
                print(f"         → {advice}")

    print(f"\n点検 {len(files)} ファイル / 指摘 {total} 件")
    if total:
        print(
            "\n直し方の基準:\n"
            "  1. 誰が・何を・どうした を書く\n"
            "  2. 数値で言えるものは数値で書く（「多い」ではなく「13.2倍」）\n"
            "  3. 否定・対比・留保から始めない\n"
            "  4. 読者に文脈の補完を求めない"
        )
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
