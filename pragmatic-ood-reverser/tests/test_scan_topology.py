from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts import scan_topology as scan


class TopologyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def put(self, path, text):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')

    def report(self, *args, status=0, root=None):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            code = scan.main([str(root or self.root), *args])
        self.assertEqual(code, status, out.getvalue())
        return out.getvalue()

    def test_pure_type_cycle_is_not_a_value_cycle_and_no_write(self):
        self.put('a/a.ts', "import type { B } from '../b/b';\nexport interface A { b: B }")
        self.put('b/b.ts', "export type { A } from '../a/a';\nexport interface B {}")
        def snapshot():
            return {p.relative_to(self.root): (p.read_bytes(), p.stat().st_mtime_ns) if p.is_file() else None
                    for p in self.root.rglob('*')}
        before = snapshot()
        text = self.report()
        value, declaration = text.split('## TS 声明图')
        self.assertNotIn('强连通分量', value)
        self.assertIn('强连通分量', declaration)
        self.assertIn('[type] `a/a.ts:L1`', text)
        self.assertEqual(before, snapshot())

    def test_witnesses_are_real_edges_and_degrees_are_unique_files(self):
        self.put('a/main.ts', "// comment\nimport '../b';\nexport { run } from '../b/index';")
        self.put('b/index.ts', "export { run } from '../c/run.task.js';")
        self.put('c/run.task.ts', "import '../a/main';\nexport function run() {}")
        text = self.report()
        self.assertEqual(text, self.report())
        self.assertIn('成员集合，不代表边序）：a, b, c', text)
        for edge in ('a → b [value] `a/main.ts:L2`', 'b → c [value] `b/index.ts:L1`', 'c → a [value] `c/run.task.ts:L1`'):
            self.assertIn(edge, text)
        self.assertNotIn('a → c', text)
        self.assertIn('`b/index.ts` (1)', text.split('Fan-in Top 8：')[1].splitlines()[0])

    def test_unmapped_alias_and_dynamic_edges_not_silent(self):
        self.put('src/a/a.ts', '/* a\n * b */\nimport { b } from "@app/b/b";\nimport("./late");')
        self.put('src/b/b.ts', 'import { a } from "@app/a/a";')
        text = self.report()
        self.assertIn('未纳入图 3', text)
        self.assertIn('`src/a/a.ts:L3` `@app/b/b`', text)
        self.assertIn('动态/require', text)
        self.assertNotIn('严格', text.split('## 覆盖边界')[0])
        self.assertIn('已解析的跨组边中未发现环', text)

    def test_aliases_use_config_not_prefix_guess(self):
        self.put('src/a/a.ts', 'import { b } from "@app/b/b";')
        self.put('src/b/b.ts', 'import { a } from "@app/a/a";')
        self.put('tsconfig.json', json.dumps({'compilerOptions': {'baseUrl': '.', 'paths': {'@app/*': ['src/*']}}}))
        text = self.report()
        self.assertIn('强连通分量', text)
        self.assertIn('未纳入图 0', text)
        self.put('tsconfig.json', '{ /* JSONC unsupported */ }')
        self.assertIn('未纳入图 2', self.report())

    def test_comments_strings_multiline_and_mixed_imports(self):
        text = '''// import 'x';
        const s = "import 'y'";
        /* import 'z' */ import {
            type T, v as val
        } from './ok';
        export type * from './only';
        export { type A } from './inline';'''
        refs = list(scan.ts_refs(list(scan.tokens(text))))
        self.assertEqual([(r.spec, r.kind, r.line) for r in refs], [('./ok', 'value', 3), ('./only', 'type', 6), ('./inline', 'inline-type', 7)])

    def test_inline_type_only_mixed_and_default_bindings(self):
        src = """import {type A, type B as C,} from './x';
        import {type as Alias} from './y';
        import Default, {type A} from './z';
        import {} from './side-effect';"""
        self.assertEqual([r.kind for r in scan.ts_refs(list(scan.tokens(src)))],
                         ['inline-type', 'value', 'value', 'value'])

    def test_java_explicit_static_unresolved_and_implicit_bounds(self):
        self.put('a/A.java', 'package demo.a;\nimport demo.b.B;\nimport static demo.b.B.any;\nimport demo.b.*;\npublic class A {}')
        self.put('b/B.java', 'package demo.b;\nimport demo.a.A;\npublic class B {}')
        self.put('a/FooTest.java', 'package demo.a;')
        text = self.report()
        self.assertIn('2 个文件', text)
        self.assertIn('a → b [static] `a/A.java:L3`', text)
        self.assertIn('b → a [java] `b/B.java:L2`', text)
        self.assertIn('通配包导入', text)
        self.assertIn('同包隐式使用', text)

    def test_empty_mixed_and_language_filter(self):
        self.put('ignored.py', 'pass')
        self.assertIn('无拓扑结论', self.report(status=1))
        self.put('A.java', 'class A {}')
        self.put('a.ts', 'export const a = 1;')
        mixed = self.report()
        self.assertIn('分语言报告', mixed)
        self.assertEqual(mixed.count('# S0 静态导入快照'), 2)
        java = self.report('--language', 'java17')
        self.assertEqual(java.count('# S0 静态导入快照'), 1)
        self.assertNotIn('TS 值候选图', java)

    def test_nested_mixed_fixture_preserves_ts_modules(self):
        root = Path(__file__).resolve().parents[1] / 'examples/fixtures'
        text = self.report(root=root)
        self.assertIn('混合目录', text)
        self.assertIn('ts/modules/billing → ts/modules/ordering [type]', text)
        self.assertIn('成员集合，不代表边序）：ts/modules/billing, ts/modules/ordering', text)
        self.assertIn('payment → order [java]', text)

    def test_deep_graph_without_python_recursion(self):
        graph = {str(i): {str(i+1)} for i in range(2000)}
        self.assertEqual(scan.components(graph), [])
        graph['2000'] = {'1999'}
        self.assertEqual(scan.components(graph), [('1999', '2000')])
