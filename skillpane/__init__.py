"""Skillpane: a local, Traditional Chinese skill library."""
import sys

# CI covers 3.11 and 3.13; stop early with a readable message instead of a later failure.
if sys.version_info < (3, 11):
    raise SystemExit('Skillpane requires Python 3.11 or newer.')

__version__ = '0.4.0'
