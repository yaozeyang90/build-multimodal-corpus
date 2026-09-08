# 工具使用与能力边界

Python 3.10+，无 pip 依赖、不联网、不读取环境凭据。命令从本 Skill／仓库根执行；从其他位置运行时将脚本路径替换为实际位置。输入／输出路径由调用者传入，不内置教材目录。

## 合成双学段演示

```bash
python3 scripts/corpus_tool.py demo --out work/demo
python3 scripts/corpus_tool.py pack --manifest work/demo/初中.json --out work/初中.sqlite
python3 scripts/corpus_tool.py pack --manifest work/demo/高中.json --out work/高中.sqlite
python3 scripts/corpus_tool.py merge work/初中.sqlite work/高中.sqlite --release-id demo-combined-v01 --out work/合并.sqlite
python3 scripts/corpus_tool.py validate work/合并.sqlite
python3 scripts/corpus_tool.py search work/合并.sqlite 地球
python3 scripts/corpus_tool.py extract work/合并.sqlite junior_demo:asset --out work/示例图.png
python3 scripts/corpus_tool.py export work/合并.sqlite --out work/可读导出
python3 -m unittest discover -s tests -v
```

`work` 可以由工具创建，但所有目标成品必须不存在；重跑换新路径。命令报告输出到 stdout，错误到 stderr 且退出码非零。模型若保存报告，保存实际输出，不能预填通过。

演示只有合成色块、示例文本和一条待核图注，不是地理教材，不用于证明语义识别能力。

## 用于真实材料

1. 按 workflow 读取用户已有解析，针对实际 JSON 格式制作适配器，保留全部原始记录和图片。
2. 按 schema 与 annotation-rules 生成／修订逐册 18 个 JSONL 文件。工具不替代这一步的模型判断，不把任意 MinerU JSON 当成规范输入。
3. 用 demo 的清单结构创建自己的 release.json；每册目录相对于清单，所有嵌入文件 path 相对于该册目录。必须显式列入源 PDF、原解析 JSON、原图及未引用图片、逐页预览等所需文件，role 记录用途。
4. 先对小样本 pack、validate，再批量。当前实现将规范表载入内存，每次读取一个文件 BLOB；大批次按册分库再合并，若内存不足需实现分批流式适配。SQLite 执行端可处理的单 BLOB 大小也构成限制。
5. 分库、合并、导出后做外部 inventory 覆盖及视觉复核。工具不会发现“清单根本没有登记的一张图”。

## 检索与图文查看

`search` 只做精确子串查询，支持单字中文，%／_ 不是通配符。本工具未创建 FTS 索引；大型库可另建经过验证的检索索引，不能声称已经配置 FTS。

`extract` 按 asset_id 从 SQLite 取回原字节，不打开源 PDF。`export` 按 node_members 输出每册 Markdown 与全部 asset 图片，另存 caption_links.json 和 asset_index.json。Markdown 中的相邻顺序只是原成员显示顺序；实际图注目标及 unresolved 状态以关系表为准。它是数据导出，不是安全的 HTML 浏览器；渲染不可信源文本时禁用原始 HTML／脚本。

## 本版没有自动实现

PDF 解析／页图渲染、任意 MinerU 版本适配、自动出版社识别、逐页语义审查、图片构件完整性识别、人工标注平台连接、模型 API 调用、知识图谱和跨版本概念匹配。SKILL.md 给出这些必要工作环节的执行指引，宿主模型需按输入与权限完成，不能把演示通过当成真实批次已完成。

merge 支持本工具生成且 schema_version 相同的库，扩展列做并集，主键重复即失败；不同历史 schema 不自动迁移。原组件以只读方式打开，不改输入文件。失败时没有发布目标成品，但可能保留 `.partial-*` 工作目录用于诊断；确认其为本次失败输出后再按用户需要清理。
