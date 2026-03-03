from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Set, Tuple
import re
import uuid

import pandas as pd

UUID_COL = "_uuid"


# -----------------------------
# Label normalization (robust)
# -----------------------------
def _norm_label(x: Any) -> str:
    if x is None:
        return ""
    s = str(x)

    # Normalize unicode whitespace
    s = s.replace("\u00A0", " ")  # NBSP
    s = s.replace("\u2007", " ")  # figure space
    s = s.replace("\u202F", " ")  # narrow NBSP

    s = s.strip()
    s = re.sub(r"\s+", " ", s)    # collapse spaces
    return s


def _clean_str_series(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .replace({"nan": "", "NaN": "", "None": "", "<NA>": "", "N/A": ""})
        .str.strip()
    )


def _find_duplicate_labels(header: List[str]) -> List[str]:
    seen: Dict[str, int] = {}
    dup: List[str] = []
    for h in header:
        k = _norm_label(h)
        seen[k] = seen.get(k, 0) + 1
    for k, cnt in seen.items():
        if k and cnt > 1:
            dup.append(k)
    return dup


def _build_upload_map(upload_cols: List[str]) -> Dict[str, str]:
    """
    normalized(label) -> original column name in upload df
    If duplicates after normalization exist, keep the FIRST one.
    """
    m: Dict[str, str] = {}
    for c in upload_cols:
        key = _norm_label(c)
        if key and key not in m:
            m[key] = c
    return m


@dataclass
class PrepareResult:
    aligned_df: pd.DataFrame
    rows_to_append: List[List[Any]]
    generated_uuid_count: int
    skipped_existing_uuid_count: int
    unmatched_dest_labels: List[str]   # dest columns that were not found in Excel
    unused_upload_labels: List[str]    # excel columns that were not used


def read_excel_tool_sheet(file_bytes: bytes, tool_sheet_name: str) -> pd.DataFrame:
    return pd.read_excel(file_bytes, sheet_name=tool_sheet_name, engine="openpyxl")


def ensure_uuid_in_header(header: List[str]) -> Tuple[List[str], bool]:
    header = [str(h) for h in header if str(h).strip() != ""]
    if UUID_COL in header:
        return header, False
    return header + [UUID_COL], True


def align_to_header(upload_df: pd.DataFrame, dest_header: List[str]) -> Tuple[pd.DataFrame, List[str], List[str]]:
    """
    Output DF columns EXACTLY == dest_header (same labels/order).
    Uses normalized label matching from upload_df.
    """
    upload_df = upload_df.copy()
    upload_df.columns = [str(c) for c in upload_df.columns]

    upload_map = _build_upload_map(list(upload_df.columns))
    used_upload_norm: Set[str] = set()

    out = pd.DataFrame(index=upload_df.index)
    unmatched_dest: List[str] = []

    for dest_col in dest_header:
        dest_col_str = str(dest_col)
        key = _norm_label(dest_col_str)

        if key in upload_map:
            src = upload_map[key]
            out[dest_col_str] = upload_df[src]
            used_upload_norm.add(key)
        else:
            out[dest_col_str] = ""
            unmatched_dest.append(dest_col_str)

    # Upload columns not used
    unused_upload = []
    for c in upload_df.columns:
        k = _norm_label(c)
        if k and k not in used_upload_norm:
            unused_upload.append(c)

    return out, unmatched_dest, unused_upload


def existing_uuid_set(dest_df: pd.DataFrame) -> Set[str]:
    if UUID_COL not in dest_df.columns:
        return set()
    s = _clean_str_series(dest_df[UUID_COL])
    return {x for x in s.tolist() if x}


def prepare_append_rows(aligned_df: pd.DataFrame, existing_uuids: Set[str]) -> Tuple[List[List[Any]], int, int, pd.DataFrame]:
    df = aligned_df.copy()

    if UUID_COL not in df.columns:
        df[UUID_COL] = ""

    uu = _clean_str_series(df[UUID_COL])

    generated = 0
    skipped = 0
    rows_out: List[List[Any]] = []

    for i in range(len(df)):
        u = uu.iloc[i]

        if not u:
            u = str(uuid.uuid4())
            df.at[i, UUID_COL] = u
            uu.iat[i] = u
            generated += 1

        if u in existing_uuids:
            skipped += 1
            continue

        rows_out.append(df.iloc[i].tolist())

    return rows_out, generated, skipped, df


def prepare_update(upload_df: pd.DataFrame, dest_header: List[str], existing_uuids: Set[str]) -> PrepareResult:
    # Safety: if destination has duplicate labels, mapping is ambiguous -> stop.
    dups = _find_duplicate_labels(dest_header)
    if dups:
        raise ValueError(f"Destination header has duplicate labels after normalization: {dups}")

    aligned_df, unmatched_dest, unused_upload = align_to_header(upload_df, dest_header)

    rows_to_append, generated, skipped, aligned_with_uuid = prepare_append_rows(aligned_df, existing_uuids)

    return PrepareResult(
        aligned_df=aligned_with_uuid,
        rows_to_append=rows_to_append,
        generated_uuid_count=generated,
        skipped_existing_uuid_count=skipped,
        unmatched_dest_labels=unmatched_dest,
        unused_upload_labels=unused_upload,
    )