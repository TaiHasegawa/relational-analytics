"""レポートの共通アセット（CSS / JavaScript）。外部ライブラリを使わない。"""

from __future__ import annotations

CSS = r"""
/* ── 設計の約束 ────────────────────────────────
   1. 補足は「塗りのブロック」で示す。左の縦線は使わない
   2. 色は彩度を落とす。見出しに色をつけない
   3. 影は、実際に重なるもの（吹き出し）だけに使う
   4. 角丸は 4px。大きく丸めない
   5. 区切りは余白と1pxの薄い罫線で出す
   6. 操作の反応は背景色の変化だけ。浮かせない・動かさない
   ──────────────────────────────────────── */
:root{
 --bg:#fff; --panel:#fff; --panel2:#f7f6f3;
 --fg:#37352f; --mut:#787774; --faint:#9b9a97;
 --line:rgba(55,53,47,.09); --line2:rgba(55,53,47,.055);
 --hover:rgba(55,53,47,.03); --sel:rgba(55,53,47,.06);

 /* 文字につける色。彩度を落とした1段階だけ使う */
 --ok:#448361; --watch:#cb912f; --warn:#d9730d; --crit:#d44c47; --accent:#337ea9;

 /* 塗りのブロックの地色 */
 --fill-gray:#f1f1ef; --fill-brown:#f4eeee; --fill-orange:#fbecdd;
 --fill-yellow:#fbf3db; --fill-green:#edf3ec; --fill-blue:#e7f3f8;
 --fill-purple:#f6f3f9; --fill-red:#fdebec;

 --d1:#337ea9; --d2:#d9730d; --d3:#448361; --d4:#9065b0;
 --d5:#c14c8a; --d6:#9f6b53; --d7:#cb912f; --d8:#787774;

 --r:4px;
 --shadow:0 0 0 1px rgba(15,15,15,.05),0 3px 6px rgba(15,15,15,.1),0 9px 24px rgba(15,15,15,.2);
 /* 明るい配色に固定する。指定しないと入力欄やスライダーに OS のダーク配色が当たる */
 color-scheme:light;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth;font-size:17px}
body{margin:0;background:var(--bg);color:var(--fg);line-height:1.55;
 font-family:ui-sans-serif,-apple-system,system-ui,"Segoe UI",
   "Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif;
 font-feature-settings:"palt" 1;font-size:1rem}

/* ── ナビゲーション ── */
.topbar{position:sticky;top:0;z-index:40;background:rgba(255,255,255,.88);
 backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.topbar .inner{max-width:1040px;margin:0 auto;padding:9px 56px;display:flex;
 align-items:center;gap:18px;flex-wrap:wrap}
.brand{font-weight:600;font-size:0.927rem;white-space:nowrap}
.brand small{display:block;font-weight:400;font-size:0.763rem;color:var(--mut)}
.nav{display:flex;gap:1px;flex-wrap:wrap;margin-left:auto}
.nav a{color:var(--mut);text-decoration:none;font-size:0.869rem;padding:4px 9px;
 border-radius:var(--r);white-space:nowrap;transition:background .08s}
.nav a:hover{background:var(--hover);color:var(--fg)}
.nav a[aria-current]{background:var(--sel);color:var(--fg);font-weight:600}

.wrap{max-width:1040px;margin:0 auto;padding:42px 56px 140px}
.wrap.wide{max-width:none;padding:0}

h1{font-size:2rem;line-height:1.2;margin:0 0 2px;font-weight:700;letter-spacing:-.018em}
h2{font-size:1.32rem;line-height:1.3;margin:38px 0 2px;font-weight:600;letter-spacing:-.01em;
 display:flex;align-items:baseline;gap:9px;flex-wrap:wrap}
h2 .n{font-weight:600}
h2 .q{font-size:0.869rem;color:var(--mut);font-weight:400}
h3{font-size:1.02rem;margin:26px 0 2px;color:var(--fg);font-weight:600;letter-spacing:-.005em}
h4{font-weight:600}
p{margin:.35em 0}
.lede{color:var(--mut);font-size:0.954rem;margin:2px 0 18px;max-width:72ch;line-height:1.65}
.sub{color:var(--mut);font-size:0.869rem}
a{color:inherit;text-decoration:underline;text-decoration-color:var(--line);
 text-underline-offset:2px}
a:hover{text-decoration-color:var(--faint)}


/* ── カード（塗りのブロック） ── */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(186px,1fr));gap:1px;margin:20px 0;
 background:var(--line);border:1px solid var(--line);border-radius:var(--r);overflow:hidden}
.card{background:var(--panel);padding:13px 15px;text-decoration:none;color:inherit;display:block;
 transition:background .08s}
a.card:hover{background:var(--hover)}
.card .k{font-size:0.779rem;color:var(--mut);line-height:1.5}
.card .v{font-size:1.5rem;font-weight:600;font-variant-numeric:tabular-nums;line-height:1.3;
 letter-spacing:-.02em}
.card .n{font-size:0.806rem;color:var(--faint);line-height:1.5}
.card.crit .v{color:var(--crit)}
.card.warn .v{color:var(--warn)}

.panel{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);
 padding:16px 18px;margin:16px 0}
.panel.flat{background:var(--panel2);border-color:transparent}

/* ── 表（横罫線だけ・縞なし） ── */
.tablewrap{border:1px solid var(--line);border-radius:var(--r);overflow:hidden;margin:16px 0}
.tablewrap .scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;font-size:0.906rem}
th,td{text-align:left;padding:8px 13px;border-bottom:1px solid var(--line2);vertical-align:top}
thead th{position:sticky;top:0;background:var(--panel2);color:var(--mut);font-weight:500;
 font-size:0.806rem;white-space:nowrap;z-index:2;border-bottom:1px solid var(--line)}
th.sortable{cursor:pointer;user-select:none}
th.sortable:hover{color:var(--fg)}
th.sortable::after{content:"↕";opacity:.3;margin-left:5px;font-size:.9em}
th[data-dir="asc"]::after{content:"↑";opacity:.9}
th[data-dir="desc"]::after{content:"↓";opacity:.9}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover{background:var(--hover)}
tbody tr.hidden{display:none}

.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:9px 13px;
 border-bottom:1px solid var(--line);background:var(--panel2)}
input[type=search],input[type=text],select{font:inherit;font-size:0.869rem;padding:4px 8px;
 border:1px solid var(--line);border-radius:var(--r);background:var(--panel);color:var(--fg)}
input[type=search]:focus,select:focus{outline:2px solid color-mix(in srgb,var(--accent) 45%,transparent);
 outline-offset:-1px}
input[type=search]{min-width:170px}
.count{font-size:0.827rem;color:var(--mut);margin-left:auto}

/* ── 小さな札 ── */
.tag{display:inline-block;padding:1px 7px;border-radius:3px;font-size:0.763rem;
 font-weight:500;white-space:nowrap}
.ok{background:var(--fill-green);color:var(--ok)}
.watch{background:var(--fill-yellow);color:var(--watch)}
.warning{background:var(--fill-orange);color:var(--warn)}
.critical{background:var(--fill-red);color:var(--crit)}

/* ── 塗りのブロック（補足・注意） ── */
/* 記号は絶対配置にする。flex にすると、本文中の <b> が1つずつ別の列になって
   「この割合は部門の人数に左右されます。」が縦に潰れる */
.note{position:relative;background:var(--fill-gray);
 border-radius:var(--r);padding:14px 16px 14px 44px;margin:16px 0;font-size:0.901rem;
 color:var(--fg);line-height:1.75;max-width:none}
.note::before{content:"💬";position:absolute;left:16px;top:14px;
 font-size:1.02em;line-height:1.75}
.note b{font-weight:600}
.note>ul{margin:5px 0 0;padding-left:1.25em}
.note>ul>li{margin:.18em 0}
.note.limit{background:var(--fill-yellow)}
.note.limit::before{content:"⚠️"}

ul{margin:.3em 0;padding-left:1.5em}
li{margin:.2em 0}
.kv{display:grid;grid-template-columns:auto 1fr;gap:2px 18px;font-size:0.896rem;margin:10px 0}
.kv dt{color:var(--mut);white-space:nowrap}
.kv dd{margin:0;font-variant-numeric:tabular-nums}
.bar{display:inline-block;width:84px;height:6px;border-radius:3px;vertical-align:middle;
 background:var(--line);position:relative;overflow:hidden;margin-right:7px}
.bar::after{content:"";position:absolute;inset:0 auto 0 0;width:var(--w);background:var(--c)}

details{margin:10px 0}
details>summary{cursor:pointer;font-size:0.901rem;color:var(--mut);font-weight:500;
 list-style:none;padding:4px 0}
details>summary:hover{color:var(--fg)}
details>summary::-webkit-details-marker{display:none}
details>summary::before{content:"▸ ";display:inline-block}
details[open]>summary::before{content:"▾ "}

code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.86em;
 background:var(--fill-gray);color:#eb5757;padding:.15em .35em;border-radius:3px}

.person{border:1px solid var(--line);border-radius:var(--r);background:var(--panel);
 padding:18px 20px;margin:14px 0}
.person h4{margin:0 0 2px;font-size:1.02rem;font-weight:600}
.person .role{font-size:0.853rem;color:var(--mut)}
/* 1人分の枠は開閉できる。見出し行を押すと開く。ホバーは背景色の変化だけ */
details.person{padding:0}
details.person>summary{display:flex;align-items:baseline;gap:10px;padding:14px 20px;
 font-size:inherit;color:var(--fg);font-weight:600;border-radius:var(--r)}
details.person>summary:hover{background:var(--hover);color:var(--fg)}
details.person>summary::before{content:"▸";color:var(--mut);font-size:.8em;width:1em}
details.person[open]>summary::before{content:"▾"}
details.person>summary h4{margin:0;display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
details.person>summary .role{font-weight:400}
details.person>.pbody{padding:2px 20px 18px}

/* ── 打ち手の枠 ── */
.actions{margin:16px 0 4px;padding:15px 17px;border-radius:var(--r);background:var(--fill-blue)}
.actions h3{margin:0 0 4px;font-size:0.827rem;color:var(--mut);font-weight:600;
 letter-spacing:.02em}
.actions h3::before{content:"📍 "}
.actions h3+p.prob{margin:0 0 14px;font-size:0.906rem;line-height:1.7}
.actions .prob b{font-variant-numeric:tabular-nums;font-weight:600}
.actions h3~h3{margin-top:2px}
.actions h3~h3::before{content:"✅ "}
.actions ul{margin:0;font-size:0.927rem}
.sim{margin-top:13px;padding-top:12px;border-top:1px solid rgba(55,53,47,.1)}
.sim .simhead{margin:0 0 4px;font-size:0.89rem}
.roletag{display:inline-block;padding:1px 7px;margin:1px 3px 1px 0;border-radius:3px;
 font-size:0.763rem;font-weight:500;text-decoration:none;
 background:var(--fill-blue);color:var(--accent)}
.roletag:hover{background:#d3e9f3}
.srcline{font-size:0.837rem;color:var(--mut);margin:24px 0 4px;padding-top:12px;
 border-top:1px solid var(--line2)}
ul.citelist{margin:6px 0 0;padding-left:18px;font-size:0.885rem;line-height:1.7}
ul.citelist b{font-weight:600}
dl.cite{margin:12px 0 0;padding:14px 16px;border-radius:var(--r);background:var(--fill-gray);
 font-size:0.869rem;line-height:1.7}
dl.cite dt{font-weight:600;margin-top:13px}
dl.cite dt:first-child{margin-top:0}
dl.cite dd{margin:1px 0 0 0}
dl.cite dd .sub{display:block;color:var(--mut)}
dl.cite dd .took{display:block;margin-top:2px;color:var(--mut)}

/* 吹き出しだけは浮かせる。実際に他の要素に重なるため */
.ctip{position:fixed;z-index:60;pointer-events:none;max-width:280px;
 background:var(--panel);border-radius:var(--r);box-shadow:var(--shadow);
 padding:9px 12px;font-size:0.827rem;line-height:1.55}
.ctip b{font-size:0.89rem;font-weight:600}
svg[data-chart]{overflow:visible}
svg[data-chart].hot [data-tip]{opacity:.18}
svg[data-chart].hot [data-tip].on{opacity:1}
svg[data-chart].hot text{opacity:.3}
svg[data-chart] [data-tip].on{stroke:var(--fg);stroke-width:1.5}

.anas{display:grid;grid-template-columns:repeat(auto-fit,minmax(268px,1fr));gap:1px;margin:16px 0;
 background:var(--line);border:1px solid var(--line);border-radius:var(--r);overflow:hidden}
.ana{display:block;padding:15px 18px 16px;background:var(--panel);text-decoration:none;color:inherit;
 transition:background .08s}
.ana:hover{background:var(--hover)}
.ana .aq{font-size:1.08rem;font-weight:600;line-height:1.45;margin-bottom:6px}
.ana .aw{font-size:0.837rem;color:var(--mut);line-height:1.6;margin-bottom:11px}
.ana .ar{padding-top:11px;border-top:1px solid var(--line2)}
/* 結果の1行目は全部を太くしない。固有名詞と数値だけを太くして、読む順を作る */
.ana .rt{margin:0;font-size:0.97rem;line-height:1.62;color:var(--fg)}
.ana .rd{margin:6px 0 0;font-size:0.85rem;color:var(--mut);line-height:1.78}
.ana .rt b{font-weight:700}
/* 灰色の説明が続くと見るところが分からない。固有名詞と数値だけ本文の色に戻す */
.ana .rd b,.ana .an b{color:var(--fg);font-weight:600}
.ana .an{font-size:0.82rem;color:var(--faint);margin-top:11px}

/* ── この分析について ── */
dl.about{display:grid;grid-template-columns:auto 1fr;gap:1px;margin:14px 0 4px;padding:0;
 background:var(--line);border:1px solid var(--line);border-radius:var(--r);overflow:hidden}
dl.about dt{background:var(--panel2);padding:11px 15px;font-size:0.848rem;font-weight:600;
 color:var(--mut);white-space:nowrap}
dl.about dd{background:var(--panel);padding:11px 15px;margin:0;font-size:0.901rem;line-height:1.7}
@media (max-width:620px){
 dl.about{grid-template-columns:1fr}
 dl.about dt{padding-bottom:3px}
 dl.about dd{padding-top:3px}
}

.sepgrp{border-radius:var(--r);padding:12px 14px;margin:8px 0;background:var(--fill-gray)}
.seph{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.seph b{font-size:0.89rem;font-weight:600}
.seph>span:first-of-type{font-variant-numeric:tabular-nums;font-weight:600;color:var(--crit)}
.sepm{display:flex;flex-wrap:wrap;gap:4px}
.sepm .chip{display:inline-flex;align-items:baseline;gap:5px;font-size:0.848rem;
 padding:2px 8px;border-radius:3px;background:var(--panel)}
.sepm .chip i{font-style:normal;font-size:0.763rem;color:var(--mut)}
.sepm .chip.more{color:var(--mut)}
.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:0.827rem;color:var(--mut);margin:8px 0}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:4px;
 vertical-align:-1px}

footer{margin-top:60px;padding-top:20px;border-top:1px solid var(--line);
 font-size:0.848rem;color:var(--mut);line-height:1.7}
footer b{color:var(--fg);font-weight:600}

@media (max-width:720px){
 .topbar .inner{padding:9px 20px}
 .wrap{padding:28px 20px 90px}
 h1{font-size:1.6rem}
}
"""


