# relational-analytics — 組織のリレーショナル分析

会議の予定（カレンダー）から **社員と社員の「関係」** を分析し、組織の構造的な特徴を測るツールです。

年齢や勤続年数といった「個人の属性」ではなく、**誰と誰がつながっているか**を見ます。

---

> **English summary** — relational-analytics turns meeting records from Google Calendar into an
> organizational network and reports five structural signals: ideation, influence, silos,
> team structure and vulnerability (single points of failure). It is designed for HR teams
> who are not engineers, so the whole workflow (setup, data collection, org-chart inference,
> interpretation) can be driven by a coding agent such as Claude Code, Codex, Gemini CLI,
> Cursor or GitHub Copilot. The report and documentation are in Japanese. Apache-2.0.


## はじめかた（エンジニアでない方へ）

### コーディングエージェントをお使いの場合 — いちばん簡単です

Claude Code / Codex / Gemini・Antigravity / Cursor / GitHub Copilot に対応しています。

このフォルダを開いて、こう頼んでください。

> **「セットアップして、サンプルで分析を見せて」**

あとは全部やってくれます。手順は `AGENTS.md` に書いてあり、
各ツール向けの設定ファイル（`CLAUDE.md` / `GEMINI.md` など）はそこを指しています。

### 自分で行う場合

**macOS** — `scripts` フォルダの中の **「はじめに実行.command」** をダブルクリックしてください。

> 「開発元を検証できないため開けません」と出たら、そのファイルを **右クリック →「開く」** を選び、もう一度「開く」を押してください。

**Windows** — `scripts` フォルダの中の **`setup.ps1`** を右クリックして「PowerShell で実行」を選んでください。

**どの OS でも（ターミナルが使える方）** — `python3 scripts/setup.py` を実行してください。

数分で終わり、サンプルのレポートがブラウザで開きます。

> うまくいかないときは、Python 3.11 以上が入っていないことがほとんどです。
> セットアップ画面に入れ方の案内が出るので、それに従ってからもう一度実行してください。

---

## 何が分かるか

典拠は『ピープルアナリティクスで人事戦略が変わる』第5章の **6つの構造的特徴** です。

| | 特徴 | 粒度 | 分かること |
|---|---|---|---|
| ❶ | 発想力 | 個人 | よいアイデアを思いつくのは誰か |
| ❷ | 影響力 | 個人 | 他者の行動を実際に変えられるのは誰か |
| ❸ | 効率性 | チーム | スケジュール通りに完了できるチームか |
| ❹ | イノベーション | チーム | 有効なイノベーションを生めるチームか |
| ❺ | サイロ | 組織 | どの部門がタコつぼ化しているか |
| ❻ | 脆弱性 | 組織 | 失ってはならないのは誰か。代替者はいるか |

とくに ❻ は、**組織図では目立たないのに情報の流れを支えている人**を見つけます。
その人が抜けると複数の部門が分断される、という状態を事前に把握できます。

---

## 用意するもの — カレンダーだけです

**名簿も、部門の一覧も、用意する必要はありません。**

カレンダーをつなぐと、会議の形から組織の構造を推定します。

| 推定するもの | 使う手がかり | 精度 |
|---|---|---|
| **チーム** | 毎週同じ顔ぶれで集まる定例会議 | 高い |
| **上司と部下** | 定期的な1on1 の相手 | 高い |
| **部門** | 課長・部長クラスが集まる定例 | ほどほど（下書き） |

推定結果は CSV として書き出されるので、**部門だけ確認して直してください**。
チームと上司の推定はほぼ正確ですが、部門は外れることがあります。

```bash
.venv/bin/relana infer-org --interactions カレンダーのデータ -o persons.csv
# → persons.csv の dept 列を見て、違っていたら直す
```

直さずにそのまま分析することもできます。その場合、サイロ診断の結果には
「部門は推定値なので下書きとして扱ってください」という注記が付きます。

---

## 何を集めて、何を集めないか

**集めるのは「誰と誰が同じ会議に出たか」だけ**です。

