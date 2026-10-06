import os
import tempfile
from pathlib import Path


_test_directory = tempfile.TemporaryDirectory(prefix="agentic-sdlc-tests-")
os.environ["WORKBENCH_DATABASE_URL"] = (
    f"sqlite:///{Path(_test_directory.name) / 'workbench.db'}"
)
os.environ["WORKBENCH_AGENT_IDENTITY_DIR"] = str(
    Path(_test_directory.name) / "identities")
