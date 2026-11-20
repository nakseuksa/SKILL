#!/usr/bin/env python3
"""
Stage 2 Pre-check: Geometry & Text Symbol Set Comparison (`precheck_geometry_symbols.py`).

Extracts uppercase geometric points/edge-triangle combinations, circled numbers,
and key numeric literals from both `question` and `book_solution_hint` in
`staging/chXX_raw.jsonl`, computes set differences and near-miss / isolated
anomalies, and writes `staging/symbol_audit/chXX_symbol_audit.json`.

Usage:
  python scripts/precheck_geometry_symbols.py --chapters 1 28
  python scripts/precheck_geometry_symbols.py --root-dir /path/to/book
  python scripts/precheck_geometry_symbols.py  # auto-discovers staging/ch*_raw.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def detect_default_root_dir() -> Path:
    """Prefer current working directory if it contains `staging/`, else script grandparent."""
    cwd = Path.cwd()
    if (cwd / "staging").is_dir():
        return cwd
    return Path(__file__).resolve().parent.parent


ROOT_DIR = detect_default_root_dir()
DEFAULT_STAGING_DIR = ROOT_DIR / "staging"
DEFAULT_OUTPUT_DIR = DEFAULT_STAGING_DIR / "symbol_audit"

RAW_FILE_RE = re.compile(r"^ch(\d+)_raw\.jsonl$")

# Non-geometric uppercase acronyms that should not be treated as point/segment labels
NON_GEOM_ACRONYMS = {
    "MO", "IMC", "AMC", "SMO", "GCD", "LCM", "CM", "MM", "KM", "DM",
}

LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+")
# Collapse spaces between single uppercase letters inside math spans, e.g. "A B C D" -> "ABCD"
MATH_SPAN_RE = re.compile(r"\$\$?(.*?)\$\$?", re.DOTALL)
SPACED_CAPS_RE = re.compile(r"(?<![A-Za-z])([A-Z](?:\s+[A-Z]){1,5})(?![A-Za-z])")
AREA_S_SUB_RE = re.compile(r"(?<![A-Za-z])S\s*_")
RT_PREFIX_RE = re.compile(r"(?<![A-Za-z])Rt(?=\s*[△\\A-Z])")
CHOICE_LABEL_RE = re.compile(r"(?m)^\s*[A-D]\s*\.\s*")
COMBO_RE = re.compile(r"(?<![A-Za-z])[A-Z]{2,6}(?![A-Za-z])")
SINGLE_CAP_RE = re.compile(r"(?<![A-Za-z])[A-Z](?![A-Za-z])")
CIRCLED_RE = re.compile(r"[\u2460-\u2473]")  # ① .. ⑳
NUMBER_RE = re.compile(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])")


def _collapse_spaced_caps_in_math(text: str) -> str:
    def _repl_math(m: re.Match[str]) -> str:
        inner = m.group(1)
        collapsed = SPACED_CAPS_RE.sub(lambda sm: sm.group(1).replace(" ", ""), inner)
        return collapsed

    return MATH_SPAN_RE.sub(_repl_math, text)


def _preprocess_text(text: str) -> str:
    if not text:
        return ""
    s = _collapse_spaced_caps_in_math(text)
    s = AREA_S_SUB_RE.sub(" ", s)
    s = RT_PREFIX_RE.sub(" ", s)
    s = CHOICE_LABEL_RE.sub(" ", s)
    s = LATEX_CMD_RE.sub(" ", s)
    # Remove primes/carets/braces so A' or A^{2} cleanly isolates A
    s = s.replace("'", " ").replace("′", " ")
    return s


def extract_symbols(text: str) -> dict[str, list[str]]:
    """Extract sorted unique geometric points, combos, circled numbers, and numeric literals."""
    cleaned = _preprocess_text(text)

    combos: set[str] = set()
    for token in COMBO_RE.findall(cleaned):
        if token not in NON_GEOM_ACRONYMS:
            combos.add(token)

    points: set[str] = set(SINGLE_CAP_RE.findall(cleaned))
    for combo in combos:
        points.update(combo)

    circled = set(CIRCLED_RE.findall(text))
    numbers = set(NUMBER_RE.findall(cleaned))

    return {
        "points": sorted(points),
        "combos": sorted(combos),
        "circled_numbers": sorted(circled),
        "numbers": sorted(numbers),
    }


def _hamming_distance(a: str, b: str) -> int:
    return sum(ch1 != ch2 for ch1, ch2 in zip(a, b))


def find_near_miss_combos(
    q_only_combos: list[str],
    s_only_combos: list[str],
) -> list[dict[str, str]]:
    """Find same-length (>=2) combo pairs differing by exactly 1 character."""
    pairs: list[dict[str, str]] = []
    for qc in q_only_combos:
        for sc in s_only_combos:
            if len(qc) == len(sc) >= 2 and _hamming_distance(qc, sc) == 1:
                pairs.append({"question_combo": qc, "solution_combo": sc})
    return pairs


def audit_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Compare question vs book_solution_hint symbols for a single raw record."""
    question = rec.get("question", "") or ""
    hint = rec.get("book_solution_hint", "") or ""
    has_hint = bool(hint.strip())

    q_sym = extract_symbols(question)
    s_sym = extract_symbols(hint)

    q_pts, s_pts = set(q_sym["points"]), set(s_sym["points"])
    q_cmb, s_cmb = set(q_sym["combos"]), set(s_sym["combos"])
    q_cir, s_cir = set(q_sym["circled_numbers"]), set(s_sym["circled_numbers"])
    q_num, s_num = set(q_sym["numbers"]), set(s_sym["numbers"])

    q_only_pts = sorted(q_pts - s_pts) if has_hint else []
    s_only_pts = sorted(s_pts - q_pts) if has_hint else []
    q_only_cmb = sorted(q_cmb - s_cmb) if has_hint else []
    s_only_cmb = sorted(s_cmb - q_cmb) if has_hint else []
    q_only_cir = sorted(q_cir - s_cir) if has_hint else []
    s_only_cir = sorted(s_cir - q_cir) if has_hint else []
    q_only_num = sorted(q_num - s_num) if has_hint else []
    s_only_num = sorted(s_num - q_num) if has_hint else []

    near_miss = find_near_miss_combos(q_only_cmb, s_only_cmb) if has_hint else []

    suspect_reasons: list[str] = []
    suspicious_isolated: list[dict[str, Any]] = []

    if has_hint and (q_only_cir or s_only_cir) and (q_cir or s_cir):
        suspect_reasons.append("CIRCLED_NUMBER_MISMATCH")
        suspicious_isolated.append({
            "type": "circled_number",
            "question_only": q_only_cir,
            "solution_only": s_only_cir,
        })

    if near_miss:
        suspect_reasons.append("NEAR_MISS_COMBO")
        for pair in near_miss:
            suspicious_isolated.append({
                "type": "near_miss_combo",
                **pair,
            })

    if has_hint and q_only_pts and s_pts:
        suspect_reasons.append("ISOLATED_QUESTION_POINT")
        suspicious_isolated.append({
            "type": "question_only_points",
            "symbols": q_only_pts,
            "solution_only_points": s_only_pts,
        })

    if has_hint and q_only_cmb and s_cmb:
        suspect_reasons.append("QUESTION_ONLY_COMBO")
        suspicious_isolated.append({
            "type": "question_only_combos",
            "symbols": q_only_cmb,
        })

    return {
        "id": rec["id"],
        "has_solution_hint": has_hint,
        "question_symbols": q_sym,
        "solution_symbols": s_sym,
        "diff": {
            "question_only_points": q_only_pts,
            "solution_only_points": s_only_pts,
            "question_only_combos": q_only_cmb,
            "solution_only_combos": s_only_cmb,
            "question_only_circled": q_only_cir,
            "solution_only_circled": s_only_cir,
            "question_only_numbers": q_only_num,
            "solution_only_numbers": s_only_num,
        },
        "near_miss_combos": near_miss,
        "suspicious_isolated_symbols": suspicious_isolated,
        "suspect_reasons": suspect_reasons,
        "is_suspect": bool(suspect_reasons),
    }


