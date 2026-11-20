#!/usr/bin/env python3
"""
Stage 2 Merger, Strict Schema/Taxonomy Validator & Audit Report Generator (`validate_enriched.py`).

Supports:
  - `--merge-shards`: merges `staging/enriched/shards/chXX_p*.jsonl` in `id` order
    into `staging/enriched/chXX_enriched.jsonl`, verifying 100% 1-to-1 ID alignment
    against `staging/chXX_raw.jsonl`.
  - Strict validation against `taxonomy.yaml`, audit rules, question purity, and
    on-disk `source_images`.
  - Automatic generation of `reports/chXX_ocr_fixes.md` and `reports/chXX_audit_report.md`
    upon validation pass.

Usage:
  python scripts/validate_enriched.py --chapter 1
  python scripts/validate_enriched.py --chapters 1 28 --merge-shards
  python scripts/validate_enriched.py --all --root-dir /path/to/book
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def detect_default_root_dir() -> Path:
    """Prefer cwd if `staging/` or `taxonomy.yaml` exists there, else script grandparent."""
    cwd = Path.cwd()
    if (cwd / "staging").is_dir() or (cwd / "taxonomy.yaml").is_file():
        return cwd
    return Path(__file__).resolve().parent.parent


ROOT_DIR = detect_default_root_dir()
DEFAULT_STAGING_DIR = ROOT_DIR / "staging"
DEFAULT_REPORTS_DIR = ROOT_DIR / "reports"
DEFAULT_TAXONOMY_PATH = ROOT_DIR / "taxonomy.yaml"

REQUIRED_TOP_KEYS = {
    "id",
    "chapter",
    "chapter_title",
    "question",
    "source_images",
    "tags",
    "audit",
}
REQUIRED_TAG_KEYS = {
    "domain",
    "topic",
    "method",
    "difficulty",
    "visual",
    "format",
    "extra_tags",
}
ALLOWED_AUDIT_STATUSES = {"pass", "auto_fixed", "flagged"}
ALLOWED_VERIFIED_BY = {
    "vision_diagram_check",
    "solution_crosscheck",
    "python_calc",
    "symbol_set_check",
    "crop_check",
}
ID_RE = re.compile(r"^ch(\d{2})_(\d{3})$")

# Question purity checks
DETAILS_RE = re.compile(r"</?(?:details|summary)\b", re.IGNORECASE)
JIEXI_HEADING_RE = re.compile(r"#{1,6}\s*解析")
ANSWER_LEAK_RE = re.compile(r"答案\s*[:：]")
EXAMPLE_PREFIX_RE = re.compile(r"^\s*例\s*\d+")
IMG_MD_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")


@dataclass(frozen=True)
class TaxonomySpec:
    domains: set[str]
    topics_by_domain: dict[str, set[str]]
    all_topics: set[str]
    all_methods: set[str]
    difficulty_levels: set[int]
    visuals: set[str]
    formats: set[str]
    controlled_vocab: set[str]


def _collect_item_names(node: Any, out: set[str]) -> None:
    """Recursively extract item names from list-of-dicts, list-of-str, or nested dict groupings."""
    if isinstance(node, list):
        for item in node:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                out.add(item["name"])
            elif isinstance(item, str):
                out.add(item)
            else:
                _collect_item_names(item, out)
    elif isinstance(node, dict):
        if isinstance(node.get("name"), str):
            out.add(node["name"])
        else:
            for val in node.values():
                _collect_item_names(val, out)


def load_taxonomy(taxonomy_path: Path | None = None) -> TaxonomySpec:
    path = taxonomy_path or (detect_default_root_dir() / "taxonomy.yaml")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    domains = {d["name"] if isinstance(d, dict) else str(d) for d in data["domains"]}
    topics_by_domain: dict[str, set[str]] = {}
    all_topics: set[str] = set()
    for dom, items in data["topics"].items():
        names: set[str] = set()
        _collect_item_names(items, names)
        topics_by_domain[dom] = names
        all_topics.update(names)

    all_methods: set[str] = set()
    _collect_item_names(data["methods"], all_methods)

    difficulty_levels = {int(d["level"]) for d in data["difficulty"]}
    difficulty_names = {d["name"] for d in data["difficulty"]}
    visuals = {v["name"] if isinstance(v, dict) else str(v) for v in data["visual"]}
    formats = {fmt["name"] if isinstance(fmt, dict) else str(fmt) for fmt in data["format"]}

    controlled_vocab = (
        domains | all_topics | all_methods | visuals | formats | difficulty_names
    )
    return TaxonomySpec(
        domains=domains,
        topics_by_domain=topics_by_domain,
        all_topics=all_topics,
        all_methods=all_methods,
        difficulty_levels=difficulty_levels,
        visuals=visuals,
        formats=formats,
        controlled_vocab=controlled_vocab,
    )


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rec = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
            if not isinstance(rec, dict):
                raise ValueError(f"{path}:{lineno}: expected JSON object")
            records.append(rec)
    return records


def merge_chapter_shards(
    chapter: int,
    staging_dir: Path,
) -> Path:
    """
    Merge `staging/enriched/shards/chXX_p*.jsonl` in `id` order into
    `staging/enriched/chXX_enriched.jsonl` if shard files exist.
    Rejects duplicate IDs across shards and validates 1-to-1 alignment with raw IDs.
    """
    enriched_dir = staging_dir / "enriched"
    shards_dir = enriched_dir / "shards"
    target_path = enriched_dir / f"ch{chapter:02d}_enriched.jsonl"

    shard_files = sorted(shards_dir.glob(f"ch{chapter:02d}_p*.jsonl"))
    if not shard_files:
        return target_path

    merged: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    dup_ids: list[str] = []

    for shard_path in shard_files:
        for rec in load_jsonl(shard_path):
            rid = rec.get("id")
            if not isinstance(rid, str) or not rid:
                raise ValueError(f"Record missing string 'id' in shard {shard_path}")
            if rid in seen_ids:
                dup_ids.append(rid)
            seen_ids.add(rid)
            merged.append(rec)

    if dup_ids:
        raise ValueError(
            f"ch{chapter:02d}: duplicate IDs across shards: {sorted(set(dup_ids))}"
        )

    raw_path = staging_dir / f"ch{chapter:02d}_raw.jsonl"
    if raw_path.is_file():
        raw_ids = [r["id"] for r in load_jsonl(raw_path)]
        _check_id_alignment(chapter, raw_ids, [r["id"] for r in merged])

    merged.sort(key=lambda r: r["id"])
    enriched_dir.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as f:
        for rec in merged:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return target_path


def _check_id_alignment(
    chapter: int,
    raw_ids: list[str],
    enriched_ids: list[str],
) -> list[str]:
    errors: list[str] = []
    dup_enriched = [rid for rid, cnt in Counter(enriched_ids).items() if cnt > 1]
    if dup_enriched:
        errors.append(
            f"ch{chapter:02d}: duplicate IDs in enriched records: {sorted(dup_enriched)}"
        )

    raw_set = set(raw_ids)
    enr_set = set(enriched_ids)
    missing = sorted(raw_set - enr_set)
    extra = sorted(enr_set - raw_set)
    if missing:
        errors.append(
            f"ch{chapter:02d}: missing {len(missing)} IDs vs raw: {missing[:10]}"
        )
    if extra:
        errors.append(
            f"ch{chapter:02d}: {len(extra)} unexpected extra IDs vs raw: {extra[:10]}"
        )
    if errors:
        raise ValueError("; ".join(errors))
    return errors


def validate_record(
    rec: dict[str, Any],
    chapter: int,
    spec: TaxonomySpec,
    root_dir: Path,
) -> list[str]:
    errs: list[str] = []
    rid = rec.get("id", "<unknown>")

    missing_keys = REQUIRED_TOP_KEYS - set(rec.keys())
    if missing_keys:
        errs.append(f"{rid}: missing top-level keys {sorted(missing_keys)}")
        return errs

    # Basic top-level field checks
    if not isinstance(rec["id"], str) or not ID_RE.match(rec["id"]):
        errs.append(f"{rid}: invalid id format")
    else:
        m = ID_RE.match(rec["id"])
        if m and int(m.group(1)) != chapter:
            errs.append(f"{rid}: id chapter prefix does not match ch{chapter:02d}")

    if type(rec["chapter"]) is not int or rec["chapter"] != chapter:
        errs.append(f"{rid}: chapter must be int {chapter}, got {rec['chapter']!r}")

    if not isinstance(rec["chapter_title"], str) or not rec["chapter_title"].strip():
        errs.append(f"{rid}: chapter_title must be non-empty string")

    q = rec["question"]
    if not isinstance(q, str) or not q.strip():
        errs.append(f"{rid}: question must be non-empty string")
    else:
        if DETAILS_RE.search(q):
            errs.append(f"{rid}: question contains <details>/<summary> residue")
        if JIEXI_HEADING_RE.search(q):
            errs.append(f"{rid}: question contains '## 解析' residue")
        if ANSWER_LEAK_RE.search(q):
            errs.append(f"{rid}: question contains '答案:' residue")
        if EXAMPLE_PREFIX_RE.match(q):
            errs.append(f"{rid}: question starts with '例 N' prefix residue")
        if IMG_MD_RE.search(q):
            errs.append(f"{rid}: question contains markdown image link residue")

    src_imgs = rec["source_images"]
    if not isinstance(src_imgs, list) or not all(isinstance(p, str) for p in src_imgs):
        errs.append(f"{rid}: source_images must be list of strings")
        src_imgs_valid_list = False
    else:
        src_imgs_valid_list = True
        for rel_path in src_imgs:
            img_path = root_dir / rel_path
            if not img_path.is_file():
                errs.append(f"{rid}: source_image missing on disk: {rel_path}")
            elif img_path.stat().st_size <= 0:
                errs.append(f"{rid}: source_image is empty (0 bytes): {rel_path}")

    # Tags validation
    tags = rec["tags"]
    if not isinstance(tags, dict):
        errs.append(f"{rid}: tags must be an object")
    else:
        missing_tag_keys = REQUIRED_TAG_KEYS - set(tags.keys())
        extra_tag_keys = set(tags.keys()) - REQUIRED_TAG_KEYS
        if missing_tag_keys:
            errs.append(f"{rid}: tags missing keys {sorted(missing_tag_keys)}")
        if extra_tag_keys:
            errs.append(f"{rid}: tags has unexpected keys {sorted(extra_tag_keys)}")

        domain = tags.get("domain")
        if not isinstance(domain, str) or domain not in spec.domains:
            errs.append(f"{rid}: invalid domain {domain!r}")
            domain_valid = False
        else:
            domain_valid = True

        topic = tags.get("topic")
        if (
            not isinstance(topic, list)
            or not (1 <= len(topic) <= 2)
            or not all(isinstance(t, str) for t in topic)
        ):
            errs.append(f"{rid}: topic must be list of 1..2 strings, got {topic!r}")
        else:
            if len(set(topic)) != len(topic):
                errs.append(f"{rid}: duplicate entries in topic {topic!r}")
            for t in topic:
                if t not in spec.all_topics:
                    errs.append(f"{rid}: uncontrolled topic {t!r}")
            if domain_valid and topic[0] not in spec.topics_by_domain.get(domain, set()):
                errs.append(
                    f"{rid}: primary topic {topic[0]!r} does not belong to domain {domain!r}"
                )

        method = tags.get("method")
        if (
            not isinstance(method, list)
            or not (1 <= len(method) <= 3)
            or not all(isinstance(m, str) for m in method)
        ):
            errs.append(f"{rid}: method must be list of 1..3 strings, got {method!r}")
        else:
            if len(set(method)) != len(method):
                errs.append(f"{rid}: duplicate entries in method {method!r}")
            for m in method:
                if m not in spec.all_methods:
                    errs.append(f"{rid}: uncontrolled method {m!r}")

        diff = tags.get("difficulty")
        if type(diff) is not int or diff not in spec.difficulty_levels:
            errs.append(
                f"{rid}: difficulty must be strict int in {sorted(spec.difficulty_levels)}, got {diff!r} ({type(diff).__name__})"
            )

        visual = tags.get("visual")
        if not isinstance(visual, str) or visual not in spec.visuals:
            errs.append(f"{rid}: invalid visual {visual!r}")
        elif src_imgs_valid_list:
            if len(src_imgs) > 0 and visual == "纯文字":
                errs.append(
                    f"{rid}: source_images is non-empty ({len(src_imgs)}), visual cannot be '纯文字'"
                )
            if len(src_imgs) == 0 and visual != "纯文字":
                errs.append(
                    f"{rid}: source_images is empty, visual must be '纯文字' (got {visual!r})"
                )

        fmt = tags.get("format")
        if not isinstance(fmt, str) or fmt not in spec.formats:
            errs.append(f"{rid}: invalid format {fmt!r}")

        extra_tags = tags.get("extra_tags")
        if (
            not isinstance(extra_tags, list)
            or len(extra_tags) > 2
            or not all(isinstance(et, str) for et in extra_tags)
        ):
            errs.append(
                f"{rid}: extra_tags must be list of 0..2 strings, got {extra_tags!r}"
            )
        else:
            if len(set(extra_tags)) != len(extra_tags):
                errs.append(f"{rid}: duplicate entries in extra_tags {extra_tags!r}")
            for et in extra_tags:
                if "#" in et:
                    errs.append(f"{rid}: extra_tag {et!r} must not contain '#'")
                if not (2 <= len(et) <= 8):
                    errs.append(
                        f"{rid}: extra_tag {et!r} length must be 2..8 chars (got {len(et)})"
                    )
                if et in spec.controlled_vocab:
                    errs.append(
                        f"{rid}: extra_tag {et!r} collides with controlled vocabulary"
                    )

    # Audit validation
    audit = rec["audit"]
    if not isinstance(audit, dict):
        errs.append(f"{rid}: audit must be an object")
    else:
        status = audit.get("status")
        if status not in ALLOWED_AUDIT_STATUSES:
            errs.append(
                f"{rid}: audit.status must be one of {sorted(ALLOWED_AUDIT_STATUSES)}, got {status!r}"
            )

        if type(audit.get("solvable")) is not bool:
            errs.append(
                f"{rid}: audit.solvable must be bool, got {audit.get('solvable')!r}"
            )

        verified_by = audit.get("verified_by")
        if (
            not isinstance(verified_by, list)
            or len(verified_by) == 0
            or not all(isinstance(v, str) for v in verified_by)
        ):
            errs.append(f"{rid}: audit.verified_by must be a non-empty list of strings")
        else:
            invalid_vb = set(verified_by) - ALLOWED_VERIFIED_BY
            if invalid_vb:
                errs.append(
                    f"{rid}: audit.verified_by has invalid entries {sorted(invalid_vb)}"
                )

        if status == "auto_fixed":
            if audit.get("ocr_fixed") is not True:
                errs.append(f"{rid}: auto_fixed requires audit.ocr_fixed === True")
            orig_q = audit.get("original_question")
            if not isinstance(orig_q, str) or not orig_q.strip():
                errs.append(f"{rid}: auto_fixed requires non-empty audit.original_question")
            elif isinstance(q, str) and orig_q == q:
                errs.append(
                    f"{rid}: auto_fixed requires audit.original_question != question"
                )
            fix_reason = audit.get("fix_reason")
            if not isinstance(fix_reason, str) or not fix_reason.strip():
                errs.append(f"{rid}: auto_fixed requires non-empty audit.fix_reason")

        if status == "flagged":
            flag_reason = audit.get("flag_reason")
            if not isinstance(flag_reason, str) or not flag_reason.strip():
                errs.append(f"{rid}: flagged requires non-empty audit.flag_reason")

    return errs


def validate_chapter(
    chapter: int,
    staging_dir: Path,
    spec: TaxonomySpec,
    root_dir: Path,
    merge_shards: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    if merge_shards:
        enriched_path = merge_chapter_shards(chapter, staging_dir)
    else:
        enriched_path = staging_dir / "enriched" / f"ch{chapter:02d}_enriched.jsonl"

    if not enriched_path.is_file():
        return [], [f"ch{chapter:02d}: missing enriched file {enriched_path}"]

    records = load_jsonl(enriched_path)
    errors: list[str] = []

    raw_path = staging_dir / f"ch{chapter:02d}_raw.jsonl"
    if raw_path.is_file():
        raw_ids = [r["id"] for r in load_jsonl(raw_path)]
        enr_ids = [r.get("id", "") for r in records]
        try:
            _check_id_alignment(chapter, raw_ids, enr_ids)
        except ValueError as exc:
            errors.append(str(exc))
    else:
        enr_ids = [r.get("id", "") for r in records]
        dups = [rid for rid, cnt in Counter(enr_ids).items() if cnt > 1]
        if dups:
            errors.append(f"ch{chapter:02d}: duplicate IDs {sorted(dups)}")

    for rec in records:
        errors.extend(validate_record(rec, chapter, spec, root_dir))

    return records, errors


def generate_reports(
    chapter: int,
    records: list[dict[str, Any]],
    reports_dir: Path,
) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    chapter_title = records[0].get("chapter_title", f"第{chapter}章") if records else f"第{chapter}章"

    # 1. chXX_ocr_fixes.md
    fixes = [r for r in records if r["audit"]["status"] == "auto_fixed"]
    ocr_fixes_path = reports_dir / f"ch{chapter:02d}_ocr_fixes.md"
    lines_fix: list[str] = [
        f"# 第 {chapter:02d} 章 OCR 自动修正记录（{chapter_title}）",
        "",
        f"- **本章总题数**: {len(records)}",
        f"- **自动修正题数 (`auto_fixed`)**: {len(fixes)}",
        "",
    ]
    if not fixes:
        lines_fix.append("本章所有题目均未触发 OCR 自动修正（0 条 `auto_fixed` 记录）。")
    else:
        for rec in fixes:
            audit = rec["audit"]
            verified_str = ", ".join(audit["verified_by"])
            lines_fix.extend([
                f"## {rec['id']}",
                "",
                f"- **修改依据 (`fix_reason`)**: {audit['fix_reason']}",
                f"- **核验方式 (`verified_by`)**: `{verified_str}`",
                "",
                "**修改前原文 (`original_question`)**:",
                "",
                f"> {audit['original_question']}",
                "",
                "**修改后文本 (`question`)**:",
                "",
                f"> {rec['question']}",
                "",
            ])
    ocr_fixes_path.write_text("\n".join(lines_fix) + "\n", encoding="utf-8")

    # 2. chXX_audit_report.md
    status_counts = Counter(r["audit"]["status"] for r in records)
    domain_counts = Counter(r["tags"]["domain"] for r in records)
    topic_counts = Counter(t for r in records for t in r["tags"]["topic"])
    method_counts = Counter(m for r in records for m in r["tags"]["method"])
    diff_counts = Counter(r["tags"]["difficulty"] for r in records)
    visual_counts = Counter(r["tags"]["visual"] for r in records)
    format_counts = Counter(r["tags"]["format"] for r in records)
    flagged = [r for r in records if r["audit"]["status"] == "flagged"]

    audit_report_path = reports_dir / f"ch{chapter:02d}_audit_report.md"
    lines_rep: list[str] = [
        f"# 第 {chapter:02d} 章 阶段 2 校验与审核报告（{chapter_title}）",
        "",
        "## 1. 审核状态分布",
        "",
        f"- **总题数**: {len(records)}",
        f"- **`pass`**: {status_counts.get('pass', 0)}",
        f"- **`auto_fixed`**: {status_counts.get('auto_fixed', 0)}",
        f"- **`flagged`**: {status_counts.get('flagged', 0)}",
        "",
        "## 2. 标签分布统计",
        "",
        "### 主板块 (`domain`)",
        *(f"- {k}: {v}" for k, v in domain_counts.most_common()),
        "",
        "### 专题 (`topic`)",
        *(f"- {k}: {v}" for k, v in topic_counts.most_common()),
        "",
        "### 解题方法 (`method`)",
        *(f"- {k}: {v}" for k, v in method_counts.most_common()),
        "",
        "### 难度 (`difficulty`)",
        *(f"- 难度 {k}: {v}" for k, v in sorted(diff_counts.items())),
        "",
        "### 视觉类型 (`visual`)",
        *(f"- {k}: {v}" for k, v in visual_counts.most_common()),
        "",
        "### 题型 (`format`)",
        *(f"- {k}: {v}" for k, v in format_counts.most_common()),
        "",
        "## 3. 人工复核清单 (`flagged` 题目详情)",
        "",
    ]
    if not flagged:
        lines_rep.append("本章无 `flagged` 题目。")
    else:
        for rec in flagged:
            q_summary = rec["question"].replace("\n", " ")
            if len(q_summary) > 120:
                q_summary = q_summary[:120] + "..."
            lines_rep.extend([
                f"### {rec['id']}",
                "",
                f"- **标记原因 (`flag_reason`)**: {rec['audit']['flag_reason']}",
                f"- **可解性 (`solvable`)**: `{rec['audit']['solvable']}`",
                f"- **核验方式 (`verified_by`)**: `{', '.join(rec['audit']['verified_by'])}`",
                f"- **原题摘要**: {q_summary}",
                "",
            ])

    lines_rep.extend([
        "## 4. 自动修正索引 (`auto_fixed`)",
        "",
    ])
    if not fixes:
        lines_rep.append("本章无 `auto_fixed` 题目。")
    else:
        for rec in fixes:
            lines_rep.append(f"- `{rec['id']}`: {rec['audit']['fix_reason']}")

    audit_report_path.write_text("\n".join(lines_rep) + "\n", encoding="utf-8")
    return ocr_fixes_path, audit_report_path


def discover_enriched_chapters(staging_dir: Path, include_shards: bool = False) -> list[int]:
    """Scan `staging/enriched/` (and optionally `shards/`) for chapter numbers 1..99."""
    found: set[int] = set()
    enr_dir = staging_dir / "enriched"
    if enr_dir.is_dir():
        for p in enr_dir.glob("ch[0-9][0-9]_enriched.jsonl"):
            found.add(int(p.name[2:4]))
    if include_shards and (enr_dir / "shards").is_dir():
        for p in (enr_dir / "shards").glob("ch[0-9][0-9]_p*.jsonl"):
            found.add(int(p.name[2:4]))
    return sorted(found)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge shards, validate Stage 2 enriched JSONL, and generate audit reports."
    )
    parser.add_argument("--chapter", type=int, help="Single chapter number to validate.")
    parser.add_argument(
        "--chapters", nargs="+", type=int, help="List of chapter numbers to validate."
    )
    parser.add_argument(
        "--all", action="store_true", help="Validate all chapters found in staging/enriched."
    )
    parser.add_argument(
        "--merge-shards",
        action="store_true",
        help="Merge staging/enriched/shards/chXX_p*.jsonl before validation.",
    )
    parser.add_argument(
        "--root-dir",
        type=Path,
        default=None,
        help="Project root directory (default: cwd if staging/ or taxonomy.yaml exists).",
    )
    parser.add_argument("--staging-dir", type=Path, default=None)
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--taxonomy", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root_dir: Path = args.root_dir or detect_default_root_dir()
    staging_dir: Path = args.staging_dir or (root_dir / "staging")
    reports_dir: Path = args.reports_dir or (root_dir / "reports")
    taxonomy_path: Path = args.taxonomy or (root_dir / "taxonomy.yaml")

    chapters: list[int] = []
    if args.chapter is not None:
        chapters.append(args.chapter)
    if args.chapters:
        chapters.extend(args.chapters)
    if args.all or not chapters:
        chapters = discover_enriched_chapters(staging_dir, include_shards=args.merge_shards)

    chapters = sorted(set(chapters))
    if not chapters:
        print(f"[ERROR] No enriched chapters found in {staging_dir / 'enriched'}", file=sys.stderr)
        return 1

    spec = load_taxonomy(taxonomy_path)

    all_errors: list[str] = []
    for ch in chapters:
        if not 1 <= ch <= 99:
            all_errors.append(f"Invalid chapter number: {ch} (expected 1..99)")
            continue
        try:
            records, errors = validate_chapter(
                ch,
                staging_dir=staging_dir,
                spec=spec,
                root_dir=root_dir,
                merge_shards=args.merge_shards,
            )
        except Exception as exc:
            all_errors.append(f"ch{ch:02d}: {exc}")
            continue

        if errors:
            all_errors.extend(errors)
            continue

        fixes_md, audit_md = generate_reports(ch, records, reports_dir)
        print(
            f"[PASS] ch{ch:02d}: {len(records)} records validated -> "
            f"{fixes_md.name}, {audit_md.name}"
        )

    if all_errors:
        print(f"[FAILED] {len(all_errors)} validation error(s):", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
