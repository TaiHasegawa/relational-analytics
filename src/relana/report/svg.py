"""レポート用の図。外部ライブラリを使わず、インラインSVGで描く。

典拠 第5章 p.113 は、ノードとエッジの図からはパフォーマンスを予測するパターンが
見つからないと指摘している。そのため全体のネットワーク図は描かない。
描くのは次の2つに限る。
  1. ある人が、どの部門と何名の接点を持っているか（エゴ図）
  2. どの部門とどの部門が、どれだけ同席したか（ヒートマップ）
"""

from __future__ import annotations

import html
import math
from typing import Any


def _e(v: Any) -> str:
    return html.escape(str(v))


# ---------------------------------------------------------------- ラベルの配置

# 日本語はほぼ全角、英数字は約0.55倍で見積もる
def _text_width(text: str, size: float) -> float:
    w = 0.0
    for ch in text:
        w += size if ord(ch) > 0x2000 else size * 0.55
    return w


def _overlaps(a: tuple, b: tuple, gap: float = 2.0) -> bool:
    return not (
        a[2] + gap < b[0] or b[2] + gap < a[0] or a[3] + gap < b[1] or b[3] + gap < a[1]
    )


def _place_labels(items: list[dict], size: float = 10.5, bounds: tuple | None = None) -> list[dict]:
    """点のラベルを、重ならない位置に置く。

    右・左・上・下の順に空いている場所を探す。どこにも置けないものは諦める。
    重なったラベルは読めないので、出さないほうがよい。

    items: {"x","y","r","text"} / 戻り値に "lx","ly","anchor","shown" を足す
    """
    placed: list[tuple] = [
        (it["x"] - it["r"], it["y"] - it["r"], it["x"] + it["r"], it["y"] + it["r"])
        for it in items
    ]
    out = []
    for it in sorted(items, key=lambda i: (-i.get("priority", 0), i["x"])):
        w = _text_width(it["text"], size)
        r = it["r"]
        d = r + 5
        cands = [
            (it["x"] + d, it["y"] + size * 0.35, "start"),
            (it["x"] - d, it["y"] + size * 0.35, "end"),
            (it["x"], it["y"] - r - 6, "middle"),
            (it["x"], it["y"] + r + size + 2, "middle"),
            (it["x"] + d * 0.7, it["y"] - r - 6, "start"),
            (it["x"] - d * 0.7, it["y"] - r - 6, "end"),
            (it["x"] + d * 0.7, it["y"] + r + size + 2, "start"),
            (it["x"] - d * 0.7, it["y"] + r + size + 2, "end"),
            (it["x"] + d, it["y"] - size * 1.1, "start"),
            (it["x"] - d, it["y"] - size * 1.1, "end"),
            (it["x"] + d, it["y"] + size * 1.6, "start"),
            (it["x"] - d, it["y"] + size * 1.6, "end"),
        ]
        chosen = None
        for lx, ly, anchor in cands:
            x0 = lx if anchor == "start" else (lx - w if anchor == "end" else lx - w / 2)
            box = (x0, ly - size, x0 + w, ly + 2)
            if bounds and (box[0] < bounds[0] or box[2] > bounds[2]
                           or box[1] < bounds[1] or box[3] > bounds[3]):
                continue
            if any(_overlaps(box, q) for q in placed):
                continue
            chosen = (lx, ly, anchor, box)
            break
        rec = dict(it)
        if chosen:
            placed.append(chosen[3])
            rec.update(lx=chosen[0], ly=chosen[1], anchor=chosen[2], shown=True)
        else:
            rec.update(lx=it["x"] + r + 5, ly=it["y"] + size * 0.35, anchor="start", shown=False)
        out.append(rec)
    return out


def _nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    """目盛りの値を決める。きりのよい間隔を選ぶ。"""
    if hi <= lo:
        return [lo]
    raw = (hi - lo) / max(count - 1, 1)
    mag = 10 ** math.floor(math.log10(raw)) if raw > 0 else 1
    step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw), default=raw)
    start = math.ceil(lo / step) * step
    out, v = [], start
    while v <= hi + step * 1e-9:
        out.append(round(v, 10))
        v += step
    return out


def _fmt(v: float) -> str:
    if v == int(v):
        return str(int(v))
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _fmt_tick(v: float) -> str:
    """目盛りの数。0.0001 のような小さい値を丸めずに出す。"""
    if v == int(v):
        return str(int(v))
    return f"{v:.10f}".rstrip("0").rstrip(".")


