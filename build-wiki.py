#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Micro-VM 分析文档 -> 静态 wiki 生成器。

把分散在 analysis/ 与各项目 analysis/ 的 markdown 文档编译成一个
浏览器可查看的静态 wiki（侧边栏导航 + 搜索 + Mermaid + 暗色模式）。

特点:
- 镜像原目录结构, 把 .md 相对链接(../xxx/foo.md)重写为 .html, 保持跨项目引用可用。
- 源码引用(.rs/.go/.sh 等, 不在 wiki 范围内)渲染为可读纯文本, 不产生死链。
- Mermaid 代码块原地转为 <div class="mermaid"> 由 mermaid.min.js 渲染。
- 纯静态, 可 file:// 打开, 也可用任意 http server 托管; 资产本地化, 离线可用。

用法: python3 build-wiki.py  (在仓库根目录运行)
输出: ./wiki/
"""
import os
import re
import html
import json
import urllib.request
import markdown as md

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "wiki")
ASSETS = os.path.join(OUT, "assets")

# ---- 要纳入 wiki 的源目录 (相对于 ROOT) ----
# (源目录, 显示名)
PROJECT_DIRS = [
    ("firecracker/analysis", "Firecracker"),
    ("cloud-hypervisor/analysis", "Cloud Hypervisor"),
    ("kata-containers/analysis", "Kata Containers"),
    ("crosvm/analysis", "crosvm"),
    ("CubeSandbox-sandbox-clone/analysis", "CubeSandbox"),
]
EXTRA_DIRS = [
    ("sandbox-bench/docs", "sandbox-bench 文档"),
]
TOP_DIR = "analysis"

# ---- 顶层 analysis/ 文档的人工分组 (文件名不含扩展名) ----
GROUP_SYNTH = ["vm-design-landscape-overview", "performance-design-basis-cross-project",
               "security-design-basis-cross-project", "analysis-improvement-recommendations",
               "claude-code-research-workflow"]
GROUP_NAV = ["README", "four-project-deep-routes", "four-project-route-coverage-matrix"]
GROUP_CROSS = ["boot-control-plane-cross-project", "snapshot-restore-cross-project",
               "storage-rootfs-sharefs-cross-project", "virtio-data-path-cross-project",
               "interrupt-event-notification-cross-project", "hypervisor-kvm-vcpu-cross-project",
               "guest-memory-dma-iommu-cross-project", "device-model-isolation-cross-project",
               "runtime-control-hotplug-cross-project", "network-connectivity-cross-project",
               "guest-agent-runtime-cross-project", "security-isolation-cross-project",
               "resource-qos-cross-project", "observability-diagnostics-cross-project",
               "cpu-interrupt-machine-cross-project", "arm64-x86-cross-project-matrix"]
GROUP_CROSSLINE = ["ch-cubesandbox-backend-notifier-restore-crossline",
                   "ch-cubesandbox-restore-guest-unavailability-checklist",
                   "fc-kata-storage-semantics-crossline"]
GROUP_HIST = ["coco-pvm-protected-vm-cross-project", "protected-vm-snapshot-migration-cross-project"]
GROUP_ARM64NET = ["arm64-network-document-index", "arm64-network-sample-coverage-matrix",
                  "arm64-network-next-target-map", "arm64-network-sample-collection-runbook",
                  "arm64-network-validation-observation-matrix", "arm64-network-failure-signature-matrix",
                  "arm64-network-evidence-maturity-matrix", "arm64-network-test-observation-command-matrix",
                  "arm64-network-next-sample-priority"]
GROUP_NONNET = ["arm64-non-network-risk-map", "non-network-sample-asset-matrix",
                "non-network-next-target-map", "non-network-evidence-bundle-template",
                "non-network-sample-collection-runbook", "non-network-evidence-gaps"]

# ---- 收集所有源 markdown: relpath(无 .wiki 前缀) -> 绝对路径 ----
sources = {}  # src_rel (如 'analysis/foo.md') -> abs path

def add_dir(rel):
    d = os.path.join(ROOT, rel)
    if not os.path.isdir(d):
        return
    for f in sorted(os.listdir(d)):
        if f.endswith(".md"):
            sources[os.path.join(rel, f)] = os.path.join(d, f)

add_dir(TOP_DIR)
for rel, _ in PROJECT_DIRS:
    add_dir(rel)
for rel, _ in EXTRA_DIRS:
    add_dir(rel)
# samples: 索引 + 各样本 SUMMARY
samp = os.path.join(ROOT, "analysis", "samples")
if os.path.isdir(samp):
    for f in sorted(os.listdir(samp)):
        if f.endswith(".md"):
            sources[os.path.join("analysis", "samples", f)] = os.path.join(samp, f)
    for sub in sorted(os.listdir(samp)):
        sp = os.path.join(samp, sub)
        if os.path.isdir(sp):
            sf = os.path.join(sp, "SUMMARY.md")
            if os.path.exists(sf):
                sources[os.path.join("analysis", "samples", sub, "SUMMARY.md")] = sf
# Agent.md (工作约定)
ag = os.path.join(ROOT, "Agent.md")
if os.path.exists(ag):
    sources["Agent.md"] = ag

# 输出 html 集合 (src_rel 去掉 .md 加 .html, 路径不变)
def out_rel_for(src_rel):
    return src_rel[:-3] + ".html"

out_set = set(out_rel_for(s) for s in sources)

# ---- 取标题 ----
def title_of(abs_path, fallback):
    try:
        with open(abs_path, encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^#\s+(.+?)\s*$", line)
                if m:
                    return m.group(1).strip()
    except Exception:
        pass
    return fallback

# ---- 链接重写 ----
HREF_RE = re.compile(r'(<a\s+[^>]*?)href="([^"]+)"([^>]*>)(.*?</a>)', re.DOTALL)

def rewrite_links(html_text, src_rel):
    """把当前文档(src_rel)里的相对 .md 链接改写为 .html; 无效链接降级为纯文本。"""
    src_dir = os.path.dirname(src_rel)
    out_dir = os.path.dirname(out_rel_for(src_rel))

    def repl(m):
        pre, href, post, inner = m.group(1), m.group(2), m.group(3), m.group(4)
        low = href.strip()
        # 外部 / 锚点 / 邮件: 保留
        if low.startswith(("http://", "https://", "mailto:", "#")):
            return m.group(0)
        # 拆出 anchor
        anchor = ""
        path_part = low
        if "#" in low:
            path_part, anchor = low.split("#", 1)
            anchor = "#" + anchor
        if path_part == "":
            return m.group(0)  # 纯锚点
        if path_part.endswith(".md"):
            # 解析目标相对源路径
            tgt_src = os.path.normpath(os.path.join(src_dir, path_part))
            tgt_out = out_rel_for(tgt_src)
            if tgt_out in out_set:
                # 计算输出相对路径
                rel_link = os.path.relpath(tgt_out, out_dir)
                return f'{pre}href="{rel_link}{anchor}"{post}{inner}'
            else:
                # 目标不在 wiki 范围: 降级为纯文本(保留可读引用)
                text = re.sub(r"<[^>]+>", "", inner)
                return f'<code class="src-ref">{html.escape(text)}</code>'
        else:
            # 非 markdown(源码 .rs/.go/.sh 等): 降级为纯文本
            text = re.sub(r"<[^>]+>", "", inner)
            return f'<code class="src-ref">{html.escape(text)}</code>'
    return HREF_RE.sub(repl, html_text)

# ---- Mermaid 转换 ----
MERMAID_RE = re.compile(
    r'<pre><code(?:\s+class="language-mermaid")?>(.*?)</code></pre>', re.DOTALL)

def convert_mermaid(html_text):
    def repl(m):
        code = html.unescape(m.group(1))
        return f'<div class="mermaid">{code}</div>'
    # 仅转 mermaid 语言块
    mm = re.compile(r'<pre><code class="language-mermaid">(.*?)</code></pre>', re.DOTALL)
    return mm.sub(lambda m: f'<div class="mermaid">{html.unescape(m.group(1))}</div>', html_text)

# ---- markdown 渲染 ----
MD_EXT = ["extra", "toc", "admonition", "sane_lists"]

def render(abs_path, src_rel):
    with open(abs_path, encoding="utf-8") as fh:
        text = fh.read()
    body = md.markdown(text, extensions=MD_EXT, output_format="html5")
    body = convert_mermaid(body)
    body = rewrite_links(body, src_rel)
    return body

# ---- 侧边栏构建 ----
def li(href_from_root, label):
    return f'<li><a href="{href_from_root}">{html.escape(label)}</a></li>'

def details(title, items_html, default_open=True):
    op = " open" if default_open else ""
    return f'<details class="nav-group"{op}><summary>{html.escape(title)}</summary><ul>{items_html}</ul></details>'

def build_sidebar():
    parts = []
    parts.append(li("index.html", "🏠 首页"))

    # 综合学习层
    items = "".join(
        li(f"{TOP_DIR}/{n}.html", title_of(sources[f"{TOP_DIR}/{n}.md"], n))
        for n in GROUP_SYNTH if f"{TOP_DIR}/{n}.md" in sources)
    parts.append(details("综合学习层", items))

    # 框架导航
    items = "".join(
        li(f"{TOP_DIR}/{n}.html", title_of(sources[f"{TOP_DIR}/{n}.md"], n))
        for n in GROUP_NAV if f"{TOP_DIR}/{n}.md" in sources)
    parts.append(details("分析框架导航", items))

    # 跨项目专题
    items = "".join(
        li(f"{TOP_DIR}/{n}.html", title_of(sources[f"{TOP_DIR}/{n}.md"], n))
        for n in GROUP_CROSS if f"{TOP_DIR}/{n}.md" in sources)
    parts.append(details("跨项目专题", items))

    # 交叉线
    items = "".join(
        li(f"{TOP_DIR}/{n}.html", title_of(sources[f"{TOP_DIR}/{n}.md"], n))
        for n in GROUP_CROSSLINE if f"{TOP_DIR}/{n}.md" in sources)
    if items:
        parts.append(details("项目交叉线", items))

    # ARM64 网络
    items = "".join(
        li(f"{TOP_DIR}/{n}.html", title_of(sources[f"{TOP_DIR}/{n}.md"], n))
        for n in GROUP_ARM64NET if f"{TOP_DIR}/{n}.md" in sources)
    if items:
        parts.append(details("ARM64 网络线", items))

    # 非网络样本
    items = "".join(
        li(f"{TOP_DIR}/{n}.html", title_of(sources[f"{TOP_DIR}/{n}.md"], n))
        for n in GROUP_NONNET if f"{TOP_DIR}/{n}.md" in sources)
    if items:
        parts.append(details("非网络样本与证据", items))

    # 历史/暂缓
    items = "".join(
        li(f"{TOP_DIR}/{n}.html", title_of(sources[f"{TOP_DIR}/{n}.md"], n))
        for n in GROUP_HIST if f"{TOP_DIR}/{n}.md" in sources)
    if items:
        parts.append(details("历史 / 暂缓参考", items, default_open=False))

    # 其他顶层文档
    known = set(GROUP_SYNTH + GROUP_NAV + GROUP_CROSS + GROUP_CROSSLINE +
                GROUP_HIST + GROUP_ARM64NET + GROUP_NONNET)
    other = [n for n in sorted(os.path.basename(s)[:-3]
             for s in sources if s.startswith("analysis/") and "/" not in s[len("analysis/"):])
             if n not in known]
    if other:
        items = "".join(li(f"{TOP_DIR}/{n}.html", title_of(sources[f"{TOP_DIR}/{n}.md"], n))
                        for n in other)
        parts.append(details("其他顶层文档", items, default_open=False))

    # 各项目
    for rel, name in PROJECT_DIRS:
        files = sorted(s for s in sources if s.startswith(rel + "/"))
        # deep-routes / deep-dive 优先
        head = [f for f in files if os.path.basename(f) in ("deep-routes.md", "deep-dive.md")]
        head.sort(key=lambda f: 0 if f.endswith("deep-routes.md") else 1)
        rest = [f for f in files if f not in head]
        items = ""
        for f in head + rest:
            label = title_of(sources[f], os.path.basename(f)[:-3])
            items += li(out_rel_for(f), label)
        if items:
            parts.append(details(name + f" ({len(files)})", items, default_open=False))

    # sandbox-bench 等
    for rel, name in EXTRA_DIRS:
        files = sorted(s for s in sources if s.startswith(rel + "/"))
        items = "".join(li(out_rel_for(f), title_of(sources[f], os.path.basename(f)[:-3])) for f in files)
        if items:
            parts.append(details(name, items, default_open=False))

    # 样本资产
    samp_files = sorted(s for s in sources if s.startswith("analysis/samples/"))
    if samp_files:
        items = "".join(li(out_rel_for(f), title_of(sources[f], os.path.basename(f)[:-3])) for f in samp_files)
        parts.append(details("样本资产", items, default_open=False))

    # Agent.md
    if "Agent.md" in sources:
        parts.append(li("Agent.html", title_of(sources["Agent.md"], "Agent 工作约定")))

    return "\n".join(parts)

SIDEBAR_HTML = ""  # filled after build

# ---- 搜索索引 ----
def build_search_index(entries):
    data = []
    for src_rel, abs_path in entries.items():
        outp = out_rel_for(src_rel)
        title = title_of(abs_path, os.path.basename(src_rel)[:-3])
        # 取前若干正文(去 markdown 符号)
        try:
            with open(abs_path, encoding="utf-8") as fh:
                txt = fh.read()
            txt = re.sub(r"```.*?```", " ", txt, flags=re.DOTALL)
            txt = re.sub(r"[#*`>\[\]()|_-]", " ", txt)
            snippet = re.sub(r"\s+", " ", txt).strip()[:200]
        except Exception:
            snippet = ""
        data.append({"title": title, "path": outp, "snippet": snippet})
    return data

# ---- 模板 ----
TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{assets}style.css">
</head>
<body>
<div class="layout">
  <aside class="sidebar">
    <div class="brand">Micro-VM 分析 Wiki</div>
    <input id="search" type="search" placeholder="搜索文档…" autocomplete="off">
    <nav class="nav">
      {sidebar}
    </nav>
  </aside>
  <main class="content">
    <div class="topbar">
      <button id="theme-toggle" title="切换暗色模式">🌙</button>
      <a class="back-home" href="{root}index.html">🏠 首页</a>
    </div>
    <article class="markdown-body">
      {body}
    </article>
    <footer class="page-foot">源文件: <code>{src}</code></footer>
  </main>
</div>
<script src="{assets}mermaid.min.js"></script>
<script>window.mermaid && mermaid.initialize({{startOnLoad:true, theme:'neutral', securityLevel:'loose'}});</script>
<script src="{assets}wiki.js"></script>
</body>
</html>
"""

