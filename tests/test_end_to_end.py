"""合成データに意図的に埋め込んだ構造を検出し続けることを保証する。

これが通らなくなった場合、パイプラインのどこかが壊れている。
"""

from datetime import datetime, timezone

import pytest

from relana.config import Config
from relana.core.analyze import analyze
from relana.demo import generate
from relana.sources.gcal.normalize import normalize

WINDOW_END = datetime(2026, 3, 31, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def result():
    raw, persons, meta = generate()
    cfg = Config()
    pmap = {p.person_id: p for p in persons}
    interactions, nrep = normalize(raw, pmap, cfg.normalize)
    snap, bundle = analyze(interactions, persons, cfg, WINDOW_END, "test", normalize_report=nrep)
    return snap, bundle, nrep


def test_pipeline_runs_and_covers_everyone(result):
    snap, bundle, _ = result
    q = snap.quality
    assert q["persons_in_master"] == 100
    assert q["edge_coverage_rate"] >= 0.95
    assert q["edges"] > 100


def test_duplicates_and_resources_are_stripped(result):
    _, _, nrep = result
    assert nrep.dropped_duplicate > 0, "同じ会議が複数カレンダーから来る前提が崩れている"
    assert nrep.removed_resources > 0, "会議室リソースが除去されていない"
    assert nrep.dropped_all_day > 0


def test_all_hands_does_not_destroy_the_graph(result):
    """100名の全社会議は 4,950 ペアを生むが、重み関数により実質ゼロになるはず。"""
    snap, bundle, _ = result
    n = bundle.undirected.number_of_nodes()
    max_edges = n * (n - 1) / 2
    density = bundle.undirected.number_of_edges() / max_edges
    assert density < 0.2, "全社会議でグラフが完全グラフ化している"
    # 辞退者を除くため人数はちょうど100にはならない
    sizes = snap.quality["meeting_size_histogram"]
    assert max(sizes) >= 80, "全社規模の会議がデータに存在しない"


def test_planted_silo_is_detected(result):
    """サポートと業務は部門間の会議を持たないよう生成している。

    部門は1階層にしたので、合成データの「運営本部」はこの2部門として出る。
    """
    snap, _, _ = result
    silos = {f.entity_id: f for f in snap.findings if f.metric == "ie_ratio"}
    for name in ("サポート", "業務"):
        assert silos[name].status == "critical"
        # 残っている接点は互いの間だけ。他の10部門との接点はない
        assert set(silos[name].extra["zero_contact_depts"]) == {
            "PR", "QA", "アーキテクチャ", "コア", "デジタル",
            "パッケージング", "人事", "東日本", "経理", "西日本",
        } - {name}
    assert silos["東日本"].status == "ok"


def test_planted_bridge_person_is_detected(result):
    """u_001 は部門を跨ぎ、外部サプライヤーへの唯一の接点として生成している。"""
    snap, _, _ = result
    vuln = {f.entity_id: f for f in snap.findings if f.feature == "vulnerability"}
    assert "u_001" in vuln, "アルビンドに相当する人物が検出されていない"
    f = vuln["u_001"]
    assert f.status == "critical"
    assert [s["entity"] for s in f.extra["sole_external_contacts"]] == [
        "ext:pkg-vendor.example.com"
    ]
    assert f.extra["succession_candidates"], "後継者候補が提示されていない"
    assert "pkg-vendor.example.com とつながっているのは、社内で 田中001 だけ" in f.interprets_as


def test_planted_team_profiles_land_in_the_right_quadrants(result):
    snap, _, _ = result
    teams = {f.entity_id: f.extra for f in snap.findings if f.feature == "team"}
    assert teams["アーキテクチャ"]["quadrant"] == "innovation"
    assert teams["QA"]["quadrant"] == "efficiency"
    assert teams["経理"]["quadrant"] == "closed"


def test_every_finding_carries_interpretation_metadata(result):
    """原則4: 数値だけを出さない。解釈と限界が必ず付く。"""
    snap, _, _ = result
    for f in snap.findings:
        assert f.source, f"{f.metric} に出典がない"
        assert f.interprets_as, f"{f.metric} に解釈がない"
        assert f.does_not_mean, f"{f.metric} に限界の記載がない"


def test_calendar_caveat_is_always_present(result):
    """会議データのみに基づくことを隠さない。"""
    snap, _, _ = result
    personal = [f for f in snap.findings if f.level in ("person", "team")]
    assert personal
    assert all(any("集計したのは会議の同席だけ" in c for c in f.caveats) for f in personal)


def test_vulnerability_disclaims_use_for_evaluation(result):
    snap, _, _ = result
    for f in snap.findings:
        if f.feature == "vulnerability":
            assert "処遇" in f.does_not_mean and "評価" in f.does_not_mean


def test_snapshot_is_json_serializable_and_reproducible(result):
    import json

    snap, _, _ = result
    blob = json.dumps(snap.to_dict(), ensure_ascii=False)
    assert len(blob) > 1000
    assert snap.config_hash and snap.code_version

    raw2, persons2, _ = generate()
    cfg2 = Config()
    inter2, _ = normalize(raw2, {p.person_id: p for p in persons2}, cfg2.normalize)
    snap2, _ = analyze(inter2, persons2, cfg2, WINDOW_END, "test")
    assert snap2.quality["edges"] == snap.quality["edges"], "同じ入力で結果が変わっている"


def test_report_renders(result, tmp_path):
    from relana.report.pages import write

    snap, bundle, _ = result
    entry = write(snap, bundle, tmp_path / "report")
    assert entry.exists()
    html = entry.read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert "リレーショナル分析" in html
