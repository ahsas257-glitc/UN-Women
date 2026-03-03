"""UI facade.

Tool dashboards import from a `ui` package. The core app ships a `design` package.
This module re-exports the design system so dashboards can import from `ui`
without breaking.
"""

from __future__ import annotations

from design.theme import apply_ui, inject_fonts
from design.altair_theme import enable_altair_theme
from design.components import glass_header, glass_divider, kpi_row, liquid_glass_intro, liquid_glass_footer

__all__ = [
    "apply_ui",
    "inject_fonts",
    "enable_altair_theme",
    "glass_header",
    "glass_divider",
    "kpi_row",
    "liquid_glass_intro",
    "liquid_glass_footer",
]
