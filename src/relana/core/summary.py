"""「この分析で分かること」に出す、分析ごとの代表的な結果を選ぶ。

5つの分析それぞれについて、「この組織ではこうなっている」と言える文を1本だけ選ぶ。
全員分・全部門分はそれぞれのページにあるので、ここでは**何が分かる分析なのかが
伝わる例**を1つ出す。概要は、5枚のカードを横に並べて読み切れる長さに保つ。

## 1本の文に2人（2部門）を出す

1人だけを出すと、読んだ人には**その1人の話**に見える。
「この分析は誰を見つけるものなのか」を伝えるには、同じ性質の人が複数いることが
分かるほうがよい。上位2件を並べ、`detail` でそれぞれの値を1つずつ出す。

3件以上は並べない。カードは横に5枚並ぶので、2行を超えると見渡せなくなる。

## 分析をまたいで順位を付けない

指標の単位が違う。I/E 比は「何倍」、切り離される人数は「何名」、
制約は 0〜1 の比率で、足したり重み付けしたりしても意味のある量にならない。
1つのスコアにまとめると、重みの付け方しだいで順位が変わり、根拠を説明できない。

そこで**分析ごとに区切って出す**。並べる順はレポート側で固定する。

## 細いところだけを出さない

典拠が「この形なら成果が出やすい」としているものも出す（`group="strength"`）。
細くなっているところだけを並べると、読んだ人は**何を保てばよいか**が分からない。
打ち手には「いまの型のまま仕事を割り当てる」というものもあり、
そのためには、どの部門と誰がその型なのかを先に知る必要がある。

## 名前は `names` に入れる

レポートは固有名詞と数値だけを太字にする（`src/relana/report/pages.py` の `_emph`）。
太字にする語を文字列から探すと「本部」「部門」のような一般語を拾うので、
**この項目で出した名前を `names` に並べて渡す**。

## 測り方をなぞらない

**「会議」「同席」「出席」という語をここで使わない。**
何をどう測ったかは、移った先の各ページの冒頭に書いてある。
ここで測り方をもう一度なぞると、読み手は**観測値から意味を自分で組み立てる**ことになる。
組み立てた結果だけを書く。

| ❌ 測り方をなぞる | ⭕ そこから言えること |
|---|---|
| 運営本部の18名は、この90日間、他部門の人と一度も同じ会議に出ていません | 運営本部の18名には、部門の外とのつながりがほとんどありません |
| 管理本部 6名 が会議で同席している相手は、この6名と石井089 だけです | 石井089 が異動すると、管理本部の6名は社内から孤立します |
| 管理本部（12名）の同席のうち、79% が部門の中だけです | 管理本部は、人のつながりの8割が部門の中で閉じています |

## 「1件もない」と書かない

関係の重みが下限（`min_edge_weight`）に満たない組は、グラフを作る前に落としている。
合成データでは、運営本部は他部門と3件の大人数会議に出ていて、そのすべてが
下限未満で落ちていた。**「一度も同じ会議に出ていない」は事実として誤り。**

書けるのは「**継続的と言える接点が残っていない**」まで。
"""

from __future__ import annotations

# 1つのカードに出す人数・部門数。横に5枚並ぶので、これを超えると見渡せなくなる
PER_CARD = 2

# 部門名ではなく社外の相手を指す。部門の一覧に混ぜない
EXTERNAL_GROUP = "（社外）"


def build(findings: list, highlights: dict | None = None) -> dict[str, list[dict]]:
    """分析のページ名をキーに、そのページの代表的な結果を返す。"""
    by_metric: dict[str, list] = {}
    for f in findings:
        by_metric.setdefault(f.metric, []).append(f)

    out: dict[str, list[dict]] = {}
    for item in (
        _influence((highlights or {}).get("influence_divergence") or []),
        _vulnerability(by_metric.get("node_criticality", [])),
        _ideation(by_metric.get("constraint", [])),
        _silo(by_metric.get("ie_ratio", [])),
        _teams(by_metric.get("density_x_range", [])),
    ):
        if item:
            out[item["page"]] = [item]
    return out


# ------------------------------------------------------------ インフルエンサー


