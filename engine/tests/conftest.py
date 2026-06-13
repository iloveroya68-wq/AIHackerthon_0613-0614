from __future__ import annotations

import sys
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ENGINE_ROOT.parent

for path in (REPO_ROOT, ENGINE_ROOT):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)
