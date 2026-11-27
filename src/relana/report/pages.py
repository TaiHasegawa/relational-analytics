"""複数ページのHTMLレポートを書き出す。

指標ごとにページを分け、共通のナビゲーションで行き来する。
表は並べ替えと絞り込みができ、ネットワーク図は分析ごとに色・大きさ・表示範囲を切り替えられる。
"""

from __future__ import annotations

import html
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..core.analyze import Snapshot
from ..core.graph import GraphBundle
from ..core import citations
from ..core.metrics import influence
from . import svg
from .assets import APP_JS, CSS, GRAPH_CSS, GRAPH_JS
from .graph_data import build as build_graph

PAGES = [
    ("index.html", "概要", "", ""),
    ("graph.html", "ネットワーク図", "", ""),
    ("influence.html", "インフルエンサー", "influence", "情報伝達の効率が良いのは誰か"),
    ("vulnerability.html", "ハブとなっている人", "vulnerability",
     "部門間のつながりを作っているのは誰か"),
    ("ideation.html", "発想の起点となる人", "ideation", "新しい発想が出やすい位置にいるのは誰か"),
    ("silo.html", "部門のつながり", "silo", "どの部門が内向きになっているか"),
    ("teams.html", "部門の型", "team", "効率型かイノベーション型か"),
    ("data.html", "データ", "", ""),
    ("sources.html", "出典", "", ""),
]


def write(
    snap: Snapshot,
    bundle: GraphBundle,
    outdir: Path,
) -> Path:
    outdir = Path(outdir)
    (outdir / "assets").mkdir(parents=True, exist_ok=True)
    (outdir / "assets" / "style.css").write_text(CSS + GRAPH_CSS, encoding="utf-8")
    (outdir / "assets" / "app.js").write_text(APP_JS, encoding="utf-8")
    (outdir / "assets" / "graph.js").write_text(GRAPH_JS, encoding="utf-8")

    by = _index(snap.findings)
    pages = {
        "index.html": _index_page(snap, by),
        "graph.html": _graph_page(snap, bundle),
        "silo.html": _silo_page(by),
        "vulnerability.html": _vuln_page(by, snap.window_days, bundle),
        "influence.html": _influence_page(snap, by),
        "ideation.html": _ideation_page(by),
        "teams.html": _team_page(by),
        "data.html": _data_page(snap),
        "sources.html": _sources_page(),
    }
    for name, body in pages.items():
        wide = name == "graph.html"
        extra = "<script src='assets/graph.js' defer></script>" if wide else ""
        (outdir / name).write_text(_shell(snap, name, body, wide, extra), encoding="utf-8")
    return outdir / "index.html"


# ---------------------------------------------------------------- 外枠


def _shell(snap: Snapshot, current: str, body: str, wide: bool, extra_head: str = "") -> str:
    title = next((t for f, t, _, _ in PAGES if f == current), "レポート")
    nav = "".join(
        f"<a href='{f}'{' aria-current=\"page\"' if f == current else ''}>{_e(t)}</a>"
        for f, t, _, _ in PAGES
    )
    return (
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{_e(title)} — リレーショナル分析 {_e(snap.snapshot_id)}</title>"
        "<link rel='stylesheet' href='assets/style.css'>"
        f"{extra_head}"
        "</head><body>"
        "<div class='topbar'><div class='inner'>"
        f"<div class='brand'>リレーショナル分析<small>{_e(snap.snapshot_id)}　"
        f"{snap.window_start} 〜 {snap.window_end}</small></div>"
        f"<nav class='nav'>{nav}</nav>"
        "</div></div>"
        f"<div class='wrap{' wide' if wide else ''}'>{body}</div>"
        "<script src='assets/app.js' defer></script>"
        "</body></html>"
    )


def _footer() -> str:
    return (
        "<footer>"
        "<p class='sub'>出典: レオナルディ／コントラクター"
        "「Better People Analytics」Harvard Business Review 2018年11-12月号"
        "（邦訳『ピープルアナリティクスで人事戦略が変わる』第5章）。"
        "<a href='sources.html'>出典</a></p>"
        "</footer>"
    )


# ---------------------------------------------------------------- 概要


def _index_page(snap: Snapshot, by: dict) -> str:
    """概要は、この分析が何かと、5つの分析の入口だけを置く。

    打ち手と図はそれぞれのページにある。概要にも並べると、同じものが2か所に出る。
    """
    q = snap.quality

    s = ["<h1>リレーショナル分析レポート</h1>"]
    s.append(
        f"<p class='lede'>{snap.window_start} から {snap.window_end} までの会議 "
        f"{q['interactions']:,}件から、{q['persons_in_master']}名のつながりを集計しました。</p>"
    )

    s.append(_about_block(snap))
    s.append(_analyses_block(snap, by, snap.highlights))
    s.append(_inferred_groups_note(snap.groups_source))
    s.append(_footer())
    return "".join(s)


def _about_block(snap: Snapshot) -> str:
    """何をどう測った分析なのかを、数値より先に短く置く。

    利用者はネットワーク分析を知らない。結果から読み始めると、
    「会議の同席だけで何が言えるのか」が分からないまま数値を受け取ることになる。
    細かい内訳は「データ」ページにあるので、ここは2行で止める。
    """
    s = ["<h2>この分析について</h2>"]
    s.append(
        "<p class='lede'><b>誰と誰がつながっているか</b>から組織を見る方法を、"
        "リレーショナルアナリティクスといいます。"
        "経歴・スキル・評価点は、その人ひとりを見れば分かるもの（属性）です。"
        "ここでは、いくつかの調査や研究に基づいて、"
        "<b>その属性では測れない、組織の中でのその人の位置</b>を見ます。"
        "元になった研究では、つながり方のいくつかの形が業績と結び付くとしています。"
        "このレポートは、その形を会議の同席記録だけから"
        "<b>簡易的に測ったもの</b>です。アンケートは取っていません。"
        "<a href='sources.html'>出典</a></p>"
    )
    rows = [
        ("データ",
         "カレンダーの参加者と日時だけです。"
         "会議の中身・件名・場所は取得していません。チャットとメールも見ていません。"
         "<a href='data.html'>内訳</a>"),
        ("分析内容",
         "インフルエンサー／ハブとなっている人／発想の起点となる人／部門のつながり／部門の型 の5つです。"
         "それぞれ何を数えたかは下に書いています。"),
    ]
    s.append("<dl class='about'>")
    for k, v in rows:
        s.append(f"<dt>{_e(k)}</dt><dd>{v}</dd>")
    s.append("</dl>")
    return "".join(s)


