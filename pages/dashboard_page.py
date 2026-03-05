from __future__ import annotations

import importlib
import streamlit as st

from ui import glass_header, glass_divider
from core.generic_dashboard import render_generic_dashboard


_TOOL_MODULE_MAP = {
    # Tool label in sidebar -> python module
    "GWO-Beneficiaries": "tools.gwo_beneficiaries.dashboard",
    "PTCRO-Beneficiaries": "tools.ptcro_beneficiaries.dashboard",
    "GSRO-Beneficiaries": "tools.gsro_beneficiaries.dashboard",
    "HOSAA-Beneficiaries": "tools.hosaa_beneficiaries.dashboard",
    "ASPSO-Beneficiaries": "tools.aspso_beneficiaries.dashboard",
}


def _render_tool_dashboard(spreadsheet_id: str, tool: str) -> bool:
    """Try to render a tool-specific dashboard.

    Returns True if rendered.
    """
    mod_name = _TOOL_MODULE_MAP.get(tool)
    if not mod_name:
        return False

    try:
        mod = importlib.import_module(mod_name)
    except Exception as e:
        st.error(f"Could not import dashboard module '{mod_name}': {e}")
        return False

    # Convention: module exposes `render(spreadsheet_id, sheet_name)` or `render_dashboard(...)`.
    for name in ("render", "render_dashboard", "main"):
        fn = getattr(mod, name, None)
        if callable(fn):
            fn(spreadsheet_id, tool)
            return True

    st.warning(f"Dashboard module '{mod_name}' is missing a render function.")
    return False


def render_dashboard(spreadsheet_id: str, tool: str) -> None:
    glass_header("Dashboard", "interactive analytics")

    # Tabbed experience feels more 'product-like'
    t1, t2 = st.tabs(["Insights", "Data Explorer"])

    with t1:
        rendered = _render_tool_dashboard(spreadsheet_id, tool)
        if not rendered:
            st.info("Tool-specific dashboard not found. Showing generic dashboard.")
            glass_divider()
            render_generic_dashboard(spreadsheet_id, tool)

    with t2:
        from core.repo import load_df

        df = load_df(spreadsheet_id, tool)
        if df.empty:
            st.info("No data found.")
            return

        st.markdown("#### Smart filters")
        # Lightweight explorer: pick up to 3 columns for quick filtering
        cols = list(df.columns)
        pick = st.multiselect("Filter columns", cols, default=cols[:2], max_selections=3)
        qdf = df
        for c in pick:
            uniq = sorted([x for x in df[c].astype(str).unique().tolist() if str(x).strip()])
            if len(uniq) == 0 or len(uniq) > 300:
                continue
            sel = st.multiselect(f"{c}", uniq, default=[])
            if sel:
                qdf = qdf[qdf[c].astype(str).isin(sel)]

        glass_divider()
        st.markdown(f"#### Preview ({len(qdf):,} rows)")
        st.dataframe(qdf, use_container_width=True, height=520)