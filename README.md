# Micro-VM 轻量化虚拟机分析 Wiki

本仓库是一个可浏览的静态 Wiki 站点，包含 Firecracker、Cloud Hypervisor、Kata Containers、crosvm、CubeSandbox 五个轻量化虚拟机项目的源码分析、跨项目专题对比、ARM64 网络判错样本与综合设计依据。

## 在线访问

启用 GitHub Pages 后，访问：`https://north-c.github.io/micro-vm-wiki/`

## 本地查看

```bash
python3 -m http.server 8000
# 浏览器打开 http://localhost:8000
```

## 内容

- 99 篇函数级链路文档（覆盖 4 个项目全部 chain）
- 4 份综合学习层文档（设计全景/性能依据/安全依据/改进意见）
- 4 份 Snapshot/Restore 深度专题（内核技术/内存/设备/跨项目）
- 1 份 Template 构建链路（从 OCI 镜像到 Template）
- ARM64 网络判错样本体系
