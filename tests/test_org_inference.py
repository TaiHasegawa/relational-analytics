"""カレンダーだけから組織構造を推定できることのテスト。

合成データには正解の組織（12チーム・5部門・12名のマネジャー）が埋め込まれている。
利用者に名簿を用意させない以上、ここの精度がそのまま使い勝手になる。
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from itertools import combinations

import pytest

from relana.config import Config
from relana.core.graph import build_graphs
from relana.core.org_inference import infer_org, infer_people
from relana.demo import generate
from relana.sources.gcal.normalize import normalize

WINDOW_END = datetime(2026, 3, 31, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def inferred():
    raw, persons, meta = generate()
    cfg = Config()
    interactions, _ = normalize(raw, {p.person_id: p for p in persons}, cfg.normalize)
    # 推定はカレンダーだけで行う。正解の名簿は渡さない
    people = {p.person_id: p for p in infer_people(interactions)}
    bundle = build_graphs(interactions, people, cfg, WINDOW_END)
    org = infer_org(interactions, bundle.undirected)
    truth = {
        "team": {pid: t for t, i in meta["teams"].items() for pid in i["members"]},
        "dept": {pid: i["dept"] for i in meta["teams"].values() for pid in i["members"]},
        "managers": {i["members"][0] for i in meta["teams"].values()},
    }
    return org, truth


def _pairwise_f1(guess: dict[str, str], truth: dict[str, str]) -> tuple[float, float]:
    common = [p for p in guess if p in truth]
    tp = fp = fn = 0
    for a, b in combinations(sorted(common), 2):
        same_g, same_t = guess[a] == guess[b], truth[a] == truth[b]
        tp += same_g and same_t
        fp += same_g and not same_t
        fn += (not same_g) and same_t
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return precision, recall


def test_people_are_discovered_without_a_roster(inferred):
    org, _ = inferred
    internal = [p for p in org.persons if not p.is_external]
    assert len(internal) == 100


def test_teams_are_recovered_from_recurring_meetings(inferred):
    """定期グループ会議の固定メンバー = チーム。最も強い痕跡。"""
    org, truth = inferred
    guess = {m: t.team_id for t in org.teams for m in t.members}
    precision, recall = _pairwise_f1(guess, truth["team"])
    assert precision >= 0.95, f"精度が落ちている: {precision}"
    assert recall >= 0.95, f"再現率が落ちている: {recall}"
    assert org.evidence["unassigned_count"] == 0


def test_managers_are_recovered_from_one_on_one_patterns(inferred):
    """A が B・C・D と定期1on1 を持ち、B・C・D 同士は持たない星形が上下関係の痕跡。"""
    org, truth = inferred
    guessed = {t.manager for t in org.teams if t.manager}
    hit = guessed & truth["managers"]
    assert len(hit) >= len(truth["managers"]) - 1
    assert not (guessed - truth["managers"]), "マネジャーでない人を誤検出している"


def test_departments_are_a_usable_draft(inferred):
    """部門はチームより精度が落ちる。利用者が修正する前提なので下書きとして十分な水準を担保する。"""
    org, truth = inferred
    members_of = {t.team_id: t.members for t in org.teams}
    guess = {
        m: d for d, tids in org.departments.items() for t in tids for m in members_of.get(t, [])
    }
    precision, recall = _pairwise_f1(guess, truth["dept"])
    assert precision >= 0.7, f"部門推定の精度が低すぎる: {precision}"
    assert recall >= 0.7, f"部門推定の再現率が低すぎる: {recall}"


def test_all_hands_does_not_merge_every_department(inferred):
    """全社定例には全マネジャーが出るため、除外しないと全チームが1部門に融合する。"""
    org, _ = inferred
    assert len(org.departments) >= 3, "部門が融合している（全社会議を除外できていない）"


def test_draft_rows_tell_the_user_what_to_check(inferred):
    org, _ = inferred
    rows = org.as_person_rows()
    assert len(rows) >= 100
    assert {"person_id", "dept", "team", "role", "_confidence", "_source"} <= set(rows[0])
    assert any(r["role"] == "マネジャー" for r in rows)


def test_inferred_groups_carry_the_circularity_caveat():
    """推定した区分でサイロを測ると循環論法になりうる。その注記が必ず付くこと。"""
    from relana.core.analyze import analyze

    raw, persons, _ = generate()
    cfg = Config()
    cfg.analysis.groups_source = "inferred"
    interactions, _ = normalize(raw, {p.person_id: p for p in persons}, cfg.normalize)
    snap, _ = analyze(interactions, persons, cfg, WINDOW_END, "t")
    silo = [f for f in snap.findings if f.metric == "ie_ratio"]
    assert silo
    assert all(any("循環論法" in c for c in f.caveats) for f in silo)
    assert snap.groups_source == "inferred"


def test_provided_groups_do_not_carry_that_caveat():
    from relana.core.analyze import analyze

    raw, persons, _ = generate()
    cfg = Config()
    interactions, _ = normalize(raw, {p.person_id: p for p in persons}, cfg.normalize)
    snap, _ = analyze(interactions, persons, cfg, WINDOW_END, "t")
    silo = [f for f in snap.findings if f.metric == "ie_ratio"]
    assert all(not any("循環論法" in c for c in f.caveats) for f in silo)


def test_external_entities_are_not_counted_as_employees(inferred):
    from relana.core.analyze import analyze

    raw, persons, _ = generate()
    cfg = Config()
    interactions, _ = normalize(raw, {p.person_id: p for p in persons}, cfg.normalize)
    people = {p.person_id: p for p in infer_people(interactions)}
    snap, _ = analyze(interactions, list(people.values()), cfg, WINDOW_END, "t")
    assert snap.quality["persons_in_master"] == 100, "外部ドメインが社員数に混ざっている"
