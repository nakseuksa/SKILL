"""离线回归：验证的是打包规则，不是模型的实际对话表现。"""
import contextlib
from io import StringIO
from pathlib import Path
from shutil import copytree, ignore_patterns
from tempfile import TemporaryDirectory
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from check_citations import valid_sections, validate


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = copytree(ROOT, Path(tmp.name) / 'skill',
                             ignore=ignore_patterns('.git', '__pycache__', 'node_modules'))

    def issues(self):
        with contextlib.redirect_stdout(StringIO()):
            return validate(self.root)

    def append(self, file, content):
        with (self.root / file).open('a', encoding='utf-8') as f:
            f.write(content)

    def test_shipped_package(self):
        self.assertEqual(self.issues(), [])

    def test_body_word_or_code_anchor_not_a_target(self):
        self.append('SKILL.md', '\n正文词\n```html\n<a id="fake"></a>\n```\n[x](#正文词) [y](#fake)\n')
        self.assertEqual(sum('找不到标题或显式锚点' in e for e in self.issues()), 2)

    def test_real_heading_and_explicit_id(self):
        self.append('SKILL.md', '\n## Case Review\n<a id="review"></a>\n[x](#case-review) [y](#review)\n')
        self.assertEqual(self.issues(), [])

    def test_example_path_is_checked_relative_to_its_own_file(self):
        self.append('examples/05-resume.md', '\n[x](../does-not-exist.md)\n')
        self.assertTrue(any('包内路径无效' in e for e in self.issues()))

    def test_single_section_over_budget(self):
        self.append('references/30-litmus.md', '长' * 1500)
        self.assertTrue(any('L10' in e and '超过' in e for e in self.issues()))

    def test_combined_route_over_budget(self):
        for rel, title in [('30-litmus', '## L99'), ('31-tradeoffs', '## 权衡五'), ('10-activities', '### A3 extra')]:
            self.append(f'references/{rel}.md', f'\n{title}\n' + 'x' * 3000)
        issues = self.issues()
        self.assertTrue(any('A3 路径' in e for e in issues))
        self.assertFalse(any('超过 4096' in e for e in issues))

    def test_missing_required_file(self):
        (self.root / 'examples/05-resume.md').unlink()
        self.assertTrue(any('缺少必需文件' in e for e in self.issues()))

    def test_real_numbered_items_not_ranges(self):
        sections = valid_sections('## 23.7 忠告\n[1] ok\n[3] ok\n## 23.8 Next\n[4] unrelated')
        self.assertEqual(sections, {'23.7', '23.8', '23.7[1]', '23.7[3]'})

    def test_bad_citation(self):
        self.append('examples/04-refactor-spring-monolith.md', '\n[§23.7[999]]\n')
        self.assertTrue(any('§23.7[999]' in e for e in self.issues()))

    def test_template_is_blank(self):
        text = (self.root / 'resources/blueprint-template.md').read_text(encoding='utf-8')
        self.assertNotRegex(text, r'\b[DAQ]-\d+')
        self.assertNotRegex(text, r'updated: \d{4}-\d\d-\d\d')
        for n in range(16):
            self.assertEqual(text.count(f'\n## {n}. '), 1)


if __name__ == '__main__':
    unittest.main()
