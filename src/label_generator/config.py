from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_layout(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Layout file not found: {p.resolve()}")
    with p.open(encoding="utf-8") as f:
        return json.load(f)
