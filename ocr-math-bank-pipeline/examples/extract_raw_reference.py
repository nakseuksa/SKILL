#!/usr/bin/env python3
"""
本文件为 Stage 1 抽取脚本参考实现，新书请按目录/题号结构定制本项目 `scripts/extract_raw.py`。
原实现面向四分卷 Markdown 与《第X题图》浮动配图绑定，可直接作为 Stage 1 规则引擎与前置预检的蓝本。
新项目只需保证输出标准 `staging/chXX_raw.jsonl` 字段契约，即可无缝衔接通用 Stage 2-3 流水线。

Stage 1: Structured Extraction & OCR Pre-check for 《明心数学资优生大题典》.

Reads the 4 OCR markdown volumes in read-only mode, skips TOC front-matter,
stitches cross-volume chapter/section boundaries (Ch 23 and Ch 32), extracts
all example problems (例题) and past-competition exercises (真题重现 <-> 参考答案),
binds floating figures (第X题图), strips competition-source parentheticals,
populates taxonomy rule_tags, runs Layer-1 OCR pre-check flags, and emits:
  - staging/ch01_raw.jsonl .. staging/ch40_raw.jsonl
  - staging/extract_report.json
  - staging/equation_table_index.json
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Ensure UTF-8 stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = Path(__file__).resolve().parent.parent
STAGING_DIR = ROOT_DIR / "staging"
TAXONOMY_PATH = ROOT_DIR / "taxonomy.yaml"

CHUNKS = [
    ("上_001_256", ROOT_DIR / "上_001_256" / "part_001_256.md"),
    ("上_257_313", ROOT_DIR / "上_257_313" / "part_257_313.md"),
    ("下_001_200", ROOT_DIR / "下_001_200" / "part_001_200.md"),
    ("下_201_400", ROOT_DIR / "下_201_400" / "part_201_400.md"),
]

CN_DIGIT = {
    "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

# Regex patterns
CHAPTER_RE = re.compile(r"^\s*#{1,6}\s*第\s*([一二三四五六七八九十0-9]+)\s*章\s*(.*)$")
SECTION_RE = re.compile(r"^\s*#{1,6}\s*(\d+\.\d+(?:\.\d+)?)\s+(.*)$")
ZHENTI_RE = re.compile(r"^\s*#{1,6}\s*真题重现\s*$")
ANS_RE = re.compile(r"^\s*#{1,6}\s*参考答案\s*$")
PART_OR_END_RE = re.compile(
    r"^\s*#{1,6}\s*(?:第[一二三四五六]篇.*|结\s*语)\s*$"
)
PROSE_STOP_RE = re.compile(
    r"^\s*#{1,6}\s*(?:延伸|练一练)\s*$"
)
LIANYILIAN_ANS_RE = re.compile(r"^\s*【[\d.]+\s*节练一练参考答案】")

# Example headings: `例 1 ...`, `例1 ...`, `## 例 1 ...`, `【例 10-1】...`, `例 14-A ...`, `例 ...`
EX_CANDIDATE_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:【)?例(?:\s*(\d+(?:\s*[-—]\s*(?:\d+|[A-Za-z]))?)\s*】?|\s+)(.*)$"
)
# Exclude prose references like "例 1 和例 2 都可以", "例1表格", "例6中的", "例 7 变身:", "例1、例2中的", "例 16 展现了"
EX_PROSE_EXCLUDE_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?例\s*\d+(?:\s*[、和与及]\s*例\s*\d+)*(?:表格|中的|变身|展现了)"
)
SOL_HEAD_RE = re.compile(r"^\s*(?:#{1,6}\s*)?解析\s*$")
SOL_INLINE_RE = re.compile(r"^\s*(?:【解析】|解析\s*[:：])\s*(.*)$")
SOL_SUBHEAD_RE = re.compile(r"^(?:[一二三四五六]年级的你|方法\s*\d+|解法\s*\d+)\s*[:：][^。？！?!]{1,40}$")

QNUM_RE = re.compile(r"^\s*(?:#{1,6}\s*)?(\d+)\.\s*(.*)$")
CAP_RE = re.compile(r"^\s*(?:#{1,6}\s*)?(第\s*\d+\s*题图)\s*$")
CAP_NUM_RE = re.compile(r"第\s*(\d+)\s*题图")
IMG_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
SUBSECTION_TAG_RE = re.compile(r"^\s*#{1,6}\s*(?:基础部分|拓展部分)\s*$")
PAGE_FROM_IMG_RE = re.compile(r"page_(\d+)_")

# Competition source parenthetical matching
COMP_STRICT_RE = re.compile(
    r"^(?:"
    r"(?:19\d{2}|20[0-2]\d)\s*(?:[年·.\s]|MO)|"
    r"第\s*[一二三四五六七八九十百0-9]+\s*届|"
    r"MO\s*\d{4}|"
    r".*?(?:数学花园探秘|探秘|华罗庚金杯|华杯赛|华杯|希望杯|迎春杯|明心|优才杯|"
    r"顺天府学|高思杯|创新杯|走美|走进美妙的?数学花园|中环杯|亚太|资优生|时代杯|"
    r"巨人杯|陈省身杯|海峡两岸|世少赛|奥林匹克|我爱数学|我们爱数学|兴趣杯|"
    r"小学生数学报|奥数|IMC|AMC|SMO|MO\s*竞赛|竞赛年鉴|竞赛通鉴|数学文化节|"
    r"小学数学竞赛|数学邀请赛|数学竞赛|入学测试题|网赛|初赛|复赛|决赛|"
    r"第一试|第二试|一试|二试|[ABCD]\s*卷|九章算术)"
    r")"
)
COMP_EXCLUDE_PREFIX_RE = re.compile(
    r"^(?:注\s*[:：]|假定|假设|单位\s*[:：]|提示\s*[:：]|即|如\s*[:：]?|例如|"
    r"其中|不含|不包括|含|不算|至少|小数|保留|取\s|π|0\s*除外|可重复|首位)"
)
STANDALONE_PAREN_RE = re.compile(r"^\s*([（(][^()（）]{2,110}[）)])\s*$")
TRAILING_PAREN_RE = re.compile(r"\s*([（(][^()（）]{2,110}[）)])\s*$")


@dataclass
class LineItem:
    chunk: str
    line_no: int
    page: int
    text: str


def parse_cn_num(s: str) -> int:
    if s.isdigit():
        return int(s)
    if s in CN_DIGIT:
        return CN_DIGIT[s]
    if s.startswith("十"):
        return 10 + (CN_DIGIT[s[1]] if len(s) > 1 else 0)
    if "十" in s:
        parts = s.split("十")
        tens = CN_DIGIT[parts[0]]
        ones = CN_DIGIT[parts[1]] if parts[1] else 0
        return tens * 10 + ones
    return -1


def load_and_stitch_chunks() -> tuple[list[LineItem], set[str]]:
    """
    Read all 4 markdown chunks, locate body start (skipping front-matter/TOC),
    rewrite relative image paths to `<chunk>/images/...`, track running page numbers,
    and stitch into a single ordered list of LineItem.
    Also returns the full set of all image paths referenced anywhere in all 4 MDs.
    """
    all_referenced_images: set[str] = set()
    stitched: list[LineItem] = []

    for chunk_name, md_path in CHUNKS:
        with open(md_path, "r", encoding="utf-8") as f:
            raw_lines = [line.rstrip("\r\n") for line in f]

        # Rewrite ![](images/...) -> ![](<chunk>/images/...) and collect all referenced images
        rewritten_lines: list[str] = []
        for line in raw_lines:
            def _repl(m: re.Match[str]) -> str:
                rel = m.group(1).strip()
                if rel.startswith("images/"):
                    full_rel = f"{chunk_name}/{rel}"
                else:
                    full_rel = rel
                all_referenced_images.add(full_rel)
                return f"![]({full_rel})"

            rewritten_lines.append(IMG_RE.sub(_repl, line))

        # Determine TOC end / body start:
        # 上_001_256 starts body at `# 第一章`
        # 下_001_200 starts body at `## 第二十六章`
        # 上_257_313 and 下_201_400 are pure continuations (start at index 0)
        start_idx = 0
        if chunk_name == "上_001_256":
            for i, line in enumerate(rewritten_lines):
                if re.match(r"^\s*#\s+第一章\b", line):
                    start_idx = i
                    break
        elif chunk_name == "下_001_200":
            for i, line in enumerate(rewritten_lines):
                if re.match(r"^\s*#{1,2}\s+第二十六章\s+直线图形基础\s*$", line):
                    start_idx = i
                    break

        # Track running page number from page_X_ in image filenames
        current_page = 1
        # Pre-scan up to start_idx to initialize current_page accurately
        for i in range(start_idx):
            for m in PAGE_FROM_IMG_RE.finditer(rewritten_lines[i]):
                current_page = int(m.group(1))

        for i in range(start_idx, len(rewritten_lines)):
            line = rewritten_lines[i]
            for m in PAGE_FROM_IMG_RE.finditer(line):
                current_page = int(m.group(1))
            stitched.append(
                LineItem(
                    chunk=chunk_name,
                    line_no=i + 1,
                    page=current_page,
                    text=line,
                )
            )

    return stitched, all_referenced_images


@dataclass
class CleanStream:
    """Line stream with <details> blocks removed, preserving summary annotations on preceding images."""
    items: list[LineItem]
    image_summaries: dict[tuple[str, int, str], str] = field(default_factory=dict)


def strip_details_blocks(lines: list[LineItem]) -> CleanStream:
    """
    Strip `<details>...</details>` blocks while associating each `<summary>` type
    with the immediately preceding image reference (if any).
    """
    clean: list[LineItem] = []
    summaries: dict[tuple[str, int, str], str] = {}
    in_details = False
    last_img_key: tuple[str, int, str] | None = None
    lines_since_img = 999

    for item in lines:
        s = item.text.strip()
        if not in_details:
            if "<details>" in s:
                in_details = True
                # Handle single-line <details>...</details> just in case
                if "</details>" in s:
                    m_sum = re.search(r"<summary>(.*?)</summary>", s)
                    if m_sum and last_img_key and lines_since_img <= 3:
                        summaries[last_img_key] = m_sum.group(1).strip()
                    in_details = False
                continue

            clean.append(item)
            imgs = IMG_RE.findall(item.text)
            if imgs:
                last_img_key = (item.chunk, item.line_no, imgs[-1])
                lines_since_img = 0
            elif s:
                lines_since_img += 1
        else:
            m_sum = re.search(r"<summary>(.*?)</summary>", s)
            if m_sum and last_img_key and lines_since_img <= 3:
                summaries[last_img_key] = m_sum.group(1).strip()
            if "</details>" in s:
                in_details = False

    return CleanStream(items=clean, image_summaries=summaries)


UNCLOSED_COMP_TAIL_RE = re.compile(
    r"\s*([（(](?:19\d{2}|20[0-2]\d)\s*(?:[年·.\s]|MO)[^()（）$\n]{1,50})$"
)


def is_competition_paren(inner: str, open_bracket: str = "(") -> bool:
    inner = inner.strip()
    if COMP_EXCLUDE_PREFIX_RE.search(inner):
        return False
    if open_bracket == "《" and inner == "九章算术":
        return False
    return bool(COMP_STRICT_RE.search(inner))


def extract_trailing_balanced_bracket(s: str) -> tuple[int, str, str] | None:
    """
    If `s` (after rstrip) ends with `)`, `）`, or `》`, scan backwards with
    nesting depth tracking to locate the matching opening bracket (`(`, `（`, or `《`).
    Returns `(start_idx, full_token, inner_text)` if found within 150 chars, else None.
    """
    stripped_s = s.rstrip()
    if not stripped_s:
        return None
    end_ch = stripped_s[-1]
    if end_ch in (")", "）"):
        close_set = (")", "）")
        open_set = ("(", "（")
    elif end_ch == "》":
        close_set = ("》",)
        open_set = ("《",)
    else:
        return None

    depth = 0
    min_idx = max(0, len(stripped_s) - 150)
    for idx in range(len(stripped_s) - 1, min_idx - 1, -1):
        ch = stripped_s[idx]
        if ch in close_set:
            depth += 1
        elif ch in open_set:
            depth -= 1
            if depth == 0:
                token = stripped_s[idx:]
                if len(token) < 4:
                    return None
                return idx, token, token[1:-1]
    return None


def strip_competition_sources(lines: list[str]) -> tuple[str, list[str]]:
    """
    Remove confirmed competition/exam source parentheticals (including nested
    parentheses, `《...》` citations, and trailing unclosed OCR-duplicated source
    fragments) from lines, preserving mathematical conditions, notes, units,
    and sub-question markers.
    Returns (cleaned_text, stripped_sources).
    """
    stripped: list[str] = []
    out_lines: list[str] = []

    for line in lines:
        s = line.strip()
        # Case 1: whole line is a standalone source parenthetical / 《...》
        m_full = extract_trailing_balanced_bracket(s)
        if m_full and m_full[0] == 0:
            _, token, inner = m_full
            if is_competition_paren(inner, token[0]):
                stripped.append(token)
                continue

        # Case 2: trailing source parenthetical(s) / 《...》 at end of line
        cur = line
        while True:
            m_trail = extract_trailing_balanced_bracket(cur)
            if not m_trail:
                break
            start_idx, token, inner = m_trail
            prefix = cur[:start_idx].rstrip()
            if token[0] == "《" and prefix.endswith(("——", "—")):
                break
            if is_competition_paren(inner, token[0]):
                stripped.append(token)
                cur = prefix
            else:
                break

        # Case 3: unclosed OCR-duplicated source fragment at end of line
        m_unclosed = UNCLOSED_COMP_TAIL_RE.search(cur)
        if m_unclosed:
            frag = m_unclosed.group(1)
            if is_competition_paren(frag[1:], frag[0]):
                stripped.append(frag)
                cur = cur[: m_unclosed.start()].rstrip()

        out_lines.append(cur)

    # Collapse excessive blank lines
    text = "\n".join(out_lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, stripped


def clean_question_and_collect_images(
    items: list[LineItem],
    summaries_map: dict[tuple[str, int, str], str],
    strip_prefix_mode: str,
) -> tuple[str, list[str], list[str], list[str], list[int]]:
    """
    Extract images, summaries, captions, pages, and produce clean neutral question text.
    strip_prefix_mode: 'example' or 'exercise'
    """
    images: list[str] = []
    img_summaries: list[str] = []
    captions: list[str] = []
    pages: list[int] = []
    text_lines: list[str] = []

    for idx, item in enumerate(items):
        s = item.text
        # Collect images on this line
        line_imgs = IMG_RE.findall(s)
        for img_path in line_imgs:
            if img_path not in images:
                images.append(img_path)
            key = (item.chunk, item.line_no, img_path)
            if key in summaries_map:
                sm = summaries_map[key]
                if sm not in img_summaries:
                    img_summaries.append(sm)
            pm = PAGE_FROM_IMG_RE.search(img_path)
            if pm:
                pno = int(pm.group(1))
                if pno not in pages:
                    pages.append(pno)

        # Strip markdown image syntax from line
        s_no_img = IMG_RE.sub("", s).strip()

        # Check standalone caption line `第 N 题图`
        m_cap = CAP_RE.match(s_no_img)
        if m_cap:
            cap_text = re.sub(r"\s+", "", m_cap.group(1))
            if cap_text not in captions:
                captions.append(cap_text)
            continue

        # Strip prefix on first non-empty text line
        if idx == 0 or (not text_lines and s_no_img):
            if strip_prefix_mode == "example":
                s_no_img = re.sub(
                    r"^\s*(?:#{1,6}\s*)?(?:【)?例(?:\s*\d+(?:\s*[-—]\s*(?:\d+|[A-Za-z]))?\s*】?|\s+)\s*",
                    "",
                    s_no_img,
                )
            elif strip_prefix_mode == "exercise":
                s_no_img = re.sub(r"^\s*(?:#{1,6}\s*)?\d+\.\s*", "", s_no_img)

        text_lines.append(s_no_img)

    # Trim leading/trailing empty lines
    while text_lines and not text_lines[0].strip():
        text_lines.pop(0)
    while text_lines and not text_lines[-1].strip():
        text_lines.pop()

    cleaned_text, stripped_sources = strip_competition_sources(text_lines)

    # Also remove trailing caption if somehow attached at end of line
    if not pages and items:
        pages = sorted({it.page for it in items})
    else:
        pages = sorted(set(pages))

    return cleaned_text, images, captions, img_summaries, pages, stripped_sources  # type: ignore


def extract_solution_text_and_images(
    items: list[LineItem], is_answer_item: bool = False
) -> tuple[str, list[str]]:
    sol_images: list[str] = []
    lines: list[str] = []
    for idx, item in enumerate(items):
        s = item.text
        for img_path in IMG_RE.findall(s):
            if img_path not in sol_images:
                sol_images.append(img_path)
        s_no_img = IMG_RE.sub("", s).strip()
        if CAP_RE.match(s_no_img):
            continue
        if idx == 0 and is_answer_item:
            s_no_img = re.sub(r"^\s*(?:#{1,6}\s*)?\d+\.\s*", "", s_no_img)
        lines.append(s_no_img)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, sol_images


def is_visual_figure_sublabel(text: str) -> bool:
    s = text.strip()
    if not s:
        return True
    if re.match(r"^(?:图\s*\d+|图\s*[a-zA-Z]|[A-Za-z]|\d+\s*号|正视图|侧视图|俯视图|\(\d+\))$", s):
        return True
    if re.match(r"^图\s*[a-zA-Z]\s*[（(].*[）)]$", s):
        return True
    return False


def parse_zhenti_block(
    block_items: list[LineItem],
    summaries_map: dict[tuple[str, int, str], str],
) -> tuple[dict[int, dict[str, Any]], int]:
    """
    Parse a `## 真题重现` block into {q_num: parsed_question_dict}.
    Handles floating figures marked with `第 k 题图` both before and after questions,
    split figure+table floats, and post-caption orphan images right before the next question.
    """
    # Filter out ## 基础部分 / ## 拓展部分 markers
    items = [it for it in block_items if not SUBSECTION_TAG_RE.match(it.text.strip())]

    # Identify question start indices sequentially (1, 2, ..., N)
    q_starts: list[tuple[int, int]] = []  # (idx_in_items, q_num)
    expected_q = 1
    for i, it in enumerate(items):
        m = QNUM_RE.match(it.text.strip())
        if m:
            num = int(m.group(1))
            if num == expected_q:
                q_starts.append((i, num))
                expected_q += 1

    if not q_starts:
        return {}, 0

    max_q = q_starts[-1][1]
    # Initial assignment: each line gets assigned to its enclosing question raw_q (0 if before Q1)
    assigned_q = [0] * len(items)
    for qi, (start_i, qnum) in enumerate(q_starts):
        end_i = q_starts[qi + 1][0] if qi + 1 < len(q_starts) else len(items)
        for idx in range(start_i, end_i):
            assigned_q[idx] = qnum

    q_start_idx_set = {idx for idx, _ in q_starts}

    # Pass 1: Reassign caption-bound floating figures/tables/diagrams (`第 k 题图`)
    # Track which indices have been claimed by a CAP(k) so subsequent CAPs stop cleanly
    claimed_by_cap: set[int] = set()
    cap_positions: list[tuple[int, int]] = []
    for idx, it in enumerate(items):
        mc = CAP_RE.match(it.text.strip())
        if mc:
            m_num = CAP_NUM_RE.search(mc.group(1))
            if m_num:
                k = int(m_num.group(1))
                if 1 <= k <= max_q:
                    cap_positions.append((idx, k))

    for cap_idx, k in cap_positions:
        raw_q = assigned_q[cap_idx]
        # Attach the caption line itself to question k
        assigned_q[cap_idx] = k
        claimed_by_cap.add(cap_idx)

        # Walk backwards from cap_idx - 1 to collect its floating figure/table/diagram
        collected: list[int] = []
        j = cap_idx - 1
        found_img = False
        found_table = False
        found_math = False
        in_table = False
        in_math = False
        last_img_had_sublabel = False
        last_img_idx: int | None = None

        def _is_bare_strip_pair(idx_a: int, idx_b: int) -> bool:
            imgs_a = IMG_RE.findall(items[idx_a].text)
            imgs_b = IMG_RE.findall(items[idx_b].text)
            if not imgs_a or not imgs_b:
                return False
            has_det_a = any((items[idx_a].chunk, items[idx_a].line_no, im) in summaries_map for im in imgs_a)
            has_det_b = any((items[idx_b].chunk, items[idx_b].line_no, im) in summaries_map for im in imgs_b)
            if has_det_a or has_det_b:
                return False
            return abs(items[idx_b].line_no - items[idx_a].line_no) <= 3

        while j >= 0:
            if j in claimed_by_cap or j in q_start_idx_set:
                break
            txt = items[j].text.strip()

            # Stop if we hit a competition-source line of a different question
            m_par = extract_trailing_balanced_bracket(txt)
            if m_par and m_par[0] == 0 and is_competition_paren(m_par[2], m_par[1][0]):
                break

            has_img = bool(IMG_RE.search(txt))
            is_tbl_row = txt.startswith("|") or txt.startswith("<table>") or "</table>" in txt or "<td>" in txt
            is_math_delim = txt == "$$"

            if has_img:
                # Guard: when CAP(k) floats inside Q(raw_q != k) and already collected an image,
                # do not steal Q(raw_q)'s trailing diagram(s) placed after CAP(raw_q) unless they
                # share labeled subfigures or form an unbroken bare-image strip (e.g., folding steps).
                if found_img and raw_q != k and raw_q > 0:
                    if not last_img_had_sublabel and (
                        last_img_idx is None or not _is_bare_strip_pair(j, last_img_idx)
                    ):
                        break
                found_img = True
                last_img_idx = j
                collected.append(j)
                j -= 1
                continue

            if is_tbl_row:
                if found_img:
                    break
                found_table = True
                in_table = True
                collected.append(j)
                j -= 1
                continue

            if is_math_delim:
                if found_img or found_table:
                    break
                in_math = not in_math
                found_math = True
                collected.append(j)
                j -= 1
                continue

            if in_math:
                collected.append(j)
                j -= 1
                continue

            if not txt:
                # Blank line: keep scanning backwards if we haven't found content yet,
                # or if inside a multi-image group before a CAP
                if found_table or found_math:
                    break
                if found_img:
                    # Peek further back: is there another image + sublabel belonging to the same CAP?
                    # Only continue across blank line if previous non-empty line is another image or sublabel!
                    p = j - 1
                    while p >= 0 and not items[p].text.strip():
                        p -= 1
                    if p >= 0 and p not in claimed_by_cap and p not in q_start_idx_set:
                        ptxt = items[p].text.strip()
                        if is_visual_figure_sublabel(ptxt):
                            if raw_q != k and not last_img_had_sublabel:
                                break
                            collected.append(j)
                            j -= 1
                            continue
                        if IMG_RE.search(ptxt):
                            if raw_q != k and raw_q > 0 and not last_img_had_sublabel and (
                                last_img_idx is None or not _is_bare_strip_pair(p, last_img_idx)
                            ):
                                break
                            collected.append(j)
                            j -= 1
                            continue
                    break
                collected.append(j)
                j -= 1
                continue

            if is_visual_figure_sublabel(txt):
                if not found_img:
                    last_img_had_sublabel = True
                elif raw_q != k and not last_img_had_sublabel:
                    break
                collected.append(j)
                j -= 1
                continue

            # Short standalone text figure like "47 53 71" right before 第2题图
            if not found_img and not found_table and not found_math and len(txt) <= 25 and not re.search(r"[。？！?!]", txt):
                collected.append(j)
                j -= 1
                continue

            break

        # If we found actual figure/table/math/diagram content, assign those lines to k
        if found_img or found_table or found_math or any(items[c].text.strip() and not is_visual_figure_sublabel(items[c].text) for c in collected):
            for c_idx in collected:
                assigned_q[c_idx] = k
                claimed_by_cap.add(c_idx)

    # Pass 2: Handle trailing image(s) after a CAP that sit right before Q(raw_q+1)
    # e.g., 下_201_400:L7630 `page_129_image_8.jpg` between `第12题图` and `12.`
    for qi, (start_i, qnum) in enumerate(q_starts):
        if qnum == 1:
            continue
        # Look immediately before start_i (skipping blank lines / details) for unclaimed images
        j = start_i - 1
        trailing_unclaimed_imgs: list[int] = []
        while j >= 0:
            if j in claimed_by_cap or j in q_start_idx_set:
                break
            txt = items[j].text.strip()
            if not txt:
                j -= 1
                continue
            if IMG_RE.search(txt):
                # Check if raw_q == qnum - 1 already had a CAP earlier in its span
                prev_q_start = q_starts[qi - 1][0]
                had_cap_in_prev_q = any(
                    CAP_RE.match(items[p].text.strip()) or p in claimed_by_cap
                    for p in range(prev_q_start, j)
                )
                if had_cap_in_prev_q:
                    trailing_unclaimed_imgs.append(j)
                    j -= 1
                    continue
            break
        for c_idx in trailing_unclaimed_imgs:
            assigned_q[c_idx] = qnum

    # Group items by assigned question number (preserving document order, keeping Q start line first)
    grouped: dict[int, list[LineItem]] = defaultdict(list)
    for qi, (start_i, qnum) in enumerate(q_starts):
        grouped[qnum].append(items[start_i])
    for idx, it in enumerate(items):
        if idx in q_start_idx_set:
            continue
        qnum = assigned_q[idx]
        if 1 <= qnum <= max_q:
            grouped[qnum].append(it)

    # Sort each question's items carefully: Q-start line first, then text/tables, keeping order
    results: dict[int, dict[str, Any]] = {}
    for qnum in range(1, max_q + 1):
        q_items = grouped.get(qnum, [])
        if not q_items:
            continue
        # Ensure the QNUM line itself is first even if floating figure appeared before QNUM
        q_start_pos = q_starts[qnum - 1][0]
        q_start_item = items[q_start_pos]
        other_items = [it for it in q_items if it is not q_start_item]
        ordered_items = [q_start_item] + other_items

        q_text, imgs, caps, sums, pages, stripped = clean_question_and_collect_images(
            ordered_items, summaries_map, strip_prefix_mode="exercise"
        )
        results[qnum] = {
            "question": q_text,
            "source_images": imgs,
            "image_captions": caps,
            "ocr_image_summaries": sums,
            "source_pages": pages,
            "stripped_source_text": stripped,
            "source_chunk": q_start_item.chunk,
        }

    return results, max_q


def parse_reference_answers(block_items: list[LineItem]) -> dict[int, tuple[str, list[str]]]:
    """
    Parse a `## 参考答案` block into {q_num: (answer_text, answer_images)},
    binding floating `第 k 题图` diagrams to their true question `k` while
    preserving sole-image answers whose caption number is an OCR typo.
    """
    q_starts: list[tuple[int, int]] = []
    expected_q = 1
    for i, it in enumerate(block_items):
        m = QNUM_RE.match(it.text.strip())
        if m:
            num = int(m.group(1))
            if num == expected_q:
                q_starts.append((i, num))
                expected_q += 1

    if not q_starts:
        return {}

    max_q = q_starts[-1][1]
    assigned_q = [0] * len(block_items)
    q_spans: dict[int, list[LineItem]] = {}
    for qi, (start_i, qnum) in enumerate(q_starts):
        end_i = q_starts[qi + 1][0] if qi + 1 < len(q_starts) else len(block_items)
        q_spans[qnum] = block_items[start_i:end_i]
        for idx in range(start_i, end_i):
            assigned_q[idx] = qnum

    q_start_idx_set = {idx for idx, _ in q_starts}
    claimed_by_cap: set[int] = set()
    cap_positions: list[tuple[int, int]] = []
    for idx, it in enumerate(block_items):
        mc = CAP_RE.match(it.text.strip())
        if mc:
            m_num = CAP_NUM_RE.search(mc.group(1))
            if m_num:
                k = int(m_num.group(1))
                if 1 <= k <= max_q:
                    cap_positions.append((idx, k))

    fig_ref_re = re.compile(r"如图|下图|图\s*\d")
    for cap_idx, k in cap_positions:
        raw_q = assigned_q[cap_idx]
        target_q = k

        if raw_q != k and raw_q > 0:
            raw_items = q_spans.get(raw_q, [])
            k_items = q_spans.get(k, [])
            raw_has_own_cap = any(
                (mc_r := CAP_RE.match(x.text.strip()))
                and (mn_r := CAP_NUM_RE.search(mc_r.group(1)))
                and int(mn_r.group(1)) == raw_q
                for x in raw_items
            )
            raw_img_count = sum(len(IMG_RE.findall(x.text)) for x in raw_items)
            raw_txt = " ".join(x.text.strip() for x in raw_items)
            k_txt = " ".join(x.text.strip() for x in k_items)
            # Typo guard (e.g. 上_001_256:L7270 ch13_021 Q4 sole figure mislabeled `第 5 题图`)
            if (
                not raw_has_own_cap
                and raw_img_count == 1
                and fig_ref_re.search(raw_txt)
                and not fig_ref_re.search(k_txt)
            ):
                target_q = raw_q

        assigned_q[cap_idx] = target_q
        claimed_by_cap.add(cap_idx)

        collected: list[int] = []
        j = cap_idx - 1
        found_img = False
        last_img_had_sublabel = False
        while j >= 0:
            if j in claimed_by_cap or j in q_start_idx_set:
                break
            txt = block_items[j].text.strip()
            has_img = bool(IMG_RE.search(txt))
            if has_img:
                if found_img and raw_q != target_q and not last_img_had_sublabel:
                    break
                found_img = True
                collected.append(j)
                j -= 1
                continue
            if not txt:
                if found_img:
                    p = j - 1
                    while p >= 0 and not block_items[p].text.strip():
                        p -= 1
                    if p >= 0 and p not in claimed_by_cap and p not in q_start_idx_set:
                        ptxt = block_items[p].text.strip()
                        if is_visual_figure_sublabel(ptxt):
                            if raw_q != target_q and not last_img_had_sublabel:
                                break
                            collected.append(j)
                            j -= 1
                            continue
                        if IMG_RE.search(ptxt) and (raw_q == target_q or last_img_had_sublabel):
                            collected.append(j)
                            j -= 1
                            continue
                    break
                collected.append(j)
                j -= 1
                continue
            if is_visual_figure_sublabel(txt):
                if not found_img:
                    last_img_had_sublabel = True
                elif raw_q != target_q and not last_img_had_sublabel:
                    break
                collected.append(j)
                j -= 1
                continue
            break

        if found_img:
            for c_idx in collected:
                assigned_q[c_idx] = target_q
                claimed_by_cap.add(c_idx)

    grouped: dict[int, list[LineItem]] = defaultdict(list)
    for start_i, qnum in q_starts:
        grouped[qnum].append(block_items[start_i])
    for idx, it in enumerate(block_items):
        if idx in q_start_idx_set:
            continue
        qnum = assigned_q[idx]
        if 1 <= qnum <= max_q:
            grouped[qnum].append(it)

    answers: dict[int, tuple[str, list[str]]] = {}
    for qnum in range(1, max_q + 1):
        q_items = grouped.get(qnum, [])
        if not q_items:
            continue
        ans_text, ans_imgs = extract_solution_text_and_images(
            q_items, is_answer_item=True
        )
        answers[qnum] = (ans_text, ans_imgs)
    return answers


def is_real_example_start(items: list[LineItem], idx: int) -> bool:
    """
    Determine whether line `idx` is a real example problem (as opposed to prose reference
    like `例 1 和例 2...` or the preview list `【例 10-1】..【例 10-8】`).
    Verified across all 40 chapters: every real example is followed by `## 解析` / `解析`
    before the next example, section, 真题重现, or chapter heading.
    """
    s = items[idx].text.strip()
    if EX_PROSE_EXCLUDE_RE.match(s):
        return False
    if not EX_CANDIDATE_RE.match(s):
        return False

    for j in range(idx + 1, len(items)):
        sj = items[j].text.strip()
        if (
            CHAPTER_RE.match(sj)
            or SECTION_RE.match(sj)
            or ZHENTI_RE.match(sj)
            or ANS_RE.match(sj)
            or PART_OR_END_RE.match(sj)
        ):
            return False
        if EX_CANDIDATE_RE.match(sj) and not EX_PROSE_EXCLUDE_RE.match(sj):
            return False
        if SOL_HEAD_RE.match(sj) or SOL_INLINE_RE.match(sj):
            return True
    return False


def load_taxonomy(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TaxonomyMapper:
    def __init__(self, tax: dict[str, Any]):
        self.tax = tax
        self.chapter_to_domain: dict[int, str] = {}
        for d in tax["domains"]:
            for ch in d["book_chapters"]:
                self.chapter_to_domain[int(ch)] = d["name"]

        self.domain_topics: dict[str, list[dict[str, Any]]] = tax["topics"]
        self.format_rules: list[tuple[str, list[re.Pattern[str]]]] = []
        # Order matters: check 计算题, 操作构造题, 判断说理题, 填空题, 解答题
        fmt_by_name = {f["name"]: f for f in tax["format"]}
        for fname in ["计算题", "操作构造题", "判断说理题", "填空题", "解答题"]:
            if fname in fmt_by_name:
                pats = [re.compile(p) for p in fmt_by_name[fname].get("regex_hints", [])]
                self.format_rules.append((fname, pats))

    def get_rule_tags(
        self,
        chapter: int,
        section: str,
        question: str,
        source_images: list[str],
        ocr_summaries: list[str],
    ) -> dict[str, Any]:
        domain = self.chapter_to_domain.get(chapter, "计算")
        topics_pool = self.domain_topics.get(domain, [])

        # Candidate topics matching chapter/section
        candidates: list[str] = []
        # Normalize section for matching (also check cross_ref like 35.3 in 逻辑推理)
        all_pools = list(topics_pool)
        if section.startswith("35.3"):
            all_pools = self.domain_topics.get("逻辑推理", []) + all_pools

        if section:
            # 1. Exact or prefix match (e.g., section='1.1.1' matches '1.1', or section='4.2.1' matches '4.2.1')
            for t in all_pools:
                for c in t.get("chapters", []):
                    if section == c or section.startswith(c + "."):
                        if t["name"] not in candidates:
                            candidates.append(t["name"])
            # 2. If none, check if topic chapter is sub-section of current section (e.g. section='4.2' matches '4.2.1')
            if not candidates:
                for t in all_pools:
                    for c in t.get("chapters", []):
                        if c.startswith(section + "."):
                            if t["name"] not in candidates:
                                candidates.append(t["name"])

        # 3. Match by whole chapter number (e.g., '5', '8')
        ch_str = str(chapter)
        if not candidates:
            for t in topics_pool:
                for c in t.get("chapters", []):
                    if c == ch_str or c.startswith(ch_str + "."):
                        if t["name"] not in candidates:
                            candidates.append(t["name"])

        # 4. Fallback: all topics of domain
        if not candidates:
            candidates = [t["name"] for t in topics_pool]

        # Format hint
        q_norm = question.replace(r"\_", "_")
        format_hint = "解答题"
        for fname, pats in self.format_rules:
            if any(p.search(q_norm) for p in pats):
                format_hint = fname
                break

        # Visual hint
        if not source_images:
            visual_hint = "纯文字"
        else:
            stat_summaries = {"bar", "bar_stacked", "area", "donut", "pie", "radar", "treemap", "funnel"}
            if any(s in stat_summaries for s in ocr_summaries):
                visual_hint = "统计与数据表"
            elif domain == "几何" or re.search(
                r"正方形|长方形|三角形|梯形|平行四边形|菱形|多边形|圆|扇形|立方体|正方体|长方体|圆柱|圆锥|阴影|周长|面积|体积|棱长|角度",
                question,
            ):
                visual_hint = "几何图形"
            elif re.search(
                r"方格|九宫格|数阵|棋盘|棋子|点阵|火柴|填数|填入|幻方|数独|网格|格点",
                question,
            ):
                visual_hint = "数阵与棋盘"
            elif "flowchart" in ocr_summaries or domain in ("行程", "逻辑推理") or re.search(
                r"路线|天平|流程图|示意图|车站|路程", question
            ):
                visual_hint = "示意图与路线图"
            else:
                visual_hint = "示意图与路线图"

        return {
            "domain": domain,
            "candidate_topics": candidates,
            "format_hint": format_hint,
            "visual_hint": visual_hint,
        }


def check_latex_balanced(text: str) -> bool:
    """Check that $$ blocks are closed and remaining unescaped $ signs are paired."""
    if not text:
        return True
    # Remove escaped \$
    s = re.sub(r"\\\$", "", text)
    # Count $$ occurrences
    dd_count = len(re.findall(r"\$\$", s))
    if dd_count % 2 != 0:
        return False
    # Strip $$ and check remaining $
    s_no_dd = s.replace("$$", "")
    single_count = s_no_dd.count("$")
    return single_count % 2 == 0


def has_table_or_grid(question: str) -> bool:
    if "<table" in question.lower():
        return True
    # Markdown table separator line
    if re.search(r"\|[\s:-]+\|", question):
        return True
    return False


def has_suspect_divisibility_times(chapter: int, question: str, solution_hint: str) -> bool:
    """
    Detect likely OCR misrecognition of `∤` as `\\times` in number-theory/divisibility context,
    e.g., `2 \\times 157, 3 \\times 157` or `\\because 3 \\times (5+9+4+8)`.
    """
    combined = f"{question}\n{solution_hint}"
    if r"\times" not in combined:
        return False
    is_nt_ctx = (31 <= chapter <= 35) or bool(
        re.search(r"整除|倍数|因数|约数|质数|合数|余数", combined)
    )
    if not is_nt_ctx:
        return False
    # Pattern 1: isolated `<num> \times <num>` or `<num> \times (...)` NOT preceded/followed by = or arithmetic op
    # Look for sequences like `2 \times 157, 3 \times 157` or `且 7 \times 1000` or `而 9 \times (4+5`
    if re.search(
        r"(?:[,，;；]|且|而|即|∴|\\therefore|\\because)\s*\d+\s*\\times\s*(?:\d+|\([^)]+\)|\\overline\{[^}]+\})\s*(?=[,，;；。]|$)",
        combined,
    ):
        return True
    return False


def run_prechecks(
    chapter: int,
    question: str,
    source_images: list[str],
    book_solution_hint: str,
) -> list[str]:
    flags: list[str] = []

    if (
        re.search(r"如图|下图|右图|左图|题图|如图所示|图中", question)
        and not source_images
        and not has_table_or_grid(question)
    ):
        flags.append("MISSING_IMAGE_SUSPECTED")

    if not check_latex_balanced(question):
        flags.append("UNBALANCED_LATEX")

    for img in source_images:
        if not (ROOT_DIR / img).is_file():
            flags.append("BROKEN_IMAGE_PATH")
            break

    effective_chars = len(re.sub(r"\s+", "", question))
    if effective_chars < 8:
        flags.append("EMPTY_OR_TINY_QUESTION")

    if not book_solution_hint.strip():
        flags.append("MISSING_SOLUTION_HINT")

    if has_suspect_divisibility_times(chapter, question, book_solution_hint):
        flags.append("SUSPECT_DIVISIBILITY_TIMES")

    return flags


def build_equation_table_index(all_referenced_images: set[str]) -> dict[str, dict[str, list[str]]]:
    """
    Scan all 4 chunk `images/` directories for unreferenced `*_equation_*.jpg`
    and `*_table_*.jpg`, grouped as `chunk -> page -> [relative_paths]`.
    """
    index: dict[str, dict[str, list[str]]] = {}
    for chunk_name, _ in CHUNKS:
        img_dir = ROOT_DIR / chunk_name / "images"
        if not img_dir.is_dir():
            continue
        by_page: dict[int, list[str]] = defaultdict(list)
        for fname in sorted(os.listdir(img_dir)):
            if "_equation_" not in fname and "_table_" not in fname:
                continue
            rel_path = f"{chunk_name}/images/{fname}"
            if rel_path in all_referenced_images:
                continue
            pm = PAGE_FROM_IMG_RE.search(fname)
            page_num = int(pm.group(1)) if pm else 0
            by_page[page_num].append(rel_path)

        index[chunk_name] = {
            str(p): sorted(paths) for p, paths in sorted(by_page.items())
        }
    return index


def extract_all() -> None:
    if not STAGING_DIR.is_dir():
        STAGING_DIR.mkdir(parents=True, exist_ok=True)
    tax = load_taxonomy(TAXONOMY_PATH)
    mapper = TaxonomyMapper(tax)

    stitched, all_referenced_images = load_and_stitch_chunks()
    clean_stream = strip_details_blocks(stitched)
    items = clean_stream.items
    summaries_map = clean_stream.image_summaries

    # Identify all chapters
    chapters_meta: dict[int, str] = {}
    chapter_records: dict[int, list[dict[str, Any]]] = {ch: [] for ch in range(1, 41)}
    pair_stats: list[dict[str, Any]] = []

    current_chapter = 0
    current_chapter_title = ""
    current_section = ""
    current_section_title = ""

    i = 0
    n = len(items)
    while i < n:
        s = items[i].text.strip()

        # Chapter heading
        m_ch = CHAPTER_RE.match(s)
        if m_ch:
            ch_num = parse_cn_num(m_ch.group(1))
            if 1 <= ch_num <= 40:
                current_chapter = ch_num
                current_chapter_title = re.sub(r"^#{1,6}\s*", "", s).strip()
                chapters_meta[ch_num] = current_chapter_title
                current_section = ""
                current_section_title = ""
            i += 1
            continue

        # Section heading
        m_sec = SECTION_RE.match(s)
        if m_sec:
            sec_num = m_sec.group(1).strip()
            sec_title = m_sec.group(2).strip()
            # Ensure section matches current chapter prefix
            if current_chapter and sec_num.split(".")[0] == str(current_chapter):
                current_section = sec_num
                current_section_title = sec_title
            i += 1
            continue

        # 真题重现 block
        if ZHENTI_RE.match(s) and current_chapter > 0:
            zt_start = i + 1
            zt_end = n
            ans_start = None
            ans_end = n
            for j in range(zt_start, n):
                sj = items[j].text.strip()
                if ANS_RE.match(sj):
                    zt_end = j
                    ans_start = j + 1
                    break
                if CHAPTER_RE.match(sj) or ZHENTI_RE.match(sj) or PART_OR_END_RE.match(sj):
                    zt_end = j
                    break

            if ans_start is not None:
                for j in range(ans_start, n):
                    sj = items[j].text.strip()
                    if (
                        CHAPTER_RE.match(sj)
                        or SECTION_RE.match(sj)
                        or ZHENTI_RE.match(sj)
                        or PART_OR_END_RE.match(sj)
                    ):
                        ans_end = j
                        break

            zt_parsed, zt_count = parse_zhenti_block(items[zt_start:zt_end], summaries_map)
            ans_parsed = (
                parse_reference_answers(items[ans_start:ans_end])
                if ans_start is not None
                else {}
            )

            pair_stats.append({
                "chapter": current_chapter,
                "section": current_section,
                "chunk": items[i].chunk,
                "line": items[i].line_no,
                "questions_count": zt_count,
                "answers_count": len(ans_parsed),
                "diff": zt_count - len(ans_parsed),
            })

            for qnum in range(1, zt_count + 1):
                qdata = zt_parsed[qnum]
                ans_text, ans_imgs = ans_parsed.get(qnum, ("", []))
                rec_id = f"ch{current_chapter:02d}_{len(chapter_records[current_chapter]) + 1:03d}"
                rule_tags = mapper.get_rule_tags(
                    current_chapter,
                    current_section,
                    qdata["question"],
                    qdata["source_images"],
                    qdata["ocr_image_summaries"],
                )
                flags = run_prechecks(
                    current_chapter,
                    qdata["question"],
                    qdata["source_images"],
                    ans_text,
                )
                chapter_records[current_chapter].append({
                    "id": rec_id,
                    "chapter": current_chapter,
                    "chapter_title": current_chapter_title,
                    "section": current_section,
                    "section_title": current_section_title,
                    "question": qdata["question"],
                    "source_images": qdata["source_images"],
                    "image_captions": qdata["image_captions"],
                    "ocr_image_summaries": qdata["ocr_image_summaries"],
                    "stripped_source_text": qdata["stripped_source_text"],
                    "book_solution_hint": ans_text,
                    "book_solution_images": ans_imgs,
                    "source_chunk": qdata["source_chunk"],
                    "source_pages": qdata["source_pages"],
                    "rule_tags": rule_tags,
                    "ocr_precheck_flags": flags,
                })

            i = ans_end if ans_start is not None else zt_end
            continue

        # Example problem (`例 N` / `【例 10-1】` / `例`)
        if current_chapter > 0 and is_real_example_start(items, i):
            ex_start = i
            sol_start = None
            sol_inline_first_text = ""
            ex_end = n

            # Locate solution start
            j = i + 1
            while j < n:
                sj = items[j].text.strip()
                if SOL_HEAD_RE.match(sj):
                    sol_start = j + 1
                    break
                m_sol_in = SOL_INLINE_RE.match(sj)
                if m_sol_in:
                    sol_start = j
                    sol_inline_first_text = m_sol_in.group(1)
                    break
                j += 1

            # Locate end of solution
            k = sol_start if sol_start is not None else i + 1
            while k < n:
                sk = items[k].text.strip()
                if (
                    CHAPTER_RE.match(sk)
                    or SECTION_RE.match(sk)
                    or ZHENTI_RE.match(sk)
                    or PART_OR_END_RE.match(sk)
                    or PROSE_STOP_RE.match(sk)
                    or LIANYILIAN_ANS_RE.match(sk)
                ):
                    ex_end = k
                    break
                if is_real_example_start(items, k):
                    ex_end = k
                    break
                k += 1

            q_slice_end = (sol_start - 1) if (sol_start is not None and SOL_HEAD_RE.match(items[sol_start - 1].text.strip())) else (sol_start if sol_start is not None else ex_end)
            sol_subhead_items: list[LineItem] = []
            if sol_start is not None and SOL_HEAD_RE.match(items[sol_start - 1].text.strip()):
                p_sub = q_slice_end - 1
                while p_sub > ex_start and not items[p_sub].text.strip():
                    p_sub -= 1
                if p_sub > ex_start and SOL_SUBHEAD_RE.match(items[p_sub].text.strip()):
                    sol_subhead_items = [items[p_sub]]
                    q_slice_end = p_sub

            q_items = items[ex_start:q_slice_end]

            q_text, imgs, caps, sums, pages, stripped = clean_question_and_collect_images(
                q_items, summaries_map, strip_prefix_mode="example"
            )

            if sol_start is not None:
                sol_items = sol_subhead_items + list(items[sol_start:ex_end])
                if sol_inline_first_text:
                    # Replace inline `【解析】...` first line with stripped prefix
                    first_it = sol_items[0]
                    sol_items[0] = LineItem(
                        chunk=first_it.chunk,
                        line_no=first_it.line_no,
                        page=first_it.page,
                        text=sol_inline_first_text,
                    )
                sol_text, sol_imgs = extract_solution_text_and_images(sol_items, is_answer_item=False)
            else:
                sol_text, sol_imgs = "", []

            rec_id = f"ch{current_chapter:02d}_{len(chapter_records[current_chapter]) + 1:03d}"
            rule_tags = mapper.get_rule_tags(
                current_chapter,
                current_section,
                q_text,
                imgs,
                sums,
            )
            flags = run_prechecks(current_chapter, q_text, imgs, sol_text)
            chapter_records[current_chapter].append({
                "id": rec_id,
                "chapter": current_chapter,
                "chapter_title": current_chapter_title,
                "section": current_section,
                "section_title": current_section_title,
                "question": q_text,
                "source_images": imgs,
                "image_captions": caps,
                "ocr_image_summaries": sums,
                "stripped_source_text": stripped,
                "book_solution_hint": sol_text,
                "book_solution_images": sol_imgs,
                "source_chunk": items[ex_start].chunk,
                "source_pages": pages,
                "rule_tags": rule_tags,
                "ocr_precheck_flags": flags,
            })

            i = ex_end
            continue

        i += 1

    # Write ch01_raw.jsonl .. ch40_raw.jsonl
    total_questions = 0
    total_images = 0
    questions_with_images = 0
    stripped_count = 0
    stripped_samples: list[dict[str, Any]] = []
    flag_counter: Counter[str] = Counter()
    flag_ids: dict[str, list[str]] = defaultdict(list)
    chapter_summary: list[dict[str, Any]] = []

    for ch in range(1, 41):
        recs = chapter_records[ch]
        out_path = STAGING_DIR / f"ch{ch:02d}_raw.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for rec in recs:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        ch_imgs = sum(len(r["source_images"]) for r in recs)
        ch_with_imgs = sum(1 for r in recs if r["source_images"])
        total_questions += len(recs)
        total_images += ch_imgs
        questions_with_images += ch_with_imgs

        for r in recs:
            if r["stripped_source_text"]:
                stripped_count += len(r["stripped_source_text"])
                if len(stripped_samples) < 50:
                    stripped_samples.append({
                        "id": r["id"],
                        "stripped": r["stripped_source_text"],
                        "question_tail": r["question"][-60:],
                    })
            for fl in r["ocr_precheck_flags"]:
                flag_counter[fl] += 1
                flag_ids[fl].append(r["id"])

        note = ""
        if len(recs) == 0:
            note = "该章为平面几何公理与基础概念阐述章（点、线、角定义及基本定理证明），原书正文无独立例题与真题重现。"
        elif ch == 40:
            note = "第40章末尾第2组真题重现（15题）的参考答案位于未录入的《下_401》分卷，故该15题带 MISSING_SOLUTION_HINT 标记。"

        chapter_summary.append({
            "chapter": ch,
            "chapter_title": chapters_meta.get(ch, ""),
            "count": len(recs),
            "questions_with_images": ch_with_imgs,
            "total_source_images": ch_imgs,
            "note": note,
        })

    # Equation / table index
    eq_tb_index = build_equation_table_index(all_referenced_images)
    with open(STAGING_DIR / "equation_table_index.json", "w", encoding="utf-8") as f:
        json.dump(eq_tb_index, f, ensure_ascii=False, indent=2)

    eq_tb_counts = {
        chunk: sum(len(v) for v in pages_dict.values())
        for chunk, pages_dict in eq_tb_index.items()
    }

    report = {
        "total_questions": total_questions,
        "total_chapters": 40,
        "zero_question_chapters": [c["chapter"] for c in chapter_summary if c["count"] == 0],
        "total_source_images": total_images,
        "questions_with_images": questions_with_images,
        "missing_image_suspected_count": flag_counter.get("MISSING_IMAGE_SUSPECTED", 0),
        "stripped_source_count": stripped_count,
        "stripped_source_samples": stripped_samples,
        "zhenti_answer_pairs": {
            "total_blocks": len(pair_stats),
            "mismatched_blocks": [p for p in pair_stats if p["diff"] != 0],
            "blocks": pair_stats,
        },
        "ocr_precheck_summary": {
            "counts": dict(flag_counter),
            "ids_by_flag": dict(flag_ids),
        },
        "unreferenced_equation_table_counts": eq_tb_counts,
        "chapters": chapter_summary,
    }

    with open(STAGING_DIR / "extract_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Extraction complete: {total_questions} questions across 40 chapters.")
    print(f"Source images bound: {total_images} (across {questions_with_images} questions).")
    print(f"Competition sources stripped: {stripped_count}")
    print(f"Precheck flags: {dict(flag_counter)}")
    print(f"Unreferenced equation/table crops: {eq_tb_counts}")


if __name__ == "__main__":
    extract_all()
