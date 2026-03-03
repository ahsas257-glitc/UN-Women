from __future__ import annotations

import re
from typing import Dict, List, Tuple

import altair as alt
import pandas as pd
import streamlit as st

from services.gsheet_client import read_values

# UI (centralized design system)
from ui import apply_ui, inject_fonts, enable_altair_theme
from ui import glass_header, glass_divider, kpi_row
from ui.tokens import STATUS_PALETTE, PALETTE


# ============================================================
# COLUMN NAMES (match Google Sheet headers)
# ============================================================
COL_START = "start"
COL_SURVEYOR = "Surveyor Name:"
COL_PROVINCE = "Province"
COL_DISTRICT = "District"
COL_VILLAGE = "Village name:"

COL_CONSENT = "Does the person consent to participate?"
COL_RECORD = "For note-taking/quality assurance, may we record the interview?"

COL_AGE = "Age group"
COL_GENDER = "Confirm gender"
COL_MARITAL = "Confirm marital status"
COL_EDU = "Level of education"
COL_EMP = "Employment status"
COL_HH = "Number of household members"
COL_INCOME = "Average income per month (local currency)"

COL_TRAIN_ATTEND = "Did you attend a training under this project?"
COL_SESSIONS = "How many sessions did you attend?"
COL_DURATION = "Approximately how long did the training last?"
COL_TOPICS = "Which of the following topics were covered? (Select all mentioned)"

COL_KIT = "Did you receive a production kit?"
COL_KIT_RECEIVE_TIME = "When did you receive the kit?"

KIT_ITEMS_IN_ORDER = [
    "Aluminum cooking pot",
    "Gas stove",
    "Gas cylinder",
    "Glass jars",
    "Knives",
    "Plastic bucket",
    "Hand mixer",
    "Table",
]

COL_PRODUCING = "Are you currently producing paste or pickles?"
COL_PRODUCE_FREQ = "How often do you produce?"
COL_SELL_WHERE = "Where do you sell? (Select all that apply)"

COL_HYGIENE = "Are hygiene practices being followed?"
COL_HYGIENE_WHYNO = "If no, why? (Select all that apply)"
WHYNO_PREFIX = "If no, why? (Select all that apply)/"

COL_MARKET_INFO = "Were you given information about markets or shopkeepers?"
COL_INTRO_BUYERS = "Did GWO introduce you to any buyers?"
COL_HELPFUL = "Was this helpful?"

COL_CHANGES = "Has this activity helped you in any way? (Select all that apply)"

COL_FAMILY_SUPPORT = "Did your family support your participation?"
COL_CONCERNS_TEXT = "Have there been any concerns from family or community? (Open-ended)"
COL_INFORMED_CONCERNS = "Were you informed how to raise concerns?"
COL_KNOW_CONTACT = "Do you know whom to contact if you have a complaint?"

COL_ID = "_id"
COL_UUID = "_uuid"


# ============================================================
# DATA UTILS (fast + safe)
# ============================================================
def _values_to_df(values: List[List[object]]) -> pd.DataFrame:
    if not values:
        return pd.DataFrame()
    header = [str(x) for x in values[0]]
    data = values[1:] if len(values) > 1 else []

    # Ensure all rows match header length
    n = len(header)
    fixed = []
    for r in data:
        r = list(r) if r is not None else []
        if len(r) < n:
            r = r + [""] * (n - len(r))
        elif len(r) > n:
            r = r[:n]
        fixed.append(r)
    return pd.DataFrame(fixed, columns=header)


def _make_unique_columns(cols: List[str]) -> List[str]:
    seen: Dict[str, int] = {}
    out: List[str] = []
    for c in cols:
        c = str(c)
        if c not in seen:
            seen[c] = 0
            out.append(c)
        else:
            seen[c] += 1
            out.append(f"{c}__{seen[c]}")
    return out


def _clean_text_series(s: pd.Series) -> pd.Series:
    s = s.astype(str).replace({"nan": "", "None": ""})
    return s.str.strip()


def _norm_bool(x) -> str:
    s = str(x).strip().lower()
    if s in {"yes", "y", "true", "1"}:
        return "Yes"
    if s in {"no", "n", "false", "0"}:
        return "No"
    if s in {"partly", "partial"}:
        return "Partly"
    if s in {"", "nan", "none"}:
        return ""
    return str(x).strip()


