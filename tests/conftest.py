# -*- coding: utf-8 -*-
"""Shared setup for the test suite.

Two things have to happen before any Murmur module is imported, which is why
they are at module level here rather than in a fixture:

1. APPDATA is pointed at a throwaway directory. `settings.CONFIG_PATH` and
   `history.DB_PATH` are both computed at import time from that variable, so
   setting it afterwards would be too late and the tests would read and write
   the real config.json, history.db and murmur.log of whoever ran them.

2. Qt is put in offscreen mode, so the widget tests run on a machine with no
   display and in CI.

`main` is imported here as well, because importing it calls _setup_logging(),
which replaces sys.stdout and sys.stderr with a log file handle. Left alone
that swallows pytest's own output for the rest of the session.
"""
import os
import sys
import tempfile
from pathlib import Path

_SANDBOX = Path(tempfile.mkdtemp(prefix="murmur-tests-"))
os.environ["APPDATA"] = str(_SANDBOX)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# The project root, so `import audio` works however pytest was invoked.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole session. Qt does not support creating a
    second one in the same process."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def murmur_main():
    """The main module, with stdout put back.

    main._setup_logging() runs at import and redirects stdout and stderr to
    murmur.log. That is right for a GUI app started by pythonw, where there is
    no console, and wrong for a test run.
    """
    import main
    sys.stdout, sys.stderr = sys.__stdout__, sys.__stderr__
    return main


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    """Point settings at a file of this test's own."""
    import settings
    path = tmp_path / "config.json"
    monkeypatch.setattr(settings, "CONFIG_PATH", path)
    return path
