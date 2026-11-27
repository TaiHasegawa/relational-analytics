"""既知グラフでの指標の正解値テスト（NFR-6）。

ネットワーク指標は「それらしい値」が出ても正しいとは限らないため、
構造が自明なグラフで期待どおりに振る舞うことを固定する。
"""

from itertools import combinations

import networkx as nx
import pytest

from relana.core.metrics import ideation, silo, team, vulnerability
from relana.core.metrics.vulnerability import replaceability


def _g(edges, attrs):
    g = nx.Graph()
    for node, a in attrs.items():
        g.add_node(node, is_external=a.get("is_external", False), display_name=node, **{
            k: v for k, v in a.items() if k != "is_external"
        })
    for a, b, w in edges:
        g.add_edge(a, b, weight=w)
    return g


def _members(names, dept="D", team_name="T"):
    return {n: {"dept": dept, "team": team_name, "role": ""} for n in names}


# ---------- ❺ サイロ ----------

def test_silo_ie_ratio_is_exact():
    """部門内3本・部門間1本 -> I/E = 3.0"""
    attrs = {**_members(["a1", "a2", "a3"], "A", "A"), **_members(["b1", "b2", "b3"], "B", "B")}
    edges = [
        ("a1", "a2", 1.0), ("a1", "a3", 1.0), ("a2", "a3", 1.0),
        ("b1", "b2", 1.0), ("b1", "b3", 1.0), ("b2", "b3", 1.0),
        ("a1", "b1", 1.0),
    ]
    out = {f.entity_id: f for f in silo.compute(_g(edges, attrs), "dept", threshold=5.0)}
    assert out["A"].value == pytest.approx(3.0)
    assert out["B"].value == pytest.approx(3.0)
    assert out["A"].status != "critical"


def test_silo_reports_the_baseline_for_the_department_size():
    """I/E 比は人数に左右される。ランダムに会った場合の値を併記する。

    100名の会社なら、12名の部門は 11/88 = 0.125、30名の部門は 29/70 = 0.414。
    何もしなくても大きい部門のほうが3倍高く出る。
    """
    small = [f"s{i}" for i in range(12)]
    big = [f"b{i}" for i in range(30)]
    rest = [f"r{i}" for i in range(58)]
    attrs = {**_members(small, "S", "S"), **_members(big, "B", "B"), **_members(rest, "R", "R")}
    edges = [(small[0], big[0], 1.0), (small[0], rest[0], 1.0), (big[0], rest[0], 1.0)]
    out = {f.entity_id: f for f in silo.compute(_g(edges, attrs), "dept")}
    assert out["S"].extra["expected_ie"] == pytest.approx(11 / 88, abs=0.01)
    assert out["B"].extra["expected_ie"] == pytest.approx(29 / 70, abs=0.01)
    assert out["B"].extra["expected_ie"] > out["S"].extra["expected_ie"] * 3


def test_silo_flags_a_small_department_that_the_absolute_threshold_misses():
    """絶対値 5:1 では拾えないが、人数で補正すると突出している部門を拾う。"""
    small = [f"s{i}" for i in range(6)]
    rest = [f"r{i}" for i in range(94)]
    attrs = {**_members(small, "S", "S"), **_members(rest, "R", "R")}
    edges = [(a, b, 1.0) for a, b in combinations(small, 2)]
    edges += [(small[0], rest[0], 1.0)]
    edges += [(a, b, 1.0) for a, b in combinations(rest[:6], 2)]
    out = {f.entity_id: f for f in silo.compute(_g(edges, attrs), "dept", threshold=5.0)}
    s_ratio, s_rel = out["S"].value, out["S"].extra["times_random"]
    assert s_ratio < 20, "この構成では絶対値はそれほど大きくならない"
    assert s_rel > s_ratio, "人数で補正すると、絶対値より大きく出る"
    assert out["S"].status in ("warning", "critical")


