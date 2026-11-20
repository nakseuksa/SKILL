---
name: ocr-math-bank-pipeline
description: Reconstructs OCR-digitized mathematics textbooks, workbooks, and exam collections (Markdown + cropped images) into a self-contained, multi-dimensionally tagged, solvability-verified question bank (`problems.jsonl` + per-question `.md` + `images/`) via a three-stage pipeline and multi-model adversarial review. Use when converting OCR math books into AI-ready question banks, stripping answers/solution hints/competition provenance at scale, auditing OCR typos and diagram-text consistency, or running resumable multi-wave pipelines. Do not use for initial PDF-to-Markdown OCR itself, generating brand-new synthetic math problems, or publishing answer keys/explanations in delivery output.
---

# OCR Math Bank Pipeline

将 OCR 识别后的数学教辅/题集 Markdown 与切图，通过**三段式流水线 + 多模型对抗验收**（Stage 1 抽取 → Stage 2 分片精标与 OCR/可解性体检 → Stage 3 纯净交付与 `flagged` 隔离），重构为每章自包含、可直接用于训练/测评/检索的纯净题库。

---

## 1. 核心铁律（6 条不可违反原则）

1. **只读基线保护**：原始 OCR 分卷与图片、`taxonomy.yaml`、`scripts/extract_raw.py` 及验收后的 `staging/chXX_raw.jsonl` 锁定只读，任何 Stage 2/3 施工或修复脚本严禁回写修改。
2. **纯净题干交付**：统一采用中性按章顺序编号 `chXX_NNN`；不区分例题与练习题；剥离竞赛/测试出处括号（保留数学条件括号）；`output/` 严禁出现解析、答案、`例 N` 前缀、`<details>` 或 Markdown 图片语法残片。
3. **`flagged` 严格隔离**：`pass` 与 `auto_fixed` 导出至 `output/chXX_<净短名>/`；存在真实缺图、图文矛盾或不可解缺陷的 `flagged` 题**完全剥离出 `output/`**（无文本、无 `.md`、无残图），隔离至 `flagged/chXX_<净短名>/`。若某章 `flagged == 0` 则不建空目录，每次导出前先清理旧章节目录防幽灵文件残留。
4. **100% 确凿 OCR 自动修复与留痕**：仅当经配图 + 原书解析 + 数学验算三重实证存在明确 OCR 错字/漏符时，置 `audit.status = "auto_fixed"`，保留 `original_question` 与 `fix_reason`，由 `validate_enriched.py` 自动汇总至 `reports/chXX_ocr_fixes.md`。
5. **多模型分工与“无 Repro 不挑刺”实证纪律**：Orchestrator 仅负责路由、契约与裁决，严禁亲手逐行改业务产物；Enricher/Patcher 用 `flash`；Adversarial Reviewer 用 `pro`，给出 `REJECTED` 必须附带至少 1 个在当前产物上确定非零退出的独立脚本 `tests/repro/repro_*.py`（无 Repro 一律视作无效挑刺直接判 `APPROVED`）。修复至退出码 `0` 后自动合入 `tests/regression/`。
6. **断点原子落盘与长周期防超时**：分片 `<=25` 题（重图章 `<=20` 题）；`review_concurrency=1` 防并发 429 拖死同批；审查将校验与 Python 验算合并为单次批处理脚本控在 3~5 分钟内结束防 OAuth 401 过期；每完成一个审查单元以 `os.replace` 原子更新 `staging/wave_state.json`，波次之间执行 `/compact`。

---

## 2. 五阶段端到端 SOP 路线图

