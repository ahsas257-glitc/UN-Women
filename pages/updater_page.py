from __future__ import annotations

import pandas as pd
import streamlit as st

from core.updater_logic import (
    ensure_uuid_in_header,
    existing_uuid_set,
    prepare_update,
    read_excel_tool_sheet,
)
from services.gsheet_client import append_rows, get_header, update_header
from ui import glass_divider, glass_header


def render_updater(spreadsheet_id: str) -> None:
    """Upload an Excel export and append new rows into a Google Sheet tab."""

    glass_header(
        "Updater",
        "Upload an Excel file",
    )

    with st.container():
        st.markdown("#### 1) Select destination tab")
        tool = st.selectbox(
            "Destination Google Sheet tab",
            [
                "GWO-Beneficiaries",
                "PTCRO-Beneficiaries",
                "GSRO-Beneficiaries",
                "HOSAA-Beneficiaries",
                "HHSO-Beneficiaries",
                "ADSDO-Beneficiaries",
                "aspso-beneficiaries",
            ],
            index=0,
            key="updater_tool",
        )

    glass_divider()

    with st.container():
        st.markdown("#### 2) Upload Excel")
        file = st.file_uploader("Excel file", type=["xlsx"], accept_multiple_files=False)
        if not file:
            st.info("Upload an .xlsx file to continue.")
            return

        file_bytes = file.read()

        try:
            xl = pd.ExcelFile(file_bytes, engine="openpyxl")
            sheet_names = xl.sheet_names
        except Exception as e:
            st.error(f"Could not read the Excel file: {e}")
            return

        excel_sheet = st.selectbox("Excel sheet to import", sheet_names, index=0)

    glass_divider()

    st.markdown("#### 3) Preview + append")

    # Read destination header from Google Sheets
    try:
        dest_header = get_header(spreadsheet_id, tool)
    except Exception as e:
        st.error(f"Could not read destination header from Google Sheets: {e}")
        return

    if not dest_header:
        st.error("Destination header is empty. Please ensure the selected tab has a header row.")
        return

    # Ensure UUID column exists in destination header
    dest_header, header_added_uuid = ensure_uuid_in_header(dest_header)

    # Read the selected Excel sheet
    try:
        upload_df = read_excel_tool_sheet(file_bytes, excel_sheet)
    except Exception as e:
        st.error(f"Could not read the selected sheet from Excel: {e}")
        return

    # Load existing UUIDs (if present) to prevent double-appends
    try:
        from core.repo import load_df

        dest_df = load_df(spreadsheet_id, tool)
        uuids = existing_uuid_set(dest_df)
    except Exception:
        uuids = set()

    # Align upload to destination header + compute append rows
    try:
        res = prepare_update(upload_df, dest_header, uuids)
    except Exception as e:
        st.error(f"Alignment failed: {e}")
        return

    c1, c2, c3, c4 = st.columns(4, gap="large")
    c1.metric("Upload rows", f"{len(upload_df):,}")
    c2.metric("Ready to append", f"{len(res.rows_to_append):,}")
    c3.metric("UUIDs generated", f"{res.generated_uuid_count:,}")
    c4.metric("Skipped (duplicate UUID)", f"{res.skipped_existing_uuid_count:,}")

    if res.unmatched_dest_labels:
        st.warning(
            "These destination columns were not found in Excel and will be appended as empty values:\n\n"
            + "\n".join([f"- {x}" for x in res.unmatched_dest_labels[:40]])
            + ("\n..." if len(res.unmatched_dest_labels) > 40 else "")
        )

    if res.unused_upload_labels:
        st.info(
            "These Excel columns are not present in the destination header and will be ignored:\n\n"
            + "\n".join([f"- {x}" for x in res.unused_upload_labels[:40]])
            + ("\n..." if len(res.unused_upload_labels) > 40 else "")
        )

    st.markdown("##### Aligned preview (first 200 rows)")
    st.dataframe(res.aligned_df.head(200), use_container_width=True)

    glass_divider()

    disabled = len(res.rows_to_append) == 0
    if st.button("Append rows to Google Sheet", type="primary", disabled=disabled):
        try:
            if header_added_uuid:
                update_header(spreadsheet_id, tool, dest_header)

            append_rows(spreadsheet_id, tool, res.rows_to_append)
            st.success(f"Appended {len(res.rows_to_append):,} rows to '{tool}'.")
        except Exception as e:
            st.error(f"Append failed: {e}")