def _analyses_block(snap: Snapshot, by: dict, hi: dict) -> str:
    """5つの分析それぞれを、名前・問い・この組織での結果 の3段で1枚に出す。

    利用者はこのレポートで何をしているかを知らない。指標名と数値だけを並べても、
    何が分かるのかが伝わらない。**その分析が答える問い**を1行で言い、
    氏名と数値の入った結果を置く。

    2段目は**人事が判断したいこと**を問いの形で書く。数え方はここに書かない。
    数え方を読んでも、どの分析を開けばよいかは決められない。
    何をどう数えたかは、移った先のページの冒頭にある。

    カードの見出しは、上の「見るもの」と左の目次と**同じ分析名**にする。
    カードごとに別の言い回しを付けると、同じものを指しているかどうかが分からない。

    結果の文は src/relana/core/summary.py が選ぶ。どれを代表にするかは
    指標ごとの判断なので、レポート側で選び直さない。
    """
    ex = snap.highlights.get("examples") or {}

    silos = [f for f in by.get("ie_ratio", []) if f.status in ("warning", "critical")]
    vuln = by.get("node_criticality", [])
    div = hi.get("influence_divergence", [])
    constraint = by.get("constraint", [])
    teams = by.get("density_x_range", [])

    silo_note = f"基準を超えた部門は{len(silos)}つです"

    cards = [
        ("influence.html", "インフルエンサー",
         "情報伝達能力が高いのは誰か",
         f"直接の相手が少ないのに情報の通り道になっている人は{len(div)}名です",
         "算出できる人がいません。"),
        ("vulnerability.html", "ハブとなっている人",
         "部門間のつながりを作っているキーパーソンは誰か",
         f"該当は{len(vuln)}名です", "抜けると誰かが孤立する人はいません。"),
        ("ideation.html", "発想の起点となる人",
         "新しい発想が出やすい位置にいるのは誰か",
         f"{len(constraint)}名を部門ごとに並べています",
         "算出できる人がいません。"),
        ("silo.html", "部門のつながり",
         "部門同士はどのように繋がっているのか",
         silo_note, "基準を超えた部門はありません。"),
        ("teams.html", "部門の型",
         "それぞれの部門は効率型かイノベーション型か",
         f"{len(teams)}部門を分類しました",
         "分類できる部門がありません。"),
    ]

    s = ["<h2>この分析で分かること</h2>"]
    s.append("<div class='anas'>")
    for href, name, question, note, empty in cards:
        rows = ex.get(href) or []
        s.append(f"<a class='ana' href='{href}'>")
        s.append(f"<div class='aq'>{_e(name)}</div>")
        s.append(f"<div class='aw'>{_e(question)}</div>")
        if rows:
            r = rows[0]
            names = r.get("names") or []
            s.append(
                f"<div class='ar'><p class='rt'>{_emph(r['title'], names)}</p>"
                f"<p class='rd'>{_emph(r['detail'], names)}</p></div>"
            )
        else:
            s.append(f"<div class='ar'><p class='rt'>{_e(empty)}</p></div>")
        s.append(f"<div class='an'>{_emph(note)}</div>")
        s.append("</a>")
    s.append("</div>")
    return "".join(s)


def _card(label: str, value: Any, note: str, cls: str = "", href: str | None = None) -> str:
    inner = (
        f"<div class='k'>{_e(label)}</div><div class='v'>{_e(value)}</div>"
        f"<div class='n'>{_e(note)}</div>"
    )
    if href:
        return f"<a class='card {cls}' href='{href}'>{inner}</a>"
    return f"<div class='card {cls}'>{inner}</div>"


# ---------------------------------------------------------------- ネットワーク図


def _graph_page(snap: Snapshot, bundle: GraphBundle) -> str:
    """人を丸、同席した関係を線で描く。

    配置は Python 側で確定させてから渡す。力学シミュレーションを使うと
    開くたびに形が変わり、前回のレポートと見比べられなくなる。

    操作盤は置かない。色や大きさの基準を選ぶ欄を左に並べると、図そのものが
    横 880px ほどに縮み、氏名が重なって読めない。図は部門で塗り分けた1枚に固定し、
    横幅をすべて図に使う。何を描いていないかは右側の注記に書く。
    """
    data = build_graph(snap, bundle)
    st = data["stats"]
    s = ["<div class='graphpage'>"]

    s.append(
        "<div class='gstage'><svg id='gsvg' viewBox='0 0 900 640' "
        "preserveAspectRatio='xMidYMid meet'><g id='g-root'>"
        "<g id='g-links'></g><g id='g-nodes'></g>"
        "<g id='g-labels'></g><g id='g-clusters'></g></g></svg></div>"
    )

    s.append("<div class='gpanel right'>")
    for label, val in [
        ("人", f"{st['people']}"),
        ("関係", f"{st['edges']}"),
        ("うち 1on1", f"{st['dyads']}"),
        ("うち部門をまたぐ", f"{st['cross']}"),
        ("描いていない関係", f"{st['hidden']}"),
        ("氏名を出せた人", f"{len(data['labels'])}/{len(data['nodes'])}"),
    ]:
        s.append(f"<div class='gstat'><span>{_e(label)}</span><b>{_e(val)}</b></div>")
    s.append("<div class='legend' id='glegend'></div>")
    s.append(
        f"<div class='ghint'>重み <b>{data['min_weight']:.1f}</b>（1on1 を1回分）"
        "以上の関係だけを描いています。"
        f"これに満たない {data['hidden_links']} 本は描いていません。"
        "全員に同じ基準を当てているので、線の多い人は実際に関係が多い人です。"
        "<b>人にカーソルを合わせると、その人とつながっている相手の氏名が出ます。</b>"
        "人をクリックすると下に指標が出ます。"
        "同じ部門の人は近くに置き、他部門と強くつながっている人は"
        "かたまりの縁に寄せています。"
        "<b>配置は固定で、開くたびに同じ形になります。</b></div>"
    )
    s.append(
        "<hr style='border:none;border-top:1px solid var(--line);margin:14px 0'>"
        "<div id='gselected'></div>"
    )
    s.append("</div>")

    s.append("</div>")
    s.append(
        "<script>window.RELANA_GRAPH="
        + json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        + ";</script>"
    )
    return "".join(s)


def _page_head(title: str, question: str) -> str:
    return f"<h1>{_e(title)}</h1><p class='lede'>{_e(question)}</p>"


def _inferred_groups_note(groups_source: str) -> str:
    """部門をカレンダーから推定したときに、その旨を書く。

    推定した区分で「区分間の往来が少ない」と測ると循環論法になりかねない。
    """
    if groups_source != "inferred":
        return ""
    return (
        "<p class='note limit'><b>部門はカレンダーから推定したものです。</b>"
        "推定した区分で「区分間の往来が少ない」と測ると循環論法になりかねないため、"
        "部門のつながりの結果は下書きとして扱ってください。</p>"
    )


_FEATURE_PAGE = {
    "influence": "インフルエンサー",
    "vulnerability": "ハブとなっている人",
    "ideation": "発想の起点となる人",
    "silo": "部門のつながり",
    "team": "部門の型",
    "roles": "概要（役割）",
}


def _sources(feature: str) -> str:
    """このページの数値がどこから来たかを1行で示し、出典ページへ送る。

    書誌をページの中に並べると、数値と打ち手の間に文献が挟まって読みにくい。
    著者名だけを出し、詳しくは出典ページで読めるようにする。
    """
    cites = citations.for_feature(feature)
    if not cites:
        return ""
    names = "／".join(c.short for c in cites)
    return (
        f"<p class='srcline'>この数値の出典: {_e(names)}。"
        f"<a href='sources.html#{_e(feature)}'>定義と、研究にない部分を見る</a></p>"
    )


def _sources_page() -> str:
    """参考にした文献を1ページにまとめる。

    どのページの数値がどの文献の定義に沿ったものか、
    どこからが典拠になく自分で決めたものかを、ここだけで読み切れるようにする。
    """
    s = ["<h1>出典</h1>"]
    s.append(
        "<p class='lede'>このレポートの数値が、どの文献の定義に沿ったものかを書きます。"
        "基準にした数値や補正には、文献にないものも含まれます。"
        "どれがそれに当たるかは、下の「分析ごとの出典」に分けて書いています。</p>"
    )

    s.append("<h2>分析ごとの出典</h2>")
    for feature, label in _FEATURE_PAGE.items():
        cites = citations.for_feature(feature)
        if not cites:
            continue
        page = next((f for f, _t, k, _q in PAGES if k == feature), "index.html")
        s.append(f"<div class='person' id='{_e(feature)}'>")
        s.append(f"<h4><a href='{page}'>{_e(label)}</a></h4>")
        s.append("<ul class='citelist'>")
        for c in cites:
            s.append(f"<li><b>{_e(c.short)}</b>　{_e(c.basis)}</li>")
        s.append("</ul>")
        own = citations.OWN_CHOICES.get(feature)
        if own:
            s.append(f"<p class='note limit'><b>研究にない部分</b>　{_e(own)}</p>")
        s.append("</div>")

    s.append("<h2>文献</h2>")
    used: dict[str, list[str]] = {}
    for feature, keys in citations.BY_FEATURE.items():
        for k in keys:
            used.setdefault(k, []).append(_FEATURE_PAGE.get(feature, feature))
    s.append("<dl class='cite'>")
    for key, c in citations.CITATIONS.items():
        pages = "、".join(dict.fromkeys(used.get(key, [])))
        title = f"<a href='{_e(c.url)}'>{_e(c.title)}</a>" if c.url else _e(c.title)
        s.append(
            f"<dt>{_e(c.short)}</dt>"
            f"<dd>{_e(c.authors)}（{_e(c.year)}）{title}"
            f"<span class='sub'>{_e(c.where)}</span>"
            + (f"<span class='took'>使っているページ: {_e(pages)}</span>" if pages else "")
            + "</dd>"
        )
    s.append("</dl>")

    s.append("<h2>この OSS が自分で決めたこと</h2>")
    s.append(
        "<p class='lede'>次の3つは、上の文献にありません。"
        "設計の理由は <code>docs/requirements.md</code> に書いています。</p>"
    )
    s.append(
        "<ul>"
        "<li>会議の人数と長さから関係の重みを出す式</li>"
        "<li>関係とみなす重みの下限</li>"
        "<li>部門をカレンダーから推定する手順</li>"
        "</ul>"
    )
    s.append(_footer())
    return "".join(s)


