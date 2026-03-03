from __future__ import annotations

import re
from typing import Dict, List

import altair as alt
import pandas as pd
import streamlit as st

from services.gsheet_client import read_values

# UI (centralized design system)
from ui import apply_ui, inject_fonts, enable_altair_theme
from ui import glass_header, glass_divider, kpi_row
from ui.tokens import STATUS_PALETTE, PALETTE


# ============================================================
# COLUMN NAMES (match Google Sheet headers) - ASPSO Beneficiaries
# NOTE: These are used safely (missing columns won't crash).
# ============================================================
COL_START = "start"
COL_SUBMISSION = "_submission_time"

COL_PROVINCE = "Province"
COL_DISTRICT = "District"

COL_AGE = "Age group"
COL_GENDER = "Confirm gender"
COL_MARITAL = "Confirm marital status"
COL_EDU = "Level of education"
COL_EMP = "Employment status"
COL_HH = "Number of household members"
COL_INCOME = "Average income per month (local currency)"

# Program
COL_INTERVENTION = "Intervention / skill area"

# Training
COL_ATTEND_TRAINING = "Did you attend any training organised by ASPSO?"
COL_TRAINING_TYPE = "What type of training did you attend?"
COL_TRAINING_DURATION = "Approximately how long did the training last?"
COL_SELECTION_CLEAR = "Before the training, were the selection criteria and process clearly explained to you?"
TOPICS_PREFIX = "What topics were covered in your training? (Select all that apply)/"
COL_TOPICS_MULTI = "What topics were covered in your training? (Select all that apply)"

# Inputs
COL_RECEIVED_ITEMS = "Did you receive any items or materials after the training?"
COL_INPUT_QUALITY = "Were you satisfied with the quality of the input/kit?"
COL_USING = "Are you currently using what you learned or received?"
COL_NOT_USING_REASON = "If no, what are the main reasons?"

# Outcomes
COL_SAFE_TRAINING = "Do you feel safe and secure accessing the training?"
COL_SATISFACTION = "How satisfied are you with the services you received?"
COL_TRAINING_HELPED = "Has the training helped you in any way?"
HELP_PREFIX = "If yes, how? (Select all that apply)/"
COL_HELP_MULTI = "If yes, how? (Select all that apply)"
COL_CHALLENGES = "What challenges have you faced in applying what you learned?"

# AAP / Safeguarding
COL_AAP_INFORMED = "Were you informed about how to raise a concern or complaint related to this project?"
COL_AAP_CONTACT = "Do you know whom to contact if you have a concern?"
COL_FEEDBACK_OPEN = "Is there anything else you would like to share about your experience with this project?"

COL_ID = "_id"
COL_UUID = "_uuid"


# ============================================================
# DATA UTILS (fast + safe) - aligned with your GSRO style
# ============================================================
def _values_to_df(values: List[List[object]]) -> pd.DataFrame:
    if not values:
        return pd.DataFrame()
    header = [str(x) for x in values[0]]
    data = values[1:] if len(values) > 1 else []

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
    for fmt in ("%-m/%-d/%Y", "%#m/%#d/%Y", "%m/%d/%Y"):
        try:
            return ts.strftime(fmt)
        except Exception:
            continue
    return ""


def _items_from_prefix(df: pd.DataFrame, prefix: str) -> List[str]:
    items = []
    for c in df.columns:
        cs = str(c)
        if cs.startswith(prefix):
            items.append(cs.replace(prefix, "").strip())
    return items


# ============================================================
# LOAD (cached) - NO FILTERING
# ============================================================
@st.cache_data(ttl=300)
def _load_df(spreadsheet_id: str, sheet_name: str) -> pd.DataFrame:
    values = read_values(spreadsheet_id, f"{sheet_name}!A:ZZ")
    df = _values_to_df(values)
    if df.empty:
        return df

    df.columns = _make_unique_columns(list(df.columns))

    # normalize boolean-ish columns
    for c in [
        COL_ATTEND_TRAINING,
        COL_SELECTION_CLEAR,
        COL_RECEIVED_ITEMS,
        COL_INPUT_QUALITY,
        COL_USING,
        COL_SAFE_TRAINING,
        COL_TRAINING_HELPED,
        COL_AAP_INFORMED,
        COL_AAP_CONTACT,
    ]:
        if c in df.columns:
            df[c] = df[c].map(_norm_bool)

    # parse time
    if COL_START in df.columns:
        df["_start_dt"] = pd.to_datetime(df[COL_START], errors="coerce")
    elif COL_SUBMISSION in df.columns:
        df["_start_dt"] = pd.to_datetime(df[COL_SUBMISSION], errors="coerce")
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

    return df


