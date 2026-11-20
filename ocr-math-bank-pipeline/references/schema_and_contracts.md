# 数据契约与 Schema 规范（Schema & Contracts）

本文档为 Stage 1–3 与状态管理文件的唯一权威 Schema 规范，所有生产脚本、校验脚本（`validate_enriched.py`）、导出脚本（`export_output.py`）与测试均必须严格对齐。

---

## 1. `staging/chXX_raw.jsonl`（Stage 1 原始抽取契约）

每行 1 个 JSON 对象，UTF-8 无 BOM；按章内 `id` 严格升序连续编号。

### 必需顶层字段（16 键）

| 字段 | 类型 | 约束与说明 |
| :--- | :--- | :--- |
| `id` | `string` | 严格匹配 `^ch\d{2}_\d{3}$`，章节号与章内序号从 `001` 起连续递增（如 `ch28_001`） |
| `chapter` | `int` | 章节整数（如 `28`），必须与 `id` 前缀一致 |
| `chapter_title` | `string` | 原始章标题（如 `"第二十八章 平面直线图形(高年级卷)"`） |
| `section` | `string` | 所属小节号（如 `"28.1"`、`"1.2.4"`），无小节时可为 `""` |
| `section_title` | `string` | 所属小节标题，无则 `""` |
| `question` | `string` | **初步清洗后的纯净题干**：已剥离 `例 N` / `N.` 前缀、竞赛出处括号、Markdown 图片语法 `![]()` |
| `source_images` | `list[string]` | 相对工作区根目录的原书配图路径（如 `["下_001_200/images/page_54_image_4.jpg"]`），无图则为 `[]` |
| `image_captions` | `list[string]` | 捕获到的图注（如 `["第15题图"]`），无则 `[]` |
| `ocr_image_summaries` | `list[string]` | 从 OCR 原文 `<details><summary>` 中提取的切图类型摘要（如 `["text_image"]`） |
| `stripped_source_text` | `list[string]` | 被剥离的竞赛/考试出处原文留痕，供审计核对防误删数学条件 |
| `book_solution_hint` | `string` | 原书对应解析或参考答案文本（**内部参考用，严禁进入 `output/`**；缺失时为 `""`） |
| `book_solution_images` | `list[string]` | 原书解析附图路径（内部参考用） |
| `source_chunk` | `string` | 来源分卷标识（如 `"上_001_256"`） |
| `source_pages` | `list[int]` | 来源页码整数列表（由图片文件名或上下文页码游标追踪） |
| `rule_tags` | `object` | 规则预填标签，含 4 键：`domain`、`candidate_topics`（非空数组）、`format_hint`、`visual_hint` |
| `ocr_precheck_flags` | `list[string]` | Stage 1 自动预警枚举数组，正常为空 `[]` |

### `ocr_precheck_flags` 合法枚举

| 枚举值 | 触发条件与 Stage 2 核查动作 |
| :--- | :--- |
| `MISSING_IMAGE_SUSPECTED` | 题干含“如图/下图/右图/左图/题图/如图所示/图中”，但 `source_images == []` 且无 Markdown/HTML 表格；Stage 2 必查是否真实缺图 |
| `UNBALANCED_LATEX` | 题干中 `$$` 或未转义 `$` 个数为奇数；Stage 2 需核对是否 OCR 漏掉公式定界符 |
| `BROKEN_IMAGE_PATH` | `source_images` 中存在磁盘上不存在的文件路径 |
| `EMPTY_OR_TINY_QUESTION` | 去除空白后题干有效字符 `< 8` |
| `MISSING_SOLUTION_HINT` | `book_solution_hint` 为空（如答案分卷未录入）；Stage 2 必须独立推导与 Python 验算，严禁以此偷懒标 `flagged` |
| `SUSPECT_DIVISIBILITY_TIMES` | 数论上下文（如 31~35 章或含整除/倍数关键词）出现孤立 `<num> \times <num>`，疑似把整除号 `∣` 或 `∤` 误识为 `\times` |

---

## 2. `staging/enriched/chXX_enriched.jsonl` 与分片 `shards/chXX_pK.jsonl`

