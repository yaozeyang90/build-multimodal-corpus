# 数据契约与历史兼容

采用 18 张核心表的 JSONL 交换格式；字段为 UTF-8 JSON，每行一对象，空表仍有空文件。未知字段保留；不靠删除列实现适配。脚本把标量存为 SQLite 标量，数组／对象存 JSON 文本，保留额外列。不是声称任意外部数据库可直接导入。

## 核心表

| 表 | 主键 | 主要内容 |
|---|---|---|
| textbooks | textbook_id | 学段、年级、series、volume、版次及证据、来源身份 |
| source_documents | document_id | textbook_id、path、sha256、源文件身份 |
| parse_runs | parse_run_id | textbook_id、解析器版本、分段、状态和参数 |
| pages | page_id | textbook_id、physical_page、printed_page_raw、preview_path |
| parse_records | parse_record_id | textbook_id、page_id／physical_page、原记录 payload、解析运行 |
| structure_nodes | node_id | textbook_id、parent_id、node_kind、level_role、原名、边界 |
| node_members | membership_id | node_id、member_type=node/block、member_id、order_key、顺序证据 |
| blocks | block_id | textbook_id、owner_node_id、block_type、文本三层、source_record_ids、physical_page |
| block_fragments | fragment_id | block_id、page_id、bbox、原框、文本层与字符跨度 |
| media_assets | asset_id | textbook_id、path、sha256、alternate_paths、derivation |
| media_occurrences | occurrence_id | textbook_id、block_id、asset_id、parent_occurrence_id、图号、审核状态 |
| spans | span_id | block_id、text_layer、text_start、text_end、用途和文本版本 |
| structural_links | link_id | textbook_id、关系类型、source_type/id、target_type/id、候选和证据 |
| annotation_records | annotation_id | 对象、producer_type、model_id、run_id、判断、证据及版本 |
| qc_records | qc_id | 对象／页、问题类型、待核原因与状态 |
| revisions | revision_id | 旧值、新值、对象、证据、操作者和版本 |
| table_cells | cell_id | table_block_id、行列、rowspan/colspan、原文与来源 |
| continuation_candidates | candidate_id | 跨页／跨栏延续候选与证据，不直接当已确认关系 |

除根节点，每个节点有同册父节点；块、片段、出现和关系必须指向存在的同册对象。跨册概念关系不属于本协议的文档结构关系。

node_kind：book / organizational_unit / pedagogical_container / task / item / front_matter / back_matter。草稿不确定类型可以留空并待审；`pack` 输出面向技术有效候选，不把未定父节点伪装有效树。

block_type：heading_text / paragraph / list_item / figure / caption / table / formula / figure_text / note / response_space / page_furniture。历史标签迁移先登记映射，不原位批量改旧库。

## 区间与身份

边界 `boundary_start`、`boundary_end_exclusive` 为 `{physical_page: 1, y: 0.2}`，半开区间。书末可用最后页＋1、y=0。并列区域另存 spatial_scope_candidate／parallel_group_id，不能仅靠线性区间解释空间包含。

`bbox=[x0,y0,x1,y1]` 使用 0–1、左上原点。字符跨度基于 Unicode 码点，使用 text_raw / text_clean / text_normalized 中指定层，区间 `[start,end)`。

新来源 ID 建议使用 `hash(source_sha256 + stable_book_key + source_locator + object_kind)`；输入未变应重跑稳定，不按数据库全局行号命名。已发布 ID 不因换路径、换显示标题或合并而重算。对象拆合通过 revisions 与来源映射表达。

## 文件清单和 SQLite

`release.json` 示例由 `demo` 生成。它包含 release_id 和 books 数组，每册有 alias、相对于清单的 directory、files 数组。files 项含 path、role，可加 sha256；册内相对路径不允许绝对路径、上跳或符号链接。

files 是明确白名单，不递归打包目录。每个 media_assets.path、alternate_paths、pages.preview_path、source_documents.path 必须列入。所有未引用原图和原始解析文件也应列入；它们是否齐全仍需与解析输出 inventory 核对，不能从数据库自身证明不存在漏文件。

辅助表：collection_metadata；book_catalog（册别与组件版本）；file_blobs（sha256、bytes、mime_type、content）；file_entries（collection-relative path、book_alias、role、sha256）；asset_files、page_files。

规范路径相对于 book_catalog.path_prefix，file_entries 路径相对于集合。文件字节按 SHA-256 去重，文件名映射与出现不去重。工具保留文本、原解析 JSON、图片／页预览／源文件，但仅包含显式清单列出的文件。

## 与既有语料的关系

字段体系提炼自曾经实施的教材候选库流程，保留 18 表思路。没有打包任何旧教材数据或私有代码副本。旧库可能含附加表、历史状态和不同细字段；导入先做只读模式检查，显式映射后用独立输出试验。

随附 `merge` 仅支持本工具相同 schema_version 的交付；不自动迁移历史库。若用户要求历史库原样保留，应复制旧库，使用经测试的专门列并集适配器，验证每组件源列 EXCEPT 差集为零；不要为满足新工具把原库重建掉。