def _silo_page(by: dict) -> str:
    rows = sorted(by.get("ie_ratio", []),
                  key=lambda f: -(f.value if f.value is not None else 1e9))
    s = [_page_head("部門のつながり", "どの部門が内向きになっているか")]
    if not rows:
        return "".join(s) + _footer()
    s.append(
        "<p class='lede'>その部門のつながりのうち、部門の中だけのものが何割かを数えます。"
        "研究では、部門内が部門外の <b>5倍を超えると有害な水準</b> としています。"
        "業務上の関連がない部門どうしなら、つながりがなくても支障はありません。"
        "打ち手は、往来を増やしたい場合のものです。"
        "この割合は部門の人数に左右されるため、"
        "<b>ランダムにつながっていた場合の割合</b>を併せて出しています。</p>"
    )
    matrix = by.get("dept_matrix", [])
    if matrix:
        m = matrix[0].extra
        s.append("<h2>部門間の往来（1ペアあたり）</h2><div class='panel'>")
        s.append("<div class='scroll'>" + svg.heatmap(m["labels"], m["sizes"], m["per_pair"]) + "</div>")
        s.append(
            "<p class='note'><b>数字が大きいマスほど、その2つの部門の人が"
            "よくつながっています。</b>"
            "<b>見るのは、業務上つながる必要があるのに数字が小さい組</b>です。"
            "<b>断絶</b> は、継続的と言える接点が残らなかった組です。"
            "縦と横が同じ部門になるマス（左上から右下への対角）は部門の中で、"
            "ほかより桁が大きくなるため、色の濃さは対角以外だけで比べてください。"
            "数字は、2人組1つあたりのつながりの量です"
            "（<a href='data.html'>内訳</a>）。</p></div>"
        )
    s.append("<h2>部門ごとの、部門の中だけのつながり</h2>")
    s.append(_table(
        "silo-table",
        ["部門", "人数", "部門の中だけのつながり", "", "ランダムならこの割合", "判定の基準", "判定"],
        [
            [
                _e(f.entity_label),
                f"<span data-v='{f.extra['member_count']}'>{f.extra['member_count']}</span>",
                f"<span data-v='{f.extra['internal_share']}'>{f.extra['internal_share']:.0%}</span>",
                svg.bar(f.extra["internal_share"], 1.0, "--mut"),
                f"<span data-v='{f.extra['expected_share']}'>{f.extra['expected_share']:.0%}</span>",
                f"<span data-v='{f.extra.get('threshold_share') or 0}'>"
                f"{(f.extra.get('threshold_share') or 0):.0%}</span>",
                _tag(f.status),
            ]
            for f in rows
        ],
        nums=[1, 2, 4, 5],
        search=True,
    ))
    small = min(rows, key=lambda f: f.extra["member_count"])
    big = max(rows, key=lambda f: f.extra["member_count"])
    s.append(
        "<p class='note'><b>「部門の中だけのつながり」が「ランダムならこの割合」を"
        "大きく上回るほど、その部門は中で閉じています。</b>"
        "人数の多い部門は、何もしなくても中の割合が高く出ます。"
        f"全{sum(f.extra['member_count'] for f in rows)}名の会社で、誰とでも等しくつながる人なら、"
        f"{small.extra['member_count']}名の部門で {small.extra['expected_share']:.0%}、"
        f"{big.extra['member_count']}名の部門で {big.extra['expected_share']:.0%} です。"
        "そのぶんを差し引いて見るために、右の列を併記しました。"
        "判定の基準は、研究の「部門内が部門外の5倍」を、その部門の人数に当てはめて出しています。</p>"
    )
    gaps = [f for f in by.get("disconnected_pair", []) if f.status == "critical"]
    for f in rows:
        if f.status not in ("warning", "critical") or not f.suggested_actions:
            continue
        e = f.extra
        zero = e.get("zero_contact_depts") or []
        if e.get("no_external_contact"):
            parts = [
                f"{_e(f.entity_label)}（{e['member_count']}名）には、"
                f"他部門との継続的な接点が <b>残っていません</b>",
                f"1回だけの大人数の会議のように証拠の弱い記録を除くと、"
                f"他の{len(zero)}部門（{_e('、'.join(zero))}）との接点が1件も残りません",
            ]
        else:
            parts = [
                f"{_e(f.entity_label)}（{e['member_count']}名）のつながりのうち、"
                f"<b>{e['internal_share']:.0%}</b> が部門の中だけです"
            ]
            if e.get("expected_share") is not None:
                parts.append(
                    f"同じ人数の部門がランダムにつながっていれば "
                    f"<b>{e['expected_share']:.0%}</b> で、"
                    f"判定の基準は {(e.get('threshold_share') or 0):.0%} です"
                )
            if zero:
                parts.append(f"接点が残っていない相手は {_e('、'.join(zero[:3]))} です")
        s.append(f"<h3>{_e(f.entity_label)}</h3>")
        s.append(_actions_block(
            f.suggested_actions,
            problem="。".join(parts) + "。",
            goal="この部門と他部門の往来を増やしたい場合",
        ))
    if gaps:
        s.append("<h2>継続的な接点が残っていない部門の組</h2><ul>")
        for f in gaps[:20]:
            s.append(f"<li>{_e(f.entity_label)}</li>")
        s.append("</ul>")
        s.append("<p class='note limit'>業務上の関連がない部門間なら、接点がなくても支障はありません。"
                 "つながる必要がある組だけを選んで対処してください。</p>")
    s.append(_limits(rows[0]))
    s.append(_sources("silo"))
    s.append(_footer())
    return "".join(s)


# -------------------------------------------------------- ハブとなっている人


def _missing_names(c: dict) -> str:
    """引き継ぎに足りない接点を、ID ではなく氏名で書く。"""
    names = c.get("missing_labels") or c.get("missing_links") or []
    if not names:
        return ""
    shown = "、".join(str(x) for x in names[:3])
    rest = c.get("missing_count", len(names)) - len(names[:3])
    tail = f" ほか{rest}名" if rest > 0 else ""
    return f"（{_e(shown)}{tail}）"


def _separated_block(groups: list[dict], label: str) -> str:
    """その人を除くと、どの集団が他の社員とつながらなくなるかを書く。"""
    if not groups:
        return ""
    s = [f"<h3>{_e(label)} が抜けるとつながらなくなる集団</h3>"]
    s.append(
        f"<p class='sub'>下の集団の人がつながっている相手は、同じ集団の中の人と {_e(label)} だけです。"
        f"{_e(label)} が抜けると、社内の他の{groups[0]['main_size']}名との接点がなくなります。</p>"
    )
    for i, grp in enumerate(groups, start=1):
        comp = "／".join(f"{x['group']} {x['count']}名" for x in grp["groups"])
        s.append("<div class='sepgrp'>")
        s.append(f"<div class='seph'><b>集団{i}</b><span>{grp['size']}名</span>"
                 f"<span class='sub'>{_e(comp)}</span></div>")
        chips = "".join(
            f"<span class='chip'>{_e(m['label'])}<i>{_e(m['group'])}</i></span>"
            for m in grp["members"]
        )
        if grp["omitted"]:
            chips += f"<span class='chip more'>ほか{grp['omitted']}名</span>"
        s.append(f"<div class='sepm'>{chips}</div>")
        s.append("</div>")
    return "".join(s)


