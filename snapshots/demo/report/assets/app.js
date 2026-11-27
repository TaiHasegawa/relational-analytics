
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
