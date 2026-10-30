"""Bounded Windows replacement recovery never bypasses storage guards."""
from copy import deepcopy
from hashlib import sha256
import errno
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from skillpane import storage
from skillpane.catalog import Catalog
from skillpane.library import Library
from skillpane.storage import Annotations, checked_replace
from test_catalog import fixture_root, skill


def windows_error(code):
    error = PermissionError(errno.EACCES, 'Synthetic replacement denial')
    error.winerror = code
    return error


class CheckedReplaceTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture_root().resolve()
        self.target = self.base / 'target.json'
        self.temporary = self.base / 'temporary.tmp'
        self.target.write_bytes(b'original')
        self.temporary.write_bytes(b'next')
        self.digest = sha256(b'next').hexdigest()

    def replace(self, check):
        checked_replace(self.temporary, self.target, expected_digest=self.digest, check=check)

    def test_transient_windows_errors_recheck_before_success(self):
        for code in (5, 32, 33):
            with self.subTest(code=code):
                self.target.write_bytes(b'original')
                self.temporary.write_bytes(b'next')
                original = Path.replace
                calls = []
                def replace(path, target):
                    calls.append(1)
                    if len(calls) < 3:
                        self.assertEqual(self.target.read_bytes(), b'original')
                        raise windows_error(code)
                    return original(path, target)
                guard = Mock()
                with patch.object(storage, 'WINDOWS_REPLACE', True), \
                        patch.object(Path, 'replace', replace), patch.object(storage.time, 'sleep') as sleep:
                    self.replace(guard)
                self.assertEqual(guard.call_count, 3)
                self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.025, 0.05])
                self.assertEqual(self.target.read_bytes(), b'next')

    def test_permanent_failure_has_five_attempts_and_preserves_original(self):
        guard = Mock()
        with patch.object(storage, 'WINDOWS_REPLACE', True), \
                patch.object(Path, 'replace', side_effect=windows_error(5)) as replace, \
                patch.object(storage.time, 'sleep') as sleep:
            with self.assertRaises(PermissionError):
                self.replace(guard)
        self.assertEqual(replace.call_count, 5)
        self.assertEqual(guard.call_count, 5)
        self.assertEqual(sleep.call_count, 4)
        self.assertAlmostEqual(sum(call.args[0] for call in sleep.call_args_list), 0.375)
        self.assertEqual(self.target.read_bytes(), b'original')
        self.assertEqual(self.temporary.read_bytes(), b'next')

    def test_unknown_errors_and_non_windows_fail_without_sleep(self):
        for windows, error in [(True, windows_error(87)), (False, windows_error(5)),
                               (True, PermissionError(errno.EACCES, 'Synthetic denial')),
                               (True, OSError(errno.ENOSPC, 'Synthetic capacity'))]:
            with self.subTest(windows=windows, code=getattr(error, 'winerror', None)):
                with patch.object(storage, 'WINDOWS_REPLACE', windows), \
                        patch.object(Path, 'replace', side_effect=error) as replace, \
                        patch.object(storage.time, 'sleep') as sleep:
                    with self.assertRaises(OSError):
                        self.replace(Mock())
                self.assertEqual(replace.call_count, 1)
                sleep.assert_not_called()

    def test_changed_target_stops_before_second_replace(self):
        original = self.target.read_bytes()
        def guard():
            if self.target.read_bytes() != original:
                raise ValueError('Synthetic external change')
        with patch.object(storage, 'WINDOWS_REPLACE', True), \
                patch.object(Path, 'replace', side_effect=windows_error(5)) as replace, \
                patch.object(storage.time, 'sleep', side_effect=lambda _: self.target.write_bytes(b'external')):
            with self.assertRaises(ValueError):
                self.replace(guard)
        self.assertEqual(replace.call_count, 1)
        self.assertEqual(self.target.read_bytes(), b'external')

    def test_changed_temporary_stops_before_second_replace(self):
        with patch.object(storage, 'WINDOWS_REPLACE', True), \
                patch.object(Path, 'replace', side_effect=windows_error(5)) as replace, \
                patch.object(storage.time, 'sleep', side_effect=lambda _: self.temporary.write_bytes(b'changed')):
            with self.assertRaises(ValueError):
                self.replace(Mock())
        self.assertEqual(replace.call_count, 1)
        self.assertEqual(self.target.read_bytes(), b'original')

    def test_linked_temporary_or_different_directory_is_rejected(self):
        with patch.object(Path, 'is_symlink', return_value=True), patch.object(Path, 'replace') as replace:
            with self.assertRaises(ValueError):
                self.replace(Mock())
            replace.assert_not_called()
        outside = self.base / 'other'
        outside.mkdir()
        with patch.object(Path, 'replace') as replace:
            with self.assertRaises(ValueError):
                checked_replace(self.temporary, outside / 'target.json',
                                expected_digest=self.digest, check=Mock())
            replace.assert_not_called()


