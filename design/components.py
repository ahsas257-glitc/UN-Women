from __future__ import annotations

import html
from typing import List, Dict

import streamlit as st


def liquid_glass_intro() -> None:
    """A short design primer shown at the top of the app."""
    st.markdown(
        """
        """,
        unsafe_allow_html=True,
    )


def glass_header(title: str, subtitle: str = "") -> None:
    title = html.escape(title)
    subtitle = html.escape(subtitle)
    st.markdown(
        f"""
        <div class="lg-glass lg-lift" style="padding: 16px 18px; margin: 0 0 14px 0;">
          <div style="font-size: 18px; font-weight: 750; letter-spacing: -0.01em;">{title}</div>
          {f'<div style="margin-top:6px; font-size: 13px; color: var(--lg-muted);">{subtitle}</div>' if subtitle else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def glass_divider() -> None:
    st.markdown(
        """
        <div style="height: 14px;"></div>
        <div style="height: 1px; background: rgba(255,255,255,0.10); border-radius: 99px;"></div>
        <div style="height: 14px;"></div>
        """,
        unsafe_allow_html=True,
    )


def kpi_row(items: List[Dict]) -> None:
    """Render KPIs using Streamlit metrics (styled globally via CSS)."""
    cols = st.columns(len(items), gap="large")
    for c, it in zip(cols, items):
        c.metric(it["label"], it["value"], help=it.get("hint", ""))


def liquid_glass_footer() -> None:
    """Full-width footer (Streamlit has no native footer styling hooks)."""
    st.markdown(
        """
        <div class="lg-footer-wrap">
          <div class="lg-glass lg-footer lg-shimmer">
            <div class="lg-footer-title">UN Women •Dashboard</div>
            <div class="lg-footer-sub">
              Built by Shabeer Ahmad Ahsas, Streamlit • Glass UI • Smart charts • Secure Google Sheets integration
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