def _neighborhood(bundle: GraphBundle, f) -> tuple[str, str]:
    """その人の周りだけを切り出した関係図を作る。

    全体図ではどこで効いているのかが見えない。つながっている相手を**部門ごとの列**に
    まとめ、社内の他の人とつながる道がその人しかない相手を赤で出す。
    """
    g = bundle.undirected
    pid = f.entity_id
    if pid not in g:
        return "", ""
    cut_ids: list[str] = []
    for grp in f.extra.get("separated_groups") or []:
        cut_ids += [m["person_id"] for m in grp.get("members", [])]
    # 切り離される集団がない人でも、社外の唯一の窓口なら同じ形で見せる
    cut_ids += [c["entity"] for c in f.extra.get("sole_external_contacts") or []]
    cut_set = {n for n in cut_ids if n in g}
    label = f.entity_label
    cut_label = f"{label} が抜けると社内から切り離される相手"
    keep_label = f"{label} を通さなくても社内とつながる相手"
    cuts_someone = True
    nbrs = list(g.neighbors(pid))
    if not cut_set:
        # 切り離される集団がない人は、その人としかつながっていない相手を赤で出す
        peers = set(nbrs)
        cut_set = {
            n for n in nbrs
            if not any(m in peers for m in g.neighbors(n) if m != pid)
        }
        cut_label = f"{label} としかつながっていない相手"
        keep_label = f"{label} のほかの相手とも直接つながっている相手"
        cuts_someone = False
    if not cut_set:
        return "", ""

    # 切り離される人には、その人の相手の先にいる人も含まれる。
    # 直接つながっている相手だけに絞ると、切り離される集団が図から欠ける
    members = []
    for n in list(dict.fromkeys(nbrs + sorted(cut_set))):
        d = g.nodes[n]
        members.append({
            "label": d.get("display_name") or n,
            "group": "（社外）" if d.get("is_external") else (d.get("dept") or ""),
            "cut": n in cut_set,
        })
    note = (
        f"<b>中央が {_e(label)}、下に並ぶのが周りにいる人です。列は部門ごとで、"
        "見出しの人数は、その部門から図に出している人数です。</b>"
        + (
            f"<b>赤い丸の人は、社内の他の人とつながる道が {_e(label)} しかありません。</b>"
            if cuts_someone
            else f"<b>赤い丸の人は、{_e(label)} のほかの相手とは直接つながっていません。</b>"
        )
        + f"灰色の丸の人は、{_e(label)} を通さなくても社内とつながります。"
        "中心から引いた線は部門までで、相手1人ずつには引いていません。"
        "1つの部門に13名以上いるときは、下に残りの人数を書いています。"
    )
    return note, svg.neighborhood(
        g.nodes[pid].get("display_name") or pid,
        g.nodes[pid].get("dept") or "",
        members,
        cut_label=cut_label,
        keep_label=keep_label,
    )


def _vuln_page(by: dict, window_days: int, bundle: GraphBundle | None = None) -> str:
    # 部門の組が切れる人を先に出す。このページの問いは「部門間をつないでいるのは誰か」
    rows = sorted(
        by.get("node_criticality", []),
        key=lambda f: (
            f.extra.get("dept_pairs_kept") if f.extra.get("dept_pairs_kept") is not None else 1.1,
            f.extra["replaceability"],
        ),
    )
    s = [_page_head("ハブとなっている人", "部門間のつながりを作っているのは誰か")]
    s.append(
        "<p class='lede'><b>複数の部門を繋いでいる人</b>を抽出します。"
        "部門間を繋いでいる人の異動や離職は、部門間の連携を損なうことがあります。</p>"
    )
    if not rows:
        s.append("<div class='panel'>該当者は検出されませんでした。</div>")
        return "".join(s) + _footer()

    s.append(_table(
        "vuln-table",
        ["人", "部門", "代わりの人がいる部門の組", "媒介中心性",
         "誰ともつながらなくなる人", "判定"],
        [
            [
                f"<a href='#{_slug(f.entity_id)}'>{_e(f.entity_label)}</a>",
                _e(f.extra.get("dept") or ""),
                _dept_pairs_cell(f.extra),
                f"<span data-v='{f.extra['betweenness']}'>{f.extra['betweenness']:.4f}</span>",
                f"<span data-v='{f.extra.get('disconnected_persons', 0)}'>"
                f"{f.extra.get('disconnected_persons', 0)}名</span>",
                _tag(f.status),
            ]
            for f in rows
        ],
        nums=[2, 3, 4],
    ))
    s.append(
        "<p class='note'><b>「代わりの人がいる部門の組」</b>は、その人がつないでいる"
        "部門の組（社外はまとめて1つの区分として数えます）のうち、"
        "<b>その人以外にもその2部門をつないでいる人がいる組</b>の割合です。"
        "<b>0% なら、その人が抜けたときにその部門との接点が残りません。</b>"
        "100% なら、すべての組に代わりの人がいます。"
        "かっこの中は<b>関わっている部門の組の数</b>で、"
        "切れる組があるときは<b>そのうち何組が切れるか</b>も書いています。"
        "部門をまたぐ接点がない人は <b>—</b> です。"
        "各人の欄にある<b>「代わりの人がいる相手どうしの組」</b>は、部門ではなく人で同じことを数えたもので、"
        "その人がつないでいる相手どうしの組のうち、"
        "<b>その人以外にも両方とつながっている人がいる組</b>の割合です。</p>"
    )

    # 1人分は開閉できる枠にする。10人分を全部開くとページが長く、目当ての人に
    # たどり着けない。最初の1人だけ開いておき、表のリンクから飛んだ人は JS で開く
    for i, f in enumerate(rows[:10]):
        e = f.extra
        role = f" / {_e(e.get('role'))}" if e.get("role") else ""
        s.append(f"<details class='person' id='{_slug(f.entity_id)}'{' open' if i == 0 else ''}>")
        s.append(f"<summary><h4>{_e(f.entity_label)} {_tag(f.status)}"
                 f"<span class='role'>{_e(e.get('dept') or '')}{role}</span></h4></summary>")
        s.append("<div class='pbody'>")
        s.append(f"<p>{_emph(f.interprets_as, [f.entity_label])}</p>")
        s.append("<dl class='kv'>")
        s.append("<dt>代わりの人がいる部門の組</dt><dd>"
                 + _dept_pairs_cell(e) + "</dd>")
        s.append("<dt>代わりの人がいる相手どうしの組</dt><dd>"
                 f"{svg.bar(1 - e['replaceability'], 1, '--mut')}"
                 f"{e['replaceability']:.0%}</dd>")
        s.append(f"<dt>媒介中心性</dt><dd>{e['betweenness']:.4f}"
                 + (f"<span class='sub'>（全社 {_rank(f)}）</span>" if f.percentile else "")
                 + "</dd>")
        if e.get("disconnected_persons"):
            s.append("<dt>誰ともつながらなくなる人</dt>"
                     f"<dd>{e['disconnected_persons']}名</dd>")
        if e.get("meeting_load_hours"):
            s.append(f"<dt>会議時間</dt><dd>{e['meeting_load_hours']:.0f}時間／{window_days}日</dd>")
        s.append("</dl>")
        s.append(_separated_block(e.get("separated_groups") or [], f.entity_label))
        near_note, near = _neighborhood(bundle, f) if bundle else ("", "")
        if near:
            s.append(f"<h3>{_e(f.entity_label)} の周りのつながり</h3>")
            s.append("<div class='panel'><div class='scroll'>" + near + "</div>")
            s.append(f"<p class='note'>{near_note}</p></div>")
        bridged = e.get("bridged_groups") or []
        if any(not b.get("is_own") for b in bridged):
            s.append(f"<h3>{_e(f.entity_label)} がつながっている部門</h3>")
            s.append("<div class='panel'><div class='scroll'>"
                     + svg.ego(f.entity_label, bridged, e.get("dept") or "") + "</div>")
            soles = [b["group"] for b in bridged if b.get("sole_bridge")]
            who = _e(f.entity_label)
            note = (f"<b>中央が {who}、右に並ぶのが {who} がつながっている部門です。</b>"
                    f"<b>赤い線</b>は、{who} が抜けるとその部門との接点が0になる"
                    "ことを表します。灰色の線は、他の人も同じ部門とつながっている"
                    "ことを表します。線が太いほど、その部門と接点のある人が多い"
                    "ことを表します。")
            if soles:
                note += (f"ここでは {_e('、'.join(soles))} が赤い線です。")
            s.append(f"<p class='note'>{note}</p></div>")
        if e.get("succession_candidates"):
            s.append("<h3>引き継ぎ候補</h3>")
            s.append(_table(
                f"succ-{_slug(f.entity_id)}",
                ["候補", "つながりの重なり", "まだつながっていない相手"],
                [
                    [
                        _e(c["label"]),
                        f"<span data-v='{c['overlap']}'>"
                        f"{svg.bar(c['overlap'], 1, '--mut')}{c['overlap']:.0%}</span>",
                        f"<span class='sub'>{c['missing_count']}件"
                        + _missing_names(c)
                        + "</span>",
                    ]
                    for c in e["succession_candidates"]
                ],
                nums=[1],
                sortable=False,
            ))
        who = _e(f.entity_label)
        parts = [
            f"{who} がつないでいる相手どうしの組のうち <b>{1 - e['replaceability']:.0%}</b> は、"
            "代わりの人がいません"
        ]
        sole = e.get("sole_external_contacts") or []
        if sole:
            names = "、".join(x.get("label") or x["entity"] for x in sole)
            parts.append(f"{_e(names)} とつながっているのは社内で {who} だけです")
        cands = e.get("succession_candidates") or []
        if cands:
            c = cands[0]
            parts.append(
                f"いま最もつながりが重なるのは {_e(c['label'])}（<b>{c['overlap']:.0%}</b>）で、"
                f"{c['missing_count']}名とまだつながっていません"
            )
        if e.get("meeting_load_hours"):
            med = e.get("meeting_load_median_hours")
            tail = (
                f"で、全社の中央値{med:.0f}時間の <b>{e['meeting_load_hours'] / med:.1f}倍</b> です"
                if med
                else "です"
            )
            parts.append(
                f"{who} の会議時間は{window_days}日で"
                f"<b>{e['meeting_load_hours']:.0f}時間</b>{tail}"
            )
        s.append(_actions_block(
            f.suggested_actions,
            e.get("simulation"),
            problem="。".join(parts) + "。",
            goal=f"{f.entity_label} が抜けても接点が残るようにしたい場合",
        ))
        s.append(f"<p class='note limit'><b>この指標の限界</b>　{_e(f.does_not_mean)}</p>")
        s.append("</div></details>")
    s.append(_limits(rows[0]))
    s.append(_sources("vulnerability"))
    s.append(_footer())
    return "".join(s)


