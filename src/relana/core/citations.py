"""レポートに出す典拠。

利用者は「なぜこの数字を見せられているのか」を知らないまま読む。
書誌は出典ページにまとめ、各ページからはそこへ送る。
指標ページの中に文献を並べると、数値と打ち手の間に挟まって読みにくい。

書誌は1か所にまとめる。コードの各所に文字列で散らすと、
版が変わったときに直し漏れる。

`basis` には **この OSS がその文献から何を取ったか** を書く。
文献を並べるだけでは、どこまでが典拠でどこからが自前の判断か分からない。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Citation:
    key: str
    authors: str
    year: str
    title: str
    where: str
    basis: str  # この OSS がここから取ったもの
    # 本文で参照するときの名前。著者の姓だけでは何の文献か分からないので、
    # 日本語で「何の文献か」が分かるように書く。年もここに含める。
    short: str
    url: str = ""


CITATIONS: dict[str, Citation] = {
    "book_ch5": Citation(
        key="book_ch5",
        short="『ピープルアナリティクスで人事戦略が変わる』第5章（2018）",
        authors="ポール・レオナルディ、ノシャー・コントラクター",
        year="2018",
        title="第5章 ピープルアナリティクスで人事戦略が変わる",
        where="『ハーバード・ビジネス・レビュー』掲載論文の邦訳。p.96-119",
        basis=(
            "この OSS が測る6つの特徴（発想力・影響力・効率性・イノベーション・"
            "サイロ・脆弱性）と、サイロと判断する 5:1 という基準"
        ),
    ),
    "leonardi_contractor_2018": Citation(
        key="leonardi_contractor_2018",
        short="同章の原論文（ハーバード・ビジネス・レビュー 2018年11-12月号）",
        authors="Paul Leonardi, Noshir Contractor",
        year="2018",
        title="Better People Analytics: Measure Who They Know, Not Just Who They Are",
        where="Harvard Business Review, November–December 2018, pp.70-81",
        basis=(
            "上の章の原論文。属性ではなく関係を測るという方針と、"
            "業績と相関するネットワーク上のパターン（構造的シグネチャ）という考え方"
        ),
    ),
    "burt_1992": Citation(
        key="burt_1992",
        short="バート『構造的空隙』（1992）",
        authors="Ronald S. Burt",
        year="1992",
        title="Structural Holes: The Social Structure of Competition",
        where="Harvard University Press",
        basis=(
            "「発想の起点となる人」で使う制約（constraint）の定義。"
            "互いにつながっていない集団の間に立つ人ほど、新しい情報に触れるという主張"
        ),
    ),
    "freeman_1977": Citation(
        key="freeman_1977",
        short="フリーマン 媒介中心性を定義した論文（1977）",
        authors="Linton C. Freeman",
        year="1977",
        title="A Set of Measures of Centrality Based on Betweenness",
        where="Sociometry, 40(1), pp.35-41",
        basis="「インフルエンサー」と「ハブとなっている人」で使う媒介中心性の定義",
    ),
    "gould_fernandez_1989": Citation(
        key="gould_fernandez_1989",
        short="グールドとフェルナンデス 仲介の型を分けた論文（1989）",
        authors="Roger V. Gould, Roberto M. Fernandez",
        year="1989",
        title="Structures of Mediation: A Formal Approach to Brokerage in Transaction Networks",
        where="Sociological Methodology, 19, pp.89-126",
        basis=(
            "「橋渡し役」の判定に使う仲介の数え方。"
            "この OSS は向きを持たないグラフで扱うため、同部門内の仲介と"
            "部門をまたぐ仲介の2種類に簡約している"
        ),
    ),
    "cross_rebele_grant_2016": Citation(
        key="cross_rebele_grant_2016",
        short="クロスほか 協働の負荷が偏ることを示した論文（2016）",
        authors="Rob Cross, Reb Rebele, Adam Grant",
        year="2016",
        title="Collaborative Overload",
        where="Harvard Business Review, January–February 2016",
        basis=(
            "「負荷が集中している人」を見る理由。"
            "協働の要請が特定の人に集まり、その人の業績と健康の両方を損なうという指摘"
        ),
    ),
    "granovetter_1973": Citation(
        key="granovetter_1973",
        short="グラノヴェッター「弱い紐帯の強さ」（1973）",
        authors="Mark S. Granovetter",
        year="1973",
        title="The Strength of Weak Ties",
        where="American Journal of Sociology, 78(6), pp.1360-1380",
        basis=(
            "部門をまたぐ接点を重く見る理由。新しい情報は、別の集団にいる相手から来るという主張。"
            "同じ集団の中では、持っている情報が互いに重なる"
        ),
    ),
    "newman_girvan_2004": Citation(
        key="newman_girvan_2004",
        short="ニューマンとガーバン モジュラリティを定義した論文（2004）",
        authors="M. E. J. Newman, M. Girvan",
        year="2004",
        title="Finding and Evaluating Community Structure in Networks",
        where="Physical Review E, 69, 026113",
        basis="部門の分かれ方の強さを1つの値で出すモジュラリティの定義",
    ),
}

# ページごとに、どの文献に基づいているか
BY_FEATURE: dict[str, list[str]] = {
    "silo": ["book_ch5", "leonardi_contractor_2018", "newman_girvan_2004", "granovetter_1973"],
    "vulnerability": ["book_ch5", "leonardi_contractor_2018", "freeman_1977"],
    "influence": ["book_ch5", "leonardi_contractor_2018", "freeman_1977"],
    "ideation": ["book_ch5", "leonardi_contractor_2018", "burt_1992"],
    "team": ["book_ch5", "leonardi_contractor_2018"],
    "roles": ["gould_fernandez_1989", "cross_rebele_grant_2016"],
}

# 典拠にない、この OSS が自分で決めたもの。典拠と混ぜない。
OWN_CHOICES: dict[str, str] = {
    "silo": (
        "I/E 比は部門の人数に左右されるため、ランダムにつながっていた場合の比を"
        "併せて出している。この補正は研究にない"
    ),
    "vulnerability": (
        "この人がいなくてもつながる組の割合と、"
        "引き継ぎ候補を加えたときの試算は、この OSS が足したもの"
    ),
    "influence": (
        "研究は指標を1つに決めていない。媒介中心性を選んだのは"
        "この OSS の判断で、理由はコードの influence.py に書いてある。"
        "「直接の相手が少ないのに情報の通り道になっている人」を、"
        "他の人どうしの経路の1%以上が通り、かつ直接つながっている相手が"
        "全社の中央値以下の人としているのも、この OSS が決めたもの"
    ),
    "ideation": "部門ごとに分けて順位を出すのは、人数の違う集団を混ぜないためで、研究にない",
    "team": "内部密度と外部範囲の境目は、観測した値の中央値で引いている。研究に数値はない",
    "roles": (
        "6つの役割の名前と、役割に当てはめる基準の値は、この OSS が決めたもの。"
        "研究にあるのは仲介の数え方と、協働の負荷が偏るという指摘まで"
    ),
}


def get(keys: list[str]) -> list[Citation]:
    return [CITATIONS[k] for k in keys if k in CITATIONS]


def for_feature(feature: str) -> list[Citation]:
    return get(BY_FEATURE.get(feature, []))
