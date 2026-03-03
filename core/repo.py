from __future__ import annotations

from typing import List
import pandas as pd
import streamlit as st

from services.gsheet_client import read_values
from core.utils_df import normalize_df, make_unique_columns


def _values_to_df(values: List[List[object]]) -> pd.DataFrame:
    if not values:
        return pd.DataFrame()

    header = make_unique_columns([str(x) for x in values[0]])
    n_cols = len(header)

    data = values[1:] if len(values) > 1 else []
    fixed_rows: List[List[object]] = []

    for r in data:
        r = list(r) if r is not None else []
        if len(r) < n_cols:
            r = r + [""] * (n_cols - len(r))
        elif len(r) > n_cols:
            r = r[:n_cols]
        fixed_rows.append(r)

    return normalize_df(pd.DataFrame(fixed_rows, columns=header))


@st.cache_data(ttl=300)
def load_destination_df(spreadsheet_id: str, sheet_name: str) -> pd.DataFrame:
    values = read_values(spreadsheet_id, f"{sheet_name}!A:ZZ")
    return _values_to_df(values)


# Backward-compatible alias used by pages/report_page.py
@st.cache_data(ttl=300)
def load_df(spreadsheet_id: str, sheet_name: str) -> pd.DataFrame:
    """Load a Google Sheet tab into a DataFrame.

    This keeps the app stable even if pages import `load_df`.
    """
    return load_destination_df(spreadsheet_id, sheet_name)