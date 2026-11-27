"""名簿のレビューと並列バッチ分割のテスト。

名簿を利用者に用意させない代わりに、収集データから作った名簿を見せて確認してもらう。
実測では、名簿が全社の55%しかないまま分析まで進んだ事例がある。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from relana.core.roster import build, render_text, split_batches, write_batches
from relana.models import Interaction, Person

D = "x.co.jp"


def _ev(i: int, members: list[str]) -> Interaction:
    return Interaction(
        event_id=f"e{i}",
        ts=datetime(2026, 1, 6, tzinfo=timezone.utc),
        source="calendar",
        channel_type="meeting",
        actor_id=members[0],
        target_ids=members[1:],
        duration_min=60,
    )


def _people(**kw) -> list[Person]:
    return [
        Person(person_id=f"{n}@{D}", email=f"{n}@{D}", display_name=n, dept=d, team=t, role=r)
        for n, (d, t, r) in kw.items()
    ]


def test_roster_groups_people_by_department():
    persons = _people(
        a=("営業本部", "東日本", "マネジャー"),
        b=("営業本部", "東日本", ""),
        c=("開発本部", "コア", "マネジャー"),
    )
    ints = [_ev(1, [f"a@{D}", f"b@{D}"]), _ev(2, [f"a@{D}", f"c@{D}"])]
    review = build(ints, persons)
    assert set(review.by_dept) == {"営業本部", "開発本部"}
    assert len(review.by_dept["営業本部"]) == 2


def test_missing_people_are_counted_against_headcount():
    """実測で45%の欠落を見逃した原因への対策。分母を渡せば不足が出る。"""
    persons = _people(a=("営業", "T", ""), b=("営業", "T", ""))
    review = build([_ev(1, [f"a@{D}", f"b@{D}"])], persons, headcount=10)
    assert review.missing == 8
    text = render_text(review)
    assert "8名が見つかっていません" in text
    assert "どの部署の方が抜けているか" in text


def test_no_headcount_asks_the_user_instead():
    persons = _people(a=("営業", "T", ""), b=("営業", "T", ""))
    text = render_text(build([_ev(1, [f"a@{D}", f"b@{D}"])], persons))
    assert "抜けている方" in text


def test_group_addresses_are_dropped_before_the_roster():
    """sales@ info@ のような確実なものは正規化で落ちる。名簿に現れない。"""
    from relana.core.group_address import is_group_address

    assert is_group_address(f"sureside-sales@{D}")
    assert is_group_address(f"info@{D}")
    assert is_group_address(f"all-aias@{D}")
    # 実在の人を落とさない
    assert not is_group_address(f"pr.tanaka@{D}")
    assert not is_group_address(f"tanaka.taro@{D}")


def test_external_group_addresses_are_not_dropped():
    """sales@取引先.com は実在の取引関係。外部エンティティとして残す必要がある。"""
    from relana.config import NormalizeConfig
    from relana.sources.gcal.normalize import normalize

    ev = {
        "id": "e1", "iCalUID": "u1",
        "start": {"dateTime": "2026-01-06T10:00:00+00:00"},
        "end": {"dateTime": "2026-01-06T11:00:00+00:00"},
        "organizer": {"email": f"a@{D}"},
        "attendees": [{"email": f"a@{D}"}, {"email": "sales@vendor.example.com"}],
    }
    out, rep = normalize([ev], {}, NormalizeConfig(internal_domains=[D]))
    assert "ext:vendor.example.com" in out[0].attendees
    assert rep.removed_group_addresses == 0


def test_remaining_suspects_are_judged_by_behaviour_not_name():
    """名前だけで疑うと pr.tanaka@ のような実在の人を誤判定する。
    1on1 が一度も無いという振る舞いを主判定にする。"""
    ints = [_ev(i, [f"a@{D}", f"b@{D}", f"c@{D}"]) for i in range(6)]
    review = build(ints, _people(a=("営業", "T", ""), b=("営業", "T", ""), c=("営業", "T", "")))
    assert any("1on1 が一度も無い" in f for e in review.entries for f in e.flags)

    # 1on1 がある人は、名前がグループ的でも疑われない
    ints2 = ints + [_ev(99, [f"pr.tanaka@{D}", f"a@{D}"])]
    review2 = build(ints2, _people(**{"pr.tanaka": ("営業", "T", "")}))
    tanaka = next(e for e in review2.entries if e.person_id == f"pr.tanaka@{D}")
    assert not any("グループ" in f for f in tanaka.flags)


def test_unknown_department_is_shown_separately():
    """所属が分からない人を混ぜて隠さない。"""
    ints = [_ev(1, [f"a@{D}", f"unknown@{D}"])]
    review = build(ints, _people(a=("営業", "T", "")))
    assert any(d.startswith("（") for d in review.by_dept)
    assert "所属が不明" in str([e.flags for e in review.entries])


# ---------- 並列収集 ----------

def test_batches_split_evenly_and_deduplicate():
    emails = [f"u{i}@{D}" for i in range(25)] + [f"u0@{D}"]
    batches = split_batches(emails, size=12)
    assert [len(b) for b in batches] == [12, 12, 1]
    assert sum(len(b) for b in batches) == 25  # 重複は除かれる


def test_each_batch_gets_its_own_working_directory(tmp_path: Path):
    """実測で、共有ディレクトリへの書き込み衝突により出力が壊れた。
    ディレクトリの分離はエージェントの裁量ではなく仕様。"""
    plan = write_batches([f"u{i}@{D}" for i in range(20)], tmp_path, size=12)
    assert len(plan) == 2
    dirs = {b["workdir"] for b in plan}
    assert len(dirs) == 2, "バッチが同じディレクトリを共有している"
    for b in plan:
        targets = Path(b["targets_file"])
        assert targets.exists()
        assert len(targets.read_text(encoding="utf-8").strip().splitlines()) == b["count"]
        assert Path(b["workdir"]) in Path(b["output_file"]).parents


def test_batch_targets_are_written_for_the_subagent(tmp_path: Path):
    plan = write_batches([f"b@{D}", f"a@{D}"], tmp_path, size=12)
    lines = Path(plan[0]["targets_file"]).read_text(encoding="utf-8").split()
    assert lines == [f"a@{D}", f"b@{D}"]  # 決定論的な順序


# ---------- 波状収集 ----------

def test_wave_targets_people_observed_but_not_yet_read():
    """収集中に新しい人が見つかるのは正常。次の波で回収する。"""
    from relana.core.roster import plan_wave

    ints = [_ev(1, [f"a@{D}", f"b@{D}", f"c@{D}"]), _ev(2, [f"a@{D}", f"d@{D}"])]
    wave, warnings = plan_wave(ints, already_read=[f"a@{D}"])
    assert wave.unread == [f"b@{D}", f"c@{D}", f"d@{D}"]
    assert not wave.converged
    assert not warnings


def test_wave_converges_when_everyone_has_been_read():
    from relana.core.roster import plan_wave

    ints = [_ev(1, [f"a@{D}", f"b@{D}"])]
    wave, _ = plan_wave(ints, already_read=[f"a@{D}", f"b@{D}"])
    assert wave.converged
    assert wave.unread == []


def test_wave_never_targets_external_entities():
    """社外は社員ではない。波の対象にしない。"""
    from relana.core.roster import plan_wave

    ints = [_ev(1, [f"a@{D}", "ext:vendor.example.com"])]
    wave, _ = plan_wave(ints, already_read=[f"a@{D}"])
    assert wave.unread == []
    assert wave.external_skipped == 1


def test_wave_warns_when_discovery_explodes():
    """未読が不自然に増えたら、顧客ドメインを社内と誤判定している可能性がある。"""
    from relana.core.roster import plan_wave

    ints = [_ev(1, [f"u{i}@{D}" for i in range(30)])]
    _, warnings = plan_wave(ints, already_read=[f"u0@{D}"])
    assert warnings
    assert "不自然に多い" in warnings[0]
