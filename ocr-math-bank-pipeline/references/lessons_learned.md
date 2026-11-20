# 实战踩坑实录与防雷清单（Lessons Learned）

本文档沉淀《明心数学资优生大题典》（40 章 1,711 题）全链路实战中真实踩过的 9 个核心工程与业务坑，每条均给出**症状 → 根因 → 永久解法**。

---

## 1. 原始分卷切图目录串卷核验
- **症状**：运行 Stage 1 抽取或人工核查第 32~40 章图片时，发现图片文件缺失或与题目页码完全对不上。
- **根因**：原始 OCR 导出整理阶段，`<chunk>/images/` 目录曾发生串卷错放（例如《明心数学》`下_201_400/images` 初期误复制成了 `上_257_313/images`），而 Markdown 中的相对路径仍是 `images/page_XXX_image_Y.jpg`。
- **永久解法**：
  1. Stage 0 开工前先做物理目录校验：比对各分卷 Markdown 引用的 `page_XXX_` 集合与对应 `<chunk>/images/` 实存文件的覆盖率（必须 100% 命中且跨分卷不重叠错位）。
  2. 将 `test_all_source_images_exist_and_non_empty` 写入 `tests/test_extract_raw.py` 强制门禁。

## 2. Windows iCloud Drive 沙箱写盘 `WinError 5`
- **症状**：工作区位于 `iCloudDrive\Downloads\...` 时，在标准沙箱终端下运行 Python 脚本执行 `shutil.rmtree`、`mkdir` 或向 `output/`、`flagged/`、`staging/`、`reports/` 写盘，偶发抛出 `PermissionError: [WinError 5] 拒绝访问`。
- **根因**：Windows 终端沙箱对 iCloud Drive 同步目录（重解析点/云端占位符权限）存在写/删权限拦截。
- **永久解法**：
  1. 子智能体（Enricher / Reviewer / Patcher）写入 JSONL、Markdown 或 Repro 脚本时，**一律使用 `write_file` / `edit_file` 工具**，严禁使用 shell 重定向写盘。
  2. `run_workflow` 宿主进程在工作区外层直接写盘通常不受沙箱 CLI 限制；当手工在终端执行 `scripts/export_output.py`（含 `shutil.rmtree` 清理旧章节目录）且确认遇 `WinError 5` 时，仅对该单一导出命令单独申请 `BypassSandbox: true`。

## 3. `run_workflow` 内置纯标准库 Python 缺少 `PyYAML`
- **症状**：`wave_workflow.py` 在 `run_workflow` 宿主机内置 Python 环境启动后，直接 `import yaml` 抛出 `ModuleNotFoundError: No module named 'yaml'`。
- **根因**：Antigravity `run_workflow` 宿主运行时仅打包了 Python 标准库，未预装第三方包 `PyYAML`。
- **永久解法**：
  1. 编排脚本 `wave_workflow.py` 顶层只允许 `import` Python 标准库。
  2. 封装 `resolve_python_bin()` 依次探测 `shutil.which("python")`、`sys.executable`、`shutil.which("python3")` 中首个能成功执行 `python -c "import yaml"` 的系统解释器，用于通过 `subprocess` 调用 `precheck_geometry_symbols.py`、`validate_enriched.py`、`export_output.py` 及解析 `taxonomy.yaml`。

## 4. Windows GBK vs UTF-8 子进程编码炸弹
- **症状**：Windows 中文系统下，子进程脚本 `print()` 输出 emoji（如 `⚠️`）或特殊数学符号时触发 `UnicodeEncodeError: 'gbk' codec can't encode character`，或宿主进程解析子进程 JSON 标准输出乱码。
- **根因**：Windows 默认控制台代码页为 CP936/GBK，未显式声明 UTF-8 时 `subprocess` 与 `sys.stdout` 易退回 GBK。
- **永久解法**：
  1. 所有 CLI 脚本入口统一加 `if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")`。
  2. `run_cli()` 调起子进程时强制注入环境变量 `PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`，并指定 `encoding="utf-8", errors="replace"`。
  3. 宿主通过 `subprocess` 跨进程传 JSON 摘要（如 `build_taxonomy_summary`）时使用 `json.dumps(..., ensure_ascii=True)`，彻底规避管道编码差异。

