# サブエージェントへの指示テンプレート

安価なモデルで実行してよい。作業は機械的だが、**曖昧にすると各自が工夫を始めて事故る**ため、
以下をそのまま渡すこと。`<>` を埋めて使う。

---

カレンダーから会議データを抽出してください。機械的な作業です。工夫は不要です。

## 作業ディレクトリ（必ずこれを使う）

```
WORKDIR=/tmp/cal/<バッチ名>
mkdir -p "$WORKDIR"
```

**一時ファイルもスクリプトも、すべて $WORKDIR の中に作ってください。**
他のエージェントが並列で動いており、共有ディレクトリにファイルを作ると互いに上書きします。

## 対象者

```
<メールアドレスを1行ずつ>
```

## 各対象者について行うこと

1. `list_events` を呼ぶ

```
calendarId: <対象者のメールアドレス>
startTime:  <開始>T00:00:00+09:00
endTime:    <終了>T00:00:00+09:00
orderBy:    startTime
eventType:  ["DEFAULT"]
pageSize:   250
```

2. `nextPageToken` が返ったら、`pageToken` に渡して次ページも取得する（必須）

3. 応答がファイルに保存された場合、**そのファイルを Read してはいけません。**
   パスを使って jq で処理します。

```bash
jq -c '.events[] | select(.attendees != null) |
  {id, summary, start: .start.dateTime, end: .end.dateTime,
   organizer: .organizer.email,
   recurring: (.recurringEventId != null),
   attendees: [.attendees[] | select(.resource != true)
               | select(.email | endswith("@<社内ドメイン>"))
               | {email: .email, responseStatus: .responseStatus}]}
  | select(.attendees | length >= 2)' "<保存されたパス>" >> "$WORKDIR/out.jsonl"
```

4. 応答が会話に直接返ってきた場合は、同じ形式の JSONL を自分で書いて `$WORKDIR/out.jsonl` に追記する

## 報告すること

**会議のタイトルや参加者を報告に含めないでください。** 以下だけを返します。

- 成功した人数 / 失敗した人（メールアドレスとエラー種別）
- 出力した行数
- `$WORKDIR/out.jsonl` のパス
- ページングが発生した人数

## してはいけないこと

- 保存されたファイルを Read する
- $WORKDIR の外にファイルを作る
- 会議の内容を報告や会話に書く
- 1ページ目だけで終わらせる