分片文件与合并终稿采用完全一致的 JSONL Schema，要求与 `chXX_raw.jsonl` **1:1 ID 对齐**，不得多题、少题或重复 ID。

### 顶层必需键（7 必需 + 1 推荐保留）
- 必需：`id`、`chapter`、`chapter_title`、`question`、`source_images`、`tags`、`audit`
- 推荐保留：`book_solution_hint`（仅供内部核验，Stage 3 导出时自动丢弃）

### `question` 纯净度硬校验规则
`validate_enriched.py` 会直接拦截以下残留：
- 不得含 `<details` / `</details` / `<summary` / `</summary`
- 不得含 `#{1,6}\s*解析`
- 不得含 `答案[:：]`
- 不得以 `^\s*例\s*\d+` 开头
- 不得含 Markdown 图片语法 `!\[[^\]]*\]\([^)]+\)`

### `tags` 7 字段规范

| 字段 | 类型 | 约束 |
| :--- | :--- | :--- |
| `domain` | `string` | 单选，必须在 `taxonomy.yaml` `domains.*.name` 内 |
| `topic` | `list[string]` | `1..2` 个去重受控词；`topic[0]` 必须属于 `topics.<domain>`；跨板块综合题 `topic[1]` 允许从其他板块选取 |
| `method` | `list[string]` | `1..3` 个去重受控词，从 `methods.通用数学思想` 与 `methods.专项解题模型与技巧` 平铺混选 |
| `difficulty` | `int` | 严格整数 `1` / `2` / `3` / `4`（禁止字符串 `"3"` 或 `bool`） |
| `visual` | `string` | 单选受控词；**强绑定规则**：`len(source_images) > 0` 时严禁为 `"纯文字"`；`len(source_images) == 0` 时必须为 `"纯文字"` |
| `format` | `string` | 单选受控词（`计算题` / `填空题` / `解答题` / `操作构造题` / `判断说理题`） |
| `extra_tags` | `list[string]` | `0..2` 个去重字符串；每个长度 `2..8` 字符；禁止含 `#`；禁止与任何受控词表（`domains`/`topics`/`methods`/`visual`/`format`/`difficulty.name`）重名 |

### `audit` 字段规范与三态联动矩阵

- `audit.verified_by`：非空 `list[string]`，元素仅限以下 **5 个合法枚举**：
  `vision_diagram_check`、`solution_crosscheck`、`python_calc`、`symbol_set_check`、`crop_check`

| `audit.status` | `solvable` | `ocr_fixed` | `original_question` | `fix_reason` | `flag_reason` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`pass`** | `true`（`bool`） | `false` / 可选 | `null` | `null` | `null` |
| **`auto_fixed`** | `true`（`bool`） | **必须 `true`** | **非空字符串且 `!= question`** | **非空字符串** | `null` |
| **`flagged`** | `false`（通常） | `false` | `null` | `null` | **非空字符串（说明具体缺陷）** |

> 可附加 `audit.note`（字符串）记录验算过程与核对摘要，便于 Reviewer 复核。

---

## 3. Stage 3 交付与隔离契约

章节目录命名规则：`ch{chapter:02d}_{short_name}`。`short_name` 由 `export_output.py` 的 `sanitize_chapter_short_name()` 自动剥离 `第X章`、处理 `五式之X——` 副标题并移除非法路径字符（限 32 字符）。

### 3.1 纯净交付区 `output/chXX_<净短名>/`
仅导出 `audit.status in {"pass", "auto_fixed"}` 的题目：
- **`problems.jsonl`**：**严格仅含 5 键**：`id`, `chapter`, `question`, `images`, `tags`（其中 `images` 为章内相对路径 `["images/chXX_NNN_1.jpg", ...]`）。
- **`images/`**：拷贝并重命名为 `{id}_{idx}{ext}`（`idx` 从 `1` 开始）。
- **`md/chXX_NNN.md`**：YAML Frontmatter + 空行 + 纯净题干 + 相对图片链接 `![](../images/chXX_NNN_k.ext)`：

