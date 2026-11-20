# 架构设计与工程治理 SOP（Architecture & SOP）

本文档定义 OCR 数学题库流水线的目录拓扑、三段式数据流、多智能体角色分工、严格实证审查闭环、长周期抗故障机制与全书终审清单。

---

## 1. 三段式数据流与目录全景

```text
[原始 OCR 只读区] <chunk>/part_*.md + <chunk>/images/*
        │
        ▼ (Stage 1: scripts/extract_raw.py)
[内部暂存区]       staging/
                    ├── chXX_raw.jsonl               # 抽取原题 + 原书解析 + 预警标记（只读基线）
                    ├── extract_report.json          # 全书统计、配对审计、ocr_precheck_summary
                    ├── equation_table_index.json    # 未引用公式/表格切图兜底索引
                    ├── waves.json                   # 均衡波次划分表
                    ├── wave_state.json              # 审查单元级原子断点状态
                    ├── symbol_audit/chXX_symbol_audit.json
                    └── enriched/
                        ├── shards/chXX_pK.jsonl     # Enricher 分片产物 (<=25 题)
                        └── chXX_enriched.jsonl      # validate_enriched --merge-shards 合并终稿
        │
        ▼ (Stage 3: scripts/export_output.py 按 audit.status 严格分流)
   ┌────┴────────────────────────────────────────┐
   ▼ (`pass` / `auto_fixed`)                     ▼ (`flagged`)
[纯净交付区] output/chXX_<净短名>/              [疑难隔离区] flagged/chXX_<净短名>/
 ├── problems.jsonl (5 键)                        ├── problems.jsonl (6 键含 flag_reason)
 ├── md/chXX_NNN.md                               ├── md/chXX_NNN.md (含隔离预警引用块)
 └── images/chXX_NNN_k.ext                        └── images/chXX_NNN_k.ext

[工程与审计资产]
 ├── reports/                  # chXX_ocr_fixes.md, chXX_audit_report.md, wave_<id>_summary.md
 ├── .agents/teamwork/         # 审查分析报告 (analysis.md / wave_reviews/*.md)
 └── tests/
     ├── test_extract_raw.py   # Stage 1 结构与契约基线测试
     ├── test_stage2_stage3.py # Stage 2-3 校验与导出基建测试
     ├── repro/                # Reviewer 驳回时提交的失败复现脚本
     └── regression/           # 修复验收后永久沉淀的防退化测试套件
```

### 目录隔离原则
1. `output/` 下**只允许出现可用题目**；任何 `flagged` 题目的文本、`.md` 与配图都不得出现在 `output/` 中。
2. `flagged/` **按需创建**：当且仅当某章 `flagged_count >= 1` 时创建对应章目录；重跑导出时必须先删除 `output/` 和 `flagged/` 下所有以 `chXX_` 开头的旧目录（`_remove_stale_chapter_dirs`），防止历史遗留幽灵文件污染。
3. 原始分卷、`staging/chXX_raw.jsonl`、`taxonomy.yaml` 在进入 Stage 2 后一律视为**只读基线**。

---

## 2. 多模型角色分工矩阵

| 角色 | 推荐模型档位 | 核心职责 | 严格边界（禁止事项） |
| :--- | :--- | :--- | :--- |
| **Orchestrator（总管）** | 高阶规划模型（主会话） | 阶段拆解、波次调度、Repro 有效性裁决、状态签收与上下文管理（`/compact`） | **严禁**亲自逐行编写业务清洗/打标数据或手改 `staging/enriched/` 产物 |
| **Enricher（分片施工员）** | `flash` | 按分片（`<=25` 题）读原始题+配图+`symbol_audit`，完成 7 维打标、OCR 核验与可解性校验 | 严禁修改 `raw.jsonl`；严禁仅因无答案标 `flagged`；严禁写 shell 重定向落盘 |
| **Adversarial Reviewer（对抗审查员）** | `pro` | 100% 复核 `auto_fixed`/`flagged`；结合符号差集抽检高风险 `pass` 题；校验隔离与落盘一致性 | **严禁**纯文字假想挑刺；`REJECTED` 必须附带失败 Repro 脚本；严禁读无关章节或跑全库单测 |
| **Patcher（定向补丁手）** | `flash` | 仅针对 Reviewer 实证通过的 Repro 脚本修改对应分片记录，直到重新合并校验导出后 Repro 退出码为 `0` | 严禁修改 Repro 脚本本身；严禁越权修改无关题目或 `raw.jsonl` |
| **Victory Auditor（终审审计员）** | `pro` / `opus` | 全量跑完后独立核查题数守恒、0 断图、0 幽灵目录、`extra_tags` 聚合与全量回归测试 | 仅做客观实证检验与报告输出，不直接篡改交付数据 |

---

## 3. 严格实证审查闭环（无 Repro 不挑刺）

```text
[Reviewer 产出]
   ├── verdict == "APPROVED" ──▶ 写 wave_state.json (status="approved")
   └── verdict == "REJECTED"
          │
          ├── repro_scripts 为空？ ──▶ 【无效挑刺】Orchestrator 直接改判 APPROVED
          │
          └── 验证每个 repro_path：文件存在 且 python repro.py Exit Code != 0？
                 ├── 全都退出 0 或文件不存在 ──▶ 【无效/已失效】改判 APPROVED
                 └── 存在确定失败的 Repro ──▶ 派发 Patcher (flash, max_fix_rounds)
                        │
                        ▼
                 重新 validate (--merge-shards) + export + 重跑失败 Repro
                        ├── 全部退出码 == 0 ──▶ 拷贝进 tests/regression/ + 判 APPROVED
                        └── 仍非零失败 ──▶ 判 REJECTED，保留阻塞待人工/下一轮介入
```

