# 结构标注规则（可迁移版 0.1）

这是流程规则，不是出版社模板。新增版式以来源证据适配；保留项目自己的手册版本。

## 组织与活动

- R-N01：`organizational_unit` 是统领正文的编排单位；`level_role` 记录 chapter/unit/theme/section/topic/learning_section/subheading/unclassified。不由 Markdown 的井号数确定层级，不改原称。
- R-N02：页眉、目录条目、图内标题不重复建正文章节；缺省层级不补造。独立章际模块按原位挂册根，不按知识相关性移入前章。
- R-C01：教学容器包含原有情境、材料、图表、问题、提示与评价。`raw_column_label` 与 `raw_title` 分开；合写标识另存 `raw_marker_text`，显示时不重复题名。
- R-C02：跨页栏目只延伸到有证据的恢复正文处；同名栏目不是同一容器。用片段及成员表达跨页，而不是跨页大矩形。
- R-C03：并列目标／任务／成果区先定空间范围，再建内部小题，避免左栏题目被右栏栏目吞并。保留 `parallel_group_id`，显示顺序不冒充唯一阅读顺序。
- R-T01：明确完整任务建 task；独立作答单元建 item；条目型知识概括仍是 list_item，不因数字或问号自动变题目。“活动目标／过程／评价”保留在活动内部。
- R-T02：只保存教材中实际存在的答案，不能用模型答案补齐。未检查答案区不能断言全书无答案。

## 内容、归属与定位

- R-B01：自然段不因换行／换栏／换页自动拆成逻辑块。每个 fragment 对应一页一处区域，原解析记录与拆合映射保留。
- R-B02：每块唯一直接 owner；节点标题归自身，既由 heading_block_ids 引用，又在自身成员中出现一次。祖先通过遍历获取，不复制内容。
- R-O01：同一容器的 node_members 混排子节点与块。编号、箭头、连续分栏是顺序证据；并列材料可用 display_only／parallel，不作为序列金标准。
- R-P01：物理页、印刷页、分段页索引分开；规范框左上原点、0–1。没定位证据则空值，不补“看起来合理”的坐标。
- R-X01：text_raw 不覆写，text_clean 和 text_normalized 分层。跨度为明确文本层／版本上的 Unicode 码点半开区间，不混用 UTF-16。OCR 修订不能偷偷改变原教材内容。

## 图文、表格与留白

- R-I01：asset 是文件，occurrence 是教材的一次出现；同文件多次出现分别记录。保留孤立／未引用文件，近似图不自动去重。
- R-I02：组合图保留整体与子图层级，共用图注指向有证据的整体；解析切片数不作为原图数。若没有完整整体文件，记录不完整并保留切片，不声称已补全。
- R-I03：地图图例、比例尺、指向标、坐标轴等实际存在构件不可随意裁掉。不生成原书没有的图件；图内问题和图内文字不得重复算作正文。
- R-CAP01：caption_of 从图注 block 指向 media_occurrence；note_of 与 explicit_refers_to 分开。图号只是局部证据，跨章重复图号不可全库直接匹配。
- R-CAP02：几何、图号、栏目范围冲突时 target_id=null、review_status=unresolved，保留候选与 evidence_refs。模型置信度高不能消除证据冲突。
- R-TAB01：表格保留逻辑表、HTML／原图、单元格及行列合并信息；跨页续表用片段，不造重复表。缺结构时保留原材料并待核，不能制造单元格。
- R-SP01：显式作答横线／绘图区保留 response_space；一般空白页边不标。前后置材料和 page_furniture 保存但不混入正文流。

## 状态

规则与模型输出通常为 unreviewed；争议为 unresolved／needs_adjudication。human_confirmed 只用于有真实人工审阅记录的对象。图像可解码不等于 `media_integrity=complete`；只有实际核对必要构件后才能这样标。
