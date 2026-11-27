"""Google カレンダーの生イベント -> interactions（設計 §5）。

ここが分析品質を決める。素のカレンダーをそのまま使うと結果が壊れる。
特に R1（会議室リソースの除去）は必須。除去しないと会議室が最強のハブになる。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ...config import NormalizeConfig
from ...models import RESPONSE_DECLINED, Interaction, Person


@dataclass
class NormalizeReport:
    seen: int = 0
    kept: int = 0
    dropped_all_day: int = 0
    dropped_too_few: int = 0
    dropped_duplicate: int = 0
    removed_resources: int = 0
    removed_declined: int = 0
    removed_group_addresses: int = 0
    group_addresses_seen: list[str] = field(default_factory=list)
    external_participants: int = 0
    hidden_attendees: int = 0
    size_histogram: dict[int, int] = field(default_factory=dict)


def normalize(
    raw_events: list[dict],
    persons: dict[str, Person],
    cfg: NormalizeConfig,
) -> tuple[list[Interaction], NormalizeReport]:
    by_email = {p.email.lower(): p for p in persons.values() if p.email}
    internal_domains = {d.lower() for d in cfg.internal_domains} or {
        p.email.split("@")[-1].lower() for p in persons.values() if "@" in p.email
    }

    from ...core.group_address import is_group_address

    extra_groups = {a.lower() for a in cfg.extra_group_addresses}
    report = NormalizeReport()
    seen_uids: set[str] = set()
    out: list[Interaction] = []

    for ev in raw_events:
        report.seen += 1

        start = ev.get("start", {})
        if cfg.exclude_all_day and "date" in start and "dateTime" not in start:
            report.dropped_all_day += 1
            continue

        uid = ev.get("iCalUID") or ev.get("id")
        occurrence_key = f"{uid}@{start.get('dateTime', start.get('date', ''))}"
        if occurrence_key in seen_uids:
            report.dropped_duplicate += 1
            continue
        seen_uids.add(occurrence_key)

        attendees_raw = ev.get("attendees") or []
        if not attendees_raw:
            report.hidden_attendees += 1
            continue

        ids: list[str] = []
        responses: dict[str, str] = {}
        ext_domains: list[str] = []

        for att in attendees_raw:
            # R1 会議室・備品リソースの除去（必須）
            if att.get("resource"):
                report.removed_resources += 1
                continue
            email = (att.get("email") or "").lower()
            if not email:
                continue
            # Google Workspace のグループは resource フラグが付かず社内ドメインで
            # 終わるため、ここで落とさないと人として数えられてしまう。
            # **社外のアドレスには適用しない。** sales@取引先.com は実在の取引関係であり、
            # どのみちドメイン単位の外部エンティティにまとめられる。
            att_domain = email.split("@")[-1] if "@" in email else ""
            att_internal = bool(att_domain) and att_domain in internal_domains
            if (
                cfg.drop_group_addresses
                and att_internal
                and (is_group_address(email) or email in extra_groups)
            ):
                report.removed_group_addresses += 1
                if email not in report.group_addresses_seen:
                    report.group_addresses_seen.append(email)
                continue
            status = att.get("responseStatus", "needsAction")
            # R3 辞退者の除去
            if cfg.drop_declined and status == RESPONSE_DECLINED:
                report.removed_declined += 1
                continue

            person = by_email.get(email)
            if person is not None:
                if person.is_bot:
                    continue
                ids.append(person.person_id)
                responses[person.person_id] = status
                continue

            # R2 / R7 名簿に無いメンバーの扱い。
            # ドメインが社内なら「名簿未登録の社員」として、メールアドレスを
            # そのまま person_id にする（名簿を用意させない運用のため）。
            # ドメインが社外なら、個人単位ではなくドメイン単位の外部エンティティにまとめる。
            domain = email.split("@")[-1] if "@" in email else ""
            is_internal = bool(domain) and domain in internal_domains
            if is_internal:
                if email not in ids:
                    ids.append(email)
                    responses[email] = status
                continue
            if cfg.external_domains_as_entity:
                node = f"ext:{domain}" if domain else f"ext:{email}"
                if node not in ids:
                    ids.append(node)
                    responses[node] = status
                if domain:
                    ext_domains.append(domain)
                report.external_participants += 1

        ids = list(dict.fromkeys(ids))
        if len(ids) < cfg.min_attendees:
            report.dropped_too_few += 1
            continue

        ts = _parse_dt(start.get("dateTime"))
        end = _parse_dt(ev.get("end", {}).get("dateTime"))
        duration = int((end - ts).total_seconds() // 60) if ts and end else None

        organizer_email = (ev.get("organizer") or {}).get("email", "").lower()
        # Google は通常、主催者も参加者に含める。含まれていない場合でも
        # 主催者は自分の会議に出ているとみなす（❷影響力の有向グラフで主催が効くため）。
        if organizer_email:
            org_person = by_email.get(organizer_email)
            org_id = org_person.person_id if org_person else organizer_email
            org_domain = organizer_email.split("@")[-1] if "@" in organizer_email else ""
            if org_id not in ids and (org_person or org_domain in internal_domains):
                ids.insert(0, org_id)
                responses.setdefault(org_id, "accepted")
        organizer = _resolve_organizer(organizer_email, by_email, ids)

        interaction = Interaction(
            event_id=str(ev.get("id")),
            ts=ts,
            source="calendar",
            channel_type="meeting",
            actor_id=organizer,
            target_ids=[i for i in ids if i != organizer],
            group_id=uid,
            duration_min=duration,
            is_recurring=bool(ev.get("recurringEventId")),
            responses=responses,
            external_domains=sorted(set(ext_domains)),
        )
        interaction.meeting_type = infer_meeting_type(interaction)
        # タイトルは「定期グループ会議」に限って保持する。
        # 1on1・単発会議のタイトルには個人的な内容が入りやすいため取得しない。
        if (
            cfg.keep_group_titles
            and interaction.is_recurring
            and len(ids) >= cfg.group_title_min_attendees
        ):
            title = (ev.get("summary") or "").strip()
            interaction.group_title = title or None
        out.append(interaction)
        report.kept += 1
        n = interaction.participant_count
        report.size_histogram[n] = report.size_histogram.get(n, 0) + 1

    return out, report


def infer_meeting_type(ev: Interaction) -> str:
    """参加人数・所要時間・定期性から会議の種類を推定する（設計 §7.2）。

    会議タイトルは取得しないため、この4要素から文脈を得る。
    """
    n = ev.participant_count
    d = ev.duration_min or 0
    has_external = any(i.startswith("ext:") for i in ev.attendees)

    if has_external:
        return "external_meeting"
    if n == 2:
        if ev.is_recurring and 25 <= d <= 60:
            return "one_on_one_recurring"
        return "one_on_one_adhoc"
    if n > 12:
        return "broadcast"
    if 3 <= n <= 6 and d >= 60:
        return "small_group_work"
    if 3 <= n <= 10 and ev.is_recurring:
        return "team_standing"
    if 4 <= n <= 10:
        return "project_meeting"
    return "other"


def _resolve_organizer(email: str, by_email: dict, ids: list[str]) -> str:
    person = by_email.get(email)
    if person is not None and person.person_id in ids:
        return person.person_id
    if email in ids:
        return email
    return ids[0]


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