def _to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _split_multiselect(val: str) -> List[str]:
    if val is None:
        return []
    s = str(val).strip()
    if not s or s.lower() in {"nan", "none"}:
        return []
    parts = re.split(r"\s*[,;|/]\s*", s)
    return [p.strip() for p in parts if p.strip()]


def _multiselect_counts(series: pd.Series) -> pd.DataFrame:
    counts: Dict[str, int] = {}
    s = _clean_text_series(series)
    s = s[s != ""]
    for v in s:
        for item in _split_multiselect(v):
            counts[item] = counts.get(item, 0) + 1
    if not counts:
        return pd.DataFrame(columns=["category", "count", "pct"])
    out = pd.DataFrame({"category": list(counts.keys()), "count": list(counts.values())})
    out = out.sort_values("count", ascending=False)
    out["pct"] = out["count"] / max(1, out["count"].sum())
    return out


def _safe_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        return df[col]
    return pd.Series([""] * len(df), index=df.index)


def _kit_pairs_from_columns(df: pd.DataFrame) -> Dict[str, Tuple[str, str]]:
    cols = list(df.columns)
    qty_cols = [c for c in cols if str(c).startswith("Quantity reported")]
    pairs: Dict[str, Tuple[str, str]] = {}
    for item in KIT_ITEMS_IN_ORDER:
        if item not in cols:
            continue
        i = cols.index(item)
        q = None
        for qc in qty_cols:
            if cols.index(qc) > i:
                q = qc
                break
        if q:
            pairs[item] = (item, q)
    return pairs


def _value_counts_df(series: pd.Series, top_n: int = 10, other_label: str = "Other") -> pd.DataFrame:
    s = _clean_text_series(series)
    s = s[s != ""]
    if s.empty:
        return pd.DataFrame(columns=["category", "count", "pct"])

    vc = s.value_counts().reset_index()
    vc.columns = ["category", "count"]
    vc["category"] = vc["category"].astype(str)

    vc = vc.sort_values("count", ascending=False).reset_index(drop=True)
    if len(vc) > top_n:
        top = vc.head(top_n).copy()
        other_count = int(vc.iloc[top_n:]["count"].sum())
        top = pd.concat([top, pd.DataFrame([{"category": other_label, "count": other_count}])], ignore_index=True)
        vc = top

    total = int(vc["count"].sum())
    vc["pct"] = vc["count"] / max(1, total)
    return vc


def _numeric_summary(series: pd.Series) -> Dict:
    s = _to_num(series).dropna()
    if s.empty:
        return {}
    return {
        "mean": float(s.mean()),
        "median": float(s.median()),
        "min": float(s.min()),
        "max": float(s.max()),
        "std": float(s.std()),
    }


def _format_mdy(ts: pd.Timestamp) -> str:
    if ts is None or pd.isna(ts):
        return ""
    # Cross-platform: %-m (unix) vs %#m (windows)
    for fmt in ("%-m/%-d/%Y", "%#m/%#d/%Y", "%m/%d/%Y"):
        try:
            return ts.strftime(fmt)
        except Exception:
            continue
    return ""


# ============================================================
# FAST NON-ENGLISH DETECTOR (translation need)
# ============================================================
def _is_non_english_text(x) -> bool:
    s = str(x).strip()
    if not s or s.lower() == "nan":
        return False
    return any(ord(ch) > 127 for ch in s)