## 5. 长任务 ~18 分钟 OAuth 401 过期与 429 限流
- **症状**：单波次处理章节过多、Pro Reviewer 并发过多或单次审查耗时超过 ~18 分钟时，子智能体触发 `401 Unauthorized`（OAuth Token 过期）或 `429 Too Many Requests` 并连带整批中断。
- **根因**：高并发抢占限流配额，以及单轮/单 Agent 持续时间过长跨越认证 Token 刷新窗口。
- **永久解法**：
  1. Enricher 分片控制在 `<= 25` 题（重图章节 `<= 20` 题，`batch_concurrency` 降为 `3`）。
  2. Reviewer 严格串行：`review_concurrency: 1`。
  3. Prompt 硬性要求 Reviewer 将隔离校验、Schema 一致性与 Python 验算合并为 **1 个临时批处理脚本** 一次运行，单审查单元控制在 **3~5 分钟、10 轮工具调用以内**；禁止读取无关章节报告或跑全库 `unittest`。
  4. 每个审查单元结束立即原子写盘 `staging/wave_state.json`，中断后直接 `skip_completed: true` 秒级续跑。

## 6. 几何视觉误判 `flagged` 陷阱（试点 `ch28_068` 教训）
- **症状**：试点阶段 Stage 2 Enricher 将第 28 章第 68 题（正八边形阴影题）判定为“左上角 $\triangle KLE$ 漏涂蓝色阴影”，错标 `flagged` (`solvable=false`)。
- **根因**：模型看小尺寸几何图时受网格线或反光感知偏差影响产生视觉幻觉，未结合几何旋转对称性与原书解析交叉核验。
- **永久解法**：
  1. Pro Reviewer 编写独立实证脚本 `tests/repro/repro_pilot_false_flagged_ch28_068.py`，通过像素 RGB 采样证明四象限青蓝色像素分布偏差 `< 3.2%` 且数学面积完全自洽，实锤打回并修复为 `pass` 后沉淀进 `tests/regression/`。
  2. 将该戒律写入 Enricher 与 Reviewer Prompt：凡怀疑“阴影漏涂/线条缺失”，必须结合图形对称性与 `book_solution_hint` 双重核验，严禁视觉幻觉误报 `flagged`。

## 7. 严重 OCR 损坏真实隔离 vs 高价值 OCR 自动修复
- **真实隔离案例（必须果断 `flagged`）**：
  - `ch01_001`：题干问“右图是小明写的加法竖式，请你判断他写得对不对”，但原书切图缺失，仅靠解析无法还原小明写的“错误竖式”。
  - `ch03_050`：多层无限循环繁分数在题干与解析中均排版彻底错乱，且第 35 页无该公式原图截图，无法 100% 唯一还原原始嵌套结构。
  - `ch28_012`：原书文字称“等腰直角三角形斜边的中点”（算出面积 32），但原书配图与解析均按“直角边中点”（算出 80），属原书图文根本矛盾。
- **高价值自动修复案例（必须实证后 `auto_fixed`）**：
  - 第 3 章一口气修复 **9 题**：其中 **8 题**为 OCR 丢失循环小数上标循环点（如把 $0.\dot{2}3\dot{4}$ 误识成普通小数 `0.234`，导致 `1.26 - 1.26` 自相矛盾），**1 题**（`ch03_040`）补回漏识别的省略号 `+\cdots+`；均经 `book_solution_hint` 与 Python 实算双重实证后写清 `fix_reason` 与 `original_question`。
  - 第 28 章 `ch28_081`：OCR 将 `△AQD` 错印为重复的 `△AQP`，对照配图与解析面积计算实证后自动修复。

## 8. 部分章节缺失原书参考答案的处理原则
- **症状**：《明心数学》第 40 章末尾 15 题（`ch40_075`~`ch40_089`）因《下_401》分卷未录入而缺失参考答案，Stage 1 已打标 `MISSING_SOLUTION_HINT`。
- **根因**：若不显式约束，Enricher 容易把“没有 `book_solution_hint` 可抄”误当成题目不可解，偷懒全部标成 `flagged`。
- **永久解法**：在文档与 `build_enrich_prompt()` 中明确规定：**`book_solution_hint` 为空严禁作为 `flagged` 理由**；必须独立完成数学推导与只读 Python 验算，确认题干自身条件完备即可正常打标 `pass` 并交付。

## 9. 重跑 `shard_size` 变化污染 & 不存在 Repro 返回 `rc=2`
- **症状 1**：先按 `shard_size=20` 跑出 `chXX_p1..p6`，重跑时改为 `shard_size=25`（只需 `p1..p5`），旧的 `chXX_p6.jsonl` 仍残留在 `shards/` 目录，导致 `--merge-shards` 合并出重复 ID 报错。
  - **永久解法**：`wave_workflow.py` 在生成分片任务前主动清理 `num_shards == 1` 的所有旧分片以及编号 `> num_shards` 的陈旧分片文件。
- **症状 2**：若 Reviewer 误填了一个不存在的 `repro_scripts` 路径，`python nonexistent.py` 返回 `rc=2`，若编排器不检查文件存在性，会把它误当成“确定失败的 Repro 铁证”而进入无限 Patch 循环。
  - **永久解法**：Triage 阶段先验证 `rp_path.is_file()`，不存在的路径直接忽略并记日志，不视为有效 Repro。
