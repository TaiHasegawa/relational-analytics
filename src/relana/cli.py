"""CLI。すべてのコマンドが --json を持ち、安定した終了コードを返す（FR-11.4）。"""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import typer

from .config import Config
from .core.analyze import analyze
from .models import Person

app = typer.Typer(
    add_completion=False,
    help="relana — 会議の同席関係から組織の構造的特徴を測る（対応規模: 従業員100名程度まで）",
)
snapshot_app = typer.Typer(help="スナップショットの操作")
app.add_typer(snapshot_app, name="snapshot")

DEFAULT_OUT = Path("snapshots")


@app.command(help="合成データで全機能を試す。自社データは不要。")
def demo(
    out: Path = typer.Option(DEFAULT_OUT, help="出力先ディレクトリ"),
    window_days: int = typer.Option(90, help="分析する期間（日）"),
    json_out: bool = typer.Option(False, "--json", help="機械可読出力"),
    open_report: bool = typer.Option(True, "--open/--no-open", help="終わったらブラウザで開く"),
    headcount: int | None = typer.Option(None, "--headcount"),
) -> None:
    """合成データで全機能を試す。自社データは不要。"""
    from .demo import generate
    from .report.pages import write as write_report
    from .sources.gcal.normalize import normalize

    cfg = Config()
    cfg.window_days = window_days
    raw, persons, _ = generate(window_days=window_days)
    pmap = {p.person_id: p for p in persons}
    interactions, nrep = normalize(raw, pmap, cfg.normalize)
    window_end = datetime(2026, 3, 31, tzinfo=timezone.utc)
    snap, bundle = analyze(
        interactions, persons, cfg, window_end, "demo",
        normalize_report=nrep, headcount=headcount or len(persons),
    )

    d = out / snap.snapshot_id
    d.mkdir(parents=True, exist_ok=True)
    entry = write_report(snap, bundle, d / "report")
    # findings.json は利用者向けの成果物ではなく、エージェントが結果を読んで
    # 説明するための機械可読インターフェース（原則4）
    (d / "findings.json").write_text(
        json.dumps(snap.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if json_out:
        typer.echo(json.dumps(snap.to_dict(), ensure_ascii=False))
        return
    _print_summary(snap)
    typer.echo(f"\nレポート: {entry}")
    if open_report:
        _open(entry)


@snapshot_app.command("create")
def snapshot_create(
    snapshot_id: str = typer.Argument(..., help="例: 2026Q1"),
    interactions_path: Path = typer.Option(..., "--interactions", help="interactions の CSV/JSONL"),
    persons_path: Path | None = typer.Option(
        None, "--persons", help="persons.csv。省略するとカレンダーから推定する"
    ),
    config_path: Path | None = typer.Option(None, "--config", help="設定YAML"),
    headcount: int | None = typer.Option(None, "--headcount", help="実際の従業員数。信頼度の判定に使う"),
    out: Path = typer.Option(DEFAULT_OUT),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """スナップショットを作る。不変であり、作成後は変更しない。"""
    from .report.pages import write as write_report

    cfg = Config.from_yaml(str(config_path)) if config_path else Config()
    interactions = _load_interactions(interactions_path)
    if not interactions:
        typer.secho("E_NO_INTERACTIONS: 相互作用イベントが0件です。入力を確認してください。", fg="red")
        raise typer.Exit(code=2)

    window_end = max(ev.ts for ev in interactions)
    if persons_path is not None:
        persons = _load_persons(persons_path)
    else:
        persons = _infer_persons(interactions, cfg, window_end)
        cfg.analysis.groups_source = "inferred"
        typer.secho(
            "名簿が指定されていないため、カレンダーから組織構造を推定しました。\n"
            "  部門の推定は外れやすいため、サイロ診断の結果には注記が付きます。\n"
            "  `relana infer-org` で下書きを書き出し、部門を修正することをおすすめします。",
            fg="yellow",
        )
    snap, bundle = analyze(
        interactions, persons, cfg, window_end, snapshot_id, headcount=headcount
    )
    d = out / snapshot_id
    d.mkdir(parents=True, exist_ok=True)
    entry = write_report(snap, bundle, d / "report")
    (d / "findings.json").write_text(
        json.dumps(snap.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if json_out:
        typer.echo(json.dumps(snap.to_dict(), ensure_ascii=False))
        return
    _print_summary(snap)
    typer.echo(f"\nレポート: {entry}")
    _open(entry)


@snapshot_app.command("list")
def snapshot_list(out: Path = typer.Option(DEFAULT_OUT)) -> None:
    """保存済みスナップショットの一覧。"""
    if not out.exists():
        typer.echo("スナップショットはまだありません。")
        return
    for p in sorted(out.iterdir()):
        f = p / "findings.json"
        if not f.exists():
            continue
        data = json.loads(f.read_text(encoding="utf-8"))
        typer.echo(
            f"{data['snapshot_id']:16s} {data['window_start']}〜{data['window_end']} "
            f"設定={data['config_hash']} 被覆={data['quality']['edge_coverage_rate']:.0%}"
        )


@app.command("infer-org", help="カレンダーだけから組織構造を推定し、名簿の下書きを作る。")
def infer_org_cmd(
    interactions_path: Path = typer.Option(..., "--interactions"),
    out: Path = typer.Option(Path("persons.csv"), "-o", "--out", help="書き出す名簿の下書き"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """カレンダーだけから組織構造（チーム・上司・部門）を推定し、名簿の下書きを作る。

    結果は**下書き**です。とくに部門は精度が落ちるため、
    書き出された CSV の dept 列を確認・修正してから分析してください。
    """
    from .core.graph import build_graphs
    from .core.org_inference import infer_org, infer_people

    interactions = _load_interactions(interactions_path)
    if not interactions:
        typer.secho("E_NO_INTERACTIONS: 相互作用イベントが0件です。", fg="red")
        raise typer.Exit(code=2)

    people = {p.person_id: p for p in infer_people(interactions)}
    cfg = Config()
    window_end = max(ev.ts for ev in interactions)
    bundle = build_graphs(interactions, people, cfg, window_end)
    org = infer_org(interactions, bundle.undirected)
    rows = org.as_person_rows()

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    if json_out:
        typer.echo(json.dumps({"evidence": org.evidence, "output": str(out)}, ensure_ascii=False, indent=2))
        return

    e = org.evidence
    typer.echo(f"\nカレンダーから組織構造を推定しました")
    typer.echo(f"  人数      {e['people_found']} 名")
    typer.echo(f"  チーム    {e['teams_found']} 個（定期グループ会議の固定メンバーから）")
    typer.echo(f"  上司      {e['managers_found']} 名（定期1on1 の非対称な星形から）")
    typer.echo(f"  部門      {e['departments_found']} 個（マネジャーが集まる定例から）")
    if e["unassigned_count"]:
        typer.secho(f"  未割当    {e['unassigned_count']} 名（定期会議に出ていない人）", fg="yellow")

    typer.echo("\n推定したチーム:")
    for t in sorted(org.teams, key=lambda x: -len(x.members)):
        mgr = f" 上司={_short(t.manager)}" if t.manager else ""
        typer.echo(f"  {t.team_id:20s} {len(t.members):2d}名 確信度={t.confidence:.2f}{mgr}")

    typer.secho(f"\n下書きを書き出しました: {out}", fg="green")
    typer.echo("")
    typer.secho("  ■ 次にやってください", bold=True)
    typer.echo("    この CSV の dept 列（部門）を確認してください。")
    typer.echo("    チームと上司の推定は精度が高いですが、部門は外れやすいためです。")
    typer.echo("    修正せずに分析すると、サイロ診断の結果が信用できません。")


def _short(pid: str | None) -> str:
    if not pid:
        return ""
    return pid.split("@")[0] if "@" in pid else pid


@app.command(help="Google カレンダーに接続する。ブラウザが開くので「許可」を押すだけ。")
def connect(
    source: str = typer.Argument("google", help="いまは google のみ"),
    client_secrets: Path = typer.Option(..., "--client-secrets", help="ダウンロードしたOAuthクライアントのJSON"),
) -> None:
    """Google カレンダーに接続する。ブラウザが開くので「許可」を押すだけ。"""
    from .sources.gcal.auth import SCOPES_READONLY, AuthError, describe_token, user_credentials

    if source != "google":
        typer.secho(f"E_UNKNOWN_SOURCE: '{source}' は未対応です。いまは google のみ。", fg="red")
        raise typer.Exit(code=2)
    try:
        user_credentials(client_secrets, scopes=SCOPES_READONLY)
    except AuthError as e:
        typer.secho(str(e), fg="red")
        raise typer.Exit(code=2) from None
    info = describe_token()
    typer.secho("✓ 接続しました", fg="green")
    typer.echo(f"  認証情報の保存先: {info['path']}（このマシンの中だけです）")


@app.command(help="Google カレンダーから会議データを収集する。本文・場所は取得しない。")
def collect(
    out: Path = typer.Option(Path("interactions.csv"), "-o", "--out"),
    persons_path: Path | None = typer.Option(None, "--persons", help="対象者。省略すると組織全体を取得"),
    calendars_file: Path | None = typer.Option(None, "--calendars", help="メールアドレスを1行ずつ書いたファイル"),
    window_days: int = typer.Option(90, "--window-days"),
    keep_titles: bool = typer.Option(
        False, "--keep-titles/--no-titles",
        help="定期グループ会議のタイトルを保持する（組織構造の判断に使う。1on1 のタイトルは取得しない）",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="実行せず所要時間の見込みだけ出す"),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="中断した続きから再開する"),
) -> None:
    """Google カレンダーから会議データを収集する。本文・場所は取得しない。"""
    from .config import NormalizeConfig
    from .sources.gcal.auth import AuthError, calendar_service, directory_service, user_credentials
    from .sources.gcal.collect import estimate, fetch_events, list_domain_users
    from .sources.gcal.normalize import normalize

    try:
        creds = user_credentials(Path.home() / ".relana" / "client_secrets.json")
    except AuthError:
        typer.secho(
            "まだ接続されていません。先に次を実行してください:\n"
            "    relana connect google --client-secrets <ダウンロードしたJSON>",
            fg="red",
        )
        raise typer.Exit(code=2) from None

    if calendars_file:
        calendars = [l.strip() for l in calendars_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    elif persons_path:
        calendars = [r["email"] for r in _read_rows(persons_path) if r.get("email")]
    else:
        try:
            calendars = list_domain_users(directory_service(creds))
            typer.echo(f"組織のメンバー {len(calendars)} 名を取得しました")
        except Exception:  # noqa: BLE001
            typer.secho(
                "E_NO_TARGETS: 対象者を決められませんでした。\n"
                "  管理者権限がない場合は --calendars でメールアドレスの一覧を渡してください。",
                fg="red",
            )
            raise typer.Exit(code=2) from None

    if dry_run:
        typer.echo(json.dumps(estimate(calendars, window_days), ensure_ascii=False, indent=2))
        return

    typer.echo(f"対象 {len(calendars)} 名 / 直近 {window_days} 日")
    if keep_titles:
        typer.secho(
            "  定期グループ会議のタイトルも取得します（組織構造の判断に使います）。\n"
            "  1on1 と単発会議のタイトル、本文・場所・添付は取得しません。",
            fg="yellow",
        )

    cp = (out.parent / ".relana-collect-checkpoint.json") if resume else None
    with typer.progressbar(length=len(calendars), label="収集中") as bar:
        seen = {"n": 0}

        def tick(p):
            bar.update(p.done - seen["n"])
            seen["n"] = p.done

        raw, report = fetch_events(
            calendar_service(creds), calendars, window_days,
            keep_titles=keep_titles, checkpoint_path=cp, on_progress=tick,
        )

    ncfg = NormalizeConfig(keep_group_titles=keep_titles)
    persons = {p.person_id: p for p in _load_persons(persons_path)} if persons_path else {}
    interactions, nrep = normalize(raw, persons, ncfg)
    _write_interactions(out, interactions)

    typer.secho(f"\n✓ {out} に {len(interactions)} 件を書き出しました", fg="green")
    typer.echo(f"  読めたカレンダー {report.calendars_read}/{report.calendars_requested}")
    if report.calendars_failed:
        typer.secho(f"  読めなかった {len(report.calendars_failed)} 件:", fg="yellow")
        for cal, why in list(report.calendars_failed.items())[:5]:
            typer.echo(f"    {cal}  {why}")
    typer.echo(f"  重複排除 {nrep.dropped_duplicate} / 会議室除去 {nrep.removed_resources} / 辞退除去 {nrep.removed_declined}")
    if report.hidden_attendee_events:
        typer.secho(f"  参加者が非表示の予定 {report.hidden_attendee_events} 件（分析に含まれません）", fg="yellow")


def _write_interactions(path: Path, interactions) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["event_id","ts","source","channel_type","actor_id","target_ids","group_id",
            "duration_min","is_recurring","meeting_type","group_title","responses"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for e in interactions:
            w.writerow([
                e.event_id, e.ts.isoformat(), e.source, e.channel_type, e.actor_id,
                "|".join(e.target_ids), e.group_id or "", e.duration_min or "",
                e.is_recurring, e.meeting_type, e.group_title or "",
                json.dumps(e.responses, ensure_ascii=False),
            ])


@app.command(help="エージェントが読み取ったカレンダーを取り込む。プロジェクト作成もOAuthも不要。")
def ingest(
    source: Path = typer.Option(..., "--from", help="エージェントが書き出した JSONL"),
    out: Path = typer.Option(Path("interactions.csv"), "-o", "--out"),
    append: bool = typer.Option(True, "--append/--replace", help="既存の出力に追記する"),
    keep_titles: bool = typer.Option(True, "--keep-titles/--no-titles"),
    internal_domain: list[str] = typer.Option(
        [], "--internal-domain", help="社内のメールドメイン。省略すると参加者から推定する"
    ),
    calendar: list[str] = typer.Option(
        [], "--calendar", help="今回読んだカレンダー（次に誰を読むべきかの判断に使う）"
    ),
    calendars_from: list[Path] = typer.Option(
        [], "--calendars-from", help="読んだカレンダーの一覧ファイル（batches の targets.txt を渡す）"
    ),
) -> None:
    """エージェントのカレンダー連携で読んだ予定を取り込む。

    エージェントは1行1件の JSONL を書くだけでよい。重複排除・会議室の除去・
    会議種別の推定は relana が行う。
    """
    from .config import NormalizeConfig
    from .sources.agent.ingest import (
        coverage_hint,
        detect_internal_domains,
        domain_breakdown,
        read_calendars,
        read_jsonl,
        record_read,
        suggest_next,
    )
    from .sources.gcal.normalize import normalize

    res = read_jsonl(source)
    if res.issues:
        for i in res.issues[:20]:
            typer.secho(f"[{i.code}] {i.line}行目: {i.message}", fg="red")
            typer.echo(f"  → {i.fix}")
        if not res.raw_events:
            raise typer.Exit(code=2)
        typer.secho(f"! {len(res.issues)}件を読み飛ばして続行します", fg="yellow")

    existing: list = []
    if append and out.exists():
        existing = _load_interactions(out)

    breakdown = domain_breakdown(res.raw_events)
    domains = list(internal_domain) or breakdown["internal"]
    if not domains:
        typer.secho(
            "E_NO_INTERNAL_DOMAIN: 社内のメールドメインを判定できませんでした。\n"
            "  --internal-domain example.co.jp のように指定してください。",
            fg="red",
        )
        raise typer.Exit(code=2)
    typer.echo(f"社内ドメイン: {', '.join(domains)}")
    if not internal_domain and breakdown["ambiguous"]:
        others = "、".join(f"{a['domain']}（{a['share']:.0%}）" for a in breakdown["ambiguous"])
        typer.secho(
            f"  ! {others} も多く出現しています。これも社内なら次のように指定してください:\n"
            f"      --internal-domain {domains[0]} --internal-domain {breakdown['ambiguous'][0]['domain']}",
            fg="yellow",
        )

    ncfg = NormalizeConfig(keep_group_titles=keep_titles, internal_domains=domains)
    interactions, nrep = normalize(res.raw_events, {}, ncfg)

    seen = {e.event_id for e in existing}
    merged = existing + [e for e in interactions if e.event_id not in seen]
    _write_interactions(out, merged)

    read_now = list(calendar)
    for f in calendars_from:
        if f.exists():
            read_now += [l.strip() for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    if read_now:
        record_read(out, read_now)

    hint = coverage_hint(res.raw_events)
    typer.secho(f"✓ {out} に {len(merged)} 件（今回 +{len(merged) - len(existing)} 件）", fg="green")
    typer.echo(f"  観測できた人数 {hint['people_observed']} 名 / 関係の観測 {hint['pair_observations']:,} 回")
    typer.echo(f"  重複排除 {nrep.dropped_duplicate} / 会議室除去 {nrep.removed_resources} / 辞退除去 {nrep.removed_declined}")
    if nrep.removed_group_addresses:
        names = "、".join(nrep.group_addresses_seen[:6])
        more = f" ほか{len(nrep.group_addresses_seen) - 6}件" if len(nrep.group_addresses_seen) > 6 else ""
        typer.echo(f"  グループアドレス除去 {nrep.removed_group_addresses}件（{names}{more}）")

    nxt = suggest_next(merged, read_calendars(out))
    if nxt["calendars_read"]:
        typer.echo(f"\n  読んだカレンダー {nxt['calendars_read']} 件 → 観測できた人数 {nxt['people_observed']} 名"
                   f"（1件あたり {nxt['leverage']} 名）")
    if nxt["suggestions"]:
        typer.echo("\n  次に読むとよいカレンダー:")
        for r in nxt["suggestions"][:5]:
            typer.echo(f"    {r['calendar']:32s} 出現{r['appearances']:3d}回  {r['reason']}")
    typer.echo("\n  十分かどうかは `relana doctor` の「集計できた人の割合」で判断できます。")


@app.command("next-calendars", help="次にどのカレンダーを読むべきかを提案する。")
def next_calendars(
    interactions_path: Path = typer.Option(Path("interactions.csv"), "--interactions"),
    limit: int = typer.Option(10, "--limit"),
    json_out: bool = typer.Option(True, "--json/--text"),
) -> None:
    """全員分を読む必要はない。多くの会議に現れる人を読むと効率がよい。"""
    from .sources.agent.ingest import read_calendars, suggest_next

    interactions = _load_interactions(interactions_path)
    result = suggest_next(interactions, read_calendars(interactions_path), limit)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command(help="収集した名簿を部署ごとに並べて表示する。利用者に確認してもらうための工程。")
def roster(
    interactions_path: Path = typer.Option(Path("interactions.csv"), "--interactions"),
    persons_path: Path | None = typer.Option(None, "--persons", help="省略すると推定する"),
    headcount: int | None = typer.Option(None, "--headcount", help="実際の従業員数"),
    out: Path | None = typer.Option(None, "-o", "--out", help="CSV として書き出す"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """収集データから名簿を組み立て、確認用に部署ごとに並べる。

    **分析に進む前に、必ずこれを利用者に見せること。**
    実測では、名簿が全社の55%しかないまま分析まで進んでしまった事例がある。
    """
    from .core.roster import build, render_text

    interactions = _load_interactions(interactions_path)
    if not interactions:
        typer.secho("E_NO_INTERACTIONS: 相互作用イベントが0件です。", fg="red")
        raise typer.Exit(code=2)

    persons = _load_persons(persons_path) if persons_path else _infer_persons(
        interactions, Config(), max(ev.ts for ev in interactions)
    )
    review = build(interactions, persons, headcount)

    if out:
        rows = [e.to_row() for e in review.entries]
        with out.open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    if json_out:
        typer.echo(json.dumps(review.to_dict(), ensure_ascii=False, indent=2))
        return
    typer.echo(render_text(review))
    if out:
        typer.secho(f"\n名簿を書き出しました: {out}", fg="green")


@app.command(help="並列収集のためにバッチを分割し、専用の作業ディレクトリを用意する。")
def batches(
    targets: Path | None = typer.Option(None, "--targets", help="メールアドレスを1行ずつ書いたファイル"),
    interactions_path: Path | None = typer.Option(None, "--interactions", help="収集済みデータから対象を取る"),
    unread_only: bool = typer.Option(
        False, "--unread", help="まだカレンダーを読んでいない人だけを対象にする（次の波）"
    ),
    workroot: Path = typer.Option(Path("/tmp/relana-cal"), "--workdir"),
    size: int = typer.Option(12, "--size", help="1バッチあたりの人数"),
    window_days: int = typer.Option(30, "--window-days"),
    domain: str | None = typer.Option(None, "--domain", help="社内ドメイン"),
) -> None:
    """並列収集の準備。バッチごとに専用ディレクトリを切る。

    実測では、複数エージェントが同じ作業ディレクトリに一時ファイルを書いて
    互いに上書きする事故が起きた。ディレクトリの分離はエージェントの裁量ではなく仕様。
    """
    from datetime import timedelta

    from .core.roster import write_batches

    from .core.roster import plan_wave
    from .sources.agent.ingest import read_calendars

    emails: list[str] = []
    wave = None
    wave_warnings: list[str] = []
    if unread_only:
        if not interactions_path:
            typer.secho("E_NEED_INTERACTIONS: --unread には --interactions が必要です。", fg="red")
            raise typer.Exit(code=2)
        ints = _load_interactions(interactions_path)
        wave, wave_warnings = plan_wave(ints, read_calendars(interactions_path))
        emails = wave.unread
        if wave.converged:
            typer.secho(
                "✓ 未読のカレンダーはありません。収束しています。\n"
                "  `relana roster --headcount <従業員数>` で、まだ見つかっていない人がいないか確認してください。",
                fg="green",
            )
            raise typer.Exit(code=0)
    elif targets:
        emails = [l.strip() for l in targets.read_text(encoding="utf-8").splitlines() if l.strip()]
    elif interactions_path:
        for ev in _load_interactions(interactions_path):
            emails += [a for a in ev.attendees if not a.startswith("ext:")]
    if not emails:
        typer.secho(
            "E_NO_TARGETS: 対象がありません。--targets か --interactions を指定してください。", fg="red"
        )
        raise typer.Exit(code=2)

    if not domain:
        doms = [e.split("@")[-1] for e in emails if "@" in e]
        domain = Counter(doms).most_common(1)[0][0] if doms else ""

    plan = write_batches(emails, workroot, size)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=window_days)

    for w in wave_warnings:
        typer.secho(f"! {w}", fg="yellow", err=True)

    typer.echo(json.dumps({
        "batches": plan,
        "total_people": sum(b["count"] for b in plan),
        **({"wave": wave.to_dict()} if wave else {}),
        "window": {"start": start.date().isoformat(), "end": end.date().isoformat()},
        "internal_domain": domain,
        "prompt_template": ".claude/skills/calendar-collect/subagent-prompt.md",
        "note": (
            "各バッチを別のサブエージェントに割り当ててください。"
            "作業ディレクトリは必ず batch ごとの workdir を使わせること。"
            "安価なモデルで構いませんが、指示は subagent-prompt.md をそのまま渡してください。"
        ),
    }, ensure_ascii=False, indent=2))


@app.command("org-draft", help="部門を判断するための材料を書き出す（判断そのものは行わない）。")
def org_draft(
    interactions_path: Path = typer.Option(..., "--interactions"),
    out: Path = typer.Option(Path("org-evidence.json"), "-o", "--out"),
) -> None:
    """部門を判断するための材料を書き出す（判断そのものは行わない）。

    アルゴリズムは「誰と誰が同じ定例に出るか」までしか分からない。
    「その定例が何の集まりか」は会議タイトルを読む必要があり、
    そこは人や言語モデルのほうが正確に判断できる。
    """
    from .core.graph import build_graphs
    from .core.org_inference import build_evidence, infer_org, infer_people

    interactions = _load_interactions(interactions_path)
    if not interactions:
        typer.secho("E_NO_INTERACTIONS: 相互作用イベントが0件です。", fg="red")
        raise typer.Exit(code=2)

    people = {p.person_id: p for p in infer_people(interactions)}
    cfg = Config()
    window_end = max(ev.ts for ev in interactions)
    bundle = build_graphs(interactions, people, cfg, window_end)
    org = infer_org(interactions, bundle.undirected)
    ev = build_evidence(interactions, org, bundle.undirected)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(json.dumps(ev, ensure_ascii=False, indent=2))
    if not ev["titles_available"]:
        typer.secho(
            "\n! 会議タイトルが含まれていません。チーム名・部門名の判断材料が乏しくなります。\n"
            "  normalize.keep_group_titles を有効にして取り込み直すと精度が上がります"
            "（定期グループ会議のタイトルのみ保持し、1on1 のタイトルは取得しません）。",
            fg="yellow",
            err=True,
        )


@app.command("org-apply", help="判断結果（部門の割り当て・チーム名）を persons.csv に反映する。")
def org_apply(
    interactions_path: Path = typer.Option(..., "--interactions"),
    mapping_path: Path = typer.Option(..., "--mapping", help="判断結果のJSON"),
    out: Path = typer.Option(Path("persons.csv"), "-o", "--out"),
) -> None:
    """判断結果（部門の割り当て・チーム名）を persons.csv に反映する。

    mapping JSON の形式:
      {"departments": {"営業本部": ["u_031チーム", "u_043チーム"]},
       "team_names": {"u_031チーム": "東日本"}}
    """
    from .core.graph import build_graphs
    from .core.org_inference import apply_mapping, infer_org, infer_people

    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    if "departments" not in mapping:
        typer.secho(
            "E_BAD_MAPPING: 'departments' キーがありません。"
            '{"departments": {"部門名": ["チームID", ...]}} の形式にしてください。',
            fg="red",
        )
        raise typer.Exit(code=2)

    interactions = _load_interactions(interactions_path)
    people = {p.person_id: p for p in infer_people(interactions)}
    cfg = Config()
    window_end = max(ev.ts for ev in interactions)
    bundle = build_graphs(interactions, people, cfg, window_end)
    org = infer_org(interactions, bundle.undirected)

    known = {t.team_id for t in org.teams}
    referenced = {tid for tids in mapping["departments"].values() for tid in tids}
    missing = referenced - known
    if missing:
        typer.secho(
            f"E_UNKNOWN_TEAM: 存在しないチームIDが指定されています: {sorted(missing)}\n"
            f"  使用可能: {sorted(known)}",
            fg="red",
        )
        raise typer.Exit(code=2)
    unmapped = known - referenced
    if unmapped:
        typer.secho(f"! どの部門にも割り当てられていないチーム: {sorted(unmapped)}", fg="yellow")

    rows = apply_mapping(org, mapping["departments"], mapping.get("team_names"))
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    typer.secho(f"✓ {out} に書き出しました（{len(rows)}名）", fg="green")
    from collections import Counter

    for d, c in Counter(r["dept"] for r in rows).most_common():
        typer.echo(f"  {d or '(未割当)'}: {c}名")


@app.command(help="入力の構造だけを返す。実データの値は表示しない。")
def profile(
    path: Path = typer.Argument(..., help="調べたいファイルまたはフォルダ"),
    json_out: bool = typer.Option(True, "--json/--text", help="機械可読出力（既定）"),
) -> None:
    """入力の構造だけを返す。実データの値は表示しない。"""
    from .core.profile import profile_path

    if not path.exists():
        typer.secho(f"E_NOT_FOUND: {path} が見つかりません。", fg="red")
        raise typer.Exit(code=2)
    info = profile_path(path)
    if json_out:
        typer.echo(json.dumps(info, ensure_ascii=False, indent=2))
        return
    typer.echo(json.dumps(info, ensure_ascii=False, indent=2))


@app.command(help="スキーマ違反をまとめて返す。1件ずつ直させて往復を増やさない。")
def validate(
    interactions_path: Path = typer.Option(..., "--interactions"),
    persons_path: Path = typer.Option(..., "--persons"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """スキーマ違反を**まとめて**返す。1件ずつ直させて往復を増やさない。"""
    from .core.validate import validate_interactions, validate_persons

    prows = _read_rows(persons_path)
    irows = _read_rows(interactions_path)
    pres = validate_persons(prows)
    ires = validate_interactions(irows, {r.get("person_id") for r in prows})
    issues = pres.issues + ires.issues

    if json_out:
        typer.echo(
            json.dumps(
                {
                    "ok": pres.ok and ires.ok,
                    "persons": pres.to_dict(),
                    "interactions": ires.to_dict(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if not issues:
            typer.secho("✓ 問題は見つかりませんでした。", fg="green")
        for i in issues:
            color = "red" if i.severity == "error" else "yellow"
            where = f"（{i.row}行目）" if i.row else ""
            typer.secho(f"[{i.code}] {i.message}{where}", fg=color)
            typer.echo(f"  → {i.fix}")
    raise typer.Exit(code=0 if (pres.ok and ires.ok) else 2)


@app.command(help="このまま分析して意味のある結果が出るかを診断する。")
def doctor(
    interactions_path: Path = typer.Option(..., "--interactions"),
    persons_path: Path | None = typer.Option(None, "--persons", help="省略するとカレンダーから推定する"),
    headcount: int | None = typer.Option(
        None, "--headcount", help="実際の従業員数。名簿は不要、人数だけで足りているか判定できる"
    ),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """このまま分析して意味のある結果が出るかを診断する。"""
    from .core.doctor import diagnose

    interactions = _load_interactions(interactions_path)
    if persons_path:
        persons = _load_persons(persons_path)
    else:
        from .sources.agent.ingest import read_jsonl  # noqa: F401
        from .core.org_inference import infer_people

        persons = [p for p in infer_people(interactions) if not p.is_external]
    checks = diagnose(
        interactions, persons, headcount=headcount, roster_provided=persons_path is not None
    )

    if json_out:
        typer.echo(json.dumps([c.to_dict() for c in checks], ensure_ascii=False, indent=2))
    else:
        mark = {"ok": ("✓", "green"), "info": ("i", "blue"), "warning": ("!", "yellow"), "critical": ("■", "red")}
        for c in checks:
            sym, color = mark.get(c.severity, ("-", None))
            typer.secho(f"{sym} {c.title}", fg=color, bold=c.severity in ("warning", "critical"))
            if c.detail:
                typer.echo(f"    {c.detail}")
            if c.action:
                typer.echo(f"    → {c.action}")
    worst = max((c.severity for c in checks), key=lambda s: ["ok", "info", "warning", "critical"].index(s))
    raise typer.Exit(code=2 if worst == "critical" else 0)


@app.command(help="指標の定義・計算式・出典・解釈の限界を返す。")
def explain(metric: str = typer.Argument(..., help="constraint / betweenness / ie_ratio / team / vulnerability")) -> None:
    """指標の定義・計算式・出典・解釈の限界を返す（ドキュメントを読みに行かせない）。"""
    info = EXPLAIN.get(metric)
    if not info:
        typer.secho(
            f"E_UNKNOWN_METRIC: '{metric}' は未知です。使用可能: {', '.join(EXPLAIN)}", fg="red"
        )
        raise typer.Exit(code=2)
    typer.echo(json.dumps(info, ensure_ascii=False, indent=2))


EXPLAIN = {
    "constraint": {
        "feature": "発想の起点となる人",
        "definition": "Burt の構造的空隙理論における制約。C_i = Σ_j (p_ij + Σ_q p_iq·p_qj)^2",
        "direction": "低いほど良い（ブローカー位置）",
        "source": "Burt (1992) / 第5章 p.100-102",
        "interprets_as": "斬新な情報へのアクセス可能性",
        "does_not_mean": "創造性そのものの保証ではない",
        "caveats": ["比較可能な集団内でのみ順位に意味がある", "母数が小さいほど順位は粗い"],
    },
    "betweenness": {
        "feature": "インフルエンサー",
        "definition": "同席の重みを距離に直したうえで、他の人どうしの最短経路がその人を通る割合（重み付き媒介中心性）",
        "direction": "高いほど良い",
        "source": "第5章 p.102-104",
        "interprets_as": "他の人どうしが会議でつながる経路のうち、その人を通る割合",
        "does_not_mean": "この数値は好感度を測っていない。役職の高さとも一致しない",
        "caveats": [
            "主催者は使っていない（代理で主催する運用があり、情報として信頼できないため）",
            "発言量や説得力は測っていない",
            "観測できていない人が増えると、経路が変わって値も変わる",
            "『ハブとなっている人』と同じ値を使っている。あちらは上位の人をさらに絞り込む",
        ],
    },
    "ie_ratio": {
        "feature": "部門のつながり",
        "definition": "部門内の同席の重み ÷ 部門外との同席の重み",
        "direction": "低いほど良い",
        "threshold": 5.0,
        "source": "第5章 p.108-111",
        "interprets_as": "部門内だけの会議が、部門外との会議の何倍あるか",
        "does_not_mean": "部門の生産性や貢献度の低さではない",
        "caveats": ["サイロ化は専門性を深めれば自然に起きる", "部門ごとのカレンダー利用習慣の差に影響される"],
    },
    "team": {
        "feature": "部門の型",
        "definition": "内部密度（1人あたり部門内接触量）× 外部範囲（1人あたり外部接触先数 × 非重複度）",
        "direction": "目的による。効率性=密度高×範囲広 / イノベーション=密度低×範囲広",
        "source": "第5章 p.104-108",
        "interprets_as": "部門がどの種類の仕事に向いているか",
        "does_not_mean": "部門の優劣ではない",
        "caveats": ["効率性の特徴を持つ部門はイノベーション集団としては失敗しやすい", "中央値分割のため境界付近は入れ替わりやすい"],
    },
    "vulnerability": {
        "feature": "ハブとなっている人",
        "definition": "他の人どうしの経路がその人を通る割合、その人を除くと切り離される集団、社内でその人だけが同席している社外の相手",
        "direction": "その人がいなくても会議でつながる組の割合が低いほど、組織は脆い",
        "source": "第5章 p.111-113",
        "interprets_as": "その人が抜けたとき、会議でつながらなくなる人がどれだけ出るか",
        "does_not_mean": "個人の処遇・評価・報酬の判断材料ではない。後継者計画とBCPのための指標",
        "caveats": ["会議以外の経路で代替関係がある可能性は捉えていない"],
    },
}


def _open(path: Path) -> None:
    """レポートをブラウザで開く。開けなくてもエラーにしない。"""
    import webbrowser

    try:
        webbrowser.open(path.resolve().as_uri())
    except Exception:
        pass


def _print_summary(snap) -> None:
    q, h = snap.quality, snap.highlights
    typer.echo(f"\n=== {snap.snapshot_id} ({snap.window_start}〜{snap.window_end}) ===")
    typer.echo(
        f"対象{q['persons_in_master']}名 / 会議{q['interactions']:,}件 / 関係{q['edges']:,}本 "
        f"/ 集計できた人 {q['edge_coverage_rate']:.0%}"
    )
    if q["persons_in_master"] > 100:
        typer.secho(
            f"⚠ 対象{q['persons_in_master']}名は公称対応範囲（100名）を超えています。"
            "収集と分析に時間がかかります。まず実行して所要時間を確認してください。",
            fg="yellow",
        )

    typer.echo("\n直接の相手が少ないのに、情報の通り道になっている人")
    for r in h["influence_divergence"][:3] or [None]:
        if r is None:
            typer.echo("  該当者はありません")
            break
        typer.echo(
            f"  {r['label']} ({r['dept']})  直接{r['direct']}名"
            f" → 他の人どうしの経路の {r['betweenness']:.2%} が通る"
            f"（媒介中心性 {r['betweenness']:.4f}）"
        )

    typer.echo("\nハブとなっている人（代替者がいない順）")
    for r in h["critical_persons"][:5] or [None]:
        if r is None:
            typer.echo("  該当者はありません")
            break
        typer.echo(
            f"  {r['label']} ({r['dept']})  "
            f"部門の組={'—' if r.get('dept_pairs_kept') is None else format(r['dept_pairs_kept'], '.0%')}"
            f" / 相手どうしの組={r['replaceability']:.0%}"
            f"  [{r['status']}]"
        )

    typer.echo("\n部門のつながり（内向きな順）")
    for r in h["siloed_depts"][:5] or [None]:
        if r is None:
            typer.echo("  警戒レベルの部門はありません")
            break
        extra = f" / ランダムの{r['times_random']}倍" if r.get("times_random") else ""
        typer.echo(f"  {r['dept']}  I/E={r['display']}{extra}  [{r['status']}]")


def _infer_persons(interactions, cfg, window_end) -> list[Person]:
    """名簿が無いときに、カレンダーから人・チーム・部門を推定する。"""
    from .core.graph import build_graphs
    from .core.org_inference import infer_org, infer_people

    people = {p.person_id: p for p in infer_people(interactions)}
    bundle = build_graphs(interactions, people, cfg, window_end)
    org = infer_org(interactions, bundle.undirected)
    by_id = {p.person_id: p for p in org.persons}
    for row in org.as_person_rows():
        p = by_id[row["person_id"]]
        p.dept, p.team, p.role = row["dept"], row["team"], row["role"]
    return list(by_id.values())


def _read_rows(path: Path) -> list[dict]:
    """検証用に生の行を読む（型変換せず、そのまま渡す）。"""
    if path.suffix == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _load_persons(path: Path) -> list[Person]:
    from datetime import date as _date

    out: list[Person] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            out.append(
                Person(
                    person_id=row["person_id"],
                    email=row.get("email", ""),
                    display_name=row.get("display_name", ""),
                    dept=row.get("dept", ""),
                    team=row.get("team", ""),
                    role=row.get("role", ""),
                    hired_at=_date.fromisoformat(row["hired_at"]) if row.get("hired_at") else None,
                    left_at=_date.fromisoformat(row["left_at"]) if row.get("left_at") else None,
                    is_bot=str(row.get("is_bot", "")).lower() == "true",
                    is_external=str(row.get("is_external", "")).lower() == "true",
                    consent_status=row.get("consent_status", "unknown"),
                )
            )
    return out


def _load_interactions(path: Path):
    from .models import Interaction

    rows: list[dict] = []
    if path.suffix == ".jsonl":
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))

    from .sources.gcal.normalize import infer_meeting_type

    out = []
    for r in rows:
        targets = r["target_ids"]
        if isinstance(targets, str):
            targets = [t for t in targets.split("|") if t]
        responses = r.get("responses") or {}
        if isinstance(responses, str) and responses.strip():
            try:
                responses = json.loads(responses)
            except json.JSONDecodeError:
                responses = {}
        if not isinstance(responses, dict):
            responses = {}
        ev = Interaction(
                event_id=r["event_id"],
                ts=datetime.fromisoformat(str(r["ts"]).replace("Z", "+00:00")),
                source=r.get("source", "calendar"),
                channel_type=r.get("channel_type", "meeting"),
                actor_id=r["actor_id"],
                target_ids=targets,
                group_id=r.get("group_id"),
                duration_min=int(r["duration_min"]) if r.get("duration_min") else None,
                is_recurring=str(r.get("is_recurring", "")).lower() == "true",
                group_title=(r.get("group_title") or None),
                responses=responses,
        )
        # meeting_type は人数・時間・定期性から導出できるので保存を必須にしない
        ev.meeting_type = r.get("meeting_type") or infer_meeting_type(ev)
        out.append(ev)
    return out


if __name__ == "__main__":
    app()
