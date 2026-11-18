#!/usr/bin/env python3
"""离线校验包内文件、章节编号、显式锚点及按节读取的预算，不判断引用语义。"""
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'references/source/part4.md'
TEMPLATE = 'resources/blueprint-template.md'
SKILL_LIMIT = 12 * 1024
SECTION_LIMIT = 4 * 1024
A3_LIMIT = 8 * 1024  # 活动卡 + 一张试金石 + 一个原语或权衡树
LINES = {
    'SKILL.md': 200, TEMPLATE: 200,
    **{f'references/{name}.md': limit for name, limit in (
        ('00-provenance', 60), ('10-activities', 300), ('20-primitives', 350),
        ('21-class-kinds', 150), ('30-litmus', 250), ('31-tradeoffs', 200),
        ('50-java17', 250), ('51-ts-server', 250), ('60-checklists', 200))},
    **{f'examples/{name}.md': 80 for name in ('01-light-ts-nextjs', '02-litmus-vipuser-java',
       '03-sealed-payment-java17', '04-refactor-spring-monolith', '05-resume')},
}
SECTION_GROUPS = {
    'references/10-activities.md': r'^### A3\b',
    'references/30-litmus.md': r'^## L\d+\b',
    'references/20-primitives.md': r'^### P\d+\b',
    'references/31-tradeoffs.md': r'^## 权衡',
}
CITATION = re.compile(r'§(\d+(?:\.\d+)*(?:\[\d+\])?)')
HEADING = re.compile(r'^(#{1,6}) +(.+?)\s*$')
LINK = re.compile(r'\[[^\]\n]*\]\(([^\s()]+)\)')


def valid_sections(source):
    valid = set()
    group = None
    for line in source.splitlines():
        if line.startswith('## '):
            group = None
            if m := re.match(r'^## (?:第(\d+)章|(\d+(?:\.\d+)+))', line):
                section = m[1] or m[2]
                valid.add(section)
                if line.split()[-1] in ('忠告', '练习'):
                    group = section
        elif group and (m := re.match(r'^(?:\[(\d+)\]|(\d+)\.)', line)):
            valid.add(f'{group}[{m[1] or m[2]}]')
    return valid


def prose(text):
    """Yield actual Markdown lines outside fenced code, with zero-based offsets."""
    fence = ''
    for i, line in enumerate(text.splitlines()):
        if fence:
            if re.fullmatch(r' {0,3}' + fence[0] + '{' + str(len(fence)) + r',}\s*', line):
                fence = ''
        elif m := re.match(r'^ {0,3}(`{3,}|~{3,})', line):
            fence = m[1]
        else:
            yield i, line


def anchors(text):
    ids = set()
    slugs = set()
    for _, line in prose(text):
        ids.update(re.findall(r'^\s*<a\s+id="([^"<>]+)"\s*>\s*</a>\s*$', line))
        if m := HEADING.match(line):
            title = m[2]
            if key := re.search(r'\{#([^ }]+)\}\s*$', title):
                ids.add(key[1])
                title = title[:key.start()]
            # Simple ATX headings used by this package. Use explicit HTML IDs for stable routing.
            base = re.sub(r'[^\w\- ]', '', title.strip().lower()).replace(' ', '-')
            if base:
                slug, n = base, 0
                while slug in slugs:
                    n += 1
                    slug = f'{base}-{n}'
                slugs.add(slug)
    return ids | slugs


def section_sizes(text, pattern):
    lines = text.splitlines(keepends=True)
    heads = [(i, line, len(m[1])) for i, line in prose(text) if (m := HEADING.match(line))]
    for n, (i, name, level) in enumerate(heads):
        if re.match(pattern, name):
            end = next((j for j, _, depth in heads[n+1:] if depth <= level), len(lines))
            yield name, len(''.join(lines[i:end]).encode())


def validate(root):
    root = root.resolve()
    errors = []
    for rel in (*LINES, SOURCE):
        if not (root / rel).is_file():
            errors.append(f'{rel}: 缺少必需文件')
    if errors:
        return errors
    valid = valid_sections((root / SOURCE).read_text(encoding='utf-8'))
    docs = {p.resolve(): p.read_text(encoding='utf-8') for p in root.rglob('*.md')
            if root / 'references/source' not in p.parents}
    ids = {p: anchors(text) for p, text in docs.items()}
    citations = 0
    peaks = {}
    for p, text in docs.items():
        rel = p.relative_to(root).as_posix()
        if rel in LINES and (not text.strip() or len(text.splitlines()) > LINES[rel]):
            errors.append(f'{rel}: 文件为空或超过 {LINES[rel]} 行')
        if rel == 'SKILL.md' and len(text.encode()) > SKILL_LIMIT:
            errors.append(f'{rel}: 超过 {SKILL_LIMIT} 字节')
        if rel in SECTION_GROUPS:
            blocks = list(section_sizes(text, SECTION_GROUPS[rel]))
            peaks[rel] = max((n for _, n in blocks), default=0)
            if not blocks:
                errors.append(f'{rel}: 未找到预算所指的标题')
            for name, n in blocks:
                if n > SECTION_LIMIT:
                    errors.append(f'{rel}: {name} 为 {n} 字节，超过 {SECTION_LIMIT}')
        for i, line in enumerate(text.splitlines(), 1):
            for sec in CITATION.findall(line):
                citations += 1
                if sec not in valid:
                    errors.append(f'{rel}:{i}: 未找到原文章节 §{sec}')
        for i, line in prose(text):
            for link in LINK.findall(re.sub(r'`[^`]*`', '', line)):
                url = urlsplit(link)
                if url.scheme or url.netloc:
                    continue  # 外链不联网检查
                target = (p.parent / unquote(url.path)).resolve() if url.path else p
                if not target.is_relative_to(root) or not target.is_file():
                    errors.append(f'{rel}:{i+1}: 包内路径无效 {link}')
                elif url.fragment and unquote(url.fragment) not in ids.get(target, set()):
                    errors.append(f'{rel}:{i+1}: 找不到标题或显式锚点 {link}')

    activity, litmus, primitive, tradeoff = (peaks[k] for k in SECTION_GROUPS)
    a3 = activity + litmus + max(primitive, tradeoff)
    if a3 > A3_LIMIT:
        errors.append(f'A3 路径 {a3} 字节，超过 {A3_LIMIT}')
    print(f'{len(docs)} 份文档，{citations} 处节号；A3 关系取舍参考路径上界 '
          f'{a3}/{A3_LIMIT} 字节（不含主文件或用户数据），最大选读小节 {max(peaks.values())} 字节。')
    return errors


if __name__ == '__main__':
    issues = validate(ROOT)
    for issue in issues:
        print(issue, file=sys.stderr)
    sys.exit(bool(issues))
