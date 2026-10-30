from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
import subprocess

from skillpane.catalog import Catalog
from skillpane.library import Library
from skillpane.storage import Annotations, clone, now
from skillpane.transfers import Transfers, validate_backup
from test_catalog import fixture_root, skill


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture_root()
        self.home = self.base / 'home'
        self.path = skill(self.home, '.agents/skills/first', 'first', 'Synthetic API one', 'First content')
        self.other = skill(self.home, '.agents/skills/second', 'second', 'Synthetic API two', 'Second content')
        self.store = Annotations(self.base / 'state')
        self.catalog = Catalog(self.home)
        self.library = Library(self.catalog, self.store)
        self.transfers = Transfers(self.library)
        self.ids = {s['name']: s['id'] for s in self.library.snapshot()['skills']}

    def rescan(self):
        self.catalog.refresh()
        return self.library.snapshot()

    def choices(self, preview):
        return {row['id']: row['target'] for row in preview['rows']}

    def apply(self, preview, mode='replace', choices=None):
        return self.transfers.apply_import({'token': preview['token'], 'choices': choices or self.choices(preview), 'mode': mode, 'restore_settings': False})

    def test_legacy_migration_preserves_annotation_and_original_backup(self):
        base = fixture_root()
        catalog = Catalog(self.home)
        legacy_id = catalog.snapshot()['skills'][0]['id']
        old = {legacy_id: {'favorite': True, 'note': 'Synthetic old note', 'status': 'review'}}
        directory = base / 'state'
        directory.mkdir()
        path = directory / 'annotations.json'
        path.write_text(json.dumps(old), encoding='utf-8')
        original = path.read_bytes()
        store = Annotations(directory)
        library = Library(catalog, store)
        entry = library.snapshot()['skills'][0]
        self.assertEqual(store.snapshot()[entry['id']], old[legacy_id])
        self.assertEqual(next((directory / 'backups').glob('*.json')).read_bytes(), original)
        restarted = Library(catalog, Annotations(directory)).snapshot()['skills'][0]
        self.assertEqual((entry['id'], entry['first_seen_at']), (restarted['id'], restarted['first_seen_at']))

    def test_unique_move_keeps_stable_identity_note_and_first_seen(self):
        before = next(s for s in self.library.snapshot()['skills'] if s['name'] == 'first')
        self.store.update(before['id'], {'note': 'Keep synthetic note'})
        self.path.parent.rename(self.path.parent.with_name('renamed'))
        after = next(s for s in self.rescan()['skills'] if s['name'] == 'first')
        self.assertEqual((before['id'], before['first_seen_at']), (after['id'], after['first_seen_at']))
        self.assertEqual(self.store.snapshot()[after['id']]['note'], 'Keep synthetic note')
        self.assertIn('First content', self.library.content(after['id']))

    def test_ambiguous_content_move_does_not_merge_two_new_skills(self):
        original_id = self.ids['first']
        self.store.update(original_id, {'note': 'Original synthetic note'})
        old = self.path.parent.with_name('moved-out')
        self.path.parent.rename(self.home / 'off-scan')
        for directory in ['copy-a', 'copy-b']:
            target = self.home / '.agents/skills' / directory / 'SKILL.md'
            target.parent.mkdir(parents=True)
            target.write_bytes((self.home / 'off-scan/SKILL.md').read_bytes())
        snapshot = self.rescan()
        copies = [s for s in snapshot['skills'] if s['name'] == 'first']
        self.assertEqual(len(copies), 2)
        self.assertNotIn(original_id, [s['id'] for s in copies])
        self.assertEqual(snapshot['orphans'][0]['id'], original_id)

    def test_move_and_content_change_requires_previewed_relink(self):
        original_id = self.ids['first']
        self.store.update(original_id, {'note': 'Old note', 'alias': 'Old alias'})
        first_seen = self.store.state['identities'][original_id]['first_seen_at']
        self.path.parent.rename(self.path.parent.with_name('new-location'))
        moved = self.path.parent.with_name('new-location') / 'SKILL.md'
        moved.write_text(moved.read_text(encoding='utf-8') + '\nChanged content', encoding='utf-8')
        target = next(s['id'] for s in self.rescan()['skills'] if s['name'] == 'first')
        self.assertNotEqual(target, original_id)
        self.store.update(target, {'alias': 'Current alias'})
        before = self.store.path.read_bytes()
        preview = self.transfers.preview_relink({'from_id': original_id, 'to_id': target})
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(preview['conflicts'], ['alias'])
        self.transfers.apply_relink({'token': preview['token'], 'mode': 'keep'})
        self.assertIn(original_id, self.library.live)
        self.assertEqual(self.store.snapshot()[original_id], {'note':'Old note', 'alias':'Current alias'})
        self.assertEqual(self.store.state['identities'][original_id]['first_seen_at'], first_seen)
        self.assertTrue(self.store.state['identities'][target]['retired'])
        self.assertEqual(self.library.snapshot()['orphans'], [])

    def test_portable_round_trip_matches_other_home_without_paths_or_bodies(self):
        values = {'alias':'Synthetic alias', 'summary':'Synthetic summary', 'category':'Custom', 'tags':['one','two'],
                  'origin_reason':'Synthetic installation reason', 'source_url':'https://example.invalid/source',
                  'scope_note':'Synthetic scope', 'modifies_files':'no', 'display_mode':'original', 'favorite':True, 'note':'Synthetic personal note', 'status':'review'}
        self.store.update(self.ids['first'], values)
        self.library.save_comparison({'left_id':self.ids['first'], 'right_id':self.ids['second'], 'decision':'keep-both','reason':'Different scope'})
        backup = self.transfers.export()
        serialized = json.dumps(backup)
        for forbidden in ['path_hint','catalog_key','legacy_ids','First content',str(self.home)]:
            self.assertNotIn(forbidden, serialized)
        second_home = fixture_root() / 'other-home'
        for path in [self.path, self.other]:
            destination = second_home / '.agents/skills' / path.parent.name / 'SKILL.md'
            destination.parent.mkdir(parents=True)
            destination.write_bytes(path.read_bytes())
        library = Library(Catalog(second_home), Annotations(second_home.parent / 'state'))
        transfers = Transfers(library)
        preview = transfers.preview_import(backup)
        self.assertTrue(all(row['target'] not in ('', 'orphan') for row in preview['rows']))
        transfers.apply_import({'token':preview['token'], 'choices':self.choices(preview), 'mode':'replace', 'restore_settings':True})
        new_id = next(s['id'] for s in library.snapshot()['skills'] if s['name'] == 'first')
        self.assertEqual(library.store.snapshot()[new_id], values)
        self.assertEqual(len(library.snapshot()['comparisons']), 1)
        self.assertFalse(next(iter(library.snapshot()['comparisons'].values()))['needs_review'])

    def test_import_preview_conflicts_and_modes_are_atomic_and_revision_checked(self):
        first = self.ids['first']
        self.store.update(first, {'note':'Backup note'})
        backup = self.transfers.export()
        self.store.update(first, {'note':'Current note', 'favorite':True})
        before = self.store.path.read_bytes()
        preview = self.transfers.preview_import(backup)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertIn('note', next(row for row in preview['rows'] if row['id'] == first)['conflicts'])
        self.apply(preview, 'keep')
        self.assertEqual(self.store.snapshot()[first]['note'], 'Current note')
        self.apply(self.transfers.preview_import(backup), 'replace')
        self.assertEqual(self.store.snapshot()[first], {'note':'Backup note'})
        stale = self.transfers.preview_import(backup)
        self.store.update(first, {'note':'Concurrent note'})
        with self.assertRaisesRegex(ValueError, '資料已變更'):
            self.apply(stale)
        self.assertEqual(self.store.snapshot()[first]['note'], 'Concurrent note')

    def test_duplicate_import_destinations_and_invalid_backup_preserve_current_data(self):
        backup = self.transfers.export()
        before = self.store.path.read_bytes()
        preview = self.transfers.preview_import(backup)
        with self.assertRaises(ValueError):
            self.apply(preview, choices={row['id']:self.ids['first'] for row in preview['rows']})
        self.assertEqual(self.store.path.read_bytes(), before)
        bad = deepcopy(backup)
        bad['records'][0]['annotation'] = {'source_url':'javascript:alert(1)'}
        with self.assertRaises(ValueError):
            self.transfers.preview_import(bad)
        bad = deepcopy(backup)
        bad['records'].append(bad['records'][0])
        with self.assertRaises(ValueError):
            validate_backup(bad)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_comparison_records_detect_changed_content_and_survive_restarts(self):
        left, right = self.ids['first'], self.ids['second']
        self.library.save_comparison({'left_id':left, 'right_id':right, 'decision':'checked', 'reason':'Synthetic review'})
        self.assertFalse(self.library.comparison(left,right)['record']['needs_review'])
        self.path.write_text(self.path.read_text(encoding='utf-8')+'\nNew behavior', encoding='utf-8')
        self.rescan()
        library = Library(self.catalog, Annotations(self.base / 'state'))
        self.assertTrue(library.comparison(left,right)['record']['needs_review'])
        self.assertIn('New behavior',library.comparison(left,right)['diff'])

    def test_corrupt_storage_can_recover_without_overwriting_original_first(self):
        backup = self.transfers.export()
        directory = self.base / 'corrupt-state'
        directory.mkdir()
        path = directory / 'annotations.json'
        path.write_text('corrupt synthetic fixture', encoding='utf-8')
        original = path.read_bytes()
        store = Annotations(directory, recover=True)
        library = Library(self.catalog, store)
        self.assertTrue(library.snapshot()['storage_error'])
        self.assertEqual(path.read_bytes(), original)
        with self.assertRaises(ValueError):
            store.update(next(iter(library.live)), {'note':'Must not write'})
        transfers = Transfers(library)
        preview = transfers.preview_import(backup)
        transfers.apply_import({'token':preview['token'],'choices':self.choices(preview),'mode':'replace','restore_settings':False})
        self.assertIsNone(store.error)
        self.assertIn(original,[p.read_bytes() for p in (directory / 'backups').glob('*.json')])

    def test_local_backup_restore_preview_and_corruption_are_non_mutating(self):
        self.store.update(self.ids['first'], {'note':'Restore me'})
        self.store.update(self.ids['first'], {'note':'Newer note'})
        before = self.store.path.read_bytes()
        preview = self.transfers.preview_restore({'backup_id':self.transfers.backups()[0]['id']})
        self.assertEqual(self.store.path.read_bytes(), before)
        self.apply(preview)
        self.assertEqual(self.store.snapshot()[self.ids['first']]['note'], 'Restore me')
        with self.assertRaises(ValueError):
            self.transfers.preview_restore({'backup_id':'../../annotations.json'})

    def test_retention_is_manual_previewed_and_only_targets_listed_backups(self):
        for number in range(4):
            self.store.update(self.ids['first'], {'note':str(number)})
        self.assertEqual(self.transfers.preview_cleanup()['files'], [])
        self.transfers.settings({'keep_last':1})
        files_before = self.transfers.backups()
        with patch.object(self.transfers, 'backups', wraps=self.transfers.backups) as listing:
            preview = self.transfers.preview_cleanup()
            self.assertEqual(listing.call_count, 1)
        self.assertEqual(len(self.transfers.backups()), len(files_before))
        self.assertEqual(len(preview['files']), len(files_before)-1)
        with self.assertRaises(ValueError):
            self.transfers.apply_cleanup({'token':preview['token'], 'confirm':False})
        with patch.object(Path, 'unlink', autospec=True) as unlink:
            self.transfers.apply_cleanup({'token':preview['token'], 'confirm':True})
            self.assertEqual({call.args[0].name for call in unlink.call_args_list},{item['id'] for item in preview['files']})
        self.assertNotIn(files_before[0]['id'],{item['id'] for item in preview['files']})

    def test_repeated_state_reads_reuse_reconciliation_until_inputs_change(self):
        with patch.object(self.catalog, 'snapshot', wraps=self.catalog.snapshot) as catalog_snapshot:
            first = self.library.snapshot()
            self.assertEqual(self.library.snapshot(), first)
            self.assertEqual(catalog_snapshot.call_count, 0)
            self.store.update(self.ids['first'], {'note': 'Fresh note'})
            self.assertEqual(self.library.snapshot()['annotations'][self.ids['first']]['note'], 'Fresh note')
            self.assertEqual(catalog_snapshot.call_count, 1)
            skill(self.home, '.agents/skills/third', 'third')
            self.catalog.refresh()
            self.assertIn('third', [s['name'] for s in self.library.snapshot()['skills']])
            self.assertEqual(catalog_snapshot.call_count, 2)
            self.library.rescan()
            self.assertEqual(catalog_snapshot.call_count, 3)
        replacement = Catalog(self.home)
        self.library.catalog = replacement
        self.assertNotEqual(replacement.generation, self.catalog.generation)
        with patch.object(replacement, 'snapshot', wraps=replacement.snapshot) as replaced:
            self.library.snapshot()
            self.assertEqual(replaced.call_count, 1)

    def test_identical_writes_skip_rewrite_and_backup_but_still_detect_external_changes(self):
        self.store.update(self.ids['first'], {'note': 'Same note', 'favorite': True})
        backups, content, revision = self.transfers.backups(), self.store.path.read_bytes(), self.store.state['revision']
        self.store.update(self.ids['first'], {'note': 'Same note'})
        self.transfers.settings({'keep_last': None})
        self.assertEqual(self.transfers.backups(), backups)
        self.assertEqual((self.store.path.read_bytes(), self.store.state['revision']), (content, revision))
        self.store.update(self.ids['first'], {'favorite': False})
        self.assertEqual(len(self.transfers.backups()), len(backups) + 1)
        self.store.path.write_bytes(self.store.path.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, '其他程序'):
            self.store.update(self.ids['first'], {'favorite': False})

    def test_failed_atomic_replace_does_not_change_memory_or_current_file(self):
        state, content = clone(self.store.state), self.store.path.read_bytes()
        with patch.object(Path, 'replace', side_effect=OSError('Synthetic disk failure')):
            with self.assertRaises(OSError):
                self.store.update(self.ids['first'], {'note':'Unwritten note'})
        self.assertEqual(self.store.state, state)
        self.assertEqual(self.store.path.read_bytes(), content)

    def test_validation_rejects_unsafe_custom_fields_and_excessive_values(self):
        for value in [{'tags':['same','same']},{'tags':['x'*31]},{'alias':'x'*101},
                      {'source_url':'https://user:password@example.invalid'}, {'source_url':'https://example.invalid/?api_key=synthetic'},
                      {'modifies_files':'maybe'},{'display_mode':'script'}]:
            with self.subTest(field=next(iter(value))), self.assertRaises(ValueError):
                self.store.update(self.ids['first'], value)

    def test_new_source_urls_reject_fragment_credentials_and_known_tokens(self):
        token = 'synthetic' + 'X' * 24
        for url in ['https://example.invalid/#access_token=' + token, 'https://example.invalid/?token=',
                    'https://example.invalid/?q=ghp_' + token, 'https://example.invalid/' + 'sk-proj-' + token,
                    'https://example.invalid/?q=%67hp_' + token]:
            with self.subTest(url=url[:40]), self.assertRaisesRegex(ValueError, '來源網址'):
                self.store.update(self.ids['first'], {'source_url': url})
        for url in ['https://example.invalid/#readme', 'https://sk-example.invalid/docs',
                    'https://example.invalid/desk-organizer-' + token, 'https://example.invalid/?topic=tokens-guide']:
            with self.subTest(url=url[:40]):
                self.assertEqual(self.store.update(self.ids['first'], {'source_url': url})['source_url'], url)

    def test_stored_and_imported_source_urls_keep_the_original_rule(self):
        url = 'https://example.invalid/#access_token=synthetic-value'
        state = clone(self.store.state)
        state['annotations'][self.ids['first']] = {'source_url': url}
        self.store.commit(state)
        self.assertEqual(Annotations(self.store.directory).snapshot()[self.ids['first']]['source_url'], url)
        records = {record['id']: record for record in validate_backup(self.transfers.export())['records']}
        self.assertEqual(records[self.ids['first']]['annotation'], {'source_url': url})

    def test_external_file_changes_are_not_overwritten(self):
        state = clone(self.store.state)
        self.store.path.write_text('Changed by another synthetic process', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '其他程序'):
            self.store.update(self.ids['first'], {'note':'Do not overwrite'})
        self.assertEqual(self.store.state, state)
        self.assertEqual(self.store.path.read_text(encoding='utf-8'), 'Changed by another synthetic process')

    def test_git_evidence_is_read_only_and_reports_author_time(self):
        process = subprocess.CompletedProcess([], 0, b'2026-09-30T01:43:00+00:00\t' + b'a'*40 + b'\n', b'')
        with patch('skillpane.library.shutil.which', return_value='git'), patch('skillpane.library.subprocess.run', return_value=process) as run:
            evidence = self.library.provenance(self.ids['first'])
            self.assertEqual(evidence['state'], 'known')
            self.assertEqual(evidence['first_added_at'], '2026-09-30T01:43:00+00:00')
            self.assertIn('core.fsmonitor=false', run.call_args.args[0])
            self.assertIn('safe.bareRepository=explicit', run.call_args.args[0])
            self.assertIn('--no-ext-diff', run.call_args.args[0])
            self.assertIn('log', run.call_args.args[0])
            self.assertEqual(run.call_args.kwargs['env']['GIT_CEILING_DIRECTORIES'], str(self.home.resolve() / '.agents'))

    def test_git_evidence_ignores_repositories_above_scan_root_and_bare_layouts(self):
        git = shutil.which('git')
        if not git:
            self.skipTest('Git integration test')
        environment = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        def run(cwd, *args):
            subprocess.run([git, '-c', 'user.name=Synthetic', '-c', 'user.email=synthetic@example.invalid',
                            '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=', *args],
                           cwd=cwd, env=environment, check=True, capture_output=True)
        def commit_all(directory):
            run(directory, 'init', '-q')
            run(directory, 'add', '-A')
            run(directory, 'commit', '-q', '-m', 'Synthetic history')
        commit_all(self.home)
        self.assertEqual(self.library.provenance(self.ids['first'])['state'], 'unknown')
        commit_all(self.home / '.agents/skills')
        self.library.git_cache.clear()
        self.assertEqual(self.library.provenance(self.ids['first'])['state'], 'known')

        base = fixture_root()
        source = base / 'source'
        source.mkdir()
        (source / 'SKILL.md').write_text('---\nname: bare\ndescription: Synthetic\n---\n', encoding='utf-8')
        commit_all(source)
        target = base / 'home/.agents/skills/bare'
        target.parent.mkdir(parents=True)
        run(base, 'clone', '-q', '--bare', str(source), str(target))
        (target / 'SKILL.md').write_bytes((source / 'SKILL.md').read_bytes())
        library = Library(Catalog(base / 'home'), Annotations(base / 'state'))
        bare = next(s['id'] for s in library.snapshot()['skills'] if s['name'] == 'bare')
        self.assertEqual(library.provenance(bare)['state'], 'unknown')

    def test_comparison_reads_each_source_once_and_diffs_outside_the_lock(self):
        held = []
        def unified_diff(*args, **kwargs):
            held.append(self.store.lock._is_owned())
            return iter(['@@ synthetic @@\n'])
        with patch.object(self.catalog, 'read', wraps=self.catalog.read) as read, \
                patch('skillpane.library.difflib.unified_diff', unified_diff):
            result = self.library.comparison(self.ids['first'], self.ids['second'])
        self.assertEqual(read.call_count, 2)
        self.assertEqual(held, [False])
        self.assertEqual(result['diff'], '@@ synthetic @@\n')

    def test_single_read_text_matches_read_text_and_stays_bounded(self):
        from skillpane.catalog import decode
        sample = self.base / 'sample.md'
        sample.write_bytes(b'\xef\xbb\xbfline one\r\nline two\rline three\n\xff\xfe end')
        self.assertEqual(decode(sample.read_bytes()), sample.read_text(encoding='utf-8-sig', errors='replace'))
        with patch.object(self.catalog, 'source_path', return_value=sample), patch('skillpane.catalog.LIMIT', 8):
            with self.assertRaises(ValueError):
                self.catalog.read('synthetic')

    def test_long_comparison_reports_truncation(self):
        self.path.write_text(self.path.read_text(encoding='utf-8') + '\n' + 'Synthetic line\n'*2000, encoding='utf-8')
        self.rescan()
        self.assertTrue(self.library.comparison(self.ids['first'],self.ids['second'])['truncated'])

    def test_changed_source_must_be_rescanned_before_saving_a_conclusion(self):
        self.path.write_text(self.path.read_text(encoding='utf-8')+'\nUnscanned change', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '重新掃描'):
            self.library.save_comparison({'left_id':self.ids['first'],'right_id':self.ids['second'],'decision':'checked','reason':'Outdated view'})
        self.assertEqual(self.store.state['comparisons'],{})

    def test_relink_preserves_comparison_with_explicit_conflict_preference(self):
        left,right = self.ids['first'],self.ids['second']
        self.library.save_comparison({'left_id':left,'right_id':right,'decision':'checked','reason':'Old conclusion'})
        self.path.parent.rename(self.path.parent.with_name('moved'))
        moved = self.path.parent.with_name('moved') / 'SKILL.md'
        moved.write_text(moved.read_text(encoding='utf-8')+'\nChanged', encoding='utf-8')
        target = next(s['id'] for s in self.rescan()['skills'] if s['name'] == 'first')
        self.library.save_comparison({'left_id':target,'right_id':right,'decision':'keep-both','reason':'Current conclusion'})
        preview = self.transfers.preview_relink({'from_id':left,'to_id':target})
        self.assertEqual(preview['comparison_conflicts'],1)
        self.transfers.apply_relink({'token':preview['token'],'mode':'keep'})
        comparison = self.library.comparison(left,right)['record']
        self.assertEqual(comparison['reason'],'Current conclusion')
        self.assertFalse(comparison['needs_review'])


if __name__ == '__main__':
    unittest.main()