def heatmap(labels: list[str], sizes: list[int], matrix: list[list[float]], cell: int = 46) -> str:
    """部門間の往来を行列で示す。断絶が空白として一目で分かる。

    色は1色だけにする。対角（部門の中）と対角以外（部門と部門の間）は
    桁が違うので、2色で塗ると同じ尺度に見えてしまう。
    対角は灰色の下地に置いて、色の濃さは対角以外だけで比べさせる。
    """
    n = len(labels)
    if n < 2:
        return ""
    pad_l, pad_t, leg = 132, 108, 54
    w = pad_l + cell * n + 16
    h = pad_t + cell * n + 16 + leg
    flat = [v for i, row in enumerate(matrix) for j, v in enumerate(row) if i != j]
    vmax = max(flat) if flat else 1.0

    def alpha(v: float) -> float:
        r = min(max(v / vmax if vmax else 0, 0), 1)
        return 0.08 + 0.72 * (r ** 0.6)

    s = [
        f"<svg viewBox='0 0 {w} {h}' style='width:100%;height:auto;max-width:{w}px' "
        "role='img' aria-label='部門と部門の間のつながりの量'>",
        "<style>"
        ".hm-l{fill:var(--mut);font-size:11px}.hm-v{font-size:11px;font-weight:600;"
        "font-variant-numeric:tabular-nums}"
        ".hm-g{fill:var(--mut);font-size:10.5px;font-variant-numeric:tabular-nums}"
        ".hm-d{stroke:var(--line);stroke-width:1;fill:none}"
        "</style>",
    ]
    for j, lab in enumerate(labels):
        x = pad_l + cell * j + cell / 2
        s.append(
            f"<text class='hm-l' x='{x}' y='{pad_t - 10}' text-anchor='start' "
            f"transform='rotate(-45 {x} {pad_t - 10})'>{_e(lab)}</text>"
        )
    for i, lab in enumerate(labels):
        y = pad_t + cell * i + cell / 2
        s.append(
            f"<text class='hm-l' x='{pad_l - 10}' y='{y + 4}' text-anchor='end'>"
            f"{_e(lab)} <tspan opacity='.6'>{sizes[i]}名</tspan></text>"
        )
        for j in range(len(labels)):
            v = matrix[i][j]
            x = pad_l + cell * j
            own = i == j
            fill = (
                "color-mix(in srgb, var(--fg) 5%, transparent)" if own
                else f"color-mix(in srgb, var(--accent) {alpha(v) * 100:.0f}%, transparent)"
            )
            s.append(
                f"<rect x='{x + 1}' y='{y - cell / 2 + 1}' width='{cell - 2}' "
                f"height='{cell - 2}' rx='3' fill='{fill}'/>"
            )
            if v == 0 and not own:
                s.append(
                    f"<text class='hm-v' x='{x + cell / 2}' y='{y + 4}' text-anchor='middle' "
                    "fill='var(--crit)'>断絶</text>"
                )
            else:
                s.append(
                    f"<text class='hm-v' x='{x + cell / 2}' y='{y + 4}' text-anchor='middle' "
                    f"fill='var({'--mut' if own else '--fg'})'>{v:.2f}</text>"
                )

    # 凡例。数字がいくつなら濃いのかを、同じ画面の中で確かめられるようにする
    ly = pad_t + cell * n + 30
    steps = 5
    bw = 34
    s.append(f"<text class='hm-g' x='{pad_l}' y='{ly - 8}'>部門と部門の間のつながり</text>")
    for k in range(steps):
        v = vmax * (k + 1) / steps
        x = pad_l + bw * k
        s.append(
            f"<rect x='{x}' y='{ly}' width='{bw - 2}' height='13' rx='2' "
            f"fill='color-mix(in srgb, var(--accent) {alpha(v) * 100:.0f}%, transparent)'/>"
        )
        s.append(
            f"<text class='hm-g' x='{x + (bw - 2) / 2}' y='{ly + 27}' "
            f"text-anchor='middle'>{v:.2f}</text>"
        )
    x2 = pad_l + bw * steps + 18
    s.append(
        f"<rect x='{x2}' y='{ly}' width='{bw - 2}' height='13' rx='2' "
        "fill='color-mix(in srgb, var(--fg) 5%, transparent)'/>"
    )
    s.append(f"<text class='hm-g' x='{x2 + bw + 2}' y='{ly + 11}'>部門の中（別の尺度）</text>")
    s.append(
        f"<text class='hm-v' x='{x2 + 16}' y='{ly + 38}' text-anchor='middle' "
        "fill='var(--crit)'>断絶</text>"
    )
    s.append(
        f"<text class='hm-g' x='{x2 + bw + 2}' y='{ly + 38}'>接点が残らなかった組</text>"
    )
    s.append("</svg>")
    return "".join(s)