| 阶段 | 执行角色 | 复核/门禁角色 | 门禁条件（Gate） | 核心产出物 |
| :--- | :--- | :--- | :--- | :--- |
| **Stage 0 初始化与词表** | Orchestrator / 架构师 | 用户确认词表边界 | 原书分卷与切图无串卷缺目录；`taxonomy.yaml` 词表正交无重名 | `taxonomy.yaml`、工作区脚本与目录、`staging/waves.json` |
| **Stage 1 抽取与实证审查** | Worker (`flash`) | Reviewer (`pro`) + `unittest` | `test_extract_raw.py` 与 `repro_*` 全绿；题数、图文绑定与出处剥离无漏失 | `scripts/extract_raw.py`、`staging/chXX_raw.jsonl`、`extract_report.json` |
| **Stage 2 试点双章压测** | `wave_workflow.py` (`flash`+`pro`) | Orchestrator 终审 | 1 轻图章 + 1 重图章闭环跑通；`false_pass_count == 0`；Repro 合入回归集 | 试点 `output/`、`flagged/`、`reports/`、`staging/wave_state.json` |
| **Stage 3 多波次全量推进** | `wave_workflow.py` (`wave=1..N`) | `pro` 逐单元实证审查 | 每波 `all_approved == true`；波次间运行测试集并 `/compact` 释放上下文 | 全书各波次 `output/`、`flagged/`、`reports/wave_<id>_summary.md` |
| **Stage 4 全书终审 Victory Audit** | Victory Auditor (`pro`/`opus`) | Orchestrator 最终签收 | 题数守恒 `output + flagged == raw`；0 断图；0 幽灵目录；全量测试 `rc=0` | `reports/victory_audit_report.md`、`extra_tags` 聚合审计结论 |

### 关键分流与模型路由速查

- **多模态视觉路由**：`source_images` 非空时 `tags.visual` 严禁填 `纯文字`，Enricher 与 Reviewer 必须逐图用 `read_file` 实看，严防将正常涂满阴影误判为 `flagged`（须结合几何对称性与解析核验）。
- **无答案章节处置**：若原书缺失部分参考答案（`MISSING_SOLUTION_HINT`），严禁偷懒标 `flagged`，必须独立推理 + Python 验算确认可解性后正常归档。
- **Triage 闭环裁决**：
  - `REJECTED` 无 Repro 脚本 → 改判 `APPROVED`。
  - `REJECTED` 附 Repro → 先核查脚本文件真实存在且运行 `Exit Code != 0`（防不存在路径 `rc=2` 误触发）→ 派 `flash` Patcher 仅改分片文件至重跑 `rc=0` → 自动拷贝至 `tests/regression/`。

### 高频状态与预警速查

| `audit.status` | 交付去向 | 强制联动字段与核验要求 |
| :--- | :--- | :--- |
| **`pass`** | `output/chXX_<净短名>/` | `solvable: true`，7 键 `tags` 合规，`verified_by` 非空 |
| **`auto_fixed`** | `output/chXX_<净短名>/` | `ocr_fixed: true` + `original_question != question` + `fix_reason`（生成 `chXX_ocr_fixes.md`） |
| **`flagged`** | `flagged/chXX_<净短名>/` | `solvable: false` + 非空 `flag_reason`（从 `output/` 完全剥离；0 flagged 不建目录） |

- **Stage 1 三类必查预警**（见 `staging/extract_report.json`）：
  - `MISSING_IMAGE_SUSPECTED`：题干含“如图/下图”但 `source_images == []`（逐题核实是否真实缺图）。
  - `SUSPECT_DIVISIBILITY_TIMES`：数论语境孤立 `\times`（核查是否把整除符误识为乘号）。
  - `MISSING_SOLUTION_HINT`：原书答案分卷缺失（严禁直接标 `flagged`，须独立推导 + Python 验算）。
- **Victory Audit 终审门禁**：总题数守恒（`output + flagged == raw`）、0 断图、0 幽灵目录、`extra_tags` 词频 `>=15` 聚合审阅、全量 `unittest` + `tests/regression/repro_*.py` 退出码 `0`。

---

## 3. 新项目快速启动命令（Copy-Paste Ready）

### Step 1：初始化工作区与通用基建

```powershell
python <skill_dir>/scripts/init_project.py --root <workspace> --book-name "<书名>" --copy-scripts --copy-taxonomy --copy-runbook
```

### Step 2：编写并验收本项目 Stage 1 抽取脚本

参照 [Stage 1 抽取实战指南](./references/stage1_extractor_guide.md) 与 [抽取参考实现](./examples/extract_raw_reference.py) 定制 `<workspace>/scripts/extract_raw.py` 及 `tests/test_extract_raw.py`，执行并验证基线全绿：

