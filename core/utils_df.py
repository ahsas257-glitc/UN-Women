from __future__ import annotations

from typing import Iterable, List, Tuple, Any, Dict
import pandas as pd


def make_unique_columns(cols: Iterable[Any], sep: str = "__") -> List[str]:
    """Return unique column names.

    If duplicate names exist, suffixes are appended: col, col__1, col__2, ...
    This prevents pandas from returning a Series when indexing a row with a duplicate label.
    """
    seen: Dict[str, int] = {}
    out: List[str] = []
    for c in cols:
        base = "" if c is None else str(c)
        base = base.strip()
        if base == "":
            base = "col"
        if base not in seen:
            seen[base] = 0
            out.append(base)
        else:
            seen[base] += 1
            out.append(f"{base}{sep}{seen[base]}")
    return out


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Lightweight DF hygiene used across the app."""
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df
    # Ensure unique columns (critical for avoiding Series truth-value errors)
    if df.columns.has_duplicates:
        df = df.copy()
        df.columns = make_unique_columns(df.columns)
    return df
