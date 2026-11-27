"""Google Calendar の認証（設計 §3）。

トークンは利用者のマシンにのみ保存され、OSS提供者のサーバを一切経由しない。

方式は3つ。設計 §3.3 のフォールバック順に対応する。
  1. 内部用OAuthクライアント  … 利用企業が自社に登録する。アプリ審査が不要
  2. サービスアカウント       … 管理者が設定。社内共有設定に依存せず最も確実
  3. （未対応）監査ログCSV
"""

from __future__ import annotations

import json
from pathlib import Path

SCOPES_READONLY = ["https://www.googleapis.com/auth/calendar.readonly"]
SCOPES_DIRECTORY = ["https://www.googleapis.com/auth/admin.directory.user.readonly"]

DEFAULT_TOKEN = Path.home() / ".relana" / "google-token.json"

SETUP_GUIDE = """\
Google カレンダーに接続するための準備（5〜10分）

  1. https://console.cloud.google.com/ を開く
  2. 画面上部でプロジェクトを新規作成する（名前は何でもよい。例: relana）
  3. 左メニュー「APIとサービス」→「ライブラリ」→ "Google Calendar API" を検索して「有効にする」
  4. 左メニュー「APIとサービス」→「OAuth同意画面」
       User Type は【内部】を選ぶ ★重要
       （内部にするとアプリ審査が不要になります。社内利用のみ可能です）
       アプリ名・サポートメールを入力して保存
  5. 左メニュー「APIとサービス」→「認証情報」→「認証情報を作成」
       →「OAuth クライアント ID」→ アプリケーションの種類は【デスクトップアプリ】
  6. 作成後、右の「JSONをダウンロード」を押す
  7. ダウンロードしたファイルのパスを relana に渡す

  ※ 手順4で【内部】が選べない場合、その Google アカウントは
     Google Workspace ではなく個人アカウントの可能性があります。
     会社のアカウントでログインし直してください。
"""


class AuthError(RuntimeError):
    """認証に失敗した。利用者が次に何をすべきかを message に含める。"""


def _require_libs():
    try:
        from google.auth.transport.requests import Request  # noqa: F401
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: F401
        from googleapiclient.discovery import build  # noqa: F401
    except ImportError as e:
        raise AuthError(
            "Google 接続用の部品が入っていません。次を実行してください:\n"
            "    .venv/bin/python -m pip install -e '.[gcal]'"
        ) from e


def user_credentials(
    client_secrets: Path,
    token_path: Path = DEFAULT_TOKEN,
    scopes: list[str] | None = None,
):
    """内部用OAuthクライアントで、利用者自身の権限の認証情報を得る（方式1）。

    ブラウザが開き、利用者が「許可」を押すとローカルに戻ってくる。
    トークンはこのマシンにのみ保存される。
    """
    _require_libs()
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    scopes = scopes or SCOPES_READONLY
    token_path = Path(token_path)
    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), scopes)
        except ValueError:
            creds = None

    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not Path(client_secrets).exists():
            raise AuthError(
                f"OAuth クライアントのファイルが見つかりません: {client_secrets}\n\n" + SETUP_GUIDE
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), scopes)
        creds = flow.run_local_server(
            port=0,
            prompt="consent",
            authorization_prompt_message="ブラウザが開きます。会社の Google アカウントで「許可」を押してください。",
            success_message="接続できました。このタブは閉じて構いません。",
        )

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    token_path.chmod(0o600)
    return creds


def service_account_credentials(key_path: Path, subject: str, scopes: list[str] | None = None):
    """サービスアカウント＋ドメイン全体の委任（方式2）。

    社内のカレンダー共有設定に依存せず、確実に全員分を取得できる。
    管理者による設定が必要。
    """
    _require_libs()
    from google.oauth2 import service_account

    if not Path(key_path).exists():
        raise AuthError(f"サービスアカウントの鍵ファイルが見つかりません: {key_path}")
    creds = service_account.Credentials.from_service_account_file(
        str(key_path), scopes=scopes or SCOPES_READONLY
    )
    return creds.with_subject(subject)


def calendar_service(creds):
    _require_libs()
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def directory_service(creds):
    _require_libs()
    from googleapiclient.discovery import build

    return build("admin", "directory_v1", credentials=creds, cache_discovery=False)


def describe_token(token_path: Path = DEFAULT_TOKEN) -> dict:
    p = Path(token_path)
    if not p.exists():
        return {"exists": False, "path": str(p)}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {
        "exists": True,
        "path": str(p),
        "scopes": data.get("scopes", []),
        "has_refresh_token": bool(data.get("refresh_token")),
    }