APP_JS = r"""
// 表の並べ替えと絞り込み。外部ライブラリを使わない。
// 表のリンクから個人の枠へ飛んだとき、閉じていれば開く
(function () {
  function openTarget() {
    var id = location.hash.slice(1);
    var el = id && document.getElementById(id);
    if (!el) return;
    var d = el.closest('details');
    if (d && !d.open) { d.open = true; el.scrollIntoView(); }
  }
  window.addEventListener('hashchange', openTarget);
  openTarget();
})();

(function () {
  function textOf(td) {
    var v = td.getAttribute('data-v');
    if (v !== null) return v;
    return td.textContent.trim();
  }
  function cmp(a, b, dir) {
    var na = parseFloat(a.replace(/[,%]/g, '')), nb = parseFloat(b.replace(/[,%]/g, ''));
    var both = !isNaN(na) && !isNaN(nb);
    var r = both ? na - nb : a.localeCompare(b, 'ja');
    return dir === 'asc' ? r : -r;
  }
  document.querySelectorAll('table[data-sortable]').forEach(function (table) {
    var tbody = table.tBodies[0];
    table.querySelectorAll('thead th').forEach(function (th, i) {
      if (th.hasAttribute('data-nosort')) return;
      th.classList.add('sortable');
      th.addEventListener('click', function () {
        var dir = th.getAttribute('data-dir') === 'asc' ? 'desc' : 'asc';
        table.querySelectorAll('thead th').forEach(function (o) { o.removeAttribute('data-dir'); });
        th.setAttribute('data-dir', dir);
        var rows = Array.prototype.slice.call(tbody.rows);
        rows.sort(function (ra, rb) { return cmp(textOf(ra.cells[i]), textOf(rb.cells[i]), dir); });
        rows.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  });

  document.querySelectorAll('[data-filter-for]').forEach(function (input) {
    var table = document.getElementById(input.getAttribute('data-filter-for'));
    if (!table) return;
    var counter = document.querySelector('[data-count-for="' + table.id + '"]');
    function apply() {
      var q = input.value.trim().toLowerCase();
      var shown = 0, rows = table.tBodies[0].rows;
      for (var i = 0; i < rows.length; i++) {
        var hit = !q || rows[i].textContent.toLowerCase().indexOf(q) >= 0;
        rows[i].classList.toggle('hidden', !hit);
        if (hit) shown++;
      }
      if (counter) counter.textContent = shown + ' / ' + rows.length + ' 件';
    }
    input.addEventListener('input', apply);
    apply();
  });

  document.querySelectorAll('[data-select-for]').forEach(function (sel) {
    var table = document.getElementById(sel.getAttribute('data-select-for'));
    if (!table) return;
    var key = sel.getAttribute('data-select-key');
    var counter = document.querySelector('[data-count-for="' + table.id + '"]');
    sel.addEventListener('change', function () {
      var v = sel.value, shown = 0, rows = table.tBodies[0].rows;
      for (var i = 0; i < rows.length; i++) {
        var hit = !v || rows[i].getAttribute('data-' + key) === v;
        rows[i].classList.toggle('hidden', !hit);
        if (hit) shown++;
      }
      if (counter) counter.textContent = shown + ' / ' + rows.length + ' 件';
    });
  });
})();

// ── 図の点にカーソルを合わせると、その人の数値を出す
(function () {
  var charts = document.querySelectorAll('svg[data-chart]');
  if (!charts.length) return;
  var tip = document.createElement('div');
  tip.className = 'ctip';
  tip.hidden = true;
  document.body.appendChild(tip);

  function move(ev) {
    var x = ev.clientX + 14, y = ev.clientY + 14;
    var r = tip.getBoundingClientRect();
    if (x + r.width > window.innerWidth - 10) x = ev.clientX - r.width - 14;
    if (y + r.height > window.innerHeight - 10) y = ev.clientY - r.height - 14;
    tip.style.left = Math.max(6, x) + 'px';
    tip.style.top = Math.max(6, y) + 'px';
  }

  charts.forEach(function (svg) {
    svg.querySelectorAll('[data-tip]').forEach(function (el) {
      el.addEventListener('mouseenter', function (ev) {
        var t = el.getAttribute('data-tip');
        if (!t) return;
        tip.innerHTML = t;
        tip.hidden = false;
        svg.classList.add('hot');
        el.classList.add('on');
        move(ev);
      });
      el.addEventListener('mousemove', move);
      el.addEventListener('mouseleave', function () {
        tip.hidden = true;
        svg.classList.remove('hot');
        el.classList.remove('on');
      });
    });
  });
})();
"""


