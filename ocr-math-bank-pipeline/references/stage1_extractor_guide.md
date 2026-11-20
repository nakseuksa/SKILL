# Stage 1 抽取实战指南（Stage 1 Extractor Guide）

每本新书的 OCR 版式与切图结构各不相同，因此 `scripts/extract_raw.py` 需要按书定制。本文档沉淀 Stage 0 侦察方法、6 大常见抽取陷阱的标准解法，以及必配预警与单元测试基线。完整参考代码见 [extract_raw_reference.py](../examples/extract_raw_reference.py)。

---

## 1. Stage 0 数据侦察清单

编写 `extract_raw.py` 之前，必须先抽样核对原始分卷与图片目录，严防源头串卷或结构误判：

1. **分卷与切图目录完整性核对**：
   - 核查每个分卷文件夹 `<chunk>/part_*.md` 中引用的 `images/page_XXX_image_Y.jpg` 是否全部真实存在于 `<chunk>/images/`。
   - **跨卷比对防串目录**：检查相邻分卷的 `images/` 首尾文件名、页码区间与文件数，确认切图未被重复拷贝或错配（详见 [lessons_learned.md](./lessons_learned.md) 第 1 条）。
2. **目录页（TOC）与前后言边界**：
   - 定位正文真正起始行（如 `# 第一章`），以及续卷起始行（续卷通常无目录，从索引 `0` 开始）。跳过封面、序言与目录页，避免把目录中的“第一章……”误当成正文章节边界。
3. **小节、例题与习题/答案层级模式**：
   - 统计全书标题级别（`#` / `##` / `###`）：章标题、小节号（`1.1.1` / `28.2`）、例题写法（`例 1` / `【例 10-1】` / `例 14-A`）、解析入口（`## 解析` / `【解析】` / `解析:`）、真题/练习块（`## 真题重现`）与参考答案块（`## 参考答案`）。
   - 排查书中非题干正文（如 `## 延伸`、`## 练一练`、`结语`）及跨章/跨卷拼接边界（如一章跨两个 Markdown 分卷）。

---

## 2. 六大经典 OCR 抽取坑及标准解法

### 坑 1：跨分卷无缝拼接与页码连续追踪
- **症状**：一章或一组 `真题重现` 跨两个分卷（如《明心数学》Ch 23 末组真题前几题在 `上_001_256`，后几题和 `参考答案` 在 `上_257_313`；Ch 32 在 `32.3` 节跨 `下_001_200` → `下_201_400`），分卷单独解析会导致题数与答案错位或断链。
- **标准解法**：
  - 实现 `load_and_stitch_chunks()`：先将各分卷内的 `![](images/...)` 重写为带分卷前缀的 `![](<chunk>/images/...)`，同时提取图片文件名 `page_(\d+)_` 维护运行页码游标。
  - 将跳过目录后的全部行按顺序拼接为统一 `list[LineItem]`（携带 `chunk`、`line_no`、`page`、`text`），再整体解析章节与 `真题重现 <-> 参考答案` 配对。

### 坑 2：浮动图题 `第N题图` 双向重绑与错标图号保护
- **症状**：排版双栏或分页时，OCR 经常把 `第 k 题图` 放在第 `k-1` 题末尾或第 `k+1` 题开头，导致图片错绑给相邻题目。个别原书答案图还会把题号印错（如第 4 题的唯一图注印成 `第 5 题图`）。
- **标准解法**（`parse_zhenti_block` / `parse_reference_answers`）：
  1. 先按顺序题号 `1, 2, ..., N` 建立初始行归属 `assigned_q`。
  2. 扫描所有独立图注行 `第 k 题图`，把图注行及向前紧邻的图片、Markdown/HTML 表格、独立数学公式块与子图标签（`图1`、`正视图` 等）统一重绑到题 `k` 并标记 `claimed_by_cap`。
  3. **参考答案错标图号保护（Typo Guard）**：当答案块中 `raw_q != k`、且 `raw_q` 本身无自己的图注、只有这 1 张图且文字引用了“如图/下图”，而题 `k` 全文未提及图形时，保留给 `raw_q`，不盲目重绑给 `k`。

### 坑 3：多图题防向后抢图与后置孤儿图归位
- **症状**：`第 k 题图` 漂移到题 `raw_q` 内部时，向后扫描很容易跨空行把 `raw_q` 自己的配图（例如 `第 raw_q 题图` 之后紧邻的裸图）一起抢走；反之，紧跟在 `第 raw_q 题图` 后面、位于下一题题号 `Q(raw_q+1)` 之前的未认领图，有时属于 `Q(raw_q+1)` 的前置浮动图。
- **标准解法**：
  - Pass 1 向后扫描时，若 `raw_q != k` 且已拿到 1 张图，遇到下一张图时除非存在明确子图标签（`last_img_had_sublabel`）或紧邻的同页连续裸图条带（`_is_bare_strip_pair`，无 `<details>` 且行距 `<=3`），否则立即 `break` 停止抢图。
  - Pass 2 扫描每题 `Q(qnum)` 起始行之前的未认领图片：若上一题 `Q(qnum-1)` 内部已经出现过自己的 `CAP_RE` 归属图，则将该紧邻的未认领图归还给 `Q(qnum)`。

