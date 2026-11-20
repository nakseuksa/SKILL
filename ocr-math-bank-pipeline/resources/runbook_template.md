# 《{{BOOK_NAME}}》题目清洗、多维打标与交付流水线 Runbook

> 本文档由 `ocr-math-bank-pipeline` 技能脚手架生成，用于规范 `{{BOOK_NAME}}` 从 Stage 1 原始抽取到 Stage 3 交付导出的全流程执行、质量门禁与断点续传。

---

## 1. 项目目标与已锁定业务规则

将全书各章原始 OCR Markdown 与切图重构为**题干纯净、多维打标、自包含可独立交付**的题库，并隔离存在印刷缺陷或无法独立求解的疑难题目：

1. **中性题号与纯净交付**：
   - 题号统一采用中性按章顺序编号 `chXX_NNN`（如 `ch01_001`），**不区分例题与练习题**，**剥离竞赛/测试出处括号**（保留数学条件括号），**不输出解析与答案**。
   - `output/chXX_<净短名>/problems.jsonl` 仅保留 5 个交付字段：`id`, `chapter`, `question`, `images`, `tags`。
   - `output/chXX_<净短名>/md/chXX_NNN.md` 同步输出 YAML Frontmatter + 纯净题干 + 相对图片链接 `![](../images/chXX_NNN_k.ext)`。
2. **`flagged` 严格隔离规则**：
   - `pass` 与 `auto_fixed` 导出至 `output/chXX_<章节净短名>/`。
   - `flagged` 题目**完全剥离出 `output/`**（无文本、无 `.md`、无残余图片），单独隔离至 `flagged/chXX_<章节净短名>/`：
     - `problems.jsonl` 包含 `id, chapter, question, images, tags, flag_reason`；
     - `md/chXX_NNN.md` 顶部包含 `flagged: true`、`flag_reason` Frontmatter 及 `> ⚠️ 隔离原因（flagged）：<flag_reason>` 引用块；
     - 若某章 `flagged == 0`，**不生成空目录**，且每次导出前先清理旧目录防止幽灵文件残留。
3. **只读基线保护**：
   - 严禁修改原始 OCR Markdown/图片分卷、`taxonomy.yaml`、`scripts/extract_raw.py` 及 `staging/chXX_raw.jsonl`。
4. **100% 确凿 OCR 自动修复与留痕**：
   - 仅当经配图 + 原书解析 + 数学验算三重实证存在明确 OCR 错字时，置为 `auto_fixed`（`ocr_fixed: true`、`original_question`、`fix_reason`），由 `validate_enriched.py` 自动记录至 `reports/chXX_ocr_fixes.md`。
5. **对抗审查铁律（无 Repro 不挑刺）**：
   - `model="pro"` Reviewer 给出 `REJECTED` 裁决必须附带至少 1 个在当前产物上确定失败（Exit Code != 0）的独立可执行脚本 `tests/repro/repro_*.py`；无 Repro 脚本的驳回视为无效挑刺，Orchestrator 直接判 `APPROVED`。
   - 修复通过后，Repro 脚本吸收进 `tests/regression/` 作为永久防退化资产。

---

## 2. 目录架构与核心脚本速查表

| 路径 | 职责与说明 |
| :--- | :--- |
| `taxonomy.yaml` | 唯一受控多维标签词表（`domain`, `topic`, `method`, `difficulty`, `visual`, `format`, `extra_tags` 约束） |
| `scripts/extract_raw.py` | Stage 1 抽取脚本（按本书目录结构编写，输出标准 `staging/chXX_raw.jsonl`） |
| `scripts/precheck_geometry_symbols.py` | Stage 2 前置符号硬比对预检，输出 `staging/symbol_audit/chXX_symbol_audit.json` |
| `scripts/validate_enriched.py` | Stage 2 分片按 `id` 合并（`--merge-shards`）、1:1 校验与 `reports/chXX_*.md` 生成 |
| `scripts/export_output.py` | Stage 3 交付拆分导出（`pass`/`auto_fixed` -> `output/`；`flagged` -> `flagged/`） |
| `scripts/wave_workflow.py` | 通用多波次 `run_workflow` 编排脚本（预检→分片精标→校验导出→Pro审查→Repro修补→状态落盘） |
| `staging/chXX_raw.jsonl` | Stage 1 原始抽取产物（按章输出，0 题空章自动跳过） |
| `staging/waves.json` | 由 `init_project.py --plan-waves` 自动生成的均衡波次计划（可选，缺失时自动动态规划） |
| `staging/enriched/` | Stage 2 分片（`shards/chXX_pK.jsonl`）与合并终稿（`chXX_enriched.jsonl`） |
| `staging/wave_state.json` | 断点续传状态文件（记录各章 `approved` 状态、空章清单与波次汇总） |
| `output/` | 最终纯净交付目录（仅含 `pass` 与 `auto_fixed`） |
| `flagged/` | 疑难隔离目录（仅在存在 `flagged` 题目的章节下生成） |
| `reports/` | 每章 `chXX_ocr_fixes.md`、`chXX_audit_report.md` 及每波 `<run_label>_summary.md` |
| `tests/regression/` | 已修复并沉淀的永久防退化 `repro_*.py` 回归套件 |

