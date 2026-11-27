"""Google カレンダーからの収集（設計 §4.2）。

取得項目は fields パラメータで明示的に絞る。これが FR-1.5（本文を取得しない）の
実装そのものであり、設定ではなく API 呼び出しの形で担保する。

summary（会議タイトル）は、組織構造の推定に使う場合のみ、明示的に要求する。
description / location / attachments / conferenceData は一切要求しない。
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from ...models import CollectionReport

# 本文を要求しない。ここに summary / description を足さない限り取得されない。
FIELDS_BASE = (
    "items(id,iCalUID,start,end,organizer(email),recurringEventId,"
    "attendees(email,responseStatus,resource,self,organizer)),nextPageToken"
)
FIELDS_WITH_TITLE = FIELDS_BASE.replace("items(id,", "items(id,summary,")

MAX_RESULTS = 2500
MAX_RETRIES = 6


@dataclass
class CollectProgress:
    total: int = 0
    done: int = 0
    current: str = ""
    events: int = 0

    @property
    def pct(self) -> float:
        return self.done / self.total if self.total else 0.0


@dataclass
class Checkpoint:
    """中断・再開のための状態（FR-1.7）。大規模では初回収集に時間がかかる。"""

    path: Path
    completed: dict[str, int] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Checkpoint":
        p = Path(path)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            return cls(path=p, completed=data.get("completed", {}), failed=data.get("failed", {}))
        return cls(path=p)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"completed": self.completed, "failed": self.failed}, ensure_ascii=False),
            encoding="utf-8",
        )


def estimate(calendars: Iterable[str], window_days: int) -> dict[str, Any]:
    """実行前に所要時間を提示する（FR-1.6 `--dry-run`）。

    1人あたり1営業日3〜5件、ページあたり最大2500件という前提から概算する。
    """
    n = len(list(calendars))
    business_days = window_days * 5 / 7
    events_per_person = business_days * 4
    total_events = int(n * events_per_person)
    pages = max(n, int(total_events / MAX_RESULTS) + n)
    seconds = pages * 0.6
    return {
        "calendars": n,
        "window_days": window_days,
        "estimated_events": total_events,
        "estimated_api_calls": pages,
        "estimated_seconds": int(seconds),
        "estimated_human": _human(seconds),
    }


def _human(seconds: float) -> str:
    if seconds < 90:
        return f"約{int(seconds)}秒"
    if seconds < 5400:
        return f"約{int(seconds / 60)}分"
    return f"約{seconds / 3600:.1f}時間"


def fetch_events(
    service,
    calendars: list[str],
    window_days: int = 90,
    end: datetime | None = None,
    keep_titles: bool = False,
    checkpoint_path: Path | None = None,
    on_progress: Callable[[CollectProgress], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[list[dict], CollectionReport]:
    """各メンバーのカレンダーから会議を取得する。

    同じ会議は参加者の人数分だけ返るが、重複排除は normalize（R8）で行う。
    ここでは取得だけに責任を持つ。
    """
    end = end or datetime.now(timezone.utc)
    start = end - timedelta(days=window_days)
    time_min, time_max = start.isoformat(), end.isoformat()
    fields = FIELDS_WITH_TITLE if keep_titles else FIELDS_BASE

    cp = Checkpoint.load(checkpoint_path) if checkpoint_path else None
    report = CollectionReport(calendars_requested=len(calendars))
    out: list[dict] = []
    progress = CollectProgress(total=len(calendars))

    for cal in calendars:
        progress.current = cal
        if cp and cal in cp.completed:
            progress.done += 1
            report.calendars_read += 1
            if on_progress:
                on_progress(progress)
            continue

        try:
            events = _fetch_one(service, cal, time_min, time_max, fields, sleep)
        except Exception as e:  # noqa: BLE001
            reason = _explain(e)
            report.calendars_failed[cal] = reason
            if cp:
                cp.failed[cal] = reason
                cp.save()
            progress.done += 1
            if on_progress:
                on_progress(progress)
            continue

        out.extend(events)
        report.calendars_read += 1
        report.events_fetched += len(events)
        report.hidden_attendee_events += sum(1 for e in events if not e.get("attendees"))
        progress.done += 1
        progress.events += len(events)
        if cp:
            cp.completed[cal] = len(events)
            cp.save()
        if on_progress:
            on_progress(progress)

    return out, report


def _fetch_one(
    service,
    calendar_id: str,
    time_min: str,
    time_max: str,
    fields: str,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict]:
    items: list[dict] = []
    page_token = None
    while True:
        resp = _with_backoff(
            lambda: service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,  # 定期会議を各回に展開する
                maxResults=MAX_RESULTS,
                fields=fields,
                pageToken=page_token,
            )
            .execute(),
            sleep=sleep,
        )
        items.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            return items


# 403 はレート制限と権限不足の両方に使われる。区別せず再試行すると、
# 共有されていないカレンダー1件ごとに数十秒を浪費する。
# 共有設定が絞られている組織では 403 が大量に出るため、ここは必ず区別する。
_RATE_LIMIT_MARKERS = (
    "ratelimitexceeded",
    "userratelimitexceeded",
    "quotaexceeded",
    "backenderror",
)


def _is_rate_limited(e: Exception) -> bool:
    blob = str(getattr(e, "content", "") or "").lower() + str(e).lower()
    return any(m in blob for m in _RATE_LIMIT_MARKERS)


def _with_backoff(call: Callable[[], Any], sleep: Callable[[float], None] = time.sleep) -> Any:
    """レート制限と一時障害から自動回復する（NFR-13）。

    権限不足（共有されていないカレンダー）は即座に諦める。再試行しても通らない。
    """
    for attempt in range(MAX_RETRIES):
        try:
            return call()
        except Exception as e:  # noqa: BLE001
            status = getattr(getattr(e, "resp", None), "status", None)
            if status == 403 and not _is_rate_limited(e):
                raise  # 権限不足。再試行しない
            if status not in (403, 429, 500, 502, 503, 504) or attempt == MAX_RETRIES - 1:
                raise
            sleep(min(2**attempt + random.random(), 32))
    raise RuntimeError("unreachable")


def _explain(e: Exception) -> str:
    """失敗の理由を、利用者が次に何をすべきか分かる言葉にする（原則3）。"""
    status = getattr(getattr(e, "resp", None), "status", None)
    return {
        403: "権限がありません（カレンダーが共有されていない可能性）",
        404: "カレンダーが見つかりません（退職者・アドレス誤り）",
        401: "認証が切れています。接続し直してください",
    }.get(status, f"{type(e).__name__}: {e}")


def list_domain_users(directory, domain: str | None = None, max_users: int = 500) -> list[str]:
    """Admin SDK でドメイン内のユーザーを列挙する（管理者権限が必要）。"""
    emails: list[str] = []
    page_token = None
    while len(emails) < max_users:
        resp = _with_backoff(
            lambda: directory.users()
            .list(
                customer="my_customer" if not domain else None,
                domain=domain,
                maxResults=min(500, max_users - len(emails)),
                orderBy="email",
                fields="users(primaryEmail,suspended,orgUnitPath,name/fullName),nextPageToken",
                pageToken=page_token,
            )
            .execute()
        )
        for u in resp.get("users", []):
            if not u.get("suspended"):
                emails.append(u["primaryEmail"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return emails


def report_to_dict(report: CollectionReport) -> dict[str, Any]:
    return asdict(report)
