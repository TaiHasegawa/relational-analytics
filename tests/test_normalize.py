"""正規化 R1〜R8 のテスト。ここを飛ばすと分析結果が壊れる。"""

from relana.config import NormalizeConfig
from relana.models import Person
from relana.sources.gcal.normalize import infer_meeting_type, normalize

DOMAIN = "example.co.jp"


def _persons(n=4):
    return {
        f"u_{i}": Person(person_id=f"u_{i}", email=f"u{i}@{DOMAIN}", dept="D", team="T")
        for i in range(1, n + 1)
    }


def _ev(attendees, eid="e1", uid="uid1", start="2026-01-06T10:00:00+00:00", minutes=60, **kw):
    end = start.replace("10:00", "11:00") if minutes == 60 else start
    return {
        "id": eid,
        "iCalUID": uid,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
        "organizer": {"email": attendees[0]["email"]},
        "attendees": attendees,
        **kw,
    }


def _att(email, status="accepted", resource=False):
    a = {"email": email, "responseStatus": status}
    if resource:
        a["resource"] = True
    return a


def test_r1_resources_are_removed():
    """会議室を除去しないと、会議室が最強のハブノードになる。"""
    persons = _persons(2)
    ev = _ev([
        _att(f"u1@{DOMAIN}"),
        _att(f"u2@{DOMAIN}"),
        _att("room1@resource.calendar.google.com", resource=True),
    ])
    out, rep = normalize([ev], persons, NormalizeConfig(internal_domains=[DOMAIN]))
    assert rep.removed_resources == 1
    assert out[0].participant_count == 2
    assert all("resource" not in a for a in out[0].attendees)


def test_r3_declined_are_removed():
    persons = _persons(3)
    ev = _ev([_att(f"u1@{DOMAIN}"), _att(f"u2@{DOMAIN}"), _att(f"u3@{DOMAIN}", "declined")])
    out, rep = normalize([ev], persons, NormalizeConfig(internal_domains=[DOMAIN]))
    assert rep.removed_declined == 1
    assert out[0].participant_count == 2


def test_r4_single_attendee_events_are_dropped():
    """自分のブロック・休暇・リマインダは関係ではない。"""
    persons = _persons(1)
    ev = _ev([_att(f"u1@{DOMAIN}")])
    out, rep = normalize([ev], persons, NormalizeConfig(internal_domains=[DOMAIN]))
    assert out == []
    assert rep.dropped_too_few == 1


def test_r6_all_day_events_are_dropped():
    persons = _persons(2)
    ev = {
        "id": "e1",
        "iCalUID": "u",
        "start": {"date": "2026-01-06"},
        "end": {"date": "2026-01-07"},
        "organizer": {"email": f"u1@{DOMAIN}"},
        "attendees": [_att(f"u1@{DOMAIN}"), _att(f"u2@{DOMAIN}")],
    }
    out, rep = normalize([ev], persons, NormalizeConfig(internal_domains=[DOMAIN]))
    assert out == []
    assert rep.dropped_all_day == 1


def test_r8_same_meeting_from_multiple_calendars_is_deduped():
    """同じ会議は参加者の人数分だけ取得されるため、重複排除は必須。"""
    persons = _persons(3)
    att = [_att(f"u1@{DOMAIN}"), _att(f"u2@{DOMAIN}"), _att(f"u3@{DOMAIN}")]
    evs = [_ev(att, eid=f"e{i}", uid="same-uid") for i in range(3)]
    out, rep = normalize(evs, persons, NormalizeConfig(internal_domains=[DOMAIN]))
    assert len(out) == 1
    assert rep.dropped_duplicate == 2


def test_r2_external_domains_become_entities():
    persons = _persons(1)
    ev = _ev([_att(f"u1@{DOMAIN}"), _att("buyer@vendor.example.com")])
    out, _ = normalize([ev], persons, NormalizeConfig(internal_domains=[DOMAIN]))
    assert "ext:vendor.example.com" in out[0].attendees


def test_body_is_never_carried_through():
    """本文・件名・場所はスキーマに存在しない（FR-1.5）。"""
    persons = _persons(2)
    ev = _ev(
        [_att(f"u1@{DOMAIN}"), _att(f"u2@{DOMAIN}")],
        summary="機密: 人事評価の相談",
        description="本文",
        location="会議室A",
    )
    out, _ = normalize([ev], persons, NormalizeConfig(internal_domains=[DOMAIN]))
    blob = repr(out[0])
    assert "機密" not in blob and "本文" not in blob and "会議室A" not in blob


def test_meeting_type_inference():
    """会議タイトルを取らずに、人数・時間・定期性から種類を推定する（設計 §7.2）。"""
    from relana.models import Interaction
    from datetime import datetime, timezone

    def mk(targets, minutes, recurring, actor="u_1"):
        return Interaction(
            event_id="e", ts=datetime(2026, 1, 6, tzinfo=timezone.utc), source="calendar",
            channel_type="meeting", actor_id=actor, target_ids=targets,
            duration_min=minutes, is_recurring=recurring,
        )

    assert infer_meeting_type(mk(["u_2"], 30, True)) == "one_on_one_recurring"
    assert infer_meeting_type(mk(["u_2"], 30, False)) == "one_on_one_adhoc"
    assert infer_meeting_type(mk([f"u_{i}" for i in range(2, 6)], 90, False)) == "small_group_work"
    assert infer_meeting_type(mk([f"u_{i}" for i in range(2, 9)], 30, True)) == "team_standing"
    assert infer_meeting_type(mk([f"u_{i}" for i in range(2, 30)], 30, True)) == "broadcast"
    assert infer_meeting_type(mk(["ext:vendor.com"], 60, False)) == "external_meeting"