def test_silo_threshold_fires_at_five_to_one():
    attrs = {**_members(["a1", "a2", "a3"], "A", "A"), **_members(["b1"], "B", "B")}
    edges = [("a1", "a2", 10.0), ("a1", "a3", 10.0), ("a2", "a3", 10.0), ("a1", "b1", 1.0)]
    out = {f.entity_id: f for f in silo.compute(_g(edges, attrs), "dept", threshold=5.0)}
    assert out["A"].value == pytest.approx(30.0)
    assert out["A"].status == "critical"  # 閾値の2倍超


def test_silo_with_no_external_contact_shows_a_dash_not_a_number():
    """部門外との会議が0件なら比は計算できない。記号で示し、数値のふりをさせない。"""
    attrs = {**_members(["a1", "a2"], "A", "A"), **_members(["b1", "b2"], "B", "B")}
    edges = [("a1", "a2", 1.0), ("b1", "b2", 1.0)]
    out = {f.entity_id: f for f in silo.compute(_g(edges, attrs), "dept")}
    assert out["A"].value is None
    assert out["A"].extra["display"] == "-"
    assert out["A"].extra["times_random_display"] == "-"
    assert out["A"].extra["no_external_contact"] is True
    assert out["A"].extra["zero_contact_depts"] == ["B"]
    assert out["A"].extra["no_external_contact"] is True


# ---------- ❻ 脆弱性 ----------

def _barbell():
    """2つの三角形を1人(bridge)だけが繋ぐ構造。bridge は代替不能。"""
    names = ["a1", "a2", "a3", "bridge", "b1", "b2", "b3"]
    attrs = _members(names)
    edges = [
        ("a1", "a2", 1.0), ("a1", "a3", 1.0), ("a2", "a3", 1.0),
        ("b1", "b2", 1.0), ("b1", "b3", 1.0), ("b2", "b3", 1.0),
        ("a1", "bridge", 1.0), ("b1", "bridge", 1.0),
    ]
    return _g(edges, attrs)


def test_replaceability_is_zero_for_a_sole_bridge():
    g = _barbell()
    assert replaceability(g, "bridge") == pytest.approx(0.0)


def test_replaceability_is_one_when_an_alternative_exists():
    g = _barbell()
    g.add_edge("a1", "b1", weight=1.0)  # 別経路を足すと bridge は代替可能になる
    assert replaceability(g, "bridge") == pytest.approx(1.0)


def test_vulnerability_flags_the_articulation_point():
    out = {f.entity_id: f for f in vulnerability.compute(_barbell())}
    assert "bridge" in out
    assert out["bridge"].status == "critical"
    assert out["bridge"].extra["is_articulation_point"] is True
    assert out["bridge"].extra["replaceability"] == pytest.approx(0.0)


def test_vulnerability_detects_sole_external_contact():
    """アルビンド検出: 外部サプライヤーへの唯一の接点。"""
    names = ["a1", "a2", "a3", "albind"]
    attrs = _members(names)
    attrs["ext:supplier"] = {"dept": "", "team": "", "role": "", "is_external": True}
    edges = [
        ("a1", "a2", 1.0), ("a1", "a3", 1.0), ("a2", "a3", 1.0),
        ("albind", "a1", 1.0), ("albind", "a2", 1.0),
        ("albind", "ext:supplier", 1.0),
    ]
    out = {f.entity_id: f for f in vulnerability.compute(_g(edges, attrs))}
    assert "albind" in out
    sole = out["albind"].extra["sole_external_contacts"]
    assert [s["entity"] for s in sole] == ["ext:supplier"]
    assert "ext:supplier とつながっているのは、社内で albind だけ" in out["albind"].interprets_as


def test_vulnerability_never_claims_to_evaluate_people():
    out = vulnerability.compute(_barbell())
    assert all("処遇" in f.does_not_mean for f in out)


# ---------- ❶ 発想力 ----------

