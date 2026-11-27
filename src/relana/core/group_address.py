"""グループ／メーリングリストのアドレス判定。

Google Workspace のグループ（`sales@` `info@` など）は実在する人ではないが、
`resource: true` が付かず社内ドメインで終わるため、会議室の除去も外部ドメインの
除去もすり抜ける。人として残ると人数を水増しし、常に多数の会議に現れるため
中心性も歪める。実測で6件の混入が確認されている。

**誤判定を避けるため、確実なものだけを自動で落とす。**
`pr@` はグループだが `pr.tanaka@` は人である。局所部の全体一致を基本とし、
紛らわしいものは落とさずに確認へ回す。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 局所部がこれ**そのもの**ならグループ。部分一致では判定しない
EXACT = {
    "all", "everyone", "staff", "members", "member", "team", "group", "groups",
    "info", "contact", "support", "help", "desk", "admin", "office", "reception",
    "sales", "marketing", "pr", "press", "ir", "recruit", "jobs", "career", "careers",
    "hr", "jinji", "soumu", "keiri", "finance", "accounting", "legal", "general",
    "announce", "announcements", "notice", "news", "newsletter", "bulletin",
    "mail", "ml", "list", "lists", "dl", "distribution",
    "noreply", "no-reply", "donotreply", "do-not-reply", "postmaster", "webmaster",
    "billing", "invoice", "order", "orders", "service", "services",
}

# 局所部の先頭／末尾がこれならグループ（例: all-aias@、sureside-sales@）
PREFIXES = ("all-", "all_", "grp-", "grp_", "ml-", "ml_", "dl-", "dl_", "team-", "group-")
SUFFIXES = (
    "-all", "_all", "-team", "_team", "-group", "_group", "-ml", "_ml",
    "-list", "_list", "-dl", "_dl", "-members", "_members", "-staff", "_staff",
    "-sales", "_sales", "-info", "_info", "-announce", "-notice", "-news",
)

# 確実とは言えないが、グループによくある語。これは**落とさず確認に回す**
SOFT = {
    "biz", "dev", "eng", "tech", "ops", "dm", "fulltime", "parttime", "intern",
    "project", "pj", "wg", "task", "committee", "board", "exec", "management",
}

_SPLIT = re.compile(r"[.\-_+]")


@dataclass
class GroupScan:
    dropped: list[str] = field(default_factory=list)
    suspected: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.dropped) + len(self.suspected)


def local_part(address: str) -> str:
    return address.split("@")[0].strip().lower()


def is_group_address(address: str) -> bool:
    """確実にグループと言えるものだけ True。自動で落としてよい判定。"""
    local = local_part(address)
    if not local:
        return False
    if local in EXACT:
        return True
    if local.startswith(PREFIXES) or local.endswith(SUFFIXES):
        return True
    return False


def is_suspected_group(address: str) -> bool:
    """グループかもしれないが断定できないもの。落とさず確認に回す。"""
    if is_group_address(address):
        return False
    parts = set(_SPLIT.split(local_part(address)))
    return bool(parts & (EXACT | SOFT))


def scan(addresses: list[str]) -> GroupScan:
    out = GroupScan()
    for a in dict.fromkeys(addresses):
        if is_group_address(a):
            out.dropped.append(a)
        elif is_suspected_group(a):
            out.suspected.append(a)
    return out
