#!/usr/bin/env python3
"""
Generic Multi-Wave Stage 2-3 Orchestration Script for `run_workflow`.

Executes the end-to-end pipeline for a chosen wave (from `staging/waves.json` or
dynamically balanced from `staging/ch*_raw.jsonl`) or an explicit chapter list:
  1. Precheck (`scripts/precheck_geometry_symbols.py --root-dir <ROOT_DIR>`)
  2. Enrich (sharded, batch-concurrent `model="flash"` agents with checkpoint/resume)
  3. Validate & Export (`scripts/validate_enriched.py --merge-shards` + `scripts/export_output.py`)
  4. Adversarial Review (grouped `model="pro"` reviewers under Strict Empirical Rule)
  5. Triage & Auto-Patch (Repro verification, targeted `model="flash"` patch, `tests/regression/` absorption)
  6. Persist `staging/wave_state.json` & `reports/<run_label>_summary.md`

Intended to be invoked via Antigravity `run_workflow(ScriptPath=..., Args={...})`.
Uses Python stdlib and `run_workflow` primitives in the host process (resolves an
external Python interpreter with PyYAML when needed).
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_WORKSPACES = globals().get("WORKSPACES") or []
_ARGS = globals().get("args") or {}

ROOT_DIR = (
    Path(_ARGS["root_dir"])
    if _ARGS.get("root_dir")
    else (Path(_WORKSPACES[0]) if _WORKSPACES else Path.cwd())
)
STAGING_DIR = ROOT_DIR / "staging"
ENRICHED_DIR = STAGING_DIR / "enriched"
SHARDS_DIR = ENRICHED_DIR / "shards"
SYMBOL_AUDIT_DIR = STAGING_DIR / "symbol_audit"
REPORTS_DIR = ROOT_DIR / "reports"
TEAMWORK_REVIEWS_DIR = ROOT_DIR / ".agents" / "teamwork" / "wave_reviews"
TESTS_REPRO_DIR = ROOT_DIR / "tests" / "repro"
TESTS_REGRESSION_DIR = ROOT_DIR / "tests" / "regression"
WAVE_STATE_PATH = STAGING_DIR / "wave_state.json"
WAVES_CONFIG_PATH = STAGING_DIR / "waves.json"
TAXONOMY_PATH = ROOT_DIR / "taxonomy.yaml"

RAW_FILE_RE = re.compile(r"^ch(\d+)_raw\.jsonl$")
DEFAULT_SKILL_SCRIPTS_DIR = (
    Path.home() / ".gemini" / "config" / "skills" / "ocr-math-bank-pipeline" / "scripts"
)

ENRICH_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "chapter": {"type": "integer"},
        "shard": {"type": "string"},
        "output_path": {"type": "string"},
        "count": {"type": "integer"},
        "pass_count": {"type": "integer"},
        "auto_fixed_count": {"type": "integer"},
        "flagged_count": {"type": "integer"},
        "auto_fixed_ids": {"type": "array", "items": {"type": "string"}},
        "flagged_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "chapter",
        "shard",
        "output_path",
        "count",
        "pass_count",
        "auto_fixed_count",
        "flagged_count",
        "auto_fixed_ids",
        "flagged_ids",
    ],
}

FIX_VALIDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "chapter": {"type": "integer"},
        "fixed": {"type": "boolean"},
        "modified_files": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": ["chapter", "fixed", "modified_files", "summary"],
}

REVIEW_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "chapters": {"type": "array", "items": {"type": "integer"}},
        "verdict": {"type": "string", "enum": ["APPROVED", "REJECTED"]},
        "issues": {"type": "array", "items": {"type": "string"}},
        "repro_scripts": {"type": "array", "items": {"type": "string"}},
        "sampled_pass_count": {"type": "integer"},
        "false_pass_count": {"type": "integer"},
        "report_path": {"type": "string"},
    },
    "required": [
        "chapters",
        "verdict",
        "issues",
        "repro_scripts",
        "sampled_pass_count",
        "false_pass_count",
        "report_path",
    ],
}

PATCH_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "chapters": {"type": "array", "items": {"type": "string", "type_override": "integer"}}
        if False
        else {"type": "array", "items": {"type": "integer"}},
        "patched_files": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": ["chapters", "patched_files", "summary"],
}


def resolve_script(
    name: str,
    skill_scripts_dir: str | Path | None = None,
    root_dir: Path | None = None,
) -> Path:
    """
    Locate a pipeline script by checking:
      1) <root_dir>/scripts/<name>
      2) <skill_scripts_dir>/<name> (if provided)
      3) <dirname(__file__)>/<name> (if __file__ is available)
      4) ~/.gemini/config/skills/ocr-math-bank-pipeline/scripts/<name>
    """
    base_root = root_dir or ROOT_DIR
    candidates: list[Path] = [base_root / "scripts" / name]
    if skill_scripts_dir:
        candidates.append(Path(skill_scripts_dir) / name)
    script_file = globals().get("__file__")
    if script_file:
        candidates.append(Path(script_file).resolve().parent / name)
    candidates.append(DEFAULT_SKILL_SCRIPTS_DIR / name)

    for cand in candidates:
        if cand.is_file():
            return cand
    raise FileNotFoundError(
        f"Unable to locate pipeline script '{name}'. Searched: {[str(c) for c in candidates]}"
    )


def run_cli(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a Python CLI script inside ROOT_DIR with UTF-8 output captured."""
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT_DIR),
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.stdout.strip():
        for line in proc.stdout.strip().splitlines():
            log(line)
    if proc.stderr.strip():
        for line in proc.stderr.strip().splitlines():
            log(f"[stderr] {line}")
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed (rc={proc.returncode}): {' '.join(cmd)}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    return proc