class CheckedReplaceStorageTests(unittest.TestCase):
    def setUp(self):
        self.base = fixture_root()
        self.source = skill(self.base / 'home', '.agents/skills/fixture', 'fixture')
        self.store = Annotations(self.base / 'state')
        self.library = Library(Catalog(self.base / 'home'), self.store)
        self.id = self.library.snapshot()['skills'][0]['id']

    def test_annotation_transient_failure_commits_once_with_one_backup(self):
        self.store.update(self.id, {'note': 'before'})
        backups = len(list((self.store.directory / 'backups').glob('*.json')))
        original = Path.replace
        calls = []
        def replace(path, target):
            calls.append(1)
            if len(calls) == 1:
                self.assertEqual(self.store.snapshot()[self.id]['note'], 'before')
                raise windows_error(5)
            return original(path, target)
        with patch.object(storage, 'WINDOWS_REPLACE', True), \
                patch.object(Path, 'replace', replace), patch.object(storage.time, 'sleep'):
            self.store.update(self.id, {'note': 'after'})
        self.assertEqual(len(calls), 2)
        self.assertEqual(Annotations(self.store.directory).snapshot()[self.id]['note'], 'after')
        self.assertEqual(len(list((self.store.directory / 'backups').glob('*.json'))), backups + 1)

    def test_history_permanent_failure_preserves_disk_memory_and_error(self):
        history = self.library.history
        before, state = history.path.read_bytes(), deepcopy(history.state)
        skills = self.library.snapshot()['skills']
        skills[0]['sha256'] = 'a' * 64
        with patch.object(storage, 'WINDOWS_REPLACE', True), \
                patch.object(Path, 'replace', side_effect=windows_error(5)) as replace, \
                patch.object(storage.time, 'sleep'):
            history.observe(skills)
        self.assertEqual(replace.call_count, 5)
        self.assertTrue(history.error)
        self.assertEqual(history.path.read_bytes(), before)
        self.assertEqual(history.state, state)
        self.assertEqual(list(self.store.directory.glob('scan-history-*.tmp')), [])

    def test_annotation_failure_removes_only_its_temporary_file(self):
        unrelated = self.store.directory / 'annotations-unrelated.tmp'
        unrelated.write_bytes(b'kept')
        with patch.object(storage, 'WINDOWS_REPLACE', False), \
                patch.object(Path, 'replace', side_effect=OSError(errno.ENOSPC, 'Synthetic capacity')):
            with self.assertRaises(OSError):
                self.store.update(self.id, {'note': 'not written'})
        self.assertEqual(list(self.store.directory.glob('annotations-*.tmp')), [unrelated])
        self.assertEqual(unrelated.read_bytes(), b'kept')

    def test_written_data_is_flushed_to_disk_before_replacement(self):
        synced = []
        original = storage.os.fsync
        def fsync(descriptor):
            synced.append(descriptor)
            return original(descriptor)
        with patch.object(storage.os, 'fsync', fsync), patch.object(Path, 'replace', autospec=True,
                                                                      side_effect=Path.replace) as replace:
            self.store.update(self.id, {'note': 'durable'})
        self.assertTrue(synced)
        self.assertEqual(replace.call_count, 1)
        self.assertEqual(Annotations(self.store.directory).snapshot()[self.id]['note'], 'durable')

    def test_history_transient_failure_saves_one_event_and_survives_restart(self):
        history = self.library.history
        skills = self.library.snapshot()['skills']
        skills[0]['sha256'] = 'a' * 64
        original = Path.replace
        calls = []
        def replace(path, target):
            calls.append(1)
            if len(calls) == 1:
                raise windows_error(32)
            return original(path, target)
        with patch.object(storage, 'WINDOWS_REPLACE', True), \
                patch.object(Path, 'replace', replace), patch.object(storage.time, 'sleep'):
            history.observe(skills)
        self.assertIsNone(history.error)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(history.snapshot()['events']), 1)
        from skillpane.changes import ScanHistory
        self.assertEqual(ScanHistory(self.store).snapshot()['events'], history.snapshot()['events'])

    def test_annotation_external_change_during_delay_is_preserved(self):
        self.store.update(self.id, {'note': 'before'})
        state = deepcopy(self.store.state)
        external = self.store.path.read_bytes() + b'\n'
        with patch.object(storage, 'WINDOWS_REPLACE', True), \
                patch.object(Path, 'replace', side_effect=windows_error(5)) as replace, \
                patch.object(storage.time, 'sleep', side_effect=lambda _: self.store.path.write_bytes(external)):
            with self.assertRaises(ValueError):
                self.store.update(self.id, {'note': 'must not commit'})
        self.assertEqual(replace.call_count, 1)
        self.assertEqual(self.store.path.read_bytes(), external)
        self.assertEqual(self.store.state, state)

    def test_directory_rebound_during_delay_never_writes_outside(self):
        from test_adversarial import link_directory
        history = self.library.history
        state = deepcopy(history.state)
        outside = self.base / 'outside'
        outside.mkdir()
        sentinel = outside / 'scan-history.json'
        sentinel.write_bytes(b'outside sentinel')
        def rebind(_):
            self.store.directory.rename(self.base / 'kept-state')
            link_directory(outside, self.store.directory)
        skills = self.library.snapshot()['skills']
        skills[0]['sha256'] = 'a' * 64
        with patch.object(storage, 'WINDOWS_REPLACE', True), \
                patch.object(Path, 'replace', side_effect=windows_error(5)) as replace, \
                patch.object(storage.time, 'sleep', side_effect=rebind):
            history.observe(skills)
        self.assertEqual(replace.call_count, 1)
        self.assertTrue(history.error)
        self.assertEqual(history.state, state)
        self.assertEqual(sentinel.read_bytes(), b'outside sentinel')
        # Cleanup never follows the rebound directory; the original temporary stays put.
        self.assertEqual([path.name for path in outside.iterdir()], ['scan-history.json'])
        self.assertEqual(len(list((self.base / 'kept-state').glob('scan-history-*.tmp'))), 1)
