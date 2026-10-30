import unittest

from skillpane.metadata import frontmatter, invocation_setting, parse_mapping


class MetadataTests(unittest.TestCase):
    def setting(self, text, path=('policy', 'allow_implicit_invocation')):
        return invocation_setting(parse_mapping(text), path, 'synthetic.yaml')

    def test_comments_boolean_and_exact_section(self):
        setting = self.setting('interface:\n  allow_implicit_invocation: true\npolicy:\n  allow_implicit_invocation: false # only manual\n')
        self.assertEqual((setting['state'], setting['allowed'], setting['line']), ('explicit', False, 4))
        self.assertEqual(self.setting('interface:\n  allow_implicit_invocation: false\n')['state'], 'default')

    def test_claude_inverse_and_original_file_line(self):
        document = frontmatter('---\nname: fixture\ndisable-model-invocation: true # manual\n---\n')
        setting = invocation_setting(document, ('disable-model-invocation',), 'SKILL.md', invert=True)
        self.assertEqual((setting['state'], setting['allowed'], setting['line']), ('explicit', False, 3))

    def test_quoted_comments_and_apostrophes(self):
        document = parse_mapping('name: "contains # text" # comment\ndescription: Apple\'s motion design # note\nother: \'it\'\'s # quoted\'\n')
        self.assertEqual(document.values[('name',)], 'contains # text')
        self.assertEqual(document.values[('description',)], "Apple's motion design")
        self.assertEqual(document.values[('other',)], "it's # quoted")

    def test_lone_surrogate_escape_is_unreadable_but_pairs_are_kept(self):
        document = parse_mapping('name: "bad\\ud800"\nlow: "\\udc80"\nemoji: "\\ud83d\\ude00"\n')
        for key in ('name', 'low'):
            with self.subTest(key=key):
                self.assertIsNone(document.values[(key,)])
                self.assertIn('代理字元', document.error_for((key,)))
        self.assertEqual(document.values[('emoji',)], '\U0001F600')

    def test_invalid_or_ambiguous_values_remain_unknown(self):
        for value in ['"false"', "'true'", 'null', '0', 'yes', '[]', '{}', '"unclosed', '&flag false', '!bool false']:
            with self.subTest(value=value):
                setting = self.setting('policy:\n  allow_implicit_invocation: ' + value)
                self.assertEqual(setting['state'], 'unknown')
                self.assertIsNone(setting['allowed'])

    def test_parent_structure_duplicates_and_indentation_remain_unknown(self):
        for text in ['policy: {allow_implicit_invocation: false}', 'policy: false', 'policy: null',
                     'policy:\n  allow_implicit_invocation: false\n  allow_implicit_invocation: true',
                     'policy:\n  allow_implicit_invocation: false\n other: true',
                     'policy:\n\tallow_implicit_invocation: false',
                     'policy:\n  <<: *default',
                     'policy:\n  allow_implicit_invocation: false\npolicy:\n  other: true']:
            with self.subTest(text=text):
                self.assertEqual(self.setting(text)['state'], 'unknown')

    def test_missing_setting_is_default_but_broken_document_is_unknown(self):
        for text in ['', 'interface:\n  display_name: "Example"', 'policy: {}']:
            with self.subTest(text=text):
                self.assertEqual(self.setting(text)['state'], 'default')
        for text in ['No frontmatter', '---\ndisable-model-invocation: false']:
            setting = invocation_setting(frontmatter(text), ('disable-model-invocation',), 'SKILL.md', invert=True)
            self.assertEqual(setting['state'], 'unknown')

    def test_unrelated_unsupported_field_does_not_override_explicit_policy(self):
        setting = self.setting('dependencies:\n  tools:\n    - type: mcp\npolicy:\n  allow_implicit_invocation: false\n')
        self.assertEqual((setting['state'], setting['allowed']), ('explicit', False))


if __name__ == '__main__':
    unittest.main()
