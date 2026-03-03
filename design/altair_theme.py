from __future__ import annotations

import altair as alt


def enable_altair_theme() -> None:
    """Register + enable a compact theme that renders well inside Streamlit.

    The theme is intentionally conservative to avoid runtime issues across Altair versions.
    """

    def _theme():
        return {
            "config": {
                "background": "transparent",
                "view": {"stroke": "transparent"},
                "font": "Inter",
                "axis": {
                    "labelFontSize": 12,
                    "titleFontSize": 12,
                    "labelColor": "rgba(255,255,255,0.82)",
                    "titleColor": "rgba(255,255,255,0.78)",
                    "domainColor": "rgba(255,255,255,0.16)",
                    "gridColor": "rgba(255,255,255,0.10)",
                    "gridOpacity": 0.35,
                    "tickOpacity": 0.6,
                },
                "legend": {
                    "labelFontSize": 12,
                    "titleFontSize": 12,
                    "labelColor": "rgba(255,255,255,0.78)",
                    "titleColor": "rgba(255,255,255,0.78)",
                },
                "title": {"fontSize": 14, "anchor": "start", "color": "rgba(255,255,255,0.88)"},
                "range": {
                    "category": [
                        "#7aa2ff",
                        "#ff7ac8",
                        "#5affd6",
                        "#f5b14c",
                        "#a78bfa",
                        "#34d399",
                        "#f472b6",
                        "#60a5fa",
                    ]
                },
                "mark": {"tooltip": True},
            }
        }

    # Idempotent registration
    try:
        alt.themes.register("unw_glass", _theme)
    except Exception:
        # Already registered
        pass

    try:
        alt.themes.enable("unw_glass")
    except Exception:
        # If enabling fails for any reason, keep default theme.
        return