def _non_english_profile(df: pd.DataFrame, max_cols: int = 120) -> pd.DataFrame:
    cols = list(df.columns)[:max_cols]
    rows = []
    for c in cols:
        s = _clean_text_series(df[c])
        s = s[s != ""]
        if s.empty:
            continue
        non_en = int(s.map(_is_non_english_text).sum())
        if non_en == 0:
            continue
        filled = int(len(s))
        rows.append(
            {
                "Column": c,
                "Non-English cells": non_en,
                "Filled cells": filled,
                "Non-English %": round(non_en / filled * 100.0, 2),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["Non-English %", "Non-English cells"], ascending=False)


# ============================================================
# LOAD (cached) - NO FILTERING
# ============================================================
@st.cache_data(ttl=300)
def _load_df(spreadsheet_id: str, sheet_name: str) -> pd.DataFrame:
    # bounded range keeps it fast
    values = read_values(spreadsheet_id, f"{sheet_name}!A:ZZ")
    df = _values_to_df(values)
    if df.empty:
        return df

    # fix duplicate column names for pyarrow/streamlit
    df.columns = _make_unique_columns(list(df.columns))

    # normalize boolean-ish columns
    for c in [
        COL_CONSENT,
        COL_RECORD,
        COL_TRAIN_ATTEND,
        COL_KIT,
        COL_PRODUCING,
        COL_HYGIENE,
        COL_MARKET_INFO,
        COL_INTRO_BUYERS,
        COL_HELPFUL,
        COL_FAMILY_SUPPORT,
        COL_INFORMED_CONCERNS,
        COL_KNOW_CONTACT,
    ]:
        if c in df.columns:
            df[c] = df[c].map(_norm_bool)

    # parse time
    if COL_START in df.columns:
        df["_start_dt"] = pd.to_datetime(df[COL_START], errors="coerce")
    else:
        df["_start_dt"] = pd.NaT

    df["_date"] = df["_start_dt"].dt.date
    df["_date_str"] = df["_start_dt"].map(_format_mdy)
    df["_month_name"] = df["_start_dt"].dt.month_name()
    df["_day_of_week"] = df["_start_dt"].dt.day_name()
    df["_day_of_month"] = df["_start_dt"].dt.day
    df["_hour"] = df["_start_dt"].dt.hour

    # gender normalization
    if COL_GENDER in df.columns:
        g = _clean_text_series(df[COL_GENDER]).str.lower()
        df["_gender_norm"] = g.map({"male": "Male", "female": "Female"}).fillna("Unknown")
    else:
        df["_gender_norm"] = "Unknown"

    # age normalization
    if COL_AGE in df.columns:
        df["_age_norm"] = _clean_text_series(df[COL_AGE])
    else:
        df["_age_norm"] = "Unknown"

    return df


# ============================================================
# MODERN CHART BUILDERS
# ============================================================
def _donut(df_: pd.DataFrame, title: str) -> alt.Chart:
    return (
        alt.Chart(df_)
        .mark_arc(innerRadius=78, outerRadius=130, cornerRadius=10)
        .encode(
            theta=alt.Theta("count:Q"),
            color=alt.Color(
                "category:N",
                scale=alt.Scale(range=STATUS_PALETTE),
                legend=alt.Legend(title="", orient="top", symbolType="circle"),
            ),
            tooltip=[
                alt.Tooltip("category:N", title="Category"),
                alt.Tooltip("count:Q", title="Count"),
                alt.Tooltip("pct:Q", title="Share", format=".1%"),
            ],
        )
        .properties(height=320, title=title)
    )


def _barh(df_: pd.DataFrame, title: str, max_rows: int = 12, color_scheme: str = "turbo") -> alt.Chart:
    d = df_.copy()
    d = d.sort_values("count", ascending=False).head(max_rows)
    d = d.sort_values("count", ascending=True)
    return (
        alt.Chart(d)
        .mark_bar(cornerRadiusTopRight=10, cornerRadiusBottomRight=10)
        .encode(
            x=alt.X("count:Q", title="Count"),
            y=alt.Y("category:N", sort=None, title=""),
            color=alt.Color("count:Q", scale=alt.Scale(scheme=color_scheme), legend=None),
            tooltip=[
                alt.Tooltip("category:N", title="Category"),
                alt.Tooltip("count:Q", title="Count"),
                alt.Tooltip("pct:Q", title="Share", format=".1%"),
            ],
        )
        .properties(height=320, title=title)
    )


def _stacked_bar(df: pd.DataFrame, x_col: str, color_col: str, title: str) -> alt.Chart:
    tmp = df.groupby([x_col, color_col]).size().reset_index(name="count")
    return (
        alt.Chart(tmp)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X(f"{x_col}:N", title=""),
            y=alt.Y("count:Q", title="Count"),
            color=alt.Color(f"{color_col}:N", scale=alt.Scale(range=STATUS_PALETTE), legend=alt.Legend(title="")),
            tooltip=[x_col, color_col, "count"],
        )
        .properties(height=320, title=title)
    )


