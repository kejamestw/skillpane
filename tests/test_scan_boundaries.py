"""Synthetic vendored checkouts must not inflate the skill inventory."""
from hashlib import sha256
from pathlib import Path
import unittest
from unittest.mock import patch

from skillpane.catalog import Catalog
from skillpane.library import Library
from skillpane.storage import Annotations, now
from test_adversarial import link_directory
from test_catalog import fixture_root, skill


class ScanBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture_root()
        self.home = self.base / 'home'

    def names(self):
        return sorted(s['name'] for s in Catalog(self.home).snapshot()['skills'])

    def test_vendored_checkout_is_one_skill_without_phantom_overlaps(self):
        outer = skill(self.home, '.claude/skills/gstack', 'gstack', 'Synthetic checkout')
        skill(self.home, '.claude/skills/autoplan', 'autoplan', 'Synthetic standalone')
        nested = [skill(self.home, '.claude/skills/gstack/autoplan', 'autoplan')]
        for agent in ('.cursor', '.factory', '.hermes', '.kiro', '.agents'):
            nested.append(skill(self.home, f'.claude/skills/gstack/{agent}/skills/mirror', 'autoplan'))
        nested.append(skill(self.home, '.claude/skills/gstack/node_modules/pkg', 'dependency'))
        before = {p: p.read_bytes() for p in (outer, *nested)}
        catalog = Catalog(self.home).snapshot()
        self.assertEqual(sorted(s['name'] for s in catalog['skills']), ['autoplan', 'gstack'])
        self.assertEqual(catalog['stats']['files'], 2)
        self.assertEqual(catalog['overlaps'], [])
        self.assertTrue(all(p.read_bytes() == content for p, content in before.items()))

    def test_containers_system_and_plugin_versions_still_expand(self):
        skill(self.home, '.codex/skills/.system/first', 'first')
        skill(self.home, '.codex/skills/.system/second', 'second')
        skill(self.home, '.agents/skills/collection/third', 'third')
        skill(self.home, '.agents/skills/collection/fourth', 'fourth')
        for version in ('1.0', '2.0'):
            skill(self.home, f'.codex/plugins/cache/market/plugin/{version}/skills/tool', 'tool')
            skill(self.home, f'.codex/plugins/cache/market/plugin/{version}/skills/tool/mirrors/hidden', 'hidden')
        snapshot = Catalog(self.home).snapshot()
        self.assertEqual(sorted(s['name'] for s in snapshot['skills']), ['first', 'fourth', 'second', 'third', 'tool'])
        self.assertEqual(snapshot['stats']['system'], 2)
        self.assertEqual(snapshot['stats']['extra_versions'], 1)

    def test_excluded_and_outside_directories_are_pruned_before_enumeration(self):
        import os
        skill(self.home, '.agents/skills/one', 'one')
        blocked = [self.home / '.agents/skills' / name for name in ('.git', 'node_modules', '.trash')]
        for path in blocked:
            skill(self.home, str(path.relative_to(self.home) / 'hidden'), 'hidden')
        outside = skill(self.home, 'outside/hidden', 'outside')
        alias = self.home / '.agents/skills/outside'
        link_directory(outside.parent, alias)
        original = os.scandir
        def guarded(path):
            resolved = Path(path).resolve()
            if resolved == outside.parent or any(resolved == p or resolved.is_relative_to(p) for p in blocked):
                raise AssertionError('Excluded or outside directory was enumerated.')
            return original(path)
        with patch('os.scandir', side_effect=guarded):
            self.assertEqual(self.names(), ['one'])

    def test_directory_links_preserve_aliases_and_stop_cycles(self):
        target = skill(self.home, '.agents/skills/first', 'first')
        alias = self.home / '.claude/skills/first'
        alias.parent.mkdir(parents=True)
        link_directory(target.parent, alias)
        container = self.home / '.agents/skills/collection'
        container.mkdir()
        link_directory(container, container / 'loop')
        snapshot = Catalog(self.home).snapshot()
        self.assertEqual(snapshot['stats']['total'], 1)
        self.assertEqual(snapshot['stats']['shared'], 1)
        self.assertEqual(snapshot['skills'][0]['associated_tools'], ['Claude', 'Codex'])
        self.assertGreaterEqual(snapshot['stats']['skipped'], 1)

    def test_invalid_outer_skill_does_not_promote_its_nested_copies(self):
        skill(self.home, '.agents/skills/invalid', 'x' * 201)
        skill(self.home, '.agents/skills/invalid/nested', 'nested')
        skill(self.home, '.agents/skills/valid', 'valid')
        self.assertEqual(self.names(), ['valid'])

    def test_old_nested_annotations_remain_available_as_orphans(self):
        skill(self.home, '.agents/skills/outer', 'outer', body='Synthetic outer content')
        child = skill(self.home, '.agents/skills/outer/nested', 'nested', body='Synthetic nested content')
        store = Annotations(self.base / 'state')
        key = 'previous-nested-identity'
        store.state['identities'][key] = {'name': 'nested', 'source': 'personal', 'plugin': '',
            'sha256': sha256(child.read_bytes()).hexdigest(), 'first_seen_at': now(),
            'catalog_key': sha256(str(child.resolve()).encode()).hexdigest()[:24],
            'path_hint': str(child), 'legacy_ids': []}
        store.state['annotations'][key] = {'note': 'Synthetic preserved note', 'favorite': True}
        store.commit(store.state)
        snapshot = Library(Catalog(self.home), store).snapshot()
        self.assertEqual([s['name'] for s in snapshot['skills']], ['outer'])
        self.assertEqual(snapshot['orphans'][0]['id'], key)
        self.assertEqual(store.snapshot()[key], {'note': 'Synthetic preserved note', 'favorite': True})


if __name__ == '__main__':
    unittest.main()
