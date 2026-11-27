"""複数ページHTMLレポートのテスト。

外部ライブラリを読み込まないこと、全ページに解釈と限界が付くこと、
ネットワーク図が6指標で絞り込めることを固定する。
"""

from __future__ import annotations

import json
from collections import Counter
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from relana.config import Config
from html import escape as _esc

from relana.core import citations as cit
from relana.core.analyze import analyze
from relana.core.reliability import assess
from relana.demo import generate
from relana.report.pages import PAGES, write
from relana.sources.gcal.normalize import normalize

WINDOW_END = datetime(2026, 3, 31, tzinfo=timezone.utc)
PAIRED = ("div", "table", "tbody", "thead", "tr", "svg", "g", "details", "ul", "ol", "a", "span")


def _build(tmp: Path, **cfg_kw):
    raw, persons, _ = generate()
    cfg = Config()
    cfg.normalize.keep_group_titles = True
    for k, v in cfg_kw.items():
        setattr(cfg.analysis, k, v)
    interactions, _ = normalize(raw, {p.person_id: p for p in persons}, cfg.normalize)
    snap, bundle = analyze(interactions, persons, cfg, WINDOW_END, "t", headcount=100)
    entry = write(snap, bundle, tmp / "report")
    return entry.parent, snap


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("rep"))


def _pages(d: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in d.glob("*.html")}


def test_every_declared_page_is_written(report):
    d, _ = report
    for name, _t, _k, _q in PAGES:
        assert (d / name).exists(), f"{name} が生成されていない"
    assert (d / "assets" / "style.css").exists()
    assert (d / "assets" / "app.js").exists()
    assert (d / "assets" / "graph.js").exists()


def test_no_external_resources(report):
    """オフラインで開ける。CDN からも読み込まない。"""
    d, _ = report
    for name, html in _pages(d).items():
        assert not re.search(r'(?:src|href)="https?://', html), f"{name} が外部を参照している"


def test_markup_is_balanced(report):
    d, _ = report
    for name, html in _pages(d).items():
        for tag in PAIRED:
            assert html.count(f"<{tag}") == html.count(f"</{tag}>"), f"{name}: {tag}"
        # <p> は SVG の <path> と区別して数える
        assert len(re.findall(r"<p[ >]", html)) == html.count("</p>"), f"{name}: p"


def test_pages_share_navigation(report):
    d, _ = report
    for name, html in _pages(d).items():
        assert "class='nav'" in html
        assert f"aria-current=\"page\"" in html, f"{name} に現在位置が示されていない"
        for other, _t, _k, _q in PAGES:
            assert f"href='{other}'" in html


def test_index_links_to_each_feature(report):
    d, _ = report
    html = (d / "index.html").read_text(encoding="utf-8")
    for page in ("silo.html", "vulnerability.html", "influence.html", "graph.html"):
        assert f"href='{page}'" in html


def test_every_feature_page_states_its_limits(report):
    """数値だけを出さない。限界を必ず添える（原則4）。"""
    d, _ = report
    for name in ("silo.html", "vulnerability.html", "influence.html", "ideation.html", "teams.html"):
        html = (d / name).read_text(encoding="utf-8")
        assert "この指標の限界" in html or "研究では" in html, name


def test_tables_are_sortable_and_filterable(report):
    d, _ = report
    html = (d / "silo.html").read_text(encoding="utf-8")
    assert "data-sortable" in html
    assert "data-filter-for" in html
    app = (d / "assets" / "app.js").read_text(encoding="utf-8")
    assert "sortable" in app and "data-filter-for" in app


# ---------- ネットワーク図 ----------

def _graph_data(d: Path) -> dict:
    html = (d / "graph.html").read_text(encoding="utf-8")
    m = re.search(r"window\.RELANA_GRAPH=(\{.*?\});</script>", html, re.S)
    assert m, "グラフデータが埋め込まれていない"
    return json.loads(m.group(1))


def test_graph_has_nodes_and_links(report):
    d, _ = report
    g = _graph_data(d)
    assert g["stats"]["people"] == 100
    assert len(g["links"]) > 100
    assert all({"s", "t", "w"} <= set(l) for l in g["links"])


def test_graph_nodes_carry_every_feature_for_filtering(report):
    """「見て終わる図」にしない。6指標で色・大きさ・絞り込みを切り替えられること。"""
    d, _ = report
    g = _graph_data(d)
    internal = [n for n in g["nodes"] if not n["external"]]
    assert any(n.get("constraint") is not None for n in internal), "❶ がない"
    assert any(n.get("betweenness") is not None for n in internal), "インフルエンサーがない"
    assert any(n.get("replaceability") is not None for n in internal), "❻ がない"
    assert all("dept" in n and "team" in n for n in internal), "❺❸❹ の軸がない"


def test_graph_marks_dyads_and_cross_department_links(report):
    d, _ = report
    g = _graph_data(d)
    assert any(l["dyad"] for l in g["links"]), "1on1 の印がない"
    assert any(l["cross"] for l in g["links"]), "部門をまたぐ印がない"


def test_graph_has_no_control_panel(report):
    """操作盤を左に並べると図が縮み、氏名が重なって読めない。

    図は部門で塗り分けた1枚に固定し、横幅をすべて図に使う。
    """
    d, _ = report
    html = (d / "graph.html").read_text(encoding="utf-8")
    for control in ("gcolor", "gsize", "gdyad", "gcross", "glabels", "gsearch", "greset"):
        assert f"id='{control}'" not in html, f"{control} が残っている"
    assert "data-dept-filter=" not in html, "部門の絞り込みが残っている"
    assert html.count("class='gpanel") == 1, "左の操作盤が残っている"


def test_graph_script_is_self_contained(report):
    d, _ = report
    js = (d / "assets" / "graph.js").read_text(encoding="utf-8")
    assert "RELANA_GRAPH" in js
    assert "import" not in js.split("//")[0]
    assert "RELANA_GRAPH" in js


# ---------- 文言と信頼度 ----------

def test_vulnerability_disclaims_use_for_evaluation(report):
    """この数値を処遇の判断に使えないことは、指標ごとの限界として各人に出す。"""
    d, _ = report
    html = (d / "vulnerability.html").read_text(encoding="utf-8")
    assert "処遇" in html
    assert "人事評価・処遇・報酬の判断に使えない" in html


