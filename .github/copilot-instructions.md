# relana — GitHub Copilot 向け

**このリポジトリの作業規約は [`AGENTS.md`](./AGENTS.md) にあります。作業を始める前に必ず読んでください。**

以下は、`AGENTS.md` を読む前でも必ず守るべき最低限の規約です。

## 利用者はエンジニアではありません

人事担当者が、自分の会社の組織構造を知るために使います。
専門用語をそのまま出さず、コマンドは利用者に実行させず **あなたが実行してください**。

## セットアップ

利用者が「セットアップして」と言ったら、確認を取らずに実行してよい。

```bash
python3 scripts/setup.py
```

Windows / macOS / Linux 共通です。以降のコマンドは `.venv/bin/relana`（Windows は `.venv\Scripts\relana.exe`）を使います。

## 絶対にしてはいけないこと

| 禁止 | 理由 |
|---|---|
| **指標の値を推測・計算で出す** | 数値は `relana` が計算します。LLM が出すと再現性と監査可能性が失われ、人事判断の根拠にできません |
| **生データファイルを全文読む（`cat` 等）** | 社員の通信履歴がコンテキストに入ります。構造を知るには `relana profile` を使ってください |
| **MCP コネクタ等で本番データを取得する** | 取得範囲がその人の見える範囲に限られ、組織全体になりません。またデータが LLM を経由します |
| **分析結果を外部サービスに送る** | 個人を特定できる情報が含まれます |
| **会議の本文・件名・場所を取得する** | スキーマに存在しません。収集スクリプトでも取得しないでください |

## 文章の書き方

レポートの文面を書くときは
[`.claude/skills/report-writing/SKILL.md`](./.claude/skills/report-writing/SKILL.md) に従い、
`python scripts/check_wording.py` で点検してください（指摘0件になるまで）。

## 結果を説明するとき

`findings.json` の `interprets_as` / `does_not_mean` / `caveats` を必ず引用してください。
とくに **`does_not_mean` を省略しないこと**。数値だけを伝えると誤読されます。

## 組織構造（チーム・部門）の判断

利用者は名簿を用意しません。カレンダーから作ります。
手順は [`.claude/skills/org-structure/SKILL.md`](./.claude/skills/org-structure/SKILL.md) にあります
（Claude Code 以外のエージェントも、このファイルを読んで同じ手順で進めてください）。

詳細は [`AGENTS.md`](./AGENTS.md) を参照してください。