# ---------------------------------------------------------------- インフルエンサー


def _influence_page(snap: Snapshot, by: dict) -> str:
    rows = by.get("betweenness", [])
    div = snap.highlights.get("influence_divergence", [])
    s = [_page_head("インフルエンサー", "情報伝達の効率が良いのは誰か")]
    s.append(
        "<p class='lede'><b>情報伝達の経路にその人が居る度合い</b>（媒介中心性）を"
        "測定します。"
        "研究によると、最も強力なインフルエンサーの特徴を"
        "「少人数でも強力なつながりを持ち、その結び付きを通してアイデアがより遠くまで広がる」"
        "とされています。直接つながっている相手の数と並べることで、"
        "<b>直接の相手は少ないのに、情報の通り道になっている人</b>が分かります。"
        "隠れたキーマンの特定や、情報の周知・統制の参考にできます。</p>"
    )
    if rows:
        gap_ids = {d["person_id"] for d in div[:8]}
        points = [
            {
                "x": f.extra["direct_contacts"],
                "y": f.value or 0,
                "label": f.entity_label,
                "highlight": f.entity_id in gap_ids,
                "tip": (
                    f"<b>{_e(f.entity_label)}</b><br>{_e(f.extra.get('dept') or '')}"
                    f"<br>直接つながっている相手 {f.extra['direct_contacts']}名"
                    f"<br>他の人どうしの経路が通る割合 {f.value:.4f}"
                ),
            }
            for f in rows
            if (f.value or 0) > 0 and f.extra.get("direct_contacts") is not None
        ]
        s.append("<h2>直接つながっている相手の数と、経路の通りやすさ</h2><div class='panel'>")
        s.append(svg.scatter(points, "直接つながっている相手の数",
                             "他の人どうしの経路が通る割合（媒介中心性）",
                             x_unit="名", y_scale="log"))
        s.append("<p class='note'><b>情報伝達力の高いメンバーは図の上部に"
                 "配置されています。</b>"
                 "左上に表示されているメンバーは、直接繋がっている相手は少ないが、"
                 "媒介中心性が高い、すなわち情報の拡散能力が高いことを"
                 "示します。</p></div>")
    if div:
        s.append("<h2>直接の相手が少ないのに、情報の通り道になっている人</h2>")
        s.append(
            "<p class='sub'>他の人どうしの経路の"
            f"{influence.MIN_BETWEENNESS:.0%} 以上が通り、"
            f"直接つながっている相手が全社の中央値（{div[0]['direct_median']:.0f}名）"
            "以下の人です。順位ではなく実際の値で選んでいます。</p>"
        )
        s.append(_table(
            "inf-table",
            ["人", "部門", "直接つながっている相手", "他の人どうしの経路が通る割合（媒介中心性）"],
            [
                [
                    _e(r["label"]),
                    _e(r["dept"] or ""),
                    f"<span data-v='{r['direct']}'>{r['direct']}名</span>",
                    f"<span data-v='{r['betweenness']}'>{r['betweenness']:.4f}</span>",
                ]
                for r in div
            ],
            nums=[2, 3],
            search=True,
        ))
        top3 = div[:3]
        problem = (
            f"直接つながっている相手が全社の中央値（{div[0]['direct_median']:.0f}名）以下なのに、"
            f"他の人どうしの経路がよく通る人が <b>{len(div)}名</b> います。"
            + "。".join(
                f"{_e(r['label'])} がつながっているのは{r['direct']}名ですが、"
                f"他の人どうしの経路の <b>{r['betweenness']:.1%}</b> が {_e(r['label'])} を通ります"
                for r in top3[:2]
            )
            + "。つながりの多い人だけに説明すると、この人たちを飛ばすことになります。"
        )
        s.append(_actions_block([
            f"新しい方針を周知するとき、{_e('、'.join(r['label'] for r in top3))} に最初に説明する",
            "部門をまたぐ案件では、この人たちを連絡係に指名する",
        ], problem=problem, goal="新しい方針を全体に行き渡らせたい場合"))
    if rows:
        s.append("<h2>全員の値</h2>")
        s.append(_table(
            "inf-all",
            ["人", "部門", "他の人どうしの経路が通る割合（媒介中心性）", "直接つながっている相手"],
            [
                [
                    _e(f.entity_label),
                    _e(f.extra.get("dept") or ""),
                    f"<span data-v='{f.value}'>{f.value:.4f}</span>",
                    f"<span data-v='{f.extra['direct_contacts']}'>{f.extra['direct_contacts']}名</span>",
                ]
                for f in sorted(rows, key=lambda f: -f.value)
            ],
            nums=[2, 3],
            search=True,
        ))
        s.append(_limits(rows[0]))
    s.append(_sources("influence"))
    s.append(_footer())
    return "".join(s)