GRAPH_CSS = r"""
.graphpage{display:grid;grid-template-columns:1fr 300px;height:calc(100vh - 51px)}
.gpanel{border-right:1px solid var(--line);background:var(--panel);overflow-y:auto;
 padding:16px 16px 40px}
.gpanel.right{border-right:none;border-left:1px solid var(--line)}
.gstage{position:relative;background:var(--bg);overflow:hidden}
.gstage svg{width:100%;height:100%;display:block;cursor:grab}
.gnode{transition:none}
.gstage svg.dragging{cursor:grabbing}
.gfield{margin:0 0 15px}
.gfield>label{display:block;font-size:0.79rem;color:var(--mut);
 font-weight:600;margin-bottom:5px}
.gfield select,.gfield input[type=search]{width:100%}
.gfield input[type=range]{width:100%;accent-color:var(--accent)}
.gcheck{display:flex;align-items:center;gap:7px;font-size:0.874rem;padding:2.5px 0;cursor:pointer}
.gcheck input{accent-color:var(--accent);margin:0}
.gcheck i{width:10px;height:10px;border-radius:3px;flex:none}
.gcheck .c{margin-left:auto;font-size:0.784rem;color:var(--mut);font-variant-numeric:tabular-nums}
.gstat{display:flex;justify-content:space-between;font-size:0.848rem;padding:2px 0;
 border-bottom:1px solid var(--line2)}
.gstat b{font-variant-numeric:tabular-nums}
.ghint{font-size:0.806rem;color:var(--mut);line-height:1.6;margin-top:14px}
.gbtn{font:inherit;font-size:0.848rem;padding:5px 11px;border:1px solid var(--line);
 border-radius:var(--r);background:var(--panel);color:var(--fg);cursor:pointer}
.gbtn:hover{background:var(--hover)}
.gsel-empty{font-size:0.88rem;color:var(--mut);line-height:1.7}
.gsel h4{margin:0 0 1px;font-size:1.02rem}
.gsel .role{font-size:0.837rem;color:var(--mut);margin-bottom:11px}
.gsel .row{display:flex;justify-content:space-between;gap:10px;font-size:0.874rem;
 padding:3.5px 0;border-bottom:1px solid var(--line2)}
.gsel .row span:last-child{font-variant-numeric:tabular-nums;text-align:right}
.gsel h5{margin:14px 0 4px;font-size:0.79rem;color:var(--mut);font-weight:600}
.groles{margin:2px 0 10px}
.gact{margin:10px 0;padding:11px 13px;border-radius:var(--r);background:var(--fill-blue)}
.gact h5{margin:0 0 4px;color:var(--mut)}
.gact h5::before{content:"✅ "}
.gact ul{margin:0;padding-left:1.1em;font-size:0.853rem;line-height:1.55}
.gsel ol{margin:0;padding-left:1.3em;font-size:0.869rem}
.glink{fill:none;stroke:var(--mut)}
.gnode{cursor:pointer;stroke:var(--panel);stroke-width:1.5}
.glabel{font-size:9.5px;fill:var(--fg);pointer-events:none;paint-order:stroke;
 stroke:var(--bg);stroke-width:2.6px;stroke-linejoin:round}
.gcluster{font-size:14px;font-weight:600;pointer-events:none;paint-order:stroke;
 stroke:var(--bg);stroke-width:4px;stroke-linejoin:round;letter-spacing:.02em}
.dim{opacity:.1}
@media(max-width:1080px){
 .graphpage{grid-template-columns:1fr;height:auto}
 .gpanel{border-right:none;border-bottom:1px solid var(--line);max-height:none}
 .gpanel.right{border-left:none;border-top:1px solid var(--line)}
 .gstage{height:70vh}
}
"""