def _influence(div: list[dict]) -> dict | None:
    """直接の相手の数のわりに、他の人どうしの経路がよく通る人を出す。"""
    rows = div[:PER_CARD]
    if not rows:
        return None
    return {
        "key": "person_reach",
        "group": "strength",
        "names": [r["label"] for r in rows],
        "title": f"{_and([r['label'] for r in rows])} は情報の伝達力が強いです",
        "detail": f"つながっている相手は {_nums((r['direct'] for r in rows), '名')} で、"
                  f"他の人どうしの経路の "
                  f"{_nums(f'{r['betweenness']:.1%}' for r in rows)} が"
                  f"{_these(rows)}を通ります。"
                  "研究によると、少人数でも強いつながりを持つ人を通して、"
                  "情報はより遠くまで広がるとされています。",
        "page": "influence.html",
    }


# ------------------------------------------------------------ ハブとなっている人


def _vulnerability(rows: list) -> dict | None:
    """その人が抜けると社内から切り離される人が出る人を出す。

    社外の窓口が1人であること自体は珍しくないため、社内が切り離される人を先に出す。
    """
    inside: list[tuple] = []
    outside: list[tuple] = []
    for f in rows:
        for g in f.extra.get("separated_groups") or []:
            kinds = g.get("groups") or []
            box = inside if any(
                str(x["group"]) != EXTERNAL_GROUP for x in kinds
            ) else outside
            box.append((g["size"], f, g))

    if inside:
        picked = sorted(inside, key=lambda t: -t[0])[:PER_CARD]
        names: list[str] = []
        parts: list[str] = []
        for _n, f, g in picked:
            names.append(f.entity_label)
            names += [str(x["group"]) for x in (g.get("groups") or [])]
            parts.append(f"{f.entity_label} が抜けると{_who(g)}")
        return {
            "key": "person_separates_internal",
            "group": "gap",
            "names": names,
            "title": f"{_and([f.entity_label for _n, f, _g in picked])} は"
                     "部門間のつながりを作っています",
            "detail": "、".join(parts) + "が社内の他の人とつながらなくなります。"
                      "後任には、この関係の引き継ぎが要ります。",
            "page": "vulnerability.html",
        }

    if not outside:
        return None
    picked = sorted(outside, key=lambda t: -t[0])[:PER_CARD]
    return {
        "key": "person_separates_external",
        "group": "gap",
        "names": [f.entity_label for _n, f, _g in picked]
                 + [g["summary"] for _n, _f, g in picked],
        "title": f"{_and([f.entity_label for _n, f, _g in picked])} は"
                 "社外との唯一の窓口になっています",
        "detail": "相手は "
                  + "、".join(g["summary"] for _n, _f, g in picked)
                  + " です。窓口が1人であること自体は珍しくありません。"
                  "引き継ぎが要るかどうかは、その相手との取引で決まります。",
        "page": "vulnerability.html",
    }


# ------------------------------------------------------------ 発想の起点となる人


def _ideation(rows: list) -> dict | None:
    """つながっている相手どうしの重なりが少ない人を出す。"""
    openers = sorted(
        [f for f in rows if f.value is not None], key=lambda f: f.value
    )[:PER_CARD]
    if not openers:
        return None
    return {
        "key": "person_open",
        "group": "strength",
        "names": [f.entity_label for f in openers],
        "title": f"{_and([f.entity_label for f in openers])} は"
                 "新しい発想が出やすい位置にいます",
        "detail": "つながっている相手は "
                  + _nums((f.extra["degree"] for f in openers), "名")
                  + " で、"
                  "その相手どうしがつながっている組は "
                  + _nums(f"{f.extra['alters_linked_share']:.0%}" for f in openers)
                  + " です。研究によると、異なる集団と繋がっている人ほど、"
                  "片方で知ったことをもう片方に持ち込めるため、"
                  "よい提案を出しやすいとされています。",
        "page": "ideation.html",
    }


# ------------------------------------------------------------ 部門のつながり