def ego(center: str, groups: list[dict], own_group: str = "") -> str:
    """ある人物がどの部門を繋いでいるかの図。

    全体図ではなく1人の周辺だけを描く。「この人がいなくなると何が切れるか」
    という機構が見えることが目的。

    切れる部門（赤）を上に、あとは接点の多い順に並べる。線の太さは接点の人数。
    文字の位置は実測幅で決める。文字数×定数だと、カタカナの長い部門名で
    次の文字と重なる。
    """
    others = [g for g in groups if not g.get("is_own")]
    if not others:
        return ""
    others = sorted(others, key=lambda g: (not g.get("sole_bridge"), -g["contacts"], g["group"]))
    w, rowh = 720, 40
    h = 50 + rowh * len(others)
    cx, cy = 150, h / 2
    xn = cx + 180
    maxc = max(g["contacts"] for g in others) or 1
    s = [
        f"<svg viewBox='0 0 {w} {h}' style='width:100%;height:auto;max-width:{w}px' "
        f"role='img' aria-label='{_e(center)} が繋いでいる先'>",
        "<style>"
        ".eg-n{fill:var(--fg);font-size:12px}.eg-s{fill:var(--mut);font-size:11px}"
        ".eg-c{fill:var(--accent)}.eg-sole{stroke:var(--crit);fill:none}"
        ".eg-ok{stroke:var(--faint);stroke-opacity:.6;fill:none}"
        "</style>",
    ]
    for i, g in enumerate(others):
        y = 32 + rowh * i
        sole = g.get("sole_bridge")
        ratio = g["contacts"] / maxc
        width = 1.5 + 2.5 * ratio
        s.append(
            f"<path class='{'eg-sole' if sole else 'eg-ok'}' "
            f"d='M{cx + 10} {cy:.1f} C {cx + 100} {cy:.1f}, {cx + 100} {y}, {xn - 8} {y}' "
            f"stroke-width='{width:.1f}'/>"
        )
        s.append(
            f"<circle cx='{xn}' cy='{y}' r='{5 + 2 * ratio:.1f}' "
            f"fill='{'var(--crit)' if sole else 'var(--faint)'}'/>"
        )
        name_x = xn + 14
        s.append(
            f"<text class='eg-n' x='{name_x}' y='{y + 4}'"
            f"{' font-weight=\'600\'' if sole else ''}>{_e(g['group'])}</text>"
        )
        note = f"接点{g['contacts']}名"
        if sole:
            note += f" ／ {center} が離れると接点が切れます"
        s.append(
            f"<text class='eg-s' x='{name_x + _text_width(g['group'], 12) + 10:.1f}' y='{y + 4}'>"
            f"{_e(note)}</text>"
        )
    s.append(f"<circle class='eg-c' cx='{cx}' cy='{cy:.1f}' r='9'/>")
    s.append(
        f"<text class='eg-n' x='{cx - 16}' y='{cy - 8:.1f}' text-anchor='end' font-weight='600'>"
        f"{_e(center)}</text>"
    )
    if own_group:
        s.append(
            f"<text class='eg-s' x='{cx - 16}' y='{cy + 9:.1f}' text-anchor='end'>{_e(own_group)}</text>"
        )
    s.append("</svg>")
    return "".join(s)


def _log_ticks(lo: float, hi: float) -> list[float]:
    """対数軸の目盛り。10倍ごとに1本置く。"""
    out, e = [], math.floor(math.log10(lo))
    while 10.0**e <= hi * (1 + 1e-9):
        out.append(10.0**e)
        e += 1
    return out


def _axis(values: list[float], scale: str) -> tuple[float, float, list[float]]:
    """軸の下限・上限と目盛りを決める。

    対数は下限を10の累乗に丸め、上限は実測の最大値に合わせる。上限まで丸めると、
    一番上の点が目盛り1本ぶん内側に入り、縦の広がりが見えなくなる。
    """
    if not values:
        return 0.0, 1.0, [0.0, 1.0]
    hi = max(values)
    if scale == "log":
        lo = 10.0 ** math.floor(math.log10(min(values)))
        hi = max(hi, lo * 10)
        return lo, hi, _log_ticks(lo, hi)
    lo = 0.0
    hi = hi if hi > 0 else 1.0
    return lo, hi, [t for t in _nice_ticks(lo, hi, 6)]