def test_report_does_not_grade_its_own_reliability(report):
    """「信頼度 高い」のような自己採点は出さない。

    取得できた会議から関係を数えていることは各ページに書いてある。
    その上で指標ごとに点を付けても、読む人の判断材料にならない。
    """
    d, _ = report
    for name, _t, _k, _q in PAGES:
        html = (d / name).read_text(encoding="utf-8")
        for word in ("データの信頼度", "信頼度", "読み方</th>"):
            assert word not in html, f"{name} に「{word}」がある"


def test_collected_headcount_stays_as_a_plain_fact(report):
    """何名分を集計したかは、判定ではなく数として残す。"""
    d, _ = report
    html = (d / "data.html").read_text(encoding="utf-8")
    assert "集計できた人" in html


def test_low_coverage_downgrades_the_fragile_metrics():
    rel = assess(observed=70, headcount=100, with_edges=70)
    assert rel.level("vulnerability")["key"] in ("low", "insufficient")
    assert rel.level("silo")["key"] in ("high", "medium")


def test_inferred_groups_are_disclosed(tmp_path: Path):
    d, snap = _build(tmp_path, groups_source="inferred")
    html = (d / "index.html").read_text(encoding="utf-8")
    assert "部門はカレンダーから推定したものです" in html
    assert "循環論法" in html


def test_participant_weight_table_is_shown(report):
    d, _ = report
    html = (d / "data.html").read_text(encoding="utf-8")
    assert "1ペアあたりの重み" in html
    assert "1on1 の何分の1か" in html
    assert "人数に応じてなめらかに軽くしています" in html


# ---------- 固定配置 ----------

def test_layout_is_fixed_and_reproducible(report):
    """図が開くたびに変わると比較できない。配置は決定論的に決める（NFR-5）。"""
    d, _ = report
    g = _graph_data(d)
    assert all("x" in n and "y" in n for n in g["nodes"]), "座標が無い"
    js = (d / "assets" / "graph.js").read_text(encoding="utf-8")
    assert "requestAnimationFrame" not in js, "力学シミュレーションが残っている"
    assert "配置は Python 側で確定済み" in js


def test_layout_is_identical_across_runs(tmp_path):
    a, _ = _build(tmp_path / "a")
    b, _ = _build(tmp_path / "b")
    pa = {n["id"]: (n["x"], n["y"]) for n in _graph_data(a)["nodes"]}
    pb = {n["id"]: (n["x"], n["y"]) for n in _graph_data(b)["nodes"]}
    assert pa == pb, "同じ入力で配置が変わっている"


def test_display_threshold_is_fixed_not_per_node(report):
    """ノードごとに上位k本を残すと、関係の少ない人にも線が付いて次数分布が歪む。
    全ノードに同じ閾値を当てる。"""
    d, _ = report
    g = _graph_data(d)
    assert g["min_weight"] == 1.0
    assert all(l["w"] >= 1.0 for l in g["links"])
    assert g["hidden_links"] > 0
    # 線が1本も描かれない人がいてよい（実際に強い関係を持たない人）
    deg = {}
    for l in g["links"]:
        deg[l["s"]] = deg.get(l["s"], 0) + 1
        deg[l["t"]] = deg.get(l["t"], 0) + 1
    assert min(deg.values()) == 1, "どのノードにも最低限の線が付いていると分布が平らになる"

    layout_src = (Path(__file__).parent.parent / "src/relana/report/layout.py").read_text(
        encoding="utf-8"
    )
    assert "次数の分布が平ら" in layout_src


def test_same_department_is_placed_together(report):
    """同じ部門の人は近くに置く。読み手が部門のかたまりを見分けられること。"""
    import math
    from collections import defaultdict
    from statistics import fmean

    d, _ = report
    g = _graph_data(d)
    byd = defaultdict(list)
    for n in g["nodes"]:
        if not n["external"]:
            byd[n["dept"]].append((n["x"], n["y"]))
    centers = {
        k: (fmean(x for x, _ in v), fmean(y for _, y in v)) for k, v in byd.items()
    }
    misplaced = 0
    for dept, pts in byd.items():
        for x, y in pts:
            nearest = min(centers, key=lambda k: math.hypot(x - centers[k][0], y - centers[k][1]))
            if nearest != dept:
                misplaced += 1
    total = sum(len(v) for v in byd.values())
    assert misplaced / total < 0.05, f"部門が混ざっている（{misplaced}/{total}名）"


def test_cluster_labels_are_emitted(report):
    d, _ = report
    g = _graph_data(d)
    assert len(g["clusters"]) == len(g["depts"])
    for c in g["clusters"]:
        assert {"name", "count", "x", "y"} <= set(c)
    html = (d / "graph.html").read_text(encoding="utf-8")
    assert "g-clusters" in html


def test_node_labels_are_placed_without_overlap(report):
    """氏名は全員分出す。重なって読めなくなる分だけ省く。"""
    d, _ = report
    g = _graph_data(d)
    assert len(g["labels"]) >= len(g["nodes"]) * 0.85
    for v in g["labels"].values():
        assert v["side"] in (1, -1)


def test_weight_slider_is_removed(report):
    d, _ = report
    html = (d / "graph.html").read_text(encoding="utf-8")
    assert "gminw" not in html
    assert "1on1 を1回分" in html
    assert "描いていません" in html


# ---------- 氏名ラベル ----------

def test_svg_group_ids_do_not_collide_with_controls(report):
    """id が重複すると getElementById が別の要素を返し、氏名が描かれない。

    実際に <select id='glabels'> と <g id='glabels'> が衝突し、
    氏名の text 要素が select の中に入って表示されなかった。
    """
    d, _ = report
    html = (d / "graph.html").read_text(encoding="utf-8")
    ids = re.findall(r"id='([A-Za-z0-9_-]+)'", html)
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"id が重複している: {dupes}"


def test_svg_groups_use_a_distinct_prefix(report):
    d, _ = report
    html = (d / "graph.html").read_text(encoding="utf-8")
    for gid in ("g-root", "g-links", "g-nodes", "g-labels", "g-clusters"):
        assert f"id='{gid}'" in html
    js = (d / "assets" / "graph.js").read_text(encoding="utf-8")
    assert "getElementById('g-labels')" in js