def _silo(rows: list) -> dict | None:
    """つながりが部門の中で閉じている部門を出す。

    外との接点が残っていない部門を、程度の問題より先に出す。
    """
    zero = sorted(
        [f for f in rows if f.extra.get("no_external_contact")],
        key=lambda f: -f.extra.get("member_count", 0),
    )
    over = sorted(
        [f for f in rows
         if f.status != "ok" and not f.extra.get("no_external_contact")],
        key=lambda f: -(f.extra.get("times_random") or 0),
    )
    picked = (zero + over)[:PER_CARD]
    if not picked:
        return None

    parts = []
    for f in picked:
        if f.extra.get("no_external_contact"):
            parts.append(f"{f.entity_label}には、部門の外とのつながりが"
                         "ほとんどありません")
        else:
            parts.append(f"{f.entity_label}は、つながりの "
                         f"{f.extra['internal_share']:.0%} が部門の中です")
    return {
        "key": "dept_no_external" if zero else "dept_ie_over",
        "group": "gap",
        "names": [f.entity_label for f in picked],
        "title": _and([
            f"{f.entity_label}（{f.extra.get('member_count', 0)}名）" for f in picked
        ]) + "は、つながりが部門の中で閉じています",
        "detail": "。".join(parts) + "。"
                  "他部門の動きは、これらの部門には届きにくい状態です。",
        "page": "silo.html",
    }


# ------------------------------------------------------------ 部門の型


def _teams(rows: list) -> dict | None:
    """典拠が成果と結び付けている2つの型を、1つずつ出す。"""
    # その型らしさが最も強い部門を選ぶ。型の定義そのもので順位を付ける
    strongest = {
        # 効率型は2つとも高いほどそれらしい
        "efficiency": lambda e: e["density_vs_median"] * e["range_vs_median"],
        # イノベーション型は、外が広く中が薄いほどそれらしい
        "innovation": lambda e: e["range_vs_median"] / (e["density_vs_median"] or 1e-9),
    }
    picked = []
    for reading, label in (("innovation", "イノベーション型"), ("efficiency", "効率型")):
        same = [f for f in rows if f.extra.get("reading") == reading]
        if same:
            picked.append((max(same, key=lambda f: strongest[reading](f.extra)), label))
    if not picked:
        return None

    title = "、".join(
        f"{f.entity_label}（{f.extra['size']}名）は{label}" for f, label in picked
    ) + "です"
    parts = []
    for f, label in picked:
        if label == "イノベーション型":
            parts.append(f"{f.entity_label}は部門の外に "
                         f"{f.extra['external_alters']}名 とつながっています")
        else:
            parts.append(f"{f.entity_label}はメンバーどうしのつながりが"
                         f"中央値の {f.extra['density_vs_median']:.2f}倍 です")
    why = ("研究によると、前者は新しい発想を生み、後者は納期を守るとされています。"
           if len(picked) == 2 else
           "研究によると、この形は成果と結び付くとされています。")
    return {
        "key": "team_shape",
        "group": "strength",
        "names": [f.entity_label for f, _l in picked],
        "detail": "。".join(parts) + "。" + why,
        "title": title,
        "page": "teams.html",
    }


# ------------------------------------------------------------ 文字列を組み立てる


def _and(labels: list[str]) -> str:
    """「伊藤095、吉田041」のように並べる。"""
    return "、".join(labels)


def _nums(values, unit: str = "") -> str:
    """「6名・5名」のように、2人分の値を1つの語に収める。

    単位は値ごとに付ける。「6・5名」と書くと、6 が何の数なのかが読み取れない。
    """
    return "・".join(f"{v}{unit}" for v in values)


def _these(rows: list) -> str:
    """文の中で何人を指しているかを書く。「この2人」「この人」を取り違えない。"""
    return f"この{len(rows)}人" if len(rows) > 1 else "この人"


def _who(group: dict) -> str:
    """切り離される集団を「管理本部の6名」のように書く。

    部門がまたがるときだけ内訳を出す。1部門なら「部門名の N名」で足りる。
    """
    kinds = group.get("groups") or []
    if len(kinds) == 1:
        return f"{kinds[0]['group']}の{group['size']}名"
    return f"{group['summary']} の計{group['size']}名"
