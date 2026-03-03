from __future__ import annotations

from typing import Any, List
from datetime import datetime, date

import streamlit as st
import gspread
import pandas as pd
import numpy as np
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@st.cache_resource(show_spinner=False)
def _client() -> gspread.Client:
    sa = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(sa, scopes=SCOPES)
    return gspread.authorize(creds)


@st.cache_resource(show_spinner=False)
def _spreadsheet(spreadsheet_id: str):
    return _client().open_by_key(spreadsheet_id)


def _worksheet(spreadsheet_id: str, sheet_name: str) -> gspread.Worksheet:
    sh = _spreadsheet(spreadsheet_id)
    return sh.worksheet(sheet_name)


def get_header(spreadsheet_id: str, sheet_name: str) -> List[str]:
    ws = _worksheet(spreadsheet_id, sheet_name)
    header = ws.row_values(1)
    return [str(x) for x in header]


# -----------------------------
# HARDENED SERIALIZATION LAYER
# -----------------------------
def _is_missing(x: Any) -> bool:
    if x is None:
        return True
    try:
        return bool(pd.isna(x))
    except Exception:
        return False


def _gs_cell(x: Any) -> Any:
    """Convert any python/pandas/numpy value to JSON-serializable Google Sheets cell."""
    if _is_missing(x):
        return ""

    # pandas Timestamp
    if isinstance(x, pd.Timestamp):
        return x.strftime("%Y-%m-%d %H:%M:%S")

    # numpy datetime64
    if isinstance(x, np.datetime64):
        ts = pd.to_datetime(x, errors="coerce")
        if _is_missing(ts):
            return ""
        return ts.strftime("%Y-%m-%d %H:%M:%S")

    # python datetime/date
    if isinstance(x, datetime):
        return x.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(x, date):
        return x.strftime("%Y-%m-%d")

    # timedeltas
    if isinstance(x, (pd.Timedelta, np.timedelta64)):
        return str(x)

    # numpy scalars -> python scalars
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)

    # primitives
    if isinstance(x, (str, int, float, bool)):
        return x

    # fallback
    return str(x)


def _sanitize_rows(rows: List[List[Any]]) -> List[List[Any]]:
    return [[_gs_cell(v) for v in row] for row in rows]


# -----------------------------
# WRITE OPERATIONS (safe)
# -----------------------------
def update_header(spreadsheet_id: str, sheet_name: str, header: List[str]) -> None:
    ws = _worksheet(spreadsheet_id, sheet_name)
    safe_header = [str(h) for h in header]
    ws.update("1:1", [safe_header])


def read_values(spreadsheet_id: str, a1_range: str) -> List[List[Any]]:
    # a1_range: "SheetName!A:ZZ"
    sheet_name, rng = a1_range.split("!", 1)
    ws = _worksheet(spreadsheet_id, sheet_name)
    return ws.get(rng)


def append_rows(spreadsheet_id: str, sheet_name: str, rows: List[List[Any]]) -> None:
    if not rows:
        return
    ws = _worksheet(spreadsheet_id, sheet_name)
    safe_rows = _sanitize_rows(rows)
    ws.append_rows(safe_rows, value_input_option="USER_ENTERED")