def discover_chapters(staging_dir: Path) -> list[int]:
    """Scan `staging/ch*_raw.jsonl` to discover all available chapter numbers."""
    if not staging_dir.is_dir():
        return []
    chapters: list[int] = []
    for p in staging_dir.glob("ch*_raw.jsonl"):
        m = RAW_FILE_RE.match(p.name)
        if m:
            ch = int(m.group(1))
            if ch >= 1:
                chapters.append(ch)
    return sorted(set(chapters))


def process_chapter(
    chapter: int,
    staging_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    raw_path = staging_dir / f"ch{chapter:02d}_raw.jsonl"
    if not raw_path.is_file():
        raise FileNotFoundError(f"Missing raw chapter file: {raw_path}")

    raw_records: list[dict[str, Any]] = []
    with raw_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                raw_records.append(json.loads(line))

    audited_records = [audit_record(r) for r in raw_records]
    suspect_ids = [r["id"] for r in audited_records if r["is_suspect"]]
    chapter_title = raw_records[0].get("chapter_title", "") if raw_records else ""

    payload = {
        "chapter": chapter,
        "chapter_title": chapter_title,
        "total_questions": len(audited_records),
        "suspect_count": len(suspect_ids),
        "suspect_ids": suspect_ids,
        "records": audited_records,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"ch{chapter:02d}_symbol_audit.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Precheck geometric/text symbol consistency between question and solution hints."
    )
    parser.add_argument(
        "--chapters",
        nargs="+",
        type=int,
        default=None,
        help="Chapter numbers to audit (default: auto-discover from staging/ch*_raw.jsonl).",
    )
    parser.add_argument(
        "--root-dir",
        type=Path,
        default=None,
        help="Project root directory (default: cwd if staging/ exists, else script parent).",
    )
    parser.add_argument(
        "--staging-dir",
        type=Path,
        default=None,
        help="Path to staging directory (default: <root-dir>/staging).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Path to output symbol_audit directory (default: <staging-dir>/symbol_audit).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root_dir: Path = args.root_dir or detect_default_root_dir()
    staging_dir: Path = args.staging_dir or (root_dir / "staging")
    output_dir: Path = args.output_dir or (staging_dir / "symbol_audit")

    if args.chapters is not None:
        chapters = sorted(set(args.chapters))
    else:
        chapters = discover_chapters(staging_dir)

    if not chapters:
        print(f"[WARN] No ch*_raw.jsonl chapters found in {staging_dir}", file=sys.stderr)
        return 1

    for ch in chapters:
        if ch < 1:
            print(f"[ERROR] Invalid chapter number: {ch} (expected >= 1)", file=sys.stderr)
            return 1
        summary = process_chapter(ch, staging_dir, output_dir)
        print(
            f"ch{ch:02d}: audited {summary['total_questions']} questions, "
            f"suspect={summary['suspect_count']} -> {output_dir / f'ch{ch:02d}_symbol_audit.json'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
