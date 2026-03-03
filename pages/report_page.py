from __future__ import annotations

import streamlit as st
import pandas as pd

from core.repo import load_df
from core.report_engine import build_summary, to_csv_bytes, to_excel_bytes, to_word_bytes
from ui import glass_header, glass_divider


def _safe_filename(name: str) -> str:
    keep = []
    for ch in name:
        if ch.isalnum() or ch in {"-", "_", "."}:
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep).strip("_") or "report"


def render_report(spreadsheet_id: str, tool: str) -> None:
    glass_header(
        "Report",
        "One-click exports (CSV / Excel / Word) + a clean executive snapshot.",
    )

    df = load_df(spreadsheet_id, tool)
    if df.empty:
        st.info("No data found in this sheet.")
        return

    # Basic hygiene: avoid extremely wide preview
    if len(df.columns) > 220:
        df = df.iloc[:, :220]

    summary = build_summary(df)

    c1, c2, c3, c4 = st.columns(4, gap="large")
    c1.metric("Rows", f"{len(df):,}")
    c2.metric("Columns", f"{len(df.columns):,}")
        # Fast cell completeness estimate (sampled columns)
    sample_cols = list(df.columns[: min(80, len(df.columns))])
    nonempty = 0
    for c in sample_cols:
        s = df[c]
        if s.dtype == object:
            ss = s.astype(str).replace({"nan": "", "None": ""}).str.strip()
            nonempty += int((ss != "").sum())
        else:
            nonempty += int(s.notna().sum())
    est_scale = len(df.columns) / max(1, len(sample_cols))
    filled_est = int(round(nonempty * est_scale))
    total_cells = int(len(df) * len(df.columns))
    missing_est = max(0, total_cells - filled_est)

    c3.metric("Filled cells (est.)", f"{filled_est:,}")
    c4.metric("Missing cells (est.)", f"{missing_est:,}")

    glass_divider()

    st.markdown("#### Executive summary")
    s_df = pd.DataFrame({"Metric": list(summary.keys()), "Value": list(summary.values())})
    st.dataframe(s_df, use_container_width=True, hide_index=True)

    glass_divider()

    st.markdown("#### Export")
    base = _safe_filename(tool)
    b1, b2, b3 = st.columns(3, gap="large")
    with b1:
        st.download_button(
            "Download CSV",
            data=to_csv_bytes(df),
            file_name=f"{base}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with b2:
        st.download_button(
            "Download Excel (data + summary)",
            data=to_excel_bytes(df, summary),
            file_name=f"{base}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with b3:
        st.download_button(
            "Download Word report",
            data=to_word_bytes(tool, df, summary),
            file_name=f"{base}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )

    glass_divider()

    st.markdown("#### Smart preview")
    left, right = st.columns([1.2, 1], gap="large")

    with left:
        st.markdown("##### Data")
        st.dataframe(df.head(300), use_container_width=True, height=520)

    with right:
        st.markdown("##### Column health")
        filled = (
            df.astype(str)
            .replace({"nan": "", "None": ""})
            .apply(lambda s: (s.str.strip() != "").sum())
            .sort_values(ascending=False)
        )
        out = pd.DataFrame(
            {
                "Column": filled.index,
                "Filled": filled.values,
                "Filled %": (filled.values / max(1, len(df)) * 100.0).round(1),
            }
        )
        st.dataframe(out.head(40), use_container_width=True, hide_index=True, height=520)