def test_key_nodes_are_marked_for_always_on_labels(report):
    """全員分を常時出すと重なって読めない。❻該当・社外・同席相手の多い人に絞る。"""
    d, _ = report
    g = _graph_data(d)
    keyed = [n for n in g["nodes"] if n.get("key")]
    assert 0 < len(keyed) < len(g["nodes"]) * 0.3
    assert all(n["key"] for n in g["nodes"] if n["external"])
    assert all(n["key"] for n in g["nodes"] if n.get("critical") in ("critical", "warning"))
    assert g["stats"]["key_nodes"] == len(keyed)


def test_hover_reveals_names(report):
    d, _ = report
    js = (d / "assets" / "graph.js").read_text(encoding="utf-8")
    assert "state.hovered" in js
    assert "ホバーした人と、その同席相手の氏名を出す" in js
    html = (d / "graph.html").read_text(encoding="utf-8")
    assert "カーソルを合わせる" in html


def test_label_mode_defaults_to_key_nodes(report):
    """全員分を常時出すと重なって読めない。既定は主要な人とホバーした人。"""
    d, _ = report
    js = (d / "assets" / "graph.js").read_text(encoding="utf-8")
    assert "labels: 'key'" in js


# ---------- 役割と打ち手 ----------

def test_roles_are_assigned_from_existing_metrics(report):
    """新しい指標は作らず、6指標の組み合わせで役割を決める。"""
    _, snap = report
    assert snap.roles
    keys = {r["key"] for p in snap.roles.values() for r in p["roles"]}
    assert keys <= {"broker", "conduit", "single_point", "overloaded", "internal_hub", "thin"}
    assert 0 < len(snap.roles) < 100


def test_roles_do_not_depend_on_inferred_job_title(report):
    """役職は推定値であり、それを基準にした役割は作らない。"""
    import inspect
    from relana.core import roles as roles_mod

    src = inspect.getsource(roles_mod)
    assert "役職は使わない" in src
    _, snap = report
    for p in snap.roles.values():
        for r in p["roles"]:
            assert "役職" not in r["why"], "役職を根拠にしている役割がある"


def test_every_role_carries_an_action(report):
    """役割を出すだけでは動けない。打ち手を必ず付ける。"""
    _, snap = report
    for p in snap.roles.values():
        for r in p["roles"]:
            assert r["actions"], f"{r['key']} に打ち手がない"


def test_priority_crosses_metrics(report):
    """優先順位は指標をまたぐ。1つの指標ページからは分からない。"""
    _, snap = report
    prio = snap.highlights["priority_people"]
    assert prio
    assert all(len(p["roles"]) >= 2 for p in prio)
    top = prio[0]
    assert len(top["roles"]) >= 3


def test_simulation_shows_the_effect_of_the_action(report):
    """打ち手を打つと数値がどう変わるかを出す。"""
    _, snap = report
    sims = [
        f.extra["simulation"]
        for f in snap.findings
        if f.feature == "vulnerability" and "simulation" in f.extra
    ]
    assert sims
    for sim in sims:
        assert sim["after"] >= sim["before"]
        assert sim["steps"][0]["links"] == 0
        assert len(sim["steps"]) >= 2
        assert sim["successor_label"]


def test_simulation_is_disclosed_as_a_calculation_not_a_prediction(report):
    d, _ = report
    html = (d / "vulnerability.html").read_text(encoding="utf-8")
    assert "グラフ上の定義に照らした計算" in html
    assert "実際にその人が役割を引き継げるかは" in html


def test_actions_sit_next_to_the_numbers(report):
    """打ち手を別ページに分けない。根拠と同じページに置く。"""
    d, _ = report
    names = {p.name for p in d.glob("*.html")}
    assert "actions.html" not in names, "打ち手だけのページを作らない"
    for page in ("silo.html", "vulnerability.html", "influence.html", "ideation.html", "teams.html"):
        html = (d / page).read_text(encoding="utf-8")
        assert "class='actions'" in html, f"{page} に打ち手がない"


def test_one_person_has_their_actions_in_one_place(report):
    """同じ人が複数のページに出るので、打ち手は人ごとに1か所へまとめる。

    各ページだけを読むと、その人に対して結局何をするのかが分からない。
    まとめる場所はネットワーク図の詳細パネル。人をクリックすると、
    その人が持つ役割の打ち手がまとめて出る。
    """
    d, snap = report
    g = _graph_data(d)
    by_id = {n["id"]: n for n in g["nodes"]}
    people = snap.highlights["priority_people"]
    assert people
    for person in people:
        node = by_id.get(person["person_id"])
        assert node, person["label"]
        acts = []
        for r in person["roles"]:
            for a in r["actions"]:
                if a not in acts:
                    acts.append(a)
        shown = node["actions"]
        assert shown, f"{person['label']} の打ち手が出ていない"
        # 役割をまたいで同じ打ち手を2回出さない
        assert len(shown) == len(set(shown)), person["label"]
        assert shown == acts[: len(shown)], person["label"]
        # 役割の名前も、その人の欄に並んでいる
        assert node["roles"] == [r["label"] for r in person["roles"]]


def test_graph_panel_shows_roles_and_actions(report):
    """図でクリックした人の役割と打ち手が、その場で出る。"""
    d, _ = report
    g = _graph_data(d)
    with_roles = [n for n in g["nodes"] if n.get("roles")]
    assert with_roles
    assert any(n.get("actions") for n in with_roles)
    js = (d / "assets" / "graph.js").read_text(encoding="utf-8")
    assert "gact" in js and "groles" in js


# ---------- 概要ページと番号の表記 ----------

# 測り方を書いてよいページ。ここ以外の説明文では「つながり」と書く
MEASUREMENT_PAGES = {"index.html", "data.html", "graph.html"}


def test_prose_does_not_restate_that_a_tie_is_a_meeting(report):
    """関係＝会議の同席であることは、概要とデータページに書いてある。

    説明文で測り方を言い直すと、読み手が観測値から意味を組み立てることになる。
    残してよいのは「この指標の限界」と打ち手だけ。
    """
    d, _ = report
    for name, _t, _k, _q in PAGES:
        if name in MEASUREMENT_PAGES:
            continue
        html = (d / name).read_text(encoding="utf-8")
        # 限界の枠と打ち手の枠を外してから探す
        body = re.sub(r"<div class='note limit'>.*?</div>", "", html, flags=re.S)
        body = re.sub(r"<p class='note limit'>.*?</p>", "", body, flags=re.S)
        body = re.sub(r"<div class='actions'>.*?</div>", "", body, flags=re.S)
        for w in ("同席", "出席"):
            assert w not in body, f"{name} の説明文に「{w}」がある"


