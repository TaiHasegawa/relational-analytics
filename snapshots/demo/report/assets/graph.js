
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
