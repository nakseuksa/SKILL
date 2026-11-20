#!/usr/bin/env python3
"""
Closed-loop Unit & Integration Test Suite for `ocr-math-bank-pipeline` Skill Assets.

All tests execute inside `tempfile.TemporaryDirectory()` and never modify the skill
directory or any user project workspace.

Run with:
  python scripts/test_skill_pipeline.py -v
"""

from __future__ import annotations

import ast
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

import yaml

SKILL_ROOT = Path(__file__).resolve().parent.parent
SKILL_SCRIPTS = SKILL_ROOT / "scripts"
SKILL_RESOURCES = SKILL_ROOT / "resources"

if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

import export_output  # noqa: E402
import init_project  # noqa: E402
import precheck_geometry_symbols  # noqa: E402
import validate_enriched  # noqa: E402


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def make_enriched_record(
    *,
    qid: str,
    chapter: int,
    chapter_title: str = "第五十五章 测试高章号几何综合",
    question: str = "如图，在△ABC中，求面积。",
    source_images: list[str] | None = None,
    status: str = "pass",
    solvable: bool = True,
    domain: str = "几何",
    topic: list[str] | None = None,
    method: list[str] | None = None,
    difficulty: int = 2,
    visual: str = "几何图形",
    fmt: str = "解答题",
    extra_tags: list[str] | None = None,
) -> dict[str, Any]:
    imgs = [] if source_images is None else source_images
    if not imgs and visual == "几何图形":
        visual = "纯文字"
    audit: dict[str, Any] = {
        "status": status,
        "solvable": solvable,
        "verified_by": ["solution_crosscheck", "python_calc"],
    }
    if status == "auto_fixed":
        audit["ocr_fixed"] = True
        audit["original_question"] = question + " (OCR误识)"
        audit["fix_reason"] = "修正OCR错字"
    elif status == "flagged":
        audit["flag_reason"] = "配图缺失需人工复核"

    return {
        "id": qid,
        "chapter": chapter,
        "chapter_title": chapter_title,
        "question": question,
        "source_images": imgs,
        "book_solution_hint": "参考解析",
        "tags": {
            "domain": domain,
            "topic": topic or ["三角形比例与等积模型"],
            "method": method or ["割补平移与等积变形"],
            "difficulty": difficulty,
            "visual": visual,
            "format": fmt,
            "extra_tags": extra_tags or [],
        },
        "audit": audit,
    }


def load_wave_workflow_module(tmp_root: Path) -> dict[str, Any]:
    """
    Parse `scripts/wave_workflow.py` using `ast.PyCF_ALLOW_TOP_LEVEL_AWAIT`, strip
    the trailing top-level `await main()`, and exec definitions in an isolated namespace.
    """
    wf_path = SKILL_SCRIPTS / "wave_workflow.py"
    source = wf_path.read_text(encoding="utf-8")
    # Syntax-check the entire file including top-level await
    compile(source, str(wf_path), "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)

    tree = ast.parse(source, filename=str(wf_path))
    # Drop final top-level `await main()` expression so helper functions can be unit-tested
    filtered_body = [
        node
        for node in tree.body
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Await))
    ]
    mod_without_await = ast.Module(body=filtered_body, type_ignores=tree.type_ignores)
    ast.fix_missing_locations(mod_without_await)
    code = compile(mod_without_await, str(wf_path), "exec")

    ns: dict[str, Any] = {
        "WORKSPACES": [str(tmp_root)],
        "args": {},
        "log": lambda msg: None,
        "phase": lambda name: None,
    }
    exec(code, ns)
    return ns


