"""共通データモデル。

原則2（スキーマ・ファースト）: アダプタが満たすべき契約はここに集約する。
本文・件名・場所はスキーマに含めない（FR-1.5）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

RESPONSE_ACCEPTED = "accepted"
RESPONSE_TENTATIVE = "tentative"
RESPONSE_NEEDS_ACTION = "needsAction"
RESPONSE_DECLINED = "declined"


@dataclass
class Person:
    """人マスタ。グルーピング軸と統制変数を兼ねる。"""

    person_id: str
    email: str
    display_name: str = ""
    dept: str = ""
    team: str = ""
    role: str = ""
    hired_at: date | None = None
    left_at: date | None = None
    is_bot: bool = False
    is_external: bool = False
    consent_status: str = "unknown"

    def active_on(self, when: date) -> bool:
        if self.hired_at and when < self.hired_at:
            return False
        if self.left_at and when > self.left_at:
            return False
        return True


@dataclass
class Interaction:
    """相互作用イベント。1会議 = 1件。

    ペアへの展開は graph 構築時に行う（ここでは展開しない）。
    """

    event_id: str
    ts: datetime
    source: str  # "calendar"
    channel_type: str  # "meeting"
    actor_id: str  # 主催者（有向グラフ用）
    target_ids: list[str]  # 主催者以外の参加者
    group_id: str | None = None  # iCalUID
    duration_min: int | None = None
    is_recurring: bool = False
    meeting_type: str = "unknown"
    # 定期グループ会議のタイトルのみ、明示的に有効化したときだけ入る。
    # 組織構造の推定にのみ使い、指標計算には一切使わない（§7.1 / FR-1.5）。
    # 1on1 と単発会議のタイトルは取得しない（個人的な内容が入りやすいため）。
    group_title: str | None = None
    responses: dict[str, str] = field(default_factory=dict)
    external_domains: list[str] = field(default_factory=list)

    @property
    def attendees(self) -> list[str]:
        """主催者を含む全参加者。"""
        if self.actor_id in self.target_ids:
            return list(self.target_ids)
        return [self.actor_id, *self.target_ids]

    @property
    def participant_count(self) -> int:
        return len(self.attendees)


@dataclass
class CollectionReport:
    """収集の品質メタ。被覆率の判断に使う（FR-1.18.4）。"""

    calendars_requested: int = 0
    calendars_read: int = 0
    calendars_failed: dict[str, str] = field(default_factory=dict)
    events_fetched: int = 0
    events_after_dedup: int = 0
    hidden_attendee_events: int = 0
