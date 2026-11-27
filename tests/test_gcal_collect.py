"""Google カレンダー収集のテスト（実APIは呼ばない）。

本文を要求しないこと、中断から再開できること、失敗の理由が人に分かる言葉で
返ることを固定する。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from relana.sources.gcal.collect import (
    FIELDS_BASE,
    FIELDS_WITH_TITLE,
    Checkpoint,
    estimate,
    fetch_events,
)


class _FakeHttpError(Exception):
    def __init__(self, status: int):
        super().__init__(f"HTTP {status}")
        self.resp = type("R", (), {"status": status})()


class FakeEvents:
    """events().list(...).execute() を模す。呼び出し引数を記録する。"""

    def __init__(self, store: dict, calls: list, fail: dict | None = None):
        self.store, self.calls, self.fail = store, calls, fail or {}

    def list(self, **kwargs):
        self.calls.append(kwargs)
        cal = kwargs["calendarId"]
        fail = self.fail

        class _Req:
            def execute(_self):
                if cal in fail:
                    raise _FakeHttpError(fail[cal])
                return {"items": store_for(cal)}

        store_for = lambda c: self.store.get(c, [])  # noqa: E731
        return _Req()


class FakeService:
    def __init__(self, store: dict, fail: dict | None = None):
        self.calls: list = []
        self._events = FakeEvents(store, self.calls, fail)

    def events(self):
        return self._events


def _event(eid: str, attendees: list[str] | None = None) -> dict:
    return {
        "id": eid,
        "iCalUID": f"{eid}@uid",
        "start": {"dateTime": "2026-01-06T10:00:00+00:00"},
        "end": {"dateTime": "2026-01-06T11:00:00+00:00"},
        "organizer": {"email": "a@x.co.jp"},
        "attendees": [{"email": e, "responseStatus": "accepted"} for e in (attendees or [])],
    }


def test_fields_never_request_message_content():
    """FR-1.5 は設定ではなく API 呼び出しの形で担保する。"""
    for fields in (FIELDS_BASE, FIELDS_WITH_TITLE):
        for forbidden in ("description", "location", "attachments", "conferenceData"):
            assert forbidden not in fields
    assert "summary" not in FIELDS_BASE
    assert "summary" in FIELDS_WITH_TITLE  # タイトルは明示的に有効化したときだけ


def test_fetch_passes_the_right_query():
    store = {"a@x.co.jp": [_event("e1", ["a@x.co.jp", "b@x.co.jp"])]}
    svc = FakeService(store)
    events, report = fetch_events(svc, ["a@x.co.jp"], window_days=30,
                                  end=datetime(2026, 3, 31, tzinfo=timezone.utc))
    assert len(events) == 1
    assert report.calendars_read == 1
    call = svc.calls[0]
    assert call["singleEvents"] is True, "定期会議を各回に展開していない"
    assert call["fields"] == FIELDS_BASE
    assert "description" not in str(call)


def test_titles_are_requested_only_when_enabled():
    svc = FakeService({"a@x.co.jp": []})
    fetch_events(svc, ["a@x.co.jp"], keep_titles=True,
                 end=datetime(2026, 3, 31, tzinfo=timezone.utc))
    assert svc.calls[0]["fields"] == FIELDS_WITH_TITLE


def test_unreadable_calendars_are_recorded_with_a_human_reason():
    """読めなかった理由が『次に何をすべきか』に繋がる言葉で残ること（原則3）。"""
    store = {"a@x.co.jp": [_event("e1", ["a@x.co.jp"])]}
    svc = FakeService(store, fail={"b@x.co.jp": 403, "c@x.co.jp": 404})
    events, report = fetch_events(svc, ["a@x.co.jp", "b@x.co.jp", "c@x.co.jp"],
                                  end=datetime(2026, 3, 31, tzinfo=timezone.utc))
    assert report.calendars_read == 1
    assert "共有されていない" in report.calendars_failed["b@x.co.jp"]
    assert "退職者" in report.calendars_failed["c@x.co.jp"]


def test_hidden_attendee_events_are_counted():
    """主催者が参加者リストを隠している予定は分析に使えない。件数を残す。"""
    store = {"a@x.co.jp": [_event("e1", ["a@x.co.jp"]), {**_event("e2"), "attendees": []}]}
    store["a@x.co.jp"][1].pop("attendees")
    svc = FakeService(store)
    _, report = fetch_events(svc, ["a@x.co.jp"], end=datetime(2026, 3, 31, tzinfo=timezone.utc))
    assert report.hidden_attendee_events == 1


def test_checkpoint_allows_resume(tmp_path: Path):
    """大規模では初回収集に時間がかかる。中断で成果がゼロにならないこと。"""
    store = {c: [_event(f"e{c}", [c])] for c in ("a@x.co.jp", "b@x.co.jp")}
    cp = tmp_path / "cp.json"
    svc1 = FakeService(store, fail={"b@x.co.jp": 500})
    _, r1 = fetch_events(svc1, list(store), checkpoint_path=cp,
                         end=datetime(2026, 3, 31, tzinfo=timezone.utc),
                         sleep=lambda _: None)
    assert r1.calendars_read == 1
    assert Checkpoint.load(cp).completed == {"a@x.co.jp": 1}

    svc2 = FakeService(store)
    _, r2 = fetch_events(svc2, list(store), checkpoint_path=cp,
                         end=datetime(2026, 3, 31, tzinfo=timezone.utc),
                         sleep=lambda _: None)
    # 済んだカレンダーは再取得しない
    assert [c["calendarId"] for c in svc2.calls] == ["b@x.co.jp"]
    assert r2.calendars_read == 2


def test_estimate_is_shown_before_running():
    est = estimate(["x"] * 100, 90)
    assert est["calendars"] == 100
    assert est["estimated_events"] > 0
    assert "約" in est["estimated_human"]


@pytest.mark.parametrize("n,days", [(10, 30), (100, 90), (1000, 90)])
def test_estimate_scales(n, days):
    est = estimate(["x"] * n, days)
    assert est["estimated_api_calls"] >= n


def test_permission_denied_is_not_retried():
    """403 は権限不足とレート制限の両方に使われる。

    区別せず再試行すると、共有されていないカレンダー1件ごとに数十秒を浪費する。
    共有設定が絞られている組織では 403 が大量に出るため、ここは致命的になる。
    """
    from relana.sources.gcal.collect import _with_backoff

    attempts = {"n": 0}

    def denied():
        attempts["n"] += 1
        raise _FakeHttpError(403)

    with pytest.raises(_FakeHttpError):
        _with_backoff(denied, sleep=lambda _: None)
    assert attempts["n"] == 1, "権限不足で再試行している"


def test_rate_limit_is_retried():
    from relana.sources.gcal.collect import _with_backoff

    attempts = {"n": 0}

    def limited():
        attempts["n"] += 1
        if attempts["n"] < 3:
            e = _FakeHttpError(403)
            e.content = b'{"error":{"errors":[{"reason":"rateLimitExceeded"}]}}'
            raise e
        return "ok"

    assert _with_backoff(limited, sleep=lambda _: None) == "ok"
    assert attempts["n"] == 3


def test_server_errors_are_retried():
    from relana.sources.gcal.collect import _with_backoff

    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise _FakeHttpError(503)
        return "ok"

    assert _with_backoff(flaky, sleep=lambda _: None) == "ok"