### 坑 4：平衡括号剥离竞赛出处而保留数学条件括号
- **症状**：简单正则 `（[^）]+）$` 会被嵌套括号截断（如 `(2009年“迎春杯”（现为“数学花园探秘”）5年级初赛)`），或者误删题干末尾真正的数学条件括号（如 `(假定平面上任何两点间都有路相通)`、`(注: 1×144 和 144×1 是同一种分法)`）。
- **标准解法**：
  - 实现逆向深度扫描 `extract_trailing_balanced_bracket(s)`：从行尾 `)` / `）` / `》` 向前追踪括号嵌套深度 `depth`，精确提取完整最外层平衡括号块，并兼容 `UNCLOSED_COMP_TAIL_RE` 清理 OCR 重复印出的半截未闭合出处。
  - 白名单 + 黑名单双重门禁：先用排除前缀 `COMP_EXCLUDE_PREFIX_RE`（`注:`、`假定`、`假设`、`单位:`、`其中`、`不含`、`保留`、`取` 等）放行数学条件；再命中 `COMP_STRICT_RE`（年份+赛事名、第X届、杯赛名、初赛/复赛/决赛/A卷等，且排除 `——` 引出的古籍名如 `《九章算术》`）才执行剥离，并记录进 `stripped_source_text` 供抽检。

### 坑 5：`例 14-A/B` 编号变体与解析/正文引用防误切、防泄漏
- **症状**：
  - 正文讲解常出现 `"例 1 和例 2 都可以"`、`"例 16 展现了"`，若直接按 `^例 \d+` 切题会把正文碎句当成空题目；而 `【例 10-1】`、`例 14-A`、`例 14-B` 又容易漏切。
  - 题干结束后紧跟 `## 解析`、`【解析】`、`解析:`，或解答末出现子标题（`五年级的你:`、`解法 1:`），以及 OCR 生成的 `<details><summary>text_image</summary>...</details>` 图注块，若不清理会污染题干或丢失图片类型提示。
- **标准解法**：
  - 预处理先运行 `strip_details_blocks()`：剔除 `<details>...</details>` 块，同时把其中 `<summary>` 里的视觉类型标签提取到 `image_summaries` 映射表 `(chunk, line_no, img_path) -> summary`，既洁净文本又保留给 `visual_hint` 使用。
  - 使用 `is_real_example_start(items, idx)`：先过 `EX_PROSE_EXCLUDE_RE`，再向后前瞻——**仅当在下一章/节/例题/`真题重现` 之前确切遇到 `解析` 标记时**才认定为真实例题；并在抽取题干时同时剥离 `例 14-A` 等复合前缀，把解析及 `SOL_SUBHEAD_RE` 全部收归 `book_solution_hint`。

### 坑 6：未引用 `equation/table` 切图建索引兜底
- **症状**：部分复杂竖式、多行连分数或大型表格在 OCR 时被切成了 `*_equation_*.jpg` 或 `*_table_*.jpg`，但 Markdown 正文里并未引用它们（或用错乱 LaTeX 替代），Stage 2 遇到损坏公式时难以快速定位原始截图。
- **标准解法**：
  - `build_equation_table_index(all_referenced_images)` 扫描全部分卷 `images/` 目录，将所有未被任何 Markdown 引用的 `*_equation_*` 与 `*_table_*` 按 `chunk -> page -> [paths]` 索引落盘至 `staging/equation_table_index.json`，供 Stage 2 校验或人工复核按页码一键反查。

---

## 3. Stage 1 必配预警与单元测试基线

### 必须输出的 3 类重点预警
在 `staging/extract_report.json` 的 `ocr_precheck_summary` 中聚合索引：
1. `MISSING_IMAGE_SUSPECTED`：题干引用附图词但 `source_images` 为空且无表格。
2. `SUSPECT_DIVISIBILITY_TIMES`：数论语境孤立 `\times`，提示检查是否为整除符误识。
3. `MISSING_SOLUTION_HINT`：原书无参考答案（如分卷缺失），提醒 Stage 2 必须独立算题核验。

### `tests/test_extract_raw.py` 必测断言清单
1. **全章存在与题数对齐**：所有章节 `chXX_raw.jsonl` 存在，总题数与 `extract_report.json` 精确相等；仅已知概念/导言章为 0 题。
2. **ID 唯一与章内连续**：`chXX_001 .. chXX_NNN` 严格连续、无重复、无跳号。
3. **Schema 与 `rule_tags` 受控校验**：16 键完整；`domain` / `candidate_topics` / `format_hint` / `visual_hint` 全部命中 `taxonomy.yaml`。
4. **图片磁盘存在与非空**：全部 `source_images` 与 `equation_table_index.json` 路径在磁盘存在且 `stat().st_size > 0`，总数与报告一致。
5. **纯净度零残留**：`question` 与 `book_solution_hint` 无 `<details>`/`<summary>`，`question` 无 `例 N` 前缀。
6. **高危边界回归断言**：跨分卷衔接块题/答 1:1 对齐（`diff == 0`）、浮动 `第N题图` 重绑样例、数学条件括号保留样例（如 `注:`、`假定`）。