# ============================================================
# CHART BUILDERS (same design language)
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
def render(spreadsheet_id: str, sheet_name: str) -> None:
    """Render the ASPSO Beneficiaries dashboard (Liquid Glass / Altair)."""

    # Safe to call here even if called globally in app.py
    inject_fonts()
    apply_ui()
    enable_altair_theme()

    glass_header("ASPSO - Beneficiaries Dashboard", "Modern * Altair charts * All records")

    df = _load_df(spreadsheet_id, sheet_name)
    if df.empty:
        st.info("No data found in this sheet. Please check the Google Sheet has data.")
        return

    total = len(df)
    pct_female = float((df["_gender_norm"] == "Female").mean() * 100.0) if total else 0.0

    pct_attended = float(df[COL_ATTEND_TRAINING].isin(["Yes", "Partly"]).mean() * 100.0) if (total and COL_ATTEND_TRAINING in df.columns) else 0.0
    pct_received = float(df[COL_RECEIVED_ITEMS].isin(["Yes", "Partly"]).mean() * 100.0) if (total and COL_RECEIVED_ITEMS in df.columns) else 0.0
    pct_using = float(df[COL_USING].isin(["Yes", "Partly"]).mean() * 100.0) if (total and COL_USING in df.columns) else 0.0
    pct_aap = float(df[COL_AAP_INFORMED].isin(["Yes", "Partly"]).mean() * 100.0) if (total and COL_AAP_INFORMED in df.columns) else 0.0

    kpi_row(
        [
            {"label": "Total interviews", "value": f"{total:,}", "hint": "All records"},
            {"label": "Female respondents", "value": f"{pct_female:.1f}%", "hint": "Gender distribution"},
            {"label": "Attended training", "value": f"{pct_attended:.1f}%", "hint": "Yes/Partly"},
            {"label": "Received inputs", "value": f"{pct_received:.1f}%", "hint": "Items/materials after training"},
            {"label": "Aware of complaints", "value": f"{pct_aap:.1f}%", "hint": "AAP / safeguarding"},
        ]
    )

    glass_divider()

    tabs = st.tabs(
        [
            "Overview & Timeline",
            "Demographics",
            "Training & Topics",
            "Inputs & Utilisation",
            "Outcomes & AAP",
            "Data Quality",
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

        glass_divider()
        c3, c4, c5 = st.columns(3, gap="large")
        with c3:
            prov = _value_counts_df(_safe_col(df, COL_PROVINCE), top_n=10)
            st.altair_chart(_barh(prov, "Top Provinces", max_rows=10, color_scheme="viridis"), use_container_width=True)
        with c4:
            skill = _value_counts_df(_safe_col(df, COL_INTERVENTION), top_n=10)
            st.altair_chart(_barh(skill, "Intervention / Skill Area", max_rows=10, color_scheme="plasma"), use_container_width=True)
        with c5:
            sat = _value_counts_df(_safe_col(df, COL_SATISFACTION), top_n=6)
            st.altair_chart(_donut(sat, "Satisfaction"), use_container_width=True)

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
                    st.caption(f"Mean: {stats['mean']:.1f} * Median: {stats['median']:.1f} * Range: {stats['min']:.0f}-{stats['max']:.0f}")

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
                    st.caption(f"Mean: {stats['mean']:.0f} * Median: {stats['median']:.0f} * Range: {stats['min']:.0f}-{stats['max']:.0f}")

    # TAB 3
    with tabs[2]:
        glass_header("Training & Topics", "Attendance, training type/duration, topics covered")

        c1, c2, c3 = st.columns(3, gap="large")
        with c1:
            attended = _value_counts_df(_safe_col(df, COL_ATTEND_TRAINING), top_n=3)
            st.altair_chart(_donut(attended, "Attended Training"), use_container_width=True)
        with c2:
            ttype = _value_counts_df(_safe_col(df, COL_TRAINING_TYPE), top_n=6)
            st.altair_chart(_donut(ttype, "Training Type"), use_container_width=True)
        with c3:
            sel = _value_counts_df(_safe_col(df, COL_SELECTION_CLEAR), top_n=3)
            st.altair_chart(_donut(sel, "Selection Process Explained"), use_container_width=True)

        glass_divider()

        c4, c5 = st.columns(2, gap="large")
        with c4:
            dur = _value_counts_df(_safe_col(df, COL_TRAINING_DURATION), top_n=8)
            st.altair_chart(_barh(dur, "Training Duration", max_rows=10, color_scheme="viridis"), use_container_width=True)
        with c5:
            safe = _value_counts_df(_safe_col(df, COL_SAFE_TRAINING), top_n=3)
            st.altair_chart(_donut(safe, "Felt Safe Accessing Training"), use_container_width=True)

        glass_divider()

        topic_items = _items_from_prefix(df, TOPICS_PREFIX)
        rows = []
        for item in topic_items:
            col = f"{TOPICS_PREFIX}{item}"
            sel = _clean_text_series(_safe_col(df, col))
            cnt = int((sel != "").sum())
            if cnt > 0:
                rows.append({"category": item, "count": cnt})

        topics_df = pd.DataFrame(rows)
        if not topics_df.empty:
            topics_df["pct"] = topics_df["count"] / max(1, int(topics_df["count"].sum()))
            st.altair_chart(_barh(topics_df.sort_values("count", ascending=False), "Topics Covered (Tick Columns)", max_rows=12, color_scheme="inferno"), use_container_width=True)
        else:
            topics = _multiselect_counts(_safe_col(df, COL_TOPICS_MULTI))
            if not topics.empty:
                st.altair_chart(_barh(topics, "Topics Covered (Parsed from Multi Text)", max_rows=12, color_scheme="inferno"), use_container_width=True)
            else:
                st.info("No topic data detected (neither tick columns nor multi text).")

    # TAB 4
    with tabs[3]:
        glass_header("Inputs & Utilisation", "Inputs received, quality, usage, and non-use reasons")

        c1, c2, c3 = st.columns(3, gap="large")
        with c1:
            rec = _value_counts_df(_safe_col(df, COL_RECEIVED_ITEMS), top_n=3)
            st.altair_chart(_donut(rec, "Received Any Items"), use_container_width=True)
        with c2:
            qual = _value_counts_df(_safe_col(df, COL_INPUT_QUALITY), top_n=3)
            st.altair_chart(_donut(qual, "Satisfied with Input Quality"), use_container_width=True)
        with c3:
            use = _value_counts_df(_safe_col(df, COL_USING), top_n=3)
            st.altair_chart(_donut(use, "Currently Using Skills/Inputs"), use_container_width=True)

        glass_divider()

        reasons = _value_counts_df(_safe_col(df, COL_NOT_USING_REASON), top_n=10)
        if not reasons.empty:
            st.altair_chart(_barh(reasons, "Reasons for Not Using (Top)", max_rows=10, color_scheme="viridis"), use_container_width=True)
        else:
            st.info("No coded 'not using' reasons found.")

    # TAB 5
    with tabs[4]:
        glass_header("Outcomes & Accountability", "Helpfulness, challenges, complaints awareness, and feedback")

        c1, c2, c3 = st.columns(3, gap="large")
        with c1:
            helped = _value_counts_df(_safe_col(df, COL_TRAINING_HELPED), top_n=3)
            st.altair_chart(_donut(helped, "Training Helped"), use_container_width=True)
        with c2:
            aap = _value_counts_df(_safe_col(df, COL_AAP_INFORMED), top_n=3)
            st.altair_chart(_donut(aap, "Informed About Complaints"), use_container_width=True)
        with c3:
            contact = _value_counts_df(_safe_col(df, COL_AAP_CONTACT), top_n=3)
            st.altair_chart(_donut(contact, "Know Whom to Contact"), use_container_width=True)

        glass_divider()

        help_items = _items_from_prefix(df, HELP_PREFIX)
        rows = []
        for item in help_items:
            col = f"{HELP_PREFIX}{item}"
            sel = _clean_text_series(_safe_col(df, col))
            cnt = int((sel != "").sum())
            if cnt > 0:
                rows.append({"category": item, "count": cnt})

        help_df = pd.DataFrame(rows)
        if not help_df.empty:
            help_df["pct"] = help_df["count"] / max(1, int(help_df["count"].sum()))
            st.altair_chart(_barh(help_df.sort_values("count", ascending=False), "How Training Helped (Tick Columns)", max_rows=10, color_scheme="plasma"), use_container_width=True)
        else:
            help_ms = _multiselect_counts(_safe_col(df, COL_HELP_MULTI))
            if not help_ms.empty:
                st.altair_chart(_barh(help_ms, "How Training Helped (Parsed Multi Text)", max_rows=10, color_scheme="plasma"), use_container_width=True)
            else:
                st.info("No 'how training helped' details captured.")

        glass_divider()

        chal = _value_counts_df(_safe_col(df, COL_CHALLENGES), top_n=10)
        if chal.empty:
            st.info("No challenges recorded (or field is empty).")
        else:
            st.altair_chart(_barh(chal, "Challenges Applying Skills (Top)", max_rows=10, color_scheme="inferno"), use_container_width=True)

        glass_divider()

        fb = _clean_text_series(_safe_col(df, COL_FEEDBACK_OPEN))
        fb = fb[fb != ""]
        glass_header("Open-ended Feedback (Sample)", "Showing up to 15 examples")
        if fb.empty:
            st.success("No open-ended feedback recorded.")
        else:
            st.dataframe(fb.head(15).to_frame("Feedback"), use_container_width=True)

    # TAB 6
    with tabs[5]:
        glass_header("Data Quality", "Missingness and duplicate checks")

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

        c1, c2 = st.columns(2, gap="large")
        with c1:
            glass_header("Duplicate Check", "UUID preferred when available")
            if COL_UUID in df.columns:
                dupe = int(df.duplicated(subset=[COL_UUID]).sum())
                st.metric("Duplicate UUID rows", dupe)
            elif COL_ID in df.columns:
                dupe = int(df.duplicated(subset=[COL_ID]).sum())
                st.metric("Duplicate ID rows", dupe)
            else:
                st.info("No UUID/ID column for duplicate checks.")

        with c2:
            st.metric("Currently using (Yes/Partly)", f"{pct_using:.1f}%")