def test_the_heatmap_has_a_legend(report):
    """数字がいくつなら濃いのかを、同じ画面の中で確かめられるようにする。"""
    d, _ = report
    html = (d / "silo.html").read_text(encoding="utf-8")
    assert "部門と部門の間のつながり" in html, "凡例の見出しがない"
    assert "部門の中（別の尺度）" in html, "対角が別の尺度だと書いていない"
    assert "接点が残らなかった組" in html, "断絶の説明がない"
    # 色は1色だけにする。対角と対角以外を2色で塗ると同じ尺度に見える
    svg = re.search(r"<svg[^>]*部門と部門の間[^>]*>.*?</svg>", html, re.S)
    assert svg, "ヒートマップがない"
    hues = set(re.findall(r"var\((--ok|--warn|--watch|--accent)\)", svg.group(0)))
    assert hues <= {"--accent"}, f"色が混在している: {hues}"


def test_a_person_who_cuts_the_network_gets_a_cutout_graph(report):
    """誰がどこを繋いでいるかは、文章より図のほうが早い。

    その人を中心に、つながっている相手を部門ごとの列に並べる。
    氏名だけを並べると、どの部門の人なのかを1人ずつ読み取ることになる。
    """
    import re

    d, snap = report
    html = (d / "vulnerability.html").read_text(encoding="utf-8")
    cut = [
        f for f in snap.findings
        if f.metric == "node_criticality" and (f.extra.get("separated_groups") or [])
    ]
    assert cut
    assert html.count(" の周りのつながり</h3>") >= len(cut)
    assert "が抜けると社内から切り離される相手" in html

    figs = re.findall(r"<svg[^>]*aria-label='([^']+) の周りの関係'(.*?)</svg>", html, re.S)
    assert figs
    for who, body in figs:
        # 切り離される相手は赤。それ以外は灰色
        assert "nb-x" in body, who
        # 列の見出しは部門名と人数。どの部門と何名つながっているかが先に出る
        heads = re.findall(r"class='nb-h'[^>]*>([^<]+)<", body)
        counts = re.findall(r"class='nb-s'[^>]*>(\d+)名<", body)
        assert heads, who
        assert len(counts) == len(heads), who
        # 同じ部門が2つの列に分かれていない
        assert len(set(heads)) == len(heads), who
        # 列の人数の合計は、図に出した相手の数と「ほかN名」の合計に一致する。
        # 凡例の丸（氏名の text が続かないもの）は数えない
        shown = len(re.findall(r"class='nb-[xn]' cx='[\d.]+' cy='[\d.]+' r='[\d.]+'/><text class='nb-t'", body))
        more = sum(int(n) for n in re.findall(r">ほか(\d+)名<", body))
        assert sum(int(c) for c in counts) == shown + more, who
        # 右端が切れていない。描いた丸の x は viewBox の幅の中にある
        head = html[: html.index(f"aria-label='{who} の周りの関係'")]
        width = int(re.findall(r"viewBox='0 0 (\d+)", head)[-1])
        xs = [float(x) for x in re.findall(r" cx='([\d.]+)'", body)]
        assert max(xs) < width, who


def test_every_chart_says_how_to_read_it(report):
    """図は、人事責任者が読む。データ分析者ではない。

    数字が大きいと何なのか、どこを見ればよいのかを、図のすぐ下に書く。
    作り方（対角が部門内、1ペアあたりに直した）だけでは、図を解釈できない。
    """
    d, _ = report
    charts = 0
    for name, _t, _k, _q in PAGES:
        html = (d / name).read_text(encoding="utf-8")
        if "<svg" not in html or name == "graph.html":
            continue
        notes = re.findall(r"</svg>(?:</div>)*<p class='note'>(.{0,60})", html, re.S)
        assert notes, f"{name}: 図の下に読み方の説明がない"
        for n in notes:
            charts += 1
            assert n.startswith("<b>"), (
                f"{name}: 図の説明が読み方から始まっていない → {n[:40]}"
            )
    assert charts >= 4, charts


def test_report_does_not_use_the_word_tenkyo(report):
    """「典拠」は日常で使う語ではない。画面では「研究」「出典」に置き換える。"""
    d, _ = report
    for name, _t, _k, _q in PAGES:
        html = (d / name).read_text(encoding="utf-8")
        assert "典拠" not in html, f"{name} に「典拠」が残っている"


def test_report_has_no_circled_numbers(report):
    """❶〜❻ は典拠の章立ての番号で、読む人には意味がない。画面に出さない。"""
    d, _ = report
    for name, _t, _k, _q in PAGES:
        html = (d / name).read_text(encoding="utf-8")
        found = [c for c in "❶❷❸❹❺❻" if c in html]
        assert not found, f"{name} に {found} が残っている"


def test_index_explains_what_each_analysis_counts(report):
    """利用者はこのレポートが何をしているかを知らない。

    5つの分析それぞれについて、その分析が答える問いと代表的な結果を出す。
    """
    d, snap = report
    html = (d / "index.html").read_text(encoding="utf-8")
    assert "この分析で分かること" in html
    assert html.count("class='ana'") == 5, "5つの分析が並んでいない"
    # カードの見出しは、目次や「見るもの」と同じ分析名にする
    for name in ("部門のつながり", "ハブとなっている人", "インフルエンサー", "発想の起点となる人", "部門の型"):
        assert f"<div class='aq'>{name}</div>" in html, f"「{name}」のカードがない"
    # 問いと、この組織での結果が両方ある
    assert html.count("class='aw'") == 5
    assert html.count("class='ar'") == 5
    # 5つの分析それぞれに、名前と数値の入った結果が1本以上ある
    # 固有名詞と数値は <b> で囲むので、比べる前に外す
    plain = html.replace("<b>", "").replace("</b>", "")
    plain = plain.replace("&lt;", "<").replace("&gt;", ">")
    ex = snap.highlights["examples"]
    for page in ("silo.html", "vulnerability.html", "influence.html",
                 "ideation.html", "teams.html"):
        rows = ex.get(page) or []
        assert rows, f"{page} の代表的な結果がない"
        for r in rows:
            assert re.search(r"\d", r["title"]), r["title"]
            assert r["title"] in plain, r["title"]
            # 誰の話かが太字になっている
            assert r.get("names"), f"{page} の names がない"
            for n in r["names"]:
                assert f"<b>{n}</b>" in html, n