# ---------------------------------------------------------------- 発想の起点となる人


def _ideation_page(by: dict) -> str:
    rows = by.get("constraint", [])
    s = [_page_head("発想の起点となる人", "新しい発想が出やすい位置にいるのは誰か")]
    s.append(
        "<p class='lede'>つながっている相手どうしが、互いにどれだけつながっているかを"
        "数えます。<b>少ない</b>ほど、互いに行き来のない複数の集団の両方に"
        "顔を出していることになります。"
        "<b>順位はこの位置で付けています。</b>"
        "その人が実際に出した発想の数は数えていません。"
        "人数の違う集団を混ぜると順位が比較できないため、部門ごとに分けました。"
        "決まった相手と深く進める仕事なら、同じ顔ぶれに偏っていても支障はありません。"
        "打ち手は、部門をまたぐ発想を増やしたい場合のものです。</p>"
    )
    s.append(
        "<p class='note'><b>表の「制約」は、つながり相手どうしがどれだけ身内で"
        "固まっているかを 0〜1 で表した値です。</b>"
        "0 に近いほど、行き来のない複数の集団に顔を出しています。"
        "1 に近いほど、いつも同じ顔ぶれとつながっています。"
        "順位はこの値で付けました（研究が使っている指標です）。</p>"
    )
    if not rows:
        return "".join(s) + _footer()
    closed_depts = {
        f.entity_label for f in by.get("ie_ratio", []) if f.extra.get("no_external_contact")
    }
    groups: dict[str, list] = defaultdict(list)
    for f in rows:
        groups[f.comparison_group or ""].append(f)
    for group, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        vals = [f.value for f in items]
        top = sorted(items, key=lambda f: f.value)[:3]
        s.append(f"<h2>{_e(group)}<span class='q'>{len(items)}名</span></h2>")
        s.append("<div class='panel'>")
        s.append(svg.strip(
            vals,
            [{"value": t.value, "label": t.entity_label} for t in top],
            True,
            points=[
                {
                    "value": f.value,
                    "label": f.entity_label,
                    "tip": (
                        f"<b>{_e(f.entity_label)}</b>"
                        f"<br>つながっている相手 {f.extra['degree']}名"
                        f"（{f.extra['alter_dept_count']}部門）"
                        f"<br>その相手どうしがつながっている組 "
                        f"{f.extra['alters_linked_share']:.0%}"
                        f"<br>制約 {f.value:.3f}（部門内 {_rank(f)}）"
                    ),
                }
                for f in items
            ],
        ))
        s.append(
            "<p class='note'><b>左にいる人ほど、互いに行き来のない複数の集団に"
            "入っています。</b>右にいる人は、いつも同じ顔ぶれとつながっています。"
            "点はこの部門の1人で、カーソルを合わせると氏名と数値が出ます。</p>"
        )
        s.append("</div>")
        if group in closed_depts:
            s.append(
                "<p class='note'><b>この部門には他部門との継続的な接点が残っていません。</b>"
                "その扱いは<a href='silo.html'>部門のつながり</a>に書いています。"
                "ここでは、部門の中でのつながりの偏りだけを見ます。</p>"
            )
            acts = []
        else:
            acts = []
            for f in top:
                for a in f.suggested_actions:
                    if a not in acts:
                        acts.append(a)
        if acts:
            closed = [f for f in items if f.value >= 0.7]
            t0 = top[0]
            problem = (
                f"{_e(group)} {len(items)}名のうち、つながっている相手どうしが最もつながっていないのは "
                f"{_e(t0.entity_label)} です。{t0.extra['degree']}名"
                f"（{t0.extra['alter_dept_count']}部門）とつながっていますが、"
                f"その中で互いにつながっている組は <b>"
                f"{t0.extra['alters_linked_share']:.0%}</b> です"
            )
            if closed:
                problem += (
                    f"。一方で <b>{len(closed)}名</b> は、"
                    "いつも同じ顔ぶれとつながっています（制約 0.70 以上）"
                )
            problem += "。"
            s.append(_actions_block(
                [f"{_e('、'.join(t.entity_label for t in top))} について: " + acts[0]] + acts[1:],
                problem=problem,
                goal="部門をまたぐ発想を増やしたい場合",
            ))
        s.append(_table(
            f"ide-{abs(hash(group)) % 99999}",
            ["人", "つながっている相手", "その相手どうしがつながっている組", "部門数", "制約",
             "部門内の順位"],
            [
                [
                    _e(f.entity_label),
                    f"<span data-v='{f.extra['degree']}'>{f.extra['degree']}名</span>",
                    f"<span data-v='{f.extra['alters_linked_share']}'>"
                    f"{f.extra['alters_linked_share']:.0%}</span>",
                    f"<span data-v='{f.extra['alter_dept_count']}'>"
                    f"{f.extra['alter_dept_count']}</span>",
                    f"<span data-v='{f.value}'>{f.value:.3f}</span>",
                    f"<span data-v='{_rank_no(f) or 0}'>{_rank(f)}</span>",
                ]
                for f in sorted(items, key=lambda f: f.value)
            ],
            nums=[1, 2, 3, 4],
            search=True,
        ))
    s.append(_limits(rows[0]))
    s.append(_sources("ideation"))
    s.append(_footer())
    return "".join(s)


# -------------------------------------------------------------- 部門の型


def _team_page(by: dict) -> str:
    rows = by.get("density_x_range", [])
    s = [_page_head("部門の型", "効率型かイノベーション型か")]
    s.append(
        "<p class='lede'>メンバーどうしのつながりの濃さと、部門外の相手の広さの2つで分類します。"
        "研究では、メンバーどうしのつながりが濃く部門外にも広く相手がいる部門は納期を守り、"
        "メンバーどうしのつながりが<b>薄く</b>部門外に広く相手がいる部門は"
        "イノベーションを生むとしています。"
        "納期を守る仕事と新規探索の仕事では、望ましい型が逆になります。"
        "どの型がよいかは、その部門が担っている仕事で決まります。"
        "2つの値がどちらも全部門の中央値から2割の中に入る部門は、"
        "<b>中央値付近</b>として型を付けていません。</p>"
    )
    if not rows:
        return "".join(s) + _footer()
    teams = [
        {
            "label": f.entity_label,
            "internal_density": f.extra["internal_density"],
            "external_range": f.extra["external_range"],
            "size": f.extra["size"],
            "median_internal_density": f.extra["median_internal_density"],
            "median_external_range": f.extra["median_external_range"],
            "quadrant_label": f.extra["quadrant_label"],
        }
        for f in rows
    ]
    s.append("<div class='panel'>" + svg.quadrant(teams)
             + "<p class='note'><b>右へ行くほど部門外に広くつながり、"
               "上へ行くほどメンバーどうしが濃くつながっています。</b>"
               "右上が効率型、右下がイノベーション型です。"
               "点線は全部門の中央値で、この線の近くにある部門は、"
               "わずかな差で別の型に移ります。"
               "丸の大きさは部門の人数です。"
               "丸にカーソルを合わせると、その部門の数値が出ます。</p></div>")
    order = {"efficiency": 0, "innovation": 1, "closed": 2, "diffuse": 3}
    s.append(_table(
        "team-table",
        ["部門", "人数", "メンバーどうしのつながり", "部門外の相手",
         "相手1人あたりのメンバー", "型", "向いている仕事"],
        [
            [
                _e(f.entity_label),
                f"<span data-v='{f.extra['size']}'>{f.extra['size']}</span>",
                f"<span data-v='{f.extra['density_vs_median']}'>"
                f"中央値の {f.extra['density_vs_median']:.2f}倍</span>",
                f"<span data-v='{f.extra['external_alters']}'>{f.extra['external_alters']}名"
                f"<span class='sub'>中央値 {f.extra['typical_external_alters']}名</span></span>",
                f"<span data-v='{f.extra['members_per_alter'] or 0}'>"
                f"{(f.extra['members_per_alter'] or 0):.1f}名</span>",
                _e(f.extra["quadrant_label"]),
                f"<span class='sub'>{_e(_fit(f.extra['reading']))}</span>",
            ]
            for f in sorted(rows, key=lambda f: order.get(f.extra["quadrant"], 9))
        ],
        nums=[1, 2, 3, 4],
        search=True,
    ))
    for f in sorted(rows, key=lambda f: order.get(f.extra["quadrant"], 9)):
        e = f.extra
        problem = (
            f"{_e(f.entity_label)}（{e['size']}名）が部門外でつながっている相手は、"
            f"全員合わせて <b>{e['external_alters']}名</b> です"
            f"（同じ人数の部門なら、全部門の中央値では {e['typical_external_alters']}名）。"
            f"メンバーどうしのつながりは、全部門の中央値の "
            f"<b>{e['density_vs_median']:.2f}倍</b> です。"
        )
        s.append(f"<h3>{_e(f.entity_label)}（{_e(e['quadrant_label'])}）</h3>")
        if e.get("reading") == "typical":
            s.append(
                f"<p>{problem}2つの値はどちらも中央値から2割の中に収まっています。"
                "この2つの値では、研究が言う効率型ともイノベーション型とも判定できません。"
                "仕事の割り当ては、この分析ではなく担当業務で決めてください。</p>"
            )
            continue
        if e.get("reading") == "diffuse_overlap":
            problem += (
                f"部門外の相手1人に、平均 <b>{e['members_per_alter']:.1f}名</b> の"
                f"メンバーがつながっています（全部門の中央値 "
                f"{e['median_members_per_alter']:.1f}名）。"
            )
        elif e.get("reading") in ("efficiency", "innovation", "closed"):
            problem += f"研究はこの組み合わせを{_e(e['quadrant_label'])}と呼んでいます。"
        if not f.suggested_actions:
            continue
        s.append(_actions_block(
            f.suggested_actions, problem=problem, goal=_team_goal(e["reading"])
        ))
    s.append(
        "<p class='note limit'>研究では、効率型の特徴を持つ部門をイノベーションに充てると"
        "最も失敗しやすいとしています。2つの値は全部門の中央値で切っているため、"
        "中央値のすぐ近くにいる部門はわずかな差で別の型に移ります。"
        "そのため、どちらも中央値から2割の中に入る部門には型を付けていません。</p>"
    )
    s.append(_sources("team"))
    s.append(_footer())
    return "".join(s)


