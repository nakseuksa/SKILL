#!/usr/bin/env python3
"""Read-only S0 inventory. Python 3.9+; Java / server TypeScript only, no compiler."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys

IGNORE = {"node_modules", "target", "build", "dist", "out", "coverage", "__pycache__", "__tests__"}
# Keep strings atomic and discard comments, preserving original source line numbers.
# This is a lexer for import declarations, not a TS/Java parser.
TOKEN = re.compile(r'''//[^\n]*|/\*[\s\S]*?(?:\*/|$)|"""[\s\S]*?(?:"""|$)|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|[\w$]+|[^\s]''')


def tokens(text):
    line, end = 1, 0
    for m in TOKEN.finditer(text):
        line += text.count("\n", end, m.start())
        val = m.group()
        if not val.startswith(("//", "/*")):
            yield val, line
        line += val.count("\n")
        end = m.end()


@dataclass(frozen=True)
class Ref:
    spec: str
    line: int
    kind: str  # java, static, value (candidate), type, inline-type, deferred


@dataclass
class Source:
    path: Path
    loc: int
    group: str
    refs: list[Ref]
    signals: Counter
    shapes: list[tuple[int, str]]


def string_token(val):
    return len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]


def ts_refs(t):
    v = [s for s, _ in t] + [""] * 4
    for i, (word, line) in enumerate(t):
        if word not in ("import", "export", "require") or (i and v[i-1] == "."):
            continue
        j = i + 1
        if word in ("require", "import") and v[j] == "(":
            yield Ref(v[j+1][1:-1] if string_token(v[j+1]) else "<表达式>", line, "deferred")
            continue
        if word == "require":
            continue
        if word == "import" and string_token(v[j]):
            yield Ref(v[j][1:-1], line, "value")
            continue
        only_type = v[j] == "type" and v[j+1] not in ("from", ",")
        j += int(only_type)
        default_binding = word == "import" and re.fullmatch(r"[\w$]+", v[j]) is not None
        kind = "type" if only_type else "value"
        if default_binding:
            j += 1  # default binding
            if v[j] == ",":
                j += 1
        if v[j] == "*":
            j += 1
            if v[j] == "as":
                j += 2
        elif v[j] == "{":
            j += 1
            start = j
            type_flags = []
            while v[j] and v[j] not in ("}", ";", "{"):
                if v[j] == ",":
                    type_flags.append(v[start] == "type" and start + 1 < j and v[start+1] != "as")
                    start = j + 1
                j += 1
            if v[j] != "}":
                continue
            if j > start:
                type_flags.append(v[start] == "type" and start + 1 < j and v[start+1] != "as")
            # With verbatimModuleSyntax an empty side-effect import may survive.
            if not only_type and not default_binding and type_flags and all(type_flags):
                kind = "inline-type"
            j += 1
        if v[j] == "from" and string_token(v[j+1]):
            yield Ref(v[j+1][1:-1], line, kind)


def java_header(t):
    pkg, refs = "(default)", []
    for i, (word, line) in enumerate(t):
        if word not in ("import", "package"):
            continue
        j = i + 1
        static = j < len(t) and t[j][0] == "static"
        j += int(static)
        parts = []
        while j < len(t) and (t[j][0] in (".", "*") or re.fullmatch(r"[\w$]+", t[j][0])):
            parts.append(t[j][0]); j += 1
        if parts and j < len(t) and t[j][0] == ";":
            if word == "package":
                pkg = "".join(parts)
            else:
                refs.append(Ref("".join(parts), line, "static" if static else "java"))
    return pkg, refs


def discover(root):
    groups = {"java17": [], "ts-server": []}
    def on_error(exc):
        raise exc  # Never report a skipped unreadable directory as scanned.
    for folder, dirs, names in os.walk(root, onerror=on_error):
        dirs[:] = sorted(d for d in dirs if d not in IGNORE and not d.startswith("."))
        for name in sorted(names):
            p = Path(folder, name).relative_to(root)
            if (root / p).is_symlink():
                continue
            if name.endswith(".java") and not name.endswith("Test.java") and "test" not in p.parts[:-1]:
                groups['java17'].append(p)
            elif name.endswith((".ts", ".tsx")) and not name.endswith(".d.ts") and not re.search(r"\.(?:spec|test)\.", name):
                groups['ts-server'].append(p)
    return groups


def shape_hints(t, lang, path):
    """Cheap source locators; counts are lexical candidates, not parsed declarations."""
    signals, hints = Counter(), []
    words = [word for word, _ in t] + [""] * 3
    depth, public = 0, False
    if lang == "ts-server" and path.stem == "index":
        signals["index 入口候选"] += 1
    for i, (word, line) in enumerate(t):
        if lang == "java17":
            if depth == 0:
                if word == "public":
                    public = True
                if word in ("class", "enum", "interface", "record") and re.fullmatch(r"[\w$]+", words[i+1]):
                    signals["公开顶层类型" if public else "包内顶层类型"] += 1
                if word in ("{", ";"):
                    public = False
            if word == "sealed" and not (i and words[i-1] == "-"):
                hints.append((line, f"sealed {words[i+1]} {words[i+2]}"))
        elif word == "export":
            signals["export 标记"] += 1
        elif word in ("kind", "type") and words[i+1] == ":" and string_token(words[i+2]):
            hints.append((line, f"判别字段候选 {word}: {words[i+2]}"))
        if word == "extends":
            hints.append((line, f"extends {words[i+1]}（含泛型约束）"))
        depth += int(word == "{") - int(word == "}")
    return signals, hints


def ts_group(path):
    """Keep nested project roots distinct when scanning a mixed repository."""
    dirs = path.parts[:-1]
    split = dirs.index("src") if "src" in dirs else -1
    prefix, local = dirs[:max(split, 0)], dirs[split+1:]
    depth = 2 if local[:1] in (("modules",), ("features",), ("domains",), ("packages",)) else 1
    return "/".join(prefix + local[:depth]) or "(root)"


def source(root, path, lang):
    text = (root / path).read_text(encoding="utf-8-sig")
    t = list(tokens(text))
    signals, shapes = shape_hints(t, lang, path)
    if lang == "java17":
        group, refs = java_header(t)
    else:
        group = ts_group(path)
        refs = list(ts_refs(t))
    return Source(path, len(text.splitlines()), group, refs, signals, shapes)


def java_resolver(units):
    index = defaultdict(list)
    packages = set()
    for u in units:
        pkg = u.group
        index[(pkg + "." if pkg != "(default)" else "") + u.path.stem].append(u.path)
        packages.add(pkg)
    # Infer physical components from the common package prefix; not business boundaries.
    chunks = [p.split(".") for p in packages if p != "(default)"]
    n = 0
    for col in zip(*chunks):
        if len(set(col)) != 1:
            break
        n += 1
    for u in units:
        tail = u.group.split(".")[n:]
        u.group = tail[0] if tail else u.group

    def resolve(u, ref):
        name = ref.spec.rsplit(".", 1)[0] if ref.kind == "static" else ref.spec
        if name.endswith(".*"):
            return None, "通配包导入（未展开）"
        while name:
            if name in index:
                hits = index[name]
                return (hits[0], "") if len(hits) == 1 else (None, "多个同名候选")
            name = name.rpartition(".")[0]
        return None, "外部或未解析的类型"
    return resolve


def ts_resolver(root, units):
    known = {u.path for u in units}
    configs = {}

    def config(folder):
        if folder not in configs:
            file = folder / "tsconfig.json"
            if not file.is_file():
                configs[folder] = config(folder.parent) if folder != root else (None, {})
            else:
                # Never guess @/ or ~/ mappings; unsupported JSONC/extends remain unresolved.
                try:
                    cfg = json.loads(file.read_text(encoding="utf-8-sig"))
                    opts = cfg["compilerOptions"]
                    base = folder / opts.get("baseUrl", ".")
                    paths = opts.get("paths", {}) if not cfg.get("extends") else {}
                    configs[folder] = base, paths if isinstance(paths, dict) else {}
                except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError):
                    configs[folder] = None, {}
        return configs[folder]

    def match(p):
        try:
            rel = p.resolve().relative_to(root)
        except (ValueError, OSError, RuntimeError):
            return None
        if rel in known:
            return rel
        stem = rel.with_suffix("") if rel.suffix in (".js", ".jsx") else rel
        return next((f for f in (Path(str(stem) + ".ts"), Path(str(stem) + ".tsx"),
                                 rel / "index.ts", rel / "index.tsx") if f in known), None)

    def resolve(u, ref):
        if ref.kind == "deferred":
            return None, "动态/require 引用（未纳入静态图）"
        if ref.spec in (".", "..") or ref.spec.startswith(("./", "../")):
            return match(root / u.path.parent / ref.spec), "相对路径未命中扫描范围"
        base, paths = config(root / u.path.parent)
        # TS picks the most specific pattern. Keep fallback order within that mapping.
        for key in sorted(paths, key=lambda k: ("*" in k, -len(k.partition("*")[0]))):
            pattern = re.escape(key).replace(r"\*", "(.*)", 1)
            m = re.fullmatch(pattern, ref.spec)
            if not m:
                continue
            values = paths[key]
            for val in values if isinstance(values, list) else []:
                if isinstance(val, str):
                    target = match(base / val.replace("*", m.group(1) if m.groups() else ""))
                    if target is not None:
                        return target, ""
            return None, "别名未命中扫描范围"
        return None, "外部包或未解析别名"
    return resolve


def components(graph):
    """Iterative Kosaraju: cyclic SCC member sets, never invented witness paths."""
    reverse = defaultdict(set)
    for a, neighbors in graph.items():
        for b in neighbors:
            reverse[b].add(a)
    finished, seen = [], set()
    for start in sorted(set(graph) | set(reverse)):
        if start in seen:
            continue
        seen.add(start)
        stack = [(start, iter(sorted(graph.get(start, ()))))]
        while stack:
            v, it = stack[-1]
            w = next(it, None)
            if w is None:
                finished.append(v); stack.pop()
            elif w not in seen:
                seen.add(w); stack.append((w, iter(sorted(graph.get(w, ())))))
    seen.clear()
    found = []
    for start in reversed(finished):
        if start in seen:
            continue
        todo, group = [start], {start}
        seen.add(start)
        while todo:
            for w in reverse[todo.pop()]:
                if w not in seen:
                    seen.add(w); group.add(w); todo.append(w)
        if len(group) > 1:
            found.append(tuple(sorted(group)))
    return sorted(found)


def report(root, lang, paths):
    units = [source(root, p, lang) for p in sorted(paths)]
    resolve = java_resolver(units) if lang == "java17" else ts_resolver(root, units)
    by_path = {u.path: u for u in units}
    files_in, files_out = defaultdict(set), defaultdict(set)
    evidence, unknown, counts = {}, [], Counter()
    for u in units:
        for ref in u.refs:
            dest, note = resolve(u, ref)
            if dest is None:
                unknown.append((u.path, ref, note)); continue
            counts[ref.kind] += 1
            if dest == u.path:
                continue
            files_in[dest].add(u.path); files_out[u.path].add(dest)
            other = by_path[dest].group
            if u.group != other:
                evidence.setdefault((u.group, other, ref.kind), (u.path, ref.line, dest))

    print(f"# S0 静态导入快照 `{lang}` · 根目录 `{root}`")
    print(f"{len(units)} 个文件 · {sum(u.loc for u in units)} 行 · 已解析导入声明 {sum(counts.values())} · 未纳入图 {len(unknown)}（仅统计识别到的引用）。路径相对于扫描根。")
    print("\n## 物理分组（不是业务边界）\n| 分组 | 文件 | 行数 | 形态线索（词法计数） |\n|---|---:|---:|---|")
    groups = defaultdict(list)
    for u in units:
        groups[u.group].append(u)
    for name, members in sorted(groups.items()):
        signals = sum((u.signals for u in members), Counter())
        hint = ", ".join(f"{s}: {n}" for s, n in sorted(signals.items())) or "—"
        print(f"| `{name}` | {len(members)} | {sum(u.loc for u in members)} | {hint} |")

    if len(groups) == 1:
        print("只有一个物理分组；本报告不判断分组内的文件环。")
    views = [("Java 显式导入", {"java", "static"})] if lang == "java17" else [
        ("TS 值候选图（非运行时证明）", {"value"}), ("TS 声明图（含类型边）", {"value", "type", "inline-type"})]
    for title, kinds in views:
        graph = defaultdict(set)
        for a, b, kind in evidence:
            if kind in kinds:
                graph[a].add(b)
        print(f"\n## {title}")
        sccs = components(graph)
        if not sccs:
            print("已解析的跨组边中未发现环。")
        for scc in sccs:
            print("- 强连通分量（成员集合，不代表边序）：" + ", ".join(scc))
    print("\n## 已解析跨组边（每种方向/种类一处证据）")
    for (a, b, kind), (p, line, dest) in sorted(evidence.items()):
        print(f"- {a} → {b} [{kind}] `{p}:L{line}` → `{dest}`")
    if not evidence:
        print("无已解析跨组边。")
    print("\n## 热点候选（按不同源/目标文件去重，含类型引用；不是风险评级）")
    for title, metric in [("Fan-in", lambda u: len(files_in[u.path])), ("Fan-out", lambda u: len(files_out[u.path])), ("LOC", lambda u: u.loc)]:
        top = sorted(units, key=lambda u: (-metric(u), u.path))[:8]
        print(f"- {title} Top 8：" + ("、".join(f"`{u.path}` ({metric(u)})" for u in top if metric(u)) or "无"))
    hints = [(u.path, line, hint) for u in units for line, hint in u.shapes]
    print(f"\n## 继承与变体线索（词法候选 {len(hints)} 处，最多展示 8 处）")
    for p, line, hint in hints[:8]:
        print(f"- `{p}:L{line}` {hint}")
    print("\n## 覆盖边界")
    for reason, n in sorted(Counter(reason for _, _, reason in unknown).items()):
        print(f"- {reason}：{n}")
    for p, ref, note in unknown[:20]:
        print(f"  - `{p}:L{ref.line}` `{ref.spec}` — {note}")
    if len(unknown) > 20:
        print(f"  - 其余 {len(unknown)-20} 条未展开；缩小扫描根以复核焦点。")
    if lang == "java17":
        print("按文件名解析显式类型/静态导入；同包隐式使用、全限定名使用、注入/反射/事件均不在图中。")
    else:
        print("只识别静态 import/export、相对路径和扫描根内严格 JSON tsconfig 的简单 paths；不模拟编译、JSONC/extends、workspace 或动态装载。import/export type 擦除；只有内联 type 的声明标为 inline-type，仅列入声明图，编译配置可能保留空导入的副作用。其他为值边候选，不等于编译产物。TSX 不等于服务端，须人工核对边界。")
    print("排除常见测试、隐藏目录、构建产物及链接文件；词法近似不能覆盖所有语法，分组环不证明文件级调用环。")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target_dir", type=Path)
    parser.add_argument("--language", choices=("java17", "ts-server"), help="只扫描指定语言")
    args = parser.parse_args(argv)
    root = args.target_dir.resolve()
    if not root.is_dir():
        parser.error(f"不是目录: {root}")
    try:
        groups = discover(root)
        chosen = [k for k, paths in groups.items() if paths and args.language in (None, k)]
        if not chosen:
            print("未找到范围内的源文件；无拓扑结论。", file=sys.stderr)
            return 1
        if all(groups.values()):
            print("混合目录；" + (f"按参数仅扫描 {args.language}。" if args.language else "分语言报告，不推断跨语言边。"))
        for lang in chosen:
            report(root, lang, groups[lang])
    except (OSError, UnicodeError) as exc:
        print(f"扫描不完整（无法读取）：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
