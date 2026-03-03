from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from core.repo import load_df
from ui import glass_header, glass_divider, kpi_row


def _clean_text(s: pd.Series) -> pd.Series:
    return s.astype(str).replace({"nan": "", "None": ""}).str.strip()


def _value_counts_df(series: pd.Series, top_n: int = 10) -> pd.DataFrame:
    s = _clean_text(series)
    s = s[s != ""]
    if s.empty:
        return pd.DataFrame(columns=["category", "count", "pct"])
    vc = s.value_counts().reset_index()
    vc.columns = ["category", "count"]
    if len(vc) > top_n:
        vc = vc.head(top_n)
    total = int(vc["count"].sum())
    vc["pct"] = vc["count"] / max(1, total)
    return vc


def _bar(df_: pd.DataFrame, title: str) -> alt.Chart:
    if df_.empty:
        return alt.Chart(pd.DataFrame({"category": [], "count": []})).mark_bar().properties(title=title)
    return (
        alt.Chart(df_)
        .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
        .encode(
            x=alt.X("category:N", sort="-y", title=""),
            y=alt.Y("count:Q", title="Count"),
            tooltip=[
                alt.Tooltip("category:N", title="Category"),
                alt.Tooltip("count:Q", title="Count"),
                alt.Tooltip("pct:Q", title="Share", format=".1%"),
            ],
        )
        .properties(height=280, title=title)
    )


def _trend(df: pd.DataFrame, start_col: str) -> alt.Chart | None:
    if start_col not in df.columns:
        return None
    ts = pd.to_datetime(df[start_col], errors="coerce")
    tmp = df.copy()
    tmp["_dt"] = ts
    tmp = tmp[tmp["_dt"].notna()]
    if tmp.empty:
        return None
    g = tmp.groupby(tmp["_dt"].dt.date).size().reset_index(name="count")
    g.columns = ["day", "count"]
    base = alt.Chart(g).encode(
        x=alt.X("day:T", title="Date"),
        y=alt.Y("count:Q", title="Records"),
        tooltip=[alt.Tooltip("day:T", title="Date"), alt.Tooltip("count:Q", title="Count")],
    )
    return (base.mark_area(opacity=0.16) + base.mark_line(strokeWidth=3) + base.mark_circle(size=70)).properties(
        height=280,
        title="Daily Record Volume",
    )


def render_generic_dashboard(spreadsheet_id: str, sheet_name: str) -> None:
    df = load_df(spreadsheet_id, sheet_name)
    if df.empty:
        st.info("No data found in this sheet.")
        return

    glass_header("Generic Dashboard", "Automatic overview when a tool-specific dashboard is not available")

    total = len(df)
    cols = list(df.columns)
    kpi_row(
        [
            {"label": "Total records", "value": f"{total:,}", "hint": "All rows loaded"},
            {"label": "Columns", "value": str(len(cols)), "hint": "Schema width"},
            {"label": "Non-empty cells", "value": f"{int((df.astype(str).replace({'nan':'','None':''}).ne('')).sum().sum()):,}", "hint": "Filled values"},
            {"label": "Missing cells", "value": f"{int((df.astype(str).replace({'nan':'','None':''}).eq('')).sum().sum()):,}", "hint": "Empty strings"},
        ]
    )

    glass_divider()

    # Trend if a timestamp-like column exists
    start_candidates = [c for c in cols if c.lower() in {"start", "timestamp", "date", "created_at"}]
    start_col = start_candidates[0] if start_candidates else cols[0]
    ch = _trend(df, start_col)
    if ch is not None:
        st.altair_chart(ch, use_container_width=True)
        glass_divider()

    # Top categories for the first few text columns
    text_cols = [c for c in cols if df[c].dtype == object][:6]
    if not text_cols:
        st.info("No categorical columns detected.")
    else:
        cc = st.columns(min(2, len(text_cols)), gap="large")
        for i, col in enumerate(text_cols[:2]):
            vc = _value_counts_df(df[col], top_n=8)
            with cc[i % 2]:
                st.altair_chart(_bar(vc, f"Top values - {col}"), use_container_width=True)

    glass_divider()
    st.markdown("#### Data preview")
    st.dataframe(df.head(250), use_container_width=True)
