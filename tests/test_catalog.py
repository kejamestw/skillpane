import json
from pathlib import Path
import unittest
from uuid import uuid4

from skillpane.catalog import Catalog, parse_frontmatter
from skillpane.storage import Annotations


def fixture_root():
    path = Path(__file__).resolve().parent.parent / '.runtime/test-runs' / uuid4().hex
    path.mkdir(parents=True)
    return path


def skill(home, relative, name='example', description='Synthetic test only', body=''):
    path = home / relative / 'SKILL.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'---\nname: {name}\ndescription: {description}\n---\n# Example\n{body}', encoding='utf-8')
    return path


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.home = fixture_root() / 'home'

    def test_plugin_versions_collapse_without_claiming_activation(self):
        skill(self.home, '.codex/plugins/cache/market/plugin/1.9.0/skills/pdf', 'pdf')
        skill(self.home, '.codex/plugins/cache/market/plugin/1.10.0/skills/pdf', 'pdf')
        catalog = Catalog(self.home)
        data = catalog.snapshot()
        self.assertEqual(data['stats']['files'], 2)
        self.assertEqual(data['stats']['plugin'], 1)
        self.assertEqual(data['stats']['extra_versions'], 1)
        self.assertEqual(data['skills'][0]['version'], '1.10.0')
        self.assertIsNone(data['skills'][0]['usage'])

    def test_same_name_different_plugins_are_separate(self):
        skill(self.home, '.codex/plugins/cache/market/first/1/skills/common', 'common')
        skill(self.home, '.codex/plugins/cache/market/second/1/skills/common', 'common')
        snapshot = Catalog(self.home).snapshot()
        self.assertEqual(snapshot['stats']['plugin'], 2)
        self.assertIn('same-name', [g['kind'] for g in snapshot['overlaps']])

    def test_junction_alias_counted_once_and_outside_target_skipped(self):
        try:
            import _winapi
        except ImportError:
            self.skipTest('Windows junction integration test')
        path = skill(self.home, '.agents/skills/animate', 'animate')
        alias = self.home / '.claude/skills/animate'
        alias.parent.mkdir(parents=True)
        _winapi.CreateJunction(str(path.parent), str(alias))
        outside = skill(self.home, 'outside/hidden')
        _winapi.CreateJunction(str(outside.parent), str(self.home / '.agents/skills/outside'))
        snapshot = Catalog(self.home).snapshot()
        self.assertEqual(snapshot['stats']['personal'], 1)
        self.assertEqual(snapshot['stats']['shared'], 1)
        self.assertEqual(snapshot['skills'][0]['associated_tools'], ['Claude', 'Codex'])
        self.assertEqual(len(snapshot['skills'][0]['aliases']), 2)
        self.assertGreaterEqual(snapshot['stats']['skipped'], 1)

    def test_classification_and_trash_exclusion(self):
        skill(self.home, '.agents/skills/one', 'one')
        skill(self.home, '.codex/skills/.system/two', 'two')
        skill(self.home, '.claude/skills/synced/three', 'three')
        skill(self.home, '.claude/skills/.trash/four', 'four')
        stats = Catalog(self.home).snapshot()['stats']
        self.assertEqual((stats['personal'], stats['system'], stats['managed'], stats['total']), (1, 1, 1, 3))

    def test_invocation_policies_are_read_without_changing_files(self):
        path = skill(self.home, '.agents/skills/prototype', 'prototype')
        path.write_text(path.read_text().replace('description:', 'disable-model-invocation: true\ndescription:'), encoding='utf-8')
        original = path.read_bytes()
        entry = Catalog(self.home).snapshot()['skills'][0]
        self.assertFalse(entry['invocation']['claude_implicit'])
        self.assertTrue(entry['invocation']['codex_implicit'])
        self.assertFalse(entry['warnings'])
        self.assertTrue(entry['advisories'])
        policy = path.parent / 'agents/openai.yaml'
        policy.parent.mkdir()
        policy.write_text('policy:\n  allow_implicit_invocation: false\n', encoding='utf-8')
        self.assertFalse(Catalog(self.home).snapshot()['skills'][0]['invocation']['codex_implicit'])
        self.assertEqual(path.read_bytes(), original)

    def test_frontmatter_multiline_and_quoted_values(self):
        data = parse_frontmatter('---\nname: "example"\ndescription: >-\n  first line\n  second line\n---\n')
        self.assertEqual(data, {'name':'example', 'description':'first line second line'})

    def test_related_categories_do_not_count_as_duplicates(self):
        skill(self.home, '.agents/skills/motion-one', 'motion-one', 'Build animations')
        skill(self.home, '.agents/skills/motion-two', 'motion-two', 'Review animation')
        snapshot = Catalog(self.home).snapshot()
        self.assertEqual(snapshot['overlaps'], [])
        self.assertEqual(snapshot['stats']['related_groups'], 1)
        self.assertEqual(len(snapshot['related_groups'][0]['ids']), 2)

    def test_provenance_requires_known_description_and_personal_location(self):
        description = "This skill encodes Emil Kowalski's philosophy on UI polish, component design, animation decisions, and the invisible details that make software feel great."
        original = skill(self.home, '.agents/skills/emil-design-eng', 'emil-design-eng', description)
        skill(self.home, '.codex/plugins/cache/market/example/1/skills/emil-design-eng', 'emil-design-eng', description)
        snapshot = Catalog(self.home).snapshot()
        personal = next(s for s in snapshot['skills'] if s['source'] == 'personal')
        plugin = next(s for s in snapshot['skills'] if s['source'] == 'plugin')
        self.assertEqual(personal['description'], description)
        self.assertEqual(personal['provenance']['display_name'], 'skillpane')
        self.assertEqual(plugin['display_name'], 'emil-design-eng')
        self.assertEqual(plugin['commands'], {'codex':'', 'claude':''})
        original.write_text(original.read_text(encoding='utf-8').replace(description, 'A different custom skill'), encoding='utf-8')
        personal = next(s for s in Catalog(self.home).snapshot()['skills'] if s['source'] == 'personal')
        self.assertEqual(personal['provenance']['display_name'], 'skill')
        self.assertEqual(personal['summary'], 'A different custom skill')

    def test_unknown_policy_is_visible_and_does_not_change_sources(self):
        path = skill(self.home, '.agents/skills/example')
        policy = path.parent / 'agents/openai.yaml'
        policy.parent.mkdir()
        policy.write_text('policy:\n  allow_implicit_invocation: "false"\n', encoding='utf-8')
        before = path.read_bytes(), policy.read_bytes()
        record = Catalog(self.home).snapshot()['skills'][0]
        self.assertIsNone(record['invocation']['codex_implicit'])
        self.assertEqual(record['invocation']['codex']['state'], 'unknown')
        self.assertTrue(record['warnings'])
        self.assertEqual(before, (path.read_bytes(), policy.read_bytes()))

    def test_scan_scope_does_not_claim_project_or_activation_coverage(self):
        snapshot = Catalog(self.home).snapshot()
        self.assertEqual(len(snapshot['scan_scope']['roots']), 4)
        self.assertFalse(snapshot['scan_scope']['project_skills_scanned'])
        self.assertFalse(snapshot['scan_scope']['activation_verified'])

    def test_lone_surrogate_metadata_falls_back_and_can_be_stored(self):
        from skillpane.library import Library
        skill(self.home, '.agents/skills/good', 'good')
        state = self.home.parent / 'state'
        library = Library(Catalog(self.home), Annotations(state))
        bad = self.home / '.agents/skills/bad-name/SKILL.md'
        bad.parent.mkdir()
        bad.write_text('---\nname: "\\ud800"\ndescription: "\\udc80"\n---\nSynthetic\n', encoding='utf-8')
        snapshot = library.rescan()
        record = next(s for s in snapshot['skills'] if s['name'] == 'bad-name')
        self.assertEqual(record['description'], '')
        self.assertTrue(any('代理字元' in warning for warning in record['warnings']))
        json.dumps(snapshot, ensure_ascii=False).encode('utf-8')
        restarted = Library(Catalog(self.home), Annotations(state)).snapshot()
        self.assertEqual(sorted(s['name'] for s in restarted['skills']), ['bad-name', 'good'])

    def test_unknown_id_cannot_read_arbitrary_file(self):
        catalog = Catalog(self.home)
        with self.assertRaises(KeyError):
            catalog.content('../../secret')


