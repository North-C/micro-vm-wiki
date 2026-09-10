(function () {
  'use strict';

  var body = document.body;
  var root = body.dataset.root || '';
  var themeButton = document.getElementById('theme-toggle');
  var menuButton = document.getElementById('menu-toggle');
  var sidebar = document.getElementById('site-sidebar');
  var scrim = document.getElementById('sidebar-scrim');
  var searchInput = document.getElementById('search');
  var searchResults = document.getElementById('search-results');
  var searchStatus = document.getElementById('search-status');
  var searchIndex = null;
  var activeResult = -1;
  var kindLabels = { tutorial: '学习路线', 'how-to': '操作指南', reference: '参考资料', explanation: '机制解析' };
  var statusLabels = { draft: '草稿', review: '复核中', current: '已按固定版本复核', historical: '历史参考', deferred: '暂缓', unconfirmed: '待固定版本复核' };
  var projectLabels = { firecracker: 'Firecracker', 'cloud-hypervisor': 'Cloud Hypervisor', crosvm: 'crosvm', 'kata-containers': 'Kata Containers', cubesandbox: 'CubeSandbox' };
  var platformLabels = { agentenv: 'AgentENV', 'e2b-infra': 'E2B-infra' };
  var layerLabels = { 'sandbox-platform': '沙箱平台', 'sandbox-infrastructure': '沙箱基础设施' };

  function resolveFromRoot(path) {
    return new URL(root + path, document.baseURI).href;
  }

  function normalizePath(url) {
    var parsed = new URL(url, document.baseURI);
    return decodeURIComponent(parsed.pathname).replace(/\/+$/, '') || '/';
  }

  function setTheme(theme) {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    if (themeButton) {
      themeButton.textContent = theme === 'dark' ? '☀️' : '🌙';
      themeButton.setAttribute('aria-label', theme === 'dark' ? '切换到浅色模式' : '切换到深色模式');
    }
  }

  var savedTheme = localStorage.getItem('mvwiki-theme');
  var preferredTheme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  setTheme(savedTheme || preferredTheme);
  if (themeButton) {
    themeButton.addEventListener('click', function () {
      var next = document.documentElement.classList.contains('dark') ? 'light' : 'dark';
      localStorage.setItem('mvwiki-theme', next);
      setTheme(next);
    });
  }

  function setNavigation(open) {
    var mobile = window.innerWidth <= 820;
    var hidden = mobile && !open;
    body.classList.toggle('nav-open', open);
    if (menuButton) menuButton.setAttribute('aria-expanded', String(open));
    if (sidebar) {
      sidebar.setAttribute('aria-hidden', String(hidden));
      sidebar.inert = hidden;
    }
  }
  if (menuButton) menuButton.addEventListener('click', function () { setNavigation(!body.classList.contains('nav-open')); });
  if (scrim) scrim.addEventListener('click', function () { setNavigation(false); });
  window.addEventListener('resize', function () { if (window.innerWidth > 820) setNavigation(false); });
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && body.classList.contains('nav-open')) {
      setNavigation(false);
      if (menuButton) menuButton.focus();
    }
  });
  setNavigation(false);

  var currentPath = normalizePath(location.href);
  document.querySelectorAll('.nav-tree a').forEach(function (link) {
    if (normalizePath(link.href) === currentPath) {
      link.setAttribute('aria-current', 'page');
      var group = link.closest('details');
      while (group) {
        group.open = true;
        group = group.parentElement && group.parentElement.closest('details');
      }
    }
  });

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function announce(message) {
    if (searchStatus) searchStatus.textContent = message;
  }

  function closeResults() {
    activeResult = -1;
    searchResults.classList.remove('open');
    searchResults.innerHTML = '';
    announce('');
    if (searchInput) searchInput.setAttribute('aria-expanded', 'false');
  }

  function resultLinks() {
    return Array.prototype.slice.call(searchResults.querySelectorAll('.search-result'));
  }

  function selectResult(index) {
    var links = resultLinks();
    if (!links.length) return;
    activeResult = Math.max(0, Math.min(index, links.length - 1));
    links.forEach(function (link, i) {
      link.setAttribute('aria-selected', String(i === activeResult));
    });
    links[activeResult].focus();
  }

  function searchableText(entry) {
    return [entry.title, entry.summary]
      .concat(
        entry.headings || [], entry.projects || [], entry.platforms || [], entry.integrates_with_projects || [],
        entry.topics || [], entry.curated_topics || [], entry.tags || [], entry.baselines || [], entry.architectures || [],
        (entry.component_baselines || []).map(function (item) { return item.component + ' ' + item.version + ' ' + item.commit; })
      )
      .join(' ')
      .toLocaleLowerCase('zh-CN');
  }

  function statusLabel(entry) {
    if (entry.scope === 'platform' && entry.status === 'unconfirmed' && (entry.component_baselines || []).length) {
      return '源码已固定，运行未验证';
    }
    return statusLabels[entry.status] || entry.status;
  }

  function renderResults(query) {
    var normalized = query.trim().toLocaleLowerCase('zh-CN');
    if (!normalized) {
      closeResults();
      return;
    }
    var hits = searchIndex.filter(function (entry) {
      return searchableText(entry).indexOf(normalized) !== -1;
    }).slice(0, 30);
    if (!hits.length) {
      searchResults.innerHTML = '<div class="search-result"><span class="search-result-title">无匹配结果</span></div>';
      searchResults.classList.add('open');
      searchInput.setAttribute('aria-expanded', 'true');
      announce('没有匹配结果');
      return;
    }
    searchResults.innerHTML = hits.map(function (entry) {
      var projects = (entry.projects || []).map(function (project) { return projectLabels[project] || project; });
      var platforms = (entry.platforms || []).map(function (platform) { return platformLabels[platform] || platform; });
      var meta = projects.concat(platforms, [layerLabels[entry.layer] || entry.layer, kindLabels[entry.kind] || entry.kind, statusLabel(entry)]).filter(Boolean).join(' · ');
      return '<a class="search-result" role="option" aria-selected="false" href="' +
        escapeHtml(resolveFromRoot(entry.route)) + '">' +
        '<span class="search-result-title">' + escapeHtml(entry.title) + '</span>' +
        '<div class="search-result-meta">' + escapeHtml(meta) + '</div>' +
        '<div class="search-result-summary">' + escapeHtml((entry.summary || '').slice(0, 110)) + '</div></a>';
    }).join('');
    searchResults.classList.add('open');
    searchInput.setAttribute('aria-expanded', 'true');
    activeResult = -1;
    announce('找到 ' + hits.length + ' 个结果');
  }

  function loadSearchIndex(callback) {
    if (searchIndex) {
      callback();
      return;
    }
    fetch(resolveFromRoot('assets/search.json'))
      .then(function (response) {
        if (!response.ok) throw new Error('search index unavailable');
        return response.json();
      })
      .then(function (data) { searchIndex = data; callback(); })
      .catch(function () { searchIndex = []; announce('搜索索引加载失败'); });
  }

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      loadSearchIndex(function () { renderResults(searchInput.value); });
    });
    searchInput.addEventListener('focus', function () {
      if (searchInput.value) loadSearchIndex(function () { renderResults(searchInput.value); });
    });
    searchInput.addEventListener('keydown', function (event) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        selectResult(0);
      } else if (event.key === 'Escape') {
        searchInput.value = '';
        closeResults();
      }
    });
    searchResults.addEventListener('keydown', function (event) {
      var links = resultLinks();
      if (!links.length) return;
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        selectResult((activeResult + 1) % links.length);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        if (activeResult <= 0) searchInput.focus();
        else selectResult(activeResult - 1);
      } else if (event.key === 'Escape') {
        event.preventDefault();
        closeResults();
        searchInput.focus();
      }
    });
  }

  document.addEventListener('click', function (event) {
    if (searchResults && !searchResults.contains(event.target) && event.target !== searchInput) closeResults();
  });

  if (window.mermaid) {
    window.mermaid.initialize({ startOnLoad: true, securityLevel: 'strict', theme: 'neutral' });
  }
})();
