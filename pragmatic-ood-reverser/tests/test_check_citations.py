from pathlib import Path
import shutil
import tempfile
import unittest

from scripts import check_citations as check


class ValidatorTests(unittest.TestCase):
    def test_budgeted_routes_and_real_citations(self):
        errors, loads, citations = check.validate(check.ROOT)
        self.assertEqual(errors, [])
        self.assertEqual(set(loads), set(check.STAGE_KIB))
        self.assertGreater(citations, 0)

    def test_items_come_from_source_not_numeric_ranges(self):
        text = '## 23.7 忠告\n[1] yes\n[3] yes\n## 24.1 概述\n[2] no\n## 25.10 练习\n19. yes'
        self.assertEqual(check.sections(text), {'23.7', '23.7[1]', '23.7[3]', '24.1', '25.10', '25.10[19]'})

    def test_anchors_require_real_headings_not_mentions(self):
        text = '# Title\nmentions #foo\n```\n# fake\n```\n<!-- <a id="bad"></a> -->\n<a id="bar"></a>\n## B\nvalue\n## C\n'
        anchors = check.anchor_sections(text)
        self.assertEqual(set(anchors), {'title', 'bar', 'b', 'c'})
        self.assertEqual(anchors['bar'], len('## B\nvalue\n'))

    def test_negative_validation_in_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in (*check.REQUIRED, check.SOURCE):
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(check.ROOT / name, dest)
            lenses = root / 'references/30-reverse-lenses.md'
            lenses.write_text(lenses.read_text().replace('id="RL1-RL5"', 'id="moved"') + '\n' + '大' * 9000)
            skill = root / 'SKILL.md'
            skill.write_text(skill.read_text() + '\n[broken](./not-there) §23.7[999]\n')
            errors = '\n'.join(check.validate(root)[0])
            for msg in ('找不到标题或锚点', '无效本地路径', '无原文条目', 'S3: 路由为空或加载体积超预算'):
                self.assertIn(msg, errors)
            lenses.unlink()
            self.assertIn('缺少必要文件', check.validate(root)[0][0])

    def test_example_evidence_locations_exist_in_fixtures(self):
        import re
        for example in (check.ROOT / 'examples').glob('*.md'):
            text = example.read_text()
            root = check.ROOT / re.search(r'`(examples/fixtures/(?:java|ts))`', text)[1]
            citations = re.findall(r'`([\w./-]+\.(?:java|ts)):L(\d+)(?:-L(\d+))?`', text)
            self.assertTrue(citations, example.name)
            for path, first, last in citations:
                with self.subTest(example=example.name, path=path, first=first):
                    self.assertLessEqual(1, int(first))
                    self.assertLessEqual(int(first), int(last or first))
                    self.assertLessEqual(int(last or first), len((root/path).read_text().splitlines()))
