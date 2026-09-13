"""Wiki routing and rendering checks; no network or real output directory."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generate


class WikiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.wiki = self.root / 'content' / 'wiki'
        self.wiki.mkdir(parents=True)
        self.output = self.root / 'public'
        self.patches = patch.multiple(generate, WIKI_DIR=self.wiki,
                                      OUTPUT_DIR=self.output, BASE_PATH='')
        self.patches.start()
        self.addCleanup(self.patches.stop)
        self.write('index.md', '---\ntitle: Wiki\n---\n[ROMs](p6/roms.md)')
        self.write('p6/roms.md', '---\ntitle: ROMs\n---\n[Home](../index.md)')

    def write(self, name, text):
        path = self.wiki / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def test_nested_pages_and_index_urls(self):
        self.write('p6/index.md', 'P6')
        pages = generate.collect_wiki_pages()
        self.assertEqual(pages['index.md']['url'], '/wiki/')
        self.assertEqual(pages['p6/index.md']['url'], '/wiki/p6/')
        self.assertEqual(pages['p6/roms.md']['url'], '/wiki/p6/roms/')
        self.assertEqual(generate.resolve_wiki_link('../index.md#p6',
                         'p6/roms.md', pages), '/wiki/#p6')
        self.assertEqual(generate.resolve_wiki_link('/wiki/p6/roms/#details',
                         'index.md', pages), '/wiki/p6/roms/#details')

    def test_markdown_links_images_reference_links_and_code(self):
        self.write('p6/photo.jpg', 'image fixture')
        self.write('p6/other note.md', '---\ntitle: Other\n---')
        pages = generate.collect_wiki_pages()
        body = ('[Other][ref]\n\n[ref]: other%20note.md?q=1#details\n\n'
                '![Photo](photo.jpg)\n\n`[literal](missing.md)`\n\n'
                '[Outside](https://example.com/file.md)\n\n'
                '[Local](#details)\n\n[CDN](//example.com/file.md)')
        with patch.object(generate, 'BASE_PATH', '/preview'):
            html = generate.render_markdown(body, link_resolver=lambda u:
                generate.resolve_wiki_link(u, 'p6/roms.md', pages))
        self.assertIn('href="/preview/wiki/p6/other%20note/?q=1#details"', html)
        self.assertIn('src="/preview/wiki/p6/photo.jpg"', html)
        self.assertIn('<code>[literal](missing.md)</code>', html)
        self.assertIn('href="https://example.com/file.md"', html)
        self.assertIn('href="//example.com/file.md"', html)
        self.assertIn('href="#details"', html)

    def test_missing_draft_and_escaping_targets_fail(self):
        self.write('draft.md', '---\ndraft: true\n---\nPrivate draft')
        pages = generate.collect_wiki_pages()
        self.assertNotIn('draft.md', pages)
        for link in ['missing.md', 'draft.md', 'missing.jpg', '../../secret.md']:
            with self.subTest(link=link), self.assertRaises(ValueError):
                generate.resolve_wiki_link(link, 'index.md', pages)

    def test_colliding_urls_fail(self):
        self.write('p6/roms/index.md', 'Conflicting page')
        with self.assertRaisesRegex(ValueError, 'Duplicate wiki URL'):
            generate.collect_wiki_pages()

    def test_missing_home_fails(self):
        (self.wiki / 'index.md').unlink()
        with self.assertRaisesRegex(ValueError, 'requires a published'):
            generate.collect_wiki_pages()

    def test_render_and_asset_copy(self):
        self.write('p6/other note.md', 'A page with spaces in its filename')
        self.write('p6/photo.jpg', 'image fixture')
        self.write('p6/.private', 'not an asset')
        self.write('p6/roms.md', '---\ntitle: ROMs & PLAs\nupdated: 2026-09-13\n---\n'
                   '[TOC]\n\n## Details\n\n![Photo](photo.jpg)')
        generate.generate_wiki(generate.collect_wiki_pages())
        html = (self.output / 'wiki/p6/roms/index.html').read_text()
        self.assertIn('ROMs &amp; PLAs', html)
        self.assertIn('Updated 2026-09-13', html)
        self.assertIn('href="/wiki/" class="active"', html)
        self.assertIn('id="details"', html)
        self.assertIn('href="#details"', html)
        self.assertNotIn('{{', html)
        self.assertNotIn('giscus', html)
        self.assertEqual((self.output / 'wiki/p6/photo.jpg').read_text(), 'image fixture')
        self.assertFalse((self.output / 'wiki/p6/.private').exists())
        self.assertFalse((self.output / 'wiki/p6/roms.md').exists())
        self.assertTrue((self.output / 'wiki/p6/other note/index.html').is_file())

    def test_blog_nav_and_static_pages_remain_usable(self):
        html = generate.generate_static_page('Projects', '<p>Projects</p>', 'nav_projects')
        self.assertIn('href="/projects/" class="active"', html)
        self.assertIn('href="/wiki/"', html)
        self.assertNotIn('{{', html)
        with patch.object(generate, 'CONTENT_ROOT', self.wiki.parent):
            self.assertEqual(generate.collect_pages(), [])


if __name__ == '__main__':
    unittest.main()