def test_graph_colors_by_department(report):
    """部門で塗った図だけを出す。色の凡例は図の右に置く。"""
    d, _ = report
    js = (d / "assets" / "graph.js").read_text(encoding="utf-8")
    assert "color: 'dept'" in js
    html = (d / "graph.html").read_text(encoding="utf-8")
    assert "id='glegend'" in html, "色の凡例がない"


# ---------- どの集団が分かれるか ----------

def test_vulnerability_names_the_groups_that_separate(report):
    """「2つ以上に分かれる」では、読んだ人が誰のことか分からない。"""
    d, snap = report
    html = (d / "vulnerability.html").read_text(encoding="utf-8")
    assert "2つ以上に分かれる" not in html
    assert "が抜けるとつながらなくなる集団" in html

    f = next(
        x for x in snap.findings
        if x.feature == "vulnerability" and x.extra.get("separated_groups")
    )
    grp = f.extra["separated_groups"][0]
    assert grp["size"] >= 1
    assert grp["main_size"] >= 1
    assert grp["members"], "切り離される人の氏名がない"
    for m in grp["members"]:
        assert m["label"] in html, f"{m['label']} が画面に出ていない"
    assert grp["summary"] in f.interprets_as


def test_succession_candidates_show_names_not_ids(report):
    """person_id は内部の識別子。人事担当者は読めない。"""
    d, snap = report
    html = (d / "vulnerability.html").read_text(encoding="utf-8")
    assert "引き継ぎ候補" in html
    assert "u_0" not in html and "ext:" not in html
    f = next(
        x for x in snap.findings
        if x.feature == "vulnerability" and x.extra.get("succession_candidates")
    )
    c = f.extra["succession_candidates"][0]
    assert len(c["missing_labels"]) == len(c["missing_links"])
    for label in c["missing_labels"]:
        assert not label.startswith("u_") and not label.startswith("ext:")


def test_one_on_one_absentee_list_is_gone(report):
    """全員の氏名を並べるだけで、次にやることが無いセクションは置かない。"""
    d, _ = report
    html = (d / "data.html").read_text(encoding="utf-8")
    assert "1on1 が観測されなかった人" not in html


def test_nodes_do_not_overlap_in_the_graph(report):
    """ノードが重なると、かたまりの中の線が隠れて構造が読めない。

    図のノードは半径 4〜15px で描く。中心間がその2倍より狭いと円が重なる。
    """
    import math

    d, _ = report
    g = _graph_data(d)
    pts = [(n["x"], n["y"]) for n in g["nodes"] if not n["external"]]
    closest = min(
        math.dist(a, b) for i, a in enumerate(pts) for b in pts[i + 1:]
    )
    assert closest >= 32.0, f"最も近い2人が {closest:.1f} しか離れていない"


def test_influence_page_uses_betweenness(report):
    """インフルエンサーは媒介中心性で測る。到達人数のような似た指標を並べない。"""
    d, snap = report
    html = (d / "influence.html").read_text(encoding="utf-8")
    assert "媒介中心性" in html
    assert "1人経由で届く人数" not in html
    assert "2ステップ" not in html

    rows = [f for f in snap.findings if f.feature == "influence"]
    assert rows and all(f.metric == "betweenness" for f in rows)
    # ハブとなっている人と同じ値を使う
    vuln = {
        f.entity_id: f.extra["betweenness"]
        for f in snap.findings
        if f.feature == "vulnerability"
    }
    for f in rows:
        if f.entity_id in vuln:
            assert abs(f.value - vuln[f.entity_id]) < 1e-9, "2ページで違う値を出さない"


# ---------- 典拠 ----------

def test_metric_pages_point_to_the_sources_page(report):
    """書誌はページの中に並べない。数値と打ち手の間に挟まると読みにくい。

    各ページには著者名だけを出し、定義は出典ページで読めるようにする。
    """
    d, _ = report
    for name, _t, key, _q in PAGES:
        if not key:
            continue
        html = (d / name).read_text(encoding="utf-8")
        assert "この数値の出典" in html, f"{name} に出典への案内がない"
        assert f"sources.html#{key}" in html, f"{name} から出典ページへ飛べない"
        for cite in cit.for_feature(key):
            assert cite.short in html or _esc(cite.short) in html
            # 書誌そのものはページに置かない
            assert cite.where not in html, f"{name} に書誌が入っている"


def test_sources_page_covers_every_reference(report):
    """出典は1ページにまとめ、どのページで使ったかを書く。"""
    d, _ = report
    html = (d / "sources.html").read_text(encoding="utf-8")
    for cite in cit.CITATIONS.values():
        assert cite.authors in html or _esc(cite.authors) in html
        assert cite.title in html or _esc(cite.title) in html
        assert cite.where in html or _esc(cite.where) in html
        assert cite.basis in html or _esc(cite.basis) in html
    assert "この OSS が自分で決めたこと" in html
    assert "使っているページ" in html


def test_sources_page_separates_our_own_choices(report):
    """典拠と、この OSS が自分で決めた部分を混ぜない。"""
    d, _ = report
    html = (d / "sources.html").read_text(encoding="utf-8")
    for feature, own in cit.OWN_CHOICES.items():
        assert f"id='{feature}'" in html, f"{feature} の節がない"
        assert own in html or _esc(own) in html


def test_sources_page_is_in_the_navigation(report):
    d, _ = report
    assert ("sources.html", "出典", "", "") in PAGES
    html = (d / "index.html").read_text(encoding="utf-8")
    assert "href='sources.html'" in html


def test_citations_carry_full_bibliographic_detail():
    """著者・年・題名・掲載先がそろっていないものを典拠として出さない。"""
    for key, c in cit.CITATIONS.items():
        assert c.key == key
        for field in ("authors", "year", "title", "where", "basis", "short"):
            assert getattr(c, field).strip(), f"{key} の {field} が空"
        assert c.year.isdigit() and 1900 < int(c.year) < 2100


