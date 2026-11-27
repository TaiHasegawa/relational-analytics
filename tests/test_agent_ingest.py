"""エージェントのカレンダー連携から取り込む経路のテスト。

利用者に Google Cloud プロジェクトを作らせない経路。
エージェントは最小限の形で書くだけでよく、正規化は relana が受け持つ。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from relana.config import NormalizeConfig
from relana.sources.agent.ingest import (
    coverage_hint,
    detect_internal_domains,
    read_calendars,
    read_jsonl,
    record_read,
    suggest_next,
    to_gcal_shape,
)
from relana.sources.gcal.normalize import normalize

DOMAIN = "example.co.jp"


def _write(tmp: Path, records: list[dict]) -> Path:
    p = tmp / "cal.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
    return p


def _rec(**kw):
    base = {
        "id": "e1",
        "start": "2026-10-08T10:00:00+09:00",
        "end": "2026-10-08T11:00:00+09:00",
        "organizer": f"a@{DOMAIN}",
        "attendees": [{"email": f"a@{DOMAIN}"}, {"email": f"b@{DOMAIN}"}],
        "recurring": True,
    }
    base.update(kw)
    return base


def _normalized(records: list[dict], domains: list[str] | None = None, **cfg_kw):
    raw = [to_gcal_shape(r, i) for i, r in enumerate(records)]
    cfg = NormalizeConfig(internal_domains=domains or detect_internal_domains(raw), **cfg_kw)
    return normalize(raw, {}, cfg)


# ---------- 入力の寛容さ ----------

def test_attendees_may_be_plain_strings():
    """エージェントが書く手間を減らす。文字列配列でも受け付ける。"""
    out, _ = _normalized([_rec(attendees=[f"a@{DOMAIN}", f"b@{DOMAIN}"])])
    assert out[0].participant_count == 2


def test_minimal_record_is_accepted():
    """start と attendees だけで動く。"""
    out, _ = _normalized([{"start": "2026-10-08T10:00:00+09:00",
                           "attendees": [f"a@{DOMAIN}", f"b@{DOMAIN}"]}])
    assert len(out) == 1


def test_missing_required_fields_give_actionable_errors(tmp_path: Path):
    p = _write(tmp_path, [{"id": "x"}, {"start": "2026-10-08T10:00:00+09:00"}])
    res = read_jsonl(p)
    assert not res.ok
    assert all(i.code == "E_MISSING_FIELD" for i in res.issues)
    assert all(i.fix for i in res.issues)


def test_broken_json_does_not_stop_the_rest(tmp_path: Path):
    p = tmp_path / "cal.jsonl"
    p.write_text("{broken\n" + json.dumps(_rec()) + "\n", encoding="utf-8")
    res = read_jsonl(p)
    assert len(res.raw_events) == 1
    assert res.issues[0].code == "E_BAD_JSON"


# ---------- 社内・社外の判定 ----------

def test_internal_domain_is_detected_from_the_data():
    """名簿を用意させない以上、どこまでが社内かもデータから決める。"""
    raw = [to_gcal_shape(_rec(attendees=[f"a@{DOMAIN}", f"b@{DOMAIN}", "x@vendor.example.com"]), 0)]
    assert detect_internal_domains(raw) == [DOMAIN]


def test_other_large_domains_are_flagged_for_confirmation():
    """件数だけで複数の社内ドメインを言い当てるのは信用できない。確認を促す。"""
    from relana.sources.agent.ingest import domain_breakdown

    raw = [to_gcal_shape(_rec(attendees=[f"a@{DOMAIN}", f"b@{DOMAIN}", "x@group.example.jp"]), 0)]
    b = domain_breakdown(raw)
    assert b["internal"] == [DOMAIN]
    assert b["ambiguous"][0]["domain"] == "group.example.jp"


def test_internal_people_keep_plain_ids_without_a_roster():
    """名簿が無くても社内の人を ext: 扱いにしない。"""
    out, _ = _normalized([_rec()])
    assert out[0].attendees == [f"a@{DOMAIN}", f"b@{DOMAIN}"]
    assert all(not a.startswith("ext:") for a in out[0].attendees)


def test_external_participants_collapse_to_domain_entities():
    """社外は個人ごとではなくドメイン単位の1ノードにまとめる（❻の単一接点検出に使う）。"""
    out, _ = _normalized(
        [_rec(attendees=[f"a@{DOMAIN}", "x@vendor.example.com", "y@vendor.example.com"])],
        domains=[DOMAIN],
    )
    assert "ext:vendor.example.com" in out[0].attendees
    assert sum(1 for a in out[0].attendees if a.startswith("ext:")) == 1


def test_organizer_is_added_when_absent_from_attendees():
    """主催者は自分の会議に出ている。❷影響力の有向グラフで主催が効く。"""
    out, _ = _normalized([_rec(organizer=f"boss@{DOMAIN}",
                               attendees=[f"a@{DOMAIN}", f"b@{DOMAIN}"])])
    assert out[0].actor_id == f"boss@{DOMAIN}"
    assert f"boss@{DOMAIN}" in out[0].attendees


# ---------- タイトルの扱い ----------

def test_titles_are_kept_only_for_recurring_group_meetings():
    records = [
        _rec(id="g", attendees=[f"a@{DOMAIN}", f"b@{DOMAIN}", f"c@{DOMAIN}"], title="チーム定例"),
        _rec(id="d", attendees=[f"a@{DOMAIN}", f"b@{DOMAIN}"], title="1on1 評価面談"),
    ]
    out, _ = _normalized(records, keep_group_titles=True)
    by_id = {e.event_id: e for e in out}
    assert by_id["g"].group_title == "チーム定例"
    assert by_id["d"].group_title is None, "1on1 のタイトルが漏れている"


# ---------- 収集の進め方 ----------

def test_coverage_hint_counts_observed_people_and_pairs():
    raw = [to_gcal_shape(_rec(attendees=[f"{c}@{DOMAIN}" for c in "abcd"]), 0)]
    hint = coverage_hint(raw)
    assert hint["people_observed"] == 4
    assert hint["pair_observations"] == 6  # 4人の会議は6ペアを生む


def test_suggest_next_excludes_already_read_calendars():
    out, _ = _normalized([
        _rec(id="1", attendees=[f"a@{DOMAIN}", f"b@{DOMAIN}", f"c@{DOMAIN}"]),
        _rec(id="2", attendees=[f"a@{DOMAIN}", f"c@{DOMAIN}"]),
    ])
    s = suggest_next(out, already_read=[f"a@{DOMAIN}"])
    cals = [r["calendar"] for r in s["suggestions"]]
    assert f"a@{DOMAIN}" not in cals
    assert cals[0] == f"c@{DOMAIN}", "出現回数が多い順になっていない"


def test_leverage_shows_that_reading_everyone_is_unnecessary():
    """1人分を読むと複数名の関係が得られる。全員分を読む必要はない。"""
    out, _ = _normalized([_rec(attendees=[f"{c}@{DOMAIN}" for c in "abcdefgh"])])
    s = suggest_next(out, already_read=[f"a@{DOMAIN}"])
    assert s["people_observed"] == 8
    assert s["leverage"] == 8.0


def test_read_calendars_are_remembered_between_runs(tmp_path: Path):
    out = tmp_path / "interactions.csv"
    record_read(out, [f"a@{DOMAIN}"])
    record_read(out, [f"b@{DOMAIN}", f"a@{DOMAIN}"])
    assert read_calendars(out) == [f"a@{DOMAIN}", f"b@{DOMAIN}"]


@pytest.mark.parametrize("field", ["description", "location", "attachments", "hangoutLink"])
def test_unknown_fields_are_never_carried_through(field):
    """スキーマに無いものは通さない。エージェントが余計に書いても落ちる。"""
    out, _ = _normalized([_rec(**{field: "秘密の内容"})])
    assert "秘密の内容" not in repr(out[0])


# ---------- 名簿なしでの発見 ----------

def test_discovery_warns_when_headcount_is_unknown():
    """名簿なしでは分母が分からない。被覆率が循環した値になることを隠さない。"""
    from relana.core.doctor import diagnose
    from relana.core.org_inference import infer_people

    out, _ = _normalized([_rec(attendees=[f"{c}@{DOMAIN}" for c in "abc"])])
    persons = [p for p in infer_people(out) if not p.is_external]
    checks = {c.code: c for c in diagnose(out, persons)}
    assert "W_NO_HEADCOUNT" in checks
    assert "循環" in checks["W_NO_HEADCOUNT"].detail
    assert "--headcount" in checks["W_NO_HEADCOUNT"].action


def test_discovery_judges_against_real_headcount():
    """利用者に聞くのは人数ひとつだけ。名簿は要らない。"""
    from relana.core.doctor import diagnose
    from relana.core.org_inference import infer_people

    out, _ = _normalized([_rec(attendees=[f"{c}@{DOMAIN}" for c in "abcdefgh"])])
    persons = [p for p in infer_people(out) if not p.is_external]

    enough = {c.code: c for c in diagnose(out, persons, headcount=8)}["DISCOVERY"]
    assert enough.severity == "ok"
    assert enough.data["rate"] == 1.0

    short = {c.code: c for c in diagnose(out, persons, headcount=20)}["DISCOVERY"]
    assert short.severity == "critical"
    assert "next-calendars" in short.action or "偏って" in short.action


def test_snowball_finds_people_never_read():
    """1人分を読むだけで、その会議に出ていた全員が発見される。"""
    out, _ = _normalized([_rec(attendees=[f"{c}@{DOMAIN}" for c in "abcde"])])
    s = suggest_next(out, already_read=[f"a@{DOMAIN}"])
    assert s["calendars_read"] == 1
    assert s["people_observed"] == 5
    # 読んでいない4名が次の候補として挙がる
    assert len(s["suggestions"]) == 4
