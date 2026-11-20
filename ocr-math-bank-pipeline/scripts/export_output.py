#!/usr/bin/env python3
"""
Stage 3 Export & Rendering Script (`export_output.py`).

Reads validated `staging/enriched/chXX_enriched.jsonl` and splits records by `audit.status`:
  1. `pass` / `auto_fixed` -> `output/chXX_<章节净短名>/` (pure delivery fields only):
     - `images/chXX_NNN_1.<ext>`, ...
     - `problems.jsonl` (keys: id, chapter, question, images, tags)
     - `md/chXX_NNN.md` (YAML frontmatter + pure question + relative image links)
  2. `flagged` -> quarantined into `flagged/chXX_<章节净短名>/` (only created if >= 1 flagged):
     - `images/chXX_NNN_1.<ext>`, ...
     - `problems.jsonl` (keys: id, chapter, question, images, tags, flag_reason)
     - `md/chXX_NNN.md` (YAML frontmatter with flagged/flag_reason + warning blockquote + question + images)

Usage:
  python scripts/export_output.py --chapters 1 28
  python scripts/export_output.py --all --root-dir /path/to/book
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

# Allow importing sibling validate_enriched when invoked as script or module
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from validate_enriched import (  # noqa: E402
    detect_default_root_dir,
    load_jsonl,
    load_taxonomy,
    validate_chapter,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = detect_default_root_dir()
CHAPTER_PREFIX_RE = re.compile(r"^\s*第\s*[一二三四五六七八九十百零0-9]+\s*章\s*")
PART_PREFIX_IN_TITLE_RE = re.compile(r"第.*?篇")
ORDINAL_PREFIX_TAGS = ("五式", "之首", "之二", "之三", "之四", "之五")
ILLEGAL_FILENAME_RE = re.compile(r"[\\/:*?\"<>|\s()（）“”‘’'\"、，,。.：:；;！!？?—\-]+")


def sanitize_chapter_short_name(chapter_title: str, chapter: int) -> str:
    """
    Derive clean short chapter directory suffix from `chapter_title`.
    When `——` is present, takes the right-hand part if the prefix is an ordinal/part
    marker (e.g. `之首`..`之五`, `五式`, `第X篇`), otherwise takes the left-hand part.
    """
    name = CHAPTER_PREFIX_RE.sub("", chapter_title or "").strip()
    if "——" in name:
        before, after = name.split("——", 1)
        if after.strip() and (
            any(tag in before for tag in ORDINAL_PREFIX_TAGS)
            or PART_PREFIX_IN_TITLE_RE.search(before)
        ):
            name = after.strip()
        elif before.strip():
            name = before.strip()
    cleaned = ILLEGAL_FILENAME_RE.sub("", name)
    if not cleaned:
        return f"ch{chapter:02d}"
    return cleaned[:32]


def render_question_markdown(
    rec: dict[str, Any],
    md_rel_images: list[str],
    *,
    flagged: bool = False,
    flag_reason: str | None = None,
) -> str:
    tags = rec["tags"]
    frontmatter: dict[str, Any] = {
        "id": rec["id"],
        "chapter": rec["chapter"],
        "domain": tags["domain"],
        "topic": tags["topic"],
        "method": tags["method"],
        "difficulty": tags["difficulty"],
        "visual": tags["visual"],
        "format": tags["format"],
        "extra_tags": tags["extra_tags"],
    }
    if flagged:
        frontmatter["flagged"] = True
        frontmatter["flag_reason"] = flag_reason or ""
    frontmatter["images"] = md_rel_images

    fm_yaml = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    ).strip()

    parts = [
        "---",
        fm_yaml,
        "---",
        "",
    ]
    if flagged:
        reason_line = " ".join((flag_reason or "").splitlines()).strip()
        parts.append(f"> ⚠️ 隔离原因（flagged）：{reason_line}")
        parts.append("")
    parts.append(rec["question"].strip())

    if md_rel_images:
        parts.append("")
        for img_ref in md_rel_images:
            parts.append(f"![]({img_ref})")
            parts.append("")
        return "\n".join(parts)
    return "\n".join(parts) + "\n"


def _write_chapter_bundle(
    target_dir: Path,
    records: list[dict[str, Any]],
    root_dir: Path,
    *,
    is_flagged: bool,
) -> None:
    images_dir = target_dir / "images"
    md_dir = target_dir / "md"
    images_dir.mkdir(parents=True, exist_ok=True)
    md_dir.mkdir(parents=True, exist_ok=True)

    problems_lines: list[str] = []
    for rec in records:
        qid = rec["id"]
        jsonl_images: list[str] = []
        md_images: list[str] = []

        for idx, src_rel in enumerate(rec["source_images"], start=1):
            src_file = root_dir / src_rel
            ext = src_file.suffix or ".jpg"
            dest_name = f"{qid}_{idx}{ext}"
            shutil.copy2(src_file, images_dir / dest_name)
            jsonl_images.append(f"images/{dest_name}")
            md_images.append(f"../images/{dest_name}")

        delivered: dict[str, Any] = {
            "id": qid,
            "chapter": rec["chapter"],
            "question": rec["question"],
            "images": jsonl_images,
            "tags": rec["tags"],
        }
        flag_reason: str | None = None
        if is_flagged:
            flag_reason = rec["audit"]["flag_reason"]
            delivered["flag_reason"] = flag_reason

        problems_lines.append(json.dumps(delivered, ensure_ascii=False))

        md_content = render_question_markdown(
            rec,
            md_images,
            flagged=is_flagged,
            flag_reason=flag_reason,
        )
        (md_dir / f"{qid}.md").write_text(md_content, encoding="utf-8")

    jsonl_text = ("\n".join(problems_lines) + "\n") if problems_lines else ""
    (target_dir / "problems.jsonl").write_text(jsonl_text, encoding="utf-8")


def _remove_stale_chapter_dirs(base_dir: Path, chapter: int) -> None:
    if not base_dir.is_dir():
        return
    prefix = f"ch{chapter:02d}_"
    for entry in base_dir.iterdir():
        if entry.is_dir() and entry.name.startswith(prefix):
            shutil.rmtree(entry)


def export_chapter_split(
    chapter: int,
    root_dir: Path,
    staging_dir: Path,
    output_dir: Path,
    flagged_dir: Path,
    taxonomy_path: Path,
    skip_validate: bool = False,
) -> dict[str, Any] | None:
    enriched_path = staging_dir / "enriched" / f"ch{chapter:02d}_enriched.jsonl"
    if not enriched_path.is_file():
        raise FileNotFoundError(f"Missing enriched file: {enriched_path}")

    if not skip_validate:
        spec = load_taxonomy(taxonomy_path)
        records, errors = validate_chapter(
            chapter, staging_dir=staging_dir, spec=spec, root_dir=root_dir
        )
        if errors:
            raise ValueError(
                f"ch{chapter:02d} failed validation before export:\n  "
                + "\n  ".join(errors)
            )
    else:
        records = load_jsonl(enriched_path)

    if not records:
        _remove_stale_chapter_dirs(output_dir, chapter)
        _remove_stale_chapter_dirs(flagged_dir, chapter)
        return None

    short_name = sanitize_chapter_short_name(records[0]["chapter_title"], chapter)
    ch_out_dir = output_dir / f"ch{chapter:02d}_{short_name}"
    ch_flag_dir = flagged_dir / f"ch{chapter:02d}_{short_name}"

    # Clean any existing chapter directories before rebuilding to avoid ghost files
    _remove_stale_chapter_dirs(output_dir, chapter)
    _remove_stale_chapter_dirs(flagged_dir, chapter)

    clean_records = [
        r for r in records if r["audit"]["status"] in {"pass", "auto_fixed"}
    ]
    flagged_records = [
        r for r in records if r["audit"]["status"] == "flagged"
    ]

    _write_chapter_bundle(ch_out_dir, clean_records, root_dir, is_flagged=False)

    exported_flag_dir: Path | None = None
    if flagged_records:
        _write_chapter_bundle(ch_flag_dir, flagged_records, root_dir, is_flagged=True)
        exported_flag_dir = ch_flag_dir

    return {
        "output_dir": ch_out_dir,
        "flagged_dir": exported_flag_dir,
        "clean_count": len(clean_records),
        "flagged_count": len(flagged_records),
    }


def export_chapter(
    chapter: int,
    root_dir: Path,
    staging_dir: Path,
    output_dir: Path,
    taxonomy_path: Path,
    skip_validate: bool = False,
    flagged_dir: Path | None = None,
) -> Path | None:
    resolved_flagged = flagged_dir if flagged_dir is not None else (root_dir / "flagged")
    res = export_chapter_split(
        chapter=chapter,
        root_dir=root_dir,
        staging_dir=staging_dir,
        output_dir=output_dir,
        flagged_dir=resolved_flagged,
        taxonomy_path=taxonomy_path,
        skip_validate=skip_validate,
    )
    return res["output_dir"] if res is not None else None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export validated Stage 2 enriched chapters to self-contained Stage 3 output & flagged."
    )
    parser.add_argument("--chapters", nargs="+", type=int, help="Chapter numbers to export.")
    parser.add_argument(
        "--all", action="store_true", help="Export all chapters present in staging/enriched."
    )
    parser.add_argument(
        "--root-dir",
        type=Path,
        default=None,
        help="Project root directory (default: cwd if staging/ or taxonomy.yaml exists).",
    )
    parser.add_argument("--staging-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--flagged-dir", type=Path, default=None)
    parser.add_argument("--taxonomy", type=Path, default=None)
    parser.add_argument("--skip-validate", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root_dir: Path = args.root_dir or detect_default_root_dir()
    staging_dir: Path = args.staging_dir or (root_dir / "staging")
    output_dir: Path = args.output_dir or (root_dir / "output")
    flagged_dir: Path = args.flagged_dir or (root_dir / "flagged")
    taxonomy_path: Path = args.taxonomy or (root_dir / "taxonomy.yaml")

    if args.all:
        enr_dir = staging_dir / "enriched"
        chapters = (
            sorted(int(p.name[2:4]) for p in enr_dir.glob("ch[0-9][0-9]_enriched.jsonl"))
            if enr_dir.is_dir()
            else []
        )
    elif args.chapters:
        chapters = sorted(set(args.chapters))
    else:
        print("[ERROR] Specify --chapters or --all", file=sys.stderr)
        return 1

    if not chapters:
        print("[ERROR] No enriched chapters found to export.", file=sys.stderr)
        return 1

    for ch in chapters:
        res = export_chapter_split(
            ch,
            root_dir=root_dir,
            staging_dir=staging_dir,
            output_dir=output_dir,
            flagged_dir=flagged_dir,
            taxonomy_path=taxonomy_path,
            skip_validate=args.skip_validate,
        )
        if res is None:
            print(f"[SKIP] ch{ch:02d}: 0 questions")
        else:
            flag_info = (
                f", flagged={res['flagged_count']} -> {res['flagged_dir']}"
                if res["flagged_count"] > 0
                else ", flagged=0"
            )
            print(
                f"[EXPORTED] ch{ch:02d} -> {res['output_dir']} "
                f"(clean={res['clean_count']}{flag_info})"
            )
            if res["clean_count"] == 0 and res["flagged_count"] > 0:
                print(
                    f"[WARN] ch{ch:02d}: all {res['flagged_count']} question(s) were flagged; "
                    f"{res['output_dir'] / 'problems.jsonl'} has 0 lines."
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