def render_page(src_rel, body, title):
    # 计算 assets 与 root 的相对前缀
    depth = out_rel_for(src_rel).count("/")
    assets_pre = ("../" * depth) + "assets/"
    root_pre = ("../" * depth)
    page = TEMPLATE.format(
        title=html.escape(title),
        assets=assets_pre,
        root=root_pre,
        sidebar=SIDEBAR_HTML,
        body=body,
        src=html.escape(src_rel),
    )
    # 修正侧边栏首页链接(侧边栏用的是 root 绝对路径, 需加 root_pre)
    page = page.replace('href="index.html"', f'href="{root_pre}index.html"')
    return page

# ---- 写入首页 ----
HOME_HTML = """<h1>Micro-VM 轻量化虚拟机分析 Wiki</h1>
<p>本 wiki 汇总了 Firecracker、Cloud Hypervisor、Kata Containers、crosvm、CubeSandbox 五个轻量化虚拟机项目的源码分析、跨项目专题对比、ARM64 网络判错样本与综合设计依据。</p>
<div class="home-grid">
  <div class="card">
    <h3>🧭 第一次进来想系统学习</h3>
    <p>从完整面貌与学习路线开始, 串起全部机制文档。</p>
    <a href="analysis/vm-design-landscape-overview.html">轻量化虚拟机设计全景与学习路线 →</a>
  </div>
  <div class="card">
    <h3>⚡ 如何构建高性能 VM</h3>
    <p>七个性能杠杆 + 实测锚点(1000 实例/15s、arm64 ctx-switch p50≈1.2µs)。</p>
    <a href="analysis/performance-design-basis-cross-project.html">性能设计依据跨项目专题 →</a>
  </div>
  <div class="card">
    <h3>🔒 安全设计依据</h3>
    <p>威胁模型、纵深防御、攻击面收敛三种范式、性能-安全张力。</p>
    <a href="analysis/security-design-basis-cross-project.html">安全设计依据跨项目专题 →</a>
  </div>
  <div class="card">
    <h3>🗺 分析框架与改进</h3>
    <p>专题完成度矩阵、改进优先级、证据标准与协作流程。</p>
    <a href="analysis/analysis-improvement-recommendations.html">分析框架改进意见 →</a>
  </div>
</div>
<h2>按阅读方式进入</h2>
<ul>
  <li><b>按项目路线</b>: 侧边栏展开各项目, 先读 <code>deep-routes</code> 再读各 <code>*-chain</code>。</li>
  <li><b>按跨项目专题</b>: 侧边栏"跨项目专题"组, 横向比较机制差异。</li>
  <li><b>按样本/证据</b>: 侧边栏"样本资产"与"非网络样本与证据"。</li>
</ul>
<h2>本地查看</h2>
<p>纯静态站点, 任选其一:</p>
<ul>
  <li>直接用浏览器打开 <code>wiki/index.html</code>。</li>
  <li>或本地起服务(支持搜索全部功能): <code>python3 -m http.server -d wiki 8000</code> 后访问 <code>http://localhost:8000</code>。</li>
</ul>
"""