def test_every_feature_is_mapped_to_a_citation():
    """典拠を書いていないページを作らない。"""
    features = {k for _f, _t, k, _q in PAGES if k}
    assert features <= set(cit.BY_FEATURE), "典拠の対応がないページがある"
    for keys in cit.BY_FEATURE.values():
        for k in keys:
            assert k in cit.CITATIONS, f"{k} の書誌がない"


# ---------- 言葉 ----------

def test_report_does_not_claim_what_it_did_not_observe(report):
    """観測したのは会議の同席だけ。知人・信頼・仲の良さは測っていない。

    社内ならほとんどが知人なので、「共通の知人」は数えたものを表さない。
    """
    d, _ = report
    for name, _t, _k, _q in PAGES:
        html = (d / name).read_text(encoding="utf-8")
        for word in ("共通の知人", "仲が良い", "信頼関係", "交流が活発", "コミュニケーション量"):
            assert word not in html, f"{name} に「{word}」がある"


def test_report_avoids_terms_the_reader_cannot_read(report):
    """読むのは人事担当者で、ネットワーク分析の用語を知らない。"""
    d, _ = report
    for name, _t, _k, _q in PAGES:
        html = (d / name).read_text(encoding="utf-8")
        for word in ("ノード", "エッジ", "被覆率", "単一障害点", "関節点",
                     "代替可能性", "代替率", "有向グラフ"):
            assert word not in html, f"{name} に「{word}」がある"


def test_replaceability_is_described_by_what_was_counted(report):
    """「代替率」ではなく、何を数えたかで書く。

    部門の組と、人と人の組の2つがある。どちらも名前で言い分け、
    何を数えたかを同じページに書く。
    """
    d, _ = report
    html = (d / "vulnerability.html").read_text(encoding="utf-8")
    assert "代わりの人がいる部門の組" in html
    assert "代わりの人がいる相手どうしの組" in html
    assert "その人以外にもその2部門をつないでいる人がいる組" in html
    assert "その人以外にも両方とつながっている人がいる組" in html
    # 個人の欄で「この人」を繰り返さない。氏名を主語にする
    assert "この人抜き" not in html
    assert "この人が抜けると" not in html


def test_citations_are_named_so_the_reader_knows_the_work(report):
    """「Leonardi & Contractor（2018）」では何の文献か分からない。"""
    d, _ = report
    html = (d / "ideation.html").read_text(encoding="utf-8")
    assert "バート『構造的空隙』（1992）" in html
    assert "『ピープルアナリティクスで人事戦略が変わる』第5章（2018）" in html
    for c in cit.CITATIONS.values():
        # 姓だけ・英語だけの短縮名を出さない
        assert len(c.short) >= 8, f"{c.key} の short が短すぎる: {c.short}"
        assert any("぀" <= ch <= "ヿ" for ch in c.short), \
            f"{c.key} の short に日本語の説明がない: {c.short}"


# ---------- 図 ----------

def _svgs(d: Path, page: str, chart: str) -> list[str]:
    html = (d / page).read_text(encoding="utf-8")
    return re.findall(rf"<svg data-chart='{chart}'.*?</svg>", html, re.S)


def test_charts_show_values_on_hover(report):
    """点が何を指しているかは、カーソルを合わせたときに出す。

    100点の散布図に全員の氏名を書くと重なって読めない。
    """
    d, _ = report
    for page, chart in [("influence.html", "scatter"), ("ideation.html", "strip"),
                        ("teams.html", "quadrant")]:
        svgs = _svgs(d, page, chart)
        assert svgs, f"{page} に {chart} がない"
        tips = re.findall(r'data-tip="([^"]+)"', svgs[0])
        assert len(tips) >= 5, f"{chart} の点に数値がない"
        assert all("&lt;b&gt;" in t for t in tips), "氏名を太字で出す"
    js = (d / "assets" / "app.js").read_text(encoding="utf-8")
    assert "data-chart" in js and "ctip" in js


def test_chart_labels_never_overlap(report):
    """重なったラベルは読めない。置けないものは出さない。"""
    d, _ = report
    for page, chart, cls in [("influence.html", "scatter", "sc-t"),
                             ("ideation.html", "strip", "st-t"),
                             ("teams.html", "quadrant", "q-t")]:
        for svg in _svgs(d, page, chart):
            boxes = []
            for m in re.finditer(
                rf"<text class='{cls}' x='([\d.-]+)' y='([\d.-]+)' text-anchor='(\w+)'>([^<]+)<",
                svg,
            ):
                x, y, anchor, text = float(m[1]), float(m[2]), m[3], m[4]
                w = sum(10.5 if ord(c) > 0x2000 else 5.8 for c in text)
                x0 = x if anchor == "start" else (x - w if anchor == "end" else x - w / 2)
                boxes.append((x0, y - 10.5, x0 + w, y + 2))
            for i, a in enumerate(boxes):
                for b in boxes[i + 1:]:
                    assert (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]), \
                        f"{page} の {chart} でラベルが重なっている"


def test_strip_separates_people_with_similar_values(report):
    """値が近い人を重ねて描くと、同じ位置に何名いるか分からない。"""
    d, _ = report
    svg = _svgs(d, "ideation.html", "strip")[0]
    lanes = {float(y) for y in re.findall(r"<circle[^>]*cy='([\d.]+)'", svg)}
    assert len(lanes) >= 2, "全員が1本の線の上に重なっている"


def test_charts_have_axis_ticks(report):
    """軸に数値がないと、点の位置が何を意味するか分からない。"""
    d, _ = report
    assert re.search(r"class='sc-tk'", _svgs(d, "influence.html", "scatter")[0])
    assert re.search(r"class='st-tk'", _svgs(d, "ideation.html", "strip")[0])
    assert re.search(r"class='q-tk'", _svgs(d, "teams.html", "quadrant")[0])


# ---------- 打ち手 ----------

def test_every_action_block_states_the_problem_first(report):
    """打ち手だけを並べても、なぜそれをするのかが分からない。

    何が起きているかを数値で先に書く。
    """
    d, _ = report
    for page in ("silo.html", "vulnerability.html", "influence.html",
                 "ideation.html", "teams.html"):
        html = (d / page).read_text(encoding="utf-8")
        blocks = re.findall(r"<div class='actions'>", html)
        probs = re.findall(r"<p class='prob'>", html)
        assert blocks, f"{page} に打ち手がない"
        assert len(probs) == len(blocks), \
            f"{page}: 打ち手 {len(blocks)} 枠に対し「いまの状態」が {len(probs)} 件"
        assert "いまの状態" in html


