"""Absolute launcher entry point so Windows can verify the owning checkout."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skillpane.server import main

if __name__ == '__main__':
    main()