def _trend_daily(df: pd.DataFrame) -> alt.Chart | None:
    tmp = df[df["_start_dt"].notna()].copy()
    if tmp.empty:
        return None
    trend = tmp.groupby(tmp["_start_dt"].dt.date).size().reset_index(name="count")
    trend.columns = ["day", "count"]
    trend = trend.sort_values("day")

    base = alt.Chart(trend).encode(
        x=alt.X("day:T", title="Date"),
        y=alt.Y("count:Q", title="Interviews"),
        tooltip=[alt.Tooltip("day:T", title="Date"), alt.Tooltip("count:Q", title="Count")],
    )
    area = base.mark_area(opacity=0.16).encode(color=alt.value(PALETTE.get("indigo", "#4C78A8")))
    line = base.mark_line(strokeWidth=3).encode(color=alt.value(PALETTE.get("indigo", "#4C78A8")))
    pts = base.mark_circle(size=70).encode(color=alt.value(PALETTE.get("pink", "#E45756")))
    return (area + line + pts).properties(height=300, title="Daily Interview Volume")


def _heatmap_day_month(df: pd.DataFrame) -> alt.Chart | None:
    tmp = df[df["_start_dt"].notna()].copy()
    if tmp.empty:
        return None

    tmp = tmp[["_month_name", "_day_of_month", "_day_of_week"]].dropna()
    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    heat = (
        alt.Chart(tmp)
        .mark_rect(cornerRadius=5)
        .encode(
            x=alt.X("_day_of_month:O", title="Day of month"),
            y=alt.Y("_day_of_week:N", sort=dow_order, title="Weekday"),
            color=alt.Color("count():Q", scale=alt.Scale(scheme="viridis"), legend=alt.Legend(title="Count")),
            tooltip=[
                alt.Tooltip("_month_name:N", title="Month"),
                alt.Tooltip("_day_of_week:N", title="Weekday"),
                alt.Tooltip("_day_of_month:O", title="Day"),
                alt.Tooltip("count():Q", title="Interviews"),
            ],
            facet=alt.Facet("_month_name:N", columns=3, title=""),
        )
        .properties(title="Calendar View: Month * Weekday * Day of Month", height=170)
    )
    return heat


def _heatmap_day_hour(df: pd.DataFrame) -> alt.Chart | None:
    tmp = df[df["_start_dt"].notna()].copy()
    if tmp.empty or tmp["_hour"].isna().all():
        return None

    tmp2 = tmp[["_hour", "_start_dt"]].copy()
    tmp2["hour"] = pd.to_numeric(tmp2["_hour"], errors="coerce")
    tmp2["weekday"] = tmp2["_start_dt"].dt.day_name()
    tmp2 = tmp2.dropna(subset=["hour", "weekday"])
    if tmp2.empty:
        return None

    dow_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return (
        alt.Chart(tmp2)
        .mark_rect(cornerRadius=5)
        .encode(
            x=alt.X("hour:O", title="Hour of day"),
            y=alt.Y("weekday:N", sort=dow_order, title="Weekday"),
            color=alt.Color("count():Q", scale=alt.Scale(scheme="viridis"), legend=alt.Legend(title="Count")),
            tooltip=[
                alt.Tooltip("weekday:N", title="Weekday"),
                alt.Tooltip("hour:O", title="Hour"),
                alt.Tooltip("count():Q", title="Interviews"),
            ],
        )
        .properties(height=280, title="Interview Density by Weekday and Hour")
    )