GRAPH_JS = r"""
// ネットワーク図。配置は Python 側で確定済みなので、ここでは動かさない。
// 図が見るたびに変わると比較できないため、力学シミュレーションは使わない。
(function () {
  var D = window.RELANA_GRAPH;
  if (!D) return;

  var svg = document.getElementById('gsvg');
  var gLinks = document.getElementById('g-links');
  var gNodes = document.getElementById('g-nodes');
  var gLabels = document.getElementById('g-labels');
  var gClusters = document.getElementById('g-clusters');
  var sel = document.getElementById('gselected');
  var DEPT_VARS = ['--d1','--d2','--d3','--d4','--d5','--d6','--d7','--d8'];

  var N = D.nodes, L = D.links, LB = D.labels || {};
  var deptColor = {};
  D.depts.forEach(function (d, i) {
    deptColor[d.name] = d.color || 'var(' + DEPT_VARS[i % 8] + ')';
  });

  N.forEach(function (n) { n.nbr = []; });
  L.forEach(function (l) { N[l.s].nbr.push(l.t); N[l.t].nbr.push(l.s); });

  var b = D.bounds;
  svg.setAttribute('viewBox', b[0] + ' ' + b[1] + ' ' + (b[2] - b[0]) + ' ' + (b[3] - b[1]));

  var state = {
    color: 'dept', size: 'degree', dyadOnly: false, crossOnly: false,
    depts: new Set(D.depts.map(function (d) { return d.name; })),
    query: '', selected: null, hovered: null, labels: 'key'
  };

  function visibleNode(n) {
    if (n.external) return true;
    return state.depts.has(n.dept);
  }
  function visibleLink(l) {
    if (state.dyadOnly && !l.dyad) return false;
    if (state.crossOnly && !l.cross) return false;
    return visibleNode(N[l.s]) && visibleNode(N[l.t]);
  }
  function metricVal(n, key) {
    if (key === 'degree') return n.degree || 0;
    if (key === 'strength') return n.strength || 0;
    if (key === 'influence' || key === 'betweenness') return (n.betweenness || 0) * 100;
    if (key === 'ideation') return n.constraint_pct == null ? 50 : n.constraint_pct;
    return 0;
  }
  function radius(n) {
    if (n.external) return 7;
    var max = state.size === 'degree' ? 28 : (state.size === 'strength' ? 120 : 100);
    return 4 + Math.sqrt(Math.max(metricVal(n, state.size), 0) / max) * 11;
  }
  function color(n) {
    if (n.external) return 'var(--mut)';
    if (state.color === 'dept') return deptColor[n.dept] || 'var(--mut)';
    if (state.color === 'vulnerability') {
      if (n.critical === 'critical') return 'var(--crit)';
      if (n.critical === 'warning') return 'var(--warn)';
      return '#cfccc7';
    }
    if (state.color === 'gap') {
      var g = n.gap == null ? 0 : n.gap;
      return g >= 40 ? 'var(--warn)' : (g <= -40 ? 'var(--accent)' : '#cfccc7');
    }
    if (state.color === 'ideation') {
      var p = n.constraint_pct == null ? 50 : n.constraint_pct;
      return p >= 80 ? 'var(--ok)' : (p <= 20 ? '#cfccc7' : 'var(--mut)');
    }
    if (state.color === 'roles') {
      var r = n.roles || [];
      if (r.indexOf('抜けると接点が切れる人') >= 0) return 'var(--crit)';
      if (r.indexOf('負荷が集中している人') >= 0) return 'var(--warn)';
      if (r.indexOf('橋渡し役') >= 0) return 'var(--accent)';
      if (r.indexOf('情報の通り道になっている人') >= 0) return 'var(--ok)';
      if (r.indexOf('接点が少ない人') >= 0) return '#cfccc7';
      return 'var(--mut)';
    }
    return 'var(--mut)';
  }

  // ── 部門のラベル
  (D.clusters || []).forEach(function (c) {
    var t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    t.setAttribute('class', 'gcluster');
    t.setAttribute('x', c.x); t.setAttribute('y', c.y);
    t.setAttribute('text-anchor', 'middle');
    t.setAttribute('fill', deptColor[c.name] || 'var(--mut)');
    t.textContent = c.name + '（' + c.count + '名）';
    t.setAttribute('data-dept', c.name);
    gClusters.appendChild(t);
  });

  var linkEls = L.map(function () {
    var e = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    e.setAttribute('class', 'glink');
    gLinks.appendChild(e); return e;
  });
  var nodeEls = N.map(function (n, i) {
    var e = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    e.setAttribute('class', 'gnode');
    e.setAttribute('cx', n.x); e.setAttribute('cy', n.y);
    e.addEventListener('mouseenter', function () { state.hovered = i; highlight(i); draw(); });
    e.addEventListener('mouseleave', function () {
      state.hovered = null; highlight(state.selected); draw();
    });
    e.addEventListener('click', function (ev) { ev.stopPropagation(); select(i); });
    gNodes.appendChild(e); return e;
  });
  var labelEls = N.map(function (n) {
    var e = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    e.setAttribute('class', 'glabel');
    e.setAttribute('y', n.y + ((LB[n.id] && LB[n.id].dy) || 3.4));
    e.textContent = n.label;
    gLabels.appendChild(e); return e;
  });

  function showLabel(n, i) {
    if (state.labels === 'none') return false;
    if (!LB[n.id]) return false;
    if (state.labels === 'all') return true;
    // ホバーした人と、その同席相手の氏名を出す
    if (state.hovered === i || state.selected === i) return true;
    if (state.hovered != null && N[state.hovered].nbr.indexOf(i) >= 0) return true;
    if (state.query && n.label.indexOf(state.query) >= 0) return true;
    return !!n.key;
  }

  function draw() {
    L.forEach(function (l, i) {
      var e = linkEls[i], vis = visibleLink(l);
      e.style.display = vis ? '' : 'none';
      if (!vis) return;
      var a = N[l.s], c = N[l.t];
      e.setAttribute('x1', a.x); e.setAttribute('y1', a.y);
      e.setAttribute('x2', c.x); e.setAttribute('y2', c.y);
      e.setAttribute('stroke-width', Math.min(3.2, 0.5 + Math.log1p(l.w) * 0.75));
      // 部門をまたぐ線は図の中央を長く横切る。薄くしないと、かたまりの中の線が埋もれる
      e.setAttribute('stroke-opacity', l.cross ? 0.14 : (l.dyad ? 0.5 : 0.32));
    });
    N.forEach(function (n, i) {
      var e = nodeEls[i], vis = visibleNode(n), t = labelEls[i];
      e.style.display = vis ? '' : 'none';
      if (!vis) { t.style.display = 'none'; return; }
      var r = radius(n);
      e.setAttribute('r', r);
      e.setAttribute('fill', color(n));
      var show = showLabel(n, i);
      t.style.display = show ? '' : 'none';
      if (show) {
        var m = LB[n.id];
        if (m.side > 0) {
          t.setAttribute('x', n.x + r + 4);
          t.setAttribute('text-anchor', 'start');
        } else {
          t.setAttribute('x', n.x - r - 4);
          t.setAttribute('text-anchor', 'end');
        }
      }
    });
    gClusters.querySelectorAll('text').forEach(function (t) {
      t.style.display = state.depts.has(t.getAttribute('data-dept')) ? '' : 'none';
    });
  }

  function highlight(idx) {
    if (idx == null) {
      nodeEls.forEach(function (e) { e.classList.remove('dim'); });
      linkEls.forEach(function (e) { e.classList.remove('dim'); });
      labelEls.forEach(function (e) { e.classList.remove('dim'); });
      return;
    }
    var keep = new Set(N[idx].nbr); keep.add(idx);
    nodeEls.forEach(function (e, i) { e.classList.toggle('dim', !keep.has(i)); });
    labelEls.forEach(function (e) { e.classList.remove('dim'); });
    linkEls.forEach(function (e, i) {
      e.classList.toggle('dim', L[i].s !== idx && L[i].t !== idx);
    });
  }

  function row(k, v) { return '<div class="row"><span>' + k + '</span><span>' + v + '</span></div>'; }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function select(idx) {
    state.selected = idx; highlight(idx); draw();
    var n = N[idx];
    var h = '<div class="gsel"><h4>' + esc(n.label) + '</h4>';
    h += '<div class="role">' + esc(n.dept) + (n.team && n.team !== n.dept ? ' / ' + esc(n.team) : '') + '</div>';
    if (n.roles && n.roles.length) {
      h += '<div class="groles">' + n.roles.map(function (r) {
        return '<span class="roletag">' + esc(r) + '</span>';
      }).join('') + '</div>';
    }
    if (n.actions && n.actions.length) {
      h += '<div class="gact"><h5>打ち手</h5><ul>'
        + n.actions.map(function (a) { return '<li>' + esc(a) + '</li>'; }).join('')
        + '</ul></div>';
    }
    h += row('同席した相手', (n.degree || 0) + ' 名');
    h += row('その相手がいる部門', n.alter_depts == null ? '—' : n.alter_depts + ' 部門');
    h += row('その相手どうしが同席している組',
             n.alters_linked == null ? '—' : Math.round(n.alters_linked * 100) + '%');
    h += row('他の人どうしの経路が通る割合（インフルエンサー）',
             n.betweenness == null ? '—' : n.betweenness.toFixed(4));
    if (n.dept_pairs_kept != null) {
      h += row('代わりの人がいる部門の組',
               Math.round(n.dept_pairs_kept * 100) + '%（' + (n.dept_pairs || 0) + '組）');
    }
    if (n.replaceability != null) {
      h += row('代わりの人がいる相手どうしの組', Math.round(n.replaceability * 100) + '%');
    }
    if (n.bridged && n.bridged.length) {
      h += '<h5>' + esc(n.label) + ' が抜けると接点が0になる先</h5><ol>'
        + n.bridged.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ol>';
    }
    var nb = n.nbr.map(function (j) { return N[j]; })
      .filter(visibleNode)
      .sort(function (a, c) { return (c.degree || 0) - (a.degree || 0); }).slice(0, 12);
    if (nb.length) {
      h += '<h5>図に描かれている同席相手</h5><ol>'
        + nb.map(function (m) {
            return '<li>' + esc(m.label) + ' <span class="sub">' + esc(m.dept) + '</span></li>';
          }).join('') + '</ol>';
    }
    sel.innerHTML = h + '</div>';
  }

  // ── 表示位置の移動と拡大縮小（配置そのものは変えない）
  var view = { x: 0, y: 0, k: 1 }, pan = null;
  function applyView() {
    document.getElementById('g-root').setAttribute(
      'transform', 'translate(' + view.x + ',' + view.y + ') scale(' + view.k + ')');
  }
  svg.addEventListener('wheel', function (ev) {
    ev.preventDefault();
    var f = ev.deltaY < 0 ? 1.12 : 1 / 1.12;
    var nk = Math.min(5, Math.max(0.4, view.k * f));
    var r = svg.getBoundingClientRect();
    var mx = ev.clientX - r.left, my = ev.clientY - r.top;
    view.x = mx - (mx - view.x) * (nk / view.k);
    view.y = my - (my - view.y) * (nk / view.k);
    view.k = nk; applyView();
  }, { passive: false });
  svg.addEventListener('mousedown', function (ev) {
    pan = { x: ev.clientX, y: ev.clientY, vx: view.x, vy: view.y };
    svg.classList.add('dragging');
  });
  window.addEventListener('mousemove', function (ev) {
    if (!pan) return;
    view.x = pan.vx + (ev.clientX - pan.x);
    view.y = pan.vy + (ev.clientY - pan.y);
    applyView();
  });
  window.addEventListener('mouseup', function () { pan = null; svg.classList.remove('dragging'); });
  svg.addEventListener('click', function () {
    state.selected = null; highlight(null); draw(); showEmpty();
  });
  function showEmpty() {
    sel.innerHTML = '<p class="gsel-empty">人をクリックすると、その人の指標と'
      + '図に描かれている同席相手が表示されます。図はドラッグで移動、ホイールで拡大縮小できます。'
      + '配置は固定で、開くたびに同じ形になります。</p>';
  }

  function bind(id, fn) {
    var el = document.getElementById(id);
    if (el) el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', function () { fn(el); });
  }
  bind('gcolor', function (el) { state.color = el.value; draw(); updateLegend(); });
  bind('gsize', function (el) { state.size = el.value; draw(); });
  bind('gdyad', function (el) { state.dyadOnly = el.checked; draw(); });
  bind('gcross', function (el) { state.crossOnly = el.checked; draw(); });
  bind('glabels', function (el) { state.labels = el.value; draw(); });
  bind('gsearch', function (el) {
    state.query = el.value.trim(); draw();
    if (!state.query) return;
    var hit = N.findIndex(function (n) {
      return visibleNode(n) && n.label.indexOf(state.query) >= 0;
    });
    if (hit >= 0) select(hit);
  });
  document.querySelectorAll('[data-dept-filter]').forEach(function (cb) {
    cb.addEventListener('change', function () {
      var d = cb.getAttribute('data-dept-filter');
      if (cb.checked) state.depts.add(d); else state.depts.delete(d);
      draw();
    });
  });
  var reset = document.getElementById('greset');
  if (reset) reset.addEventListener('click', function () {
    view = { x: 0, y: 0, k: 1 }; applyView();
  });

  function updateLegend() {
    var el = document.getElementById('glegend');
    if (!el) return;
    var items;
    if (state.color === 'dept') {
      items = D.depts.map(function (d) {
        return '<span><i style="background:' + deptColor[d.name] + '"></i>' + esc(d.name) + '</span>';
      });
    } else if (state.color === 'vulnerability') {
      items = ['<span><i style="background:var(--crit)"></i>要対応</span>',
               '<span><i style="background:var(--warn)"></i>警戒</span>',
               '<span><i style="background:#cfccc7"></i>該当なし</span>'];
    } else if (state.color === 'gap') {
      items = ['<span><i style="background:var(--warn)"></i>媒介中心性が接触数より高い</span>',
               '<span><i style="background:var(--accent)"></i>接触数が媒介中心性より高い</span>',
               '<span><i style="background:#cfccc7"></i>差が小さい</span>'];
    } else if (state.color === 'roles') {
      items = ['<span><i style="background:var(--crit)"></i>抜けると接点が切れる</span>',
               '<span><i style="background:var(--warn)"></i>負荷が集中</span>',
               '<span><i style="background:var(--accent)"></i>橋渡し役</span>',
               '<span><i style="background:var(--ok)"></i>情報の通り道</span>',
               '<span><i style="background:#cfccc7"></i>接点が少ない</span>'];
    } else {
      items = ['<span><i style="background:var(--ok)"></i>制約が低い（上位20%）</span>',
               '<span><i style="background:#cfccc7"></i>制約が高い（下位20%）</span>'];
    }
    el.innerHTML = items.join('');
  }

  updateLegend(); draw(); showEmpty(); applyView();
})();
"""
