"""Prevent accidental publication of local scan history copied out of .data."""
import unittest

from scripts.check_publication import forbidden


class PublicationTests(unittest.TestCase):
    def test_scan_history_and_failure_temps_remain_private_when_copied(self):
        for name in ('scan-history.json', 'review/SCAN-HISTORY.JSON',
                     'scan-history-abcdef.tmp', 'review/scan-history-123.tmp'):
            with self.subTest(name=name):
                self.assertTrue(forbidden(name))
        for name in ('skillpane/changes.py', 'web/changes.js', 'tests/test_changes.py'):
            self.assertFalse(forbidden(name))
