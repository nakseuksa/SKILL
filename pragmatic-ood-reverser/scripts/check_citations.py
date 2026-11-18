#!/usr/bin/env python3
"""Validate the bundled Markdown routes, load budgets and source section IDs (not claim semantics)."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path('references/source/part4.md')
REQUIRED = (
    'SKILL.md', 'resources/system-map-template.md', 'references/00-provenance.md',
    'references/10-excavation-flow.md', 'references/20-role-anatomy.md', 'references/21-invariant-mining.md',
    'references/30-reverse-lenses.md', 'references/50-java-spring-reverse.md', 'references/51-ts-nextjs-reverse.md',
    'examples/01-onboarding-ts-nextjs.md', 'examples/02-impact-payment-java.md', 'examples/03-deep-audit-spring-god.md',
    'scripts/scan_topology.py',
)
# KiB per stage of the route table. Count linked MD sections (one language at a time),
# including optional routes, but not the common SKILL.md, the script or inspected project source.
STAGE_KIB = {'T / S0': 8, 'S1': 12, 'S2': 20, 'S3': 20, 'S4': 16}
CITATION = re.compile(r'§(\d+(?:\.\d+)*(?:\[\d+\])?)')
LINK = re.compile(r'\]\(([^()\s]+)\)')
HEADING = re.compile(r'^(#{1,6})\s+(.+?)\s*$')
ID = re.compile(r'''^\s*<a\s+id=["']([^"']+)["']\s*>\s*</a>\s*$''')


def sections(text):
    valid, list_section = set(), None
    for line in text.splitlines():
        if line.startswith('## '):
            list_section = None
            chap = re.match(r'^## 第(\d+)章', line)
            sec = re.match(r'^## (\d+(?:\.\d+)+)\s+(.+)', line)
            if chap:
                valid.add(chap[1])
            if sec:
                valid.add(sec[1])
                if sec[2].strip() in ('忠告', '练习'):
                    list_section = sec[1]
        elif list_section:
            item = re.match(r'^(?:\[(\d+)\]|(\d+)\.\s)', line)
            if item:
                valid.add(f'{list_section}[{item[1] or item[2]}]')
    return valid


def visible(text):
    # Preserve line numbers even in HTML comments and fenced examples.
    text = re.sub(r'<!--[\s\S]*?(?:-->|$)', lambda m: '\n' * m[0].count('\n'), text)
    fence = ''
    for line in text.splitlines():
        mark = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if fence:
            if mark and mark[1].startswith(fence) and not line[mark.end():].strip():
                fence = ''
            yield ''
        elif mark:
            fence = mark[1]
            yield ''
        else:
            yield line


def anchor_sections(text):
    """Map actual explicit IDs or heading slugs to their UTF-8 section size."""
    lines = text.splitlines(keepends=True)
    headings, pending, seen_slug = [], [], Counter()
    for i, line in enumerate(visible(text)):
        explicit, h = ID.match(line), HEADING.match(line)
        if explicit:
            pending.append(explicit[1])
        elif h:
            slug = re.sub(r'[^\w\- ]', '', h[2].lower()).replace(' ', '-')
            n = seen_slug[slug]; seen_slug[slug] += 1
            headings.append((i, len(h[1]), pending + [slug if not n else f'{slug}-{n}']))
            pending = []
        elif line.strip():
            pending = []
    sizes = {}
    for j, (i, level, names) in enumerate(headings):
        stop = next((k for k, depth, _ in headings[j + 1:] if depth <= level), len(lines))
        size = len(''.join(lines[i:stop]).encode())
        for name in names:
            sizes[name] = size
    return sizes


def validate(root):
    root = root.resolve()
    errors, loads = [], {}
    for file in (*REQUIRED, SOURCE):
        if not (root / file).is_file():
            errors.append(f'缺少必要文件: {file}')
    if errors:
        return errors, loads, 0
    valid = sections((root / SOURCE).read_text(encoding='utf-8'))
    docs = {root / 'SKILL.md', *root.glob('references/*.md'), *root.glob('examples/*.md'), *root.glob('resources/*.md')}
    texts = {p: p.read_text(encoding='utf-8') for p in docs}
    anchors = {p: anchor_sections(text) for p, text in texts.items()}
    citations = 0
    for path in sorted(docs):
        rel, text = path.relative_to(root), texts[path]
        limit = 80 if rel.parts[0] == 'examples' else 200
        if not text.strip() or len(text.splitlines()) > limit:
            errors.append(f'{rel}: 文档为空或超过 {limit} 行')
        for i, line in enumerate(text.splitlines(), 1):
            for ref in CITATION.findall(line):
                citations += 1
                if ref not in valid:
                    errors.append(f'{rel}:{i}: 无原文条目 §{ref}')
        for i, line in enumerate(visible(text), 1):
            stage = None
            if rel == Path('SKILL.md') and line.startswith('| '):
                label = line.split('|')[1].strip()
                stage = next((s for s in STAGE_KIB if label.startswith(s + ' ')), None)
            sizes = {}
            for link in LINK.findall(re.sub(r'`[^`]*`', '', line)):
                url = urlsplit(link)
                if url.scheme or url.netloc:
                    continue
                dest = (path.parent / unquote(url.path)).resolve() if url.path else path
                anchor = unquote(url.fragment)
                if not dest.is_relative_to(root) or not dest.is_file():
                    errors.append(f'{rel}:{i}: 无效本地路径 {link}'); continue
                if anchor and anchor not in anchors.get(dest, {}):
                    errors.append(f'{rel}:{i}: 找不到标题或锚点 {link}'); continue
                if dest in texts:
                    sizes[(dest, anchor)] = anchors[dest][anchor] if anchor else len(texts[dest].encode())
            if stage:
                def amount(prefix):
                    return sum(n for (p, _), n in sizes.items() if p.name.startswith(prefix))
                java, ts = amount('50-java-'), amount('51-ts-')
                loads[stage] = sum(sizes.values()) - min(java, ts)
                if not sizes or loads[stage] > STAGE_KIB[stage] * 1024:
                    errors.append(f'{stage}: 路由为空或加载体积超预算 {STAGE_KIB[stage]} KiB')
    for stage in STAGE_KIB.keys() - loads.keys():
        errors.append(f'缺少活动路由: {stage}')
    return errors, loads, citations


def main():
    errors, loads, citations = validate(ROOT)
    for stage, n in loads.items():
        print(f'{stage}: {n / 1024:.1f} / {STAGE_KIB[stage]} KiB（路由中的 Markdown 片段）')
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f'通过：{citations} 处原文章节编号、本地链接/锚点、行数和阶段预算。未验证引述语义。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