| 集めるもの | 集めないもの |
|---|---|
| 会議の参加者 | **会議のタイトル** |
| 開始時刻・所要時間 | **議題・本文・議事録** |
| 主催者 | **場所・添付ファイル** |

会議のタイトルを取らないため、情報システム部門の承認が通りやすく、
社員の心理的な抵抗も小さくなります。

会議タイトルがなくても、**参加人数・所要時間・定期性**から
「1on1」「チーム定例」「全体会」といった会議の種類は推定できます。

---

## 対応規模

**従業員100名程度まで**を公称の対応範囲としています。

| 規模 | 分析 | 収集 |
|---|---|---|
| 〜100名 | 数秒 | 数分 |
| 100〜300名 | 数十秒 | 10分前後 |
| 300〜1,000名 | 数分 | 30分〜数時間 |
| 1,000名〜 | 10分以上 | 数時間〜。**非推奨** |

100名を超える場合も動作しますが、**収集・分析に時間とコストがかかります。**
ここでいうコストは計算時間だけでなく、情報システム部門との調整や、
社員への説明にかかる手間も含みます。対象人数が100名を超えると警告が出ます。

---

## 自社のカレンダーで分析するには

### いちばん簡単な方法 — エージェントに頼む

Claude Code などのカレンダー連携が使える場合、**Google Cloud の設定は一切不要**です。

> **「カレンダーから組織のつながりを分析して」**

エージェントが同僚のカレンダーを順に読み、`relana` に取り込んで分析します。
手順は `.claude/skills/calendar-collect/SKILL.md` にあります。

**全員分を読む必要はありません。** 1人分を読むと、その人の会議に出ていた
全員どうしの関係が分かるため、100名の組織なら15〜20名分で足ります。

### API でつないで自動化したい場合

継続的に自動収集したくなったら、この経路に移ります。**この場合のみ Google Cloud
プロジェクトが必要**です。まず取得できるかを確認します。

```bash
.venv/bin/python scripts/verify_calendar_access.py \
    --client-secrets <ダウンロードしたJSON> \
    --colleagues 同僚1@example.co.jp,同僚2@example.co.jp
```

準備（Google側の設定）の手順は、このスクリプトが画面に表示します。5〜10分です。
エージェントをお使いなら「カレンダーに接続して」と頼めば案内してくれます。

確認が取れたら:

```bash
.venv/bin/relana connect google --client-secrets <JSON>   # ブラウザで「許可」を押す
.venv/bin/relana collect --keep-titles -o interactions.csv
.venv/bin/relana org-draft --interactions interactions.csv -o org-evidence.json
# → エージェントが部門を判断し、persons.csv を作る
.venv/bin/relana snapshot create 2026Q1 --interactions interactions.csv --persons persons.csv
```

---

## 使い方

```bash
.venv/bin/relana demo                  # サンプルで試す（自社データ不要）
.venv/bin/relana explain vulnerability # 指標の定義・出典・限界を見る
.venv/bin/relana snapshot create 2026Q1 --interactions ... --persons ...
.venv/bin/relana snapshot list
```

分析は **スナップショット**（ある期間を固めたもの）の単位で行います。
一度作れば、切り口を変えた再分析は待ち時間なしで行えます。

---

## 取り扱いについて

- 出力には**個人を特定できる情報が含まれます**。閲覧範囲の管理は運用側の責任です
- 本ツールの指標は **解雇・懲戒・人事評価点の根拠として設計されていません**。
  配置・後継者計画・組織改善の材料としてお使いください
- 従業員データの収集・利用には、利用目的の特定と通知または公表が求められます。
  公表はプライバシーポリシーや就業規則への記載で満たせます。詳細は `docs/governance/` を参照してください

---

## ドキュメント

| | |
|---|---|
| `AGENTS.md` | エージェント向けの作業規約（**正本**。`CLAUDE.md` 等はここを指すだけ） |
| `docs/requirements.md` | 要件定義 |
| `docs/design-google-calendar.md` | Google カレンダー版の設計（重み関数の根拠など） |

## ライセンス

Apache-2.0