def test_the_problem_is_written_with_numbers(report):
    """「サイロ化しています」ではなく、何倍かを書く。"""
    d, _ = report
    for page in ("silo.html", "vulnerability.html", "influence.html",
                 "ideation.html", "teams.html"):
        html = (d / page).read_text(encoding="utf-8")
        for prob in re.findall(r"<p class='prob'>(.*?)</p>", html, re.S):
            assert re.search(r"\d", prob), f"{page} の「いまの状態」に数値がない: {prob[:60]}"
            assert "<b>" in prob, f"{page} の「いまの状態」で数値を強調していない"


def test_the_problem_does_not_repeat_the_card_summary(report):
    """カードの冒頭文と同じ内容を打ち手の枠で繰り返さない。"""
    d, snap = report
    html = (d / "vulnerability.html").read_text(encoding="utf-8")
    probs = re.findall(r"<p class='prob'>(.*?)</p>", html, re.S)
    assert probs
    for prob in probs:
        assert "社内の他の人とつながらなくなる" not in prob, "切り離される集団は上の節で書いている"
    # 打ち手が指す事実（後継者・会議時間）を書く
    assert any("いま最もつながりが重なるのは" in p for p in probs)


def test_actions_are_framed_as_conditional_on_a_goal(report):
    """その状態を変えるべきかは、その部門が担っている仕事で決まる。

    この OSS は仕事の中身を観測していないので、変えるべきだとは書けない。
    打ち手の見出しは「〜したい場合」にする。
    """
    d, _ = report
    goals = {
        "silo.html": {"この部門と他部門の往来を増やしたい場合"},
        "vulnerability.html": {"が抜けても接点が残るようにしたい場合"},
        "influence.html": {"新しい方針を全体に行き渡らせたい場合"},
        "ideation.html": {"部門をまたぐ発想を増やしたい場合"},
        "teams.html": {
            "この部門に仕事を割り当てるとき",
            "部門外との接点を増やしたい場合",
            "この部門が外から情報を受け取れるようにしたい場合",
            "いまの時間のまま、部門外に届く範囲を広げたい場合",
        },
    }
    for page, want in goals.items():
        html = (d / page).read_text(encoding="utf-8")
        found = set(re.findall(r"<p class='prob'>.*?</p><h3>([^<]*)</h3>", html, re.S))
        assert found, f"{page} に打ち手の見出しがない"
        # 個人のページは見出しに氏名が入る（「伊藤095 が抜けても…」）ので、末尾で見る
        bad = {x for x in found if not any(x.endswith(w) for w in want)}
        assert not bad, f"{page}: 想定外の見出し {bad}"
        assert "<h3>打ち手</h3>" not in html, f"{page} に条件のない「打ち手」が残っている"


def test_pages_say_the_state_may_be_acceptable(report):
    """数値が基準を超えていても、その部門の仕事によっては支障がない。"""
    d, _ = report
    for page, phrase in [
        ("silo.html", "業務上の関連がない部門どうしなら、つながりがなくても支障はありません"),
        ("ideation.html", "決まった相手と深く進める仕事なら、同じ顔ぶれに偏っていても支障はありません"),
        ("teams.html", "どの型がよいかは、その部門が担っている仕事で決まります"),
    ]:
        html = (d / page).read_text(encoding="utf-8")
        assert phrase in html, f"{page} に条件の断りがない"


# ---------- 見た目 ----------

def _css(d: Path) -> str:
    return (d / "assets" / "style.css").read_text(encoding="utf-8")


def test_only_the_tooltip_is_allowed_to_float(report):
    """影は、実際に他の要素に重なるものだけに使う。

    カードや表に影をつけると、読み物ではなく管理画面に見える。
    """
    d, _ = report
    for rule in re.findall(r"([^{}]+)\{([^}]*)\}", _css(d)):
        sel, body = rule[0].strip(), rule[1]
        if "box-shadow" not in body or "none" in body:
            continue
        assert ".ctip" in sel, f"{sel} に影がついている"


def test_hover_does_not_move_anything(report):
    """押せる場所が多い画面で要素が動くと、視線が揺れ続ける。"""
    d, _ = report
    for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", _css(d)):
        if ":hover" not in sel:
            continue
        assert "transform" not in body, f"{sel} でホバー時に動いている"
        assert "box-shadow" not in body, f"{sel} でホバー時に影が出る"


def test_corner_radius_is_small(report):
    """大きな丸みは、文書の中で要素だけが浮いて見える。"""
    d, _ = report
    for m in re.finditer(r"border-radius:\s*([\d.]+)px", _css(d)):
        assert float(m[1]) <= 6, f"角丸 {m[1]}px は大きい"


def test_headings_are_not_colored(report):
    """見出しは大きさ・太さ・余白で区切る。色で目立たせない。

    無彩色（黒・灰）は使ってよい。目立たせるための色を使わない。
    """
    neutral = {"var(--fg)", "var(--mut)", "var(--faint)", "inherit"}
    d, _ = report
    for sel, body in re.findall(r"([^{}]+)\{([^}]*)\}", _css(d)):
        if not re.match(r"^h[1-4]\b", sel.strip()):
            continue
        col = re.search(r"(?<!background-)color:\s*([^;]+)", body)
        if col:
            assert col[1].strip() in neutral, f"{sel} に目立たせるための色がついている"


def test_callouts_are_filled_blocks_with_an_icon(report):
    """左の縦線だけでは、注意書きなのか引用なのか見分けがつかない。"""
    d, _ = report
    css = _css(d)
    note = re.search(r"\.note\{([^}]*)\}", css)
    assert note and "background:var(--fill-gray)" in note[1]
    assert "border-left" not in note[1], "縦線ではなく塗りで示す"
    assert re.search(r"\.note::before\{[^}]*content:\"💬\"", css)
    assert re.search(r"\.note\.limit::before\{[^}]*content:\"⚠️\"", css)
    html = (d / "vulnerability.html").read_text(encoding="utf-8")
    assert "class='note limit'" in html


