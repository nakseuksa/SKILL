#!/usr/bin/env python3
"""
Generic Project Scaffolding & Wave Planning CLI (`init_project.py`).

Creates the standard directory layout for a new OCR math question bank project,
initializes a clean `staging/wave_state.json`, optionally copies generic pipeline
scripts, `taxonomy.yaml`, and renders `PIPELINE_RUNBOOK.md` from skill templates,
and can auto-plan balanced multi-wave execution batches (`staging/waves.json`)
after Stage 1 extraction completes.

Pure Python stdlib.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SKILL_ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS_DIR = SKILL_ROOT / "scripts"
SKILL_RESOURCES_DIR = SKILL_ROOT / "resources"

STANDARD_DIRS = (
    Path("staging/enriched/shards"),
    Path("staging/symbol_audit"),
    Path("scripts"),
    Path("reports"),
    Path("tests/repro"),
    Path("tests/regression"),
    Path(".agents/teamwork/wave_reviews"),
)

COPYABLE_SCRIPTS = (
    "precheck_geometry_symbols.py",
    "validate_enriched.py",
    "export_output.py",
    "wave_workflow.py",
)

RAW_FILE_RE = re.compile(r"^ch(\d+)_raw\.jsonl$")


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with tmp_path.open("w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def ensure_directories(root_dir: Path) -> list[Path]:
    created: list[Path] = []
    for rel in STANDARD_DIRS:
        target = root_dir / rel
        if not target.exists():
            created.append(target)
        target.mkdir(parents=True, exist_ok=True)
    return created


def ensure_wave_state(root_dir: Path, book_name: str) -> tuple[Path, bool]:
    state_path = root_dir / "staging" / "wave_state.json"
    if state_path.is_file():
        return state_path, False
    payload = {
        "version": 1,
        "book_name": book_name,
        "pilot_completed": [],
        "empty_chapters": [],
        "chapters": {},
        "waves": {},
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    atomic_write_json(state_path, payload)
    return state_path, True


def copy_with_guard(src: Path, dst: Path, *, force: bool) -> str:
    if not src.is_file():
        raise FileNotFoundError(f"Missing skill asset: {src}")
    if dst.exists() and not force:
        return "skipped"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return "copied"


def render_runbook(
    template_path: Path,
    dst: Path,
    *,
    book_name: str,
    root_dir: Path,
    force: bool,
) -> str:
    if not template_path.is_file():
        raise FileNotFoundError(f"Missing runbook template: {template_path}")
    if dst.exists() and not force:
        return "skipped"
    text = template_path.read_text(encoding="utf-8")
    rendered = (
        text.replace("{{BOOK_NAME}}", book_name)
        .replace("{{WORKSPACE_ROOT}}", str(root_dir.resolve()))
        .replace("{{SKILL_ROOT}}", str(SKILL_ROOT))
        .replace("{{SKILL_SCRIPTS_DIR}}", str(SKILL_SCRIPTS_DIR))
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(rendered, encoding="utf-8")
    return "copied"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                records.append(json.loads(stripped))
    return records


def plan_waves(
    root_dir: Path,
    *,
    book_name: str,
    target_weight: float = 250.0,
    exclude_chapters: list[int] | None = None,
) -> dict[str, Any]:
    staging_dir = root_dir / "staging"
    excluded = {int(c) for c in (exclude_chapters or [])}

    found_files: list[tuple[int, Path]] = []
    if staging_dir.is_dir():
        for p in staging_dir.glob("ch*_raw.jsonl"):
            m = RAW_FILE_RE.match(p.name)
            if m:
                found_files.append((int(m.group(1)), p))

    if not found_files:
        raise FileNotFoundError(
            f"No ch*_raw.jsonl files found in {staging_dir}. Run Stage 1 extraction first."
        )

    empty_chapters: list[int] = []
    chapter_stats: dict[str, dict[str, Any]] = {}
    active_items: list[dict[str, Any]] = []

    for ch, path in sorted(found_files, key=lambda x: x[0]):
        recs = load_jsonl(path)
        q_cnt = len(recs)
        q_with_imgs = sum(1 for r in recs if r.get("source_images"))
        img_cnt = sum(len(r.get("source_images") or []) for r in recs)
        weight = round(q_cnt + 0.5 * img_cnt, 2)

        chapter_stats[str(ch)] = {
            "chapter": ch,
            "questions": q_cnt,
            "questions_with_images": q_with_imgs,
            "images": img_cnt,
            "weight": weight,
        }

        if q_cnt == 0:
            empty_chapters.append(ch)
            continue
        if ch in excluded:
            continue
        active_items.append(chapter_stats[str(ch)])

    waves: dict[str, list[int]] = {}
    wave_summaries: list[dict[str, Any]] = []
    cur_items: list[dict[str, Any]] = []
    cur_weight = 0.0
    wave_idx = 1

    def _flush(idx: int, items: list[dict[str, Any]]) -> None:
        waves[str(idx)] = [it["chapter"] for it in items]
        wave_summaries.append(
            {
                "wave": idx,
                "chapters": [it["chapter"] for it in items],
                "chapter_count": len(items),
                "questions": sum(it["questions"] for it in items),
                "questions_with_images": sum(it["questions_with_images"] for it in items),
                "images": sum(it["images"] for it in items),
                "weight": round(sum(it["weight"] for it in items), 2),
            }
        )

    for item in active_items:
        w = float(item["weight"])
        if cur_items and cur_weight + w > target_weight:
            _flush(wave_idx, cur_items)
            wave_idx += 1
            cur_items = []
            cur_weight = 0.0
        cur_items.append(item)
        cur_weight += w

    if cur_items:
        _flush(wave_idx, cur_items)

    plan_payload: dict[str, Any] = {
        "version": 1,
        "book_name": book_name,
        "wave_target_qs": target_weight,
        "image_weight": 0.5,
        "excluded_chapters": sorted(excluded),
        "empty_chapters": sorted(empty_chapters),
        "waves": waves,
        "wave_summaries": wave_summaries,
        "chapter_stats": chapter_stats,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    waves_path = staging_dir / "waves.json"
    atomic_write_json(waves_path, plan_payload)
    return plan_payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize a new OCR math bank project workspace and optionally plan balanced waves."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Target project workspace root directory (default: cwd).",
    )
    parser.add_argument(
        "--book-name",
        type=str,
        default=None,
        help="Book or question bank name (default: directory name of --root).",
    )
    parser.add_argument(
        "--copy-scripts",
        action="store_true",
        help="Copy generic Stage 2-3 pipeline scripts into <root>/scripts/.",
    )
    parser.add_argument(
        "--copy-taxonomy",
        action="store_true",
        help="Copy resources/taxonomy_template.yaml to <root>/taxonomy.yaml.",
    )
    parser.add_argument(
        "--copy-runbook",
        action="store_true",
        help="Render resources/runbook_template.md to <root>/PIPELINE_RUNBOOK.md.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files when copying scripts, taxonomy, or runbook.",
    )
    parser.add_argument(
        "--plan-waves",
        action="store_true",
        help="Scan staging/ch*_raw.jsonl and generate balanced staging/waves.json.",
    )
    parser.add_argument(
        "--wave-target-qs",
        type=float,
        default=250.0,
        help="Target weighted question count per wave when --plan-waves is set (default: 250).",
    )
    parser.add_argument(
        "--exclude-chapters",
        nargs="+",
        type=int,
        default=[],
        help="Chapter numbers to exclude from wave planning (e.g. completed pilot chapters).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root_dir: Path = args.root.resolve()
    book_name: str = args.book_name or root_dir.name or "MathQuestionBank"

    ensure_directories(root_dir)
    state_path, state_created = ensure_wave_state(root_dir, book_name)
    print(
        f"[INIT] Workspace: {root_dir} (book_name={book_name}, "
        f"wave_state={'created' if state_created else 'exists'} -> {state_path})"
    )

    if args.copy_scripts:
        for script_name in COPYABLE_SCRIPTS:
            src = SKILL_SCRIPTS_DIR / script_name
            dst = root_dir / "scripts" / script_name
            status = copy_with_guard(src, dst, force=args.force)
            print(f"[SCRIPTS] {script_name}: {status} -> {dst}")

    if args.copy_taxonomy:
        src = SKILL_RESOURCES_DIR / "taxonomy_template.yaml"
        dst = root_dir / "taxonomy.yaml"
        status = copy_with_guard(src, dst, force=args.force)
        print(f"[TAXONOMY] taxonomy.yaml: {status} -> {dst}")

    if args.copy_runbook:
        src = SKILL_RESOURCES_DIR / "runbook_template.md"
        dst = root_dir / "PIPELINE_RUNBOOK.md"
        status = render_runbook(
            src,
            dst,
            book_name=book_name,
            root_dir=root_dir,
            force=args.force,
        )
        print(f"[RUNBOOK] PIPELINE_RUNBOOK.md: {status} -> {dst}")

    if args.plan_waves:
        plan = plan_waves(
            root_dir,
            book_name=book_name,
            target_weight=args.wave_target_qs,
            exclude_chapters=args.exclude_chapters,
        )
        waves_path = root_dir / "staging" / "waves.json"
        print(
            f"[WAVES] Planned {len(plan['waves'])} wave(s) -> {waves_path} "
            f"(empty_chapters={plan['empty_chapters']}, excluded={plan['excluded_chapters']})"
        )
        for ws in plan["wave_summaries"]:
            print(
                f"  - Wave {ws['wave']}: chapters={ws['chapters']}, "
                f"questions={ws['questions']}, images={ws['images']}, weight={ws['weight']}"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
