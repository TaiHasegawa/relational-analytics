"""データ品質の診断（FR-2.2）。

validate がスキーマの正しさを見るのに対し、doctor は
「このまま分析して意味のある結果が出るか」を見る。
各警告には必ず推奨アクションを添える。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from ..models import Interaction, Person

NOMINAL_MAX_PERSONS = 100
MIN_MEANINGFUL_PERSONS = 30
SMALL_MEETING_MAX = 8  # 共有アカウント判定で数える会議の上限人数


@dataclass
class Check:
    code: str
    severity: str  # ok | info | warning | critical
    title: str
    detail: str
    action: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "action": self.action,
            "data": self.data,
        }


def diagnose(
    interactions: list[Interaction],
    persons: list[Person],
    normalize_report: Any | None = None,
    headcount: int | None = None,
    roster_provided: bool = False,
) -> list[Check]:
    """headcount は実際の従業員数。名簿を用意しない運用では分母が分からないため、
    これが無いと被覆率は「見つけた人のうち何%」という循環した値になる。"""
    checks: list[Check] = []
    active = [p for p in persons if not p.is_bot and not p.is_external]
    n = len(active)
    observed = {pid for ev in interactions for pid in ev.attendees if not pid.startswith("ext:")}

    checks.append(_scale(headcount or n))
    checks.append(_discovery(len(observed), headcount))
    checks.append(_coverage(active, observed))
    checks += _grouping(active)
    checks.append(_meeting_sizes(interactions))
    checks += _resources(interactions)
    checks.append(_period_gaps(interactions))
    checks += _bots(interactions, persons)
    checks += _group_addresses(interactions)
    checks += _roster_gap(interactions, persons, roster_provided)
    checks.append(_external_ratio(interactions))
    checks.append(_one_on_one(interactions))
    return [c for c in checks if c is not None]


def _scale(n: int) -> Check:
    if n > 1000:
        return Check(
            "W_SCALE_LARGE", "warning", f"対象 {n} 名",
            "公称の対応範囲（100名程度）を大きく超えています。収集・分析ともに時間がかかり、"
            "全社一括の個人ランキングは解釈も難しくなります。",
            "事業部・拠点ごとにスナップショットを分けることを検討してください。",
            {"persons": n},
        )
    if n > NOMINAL_MAX_PERSONS:
        return Check(
            "W_SCALE_OVER", "warning", f"対象 {n} 名",
            f"公称の対応範囲（{NOMINAL_MAX_PERSONS}名程度）を超えています。"
            "動作しますが、データ収集と分析に時間がかかります。",
            "まずはこのまま実行して所要時間を確認してください。",
            {"persons": n},
        )
    if n < MIN_MEANINGFUL_PERSONS:
        return Check(
            "W_SCALE_SMALL", "warning", f"対象 {n} 名",
            f"{MIN_MEANINGFUL_PERSONS}名未満ではネットワークの構造が単純すぎて、"
            "構造的特徴が分散しません（全員が全員を知っている状態に近づきます）。",
            "個人スコアの順位は使わず、部門単位の傾向だけを見てください。",
            {"persons": n},
        )
    return Check("OK_SCALE", "ok", f"対象 {n} 名", "対応範囲内です。", data={"persons": n})


def _discovery(observed: int, headcount: int | None) -> Check:
    """名簿なしで集めた場合、何名を見つけられたか。

    カレンダーの参加者から人を芋づる式に見つけるため、全従業員数は
    データからは分からない。利用者に人数だけ聞くことで初めて判定できる。
    """
    if headcount is None:
        return Check(
            "W_NO_HEADCOUNT", "warning", f"{observed} 名を発見しました",
            "実際の従業員数が分からないため、これで足りているか判定できません。"
            "見つけた人の中での割合は、見つけた範囲に左右される循環した値になります。",
            "従業員数を --headcount で指定してください（名簿は不要、人数だけで十分です）。",
            {"observed": observed},
        )
    rate = observed / headcount if headcount else 0.0
    if rate >= 0.9:
        sev, action = "ok", ""
    elif rate >= 0.7:
        sev = "warning"
        action = "`relana next-calendars` の提案に従って、あと数名分のカレンダーを読んでください。"
    else:
        sev = "critical"
        action = (
            "読んだカレンダーが特定の集団に偏っています。"
            "まだ現れていない部門の人を起点に加えてください。"
        )
    return Check(
        "DISCOVERY", sev, f"{observed}/{headcount} 名を発見（{rate:.0%}）",
        f"従業員{headcount}名のうち{observed}名がカレンダー上に現れています。"
        + ("" if sev == "ok" else "残りはまだ見つかっていません。"),
        action,
        {"observed": observed, "headcount": headcount, "rate": round(rate, 3)},
    )


def _coverage(active: list[Person], observed: set[str]) -> Check:
    if not active:
        return Check("E_NO_PERSONS", "critical", "名簿が空です", "分析できません。", "persons を用意してください。")
    rate = len(observed) / len(active)
    missing = [p.person_id for p in active if p.person_id not in observed]
    if rate < 0.5:
        sev, detail = "critical", (
            f"名簿 {len(active)} 名のうち、会議に一度も現れないのが {len(missing)} 名います。"
            "カレンダーの社内共有設定が『予定の有無のみ』になっていると、こうなります。"
        )
        action = "サービスアカウント＋ドメイン全体の委任での収集に切り替えてください（設計 §3.3 方式2）。"
    elif rate < 0.85:
        sev, detail = "warning", (
            f"会議に現れないのが {len(missing)} 名います（集計できた人 {rate:.0%}）。"
            "カレンダーを使わない働き方の人や、共有設定を個別に絞っている人が含まれます。"
        )
        action = "欠けている人の所属に偏りがないか確認してください。偏っていると部門比較が歪みます。"
    else:
        sev, detail, action = "ok", f"集計できた人 {rate:.0%}", ""
    return Check(
        "COVERAGE", sev, f"集計できた人 {rate:.0%}", detail, action,
        {"rate": round(rate, 3), "missing_count": len(missing), "missing_sample": missing[:10]},
    )


def _grouping(active: list[Person]) -> list[Check]:
    out = []
    for attr, label, feature in (("dept", "部門", "サイロ診断"), ("team", "チーム", "チーム分析")):
        blank = [p.person_id for p in active if not getattr(p, attr)]
        if blank:
            out.append(
                Check(
                    f"W_MISSING_{attr.upper()}", "warning" if len(blank) < len(active) else "critical",
                    f"{label}が未設定の人が {len(blank)} 名",
                    f"{label}が空だと『(未設定)』という一つの塊として集計され、{feature}が歪みます。",
                    f"persons の {attr} 列を埋めてください。",
                    {"count": len(blank), "sample": blank[:10]},
                )
            )
    if not out:
        out.append(Check("OK_GROUPING", "ok", "部門・チームの設定", "すべて設定されています。"))
    return out


def _meeting_sizes(interactions: list[Interaction]) -> Check:
    if not interactions:
        return Check("E_NO_EVENTS", "critical", "イベントが0件", "分析できません。", "収集結果を確認してください。")
    sizes = Counter(ev.participant_count for ev in interactions)
    big = sum(c for n, c in sizes.items() if n > 20)
    two = sizes.get(2, 0)
    total = len(interactions)
    if two / total < 0.05:
        return Check(
            "W_FEW_DYADS", "warning", "1on1 がほとんどありません",
            f"2名の会議が全体の {two / total:.0%} しかありません。"
            "1on1 は最も強い関係のシグナルなので、これが無いと関係の濃淡が出にくくなります。",
            "カレンダーに1on1 を登録しない組織では、会議データから関係の濃淡が出ません。",
            {"two_person_ratio": round(two / total, 3)},
        )
    return Check(
        "OK_SIZES", "ok", "会議サイズの分布",
        f"1on1 {two}件 / 20名超 {big}件。大人数会議は重み関数により自動的にほぼゼロになります。",
        data={"histogram": dict(sorted(sizes.items()))},
    )


def _resources(interactions: list[Interaction]) -> list[Check]:
    """会議室が参加者として残っていると、会議室が最強のハブノードになる。"""
    suspects = Counter()
    for ev in interactions:
        for pid in ev.attendees:
            low = pid.lower()
            if "resource.calendar" in low or low.startswith("ext:resource"):
                suspects[pid] += 1
    if suspects:
        return [
            Check(
                "C_RESOURCE_CONTAMINATION", "critical", "会議室リソースが混入しています",
                f"{len(suspects)} 件のリソースが参加者として残っています（例: {list(suspects)[:3]}）。"
                "このままだと会議室が全員とつながったハブとして扱われ、結果が壊れます。",
                "normalize.drop_resources を true にして取り込み直してください。",
                {"resources": dict(suspects.most_common(5))},
            )
        ]
    return []


def _period_gaps(interactions: list[Interaction]) -> Check:
    days = sorted({ev.ts.date() for ev in interactions})
    if len(days) < 2:
        return Check("W_SHORT_PERIOD", "warning", "期間が短すぎます", "1日分しかデータがありません。",
                     "窓を広げて収集し直してください。")
    gaps = [
        (a, b) for a, b in zip(days, days[1:]) if (b - a) > timedelta(days=10)
    ]
    if gaps:
        return Check(
            "W_PERIOD_GAP", "warning", "期間に欠落があります",
            f"{len(gaps)} 箇所で10日以上データがありません（例: {gaps[0][0]} 〜 {gaps[0][1]}）。"
            "収集が途中で止まるとこうなります。",
            "収集をやり直すか、窓をデータのある期間に合わせてください。",
            {"gaps": [[str(a), str(b)] for a, b in gaps[:5]]},
        )
    return Check("OK_PERIOD", "ok", f"期間 {days[0]} 〜 {days[-1]}", f"{len(days)} 日分のデータがあります。")


def _bots(interactions: list[Interaction], persons: list[Person]) -> list[Check]:
    """共有アカウント・ボットの疑い: 極端に多くの相手と接触している人物。"""
    contacts: dict[str, set[str]] = {}
    for ev in interactions:
        att = ev.attendees
        # 全社会議では全員が全員と「接触」してしまうため、
        # 実質的な関係が現れる小規模会議だけを数える
        if len(att) > SMALL_MEETING_MAX:
            continue
        for pid in att:
            contacts.setdefault(pid, set()).update(a for a in att if a != pid)
    internal = {p.person_id for p in persons if not p.is_bot and not p.is_external}
    if len(internal) < 10:
        return []
    counts = {k: len(v) for k, v in contacts.items() if k in internal}
    if not counts:
        return []
    threshold = max(len(internal) * 0.9, 10)
    suspects = {k: v for k, v in counts.items() if v >= threshold}
    if suspects:
        return [
            Check(
                "W_SHARED_ACCOUNT", "warning", "共有アカウントの疑い",
                f"{len(suspects)} 名が社内のほぼ全員と接触しています（例: {list(suspects)[:3]}）。"
                "受付や総務の共有カレンダー、またはボットがこれに該当します。",
                "該当する場合は persons の is_bot を true にして除外してください。",
                {"suspects": dict(sorted(suspects.items(), key=lambda kv: -kv[1])[:5])},
            )
        ]
    return []


def _group_addresses(interactions: list[Interaction]) -> list[Check]:
    """人として数えてはいけないアドレスが残っていないか。

    `sales@` `info@` のように名前で確実に分かるものは正規化で既に落ちている
    （core/group_address.py）。ここで見るのは**振る舞いでしか分からないもの**。

    メーリングリストは1on1 を持たない。名前だけで疑うと `pr.tanaka@` のような
    実在の人を誤判定するため、振る舞いを主判定にする。
    """
    from .group_address import is_suspected_group

    appear: Counter = Counter()
    dyads: Counter = Counter()
    for ev in interactions:
        att = [a for a in ev.attendees if not a.startswith("ext:")]
        for pid in att:
            appear[pid] += 1
            if len(att) == 2:
                dyads[pid] += 1

    suspects = [
        {
            "address": pid,
            "meetings": n,
            "one_on_ones": 0,
            "name_looks_like_group": is_suspected_group(pid),
        }
        for pid, n in appear.items()
        if n >= 5 and dyads[pid] == 0
    ]
    if not suspects:
        return []
    suspects.sort(key=lambda r: (-int(r["name_looks_like_group"]), -r["meetings"]))
    return [
        Check(
            "W_GROUP_ADDRESS", "warning",
            f"グループアドレスの疑いが {len(suspects)} 件",
            "多くの会議に出ているのに1on1 が一度もありません。"
            "メーリングリストは人として残ると人数を水増しし、常に多数の会議に現れるため"
            "中心性も歪めます。ただし、本当に1on1 を持たない人である可能性もあります。",
            "グループであれば normalize.extra_group_addresses に追加して取り込み直してください。"
            "人であればそのままで構いません。",
            {"suspects": suspects[:10]},
        )
    ]


def _roster_gap(
    interactions: list[Interaction], persons: list[Person], roster_provided: bool
) -> list[Check]:
    """収集データに現れたのに名簿に無い人。名簿の取りこぼしを自己検出する。

    実測では、単一の「全体MTG」から作った名簿が全社の約55%しか無く、
    収集データとの突き合わせで92名の漏れが判明した。
    """
    if not roster_provided:
        return []
    known = {p.person_id for p in persons}
    observed = {
        pid for ev in interactions for pid in ev.attendees if not pid.startswith("ext:")
    }
    missing = sorted(observed - known)
    if not missing:
        return [Check("OK_ROSTER", "ok", "名簿の網羅性", "収集データに現れた人は全員名簿にあります。")]
    sev = "critical" if len(missing) > len(known) * 0.2 else "warning"
    return [
        Check(
            "W_ROSTER_GAP", sev,
            f"名簿に無い人が {len(missing)} 名",
            f"収集した会議に現れているのに名簿に載っていない人が {len(missing)} 名います。"
            "名簿の作り方が偏っているとこうなります"
            "（例: 単一の『全体MTG』から名簿を作ると、その会議に招待されていない人が丸ごと漏れます）。"
            "メーリングリストが混ざっている場合も、ここに現れます。",
            "この一覧を名簿に追加し、その人たちのカレンダーも収集してください。"
            "追加しないと、その人たちが所属する部門が過小評価されます。",
            {"missing_count": len(missing), "missing": missing[:50]},
        )
    ]


def _external_ratio(interactions: list[Interaction]) -> Check:
    ext = sum(1 for ev in interactions if any(a.startswith("ext:") for a in ev.attendees))
    rate = ext / len(interactions) if interactions else 0
    if rate > 0.5:
        return Check(
            "W_EXTERNAL_HEAVY", "warning", f"外部との会議が {rate:.0%}",
            "社外ミーティングが半数を超えています。社内の関係を測るには情報が足りません。",
            "社内の関係に絞るなら、外部ドメインを除外した設定でも分析して比較してください。",
            {"rate": round(rate, 3)},
        )
    return Check("OK_EXTERNAL", "ok", f"外部との会議 {rate:.0%}", "", data={"rate": round(rate, 3)})


def _one_on_one(interactions: list[Interaction]) -> Check:
    recurring = sum(1 for ev in interactions if ev.meeting_type == "one_on_one_recurring")
    return Check(
        "OK_ONE_ON_ONE", "ok", f"定期1on1 {recurring} 件",
        "1on1 は最も強い関係のシグナルとして別グラフでも分析されます。",
        data={"recurring_one_on_one": recurring},
    )
