from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def load_data(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Data file not found: {p.resolve()}")

    suffix = p.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(p, dtype=str)
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(p, dtype=str)
    else:
        raise ValueError(f"Unsupported data format: {suffix}")

    df = df.fillna("")
    return df.to_dict(orient="records")


def validate_columns(records: list[dict], layout: dict) -> list[str]:
    """Return list of missing column names (layout keys absent in data)."""
    if not records:
        return []
    present = set(records[0].keys())
    return [k for k in layout if not k.startswith("_") and k not in present]