# ---------------------------------------------------------------- データ




def _data_page(snap: Snapshot) -> str:
    from ..core.weights import size_weight

    q = snap.quality
    s = ["<h1>データの内訳</h1>"]
    s.append("<div class='cards'>")
    s.append(_card("集計できた人", f"{q['persons_in_master']}名",
                   f"同席が1件以上あったのは {q['edge_coverage_rate']:.0%}"))
    s.append(_card("会議イベント", f"{q['interactions']:,}", "重複排除後"))
    s.append(_card("関係", f"{q['edges']:,}", "同席が下限を超えた組"))
    s.append(_card("同席が少なく除外", f"{q['edges_dropped_below_threshold']:,}", "単発の同席など"))
    s.append(_card("1on1 の関係", f"{q['one_on_one_edges']:,}", "2名の会議由来"))
    s.append("</div>")

    s.append("<h2>会議の種類</h2>")
    s.append(_table("mt-table", ["種類", "件数"],
                    [[_e(_type_label(k)), f"<span data-v='{v}'>{v:,}</span>"]
                     for k, v in q["meeting_type_counts"].items()], nums=[1]))

    s.append("<h2>参加人数と重み</h2>")
    s.append(_table(
        "sz-table",
        ["人数", "件数", "1ペアあたりの重み", "1on1 の何分の1か"],
        [
            [
                f"<span data-v='{n}'>{n}</span>",
                f"<span data-v='{c}'>{c:,}</span>",
                f"<span data-v='{size_weight(n)}'>{size_weight(n):.4f}</span>",
                f"<span class='sub'>{'1/' + format(1 / size_weight(n), ',.0f') if size_weight(n) > 1e-9 else 'ほぼ0'}</span>",
            ]
            for n, c in sorted(q["meeting_size_histogram"].items())
        ],
        nums=[0, 1, 2],
    ))
    s.append(
        "<p class='note'><b>参加人数が多い会議ほど、1組あたりを軽く数えています。</b>"
        "2名で60分の会議を 1.0 として、100名の会議は1組あたり 1on1 の約2万分の1です。"
        "全社会議に出ても、全員と結び付いた扱いにはなりません。"
        "人数で線を引かず、人数に応じてなめらかに軽くしています。</p>"
    )

    # 同じ設定・同じ版なら同じ数値になることを確かめられるよう、ここに残す
    s.append("<h2>再現情報</h2>")
    s.append(_table("rp-table", ["項目", "値"], [
        ["集計期間", f"{_e(snap.window_start)} 〜 {_e(snap.window_end)}"],
        ["設定", f"<code>{_e(snap.config_hash)}</code>"],
        ["版", _e(snap.code_version)],
    ], sortable=False))
    s.append(
        "<p class='note'>設定を変えると値が変わります。"
        "過去のレポートと比べるときは、この2つが同じかを確認してください。</p>"
    )

    s.append(_footer())
    return "".join(s)


# ---------------------------------------------------------------- 部品


def _table(
    tid: str,
    headers: list[str],
    rows: list[list[str]],
    nums: list[int] | None = None,
    search: bool = False,
    sortable: bool = True,
) -> str:
    nums = nums or []
    s = ["<div class='tablewrap'>"]
    if search:
        s.append(
            f"<div class='toolbar'><input type='search' data-filter-for='{tid}' "
            f"placeholder='絞り込み'><span class='count' data-count-for='{tid}'></span></div>"
        )
    s.append(f"<div class='scroll'><table id='{tid}'"
             + (" data-sortable" if sortable else "") + "><thead><tr>")
    for i, h in enumerate(headers):
        cls = " class='num'" if i in nums else ""
        nosort = " data-nosort" if not h else ""
        s.append(f"<th{cls}{nosort}>{_e(h) if h else ''}</th>")
    s.append("</tr></thead><tbody>")
    for r in rows:
        s.append("<tr>")
        for i, c in enumerate(r):
            s.append(f"<td{' class=\"num\"' if i in nums else ''}>{c}</td>")
        s.append("</tr>")
    s.append("</tbody></table></div></div>")
    return "".join(s)


def _actions_block(
    actions: list[str], sim: dict | None = None, problem: str = "", goal: str = ""
) -> str:
    """いまの状態と、それを変えたい場合の打ち手を並べて出す。

    打ち手だけを並べると、なぜそれをするのかが分からない。
    何が起きているかを数値で先に書き、その下に打ち手を置く。
    数値と打ち手を離すと、打ち手の根拠を確かめられないので同じ枠に入れる。

    打ち手の見出しは「〜したい場合」にする。**その状態を変えるべきかどうかは、
    その部門や部門が担っている仕事によって決まる。** この OSS は仕事の中身を
    観測していないので、変えるべきだと書ける根拠がない。
    """
    if not actions and not sim:
        return ""
    s = ["<div class='actions'>"]
    if problem:
        s.append(f"<h3>いまの状態</h3><p class='prob'>{problem}</p>")
    s.append(f"<h3>{_e(goal) if goal else '打ち手'}</h3><ul>")
    s += [f"<li>{_e(x)}</li>" for x in actions]
    s.append("</ul>")
    if sim and sim.get("steps"):
        s.append("<div class='sim'>")
        s.append(
            f"<p class='simhead'><b>{_e(sim['successor_label'])}</b> を接点に加えた場合の試算</p>"
        )
        s.append(_sim_steps(sim))
        parts = [f"代わりの人がいる相手どうしの組 {sim['before']:.0%} → {sim['after']:.0%}"]
        if sim.get("enough_at"):
            parts.append(f"切り離される集団は <b>{sim['enough_at']}件</b> つなぐとなくなります")
        s.append(
            f"<p class='note'><b>横軸は {_e(sim['successor_label'])} を同席させる接点の数、"
            "縦軸は代わりの人がいる相手どうしの組です。</b>"
            + "　／　".join(parts) + "</p>"
        )
        s.append(
            "<p class='note limit'>これはグラフ上の定義に照らした計算です。"
            "実際にその人が役割を引き継げるかは、別に確認してください。</p>"
        )
        s.append("</div>")
    s.append("</div>")
    return "".join(s)


