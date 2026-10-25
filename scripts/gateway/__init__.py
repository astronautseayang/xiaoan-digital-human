"""Import shim for test scripts executed directly from this directory.

The real package lives one directory above ``scripts``.  Exposing that
directory as this package path keeps direct script execution equivalent to
running the tests with ``PYTHONPATH=.``.
"""
from pathlib import Path

__path__ = [str(Path(__file__).resolve().parents[2] / 'gateway')]