def test_examples_rank_internal_separation_above_external(report):
    """社外との窓口が1人なのは珍しくない。社内が切り離される話と同じ扱いにしない。"""
    _d, snap = report
    inside = [
        f for f in snap.findings
        if f.metric == "node_criticality"
        for g in (f.extra.get("separated_groups") or [])
        if any(str(x["group"]) != "（社外）" for x in (g.get("groups") or []))
    ]
    keys = [h["key"] for h in snap.highlights["examples"].get("vulnerability.html", [])]
    if inside:
        assert keys and keys[0] == "person_separates_internal", keys


def test_a_dept_story_is_not_told_on_two_pages(report):
    """同じ事実を2ページで繰り返すと、読者には別の問題が2件あるように見える。

    他部門との同席が0件の部門は「部門のつながり」に書く。
    「発想の起点となる人」では繰り返さず、そちらへ送る。
    """
    d, snap = report
    closed = [
        f.entity_label
        for f in snap.findings
        if f.metric == "ie_ratio" and f.extra.get("no_external_contact")
    ]
    if not closed:
        return
    ide = (d / "ideation.html").read_text(encoding="utf-8")
    assert "部門のつながり" in ide and "silo.html" in ide
    for dept in closed:
        block = re.search(
            rf"<h2>{re.escape(dept)}.*?(?=<h2>|<div class='note limit'><b>この指標の限界)",
            ide,
            re.S,
        )
        assert block, dept
        assert "class='actions'" not in block.group(0), (
            f"{dept} の打ち手が『部門のつながり』と重複している"
        )


def test_actions_are_not_the_same_text_for_everyone(report):
    """全員に同じ打ち手を出すと、読者は打ち手ごと読み飛ばす。

    同じ文面が、そのページの対象の半分を超えてはいけない。
    """
    for page in ("silo.html", "vulnerability.html", "teams.html", "ideation.html"):
        html = (report[0] / page).read_text(encoding="utf-8")
        blocks = re.findall(r"<h3>[^<]*</h3><ul>(.*?)</ul>", html, re.S)
        assert blocks, f"{page} に打ち手がない"
        if len(blocks) < 3:
            continue
        top = Counter(blocks).most_common(1)[0][1]
        assert top <= len(blocks) / 2, (
            f"{page}: {len(blocks)}件中{top}件が同じ打ち手になっている"
        )


def test_a_ratio_that_cannot_be_computed_is_not_printed_as_a_number(report):
    """部門外との会議が0件なら比は出せない。∞ は数値に見えるので使わない。"""
    d, _ = report
    html = (d / "silo.html").read_text(encoding="utf-8")
    assert "∞" not in html
    assert "-倍" not in html


def test_teams_near_the_median_are_not_given_a_type(report):
    """2つの軸はどちらも中央値で切っている。中央値付近の部門に型を付けない。"""
    d, snap = report
    teams = [f for f in snap.findings if f.metric == "density_x_range"]
    near = [f for f in teams if f.extra["reading"] == "typical"]
    html = (d / "teams.html").read_text(encoding="utf-8")
    for f in near:
        assert f.extra["quadrant_label"] == "中央値付近"
        assert not f.suggested_actions, f"{f.entity_label} に型から導いた打ち手が付いている"
        assert f"{f.entity_label}（中央値付近）" in html


def test_diffuse_teams_are_split_by_what_causes_it(report):
    """部門外との接点が少ない原因は2つある。原因で打ち手が変わる。"""
    _d, snap = report
    teams = [f for f in snap.findings if f.metric == "density_x_range"]
    readings = {f.extra["reading"] for f in teams}
    assert "diffuse" not in readings, "読み方を分けずに象限のまま打ち手を出している"
    for f in teams:
        if f.extra["reading"] == "diffuse_overlap":
            assert f.extra["external_nonredundancy"] < f.extra["median_external_nonredundancy"]
        if f.extra["reading"] == "diffuse_narrow":
            assert f.extra["external_nonredundancy"] >= f.extra["median_external_nonredundancy"]


def test_index_explains_the_method_before_the_results(report):
    """利用者はネットワーク分析を知らない。何をどう測ったかを数値より先に置く。"""
    d, _ = report
    html = (d / "index.html").read_text(encoding="utf-8")
    for phrase in ("この分析について", "データ", "分析内容"):
        assert phrase in html, phrase
    order = [html.index(x) for x in ("この分析について", "この分析で分かること")]
    assert order == sorted(order), "手法の説明が結果より後ろに出ている"
    # 会議の中身を取っていないことを、ここで必ず書く
    assert "会議の中身・件名・場所は取得していません" in html


def test_examples_do_not_restate_how_it_was_measured(report):
    """代表的な結果では測り方をなぞらない。

    何をどう測ったかは、同じカードの「数えたこと」と各ページにある。
    ここでもう一度なぞると、読み手が観測値から意味を組み立てることになる。
    """
    _d, snap = report
    for rows in snap.highlights["examples"].values():
        for h in rows:
            for w in ("会議", "同席", "出席"):
                assert w not in h["title"], f"{h['title']} に「{w}」が入っている"


def test_report_does_not_claim_a_contact_never_happened(report):
    """重みが下限に満たない組は、グラフを作る前に落としている。

    落とした記録があるので「1件もない」「一度もない」とは書けない。
    """
    d, snap = report
    assert snap.quality["edges_dropped_below_threshold"] > 0
    for page in ("index.html", "silo.html", "ideation.html"):
        html = (d / page).read_text(encoding="utf-8")
        for w in ("1件もありません", "一度も", "0件です"):
            assert w not in html, f"{page} に「{w}」がある"


def test_examples_show_strengths_as_well_as_gaps(report):
    """細くなっているところだけを並べると、何を保てばよいかが分からない。

    典拠が「この形なら成果が出やすい」としているものも代表的な結果に出す。
    """
    _d, snap = report
    rows = [h for v in snap.highlights["examples"].values() for h in v]
    groups = {h["group"] for h in rows}
    assert groups == {"strength", "gap"}, groups
    # 強みにも根拠を添える。良い形だと決めているのは研究であって、この OSS ではない
    for h in rows:
        if h["group"] == "strength":
            assert "研究" in h["detail"], h["title"]
    # 部門の型は、典拠が成果と結び付けている型を先に出す
    teams = [h["group"] for h in snap.highlights["examples"].get("teams.html", [])]
    assert teams and teams[0] == "strength", teams
