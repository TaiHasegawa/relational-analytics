"""ネットワーク図の配置をサーバ側で確定させる。

図が動くと、見るたびに形が変わって比較できない。配置は決定論的に計算し、
同じ入力なら同じ図になるようにする（NFR-5）。

配置の方針:
  1. 同じ部門の人を1か所にまとめる
  2. 往来の多い部門どうしを隣に置く
  3. 他部門と強くつながっている人は、相手部門に近い側へ寄せる
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

import networkx as nx

SEED = 42
# ノードどうしの最小間隔（中心間）。
# 図のノードは半径 4〜15px で描くので、15+15=30 より十分広く取らないと
# 円どうしが重なり、かたまりの中の線が隠れて読めなくなる。
MIN_GAP = 40.0
BRIDGE_PULL = 0.42  # 他部門側へ寄せる強さ

# 図に描く関係の下限。重み 1.0 は「1on1 を1回分」に相当する接触量。
# 重みの単位がそのまま意味を持つため、この値は分位点のようにデータごとに
# 変わらない。全ノードに同じ閾値を当てるので、次数の分布が歪まない。
DISPLAY_MIN_WEIGHT = 1.0
CLUSTER_GAP = 110.0  # かたまりどうしの最小の隙間
# 縦方向に強く引き寄せる倍率。図は横長の枠に入るので、全体が正方形に近い形に
# なると上下に余白が出て図が小さく表示される。縦を詰めて横に広げる。
Y_GRAVITY = 12.0
# 部門名ラベルの文字の大きさ（assets.py の .gcluster と合わせる）
LABEL_FONT = 14.0


def display_edges(g: nx.Graph, min_weight: float = DISPLAY_MIN_WEIGHT) -> set[tuple[str, str]]:
    """図に描く関係を選ぶ。全ノードに同じ閾値を当てる。

    ノードごとに上位 k 本を残す方法は使わない。その方法だと、関係の少ない人にも
    必ず k 本の線が付くため、次数の分布が平らになって density が実際より高く見える。
    図から構造を読む以上、この歪みは許容できない。

    閾値 1.0 は「1on1 を1回分」に相当する接触量。重みの単位に意味があるので、
    組織が変わっても同じ基準で読める。これに満たない関係は描かないが、
    件数は図の注記として示す。
    """
    out: set[tuple[str, str]] = set()
    for a, b, d in g.edges(data=True):
        if d.get("weight", 1.0) >= min_weight:
            out.add((a, b) if a <= b else (b, a))
    return out


def compute(
    g: nx.Graph, group_attr: str = "dept", min_weight: float = DISPLAY_MIN_WEIGHT
) -> dict[str, Any]:
    """ノード座標、部門ラベルの位置、描画範囲を返す。

    配置は図に描く関係だけで計算する。描かない線に引かれて配置が決まると、
    図の見た目と配置の根拠がずれる。
    """
    shown = display_edges(g, min_weight)
    lay = nx.Graph()
    lay.add_nodes_from(g.nodes(data=True))
    for a, b in shown:
        lay.add_edge(a, b, **g[a][b])
    g = lay
    internal = [n for n, d in g.nodes(data=True) if not d.get("is_external")]
    externals = [n for n, d in g.nodes(data=True) if d.get("is_external")]

    groups: dict[str, list[str]] = defaultdict(list)
    for n in internal:
        groups[g.nodes[n].get(group_attr) or "(未設定)"].append(n)
    names = _order_groups(g, groups, group_attr)
    if not names:
        return {"pos": {}, "groups": [], "bounds": [0, 0, 100, 100]}

    # まず部門ごとに中の配置を決め、そのかたまりが実際にどれだけの大きさに
    # なったかを測ってから、かたまりどうしを詰める。場所の見積もりで詰めると、
    # 人が少ない部門のまわりに使われない余白が残る
    pos: dict[str, tuple[float, float]] = {}
    for name in names:
        pos.update(_place_within(g, sorted(groups[name]), 0.0, 0.0, len(groups[name])))
    size = {k: _spread(pos, groups[k], (0.0, 0.0)) for k in names}

    cross = _cross_weights(g, groups, group_attr)
    centers = _pack_groups(names, _group_centers(names, groups), size, cross)
    for name in names:
        cx, cy = centers[name]
        for m in groups[name]:
            pos[m] = (pos[m][0] + cx, pos[m][1] + cy)

    _pull_bridges(g, pos, centers, group_attr)
    inside = {m for ms in groups.values() for m in ms}
    # 押し離すと円から出て、戻すとまた重なる。交互に回して両方を満たす
    for i in range(8):
        _clamp_to_clusters(pos, groups, centers)
        _relax(pos, rounds=30, members=inside)
    # 他部門と強くつながっている人を縁へ寄せた分、かたまりは詰める前の見積もりより
    # 大きくなる。部門が多いと、この差でかたまりどうしが重なり、色が混ざって
    # どこからどこまでが1つの部門なのか読めなくなる。実測の大きさで押し離す
    _clamp_to_clusters(pos, groups, centers)
    measured = {k: _spread(pos, groups[k], centers[k]) for k in names}
    moved = _separate(names, centers, measured)
    for name in names:
        dx = moved[name][0] - centers[name][0]
        dy = moved[name][1] - centers[name][1]
        if dx or dy:
            for m in groups[name]:
                pos[m] = (pos[m][0] + dx, pos[m][1] + dy)
    centers = moved
    _clamp_to_clusters(pos, groups, centers)
    # ここまでの輪は、1人も重ならずに入る大きさで取ってある。実際の配置は
    # それより小さく収まるので、空いた分だけ全体を縮めて図を詰める
    centers, blobs = _contract(pos, groups)
    _place_externals(g, pos, externals, centers, group_attr)

    # 部門ラベルは、人の丸のかたまりのすぐ外に置く
    gx = sum(c[0] for c in centers.values()) / len(centers)
    gy = sum(c[1] for c in centers.values()) / len(centers)
    label_pos = {}
    for name in names:
        cx, cy = centers[name]
        dx, dy = cx - gx, cy - gy
        d = math.hypot(dx, dy) or 1.0
        label_pos[name] = (cx + dx / d * (blobs[name] + 18),
                           cy + dy / d * (blobs[name] + 18))

    # 部門名は人の丸より外に出す。丸の座標だけで範囲を決めると、文字が枠の外で切れる
    allx = [p[0] for p in pos.values()] or [0]
    ally = [p[1] for p in pos.values()] or [0]
    for name, (lx, ly) in label_pos.items():
        half = _label_half_width(name, len(groups[name]))
        allx += [lx - half, lx + half]
        ally += [ly - LABEL_FONT, ly + LABEL_FONT]
    pad = 40
    bounds = [min(allx) - pad, min(ally) - pad, max(allx) + pad, max(ally) + pad]

    return {
        "pos": {n: [round(float(x), 1), round(float(y), 1)] for n, (x, y) in pos.items()},
        "groups": [
            {
                "name": name,
                "count": len(groups[name]),
                "x": round(float(label_pos[name][0]), 1),
                "y": round(float(label_pos[name][1]), 1),
            }
            for name in names
        ],
        "bounds": [round(float(v), 1) for v in bounds],
    }


def _order_groups(g: nx.Graph, groups: dict[str, list[str]], attr: str) -> list[str]:
    """往来の多い部門どうしが隣になるよう、円周上の順番を決める。

    最大の部門から始め、まだ置いていない部門のうち直前の部門と最も往来の多いものを
    順に並べる。貪欲法だが決定論的で、線の交差がかなり減る。
    """
    if not groups:
        return []
    cross = _cross_weights(g, groups, attr)

    remaining = sorted(groups, key=lambda k: (-len(groups[k]), k))
    order = [remaining.pop(0)]
    while remaining:
        last = order[-1]
        remaining.sort(
            key=lambda k: (-cross.get((last, k) if last <= k else (k, last), 0.0), k)
        )
        order.append(remaining.pop(0))
    return order


def _cross_weights(
    g: nx.Graph, groups: dict[str, list[str]], attr: str
) -> dict[tuple[str, str], float]:
    """部門どうしの往来の重み。キーは部門名を並べ替えた組。"""
    cross: dict[tuple[str, str], float] = defaultdict(float)
    for a, b, d in g.edges(data=True):
        ga = g.nodes[a].get(attr) or "(未設定)"
        gb = g.nodes[b].get(attr) or "(未設定)"
        if ga in groups and gb in groups and ga != gb:
            cross[(ga, gb) if ga <= gb else (gb, ga)] += d.get("weight", 1.0)
    return cross


def _pack_groups(
    names: list[str],
    centers: dict[str, tuple[float, float]],
    rad: dict[str, float],
    cross: dict[tuple[str, str], float],
) -> dict[str, tuple[float, float]]:
    """かたまりを寄せ集めて、枠に収まる形に詰める。

    輪の上に等間隔で並べると、部門が5つでも中央に大きな穴が空き、
    部門と部門の間が人数に関係なく離れる。実際の画面では、図は縦より横が長い
    枠に入るので、輪のままだと左右も余る。

    そこで輪を出発点にして、往来の多い部門どうしを引き寄せ、重なった分だけ
    押し戻す。往来のない部門にも中心へ寄せる力をかけ、重ならない位置まで詰める。
    すべて決定論的な反復なので、同じ入力なら同じ配置になる。
    """
    if len(names) < 2:
        return centers
    top = max(cross.values()) if cross else 1.0
    pull = {
        k: {j: cross.get((k, j) if k <= j else (j, k), 0.0) / top for j in names if j != k}
        for k in names
    }
    pt = dict(centers)
    for _ in range(600):
        # 往来のある部門を引き寄せる
        step: dict[str, list[float]] = {k: [0.0, 0.0] for k in names}
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                w = pull[a][b]
                if w <= 0:
                    continue
                dx, dy = pt[b][0] - pt[a][0], pt[b][1] - pt[a][1]
                d = math.hypot(dx, dy) or 1.0
                slack = d - (rad[a] + rad[b] + CLUSTER_GAP)
                if slack <= 0:
                    continue
                f = 0.03 * w * slack
                step[a][0] += dx / d * f
                step[a][1] += dy / d * f
                step[b][0] -= dx / d * f
                step[b][1] -= dy / d * f
        # 中心へ寄せる。往来のない部門も、重ならない範囲まで図の中へ引き寄せる
        for k in names:
            step[k][0] -= pt[k][0] * 0.006
            step[k][1] -= pt[k][1] * 0.006 * Y_GRAVITY
        pt = {k: (pt[k][0] + step[k][0], pt[k][1] + step[k][1]) for k in names}
        pt = _separate(names, pt, rad, rounds=4)
    return {k: (round(v[0], 3), round(v[1], 3)) for k, v in pt.items()}


def _separate(
    names: list[str],
    centers: dict[str, tuple[float, float]],
    rad: dict[str, float],
    rounds: int = 60,
) -> dict[str, tuple[float, float]]:
    """重なったかたまりを、縁が CLUSTER_GAP だけ離れるまで押し離す。"""
    pt = dict(centers)
    for _ in range(rounds):
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                dx, dy = pt[b][0] - pt[a][0], pt[b][1] - pt[a][1]
                d = math.hypot(dx, dy) or 1.0
                want = rad[a] + rad[b] + CLUSTER_GAP
                if d >= want:
                    continue
                sh = (want - d) / 2
                ux, uy = dx / d, dy / d
                pt[a] = (pt[a][0] - ux * sh, pt[a][1] - uy * sh)
                pt[b] = (pt[b][0] + ux * sh, pt[b][1] + uy * sh)
    return pt


def _group_centers(
    names: list[str], groups: dict[str, list[str]]
) -> dict[str, tuple[float, float]]:
    """部門のかたまりを円周上に並べる。

    隣り合うかたまりが重ならない**最小**の輪を求める。角度は人数比ではなく、
    隣り合う2つに必要な中心間の距離から決める。

    これは `_pack_groups` の出発点で、最終的な配置ではない。
    """
    n = len(names)
    if n == 1:
        return {names[0]: (0.0, 0.0)}
    radii = {k: _clamp_limit(len(groups[k])) for k in names}

    # 隣り合う2つに必要な中心間の距離。これを弦として角度を割り当てる
    need = [
        (radii[names[i]] + radii[names[(i + 1) % n]] + CLUSTER_GAP) / 2.0
        for i in range(n)
    ]
    ring = _ring_radius(need)

    centers: dict[str, tuple[float, float]] = {}
    angle = -math.pi / 2
    for i, name in enumerate(names):
        centers[name] = (ring * math.cos(angle), ring * math.sin(angle))
        angle += 2 * math.asin(min(1.0, need[i] / ring))
    return centers


def _ring_radius(need: list[float]) -> float:
    """かたまりが重ならずに一周する、**最小**の輪の半径を求める。

    輪を人数比で等分すると、小さい部門どうしに割り当たる角度が狭くなり、
    その2つを離すために輪全体が大きくなる。図の中央が空き、部門が遠くに離れて
    部門をまたぐ線ばかりが目立つ。

    ここでは逆に、必要な中心間の距離（弦）から角度を決め、その合計がちょうど
    一周になる半径を二分法で探す。角度の合計は半径について単調に減るので、
    解は1つに決まる。
    """
    def turn(r: float) -> float:
        return sum(2 * math.asin(min(1.0, d / r)) for d in need)

    lo = max(need)  # これ未満だと弦が直径を超えて、角度が決まらない
    if turn(lo) <= 2 * math.pi:
        return lo
    hi = lo
    while turn(hi) > 2 * math.pi:
        hi *= 2
    for _ in range(60):
        mid = (lo + hi) / 2
        if turn(mid) > 2 * math.pi:
            lo = mid
        else:
            hi = mid
    return hi


def _clamp_limit(count: int) -> float:
    """この半径の円から出た人は縁に戻す。かたまりどうしの間隔もこの値で測る。

    すべての人がこの円の中に収まるので、円どうしが離れていれば
    部門のかたまりが重なることはない。
    """
    return _pack_radius(count) * 1.25 + 15.0


def _cluster_radius(count: int) -> float:
    """かたまり1つに充てる場所の広さ。ここから出た人は縁に戻す。

    実際の配置はこれより小さく収まる。余った分は `_contract` で詰める。
    """
    return max(45.0, _pack_radius(count) * 1.55)


def _pack_radius(count: int) -> float:
    """その人数が MIN_GAP を保って詰められる、**いちばん小さい**円の半径。"""
    count = max(count, 1)
    return MIN_GAP * math.sqrt(count / math.pi) / 0.82


def _place_within(
    g: nx.Graph, members: list[str], cx: float, cy: float, count: int
) -> dict[str, tuple[float, float]]:
    """部門の中の配置。部門内の関係でレイアウトし、円の中に収める。"""
    # 詰められる最小の大きさに合わせる。場所の広さ（_cluster_radius）に
    # 合わせて広げると、人の少ない部門ほどすかすかになり、図が間延びする
    r = _pack_radius(count)
    if count == 1:
        return {members[0]: (cx, cy)}
    sub = g.subgraph(members)
    if sub.number_of_edges() == 0:
        return {
            m: (
                cx + r * 0.9 * math.cos(2 * math.pi * i / count),
                cy + r * 0.9 * math.sin(2 * math.pi * i / count),
            )
            for i, m in enumerate(members)
        }
    raw = nx.spring_layout(sub, seed=SEED, weight="weight", iterations=200, k=1.5 / math.sqrt(count))
    xs = [p[0] for p in raw.values()]
    ys = [p[1] for p in raw.values()]
    mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    far = max(math.hypot(p[0] - mx, p[1] - my) for p in raw.values()) or 1.0
    scale = r / far
    return {
        m: (cx + (raw[m][0] - mx) * scale, cy + (raw[m][1] - my) * scale) for m in members
    }


def _contract(
    pos: dict[str, tuple[float, float]],
    groups: dict[str, list[str]],
) -> tuple[dict[str, tuple[float, float]], dict[str, float]]:
    """かたまりどうしの隙間を詰める。

    輪の大きさは「その人数が1人も重ならずに入る円」から決めている。実際の配置は
    部門内の関係で決まるため、たいていその円よりずっと小さく収まる。
    そのままだと部門と部門の間が大きく空き、部門をまたぐ長い線ばかりが目立つ。

    置き終わってから実際のかたまりの大きさを測り、どの2つも `CLUSTER_GAP` を
    保てる範囲で全体を中心に寄せる。かたまりの形も部門の並び順も変わらない。

    戻り値は、縮めたあとのかたまりの中心と半径。
    """
    live = {k: v for k, v in groups.items() if v}
    if len(live) < 2:
        cen = {k: _centroid(pos, ms) for k, ms in live.items()}
        return cen, {k: _spread(pos, ms, cen[k]) for k, ms in live.items()}

    cen = {k: _centroid(pos, ms) for k, ms in live.items()}
    rad = {k: _spread(pos, ms, cen[k]) for k, ms in live.items()}
    gx = sum(c[0] for c in cen.values()) / len(cen)
    gy = sum(c[1] for c in cen.values()) / len(cen)

    names = list(live)
    ratio = 0.0
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            d = math.hypot(cen[a][0] - cen[b][0], cen[a][1] - cen[b][1])
            if d <= 0:
                return cen, rad
            ratio = max(ratio, (rad[a] + rad[b] + CLUSTER_GAP) / d)
    s = min(max(ratio, 0.3), 1.0)
    if s >= 0.999:
        return cen, rad

    for ms in live.values():
        for m in ms:
            x, y = pos[m]
            pos[m] = (gx + (x - gx) * s, gy + (y - gy) * s)
    cen = {k: (gx + (c[0] - gx) * s, gy + (c[1] - gy) * s) for k, c in cen.items()}
    return cen, rad


def _centroid(pos: dict, members: list[str]) -> tuple[float, float]:
    xs = [pos[m][0] for m in members]
    ys = [pos[m][1] for m in members]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _spread(pos: dict, members: list[str], center: tuple[float, float]) -> float:
    """かたまりの実際の半径。丸の半径ぶんだけ外に足す。"""
    far = max(math.hypot(pos[m][0] - center[0], pos[m][1] - center[1]) for m in members)
    return far + 15.0


def _pull_bridges(
    g: nx.Graph,
    pos: dict[str, tuple[float, float]],
    centers: dict[str, tuple[float, float]],
    attr: str,
) -> None:
    """他部門と強くつながっている人を、相手部門に近い側へ寄せる。

    これにより、部門間をつないでいる人がかたまりの縁に立つ。
    ❻脆弱性で検出される人物が、図の上でも見つけやすくなる。
    """
    moved: dict[str, tuple[float, float]] = {}
    for n in pos:
        own = g.nodes[n].get(attr) if n in g else None
        if own not in centers:
            continue
        total = 0.0
        tx = ty = 0.0
        for nb in g.neighbors(n):
            other = g.nodes[nb].get(attr)
            if g.nodes[nb].get("is_external") or other == own or other not in centers:
                continue
            w = g[n][nb].get("weight", 1.0)
            total += w
            tx += centers[other][0] * w
            ty += centers[other][1] * w
        if total <= 0:
            continue
        inside = g.subgraph(
            [m for m in g.neighbors(n) if g.nodes[m].get(attr) == own]
        ).number_of_nodes()
        share = total / (total + max(inside, 1) * 2.0)
        f = min(BRIDGE_PULL, share)
        x, y = pos[n]
        moved[n] = (x + (tx / total - x) * f, y + (ty / total - y) * f)
    pos.update(moved)


def _clamp_to_clusters(
    pos: dict[str, tuple[float, float]],
    groups: dict[str, list[str]],
    centers: dict[str, tuple[float, float]],
) -> None:
    """かたまりの円から出た人を、縁に戻す。

    橋渡しの引き寄せと重なり解消で外へ出ると、部門のかたまりが混ざって
    どこまでが同じ部門か読めなくなる。縁までは許し、それより外は戻す。
    """
    for name, members in groups.items():
        cx, cy = centers[name]
        limit = _clamp_limit(len(members))
        for m in members:
            x, y = pos[m]
            dx, dy = x - cx, y - cy
            d = math.hypot(dx, dy)
            if d > limit:
                pos[m] = (cx + dx / d * limit, cy + dy / d * limit)


def _place_externals(
    g: nx.Graph,
    pos: dict[str, tuple[float, float]],
    externals: list[str],
    centers: dict[str, tuple[float, float]],
    attr: str,
) -> None:
    """社外の相手は、最も往来のある部門の外側に置く。"""
    if not centers:
        return
    cx = sum(c[0] for c in centers.values()) / len(centers)
    cy = sum(c[1] for c in centers.values()) / len(centers)
    for i, e in enumerate(sorted(externals)):
        best, bw = None, 0.0
        for nb in g.neighbors(e):
            d = g[e][nb].get("weight", 1.0)
            grp = g.nodes[nb].get(attr)
            if grp in centers and d > bw:
                best, bw = grp, d
        bx, by = centers.get(best, (cx, cy))
        dx, dy = bx - cx, by - cy
        norm = math.hypot(dx, dy) or 1.0
        pos[e] = (bx + dx / norm * 95 + (i % 2) * 24, by + dy / norm * 95 + (i % 3) * 20)


def _relax(
    pos: dict[str, tuple[float, float]],
    rounds: int = 60,
    members: set[str] | None = None,
) -> None:
    """重なったノードを押し離す。決定論的に収束させる。"""
    keys = sorted(members) if members is not None else sorted(pos)
    for _ in range(rounds):
        moved = False
        for i, a in enumerate(keys):
            ax, ay = pos[a]
            for b in keys[i + 1 :]:
                bx, by = pos[b]
                dx, dy = bx - ax, by - ay
                d = math.hypot(dx, dy)
                if d >= MIN_GAP:
                    continue
                if d < 1e-6:
                    dx, dy, d = 0.6, 0.4, 0.72
                push = (MIN_GAP - d) / 2 + 0.25
                ux, uy = dx / d * push, dy / d * push
                pos[a] = (ax - ux, ay - uy)
                pos[b] = (bx + ux, by + uy)
                ax, ay = pos[a]
                moved = True
        if not moved:
            break


def place_labels(
    pos: dict[str, tuple[float, float]],
    order: list[tuple[str, str, float]],
    char_w: float = 5.4,
    h: float = 10.5,
) -> dict[str, dict[str, Any]]:
    """氏名ラベルを重ならないように置く。

    全員分を同じ側に出すと重なって読めない。左右と上下にずらして空きを探し、
    それでも置けない人は出さない。場所を確保する順番は呼び出し側が決める。

    返すのは node からの相対位置（左右どちらか、縦のずれ）。
    丸の大きさは表示中に変わるため、最終的な x は描画側で決める。
    """
    placed: list[tuple[float, float, float, float]] = []
    out: dict[str, dict[str, Any]] = {}
    offsets = [(1, 0.0), (-1, 0.0), (1, -1.0), (-1, -1.0), (1, 1.0), (-1, 1.0), (1, 2.0), (-1, 2.0)]
    for node, label, r in order:
        x, y = pos[node]
        w = len(label) * char_w + 5
        for side, dy in offsets:
            lx = x + (r + 4) if side > 0 else x - (r + 4) - w
            ly = y + 3.4 + dy * (h + 1)
            box = (lx, ly - h * 0.8, lx + w, ly + h * 0.25)
            if any(_overlap(box, p) for p in placed):
                continue
            placed.append(box)
            out[node] = {"side": side, "dy": round(dy * (h + 1) + 3.4, 1), "w": round(w, 1)}
            break
    return out


def _overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _label_half_width(name: str, count: int) -> float:
    """部門名ラベルの横幅の半分。中央そろえで描くので、左右に同じだけ要る。"""
    text = f"{name}（{count}名）"
    # 全角は font-size と同じ幅、半角はその半分で見積もる
    width = sum(LABEL_FONT if ord(c) > 0x2000 else LABEL_FONT / 2 for c in text)
    return width / 2
