import unittest

from scripts.check_docs import broken_links
from test_catalog import fixture_root


class DocumentationTests(unittest.TestCase):
    def test_relative_images_unicode_fragments_and_external_links(self):
        root = fixture_root()
        document = root / 'docs/tour.md'
        document.parent.mkdir()
        (root / 'README.md').write_text('Synthetic docs', encoding='utf-8')
        (document.parent / '圖.png').write_bytes(b'Synthetic image placeholder')
        text = '[Read](../README.md#fragment) ![Image](%E5%9C%96.png) <img src="圖.png"> [Web](https://example.invalid) [Here](#local)'
        self.assertEqual(broken_links(text, document, root), 0)

    def test_missing_and_outside_root_links_are_rejected(self):
        root = fixture_root()
        document = root / 'README.md'
        text = '[Missing](missing.md) <img src="absent.png"> [Escape](../outside.md) [File](file:///tmp/test.md)'
        self.assertEqual(broken_links(text, document, root), 4)