```markdown
---
id: ch28_001
chapter: 28
domain: 几何
topic:
- 勾股定理与弦图问题
method:
- 弦图与勾股构造
- 容斥原理与韦恩图
- 割补平移与等积变形
difficulty: 2
visual: 几何图形
format: 解答题
extra_tags: []
images:
- ../images/ch28_001_1.jpg
---

两张相同的长方形纸片，每张纸片的面积为48平方厘米……

![](../images/ch28_001_1.jpg)
```

### 3.2 疑难隔离区 `flagged/chXX_<净短名>/`
仅当该章 `flagged_count >= 1` 时创建：
- **`problems.jsonl`**：**6 键**：`id`, `chapter`, `question`, `images`, `tags`, `flag_reason`。
- **`images/`**：隔离该题对应的原图 `{id}_{idx}{ext}`。
- **`md/chXX_NNN.md`**：Frontmatter 增加 `flagged: true` 与 `flag_reason`，正文顶部增加单行告警引用块：

```markdown
---
id: ch28_012
chapter: 28
...
flagged: true
flag_reason: 题干与配图及原书解析存在矛盾...
images:
- ../images/ch28_012_1.jpg
---

> ⚠️ 隔离原因（flagged）：题干与配图及原书解析存在矛盾...

如图, 正方形 $ABCD$ 的边长为 8...

![](../images/ch28_012_1.jpg)
```

---

## 4. `staging/waves.json` 与 `staging/wave_state.json`

### `staging/waves.json`（波次规划文件）
由 `init_project.py --plan-waves` 生成，供通用 `wave_workflow.py` 读取各波次章节分配：

```json
{
  "version": 1,
  "wave_target_qs": 250,
  "waves": {
    "1": {"chapters": [2, 3, 4], "total_questions": 240, "questions_with_images": 7}
  }
}
```

### `staging/wave_state.json`（原子断点状态文件）
每次以 `.json.tmp` + `fsync` + `os.replace` 原子写盘：

```json
{
  "version": 1,
  "pilot_completed": [1, 28],
  "empty_chapters": [26],
  "chapters": {
    "ch03": {
      "chapter": 3,
      "status": "approved",
      "verdict": "APPROVED",
      "total": 50,
      "pass": 40,
      "auto_fixed": 9,
      "flagged": 1,
      "sampled_pass_count": 40,
      "false_pass_count": 0,
      "review_report": ".agents/teamwork/wave_reviews/wave_1_review_ch03.md"
    }
  },
  "waves": {
    "wave_1": {
      "chapters": [2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
      "all_approved": true,
      "absorbed_repros": [],
      "updated_at": "2026-11-20T14:29:53Z"
    }
  },
  "updated_at": "2026-11-20T14:29:53Z"
}
```

---

## 5. `taxonomy.yaml` 定制规范

新书定制 `taxonomy.yaml` 时须保持以下机器可解析结构（见 [taxonomy_template.yaml](../resources/taxonomy_template.yaml)）：
1. **`domains`**：每项含 `name`、`book_chapters`（整数列表）、`desc`；支持跨章映射如 `cross_ref_sections`（例：第 35.3 节改标 `逻辑推理`）。
2. **`topics`**：按 `domain` 名称分组，每项含 `name`、`desc`、`chapters`（支持 `"28.1"` 小节级或 `"8"` 整章级前缀自动继承）。
3. **`methods`**：严格分两级：`通用数学思想`（列表）与 `专项解题模型与技巧`（按板块分组的字典），打标时由 LLM 平铺选入 `tags.method`；`topic` 与 `method` 语义正交不重名（`topic` 回答“考什么场景/模型”，`method` 回答“用什么思想/招式破局”）。
4. **`difficulty`**：`level: 1..4`（整数）与 `name`（如 `1-基础`）。
5. **`visual`**：必须包含 `"纯文字"`（`require_vision: false`）及其他多模态类型（`require_vision: true`）。
6. **`format`**：每项含 `name` 与 `regex_hints`，供 Stage 1 按优先级正则预判 `format_hint`。