```powershell
python scripts/extract_raw.py
python -m unittest tests/test_extract_raw.py tests/test_stage2_stage3.py -v
```

### Step 3：自动生成均衡波次计划（目标 ~250 题/波）

```powershell
python <skill_dir>/scripts/init_project.py --root <workspace> --plan-waves --wave-target-qs 250
```

### Step 4：试点 2 章压测闭环（选 1 轻图章 + 1 重图章）

通过 `run_workflow` 工具拉起试点章节（示例为第 1 章轻图 + 第 28 章重图）：

```json
{
  "ScriptPath": "<workspace>/scripts/wave_workflow.py",
  "Args": {
    "chapters": [1, 28],
    "shard_size": 25,
    "batch_concurrency": 4,
    "review_concurrency": 1,
    "skip_completed": false,
    "run_reviewer": true,
    "max_fix_rounds": 1
  }
}
```

### Step 5：按波次推进、断点续跑与单章手工重跑

**波次推进与断电/429/401 续跑参数模板**（重图波次建议将 `shard_size` 降至 `20`、`batch_concurrency` 降至 `3`）：

```json
{
  "ScriptPath": "<workspace>/scripts/wave_workflow.py",
  "Args": {
    "wave": 1,
    "shard_size": 25,
    "batch_concurrency": 4,
    "review_concurrency": 1,
    "skip_completed": true,
    "run_reviewer": true,
    "max_fix_rounds": 1
  }
}
```

| `wave_workflow.py` 常用 Args | 默认值 | 说明与调优建议 |
| :--- | :---: | :--- |
| `wave` / `chapters` | 必填其一 | 指定 `1..N` 波次号，或传 `[27]` 覆盖重跑特定章节 |
| `shard_size` | `25` | 每片题数上限；重图几何章调为 `20` 防看图超时 |
| `batch_concurrency` | `4` | Enricher 并行度；重图波次建议降为 `3` |
| `review_concurrency` | `1` | Pro Reviewer 并行度；**固定保持 `1` 防 429 限流** |
| `skip_completed` | `true` | 自动跳过已通过分片与 `approved` 章节；覆盖重跑置 `false` |
| `max_fix_rounds` | `1` | Repro 驳回后自动派发 `flash` 定向修补的最大轮数 |

**单章手工校验导出与全量回归命令**（若 Windows iCloud 目录触发沙箱 `WinError 5`，仅对 `export_output.py` 单独提权 `BypassSandbox: true`）：

```powershell
# 1. 符号硬比对预检 -> staging/symbol_audit/chXX_symbol_audit.json
python scripts/precheck_geometry_symbols.py --chapters 27

# 2. 合并分片 + 严格 Schema/纯净度校验 + 生成 reports/chXX_*.md
python scripts/validate_enriched.py --chapters 27 --merge-shards

# 3. 拆分导出至 output/ 与 flagged/（重图/无flagged章自动清理旧目录）
python scripts/export_output.py --chapters 27

# 4. 全量自动化测试与回归套件（每波次收口必跑，然后 /compact）
python -m unittest tests/test_extract_raw.py tests/test_stage2_stage3.py -v
python -m unittest discover -s tests/regression -p "repro_*.py" -v
```

---

## 4. 按需查阅参考手册索引

- **架构、多模型协同与全周期运维 SOP**：[architecture_and_sop.md](./references/architecture_and_sop.md)
- **Stage 1/2/3 JSONL、Frontmatter 与状态文件 Schema 契约**：[schema_and_contracts.md](./references/schema_and_contracts.md)
- **新书 Stage 1 抽取脚本编写与 6 大 OCR 坑解法**：[stage1_extractor_guide.md](./references/stage1_extractor_guide.md)
- **实战踩坑实录与防雷清单（WinError 5 / GBK / OAuth 401 / 视觉误判等）**：[lessons_learned.md](./references/lessons_learned.md)
- **多维标签受控词表可定制模板**：[taxonomy_template.yaml](./resources/taxonomy_template.yaml)
- **Stage 1 抽取参考代码（《明心数学》完整实现）**：[extract_raw_reference.py](./examples/extract_raw_reference.py)