class TestInitProject(unittest.TestCase):
    def test_scaffold_templates_and_plan_waves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "MyNewBook"
            rc = init_project.main(
                [
                    "--root",
                    str(root),
                    "--book-name",
                    "测试新奥数题典",
                    "--copy-scripts",
                    "--copy-taxonomy",
                    "--copy-runbook",
                ]
            )
            self.assertEqual(rc, 0)

            for rel in (
                "staging/enriched/shards",
                "staging/symbol_audit",
                "scripts",
                "reports",
                "tests/repro",
                "tests/regression",
                ".agents/teamwork/wave_reviews",
            ):
                self.assertTrue((root / rel).is_dir(), f"Missing dir {rel}")

            state = json.loads((root / "staging/wave_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["book_name"], "测试新奥数题典")
            self.assertEqual(state["pilot_completed"], [])
            self.assertEqual(state["empty_chapters"], [])
            self.assertEqual(state["chapters"], {})

            for sname in (
                "precheck_geometry_symbols.py",
                "validate_enriched.py",
                "export_output.py",
                "wave_workflow.py",
            ):
                self.assertTrue((root / "scripts" / sname).is_file())

            self.assertTrue((root / "taxonomy.yaml").is_file())
            runbook = (root / "PIPELINE_RUNBOOK.md").read_text(encoding="utf-8")
            self.assertIn("测试新奥数题典", runbook)
            self.assertNotIn("{{BOOK_NAME}}", runbook)
            self.assertNotIn("{{WORKSPACE_ROOT}}", runbook)

            # Create mock raw chapters: ch01 (pilot), ch02 (empty), ch03..ch05
            write_jsonl(root / "staging/ch01_raw.jsonl", [{"id": "ch01_001", "source_images": []}])
            (root / "staging/ch02_raw.jsonl").write_text("", encoding="utf-8")
            write_jsonl(
                root / "staging/ch03_raw.jsonl",
                [{"id": f"ch03_{i:03d}", "source_images": ["a.jpg", "b.jpg"]} for i in range(1, 5)],
            )  # 4 Qs + 8 imgs -> weight 8.0
            write_jsonl(
                root / "staging/ch04_raw.jsonl",
                [{"id": f"ch04_{i:03d}", "source_images": []} for i in range(1, 6)],
            )  # 5 Qs -> weight 5.0
            write_jsonl(
                root / "staging/ch05_raw.jsonl",
                [{"id": f"ch05_{i:03d}", "source_images": []} for i in range(1, 6)],
            )  # 5 Qs -> weight 5.0

            rc_plan = init_project.main(
                [
                    "--root",
                    str(root),
                    "--book-name",
                    "测试新奥数题典",
                    "--plan-waves",
                    "--wave-target-qs",
                    "10",
                    "--exclude-chapters",
                    "1",
                ]
            )
            self.assertEqual(rc_plan, 0)
            waves_data = json.loads((root / "staging/waves.json").read_text(encoding="utf-8"))
            self.assertEqual(waves_data["empty_chapters"], [2])
            self.assertEqual(waves_data["excluded_chapters"], [1])
            # ch03 (w=8) fits wave 1, ch04 (w=5) pushes >10 -> wave 2 gets [4, 5] (w=10)
            self.assertEqual(waves_data["waves"], {"1": [3], "2": [4, 5]})


class TestPrecheckGeometrySymbols(unittest.TestCase):
    def test_auto_discover_and_root_dir_beyond_40(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging = root / "staging"
            write_jsonl(
                staging / "ch55_raw.jsonl",
                [
                    {
                        "id": "ch55_001",
                        "chapter": 55,
                        "chapter_title": "第五十五章 扩展几何",
                        "question": "如图，在△ABE中，①比②大3。",
                        "book_solution_hint": "在△ABF中，①比③大3。",
                    }
                ],
            )
            rc = precheck_geometry_symbols.main(["--root-dir", str(root)])
            self.assertEqual(rc, 0)
            audit_file = staging / "symbol_audit" / "ch55_symbol_audit.json"
            self.assertTrue(audit_file.is_file())
            payload = json.loads(audit_file.read_text(encoding="utf-8"))
            self.assertEqual(payload["chapter"], 55)
            self.assertEqual(payload["suspect_ids"], ["ch55_001"])
            self.assertIn("NEAR_MISS_COMBO", payload["records"][0]["suspect_reasons"])
            self.assertIn("CIRCLED_NUMBER_MISMATCH", payload["records"][0]["suspect_reasons"])


class TestValidateEnriched(unittest.TestCase):
    def test_taxonomy_template_counts_and_ch55_merge_validate(self) -> None:
        tpl_path = SKILL_RESOURCES / "taxonomy_template.yaml"
        spec = validate_enriched.load_taxonomy(tpl_path)
        self.assertEqual(len(spec.domains), 7)
        self.assertEqual(len(spec.all_topics), 57)
        self.assertEqual(len(spec.all_methods), 44)
        self.assertEqual(spec.difficulty_levels, {1, 2, 3, 4})
        self.assertEqual(len(spec.visuals), 5)
        self.assertEqual(len(spec.formats), 5)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "img55.jpg").write_bytes(b"fake-image")
            write_jsonl(
                root / "staging/ch55_raw.jsonl",
                [{"id": "ch55_001"}, {"id": "ch55_002"}],
            )
            r1 = make_enriched_record(
                qid="ch55_001",
                chapter=55,
                question="如图，求三角形面积。",
                source_images=["img55.jpg"],
                status="auto_fixed",
                visual="几何图形",
            )
            r2 = make_enriched_record(
                qid="ch55_002",
                chapter=55,
                question="图缺失。",
                source_images=[],
                status="flagged",
                solvable=False,
                visual="纯文字",
            )
            write_jsonl(root / "staging/enriched/shards/ch55_p2.jsonl", [r2])
            write_jsonl(root / "staging/enriched/shards/ch55_p1.jsonl", [r1])

            rc = validate_enriched.main(
                [
                    "--all",
                    "--merge-shards",
                    "--root-dir",
                    str(root),
                    "--taxonomy",
                    str(tpl_path),
                ]
            )
            self.assertEqual(rc, 0)
            self.assertTrue((root / "staging/enriched/ch55_enriched.jsonl").is_file())
            self.assertTrue((root / "reports/ch55_ocr_fixes.md").is_file())
            self.assertTrue((root / "reports/ch55_audit_report.md").is_file())

    def test_load_taxonomy_supports_flat_and_custom_method_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flat_tax = {
                "domains": [{"name": "代数"}],
                "topics": {"代数": [{"name": "一元二次方程"}]},
                "methods": [{"name": "配方法"}, {"name": "因式分解"}],
                "difficulty": [{"level": 1, "name": "1-基础"}],
                "visual": [{"name": "纯文字"}],
                "format": [{"name": "解答题"}],
            }
            p = Path(tmp) / "flat.yaml"
            p.write_text(yaml.safe_dump(flat_tax, allow_unicode=True), encoding="utf-8")
            spec = validate_enriched.load_taxonomy(p)
            self.assertEqual(spec.all_methods, {"配方法", "因式分解"})


class TestExportOutput(unittest.TestCase):
    def test_split_images_ghost_cleanup_and_short_name(self) -> None:
        self.assertEqual(
            export_output.sanitize_chapter_short_name("第一章 “五式”之首——计算基础", 1),
            "计算基础",
        )
        self.assertEqual(
            export_output.sanitize_chapter_short_name("第三章 第二篇——函数与导数", 3),
            "函数与导数",
        )
        self.assertEqual(
            export_output.sanitize_chapter_short_name("第三十六章 组合计数——管中窥计数", 36),
            "组合计数",
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tpl_path = SKILL_RESOURCES / "taxonomy_template.yaml"
            (root / "img1.jpg").write_bytes(b"img-data")
            (root / "img2.png").write_bytes(b"img-data-2")
            write_jsonl(
                root / "staging/ch55_raw.jsonl",
                [{"id": "ch55_001"}, {"id": "ch55_002"}],
            )
            r1 = make_enriched_record(
                qid="ch55_001",
                chapter=55,
                chapter_title="第五十五章 第一篇——高章测试",
                question="如图，求面积。",
                source_images=["img1.jpg"],
                status="pass",
                visual="几何图形",
            )
            r2 = make_enriched_record(
                qid="ch55_002",
                chapter=55,
                chapter_title="第五十五章 第一篇——高章测试",
                question="图有矛盾。",
                source_images=["img2.png"],
                status="flagged",
                solvable=False,
                visual="几何图形",
            )
            write_jsonl(root / "staging/enriched/ch55_enriched.jsonl", [r1, r2])

            # Pre-seed stale directory to verify ghost cleanup
            stale_dir = root / "output/ch55_旧目录"
            stale_dir.mkdir(parents=True)
            (stale_dir / "ghost.txt").write_text("stale", encoding="utf-8")

            rc = export_output.main(
                ["--all", "--root-dir", str(root), "--taxonomy", str(tpl_path)]
            )
            self.assertEqual(rc, 0)
            self.assertFalse(stale_dir.exists())

            out_dir = root / "output/ch55_高章测试"
            flg_dir = root / "flagged/ch55_高章测试"
            self.assertTrue((out_dir / "images/ch55_001_1.jpg").is_file())
            self.assertFalse((out_dir / "md/ch55_002.md").exists())
            self.assertTrue((flg_dir / "images/ch55_002_1.png").is_file())
            self.assertTrue((flg_dir / "md/ch55_002.md").is_file())

            # Now flip r2 to pass -> flagged dir must not exist at all
            r2["audit"] = {
                "status": "pass",
                "solvable": True,
                "verified_by": ["vision_diagram_check"],
            }
            write_jsonl(root / "staging/enriched/ch55_enriched.jsonl", [r1, r2])
            rc2 = export_output.main(
                ["--chapters", "55", "--root-dir", str(root), "--taxonomy", str(tpl_path)]
            )
            self.assertEqual(rc2, 0)
            self.assertFalse(flg_dir.exists())


class TestWaveWorkflow(unittest.TestCase):
    def test_ast_and_static_dehardcoding_guarantees(self) -> None:
        wf_path = SKILL_SCRIPTS / "wave_workflow.py"
        src = wf_path.read_text(encoding="utf-8")

        # 1. AST compile check with top-level await support
        compile(src, str(wf_path), "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)

        # 2. No book-specific hardcoding or top-level yaml import
        self.assertNotIn("明心", src)
        self.assertNotIn("五式", src)
        self.assertIsNone(re.search(r"pilot_completed.*28", src))

        tree = ast.parse(src, filename=str(wf_path))
        for stmt in tree.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    self.assertNotEqual(alias.name, "yaml", "Top-level import yaml is forbidden")
            elif isinstance(stmt, ast.ImportFrom):
                self.assertNotEqual(stmt.module, "yaml", "Top-level from yaml import is forbidden")

        # 3. Required operational patterns
        for token in ("os.replace", "PYTHONUTF8", "ensure_ascii=True", "review_concurrency", "--root-dir"):
            self.assertIn(token, src)

    def test_dynamic_waves_missing_hints_and_resolve_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ns = load_wave_workflow_module(root)

            # Setup staging with empty ch02 and non-empty ch01 (no hint), ch03 (with imgs)
            staging = root / "staging"
            write_jsonl(
                staging / "ch01_raw.jsonl",
                [
                    {
                        "id": "ch01_001",
                        "book_solution_hint": "",
                        "ocr_precheck_flags": ["MISSING_SOLUTION_HINT"],
                        "source_images": [],
                    },
                    {
                        "id": "ch01_002",
                        "book_solution_hint": "有解析",
                        "ocr_precheck_flags": [],
                        "source_images": ["a.jpg", "b.jpg"],
                    },
                ],
            )
            (staging / "ch02_raw.jsonl").write_text("", encoding="utf-8")
            write_jsonl(
                staging / "ch03_raw.jsonl",
                [{"id": f"ch03_{i:03d}", "source_images": []} for i in range(1, 5)],
            )

            self.assertEqual(ns["detect_empty_chapters"](staging), [2])

            waves, empty = ns["plan_balanced_waves"](staging, target_wave_weight=3.5)
            self.assertEqual(empty, [2])
            # ch01 has 2 Qs + 2 imgs * 0.5 = weight 3.0 -> wave 1; ch03 weight 4.0 -> wave 2
            self.assertEqual(waves, {1: [1], 2: [3]})

            # Test waves.json compatibility (nested and flat)
            w_nested = staging / "waves_nested.json"
            w_nested.write_text(json.dumps({"waves": {"1": [1, 3]}}), encoding="utf-8")
            self.assertEqual(ns["load_waves_from_file"](w_nested), {1: [1, 3]})
            w_flat = staging / "waves_flat.json"
            w_flat.write_text(json.dumps({"1": [1], "2": [3]}), encoding="utf-8")
            self.assertEqual(ns["load_waves_from_file"](w_flat), {1: [1], 2: [3]})

            # Test dynamic missing hint detection in enrich & review prompts
            raw_ch1 = ns["load_jsonl"](staging / "ch01_raw.jsonl")
            missing = ns["find_missing_hint_ids"](raw_ch1)
            self.assertEqual(missing, ["ch01_001"])

            enrich_prompt = ns["build_enrich_prompt"](
                {
                    "chapter": 1,
                    "shard_label": "ch01_full",
                    "output_rel": "staging/enriched/ch01_enriched.jsonl",
                    "expected_ids": ["ch01_001", "ch01_002"],
                    "suspect_slice": [],
                    "missing_hint_ids": missing,
                },
                "TAXONOMY_SUMMARY",
            )
            self.assertIn("ch01_001", enrich_prompt)
            self.assertIn("无参考答案", enrich_prompt)

            review_prompt = ns["build_review_prompt"](
                [1],
                ".agents/teamwork/wave_reviews/wave_1_review_ch01.md",
                missing_hint_by_ch={1: missing},
            )
            self.assertIn("ch01_001", review_prompt)
            self.assertIn("MISSING_SOLUTION_HINT", review_prompt)

            # Test resolve_script fallback to skill scripts dir
            resolved = ns["resolve_script"](
                "validate_enriched.py", skill_scripts_dir=SKILL_SCRIPTS, root_dir=root
            )
            self.assertEqual(resolved, SKILL_SCRIPTS / "validate_enriched.py")

            # Test build_taxonomy_summary with template and flat methods
            summary_tpl = ns["build_taxonomy_summary"](
                sys.executable, SKILL_RESOURCES / "taxonomy_template.yaml"
            )
            self.assertIn("通用数学思想", summary_tpl)
            self.assertIn("专项解题模型与技巧", summary_tpl)

            flat_tax_path = root / "flat_taxonomy.yaml"
            flat_tax_path.write_text(
                yaml.safe_dump(
                    {
                        "domains": [{"name": "代数"}],
                        "topics": {"代数": [{"name": "函数"}]},
                        "methods": [{"name": "换元法"}],
                        "difficulty": [{"level": 1, "name": "1-基础"}],
                        "visual": [{"name": "纯文字"}],
                        "format": [{"name": "解答题"}],
                    },
                    allow_unicode=True,
                ),
                encoding="utf-8",
            )
            summary_flat = ns["build_taxonomy_summary"](sys.executable, flat_tax_path)
            self.assertIn("换元法", summary_flat)


if __name__ == "__main__":
    unittest.main()