def _missingness_table(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    result = []
    for col in df.columns:
        cleaned = _clean_text_series(df[col])
        missing_count = int((cleaned == "").sum()) + int(df[col].isna().sum())
        pct = (missing_count / max(1, len(df))) * 100.0
        result.append({"Column": col, "Missing %": round(pct, 2)})
    out = pd.DataFrame(result).sort_values("Missing %", ascending=False)
    return out.head(top_n)


# ============================================================
# MAIN RENDER
# ============================================================
def render(spreadsheet_id: str, sheet_name: str):
    """Render the GWO Beneficiary KII dashboard."""

    inject_fonts()
    apply_ui()
    enable_altair_theme()

    glass_header("GWO - Beneficiary KII Dashboard", "Modern * Altair charts * All records")

    df = _load_df(spreadsheet_id, sheet_name)
    if df.empty:
        st.info("No data found in this sheet. Please check the Google Sheet has data.")
        return

    # KPIs
    total = len(df)
    pct_female = float((df["_gender_norm"] == "Female").mean() * 100.0) if total else 0.0
    pct_training = float((df[COL_TRAIN_ATTEND] == "Yes").mean() * 100.0) if (total and COL_TRAIN_ATTEND in df.columns) else 0.0
    pct_kit = float((df[COL_KIT] == "Yes").mean() * 100.0) if (total and COL_KIT in df.columns) else 0.0
    pct_helpful = float(df[COL_HELPFUL].isin(["Yes", "Partly"]).mean() * 100.0) if (total and COL_HELPFUL in df.columns) else 0.0

    kpi_row(
        [
            {"label": "Total KIIs", "value": f"{total:,}", "hint": "All records"},
            {"label": "Female respondents", "value": f"{pct_female:.1f}%", "hint": "Gender distribution"},
            {"label": "Attended training", "value": f"{pct_training:.1f}%", "hint": "Service access"},
            {"label": "Received production kit", "value": f"{pct_kit:.1f}%", "hint": "Service receipt"},
            {"label": "Satisfied (helpful)", "value": f"{pct_helpful:.1f}%", "hint": "Perceived usefulness"},
        ]
    )

    glass_divider()

    tabs = st.tabs(
        [
            "Overview & Timeline",
            "Demographics",
            "Services & Outcomes",
            "Safeguarding & Accountability",
            "Data Quality & Translation",
        ]
    )

    # TAB 1
    with tabs[0]:
        glass_header("Interview Timeline & Activity Patterns", "Daily volume, weekday/hour density, and calendar heatmap")

        c1, c2 = st.columns([1.2, 1], gap="large")
        with c1:
            ch = _trend_daily(df)
            st.altair_chart(ch, use_container_width=True) if ch else st.info("Insufficient datetime data for trends.")
        with c2:
            ch = _heatmap_day_hour(df)
            st.altair_chart(ch, use_container_width=True) if ch else st.info("Not enough timestamp detail for weekday-hour heatmap.")

        glass_divider()

        ch = _heatmap_day_month(df)
        st.altair_chart(ch, use_container_width=True) if ch else st.info("No valid timestamps for calendar view.")

        glass_divider()
        glass_header("Date-only Format (m/d/YYYY)", "Time removed per requirement")
        preview = df[["_date_str"]].dropna().head(12)
        st.dataframe(preview.rename(columns={"_date_str": "Interview date (m/d/YYYY)"}), use_container_width=True)

    # TAB 2
    with tabs[1]:
        glass_header("Respondent Demographics", "Age, gender, education, marital status, household size, income")

        c1, c2 = st.columns(2, gap="large")
        with c1:
            age = _value_counts_df(_safe_col(df, COL_AGE), top_n=8)
            st.altair_chart(_barh(age, "Age Group", color_scheme="viridis"), use_container_width=True)

            marital = _value_counts_df(_safe_col(df, COL_MARITAL), top_n=6)
            st.altair_chart(_barh(marital, "Marital Status", color_scheme="plasma"), use_container_width=True)

        with c2:
            gender = _value_counts_df(df["_gender_norm"], top_n=4)
            st.altair_chart(_donut(gender, "Gender Distribution"), use_container_width=True)

            edu = _value_counts_df(_safe_col(df, COL_EDU), top_n=8)
            st.altair_chart(_barh(edu, "Education Level", color_scheme="cividis"), use_container_width=True)

        glass_divider()

        if COL_AGE in df.columns:
            st.altair_chart(_stacked_bar(df, COL_AGE, "_gender_norm", "Age Group by Gender"), use_container_width=True)

        glass_divider()

        c3, c4 = st.columns(2, gap="large")
        with c3:
            glass_header("Household Size", "Histogram + summary")
            hh = _to_num(_safe_col(df, COL_HH)).dropna()
            if hh.empty:
                st.info("No numeric household size data.")
            else:
                hist = (
                    alt.Chart(pd.DataFrame({"hh": hh}))
                    .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                    .encode(
                        x=alt.X("hh:Q", bin=alt.Bin(maxbins=15), title="Household members"),
                        y=alt.Y("count()", title="Frequency"),
                        tooltip=["count()"],
                    )
                    .properties(height=250)
                )
                st.altair_chart(hist, use_container_width=True)
                stats = _numeric_summary(_safe_col(df, COL_HH))
                if stats:
                    st.caption(
                        f"Mean: {stats['mean']:.1f} * Median: {stats['median']:.1f} * Range: {stats['min']:.0f}-{stats['max']:.0f}"
                    )

        with c4:
            glass_header("Monthly Income", "Histogram + summary")
            inc = _to_num(_safe_col(df, COL_INCOME)).dropna()
            if inc.empty:
                st.info("No numeric income data.")
            else:
                hist = (
                    alt.Chart(pd.DataFrame({"inc": inc}))
                    .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
                    .encode(
                        x=alt.X("inc:Q", bin=alt.Bin(maxbins=15), title="Income (local currency)"),
                        y=alt.Y("count()", title="Frequency"),
                        tooltip=["count()"],
                    )
                    .properties(height=250)
                )
                st.altair_chart(hist, use_container_width=True)
                stats = _numeric_summary(_safe_col(df, COL_INCOME))
                if stats:
                    st.caption(
                        f"Mean: {stats['mean']:.0f} * Median: {stats['median']:.0f} * Range: {stats['min']:.0f}-{stats['max']:.0f}"
                    )

    # TAB 3
    with tabs[2]:
        glass_header("Services, Training & Outcomes", "Training, kits, production, hygiene, and market linkages")

        c1, c2, c3 = st.columns(3, gap="large")
        with c1:
            attend = _value_counts_df(_safe_col(df, COL_TRAIN_ATTEND), top_n=3)
            st.altair_chart(_donut(attend, "Training Attendance"), use_container_width=True)
        with c2:
            kit = _value_counts_df(_safe_col(df, COL_KIT), top_n=3)
            st.altair_chart(_donut(kit, "Received Kit"), use_container_width=True)
        with c3:
            producing = _value_counts_df(_safe_col(df, COL_PRODUCING), top_n=3)
            st.altair_chart(_donut(producing, "Currently Producing"), use_container_width=True)

        glass_divider()

        topics = _multiselect_counts(_safe_col(df, COL_TOPICS))
        if not topics.empty:
            st.altair_chart(_barh(topics, "Training Topics Covered (Top)", max_rows=12, color_scheme="inferno"), use_container_width=True)
        else:
            st.info("No training topics captured.")

        glass_divider()

        pairs = _kit_pairs_from_columns(df)
        if pairs:
            rows = []
            for item, (yes_col, qty_col) in pairs.items():
                yes = _clean_text_series(_safe_col(df, yes_col)).map(_norm_bool)
                pct = float((yes == "Yes").mean() * 100.0) if len(yes) else 0.0
                qty = _to_num(_safe_col(df, qty_col))
                avg_qty = float(qty.mean()) if not qty.isna().all() else 0.0
                rows.append({"item": item, "percent_received": pct, "avg_quantity": avg_qty})
            kit_df = pd.DataFrame(rows).sort_values("percent_received", ascending=False)

            bubble = (
                alt.Chart(kit_df)
                .mark_circle(opacity=0.75, strokeWidth=1)
                .encode(
                    x=alt.X("item:N", title="Kit item", sort=None),
                    y=alt.Y("percent_received:Q", title="% received", scale=alt.Scale(domain=[0, 100])),
                    size=alt.Size(
                        "avg_quantity:Q",
                        scale=alt.Scale(range=[120, 900]),
                        legend=alt.Legend(title="Avg qty"),
                    ),
                    color=alt.Color("item:N", scale=alt.Scale(range=STATUS_PALETTE), legend=None),
                    tooltip=[
                        alt.Tooltip("item:N", title="Item"),
                        alt.Tooltip("percent_received:Q", title="% received", format=".1f"),
                        alt.Tooltip("avg_quantity:Q", title="Avg quantity", format=".2f"),
                    ],
                )
                .properties(height=360, title="Kit Items: % Received vs Average Quantity")
            )
            st.altair_chart(bubble, use_container_width=True)
        else:
            st.info("Kit item columns not detected.")

        glass_divider()

        c4, c5 = st.columns(2, gap="large")
        with c4:
            hyg = _value_counts_df(_safe_col(df, COL_HYGIENE), top_n=3)
            st.altair_chart(_donut(hyg, "Hygiene Practices Followed"), use_container_width=True)
        with c5:
            reasons = _multiselect_counts(_safe_col(df, COL_HYGIENE_WHYNO))
            # Some forms export reasons as separate columns like "If no, why?/Reason".
            for c in df.columns:
                if str(c).startswith(WHYNO_PREFIX):
                    label = str(c).replace(WHYNO_PREFIX, "").strip()
                    sel = _clean_text_series(df[c])
                    cnt = int((sel != "").sum())
                    if cnt > 0:
                        reasons = pd.concat(
                            [reasons, pd.DataFrame([{"category": label, "count": cnt, "pct": 0.0}])],
                            ignore_index=True,
                        )
            if reasons.empty:
                st.info("No 'reason' data captured.")
            else:
                reasons = reasons.groupby("category", as_index=False)["count"].sum()
                reasons["pct"] = reasons["count"] / max(1, reasons["count"].sum())
                reasons = reasons.sort_values("count", ascending=False)
                st.altair_chart(_barh(reasons, "Reasons Hygiene Not Followed", max_rows=8), use_container_width=True)

        glass_divider()

        c6, c7, c8 = st.columns(3, gap="large")
        with c6:
            mkt = _value_counts_df(_safe_col(df, COL_MARKET_INFO), top_n=3)
            st.altair_chart(_donut(mkt, "Market Info Provided"), use_container_width=True)
        with c7:
            intro = _value_counts_df(_safe_col(df, COL_INTRO_BUYERS), top_n=3)
            st.altair_chart(_donut(intro, "Introduced to Buyers"), use_container_width=True)
        with c8:
            helpful = _value_counts_df(_safe_col(df, COL_HELPFUL), top_n=3)
            st.altair_chart(_donut(helpful, "Was It Helpful?"), use_container_width=True)

        changes = _multiselect_counts(_safe_col(df, COL_CHANGES))
        if not changes.empty:
            glass_divider()
            st.altair_chart(_barh(changes, "Perceived Changes from Activity", max_rows=10), use_container_width=True)

    # TAB 4
    with tabs[3]:
        glass_header("Safeguarding & Accountability", "Complaint awareness, family support, and open-ended concerns")

        c1, c2, c3 = st.columns(3, gap="large")
        with c1:
            informed = _value_counts_df(_safe_col(df, COL_INFORMED_CONCERNS), top_n=3)
            st.altair_chart(_donut(informed, "Informed How to Raise Concerns"), use_container_width=True)
        with c2:
            know = _value_counts_df(_safe_col(df, COL_KNOW_CONTACT), top_n=3)
            st.altair_chart(_donut(know, "Knows Whom to Contact"), use_container_width=True)
        with c3:
            fam = _value_counts_df(_safe_col(df, COL_FAMILY_SUPPORT), top_n=3)
            st.altair_chart(_donut(fam, "Family Supported Participation"), use_container_width=True)

        glass_divider()

        txt = _clean_text_series(_safe_col(df, COL_CONCERNS_TEXT))
        txt = txt[txt != ""]
        glass_header("Open-ended Concerns (Sample)", "Showing up to 15 examples")
        if txt.empty:
            st.success("No open-ended concerns recorded.")
        else:
            st.dataframe(txt.head(15).to_frame("Concern"), use_container_width=True)

    # TAB 5
    with tabs[4]:
        glass_header("Data Quality & Translation Requirements", "Missingness, duplicates, and non-English detection")

        miss = _missingness_table(df, top_n=20)
        miss_chart = (
            alt.Chart(miss)
            .mark_bar(cornerRadiusTopRight=10, cornerRadiusBottomRight=10)
            .encode(
                x=alt.X("Missing %:Q", title="Missing (%)"),
                y=alt.Y("Column:N", sort="-x", title=""),
                color=alt.Color("Missing %:Q", scale=alt.Scale(scheme="viridis"), legend=None),
                tooltip=[alt.Tooltip("Column:N"), alt.Tooltip("Missing %:Q", format=".2f")],
            )
            .properties(height=360, title="Top Variables by Missing Percentage")
        )
        st.altair_chart(miss_chart, use_container_width=True)

        glass_divider()

        d1, d2 = st.columns(2, gap="large")
        with d1:
            glass_header("Duplicate Check", "UUID preferred when available")
            if COL_UUID in df.columns:
                dupe = int(df.duplicated(subset=[COL_UUID]).sum())
                st.metric("Duplicate UUID rows", dupe)
            elif COL_ID in df.columns:
                dupe = int(df.duplicated(subset=[COL_ID]).sum())
                st.metric("Duplicate ID rows", dupe)
            else:
                st.info("No UUID/ID column for duplicate checks.")

        with d2:
            glass_header("Translation Need", "Columns containing non-English text (non-ASCII)")
            prof = _non_english_profile(df, max_cols=120)
            if prof.empty:
                st.success("No non-English text detected in the checked columns.")
            else:
                st.dataframe(prof.head(20), use_container_width=True)
