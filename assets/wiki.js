// Micro-VM 分析 Wiki 脚本: 暗色模式 + 搜索 + 当前页高亮
(function () {
  // ---- 暗色模式 ----
  var KEY = 'mvwiki-theme';
  var btn = document.getElementById('theme-toggle');
  function apply(t) {
    document.documentElement.classList.toggle('dark', t === 'dark');
    if (btn) btn.textContent = t === 'dark' ? '☀️' : '🌙';
  }
  var saved = localStorage.getItem(KEY) ||
    (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  apply(saved);
  if (btn) btn.addEventListener('click', function () {
    var now = document.documentElement.classList.contains('dark') ? 'light' : 'dark';
    localStorage.setItem(KEY, now); apply(now);
  });

  // ---- 当前页侧边栏高亮 ----
  var here = location.pathname.split('/').pop() || 'index.html';
  if (here === '') here = 'index.html';
  document.querySelectorAll('.nav a').forEach(function (a) {
    var href = a.getAttribute('href') || '';
    if (href.split('/').pop() === here) {
      a.classList.add('active');
      // 展开所在分组
      var p = a.closest('details.nav-group');
      while (p) { p.open = true; p = p.parentElement && p.parentElement.closest('details.nav-group'); }
    }
  });

  // ---- 搜索 ----
  var input = document.getElementById('search');
  var box = document.createElement('div');
  box.className = 'search-results';
  input.parentNode.insertBefore(box, input.nextSibling);
  var index = null;
  function depthPrefix() {
    // 从当前页面路径深度推算 assets 前缀
    var p = location.pathname;
    // 以目录形式时 pathname 形如 /.../wiki/analysis/foo.html
    var parts = p.split('/');
    var depth = 0;
    for (var i = parts.length - 1; i >= 0; i--) {
      if (parts[i] === 'wiki') break;
      depth++;
    }
    // depth 包含文件名, assets 前缀 = (depth-1) 个 ../
    var up = Math.max(0, depth - 1);
    return '../'.repeat(up);
  }
  function ensureIndex(cb) {
    if (index) return cb();
    var x = new XMLHttpRequest();
    x.open('GET', depthPrefix() + 'assets/search.json', true);
    x.onload = function () {
      try { index = JSON.parse(x.responseText); } catch (e) { index = []; }
      cb();
    };
    x.onerror = function () { index = []; cb(); };
    x.send();
  }
  function rel(href) {
    // href 是 root 相对(如 analysis/x.html), 按当前页深度补前缀
    var pre = depthPrefix();
    return pre + href;
  }
  function render(q) {
    q = q.trim();
    if (!q) { box.style.display = 'none'; box.innerHTML = ''; return; }
    var ql = q.toLowerCase();
    var hits = index.filter(function (e) {
      return e.title.toLowerCase().indexOf(ql) >= 0 || e.snippet.toLowerCase().indexOf(ql) >= 0;
    }).slice(0, 30);
    if (!hits.length) {
      box.innerHTML = '<div class="res"><div class="t">无匹配</div></div>';
      box.style.display = 'block';
      return;
    }
    box.innerHTML = hits.map(function (e) {
      return '<a class="res" href="' + rel(e.path) + '"><div class="t">' + esc(e.title) +
        '</div><div class="s">' + esc(e.snippet.slice(0, 90)) + '</div></a>';
    }).join('');
    box.style.display = 'block';
  }
  function esc(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  if (input) {
    input.addEventListener('input', function () { ensureIndex(function () { render(input.value); }); });
    input.addEventListener('focus', function () { if (input.value) { ensureIndex(function () { render(input.value); }); } });
    document.addEventListener('click', function (e) {
      if (!box.contains(e.target) && e.target !== input) box.style.display = 'none';
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { input.value = ''; render(''); input.blur(); }
    });
  }
})();