def test_constraint_is_lower_for_a_broker_than_a_clique_member():
    """ブローカー位置（3クラスタを繋ぐ）は、密な集団の一員より制約が低い。"""
    attrs = _members(["broker", "x1", "x2", "y1", "y2", "z1", "z2"])
    edges = [
        ("x1", "x2", 1.0), ("y1", "y2", 1.0), ("z1", "z2", 1.0),
        ("broker", "x1", 1.0), ("broker", "y1", 1.0), ("broker", "z1", 1.0),
        ("x1", "y1", 0.0001),
    ]
    out = {f.entity_id: f for f in ideation.compute(_g(edges, attrs), "dept")}
    assert out["broker"].value < out["x1"].value
    assert out["broker"].direction == "lower_is_better"


# ---------- ❸❹ チーム ----------

def test_team_quadrants_cover_all_four_cases():
    """内部密度 x 外部範囲で4象限に分かれること。

    中央値分割のため、チーム数が少ないと境界付近は不安定になる。
    ここでは4チームを明確に離して配置する。
    """
    attrs: dict = {}
    edges: list = []

    # 外部接続先のプール（min_size 未満のチームに置き、象限判定の対象から外す）
    pool = [f"o{i}" for i in range(24)]
    for i, o in enumerate(pool):
        attrs[o] = {"dept": "O", "team": f"out{i // 2}", "role": ""}

    def make(name, members, internal_w, n_external, offset):
        attrs.update(_members(members, name, name))
        if internal_w:
            for i, a in enumerate(members):
                for b in members[i + 1 :]:
                    edges.append((a, b, internal_w))
        for i, node in enumerate(members):
            for o in pool[offset + i * n_external : offset + (i + 1) * n_external]:
                edges.append((node, o, 1.0))

    #        name          members              内部   外部/人  pool offset
    make("efficiency_t", ["e1", "e2", "e3", "e4"], 5.0, 2, 0)
    make("closed_t", ["c1", "c2", "c3", "c4"], 5.0, 0, 0)
    make("innovation_t", ["i1", "i2", "i3", "i4"], 0.0, 2, 8)
    make("diffuse_t", ["f1", "f2", "f3", "f4"], 0.0, 0, 0)

    out = {f.entity_id: f for f in team.compute(_g(edges, attrs), "team", min_size=3)}
    assert out["efficiency_t"].extra["quadrant"] == "efficiency"
    assert out["closed_t"].extra["quadrant"] == "closed"
    assert out["innovation_t"].extra["quadrant"] == "innovation"
    assert out["diffuse_t"].extra["quadrant"] == "diffuse"

    # 同じ2変数を逆向きに読むことが設計の要点。警告文が必ず付く
    assert any("イノベーション集団としては失敗" in c for c in out["efficiency_t"].caveats)


def test_internal_density_is_not_biased_by_team_size():
    """1人あたりに正規化しているため、同じ結び付き方なら規模が違っても近い値になる。"""
    def ring(n, name):
        names = [f"{name}{i}" for i in range(n)]
        attrs = _members(names, name, name)
        edges = [(names[i], names[(i + 1) % n], 1.0) for i in range(n)]
        return attrs, edges

    a_attrs, a_edges = ring(4, "small")
    b_attrs, b_edges = ring(12, "big")
    g = _g(a_edges + b_edges, {**a_attrs, **b_attrs})
    out = {f.entity_id: f for f in team.compute(g, "team", min_size=3)}
    small = out["small"].extra["internal_density"]
    big = out["big"].extra["internal_density"]
    assert small == pytest.approx(big, rel=0.05)
    # 従来の「総重み / 可能ペア数」だと規模で大きくずれる
    assert out["small"].extra["classic_density"] > out["big"].extra["classic_density"] * 2



# ---------- ❷ 影響力 ----------

