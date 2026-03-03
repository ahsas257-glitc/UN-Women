from __future__ import annotations

import streamlit as st

from pages.updater_page import render_updater
from pages.dashboard_page import render_dashboard
from pages.report_page import render_report

from ui import apply_ui, inject_fonts, enable_altair_theme, liquid_glass_intro, liquid_glass_footer


TOOLS = [
    "GWO-Beneficiaries",
    "PTCRO-Beneficiaries",
    "GSRO-Beneficiaries",
    "HOSAA-Beneficiaries",
    "HHSO-Beneficiaries",
    "ADSDO-Beneficiaries",
    "ASPSO-Beneficiaries",
]

PAGES = ["Updater", "Dashboard", "Report"]


def main() -> None:
    st.set_page_config(page_title="UN Women - Liquid Glass", layout="wide", initial_sidebar_state="expanded")

    # Global styling (safe to call on every run)
    inject_fonts()
    apply_ui()
    enable_altair_theme()

    spreadsheet_id = st.secrets.get("GSHEET_ID", "")
    if not spreadsheet_id:
        st.error("GSHEET_ID is missing in secrets.")
        return

    with st.sidebar:
        st.markdown("### Navigation")
        page = st.radio("Page", PAGES, index=0)
        tool = st.selectbox("Select Tool", TOOLS, index=0)

    # Hero / introduction
    liquid_glass_intro()

    if page == "Updater":
        render_updater(spreadsheet_id)
    elif page == "Dashboard":
        render_dashboard(spreadsheet_id, tool)
    elif page == "Report":
        render_report(spreadsheet_id, tool)
    else:
        st.info("Select a page from the sidebar.")

    # Footer (keeps the design complete: sidebar + body + footer)
    liquid_glass_footer()


if __name__ == "__main__":
    main()