**核心要点**：
- `tests/repro/repro_*.py` 必须独立可执行（基于 `unittest` 或显式 `sys.exit(1)` 断言），明确指向具体 `chXX_NNN` 与违反的规则。
- 避免将“文件不存在导致的 Python `rc=2`”误判为 Repro 实证成功：编排器必须先校验 `rp_path.is_file()` 再执行脚本。
- 若存在分片文件（`staging/enriched/shards/chXX_p*.jsonl`），Patcher **必须修改对应分片文件**，否则下次 `validate_enriched.py --merge-shards` 会用旧分片覆盖手工改过的 `chXX_enriched.jsonl`。

---

## 4. 长周期稳定性与抗故障机制

1. **分片上限防超时**：常规章节 `shard_size <= 25`；重图几何章节（如大量配图需多模态逐图打开核验）将 `shard_size` 降至 `20`、`batch_concurrency` 降至 `3`。
2. **串行审查并发 (`review_concurrency = 1`)**：`model="pro"` 单单元较重，若多单元高并发并行极易触发 API `429` 限流并连坐整批失败；设 `review_concurrency: 1` 逐单元稳步推进最稳妥。
3. **审查单元粒度分组**：单章题数 `>= 45` 或含图题数 `>= 15` 时独立分配 1 个 Reviewer 单元；其余轻量章按每组最多 3 章且总题数 `<= 65` 合并，防止单次审查过载。
4. **单单元 3~5 分钟防 401 过期**：要求 Reviewer 将“Schema 核对 + `output/`/`flagged/` 隔离核对 + Python 数学抽检”合并为 **1 个临时批处理脚本**（写入 scratch 目录）一次执行，严控在 10 轮工具调用与 3~5 分钟内完结，避免长时间运行遭遇 OAuth 401 Token 过期中断。
5. **双重原子断点**：
   - 分片断点：`wave_workflow.py` 启动时调用 `is_valid_shard_file(path, expected_ids)`，对已完整落盘且 1:1 ID 对齐的分片自动跳过（`skip_completed: true`）。
   - 审查断点：每结束一个审查单元立即以 `tmp + fsync + os.replace` 原子更新 `staging/wave_state.json`。重跑时自动跳过 `status == "approved"` 的章节。
6. **波次间上下文瘦身**：每跑完 1 个波次，执行全量单元测试 + 回归测试确认无退化，随后在主会话执行 `/compact` 清理冗长工具日志再启动下一波次。

---

## 5. 试点 2 章的科学选章与放行指标

在全量推进前，必须用 **2 章试点** 跑通从 `precheck` 到 `export` 再到 `Reviewer + Repro + Regression` 的完整闭环：
- **选章策略**：
  1. **1 个轻量纯文字/少图章**（如第 1 章，~15–30 题）：验证基础字段、出处剥离、OCR 预警识别与高速流水线连通性。
  2. **1 个重度几何/图文混排大章**（如第 28 章，~80–120 题、近百张配图）：极限压测分片合并、多模态看图精度、视觉误判防线与 Repro 吸收闭环。
- **试点抽检方法论与放行指标**：
  - `auto_fixed` 与 `flagged` 题目：**100% 逐题双人/跨模型复核**（必看原图 + 必核原书解析）。
  - `pass` 题目：轻图章可全量/高比例抽检；大章至少抽检 **~50%**（重点覆盖 `symbol_audit` 命中项及高难度题），统计 `sampled_pass_count` 与 `false_pass_count`。
  - **放行门槛**：`false_pass_count == 0`（估算全库漏网硬错率 `< 2%`），且试点触发的所有 Repro 均已修补并沉淀入 `tests/regression/`，全量 `unittest` Exit Code = `0`。

---

## 6. 全书终审 Victory Audit 验收清单

全部波次 `all_approved == true` 后，由 Victory Auditor 执行以下 6 项硬验收：

1. **全书总题数守恒**：`sum(output 题数) + sum(flagged 题数) == sum(staging/chXX_raw.jsonl 题数)`，与 `staging/extract_report.json` 零偏差；空章节（如概念章）无幽灵产物。
2. **零断图与图文对应**：遍历 `output/` 与 `flagged/` 所有 `problems.jsonl` 与 `md/*.md`，确认 100% 图片路径存在、非空（`>0 bytes`）且文件名与题号严格匹配。
3. **零幽灵目录与隔离纯洁性**：确认 `output/` 无任何 `flagged` ID、`flag_reason`、答案/解析残片；确认 `flagged == 0` 的章节在 `flagged/` 下无空目录。
4. **全量 `validate_enriched.py` 与 `unittest` 零失败**：
   - `python scripts/validate_enriched.py --all` 退出码 `0`
   - `python -m unittest tests/test_extract_raw.py tests/test_stage2_stage3.py -v` 退出码 `0`
   - `python -m unittest discover -s tests/regression -p "repro_*.py" -v` 退出码 `0`
5. **`extra_tags` 聚合晋升审计**：统计全书 `output/` 中 `extra_tags` 词频；若出现频次 `>= 15` 的高频合法概念，汇总清单提交人类/架构师评审是否升格纳入下一版受控词表。
6. **交付物抽样终验**：跨各板块随机抽查若干最终 `.md` 与 `problems.jsonl`，核验 YAML Frontmatter 可解析、LaTeX 公式定界符平衡、相对图链可直接渲染。