class StorageTests(unittest.TestCase):
    def test_annotations_persist_without_touching_skill_and_backups_are_unique(self):
        base = fixture_root()
        original = skill(base / 'home', '.agents/skills/example')
        content = original.read_bytes()
        storage = Annotations(base / 'state')
        storage.update('example', {'favorite': True})
        storage.update('example', {'status': 'review'})
        storage.update('example', {'note': '只記錄測試筆記'})
        self.assertEqual(len(list((base / 'state/backups').glob('*.json'))), 2)
        self.assertEqual(Annotations(base / 'state').snapshot()['example']['note'], '只記錄測試筆記')
        self.assertEqual(original.read_bytes(), content)

    def test_validation_rejects_unknown_fields_and_wrong_types(self):
        storage = Annotations(fixture_root() / 'state')
        for payload in [{'path':'outside'}, {'favorite':'yes'}, {'status':'delete'}, {'note':'a'*4001}]:
            with self.subTest(payload_key=list(payload)[0]), self.assertRaises(ValueError):
                storage.update('example', payload)

    def test_corrupt_annotations_are_preserved(self):
        directory = fixture_root()
        target = directory / 'annotations.json'
        target.write_text('corrupt fixture', encoding='utf-8')
        with self.assertRaises(ValueError):
            Annotations(directory)
        self.assertEqual(target.read_text(), 'corrupt fixture')


if __name__ == '__main__':
    unittest.main()
