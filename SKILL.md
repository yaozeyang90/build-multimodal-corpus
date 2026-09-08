---
name: build-multimodal-corpus
description: "Build, extend, validate, and merge multimodal structural corpora from textbooks or other structured documents. Preserve hierarchy, teaching activities, source regions, images, and caption links. Use for 多模态结构语料库构建、结构标注、图文关联与分库合并; not for ordinary summaries or PDF-to-Markdown conversion alone."
---

# 多模态结构语料库构建

把材料整理为可追溯的“组织结构＋教学活动＋内容块＋图像出现”候选库，为后续比较提供结构数据；不自动构建知识图谱。适用于不同模型，执行端需能读文件、运行 Python；图像语义核验还需视觉能力。这里的“多模态”不是“多模型投票”。

用户明确要求优先于本技能中的流程建议，不改变宿主安全规则。先说明本次采用技能的哪一部分；若因技能建议改变步骤或暂停，指出具体规则与原因。不要把创建语料、上传解析服务、公开发布视为同一种授权。

## 选入口

- **新建／续建**：读 [workflow.md](references/workflow.md)、[schema.md](references/schema.md)。先盘点已有解析及成品，缺什么补什么；输入格式未知时先检查样本，不盲套解析器版本。
- **结构与图注修订**：再读 [annotation-rules.md](references/annotation-rules.md)。修改新版本，保留来源、旧值、证据、审核状态。
- **人工或多模型对齐**：读 [model-contract.md](references/model-contract.md)，冻结输入、命名空间与证据范围，不把模型答案当金标准。
- **导出、校验、分库合并**：读 [toolkit.md](references/toolkit.md)、[quality.md](references/quality.md)。优先运行随附工具，非支持格式需适配后验证。
- **仅从语料库检索**：使用 `search` / `extract` 或只读 SQL；不重新读取 PDF、不调用 OCR，不顺带修改数据库。

## 不可丢失的信息

1. 册、章／单元／主题、节／专题、正文小标题，以及阅读、活动、任务、小题在同一结构树中表达；保留原称与原位，不能按知识主题重排。
2. 页不是结构节点。内容块可跨页，片段每次只落在一页；保留物理页、印刷页、原框、规范框及坐标转换依据。
3. 每块只有一个直接归属；标题块归其节点自己，有序成员不重复收录。先定容器范围和并列区域，再建内部任务。
4. 图片文件、图片出现、组合图／子图分别建档。保存未引用图片；只按文件哈希去重，不把不同出现合并。
5. 图注以来源提示、图号和空间证据综合判断。冲突时 `target_id=null`，留候选与原因，不以最近图片强行补齐。
6. 保留原始解析与原文；清洗文本另存。规则／模型候选默认未审核，不宣称人工确认或未测量的准确率。
7. 合并保持原有 ID、字段、修订和组件版本；主键冲突先查来源，不能用忽略冲突插入消掉记录。
8. 模型生成的知识解释、答案或概念对齐不混入教材原文。未来跨版本比较的接口不是已建好的语义关系。

## 执行与交付

先用代表性小样本打通流程，再批量。维护 `inventory`、解析状态、逐册配置、待核队列与阶段检查点；已完成解析不重复付费提交。工具不内置 OCR 服务或模型 API。

脚本入口：`python3 <本技能目录>/scripts/corpus_tool.py --help`。Python 3.10+，核心仅标准库。可用 `demo` 在新目录生成完全合成的双学段材料，验证 `pack → validate → merge → export`。**脚本处理规范化数据与交付；任意 OCR 到规范结构的适配与语义判断由执行模型按规则完成，不声称一条命令自动准确解析所有版式。**

最终提供实际生成的文件链接、册数／页数／块／图片出现数、已运行的检查、待核数量与限制。用户要高中、初中、合并三库时分别输出三个独立 SQLite，嵌入所列图片与来源文件，并验证合并精确并集。未列入文件清单的文件不会被工具自动扫描打包，需先核对清单覆盖。