def test_influence_measures_betweenness_not_organizer():
    """主催者は使わない。他の人どうしの経路がどれだけその人を通るかを測る。"""
    from relana.core.metrics import influence

    # b は a と c/d/e の間に立つ。a-c の経路は必ず b を通る
    attrs = _members(["a", "b", "c", "d", "e", "f"])
    edges = [("a", "b", 1.0), ("b", "c", 1.0), ("b", "d", 1.0), ("b", "e", 1.0),
             ("f", "c", 1.0)]
    g = _g(edges, attrs)
    out = {f.entity_id: f for f in influence.compute(g, "dept")}
    assert out["b"].metric == "betweenness"
    assert out["b"].value > out["a"].value, "間に立つ b のほうが高い"
    assert out["a"].value == 0.0, "端にいる a を通る経路はない"
    assert out["a"].extra["direct_contacts"] == 1
    assert "organized" not in str(out["a"].extra)


def test_influence_finds_brokers_with_few_contacts():
    """典拠: 少人数でも強力なつながりを持ち、アイデアが遠くまで広がる人物。"""
    from relana.core.metrics import influence

    left = [f"l{i}" for i in range(6)]
    right = [f"r{i}" for i in range(6)]
    attrs = _members(["gate"] + left + right)
    # gate は2名としか直接つながらないが、左右の集団をつなぐ唯一の経路
    edges = [("gate", "l0", 1.0), ("gate", "r0", 1.0)]
    edges += [(a, b, 1.0) for a in left for b in left if a < b]
    edges += [(a, b, 1.0) for a in right for b in right if a < b]
    out = {f.entity_id: f for f in influence.compute(_g(edges, attrs), "dept")}

    assert out["gate"].extra["direct_contacts"] < out["l0"].extra["direct_contacts"]
    assert out["gate"].value > out["l0"].value, "直接の相手が少なくても経路は通る"

    div = influence.divergence_ranking(list(out.values()))
    assert div[0]["person_id"] == "gate"
    assert div[0]["betweenness"] >= influence.MIN_BETWEENNESS
    assert div[0]["direct"] <= div[0]["direct_median"]


def test_influence_divergence_skips_people_who_are_merely_isolated():
    """直接の相手が2名しかいないだけの人を「通り道」と呼ばない。

    媒介中心性そのものが低い人を上位に出すと、周知の相手として誤った人を示す。
    """
    from relana.core.metrics import influence

    left = [f"l{i}" for i in range(6)]
    right = [f"r{i}" for i in range(6)]
    attrs = _members(["gate", "lonely"] + left + right)
    edges = [(a, b, 1.0) for a in left for b in left if a < b]
    edges += [(a, b, 1.0) for a in right for b in right if a < b]
    # gate は2名としか直接つながらないが、左右をつなぐ唯一の経路
    edges += [("gate", "l0", 1.0), ("gate", "r0", 1.0)]
    # lonely も2名としかつながらないが、どちらも同じ集団の中。経路は1本も通らない
    edges += [("lonely", "l1", 1.0), ("lonely", "l2", 1.0)]
    out = list(influence.compute(_g(edges, attrs), "dept"))
    by = {f.entity_id: f for f in out}
    assert by["lonely"].extra["direct_contacts"] == by["gate"].extra["direct_contacts"]
    assert by["lonely"].value == 0.0
    div = influence.divergence_ranking(out)
    assert "gate" in {r["person_id"] for r in div}
    assert "lonely" not in {r["person_id"] for r in div}, "直接の相手が少ないだけの人を出さない"
    for row in div:
        assert row["betweenness"] >= influence.MIN_BETWEENNESS, "順位ではなく実際の値で切る"


def test_influence_never_uses_the_organizer_field():
    """主催の記録は代理設定で汚れるため、分析に使わない。"""
    import inspect
    from relana.core.metrics import influence
    from relana.core import graph as graph_mod

    for mod in (influence, graph_mod):
        src = inspect.getsource(mod)
        body = "\n".join(
            ln for ln in src.split("\n") if not ln.strip().startswith("#")
        )
        assert "actor_id" not in body.split('"""')[-1], f"{mod.__name__} が主催者を使っている"