def resolve_python_bin() -> str:
    """Resolve the first Python interpreter capable of importing PyYAML."""
    candidates: list[str] = []
    seen: set[str] = set()
    for raw in (shutil.which("python"), sys.executable, shutil.which("python3")):
        if not raw:
            continue
        key = os.path.normcase(os.path.abspath(raw))
        if key in seen:
            continue
        seen.add(key)
        candidates.append(raw)

    errors: list[str] = []
    for cand in candidates:
        try:
            proc = subprocess.run(
                [cand, "-c", "import yaml"],
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            errors.append(f"{cand}: {exc}")
            continue
        if proc.returncode == 0:
            return cand
        detail = (proc.stderr or proc.stdout or "").strip()
        errors.append(f"{cand} (rc={proc.returncode}): {detail}")

    raise RuntimeError(
        "Failed to locate a Python interpreter with PyYAML installed. "
        f"Tried candidates={candidates}. Errors: {'; '.join(errors)}"
    )


def build_validate_cmd(
    ch: int,
    python_bin: str,
    skill_scripts_dir: str | Path | None = None,
) -> list[str]:
    """Build validate_enriched.py command, passing --merge-shards only if shards exist."""
    script_path = resolve_script("validate_enriched.py", skill_scripts_dir=skill_scripts_dir)
    cmd = [
        python_bin,
        str(script_path),
        "--root-dir",
        str(ROOT_DIR),
        "--chapters",
        str(ch),
    ]
    if SHARDS_DIR.is_dir() and any(SHARDS_DIR.glob(f"ch{ch:02d}_p*.jsonl")):
        cmd.append("--merge-shards")
    return cmd


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return records


def is_valid_shard_file(path: Path, expected_ids: list[str]) -> bool:
    """Return True iff `path` exists, parses cleanly as JSONL, and aligns 1-to-1 with `expected_ids`."""
    if not path.is_file():
        return False
    try:
        recs = load_jsonl(path)
    except Exception:
        return False
    if len(recs) != len(expected_ids):
        return False
    actual_ids = [r.get("id") for r in recs]
    return sorted(actual_ids) == sorted(expected_ids) and len(set(actual_ids)) == len(expected_ids)


def detect_empty_chapters(staging_dir: Path | None = None) -> list[int]:
    """Scan `staging/ch*_raw.jsonl` and return sorted chapter numbers that have 0 records."""
    s_dir = staging_dir or STAGING_DIR
    if not s_dir.is_dir():
        return []
    empty: list[int] = []
    for p in s_dir.glob("ch*_raw.jsonl"):
        m = RAW_FILE_RE.match(p.name)
        if not m:
            continue
        ch = int(m.group(1))
        has_records = False
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    has_records = True
                    break
        if not has_records:
            empty.append(ch)
    return sorted(set(empty))


def plan_balanced_waves(
    staging_dir: Path | None = None,
    *,
    target_wave_weight: float = 250.0,
    exclude_chapters: set[int] | None = None,
) -> tuple[dict[int, list[int]], list[int]]:
    """
    Scan `staging/ch*_raw.jsonl`, skip 0-question empty chapters and `exclude_chapters`,
    and partition remaining chapters into balanced waves `1..K` where each image adds
    `+0.5` weight to the chapter's question count.
    Returns `(waves_dict, empty_chapters)`.
    """
    s_dir = staging_dir or STAGING_DIR
    excluded = set(exclude_chapters or set())
    empty_chapters: list[int] = []
    chapter_weights: list[tuple[int, float]] = []

    found_files: list[tuple[int, Path]] = []
    if s_dir.is_dir():
        for p in s_dir.glob("ch*_raw.jsonl"):
            m = RAW_FILE_RE.match(p.name)
            if m:
                found_files.append((int(m.group(1)), p))

    for ch, path in sorted(found_files, key=lambda x: x[0]):
        recs = load_jsonl(path)
        if not recs:
            empty_chapters.append(ch)
            continue
        if ch in excluded:
            continue
        img_count = sum(len(r.get("source_images") or []) for r in recs)
        weight = len(recs) + 0.5 * img_count
        chapter_weights.append((ch, weight))

    waves: dict[int, list[int]] = {}
    cur_chapters: list[int] = []
    cur_weight = 0.0
    wave_idx = 1

    for ch, w in chapter_weights:
        if cur_chapters and cur_weight + w > target_wave_weight:
            waves[wave_idx] = cur_chapters
            wave_idx += 1
            cur_chapters = []
            cur_weight = 0.0
        cur_chapters.append(ch)
        cur_weight += w

    if cur_chapters:
        waves[wave_idx] = cur_chapters

    return waves, sorted(set(empty_chapters))


def load_waves_from_file(waves_path: Path) -> dict[int, list[int]]:
    """
    Load waves mapping from `staging/waves.json`, supporting both
    `{"waves": {"1": [..], ...}}` and `{"1": [..], ...}`.
    """
    raw = json.loads(waves_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid waves config in {waves_path}: expected JSON object")
    waves_obj = raw["waves"] if isinstance(raw.get("waves"), dict) else raw
    parsed: dict[int, list[int]] = {}
    for k, v in waves_obj.items():
        if str(k).isdigit() and isinstance(v, list):
            parsed[int(k)] = [int(c) for c in v]
    return parsed


def load_wave_state(state_path: Path | None = None, staging_dir: Path | None = None) -> dict[str, Any]:
    target_path = state_path or WAVE_STATE_PATH
    if target_path.is_file():
        data = json.loads(target_path.read_text(encoding="utf-8"))
    else:
        data = {
            "version": 1,
            "pilot_completed": [],
            "empty_chapters": [],
            "chapters": {},
            "waves": {},
        }
    data.setdefault("version", 1)
    data.setdefault("pilot_completed", [])
    data.setdefault("chapters", {})
    data.setdefault("waves", {})
    detected_empty = detect_empty_chapters(staging_dir)
    existing_empty = [int(c) for c in data.get("empty_chapters", [])]
    data["empty_chapters"] = sorted(set(existing_empty) | set(detected_empty))
    return data


def save_wave_state(state: dict[str, Any], state_path: Path | None = None) -> None:
    target_path = state_path or WAVE_STATE_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tmp_path = target_path.with_suffix(".json.tmp")
    payload = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    with tmp_path.open("w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, target_path)


def build_chapter_state_entry(
    ch: int,
    rev_info: dict[str, Any],
    run_reviewer: bool,
) -> dict[str, Any]:
    enr_recs = load_jsonl(ENRICHED_DIR / f"ch{ch:02d}_enriched.jsonl")
    pass_cnt = sum(1 for r in enr_recs if r["audit"]["status"] == "pass")
    fix_cnt = sum(1 for r in enr_recs if r["audit"]["status"] == "auto_fixed")
    flg_cnt = sum(1 for r in enr_recs if r["audit"]["status"] == "flagged")
    verdict = rev_info.get("verdict", "VALIDATED_NO_REVIEW" if not run_reviewer else "APPROVED")
    ch_status = (
        "approved"
        if verdict == "APPROVED"
        else ("validated" if verdict == "VALIDATED_NO_REVIEW" else "rejected")
    )
    return {
        "chapter": ch,
        "status": ch_status,
        "verdict": verdict,
        "total": len(enr_recs),
        "pass": pass_cnt,
        "auto_fixed": fix_cnt,
        "flagged": flg_cnt,
        "sampled_pass_count": rev_info.get("sampled_pass_count", 0),
        "false_pass_count": rev_info.get("false_pass_count", 0),
        "review_report": rev_info.get("report_path", ""),
    }


def _load_taxonomy_yaml(python_bin: str, taxonomy_path: Path) -> dict[str, Any]:
    try:
        import yaml  # noqa: PLC0415

        return yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))
    except ModuleNotFoundError:
        proc = subprocess.run(
            [
                python_bin,
                "-c",
                "import json, pathlib, sys, yaml; print(json.dumps(yaml.safe_load(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')), ensure_ascii=True))",
                str(taxonomy_path),
            ],
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return json.loads(proc.stdout)


def _format_method_names(items: list[Any]) -> list[str]:
    return [x["name"] if isinstance(x, dict) else str(x) for x in items]


def build_taxonomy_summary(
    python_bin: str,
    taxonomy_path: Path | None = None,
) -> str:
    data = _load_taxonomy_yaml(python_bin, taxonomy_path or TAXONOMY_PATH)
    lines: list[str] = ["### 受控词表摘要 (`taxonomy.yaml`)"]
    domain_names = [d["name"] if isinstance(d, dict) else str(d) for d in data["domains"]]
    lines.append(f"- **domains** (单选): {domain_names}")
    lines.append("- **topics** (1~2 个，第 1 个必须属于所选 domain):")
    for dom, items in data["topics"].items():
        names = [x["name"] if isinstance(x, dict) else str(x) for x in items]
        lines.append(f"  - `{dom}`: {names}")

    methods_root = data["methods"]
    if isinstance(methods_root, list):
        lines.append(
            f"- **methods** (平铺选 1~3 个，不可重复): {_format_method_names(methods_root)}"
        )
    elif isinstance(methods_root, dict):
        lines.append("- **methods** (跨组混选 1~3 个，不可重复):")
        for grp, val in methods_root.items():
            if isinstance(val, list):
                lines.append(f"  - `{grp}`: {_format_method_names(val)}")
            elif isinstance(val, dict):
                lines.append(f"  - `{grp}`:")
                for sub_grp, items in val.items():
                    if isinstance(items, list):
                        lines.append(f"    - `{sub_grp}`: {_format_method_names(items)}")

    diff_desc = ", ".join(
        f"{d['level']}-{d['name']}" if isinstance(d, dict) else str(d)
        for d in data["difficulty"]
    )
    lines.append(f"- **difficulty** (严格整数): {diff_desc}")
    visual_names = [v["name"] if isinstance(v, dict) else str(v) for v in data["visual"]]
    lines.append(
        f"- **visual** (单选；`source_images` 非空严禁为 `纯文字`，空必须为 `纯文字`): {visual_names}"
    )
    format_names = [f["name"] if isinstance(f, dict) else str(f) for f in data["format"]]
    lines.append(f"- **format** (单选): {format_names}")
    lines.append("- **extra_tags**: 0~2 个字符串，2~8 字符，不含 `#`，禁止与上述受控词表重名。")
    return "\n".join(lines)


def find_missing_hint_ids(records: list[dict[str, Any]]) -> list[str]:
    """Identify records with empty `book_solution_hint` or `MISSING_SOLUTION_HINT` flag."""
    missing: list[str] = []
    for r in records:
        hint = (r.get("book_solution_hint") or "").strip()
        flags = r.get("ocr_precheck_flags") or []
        if not hint or "MISSING_SOLUTION_HINT" in flags:
            rid = r.get("id")
            if isinstance(rid, str) and rid:
                missing.append(rid)
    return missing


def chunk_list(items: list[Any], size: int) -> list[list[Any]]:
    n = max(1, int(size))
    return [items[i : i + n] for i in range(0, len(items), n)]


def build_enrich_prompt(item: dict[str, Any], taxonomy_summary: str) -> str:
    ch = item["chapter"]
    shard_label = item["shard_label"]
    out_rel = item["output_rel"]
    expected_ids = item["expected_ids"]
    suspect_slice = item["suspect_slice"]
    missing_hint_ids: list[str] = item.get("missing_hint_ids") or []

    missing_hint_note = ""
    if missing_hint_ids:
        missing_hint_note = (
            f"\n> ⚠️ **无参考答案特别注意**：本分片中以下 {len(missing_hint_ids)} 题 "
            f"`book_solution_hint` 为空或含 `MISSING_SOLUTION_HINT` 标记：`{json.dumps(missing_hint_ids, ensure_ascii=False)}`。\n"
            "> 严禁偷懒标 `flagged`！必须独立推导并用 Python 验算来核查可解性与标签。\n"
        )

    suspect_block = (
        json.dumps(suspect_slice, ensure_ascii=False, indent=2)
        if suspect_slice
        else "（本分片无 symbol_audit 预警记录，仍需逐题独立核验）"
    )

    return f"""你是 Stage 2 题目精标与体检工程师（Enricher），负责完成第 {ch:02d} 章分片 `{shard_label}` 的精标、OCR 核验与落盘。

## 1. 目标范围与输出路径
- 读取原始文件：`staging/ch{ch:02d}_raw.jsonl`
- 本分片负责题号（共 {len(expected_ids)} 题，必须 1-to-1 完整覆盖、按 ID 升序输出，不得遗漏或多余）：
  `{expected_ids[0]}` .. `{expected_ids[-1]}`
  完整 ID 列表：`{json.dumps(expected_ids, ensure_ascii=False)}`
- 输出目标路径（**必须使用 `write_file` 工具写入，严禁使用 shell 重定向写文件**）：
  `{out_rel}`（JSONL 格式，每行 1 个 JSON 对象，UTF-8 无 BOM）
{missing_hint_note}
## 2. 符号硬比对预警（`staging/symbol_audit/ch{ch:02d}_symbol_audit.json` 本分片命中）
```json
{suspect_block}
```

## 3. 核心业务规则（必须严格遵守）
1. **配图与视觉核验**：只要 `source_images` 非空，必须用 `read_file` 逐张打开原始配图进行多模态核验；`tags.visual` 严禁填 `纯文字`。注意区分“印刷正常涂满阴影”与真实缺失/错图，严禁幻觉误判 `flagged`。
2. **算式/推理实算**：结合 `book_solution_hint` 与数学推演（必要时可用只读 Python 命令算数值/组合数）核对题干数据自洽性与可解性。
3. **100% 确凿 OCR 自动修复 (`auto_fixed`)**：
   - 仅当原题 `question` 存在**100% 确凿**的 OCR 错字/漏字/字母误识（经配图 + 原书解析 + 数学计算三重实证），才允许修改 `question`，且必须设置：
     - `audit.status = "auto_fixed"`, `audit.ocr_fixed = true`
     - `audit.original_question` = 修改前原文（须与 `question` 不同）
     - `audit.fix_reason` = 详细修改依据
   - 严禁篡改无误题干的文风，严禁修改 `id`, `chapter`, `chapter_title`, `source_images`, `book_solution_hint`。
4. **疑难隔离 (`flagged`)**：
   - 仅当题目存在真实配图缺失、图文根本矛盾、条件严重缺失导致无法独立求解且无法通过明确 OCR 修字还原时，设为 `audit.status = "flagged"`, `audit.solvable = false`，并写明具体 `audit.flag_reason`。
5. **题干纯净度**：`question` 严禁出现 `<details>`/`<summary>`、`## 解析`、`答案:`、`例 N` 前缀、竞赛括号出处残片或 Markdown 图片语法 `![]()`。
6. **每条记录必须包含的顶层键**：
   `id`, `chapter`, `chapter_title`, `question`, `source_images`, `book_solution_hint`, `tags`, `audit`
   其中 `audit.verified_by` 只能从 `["vision_diagram_check", "solution_crosscheck", "python_calc", "symbol_set_check", "crop_check"]` 中选取非空列表。

{taxonomy_summary}

## 4. 完成动作
使用 `write_file` 将全部 {len(expected_ids)} 条合法 JSON 记录写入 `{out_rel}` 后，调用 `finish` 工具返回符合 schema 的摘要对象。"""


def build_fix_validate_prompt(ch: int, err_text: str) -> str:
    return f"""你是 Stage 2 校验修复工程师。第 {ch:02d} 章在运行 `scripts/validate_enriched.py --chapters {ch} --merge-shards` 时校验失败。

## 错误输出
```text
{err_text[:6000]}
```

## 修复要求
1. 检查 `staging/enriched/shards/ch{ch:02d}_p*.jsonl`（若存在）或 `staging/enriched/ch{ch:02d}_enriched.jsonl`，对照 `staging/ch{ch:02d}_raw.jsonl` 与 `taxonomy.yaml` 定位所有报错条目。
2. 必须使用 `edit_file` 或 `write_file` 修正对应分片/文件（如果分片存在，**必须修改分片文件 `staging/enriched/shards/ch{ch:02d}_p*.jsonl`**，避免 `--merge-shards` 重新覆盖）。
3. 严禁修改 `staging/ch{ch:02d}_raw.jsonl`、`taxonomy.yaml` 或原始文件。
4. 修复完成后，调用 `finish` 工具返回符合 schema 的 JSON 对象。"""


def build_review_prompt(
    unit_chapters: list[int],
    report_rel: str,
    missing_hint_by_ch: dict[int, list[str]] | None = None,
) -> str:
    ch_tags = ", ".join(f"ch{c:02d}" for c in unit_chapters)
    missing_ids: list[str] = []
    if missing_hint_by_ch:
        for ch in unit_chapters:
            missing_ids.extend(missing_hint_by_ch.get(ch, []))

    missing_hint_clause = ""
    if missing_ids:
        missing_hint_clause = (
            f"以及以下无参考答案题（`MISSING_SOLUTION_HINT`）：`{json.dumps(missing_ids, ensure_ascii=False)}`，"
        )

    return f"""你是独立对抗审查员（Adversarial Reviewer, `model="pro"`），负责审查 {ch_tags} 的 Stage 2-3 产出。

## 1. 审查范围与文件
对以下章节逐章检查：
- 合并产物：`staging/enriched/chXX_enriched.jsonl`
- 原始对照：`staging/chXX_raw.jsonl` 与 `staging/symbol_audit/chXX_symbol_audit.json`
- 审核报告：`reports/chXX_audit_report.md`、`reports/chXX_ocr_fixes.md`
- Stage 3 交付与隔离：`output/chXX_<净短名>/` 与 `flagged/chXX_<净短名>/`

## 2. 必须执行的 3 项审查任务
1. **100% 复核所有 `auto_fixed` 与 `flagged` 题目**：
   - 如有配图，必须用 `read_file` 打开原始图片核验，严防把正常涂色/正常阴影/正常配图误标为 `flagged`。
   - 核验所有 `auto_fixed` 修改依据是否 100% 确凿，且 `question` 已同步更新到 `output/`。
2. **对抗性 False-Pass 猎杀（抽检高风险 `pass` 题）**：
   - 结合 `symbol_audit` 中的 `CIRCLED_NUMBER_MISMATCH`、`NEAR_MISS_COMBO`、`ISOLATED_QUESTION_POINT` 预警题{missing_hint_clause}打开配图或用 Python 实算抽检高风险 `pass` 题，记录抽检数 `sampled_pass_count` 与漏网硬错数 `false_pass_count`。
3. **`output/` 与 `flagged/` 隔离核验**：
   - `output/chXX_*/` 仅含 `pass` 和 `auto_fixed`，`problems.jsonl` 仅含 `id, chapter, question, images, tags`，绝不含任何 `flagged` 题目、图片或 `.md`。
   - `flagged/chXX_*/` 在有 `flagged` 题时完整包含隔离题、`flag_reason`、引用块与配图；在 `flagged == 0` 时不得存在空目录。

## 3. 核心审查纪律：无 Repro 不挑刺（Strict Empirical Rule）
- 严禁纯文字猜测或文风洁癖式驳回！
- 若全部通过，设 `verdict = "APPROVED"`，`issues = []`，`repro_scripts = []`。
- 若给出 `verdict = "REJECTED"`，**必须**用 `write_file` 在 `tests/repro/` 下编写至少 1 个独立可执行 Python Repro 脚本（例如 `tests/repro/repro_ch{unit_chapters[0]:02d}_<issue>.py`），用 `run_command` 运行该脚本确认其产生确定性失败（Exit Code != 0），并在 `repro_scripts` 中返回相对路径列表。

## 4. 交付物
使用 `write_file` 将完整审查分析报告写入 `{report_rel}`，随后调用 `finish` 返回符合 schema 的 JSON 对象。

## 5. 效率与防超时要求
- 将隔离核验、Schema/报告一致性校验与 Python 数学抽检合并写入 **1 个临时批处理脚本**（保存在自身 scratch 目录中）一次性运行，避免碎片化多轮调用。
- 仅检查目标章节自身产物与对应配图，**不要**读取无关章节报告或重复跑全仓库 `unittest`。
- 控制单审查单元在 **3~5 分钟、10 轮工具调用以内**快速完成报告落盘并立即调用 `finish`，防止长耗时触发 OAuth 401 过期。"""


def build_patch_prompt(
    unit_chapters: list[int],
    issues: list[str],
    repro_scripts: list[str],
    failure_logs: str,
) -> str:
    ch_tags = ", ".join(f"ch{c:02d}" for c in unit_chapters)
    return f"""你是定向修复工程师（Patch Worker），仅负责修复 {ch_tags} 被 Reviewer Repro 脚本实证的缺陷。

## 1. 失败的 Repro 脚本与日志
- Repro 脚本：{json.dumps(repro_scripts, ensure_ascii=False)}
- 阻塞问题列表：{json.dumps(issues, ensure_ascii=False)}
- 失败日志摘要：
```text
{failure_logs[:6000]}
```

## 2. 修复约束
1. 阅读上述 Repro 脚本与对应章节 `staging/enriched/shards/chXX_p*.jsonl`（若有分片则**必须修改分片文件**，否则修改 `staging/enriched/chXX_enriched.jsonl`）。
2. 遵循最小补丁原则，使用 `edit_file` / `write_file` 仅修复使 Repro 脚本通过（Exit Code = 0）所需的错误记录；**严禁修改 Repro 脚本本身**，严禁修改 `staging/chXX_raw.jsonl`、`taxonomy.yaml` 或 `scripts/extract_raw.py`。
3. 修复完成后，调用 `finish` 返回符合 schema 的 JSON 对象。"""


def group_chapters_for_review(
    chapters: list[int],
    counts_by_ch: dict[int, int],
    img_counts_by_ch: dict[int, int],
) -> list[list[int]]:
    """Large or diagram-heavy chapters get standalone Pro reviewers; 2~3 small chapters merge."""
    units: list[list[int]] = []
    small_buf: list[int] = []
    small_q_sum = 0

    for ch in chapters:
        q_cnt = counts_by_ch.get(ch, 0)
        img_cnt = img_counts_by_ch.get(ch, 0)
        if q_cnt >= 45 or img_cnt >= 15:
            if small_buf:
                units.append(small_buf)
                small_buf = []
                small_q_sum = 0
            units.append([ch])
        else:
            if small_buf and (len(small_buf) >= 3 or small_q_sum + q_cnt > 65):
                units.append(small_buf)
                small_buf = []
                small_q_sum = 0
            small_buf.append(ch)
            small_q_sum += q_cnt

    if small_buf:
        units.append(small_buf)
    return units


async def main() -> None:
    run_args = globals().get("args") or {}
    python_bin = resolve_python_bin()
    log(f"Using Python interpreter: {python_bin}")

    skill_scripts_dir = run_args.get("skill_scripts_dir")
    wave_id = run_args.get("wave")
    explicit_chapters = run_args.get("chapters")
    shard_size = int(run_args.get("shard_size", 25))
    batch_concurrency = int(run_args.get("batch_concurrency", 4))
    review_concurrency = max(1, int(run_args.get("review_concurrency", 1)))
    skip_completed = bool(run_args.get("skip_completed", True))
    run_reviewer = bool(run_args.get("run_reviewer", True))
    max_fix_rounds = int(run_args.get("max_fix_rounds", 1))
    target_wave_weight = float(run_args.get("wave_target_qs", 250))

    state = load_wave_state()
    empty_set = set(state.get("empty_chapters", []))
    pilot_set = {int(c) for c in state.get("pilot_completed", [])}
    extra_excluded = {int(c) for c in (run_args.get("exclude_chapters") or [])}

    if explicit_chapters:
        target_chapters = sorted({int(c) for c in explicit_chapters})
        run_label = f"custom_{'_'.join(f'{c:02d}' for c in target_chapters)}"
    elif wave_id is not None:
        wid = int(wave_id)
        if WAVES_CONFIG_PATH.is_file():
            waves_map = load_waves_from_file(WAVES_CONFIG_PATH)
        else:
            waves_map, detected_empty = plan_balanced_waves(
                STAGING_DIR,
                target_wave_weight=target_wave_weight,
                exclude_chapters=pilot_set | extra_excluded,
            )
            empty_set |= set(detected_empty)
            state["empty_chapters"] = sorted(empty_set)
        if wid not in waves_map:
            raise ValueError(
                f"Invalid wave {wid}; available wave IDs: {sorted(waves_map.keys())}"
            )
        target_chapters = list(waves_map[wid])
        run_label = f"wave_{wid}"
    else:
        raise ValueError("Args must specify 'wave' or 'chapters' ([int, ...]).")

    non_empty_targets = [c for c in target_chapters if c not in empty_set]
    skipped_empty = [c for c in target_chapters if c in empty_set]
    if skipped_empty:
        log(f"[SKIP] Excluding empty chapter(s): {skipped_empty}")
    target_chapters = non_empty_targets
    if not target_chapters:
        log("[SKIP] No non-empty target chapters to process.")
        return

    if skip_completed:
        active_chapters = [
            c
            for c in target_chapters
            if state["chapters"].get(f"ch{c:02d}", {}).get("status") != "approved"
        ]
        skipped_chapters = [c for c in target_chapters if c not in active_chapters]
        if skipped_chapters:
            log(f"[RESUME] Skipping already-approved chapters: {skipped_chapters}")
    else:
        active_chapters = list(target_chapters)

    if not active_chapters:
        log("[DONE] All target chapters are already approved in staging/wave_state.json.")
        return

    log(
        f"Target run={run_label}, active_chapters={active_chapters}, "
        f"shard_size={shard_size}, concurrency={batch_concurrency}, review_concurrency={review_concurrency}"
    )

    # ------------------------------------------------------------------
    # Phase 1: Precheck
    # ------------------------------------------------------------------
    phase("Precheck")
    precheck_script = resolve_script("precheck_geometry_symbols.py", skill_scripts_dir=skill_scripts_dir)
    run_cli(
        [
            python_bin,
            str(precheck_script),
            "--root-dir",
            str(ROOT_DIR),
            "--chapters",
            *[str(c) for c in active_chapters],
        ]
    )

    # ------------------------------------------------------------------
    # Phase 2: Enrich (sharded + checkpoint/resume + batched parallel)
    # ------------------------------------------------------------------
    phase("Enrich")
    taxonomy_summary = build_taxonomy_summary(python_bin)
    enrich_tasks: list[dict[str, Any]] = []
    counts_by_ch: dict[int, int] = {}
    img_counts_by_ch: dict[int, int] = {}
    missing_hint_by_ch: dict[int, list[str]] = {}

    for ch in active_chapters:
        raw_path = STAGING_DIR / f"ch{ch:02d}_raw.jsonl"
        raw_records = load_jsonl(raw_path)
        counts_by_ch[ch] = len(raw_records)
        img_counts_by_ch[ch] = sum(1 for r in raw_records if r.get("source_images"))
        missing_hint_by_ch[ch] = find_missing_hint_ids(raw_records)

        audit_path = SYMBOL_AUDIT_DIR / f"ch{ch:02d}_symbol_audit.json"
        audit_data = json.loads(audit_path.read_text(encoding="utf-8"))
        suspect_by_id = {
            r["id"]: {
                "id": r["id"],
                "suspect_reasons": r["suspect_reasons"],
                "near_miss_combos": r["near_miss_combos"],
                "diff": r["diff"],
            }
            for r in audit_data.get("records", [])
            if r.get("is_suspect")
        }

        num_shards = max(1, math.ceil(len(raw_records) / max(1, shard_size)))
        if SHARDS_DIR.is_dir():
            for stale in sorted(SHARDS_DIR.glob(f"ch{ch:02d}_p*.jsonl")):
                if num_shards == 1:
                    stale.unlink()
                    log(f"[CLEANUP] Removed stale shard {stale.relative_to(ROOT_DIR)}")
                else:
                    suffix = stale.stem.split("_p", 1)[-1]
                    if suffix.isdigit() and int(suffix) > num_shards:
                        stale.unlink()
                        log(f"[CLEANUP] Removed stale shard {stale.relative_to(ROOT_DIR)}")
        for shard_idx in range(num_shards):
            slice_recs = raw_records[shard_idx * shard_size : (shard_idx + 1) * shard_size]
            expected_ids = [r["id"] for r in slice_recs]
            if num_shards == 1:
                shard_label = f"ch{ch:02d}_full"
                out_path = ENRICHED_DIR / f"ch{ch:02d}_enriched.jsonl"
                out_rel = f"staging/enriched/ch{ch:02d}_enriched.jsonl"
            else:
                p_num = shard_idx + 1
                shard_label = f"ch{ch:02d}_p{p_num}"
                out_path = SHARDS_DIR / f"ch{ch:02d}_p{p_num}.jsonl"
                out_rel = f"staging/enriched/shards/ch{ch:02d}_p{p_num}.jsonl"

            if skip_completed and is_valid_shard_file(out_path, expected_ids):
                log(f"[RESUME] Skip valid existing shard {out_rel} ({len(expected_ids)} records)")
                continue

            suspect_slice = [suspect_by_id[rid] for rid in expected_ids if rid in suspect_by_id]
            shard_missing_hints = find_missing_hint_ids(slice_recs)
            enrich_tasks.append(
                {
                    "chapter": ch,
                    "shard_label": shard_label,
                    "output_rel": out_rel,
                    "expected_ids": expected_ids,
                    "suspect_slice": suspect_slice,
                    "missing_hint_ids": shard_missing_hints,
                }
            )

    if enrich_tasks:
        ENRICHED_DIR.mkdir(parents=True, exist_ok=True)
        SHARDS_DIR.mkdir(parents=True, exist_ok=True)
        batches = chunk_list(enrich_tasks, batch_concurrency)
        log(f"Running {len(enrich_tasks)} Enricher shard(s) across {len(batches)} batch(es)...")

        async def _run_enrich_batch(batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return await parallel(
                batch,
                lambda item: agent(
                    prompt=build_enrich_prompt(item, taxonomy_summary),
                    schema=ENRICH_RESULT_SCHEMA,
                    role=f"Enrich {item['shard_label']}",
                    type_name="self",
                    workspace="inherit",
                    model="flash",
                ),
            )

        enrich_results_nested = await pipeline(batches, _run_enrich_batch)
        for batch_res in enrich_results_nested:
            for r in batch_res:
                log(
                    f"[ENRICHED] {r['shard']} -> {r['output_path']} "
                    f"(n={r['count']}, pass={r['pass_count']}, auto_fixed={r['auto_fixed_count']}, flagged={r['flagged_count']})"
                )
    else:
        log("[RESUME] All enrich shards already exist and are valid.")

    # ------------------------------------------------------------------
    # Phase 3: Validate & Export
    # ------------------------------------------------------------------
    phase("Validate & Export")
    for ch in active_chapters:
        val_proc = run_cli(
            build_validate_cmd(ch, python_bin, skill_scripts_dir=skill_scripts_dir),
            check=False,
        )
        if val_proc.returncode != 0:
            err_msg = (val_proc.stdout + "\n" + val_proc.stderr).strip()
            log(f"[WARN] ch{ch:02d} failed initial validation; launching targeted fix agent...")
            fix_res = await agent(
                prompt=build_fix_validate_prompt(ch, err_msg),
                schema=FIX_VALIDATE_SCHEMA,
                role=f"Fix Validate ch{ch:02d}",
                type_name="self",
                workspace="inherit",
                model="flash",
            )
            log(f"[FIXED] ch{ch:02d}: {fix_res['summary']}")
            run_cli(
                build_validate_cmd(ch, python_bin, skill_scripts_dir=skill_scripts_dir),
                check=True,
            )

    export_script = resolve_script("export_output.py", skill_scripts_dir=skill_scripts_dir)
    run_cli(
        [
            python_bin,
            str(export_script),
            "--root-dir",
            str(ROOT_DIR),
            "--chapters",
            *[str(c) for c in active_chapters],
        ],
        check=True,
    )

    # ------------------------------------------------------------------
    # Phase 4 & 5: Adversarial Review + Triage & Auto-Patch
    # ------------------------------------------------------------------
    review_by_ch: dict[int, dict[str, Any]] = {}
    absorbed_repros: list[str] = []

    if run_reviewer:
        phase("Adversarial Review & Triage")
        TEAMWORK_REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
        TESTS_REPRO_DIR.mkdir(parents=True, exist_ok=True)
        review_units = group_chapters_for_review(active_chapters, counts_by_ch, img_counts_by_ch)
        rev_batches = chunk_list(review_units, review_concurrency)
        log(
            f"Launching {len(review_units)} Pro Reviewer unit(s) across "
            f"{len(rev_batches)} batch(es) (review_concurrency={review_concurrency})..."
        )

        def _unit_label(chs: list[int]) -> str:
            return f"ch{chs[0]:02d}" if len(chs) == 1 else f"ch{chs[0]:02d}-ch{chs[-1]:02d}"

        async def _run_review_batch(batch: list[list[int]]) -> list[dict[str, Any]]:
            return await parallel(
                batch,
                lambda chs: agent(
                    prompt=build_review_prompt(
                        chs,
                        f".agents/teamwork/wave_reviews/{run_label}_review_{_unit_label(chs)}.md",
                        missing_hint_by_ch=missing_hint_by_ch,
                    ),
                    schema=REVIEW_RESULT_SCHEMA,
                    role=f"Review {_unit_label(chs)}",
                    type_name="self",
                    workspace="inherit",
                    model="pro",
                ),
            )

        for batch_idx, batch in enumerate(rev_batches, start=1):
            log(f"[REVIEW] Batch {batch_idx}/{len(rev_batches)}: {[_unit_label(chs) for chs in batch]}")
            batch_reviews = await _run_review_batch(batch)

            for rev in batch_reviews:
                chs = [int(c) for c in rev["chapters"]]
                label = _unit_label(chs)
                verdict = rev["verdict"]
                repros = [str(p) for p in rev.get("repro_scripts", []) if str(p).strip()]

                if verdict == "REJECTED" and not repros:
                    log(
                        f"[TRIAGE] {label}: Reviewer returned REJECTED without repro scripts -> "
                        "overridden to APPROVED per Strict Empirical Rule."
                    )
                    verdict = "APPROVED"

                if verdict == "REJECTED" and repros:
                    failing_repros: list[str] = []
                    failure_logs_parts: list[str] = []
                    for rp in repros:
                        rp_path = Path(rp) if Path(rp).is_absolute() else (ROOT_DIR / rp)
                        if not rp_path.is_file():
                            log(f"[TRIAGE] Ignoring nonexistent repro script: {rp}")
                            continue
                        rp_proc = run_cli([python_bin, str(rp_path)], check=False)
                        if rp_proc.returncode != 0:
                            failing_repros.append(rp)
                            failure_logs_parts.append(
                                f"=== {rp} (rc={rp_proc.returncode}) ===\n{rp_proc.stdout}\n{rp_proc.stderr}"
                            )

                    initial_failing_repros = list(failing_repros)

                    if not failing_repros:
                        log(f"[TRIAGE] {label}: All submitted repro scripts exited 0 -> APPROVED.")
                        verdict = "APPROVED"
                    else:
                        for round_idx in range(1, max_fix_rounds + 1):
                            log(f"[PATCH] {label} round {round_idx}/{max_fix_rounds} for {failing_repros}")
                            patch_res = await agent(
                                prompt=build_patch_prompt(
                                    chs,
                                    rev.get("issues", []),
                                    failing_repros,
                                    "\n".join(failure_logs_parts),
                                ),
                                schema=PATCH_RESULT_SCHEMA,
                                role=f"Patch {label} r{round_idx}",
                                type_name="self",
                                workspace="inherit",
                                model="flash",
                            )
                            log(f"[PATCHED] {label}: {patch_res['summary']}")

                            for c in chs:
                                run_cli(
                                    build_validate_cmd(c, python_bin, skill_scripts_dir=skill_scripts_dir),
                                    check=True,
                                )
                            run_cli(
                                [
                                    python_bin,
                                    str(export_script),
                                    "--root-dir",
                                    str(ROOT_DIR),
                                    "--chapters",
                                    *[str(c) for c in chs],
                                ],
                                check=True,
                            )

                            still_failing: list[str] = []
                            new_logs: list[str] = []
                            for rp in failing_repros:
                                rp_path = Path(rp) if Path(rp).is_absolute() else (ROOT_DIR / rp)
                                re_proc = run_cli([python_bin, str(rp_path)], check=False)
                                if re_proc.returncode != 0:
                                    still_failing.append(rp)
                                    new_logs.append(
                                        f"=== {rp} (rc={re_proc.returncode}) ===\n{re_proc.stdout}\n{re_proc.stderr}"
                                    )
                            failing_repros = still_failing
                            failure_logs_parts = new_logs
                            if not failing_repros:
                                break

                        if not failing_repros:
                            TESTS_REGRESSION_DIR.mkdir(parents=True, exist_ok=True)
                            for rp in initial_failing_repros:
                                src_rp = Path(rp) if Path(rp).is_absolute() else (ROOT_DIR / rp)
                                if src_rp.is_file():
                                    dst_rp = TESTS_REGRESSION_DIR / src_rp.name
                                    shutil.copy2(src_rp, dst_rp)
                                    absorbed_repros.append(
                                        str(dst_rp.relative_to(ROOT_DIR)).replace("\\", "/")
                                    )
                            verdict = "APPROVED"
                            log(
                                f"[TRIAGE] {label}: All repros now pass (rc=0) -> "
                                "APPROVED & absorbed into tests/regression/."
                            )
                        else:
                            verdict = "REJECTED"
                            log(
                                f"[TRIAGE] {label}: Repro(s) still failing after "
                                f"{max_fix_rounds} round(s): {failing_repros}"
                            )

                for c in chs:
                    rev_info = {
                        "verdict": verdict,
                        "sampled_pass_count": rev["sampled_pass_count"],
                        "false_pass_count": rev["false_pass_count"],
                        "report_path": rev["report_path"],
                    }
                    review_by_ch[c] = rev_info
                    state["chapters"][f"ch{c:02d}"] = build_chapter_state_entry(
                        c, rev_info, run_reviewer=True
                    )
                save_wave_state(state)
                log(f"[CHECKPOINT] Saved wave_state.json after review unit {label} -> verdict={verdict}")
    else:
        phase("Adversarial Review (Skipped)")
        log("run_reviewer=False -> skipping Pro adversarial review.")
        for ch in active_chapters:
            state["chapters"][f"ch{ch:02d}"] = build_chapter_state_entry(
                ch, {}, run_reviewer=False
            )

    # ------------------------------------------------------------------
    # Phase 6: Persist State & Generate Wave Summary
    # ------------------------------------------------------------------
    phase("Summary & State")
    summary_rows: list[dict[str, Any]] = []
    for ch in target_chapters:
        ch_key = f"ch{ch:02d}"
        if ch_key in state["chapters"]:
            ch_entry = state["chapters"][ch_key]
        else:
            ch_entry = build_chapter_state_entry(
                ch, review_by_ch.get(ch, {}), run_reviewer=run_reviewer
            )
            state["chapters"][ch_key] = ch_entry
        summary_rows.append(ch_entry)

    prev_repros = state.get("waves", {}).get(run_label, {}).get("absorbed_repros", [])
    merged_repros: list[str] = []
    seen_repros: set[str] = set()
    for rp in [*prev_repros, *absorbed_repros]:
        if rp not in seen_repros:
            seen_repros.add(rp)
            merged_repros.append(rp)

    state.setdefault("waves", {})[run_label] = {
        "chapters": target_chapters,
        "all_approved": all(r["status"] == "approved" for r in summary_rows),
        "absorbed_repros": merged_repros,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    save_wave_state(state)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_md_path = REPORTS_DIR / f"{run_label}_summary.md"
    md_lines: list[str] = [
        f"# {run_label} 执行汇总报告",
        "",
        f"- **波次章节**: `{target_chapters}`（本轮处理: `{active_chapters}`）",
        f"- **总题数**: {sum(r['total'] for r in summary_rows)}",
        f"- **`pass` / `auto_fixed` / `flagged`**: "
        f"{sum(r['pass'] for r in summary_rows)} / {sum(r['auto_fixed'] for r in summary_rows)} / {sum(r['flagged'] for r in summary_rows)}",
        f"- **沉淀回归用例**: `{merged_repros}`",
        "",
        "| 章节 | 总题数 | pass | auto_fixed | flagged | Reviewer 结论 | False-Pass 漏网 |",
        "| :--- | ---: | ---: | ---: | ---: | :--- | ---: |",
    ]
    for r in summary_rows:
        md_lines.append(
            f"| ch{r['chapter']:02d} | {r['total']} | {r['pass']} | {r['auto_fixed']} | "
            f"{r['flagged']} | {r.get('verdict', r.get('status', '').upper())} | {r.get('false_pass_count', 0)} |"
        )
    summary_md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    log(f"Saved state -> {WAVE_STATE_PATH}")
    log(f"Saved summary -> {summary_md_path}")
    for line in md_lines[6:]:
        log(line)


await main()
