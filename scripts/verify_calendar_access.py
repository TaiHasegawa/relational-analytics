#!/usr/bin/env python3
"""Google カレンダーから必要なデータが取れるかを確認する。

設計書 docs/design-google-calendar.md §3.4 の検証 V1〜V4 を実行する。
**本番の収集は行わない。** 数名分を読んで、取れるかどうかだけを確かめる。

使い方:
    .venv/bin/python scripts/verify_calendar_access.py \
        --client-secrets ~/Downloads/client_secret_xxx.json \
        --colleagues 同僚1@example.co.jp,同僚2@example.co.jp,同僚3@example.co.jp

何が分かるか:
    V1  他のメンバーのカレンダーを読めるか
    V2  読めた予定に「参加者」が含まれるか  ★これが最重要
    V3  アプリ審査なしで接続できるか
    V4  100名分だとどれくらい時間がかかるか
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from relana.sources.gcal.auth import (  # noqa: E402
    SCOPES_READONLY,
    SETUP_GUIDE,
    AuthError,
    calendar_service,
    user_credentials,
)
from relana.sources.gcal.collect import FIELDS_BASE, estimate  # noqa: E402

C = {"b": "\033[1m", "g": "\033[32m", "y": "\033[33m", "r": "\033[31m", "x": "\033[0m"}
if not sys.stdout.isatty():
    C = dict.fromkeys(C, "")


def head(msg: str) -> None:
    print(f"\n{C['b']}{msg}{C['x']}")


def ok(msg: str) -> None:
    print(f"{C['g']}✓{C['x']} {msg}")


def warn(msg: str) -> None:
    print(f"{C['y']}!{C['x']} {msg}")


def bad(msg: str) -> None:
    print(f"{C['r']}✗{C['x']} {msg}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Google カレンダーの取得可否を確認する")
    ap.add_argument("--client-secrets", type=Path, help="ダウンロードした OAuth クライアントの JSON")
    ap.add_argument("--colleagues", default="", help="同僚のメールアドレス（カンマ区切り、3名程度）")
    ap.add_argument("--window-days", type=int, default=30)
    ap.add_argument("--out", type=Path, default=ROOT / "verify-report.json")
    args = ap.parse_args()

    print(
        "\n  Google カレンダーの取得可否を確認します\n"
        "  ────────────────────────────────────────\n"
        "  数名分の予定を読むだけで、本番の収集は行いません。\n"
    )

    report: dict = {"checked_at": datetime.now(timezone.utc).isoformat()}

    if not args.client_secrets:
        print(SETUP_GUIDE)
        bad("--client-secrets にダウンロードした JSON のパスを指定して、もう一度実行してください。")
        return 2

    # ── V3: 認証（内部クライアントなら審査なしで通るはず）
    head("V3  接続できるか")
    try:
        creds = user_credentials(args.client_secrets, scopes=SCOPES_READONLY)
    except AuthError as e:
        bad(str(e))
        return 2
    except Exception as e:  # noqa: BLE001
        bad(f"接続に失敗しました: {type(e).__name__}: {e}")
        print(
            "\n  「このアプリは確認されていません」と表示された場合、\n"
            "  OAuth同意画面の User Type が【内部】になっていない可能性があります。\n"
            "  手順4 を確認してください。\n"
        )
        return 2
    ok("接続できました（アプリ審査なし）")
    report["v3_auth"] = "ok"

    service = calendar_service(creds)
    time_min = (datetime.now(timezone.utc) - timedelta(days=args.window_days)).isoformat()
    time_max = datetime.now(timezone.utc).isoformat()

    def read(cal: str) -> tuple[list[dict] | None, str]:
        try:
            resp = (
                service.events()
                .list(
                    calendarId=cal,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    maxResults=250,
                    fields=FIELDS_BASE,
                )
                .execute()
            )
            return resp.get("items", []), ""
        except Exception as e:  # noqa: BLE001
            status = getattr(getattr(e, "resp", None), "status", None)
            return None, f"HTTP {status}" if status else f"{type(e).__name__}"

    # ── 自分のカレンダー（前提確認）
    head("前提  自分のカレンダーを読めるか")
    mine, err = read("primary")
    if mine is None:
        bad(f"自分のカレンダーすら読めません（{err}）。スコープ設定を確認してください。")
        return 2
    ok(f"{len(mine)} 件の予定を取得しました（直近{args.window_days}日）")
    report["own_events"] = len(mine)

    colleagues = [c.strip() for c in args.colleagues.split(",") if c.strip()]
    if not colleagues:
        warn("--colleagues が指定されていないため、V1・V2 を確認できません。")
        print(
            "\n  同僚のメールアドレスを3名ほど指定して、もう一度実行してください:\n"
            "    --colleagues a@example.co.jp,b@example.co.jp,c@example.co.jp\n"
        )
        return 2

    # ── V1: 他メンバーのカレンダーを読めるか
    head("V1  他のメンバーのカレンダーを読めるか")
    results: dict[str, dict] = {}
    t0 = time.time()
    for cal in colleagues:
        items, err = read(cal)
        if items is None:
            bad(f"{cal}  読めません（{err}）")
            results[cal] = {"readable": False, "error": err}
            continue
        ok(f"{cal}  {len(items)} 件")
        results[cal] = {"readable": True, "events": len(items), "items": items}
    elapsed = time.time() - t0
    report["v1_readable"] = {k: v.get("readable", False) for k, v in results.items()}

    readable = [c for c, r in results.items() if r.get("readable")]
    if not readable:
        bad("他のメンバーのカレンダーを1件も読めませんでした。")
        print_verdict("service_account", report, args.out)
        return 1

    # ── V2: 参加者が含まれるか ★最重要
    head("V2  予定に「参加者」が含まれるか  ★これが最重要")
    with_attendees = 0
    total = 0
    for cal in readable:
        items = results[cal]["items"]
        total += len(items)
        with_attendees += sum(1 for e in items if e.get("attendees"))
    rate = with_attendees / total if total else 0.0
    report["v2_attendee_rate"] = round(rate, 3)
    report["v2_events_checked"] = total

    if total == 0:
        warn("予定が0件のため判定できません。期間を延ばすか、別のメンバーで試してください。")
        print_verdict("inconclusive", report, args.out)
        return 1
    if rate >= 0.3:
        ok(f"{with_attendees}/{total} 件に参加者が含まれていました（{rate:.0%}）")
        verdict = "personal_oauth"
    elif rate > 0:
        warn(f"参加者が含まれるのは {with_attendees}/{total} 件（{rate:.0%}）しかありません。")
        verdict = "partial"
    else:
        bad("参加者が1件も取得できませんでした。")
        print(
            "\n  カレンダーの社内共有設定が「予定の有無のみ（free/busy）」になっている可能性が高いです。\n"
            "  この設定では誰と誰が同席したかが分からないため、分析できません。\n"
        )
        verdict = "service_account"

    # ── V4: 100名分の所要時間
    head("V4  100名分だとどれくらいかかるか")
    per_cal = elapsed / max(len(colleagues), 1)
    est = estimate(["x"] * 100, 90)
    measured = per_cal * 100 * (90 / args.window_days)
    print(f"  実測   1カレンダーあたり {per_cal:.2f} 秒")
    print(f"  概算   100名・90日で約 {int(measured / 60)} 分（API呼び出し {est['estimated_api_calls']} 回程度）")
    report["v4_seconds_per_calendar"] = round(per_cal, 3)
    report["v4_estimated_minutes_for_100"] = round(measured / 60, 1)

    print_verdict(verdict, report, args.out)
    return 0 if verdict == "personal_oauth" else 1


def print_verdict(verdict: str, report: dict, out: Path) -> None:
    report["verdict"] = verdict
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    head("結論")
    if verdict == "personal_oauth":
        ok("方式1（内部用OAuthクライアント）で分析できます。")
        print(
            "\n  このまま本番の収集に進めます。\n"
            "  設計書の方式1が成立したので、利用者は「許可」を1回押すだけで済みます。\n"
        )
    elif verdict == "partial":
        warn("一部の予定でしか参加者が取れません。")
        print(
            "\n  主催者が「ゲストは他のゲストを表示できない」を設定している予定が多いか、\n"
            "  一部のメンバーだけ共有設定が絞られている可能性があります。\n"
            "  被覆率が足りるかは relana doctor で確認できます。\n"
            "  不足するようなら、サービスアカウント方式（設計 §3.3 方式2）に切り替えてください。\n"
        )
    elif verdict == "service_account":
        bad("方式1では必要なデータが取れません。")
        print(
            "\n  サービスアカウント＋ドメイン全体の委任（設計 §3.3 方式2）に切り替えてください。\n"
            "  この方式は社内のカレンダー共有設定に依存せず、確実に全員分を取得できます。\n"
            "  管理者の設定が10分ほど必要です。\n"
        )
    else:
        warn("判定できませんでした。期間やメンバーを変えて再実行してください。")

    print(f"  結果を書き出しました: {out}\n")


if __name__ == "__main__":
    sys.exit(main())
