# Build Multimodal Corpus

多模态结构语料库构建 Skill · v0.1.0

将“已有解析 → 来源标准化 → 组织与活动标注 → 图文关联 → 质量核查 → 分库与合并交付”封装成可移植的模型执行流程。源于中学地理教材语料实践，但不硬编码教材内容、出版社数量、机器目录或模型供应商。

**这是候选语料构建流程＋确定性数据工具，不是全自动 OCR 产品，也不承诺所有模型均可无工具直接运行。**

## 能做什么

- 保留册—章／单元—节／专题—栏目—任务—小题，以及原名称、位置和有序成员。
- 保存原文、来源页与区域；区分图像文件、出现次数、组合图和图注。
- 图注冲突留空并进入待核队列，不强行配对。
- 按模型中立协议组织人工／模型结果与来源 ID 对齐。
- 校验规范 JSONL，嵌入图片打包为单文件 SQLite，导出带图片的 Markdown。
- 分别输出初中、高中、合并库；合并核验原有字段精确并集，不改源库。

## 交给其他大模型使用

支持 Agent Skills 的宿主：把整个仓库目录作为一个 Skill 安装，入口为 [SKILL.md](SKILL.md)。文件夹建议命名 `build-multimodal-corpus`。宿主安装位置各异，按对应工具的当前说明选择；不要只复制入口而遗漏 scripts／references。

不支持自动发现的模型：将本仓库提供为可访问文件，再发送：

```text
请读取 build-multimodal-corpus/SKILL.md，并按其中的路由读取所需参考文件。
输入目录是：<我的解析结果目录>。
构建保留组织结构、教学活动、图片及图注证据的候选语料。
复用已有解析，不未经授权上传；输出目录是：<新目录>。
需要初中、高中、合并三个 SQLite 文件，提供实际校验结果与待核项。
```

模型需要文件访问和 Python 3.10+ 执行工具；核图需要视觉能力。纯聊天界面只能指导或给出标注建议，不能直接操作用户磁盘。本仓库没有自动多模型调度服务。

Codex 也可显式调用 `$build-multimodal-corpus`。目录格式与渐进加载方式参考 [OpenAI 官方 Build skills 文档](https://learn.chatgpt.com/docs/build-skills)；`agents/openai.yaml` 是可选宿主元数据，其他模型可忽略。

## 先跑一个不含教材的示例

在仓库根执行：

```bash
python3 scripts/corpus_tool.py demo --out work/demo
python3 scripts/corpus_tool.py pack --manifest work/demo/初中.json --out work/初中.sqlite
python3 scripts/corpus_tool.py pack --manifest work/demo/高中.json --out work/高中.sqlite
python3 scripts/corpus_tool.py merge work/初中.sqlite work/高中.sqlite --release-id demo-v01 --out work/合并.sqlite
python3 scripts/corpus_tool.py validate work/合并.sqlite
python3 scripts/corpus_tool.py export work/合并.sqlite --out work/Markdown
python3 -m unittest discover -s tests -v
```

示例自动生成 2 册极小合成数据，不联网、无需账号或 API 密钥。真实数据需先按流程生成 18 表 JSONL 和文件清单，**工具不会把任意 PDF／MinerU 输出直接转换成可靠结构**。详见 [工具使用](references/toolkit.md)。

## 仓库内容

```text
SKILL.md                 模型入口与关键约束
agents/openai.yaml       可选显示元数据
references/              流程、结构规则、schema、模型对齐、质量与命令说明
scripts/corpus_tool.py   pack / validate / merge / search / extract / export / demo
scripts/package_skill.py 白名单打包发布仓库与 ZIP，不包含语料文件
tests/                   合成数据的行为与回归测试
.github/workflows/       离线测试 CI
```

## 质量与授权边界

技术检查不等于 OCR／结构／图注语义正确。真实批次需要 inventory 覆盖核对及视觉／人工复核；本版不提供人工金标准或准确率数字。历史语料库需模式适配，不声称旧版本任意 SQLite 即插即用。

仓库仅含流程、原创工具及合成样本，不含教材 PDF、教材原文／图片、私人数据库、API 凭据或个人路径。工具代码采用 MIT；该许可不覆盖使用者输入的教材及生成的教材内容。发布语料需自行确认相应权利。

## 上传 GitHub

本地准备和远程发布分开。先提供 GitHub 用户／组织、仓库名与 public/private 选择，再通过已有授权连接或本机登录发布；不要发送密码或令牌。推荐仓库名 `build-multimodal-corpus`。上传前检查只有本 README 所列代码和文档；不要把 work 或真实语料目录上传。

首次发布可标记 `v0.1.0`。本仓库准备完毕并不表示已经建立了线上地址。

维护者可运行 `python3 scripts/package_skill.py --out <仓库外的新发布目录>` 重建代码／文档白名单包及 SHA-256 清单。仍需人工检查内容与传播权利。

## English summary

A model-neutral Agent Skill for evidence-preserving multimodal structural corpora. It unifies document hierarchy and pedagogical activities while separating source blocks, page fragments, media assets, occurrences, and caption relations. The Python standard-library toolkit validates canonical JSONL, packages self-contained SQLite files, checks exact-union merges, and exports text/images. OCR adapters and semantic annotation are guided tasks, not bundled automatic services. All examples are synthetic. Read SKILL.md first.