def main():
    global SIDEBAR_HTML
    os.makedirs(ASSETS, exist_ok=True)
    # 清理旧输出
    SIDEBAR_HTML = build_sidebar()
    # 侧边栏里的 href 都是 root 相对(如 analysis/x.html), 写入每页时需根据页面深度补前缀
    # 简化: 统计最大深度后统一加 <base>? 改为每页处理: 把 sidebar 链接前缀化
    # 这里采用: 页面里替换侧边栏链接, 加 root_pre
    count = 0
    search_entries = {}
    for src_rel, abs_path in sources.items():
        body = render(abs_path, src_rel)
        title = title_of(abs_path, src_rel[:-3])
        outp = os.path.join(OUT, out_rel_for(src_rel))
        os.makedirs(os.path.dirname(outp), exist_ok=True)
        depth = out_rel_for(src_rel).count("/")
        root_pre = ("../" * depth)
        assets_pre = root_pre + "assets/"
        # 给侧边栏内的相对链接补前缀 (它们以 analysis/ / firecracker/ / Agent.html / index.html 开头)
        sb = SIDEBAR_HTML
        sb = re.sub(r'href="(?!https?:)(?!/)([^"]+\.html)"',
                    lambda m: f'href="{root_pre}{m.group(1)}"', sb)
        page = TEMPLATE.format(
            title=html.escape(title), assets=assets_pre, root=root_pre,
            sidebar=sb, body=body, src=html.escape(src_rel))
        page = page.replace('href="index.html"', f'href="{root_pre}index.html"')
        with open(outp, "w", encoding="utf-8") as fh:
            fh.write(page)
        search_entries[src_rel] = abs_path
        count += 1
    # 首页
    home_depth = 0
    sb = re.sub(r'href="(?!https?:)(?!/)([a-zA-Z0-9_\-./]+\.html|Agent\.html)"',
                lambda m: f'href="{m.group(1)}"', SIDEBAR_HTML)
    home_page = TEMPLATE.format(
        title="Micro-VM 分析 Wiki", assets="assets/", root="",
        sidebar=sb, body=HOME_HTML, src="(首页)")
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(home_page)
    # 搜索索引
    with open(os.path.join(ASSETS, "search.json"), "w", encoding="utf-8") as fh:
        json.dump(build_search_index(search_entries), fh, ensure_ascii=False)
    print(f"生成完成: {count} 个文档 + 首页 -> {OUT}")

if __name__ == "__main__":
    main()