---

## 3. 波次规划与 `run_workflow` 标准调用

### 3.1 Stage 1 完成后自动规划均衡波次

```powershell
python "{{SKILL_SCRIPTS_DIR}}\init_project.py" --root "{{WORKSPACE_ROOT}}" --book-name "{{BOOK_NAME}}" --plan-waves --wave-target-qs 250
```

> 若已有试点验收通过的章节，可附加 `--exclude-chapters 1 28` 将其排除在后续波次之外；`init_project.py` 会自动跳过 0 题空章节并按每张配图 `+0.5` 题的权重生成均衡波次 `staging/waves.json`。

### 3.2 `run_workflow` 标准调用模板

使用 `run_workflow` 工具传入 `ScriptPath`：

- `ScriptPath`: `{{WORKSPACE_ROOT}}\scripts\wave_workflow.py`（若未复制到项目内，也可直接指向 `{{SKILL_SCRIPTS_DIR}}\wave_workflow.py`）

推荐 `Args`（均支持 `skip_completed: true` 断点续传）：

```json
// 1. 轻/中度配图波次（默认推荐）
{"wave": 1, "shard_size": 25, "batch_concurrency": 4, "review_concurrency": 1, "skip_completed": true, "run_reviewer": true, "max_fix_rounds": 1}

// 2. 重度几何配图波次（建议降并发与分片大小以保证看图精度）
{"wave": 4, "shard_size": 20, "batch_concurrency": 3, "review_concurrency": 1, "skip_completed": true, "run_reviewer": true, "max_fix_rounds": 1}

// 3. 单章/指定章节覆盖重跑
{"chapters": [1, 2], "skip_completed": false, "run_reviewer": true}
```

### 3.3 单章手工重跑与全量验证命令

```powershell
# 1. 符号硬比对预检（不传 --chapters 时自动扫描 staging/ch*_raw.jsonl）
python scripts/precheck_geometry_symbols.py --root-dir "{{WORKSPACE_ROOT}}" --chapters 1

# 2. 合并分片 + 严格校验 + 生成 reports/chXX_*.md
python scripts/validate_enriched.py --root-dir "{{WORKSPACE_ROOT}}" --chapters 1 --merge-shards

# 3. 导出至 output/ 与 flagged/
python scripts/export_output.py --root-dir "{{WORKSPACE_ROOT}}" --chapters 1

# 4. 回归测试套件
python -m unittest discover -s tests/regression -p "repro_*.py" -v
```

---

## 4. 实战经验与踩坑备忘

1. **云盘/受限目录写权限规避（`WinError 5`）**：
   - 若工作区位于 iCloud Drive / OneDrive 等受保护目录，标准终端沙箱下 CLI 删除或写盘可能抛出 `PermissionError: [WinError 5]`。
   - **规避策略**：子 Agent 落盘 JSONL / Markdown / Repro 时优先使用 **`write_file` / `edit_file` 工具**；仅当 CLI 脚本确报 `PermissionError` 时，单独对该一条写盘命令申请提权执行。
2. **严防几何视觉误报 `flagged`**：
   - Enricher 与 Reviewer 看图时，若怀疑“阴影漏涂/线条缺失”，**必须结合几何对称性与原书 `book_solution_hint` 交叉验证**，切勿把正常印刷阴影/网格线密度误判为缺图。
3. **无参考答案题（`MISSING_SOLUTION_HINT`）独立验算**：
   - 当原始数据中某题 `book_solution_hint` 为空时，`wave_workflow.py` 会自动向 Enricher 与 Reviewer 注入具体题号提醒。**严禁因无参考答案而偷懒标 `flagged`**，必须独立完成数学推导并用 Python 验算。
4. **防超时审查与原子落盘**：
   - `wave_workflow.py` 默认 `review_concurrency=1` 且每完成一个审查单元即通过 `os.replace` 原子更新 `staging/wave_state.json`；Reviewer 应将一致性和数学抽检合并为单次脚本执行，控制单单元在 3~5 分钟内完成。