def scatter(
    points: list[dict],
    x_label: str,
    y_label: str,
    note: str = "",
    height: int = 400,
    x_scale: str = "linear",
    y_scale: str = "linear",
    x_unit: str = "",
    y_unit: str = "",
) -> str:
    """2軸の散布図。実際の値で置く。

    軸ごとにスケールを選べる。片方が人数（2〜21名）、もう片方が割合
    （0.02%〜17.6%）のように広がり方が違うとき、両方を同じ目盛りにすると
    一方が1本の線に潰れる。

    点にカーソルを合わせると、その人の数値が出る。
    氏名は重ならない位置にだけ置く。重なったラベルは読めない。
    """
    if not points:
        return ""
    W, H, P = 680, height, 60
    xlo, xhi, xticks = _axis([p["x"] for p in points], x_scale)
    ylo, yhi, yticks = _axis([p["y"] for p in points], y_scale)

    def frac(v: float, lo: float, hi: float, scale: str) -> float:
        if scale == "log":
            if v <= 0 or hi <= lo:
                return 0.0
            return (math.log10(v) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
        return 0.0 if hi <= lo else (v - lo) / (hi - lo)

    def sx(v: float) -> float:
        return P + frac(v, xlo, xhi, x_scale) * (W - P * 2)

    def sy(v: float) -> float:
        return H - P - frac(v, ylo, yhi, y_scale) * (H - P * 2)

    s = [
        f"<svg data-chart='scatter' viewBox='0 0 {W} {H}' style='width:100%;height:auto' "
        f"role='img' aria-label='{_e(x_label)}と{_e(y_label)}'>",
        "<style>.sc-ax{stroke:var(--line)}"
        ".sc-gr{stroke:var(--line2)}"
        ".sc-l{fill:var(--mut);font-size:11px}.sc-tk{fill:var(--mut);font-size:9.5px}"
        ".sc-p{fill:var(--accent);opacity:.6;cursor:pointer;transition:r .1s,opacity .1s}"
        ".sc-h{fill:var(--warn);opacity:.95;cursor:pointer}"
        ".sc-t{fill:var(--fg);font-size:10.5px;pointer-events:none}</style>",
    ]
    for t in yticks:
        s.append(f"<line class='sc-gr' x1='{P}' y1='{sy(t):.1f}' x2='{W - P}' y2='{sy(t):.1f}'/>")
        s.append(
            f"<text class='sc-tk' x='{P - 7}' y='{sy(t) + 3.5:.1f}' text-anchor='end'>"
            f"{_fmt_tick(t)}{_e(y_unit)}</text>"
        )
    for t in xticks:
        s.append(f"<line class='sc-gr' x1='{sx(t):.1f}' y1='{P}' x2='{sx(t):.1f}' y2='{H - P}'/>")
        s.append(
            f"<text class='sc-tk' x='{sx(t):.1f}' y='{H - P + 15}' text-anchor='middle'>"
            f"{_fmt_tick(t)}{_e(x_unit)}</text>"
        )
    s.append(f"<line class='sc-ax' x1='{P}' y1='{H - P}' x2='{W - P}' y2='{H - P}'/>")
    s.append(f"<line class='sc-ax' x1='{P}' y1='{P}' x2='{P}' y2='{H - P}'/>")
    s.append(
        f"<text class='sc-l' x='{W - P}' y='{H - P + 34}' text-anchor='end'>"
        f"{_e(x_label)} →</text>"
    )
    s.append(f"<text class='sc-l' x='{P - 10}' y='{P - 16}'>↑ {_e(y_label)}</text>")
    if note:
        s.append(f"<text class='sc-tk' x='{W - P}' y='{P - 16}' text-anchor='end'>{_e(note)}</text>")

    labels = []
    for i, pt in enumerate(points):
        x, y = sx(pt["x"]), sy(pt["y"])
        hot = bool(pt.get("highlight"))
        r = 5.5 if hot else 3.6
        s.append(
            f"<circle class='{'sc-h' if hot else 'sc-p'}' cx='{x:.1f}' cy='{y:.1f}' r='{r}' "
            f"data-tip=\"{_e(pt.get('tip') or pt.get('label') or '')}\" data-i='{i}'/>"
        )
        if hot and pt.get("label"):
            labels.append({"x": x, "y": y, "r": r, "text": pt["label"], "priority": 1})
    for lab in _place_labels(labels, bounds=(4, 4, W - 4, H - 4)):
        if not lab["shown"]:
            continue
        s.append(
            f"<text class='sc-t' x='{lab['lx']:.1f}' y='{lab['ly']:.1f}' "
            f"text-anchor='{lab['anchor']}'>{_e(lab['text'])}</text>"
        )
    s.append("</svg>")
    return "".join(s)


def strip(values: list[float], marks: list[dict], lower_better: bool = False,
          points: list[dict] | None = None) -> str:
    """分布の帯。個人がその部門の中でどのあたりにいるかを示す。

    値が近い人は縦にずらして重ならないようにする（蜂群図）。
    重ねて描くと、同じ位置に何名いるかが分からない。
    """
    if len(values) < 2:
        return ""
    W, P = 620, 26
    lo, hi = min(values), max(values)
    rng = (hi - lo) or 1.0
    pos = lambda v: P + (v - lo) / rng * (W - P * 2)  # noqa: E731

    rows = points or [{"value": v, "label": "", "tip": ""} for v in values]
    R = 4.2
    lanes: list[list[float]] = []
    placed = []
    for rec in sorted(rows, key=lambda r: r["value"]):
        x = pos(rec["value"])
        for li, lane in enumerate(lanes):
            if not lane or x - lane[-1] >= R * 2 + 0.6:
                lane.append(x)
                placed.append((rec, x, li))
                break
        else:
            lanes.append([x])
            placed.append((rec, x, len(lanes) - 1))

    base = 30
    H = base + len(lanes) * (R * 2 + 1.4) + 44
    axis = base - 10
    s = [
        f"<svg data-chart='strip' viewBox='0 0 {W} {H:.0f}' style='width:100%;height:auto'>",
        "<style>.st-b{fill:var(--line2)}"
        ".st-p{fill:var(--mut);opacity:.55;cursor:pointer}"
        ".st-m{fill:var(--accent);opacity:.95;cursor:pointer}"
        ".st-t{fill:var(--fg);font-size:10px;pointer-events:none}"
        ".st-l{fill:var(--mut);font-size:9.5px}.st-tk{fill:var(--mut);font-size:9px}"
        ".st-ax{stroke:var(--line)}</style>",
        f"<line class='st-ax' x1='{P}' y1='{axis}' x2='{W - P}' y2='{axis}'/>",
    ]
    for t in _nice_ticks(lo, hi, 6):
        x = pos(t)
        s.append(f"<line class='st-ax' x1='{x:.1f}' y1='{axis}' x2='{x:.1f}' y2='{axis - 4}'/>")
        s.append(f"<text class='st-tk' x='{x:.1f}' y='{axis - 8}' text-anchor='middle'>{_fmt(t)}</text>")

    marked = {m["label"] for m in marks}
    labels = []
    for rec, x, li in placed:
        y = base + li * (R * 2 + 1.4) + R
        hot = rec.get("label") in marked and rec.get("label")
        s.append(
            f"<circle class='{'st-m' if hot else 'st-p'}' cx='{x:.1f}' cy='{y:.1f}' "
            f"r='{R if hot else R - 1.4:.1f}' data-tip=\"{_e(rec.get('tip') or rec.get('label') or '')}\"/>"
        )
        if hot:
            labels.append({"x": x, "y": y, "r": R, "text": rec["label"], "priority": 1})
    for lab in _place_labels(labels, size=10, bounds=(2, 2, W - 2, H - 34)):
        if not lab["shown"]:
            continue
        s.append(
            f"<text class='st-t' x='{lab['lx']:.1f}' y='{lab['ly']:.1f}' "
            f"text-anchor='{lab['anchor']}'>{_e(lab['text'])}</text>"
        )

    left, right = (
        ("行き来のない複数の集団に顔を出している", "いつも同じ顔ぶれとつながっている")
        if lower_better
        else ("低", "高")
    )
    s.append(f"<text class='st-l' x='{P}' y='{H - 10:.0f}'>← {_e(left)}</text>")
    s.append(f"<text class='st-l' x='{W - P}' y='{H - 10:.0f}' text-anchor='end'>{_e(right)} →</text>")
    s.append("</svg>")
    return "".join(s)


def quadrant(teams: list[dict]) -> str:
    """内部密度 × 外部範囲の4象限。同じ2変数を逆向きに読むことを示す。"""
    if not teams:
        return ""
    xs = [t["external_range"] for t in teams]
    ys = [t["internal_density"] for t in teams]
    mx, my = teams[0]["median_external_range"], teams[0]["median_internal_density"]
    x0, x1 = 0, max(xs) * 1.18 or 1
    y0, y1 = 0, max(ys) * 1.18 or 1
    W, H, P = 680, 420, 56
    sx = lambda v: P + (v - x0) / (x1 - x0) * (W - P * 2)  # noqa: E731
    sy = lambda v: H - P - (v - y0) / (y1 - y0) * (H - P * 2)  # noqa: E731
    s = [
        f"<svg data-chart='quadrant' viewBox='0 0 {W} {H}' style='width:100%;height:auto' "
        "role='img' aria-label='部門の内部密度と外部範囲'>",
        "<style>.q-ax{stroke:var(--line)}.q-md{stroke:var(--mut);stroke-dasharray:4 4;opacity:.5}"
        ".q-l{fill:var(--mut);font-size:11px}.q-z{font-size:10.5px;opacity:.9}"
        ".q-tk{fill:var(--mut);font-size:9.5px}"
        ".q-p{fill:var(--accent);opacity:.55;cursor:pointer}"
        ".q-t{fill:var(--fg);font-size:10.5px;pointer-events:none}</style>",
    ]
    zones = [
        (sx(mx), P, W - P, sy(my), "効率型", "納期を守る仕事向き", "--ok"),
        (sx(mx), sy(my), W - P, H - P, "イノベーション型", "新規探索の仕事向き", "--accent"),
        (P, P, sx(mx), sy(my), "閉鎖型", "部門外とのつながりが少ない", "--warn"),
        (P, sy(my), sx(mx), H - P, "拡散型", "共同で作業しているか確認", "--mut"),
    ]
    for xa, ya, xb, yb, name, sub, col in zones:
        s.append(
            f"<rect x='{xa}' y='{ya}' width='{max(xb - xa, 0)}' height='{max(yb - ya, 0)}' "
            f"fill='color-mix(in srgb, var({col}) 7%, transparent)'/>"
        )
        s.append(
            f"<text class='q-z' x='{(xa + xb) / 2}' y='{ya + 16}' text-anchor='middle' "
            f"fill='var({col})'>{_e(name)}</text>"
        )
        s.append(
            f"<text class='q-z' x='{(xa + xb) / 2}' y='{ya + 29}' text-anchor='middle' "
            f"fill='var(--mut)' opacity='.8'>{_e(sub)}</text>"
        )
    for t in _nice_ticks(0, x1, 6):
        s.append(f"<text class='q-tk' x='{sx(t):.1f}' y='{H - P + 15}' text-anchor='middle'>{_fmt(t)}</text>")
    for t in _nice_ticks(0, y1, 6):
        s.append(f"<text class='q-tk' x='{P - 7}' y='{sy(t) + 3.5:.1f}' text-anchor='end'>{_fmt(t)}</text>")
    s.append(f"<line class='q-ax' x1='{P}' y1='{H - P}' x2='{W - P}' y2='{H - P}'/>")
    s.append(f"<line class='q-ax' x1='{P}' y1='{P}' x2='{P}' y2='{H - P}'/>")
    s.append(f"<line class='q-md' x1='{sx(mx):.1f}' y1='{P}' x2='{sx(mx):.1f}' y2='{H - P}'/>")
    s.append(f"<line class='q-md' x1='{P}' y1='{sy(my):.1f}' x2='{W - P}' y2='{sy(my):.1f}'/>")
    s.append(f"<text class='q-l' x='{W - P}' y='{H - P + 34}' text-anchor='end'>部門外の相手が多い →</text>")
    s.append(f"<text class='q-l' x='{P - 10}' y='{P - 18}'>↑ メンバーどうしのつながりが濃い</text>")

    labels = []
    for t in teams:
        cx, cy = sx(t["external_range"]), sy(t["internal_density"])
        r = 4 + math.sqrt(t["size"]) * 1.1
        tip = (
            f"<b>{_e(t['label'])}</b><br>{t['size']}名 ／ {_e(t.get('quadrant_label', ''))}"
            f"<br>内部密度 {t['internal_density']:.1f}"
            f"<br>外部範囲 {t['external_range']:.2f}"
        )
        s.append(
            f"<circle class='q-p' cx='{cx:.1f}' cy='{cy:.1f}' r='{r:.1f}' data-tip=\"{_e(tip)}\"/>"
        )
        labels.append({"x": cx, "y": cy, "r": r, "text": t["label"], "priority": t["size"]})
    for lab in _place_labels(labels, bounds=(4, P - 2, W - 4, H - P + 2)):
        if not lab["shown"]:
            continue
        s.append(
            f"<text class='q-t' x='{lab['lx']:.1f}' y='{lab['ly']:.1f}' "
            f"text-anchor='{lab['anchor']}'>{_e(lab['text'])}</text>"
        )
    s.append("</svg>")
    return "".join(s)


def bar(value: float, maximum: float, color: str = "--accent", width: int = 120) -> str:
    ratio = min(max(value / maximum, 0), 1) if maximum else 0
    return (
        f"<span class='bar' style='--w:{ratio * 100:.1f}%;--c:var({color})' "
        f"aria-hidden='true'></span>"
    )


# 社外をまとめて置く区分の名前。部門名と並べて書かないために使う
EXTERNAL_LABEL = "（社外）"

# 1つの部門に出す人数の上限。これを超えると図が縦に伸びて読み通せない
MAX_PER_GROUP = 12

# 1段に並べる列の上限。これを超えると2段にする。横に並べ続けると右端が切れる
MAX_COLS = 5


def neighborhood(
    center: str,
    center_group: str,
    members: list[dict],
    cut_label: str = "抜けると社内から切り離される相手",
    keep_label: str = "",
) -> str:
    """1人とその周りだけを切り出した関係図。

    **部門ごとに1列**にまとめる。氏名を並べただけでは、どの部門の人なのかを
    1人ずつ読み取ることになる。列にすると、この人がどの部門と何名ずつ
    つながっているかが先に目に入る。

    赤い丸は、社内の他の人とつながる道がこの人しかない相手。
    灰色の丸は、この人を通さなくてもつながる相手。

    中心から相手1人ずつへ線を引くと、列をまたいだ線が氏名の上を横切って読めなくなる。
    中心から引くのは**列（部門）まで**にして、相手がこの人とつながっていることは
    その列に入っていることで表す。

    列が6つ以上あるときは2段にする。下の段への線は、上の段の列と列の隙間を
    まっすぐ通す。氏名は隙間にかからない幅で切る。
    """
    cols = _by_group(members)
    if not cols:
        return ""
    n = len(cols)
    n1 = n if n <= MAX_COLS else math.ceil(n / 2)
    band1, band2 = cols[:n1], cols[n1:]
    n2 = len(band2)
    w = 720
    span_cols = n1 + (1 if n2 == n1 else 0)
    colw = min(200.0, (w - 32) / span_cols)
    x0 = (w - colw * span_cols) / 2
    row = 28
    # 列の見出しの上に 60px 空ける。中心からの線はここで扇形に広がり、見出しの文字に
    # かからない。見出し（部門名・人数）はその下、縦の線はさらに下から始める
    top1 = 120
    fan = 60
    cx, cy = w / 2, 28

    def band_bottom(band: list[dict], top: float) -> float:
        last = top + row * max(max(len(c["shown"]) for c in band) - 1, 0)
        return last + (22 if any(c["omitted"] for c in band) else 0)

    bottom1 = band_bottom(band1, top1)
    top2 = bottom1 + 100 if band2 else None
    bottom = band_bottom(band2, top2) if band2 else bottom1
    h = bottom + 50

    s = [
        f"<svg viewBox='0 0 {w} {h:.0f}' style='width:100%;height:auto;max-width:{w}px' "
        f"role='img' aria-label='{_e(center)} の周りの関係'>",
        "<style>"
        ".nb-e{stroke:var(--faint);stroke-opacity:.55;stroke-width:1.3;fill:none}"
        ".nb-sp{stroke:var(--faint);stroke-opacity:.4;stroke-width:1}"
        ".nb-n{fill:var(--faint)}.nb-x{fill:var(--crit)}"
        ".nb-t{fill:var(--fg);font-size:12px}.nb-s{fill:var(--mut);font-size:11px}"
        ".nb-h{fill:var(--fg);font-size:12px;font-weight:600}"
        "</style>",
    ]

    def column(col: dict, x: float, top: float, avail: float) -> None:
        # 氏名は次の列（または右端）の手前で切る。はみ出すと隣の列や下の段への線に重なる。
        # 社外のドメインは英字で幅が狭いので、文字数ではなく実測幅で切る
        maxw = max(avail - 30, 40)
        last = top + row * max(len(col["shown"]) - 1, 0)
        s.append(f"<path class='nb-sp' d='M{x:.1f} {top - 22:.1f} L{x:.1f} {last:.1f}'/>")
        s.append(
            f"<text class='nb-h' x='{x:.1f}' y='{top - 44:.1f}'>"
            f"{_clip(col['group'], maxw, 12)}</text>"
        )
        s.append(f"<text class='nb-s' x='{x:.1f}' y='{top - 30:.1f}'>{col['total']}名</text>")
        for k, m in enumerate(col["shown"]):
            y = top + row * k
            cut = bool(m.get("cut"))
            s.append(
                f"<circle class='{'nb-x' if cut else 'nb-n'}' cx='{x:.1f}' cy='{y:.1f}' "
                f"r='{5.5 if cut else 4.5}'/>"
            )
            s.append(
                f"<text class='nb-t' x='{x + 12:.1f}' y='{y + 4:.1f}'>"
                f"{_clip(m['label'], maxw, 12)}</text>"
            )
        if col["omitted"]:
            s.append(
                f"<text class='nb-s' x='{x + 12:.1f}' y='{last + 22:.1f}'>"
                f"ほか{col['omitted']}名</text>"
            )

    def fan_path(x: float, end: float) -> str:
        y0 = cy + 10
        return (
            f"M{cx:.1f} {y0:.1f} C{cx:.1f} {y0 + (end - y0) * 0.6:.1f}, "
            f"{x:.1f} {y0 + (end - y0) * 0.4:.1f}, {x:.1f} {end:.1f}"
        )

    for i, col in enumerate(band1):
        x = x0 + colw * i + 9
        s.append(f"<path class='nb-e' d='{fan_path(x, top1 - fan)}'/>")
        # 右端の列は、右に線が通らなければ右端まで使ってよい
        avail = (w - 16 - x) if (i == n1 - 1 and n2 < n1) else colw
        column(col, x, top1, avail)
    for j, col in enumerate(band2):
        # 上の段の列の境目を通す。氏名は境目の手前で切ってある
        x = x0 + colw * (j + 1)
        s.append(
            f"<path class='nb-e' d='{fan_path(x, top1 - fan)} L{x:.1f} {top2 - fan:.1f}'/>"
        )
        avail = (w - 16 - x) if j == n2 - 1 else colw
        column(col, x, top2, avail)

    s.append(f"<circle cx='{cx:.1f}' cy='{cy:.1f}' r='10' fill='var(--accent)'/>")
    s.append(
        f"<text class='nb-t' x='{cx - 16:.1f}' y='{cy + 4:.1f}' text-anchor='end' "
        f"font-weight='600'>{_e(center)}</text>"
    )
    if center_group:
        s.append(f"<text class='nb-s' x='{cx + 16:.1f}' y='{cy + 4:.1f}'>{_e(center_group)}</text>")
    # 凡例。赤と灰色の意味を図の中に書く
    ly = h - 12
    lx = 16.0
    s.append(f"<circle class='nb-x' cx='{lx:.1f}' cy='{ly - 4}' r='5'/>")
    s.append(f"<text class='nb-s' x='{lx + 10:.1f}' y='{ly}'>{_e(cut_label)}</text>")
    if keep_label:
        lx += 10 + _text_width(cut_label, 11) + 24
        s.append(f"<circle class='nb-n' cx='{lx:.1f}' cy='{ly - 4}' r='4.5'/>")
        s.append(f"<text class='nb-s' x='{lx + 10:.1f}' y='{ly}'>{_e(keep_label)}</text>")
    s.append("</svg>")
    return "".join(s)


def _by_group(members: list[dict]) -> list[dict]:
    """部門ごとにまとめる。人数の多い部門を先に、社外を末尾に置く。

    社外は部門ではないので、部門名と同じ並びに混ぜない。
    """
    bag: dict[str, list[dict]] = {}
    for m in members:
        bag.setdefault(m.get("group") or "（部門なし）", []).append(m)
    out = []
    for g in sorted(bag, key=lambda g: (g == EXTERNAL_LABEL, -len(bag[g]), g)):
        # 切り離される相手を列の上に出す。同じ部門の中で見比べられるようにする
        ms = sorted(bag[g], key=lambda m: (not m.get("cut"), m["label"]))
        out.append({
            "group": g,
            "total": len(ms),
            "shown": ms[:MAX_PER_GROUP],
            "omitted": max(len(ms) - MAX_PER_GROUP, 0),
        })
    return out


def _clip(text: str, maxw: float, size: float) -> str:
    """列の幅に収めた text 要素の中身を返す。はみ出した氏名は隣の列と重なって読めなくなる。

    切ったときは <title> に全文を入れる。マウスを載せると全文が出る。
    """
    if _text_width(text, size) <= maxw:
        return _e(text)
    out = text
    while out and _text_width(out + "…", size) > maxw:
        out = out[:-1]
    return f"<title>{_e(text)}</title>{_e(out)}…"