def _sim_steps(sim: dict) -> str:
    """同席させる相手を1人ずつ増やしたときの変化。どこまでやれば十分かを示す。"""
    steps = sim["steps"]
    hi = max(x["replaceability"] for x in steps) or 1.0
    W, H, P = 420, 112, 26
    n = len(steps) - 1 or 1
    pts = []
    out = [f"<svg viewBox='0 0 {W} {H}' style='width:100%;height:auto;max-width:{W}px'>",
           "<style>.sm-l{stroke:var(--accent);fill:none;stroke-width:2}"
           ".sm-d{fill:var(--accent)}.sm-t{fill:var(--mut);font-size:9.5px}"
           ".sm-v{fill:var(--fg);font-size:10px;font-variant-numeric:tabular-nums}"
           ".sm-ax{stroke:var(--line)}</style>",
           f"<line class='sm-ax' x1='{P}' y1='{H - 22}' x2='{W - 10}' y2='{H - 22}'/>"]
    for i, st_ in enumerate(steps):
        x = P + i / n * (W - P - 24)
        y = (H - 26) - (st_["replaceability"] / hi) * (H - 52)
        pts.append(f"{x:.1f},{y:.1f}")
        out.append(f"<circle class='sm-d' cx='{x:.1f}' cy='{y:.1f}' r='3.4'/>")
        out.append(f"<text class='sm-v' x='{x:.1f}' y='{y - 7:.1f}' text-anchor='middle'>"
                   f"{st_['replaceability']:.0%}</text>")
        out.append(f"<text class='sm-t' x='{x:.1f}' y='{H - 8}' text-anchor='middle'>"
                   f"{st_['links']}件</text>")
    out.insert(3, f"<polyline class='sm-l' points='{' '.join(pts)}'/>")
    out.append(f"<text class='sm-t' x='2' y='{H - 26}'>代わりの人がいる相手どうしの組</text>")
    out.append("</svg>")
    return "".join(out)


def _index(findings: list) -> dict[str, list]:
    out: dict[str, list] = defaultdict(list)
    for f in findings:
        out[f.metric].append(f)
    return out


def _actions(findings: list) -> str:
    acts: list[str] = []
    for f in findings:
        for x in f.suggested_actions:
            if x not in acts:
                acts.append(x)
    if not acts:
        return ""
    return ("<details open><summary>打ち手の候補</summary><ul>"
            + "".join(f"<li>{_e(x)}</li>" for x in acts) + "</ul></details>")


def _limits(f) -> str:
    """この指標で判断してはいけないことを、1件ずつ分けて並べる。

    <br> でつなぐと、どこまでが1件なのかが読み取れない。見出しと箇条書きに分ける。
    """
    items = [f.does_not_mean] + list(f.caveats)
    lis = "".join(f"<li>{_e(c)}</li>" for c in items)
    return f"<div class='note limit'><b>この指標の限界</b><ul>{lis}</ul></div>"


def _team_goal(reading: str) -> str:
    """読み方ごとに、打ち手が何を目指すものかを書く。

    効率型とイノベーション型は、いまの型を前提に仕事を割り当てる話。
    閉鎖型と、部門外との接点が少ない型は、接点そのものを増やす話。
    メンバーが同じ相手と会っている型は、接点の数ではなく分け方を変える話。
    """
    return {
        "efficiency": "この部門に仕事を割り当てるとき",
        "innovation": "この部門に仕事を割り当てるとき",
        "closed": "部門外との接点を増やしたい場合",
        "diffuse_narrow": "この部門が外から情報を受け取れるようにしたい場合",
        "diffuse_overlap": "いまの時間のまま、部門外に届く範囲を広げたい場合",
    }.get(reading, "打ち手")


def _fit(reading: str) -> str:
    return {
        "efficiency": "納期を守る必要があるプロジェクト",
        "innovation": "新規探索や新商品開発",
        "closed": "部門内で完結する業務",
        "diffuse_narrow": "部門内で完結する業務",
        "diffuse_overlap": "担当を分けて進める業務",
        "typical": "この分析では決まらない",
    }.get(reading, "")


def _type_label(k: str) -> str:
    return {
        "one_on_one_recurring": "1on1（定期）",
        "one_on_one_adhoc": "1on1（単発）",
        "team_standing": "部門の定例",
        "small_group_work": "小グループ作業",
        "project_meeting": "プロジェクト会議",
        "broadcast": "情報共有・全体会",
        "external_meeting": "外部ミーティング",
        "other": "その他",
    }.get(k, k)


def _dept_pairs_cell(e: dict) -> str:
    """「代わりの人がいる部門の組」のセル。母数（何組か）を添える。"""
    kept = e.get("dept_pairs_kept")
    if kept is None:
        return "<span data-v='1.1'>—</span>"
    n = e.get("dept_pairs") or 0
    cut = round((1 - kept) * n)
    # 表のセルは短くする。読み方は表の下の注記に1回だけ書く
    note = f"{n}組" if cut == 0 else f"{n}組中{cut}組"
    return (f"<span data-v='{kept}'>{svg.bar(1 - kept, 1, '--mut')}{kept:.0%}"
            f"<span class='sub'>（{note}）</span></span>")


def _rank_no(f) -> int | None:
    """比較した集団の中での順位。

    指標側はパーセンタイル（上から何%の位置か）を持っているが、
    読むのは人事担当者で「93%ile」は読めない。順位に戻して母数と一緒に出す。
    """
    n = f.comparison_n or 0
    if f.percentile is None or n < 2:
        return None
    return round((1 - f.percentile / 100) * (n - 1)) + 1


def _rank(f) -> str:
    """「30名中2位」。母数を付けないと、順位の重みが分からない。"""
    i = _rank_no(f)
    return "—" if i is None else f"{f.comparison_n}名中{i}位"


def _tag(status: str) -> str:
    label = {"ok": "問題なし", "watch": "注目", "warning": "警戒", "critical": "要対応"}.get(status, status)
    return f"<span class='tag {status}'>{label}</span>"


def _slug(s: str) -> str:
    return "p-" + "".join(c if c.isalnum() else "-" for c in str(s))


def _e(v: Any) -> str:
    return html.escape(str(v))


# 単位の付いた数だけを拾う。氏名の末尾の番号（石井089）を太字にしないため。
# 実体参照（&#x27; など）と、先に入れた <b> の中を拾わないよう、それらを先に食わせる
_NUM = re.compile(
    r"</?b>|&#?\w+;|(\d[\d,]*(?:\.\d+)?(?:名|%|倍|件|組|つ|割|本|人|部門))"
)


def _emph(text: str, names: list[str] | None = None) -> str:
    """文章の中の固有名詞と数値だけを太字にする。

    文を丸ごと太くすると、どこが部門名でどこが数値なのか分からない。
    灰色の説明文も同じで、全部が同じ濃さだと読む順が決まらない。
    **誰の話か（固有名詞）と、どれだけか（数値）**の2つだけを太字にする。

    固有名詞は推測せず、`src/relana/core/summary.py` が付けた名前だけを使う。
    文字列から探すと「本部」「部門」のような語を拾ってしまう。
    """
    out = _e(text)
    uniq = sorted({n for n in (names or []) if n}, key=len, reverse=True)
    if uniq:
        pat = "|".join(re.escape(_e(n)) for n in uniq)
        out = re.sub(f"({pat})", r"<b>\1</b>", out)
    return _NUM.sub(lambda m: f"<b>{m.group(1)}</b>" if m.group(1) else m.group(0), out)
