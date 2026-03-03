from __future__ import annotations

from typing import Any, List, Optional, Tuple

import altair as alt
import pandas as pd
import streamlit as st

from services.gsheet_client import read_values
from ui import (
    apply_ui,
    inject_fonts,
    enable_altair_theme,
    glass_header,
    glass_divider,
    kpi_row,
    liquid_glass_footer,
)

# =========================
# Sheet column names (PTCRO)
# =========================
COL_START = "start"
COL_SUBMISSION = "_submission_time"

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
COL_RESP_CAT = "Respondent category"

COL_HYGIENE_ATTEND = "Did you attend hygiene awareness sessions?"
COL_HYGIENE_INFORMED = "How were you informed about the session?"
COL_SEPARATE = "Were sessions conducted separately for men and women?"
COL_PARTICIPATE = "Were you able to participate fully?"
COL_UNDERSTAND_CHANGE = "Did the session change your understanding of hygiene?"

COL_KIT_RECEIVED = "Did your household receive a hygiene kit?"
COL_SELECTED = "How were beneficiaries selected?"

KIT_PREFIX = "What items were included in the kit? (Tick all)/"
MECH_PREFIX = "What mechanisms were mentioned? (Select all)/"

COL_PRACTICES_CHANGED = "What hygiene practices have changed in your household?"
COL_PREVENTS = "What prevents full adoption of hygiene practices?"
COL_INFORMED_FEEDBACK = "Were you informed about how to provide feedback or complaints?"
COL_TRUST = "Do you trust these mechanisms?"

COL_UUID = "_uuid"


# =========================
# Helpers
# =========================
def _values_to_df(values: List[List[Any]]) -> pd.DataFrame:
    if not values:
        return pd.DataFrame()
    header = [str(x).strip() for x in values[0]]
    data = values[1:] if len(values) > 1 else []

    n = len(header)
    fixed: List[List[Any]] = []
    for r in data:
        r = list(r) if r is not None else []
        if len(r) < n:
            r = r + [""] * (n - len(r))
        elif len(r) > n:
            r = r[:n]
        fixed.append(r)

    df = pd.DataFrame(fixed, columns=header)
    if not df.empty:
        df = df.dropna(how="all")
    return df


def _norm_text(s: pd.Series) -> pd.Series:
    return s.astype(str).replace({"nan": "", "None": ""}).str.strip()


def _norm_yes_no(x: Any) -> str:
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


def _col(df: pd.DataFrame, name: str) -> Optional[str]:
    """Best-effort: exact, or case-insensitive+strip match."""
    if name in df.columns:
        return name
    want = name.strip().lower()
    for c in df.columns:
        if str(c).strip().lower() == want:
            return c
    return None


def _prefix_cols(df: pd.DataFrame, prefix: str) -> List[str]:
    out = []
    p = prefix.strip().lower()
    for c in df.columns:
        if str(c).strip().lower().startswith(p):
            out.append(c)
    return out


def _metric_pct(n: int, d: int) -> str:
    if d <= 0:
        return "—"
    return f"{(100.0 * n / d):.1f}%"


def _top_n_counts(s: pd.Series, n: int = 12) -> pd.DataFrame:
    s = _norm_text(s)
    s = s[s != ""]
    vc = s.value_counts(dropna=True).head(n)
    return vc.rename_axis("value").reset_index(name="count")


def _bar(df_counts: pd.DataFrame, title: str, x: str = "count", y: str = "value") -> alt.Chart:
    return (
        alt.Chart(df_counts, title=title)
        .mark_bar()
        .encode(
            x=alt.X(f"{x}:Q", title="Count"),
            y=alt.Y(f"{y}:N", sort="-x", title=""),
            tooltip=[alt.Tooltip(f"{y}:N", title="Value"), alt.Tooltip(f"{x}:Q", title="Count")],
        )
        .properties(height=320)
    )


def _yesno_bar(df: pd.DataFrame, col_name: str, title: str) -> Optional[alt.Chart]:
    c = _col(df, col_name)
    if not c:
        return None
    s = df[c].map(_norm_yes_no)
    counts = s[s != ""].value_counts().rename_axis("value").reset_index(name="count")
    if counts.empty:
        return None
    return _bar(counts, title)


def _time_series(df: pd.DataFrame, dt_col: str, title: str) -> Optional[alt.Chart]:
    c = _col(df, dt_col)
    if not c:
        return None
    ts = pd.to_datetime(_norm_text(df[c]), errors="coerce", utc=False)
    tdf = pd.DataFrame({"date": ts.dt.date}).dropna()
    if tdf.empty:
        return None
    agg = tdf.value_counts("date").rename("count").reset_index().sort_values("date")
    return (
        alt.Chart(agg, title=title)
        .mark_line(point=True)
        .encode(
            x=alt.X("date:T", title="Date"),
            y=alt.Y("count:Q", title="Interviews"),
            tooltip=[alt.Tooltip("date:T", title="Date"), alt.Tooltip("count:Q", title="Count")],
        )
        .properties(height=260)
    )


def _multiselect_prefix_counts(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    cols = _prefix_cols(df, prefix)
    items: List[Tuple[str, int]] = []
    for c in cols:
        label = str(c)[len(prefix) :].strip()
        s = _norm_text(df[c]).map(_norm_yes_no)
        count_yes = int((s == "Yes").sum())
        if count_yes > 0:
            items.append((label, count_yes))
    return (
        pd.DataFrame(items, columns=["value", "count"])
        .sort_values("count", ascending=False)
        .reset_index(drop=True)
    )


# =========================
# Dashboard entrypoint
# =========================
def render(spreadsheet_id: str, sheet_name: str) -> None:
    apply_ui()
    inject_fonts()
    enable_altair_theme()

    values = read_values(spreadsheet_id, f"{sheet_name}!A:ZZ")
    df = _values_to_df(values)

    glass_header("PTCRO • Beneficiaries Dashboard", "Modern insights for hygiene awareness interviews")

    if df.empty:
        st.info("No data found in this sheet.")
        return

    # Normalize key categorical columns
    for key in (COL_PROVINCE, COL_DISTRICT, COL_GENDER, COL_AGE, COL_SURVEYOR):
        c = _col(df, key)
        if c:
            df[c] = _norm_text(df[c])

    total = len(df)
    provinces = df[_col(df, COL_PROVINCE)].nunique() if _col(df, COL_PROVINCE) else 0
    districts = df[_col(df, COL_DISTRICT)].nunique() if _col(df, COL_DISTRICT) else 0

    consent_col = _col(df, COL_CONSENT)
    consent_yes = int(df[consent_col].map(_norm_yes_no).eq("Yes").sum()) if consent_col else 0
    consent_den = int(df[consent_col].map(_norm_yes_no).isin(["Yes", "No"]).sum()) if consent_col else 0

    record_col = _col(df, COL_RECORD)
    record_yes = int(df[record_col].map(_norm_yes_no).eq("Yes").sum()) if record_col else 0
    record_den = int(df[record_col].map(_norm_yes_no).isin(["Yes", "No"]).sum()) if record_col else 0

    kit_col = _col(df, COL_KIT_RECEIVED)
    kit_yes = int(df[kit_col].map(_norm_yes_no).eq("Yes").sum()) if kit_col else 0
    kit_den = int(df[kit_col].map(_norm_yes_no).isin(["Yes", "No"]).sum()) if kit_col else 0

    hygiene_attend_col = _col(df, COL_HYGIENE_ATTEND)
    hygiene_yes = int(df[hygiene_attend_col].map(_norm_yes_no).eq("Yes").sum()) if hygiene_attend_col else 0
    hygiene_den = (
        int(df[hygiene_attend_col].map(_norm_yes_no).isin(["Yes", "No", "Partly"]).sum())
        if hygiene_attend_col
        else 0
    )

    kpi_row(
        [
            {"label": "Interviews", "value": f"{total:,}"},
            {"label": "Provinces", "value": f"{provinces:,}"},
            {"label": "Districts", "value": f"{districts:,}"},
            {"label": "Consent (Yes)", "value": f"{consent_yes:,}", "hint": f"Rate: {_metric_pct(consent_yes, consent_den)}"},
            {"label": "Recording (Yes)", "value": f"{record_yes:,}", "hint": f"Rate: {_metric_pct(record_yes, record_den)}"},
            {"label": "Hygiene kit received (Yes)", "value": f"{kit_yes:,}", "hint": f"Rate: {_metric_pct(kit_yes, kit_den)}"},
        ]
    )

    glass_divider()

    # Smart filters
    with st.expander("Smart filters", expanded=True):
        cprov = _col(df, COL_PROVINCE)
        cdst = _col(df, COL_DISTRICT)
        cgen = _col(df, COL_GENDER)
        cage = _col(df, COL_AGE)

        q = df
        col1, col2, col3, col4 = st.columns(4, gap="large")
        if cprov:
            opts = sorted([x for x in q[cprov].unique().tolist() if str(x).strip()])
            sel = col1.multiselect("Province", opts, default=[])
            if sel:
                q = q[q[cprov].isin(sel)]
        if cdst:
            opts = sorted([x for x in q[cdst].unique().tolist() if str(x).strip()])
            sel = col2.multiselect("District", opts, default=[])
            if sel:
                q = q[q[cdst].isin(sel)]
        if cgen:
            opts = sorted([x for x in q[cgen].unique().tolist() if str(x).strip()])
            sel = col3.multiselect("Gender", opts, default=[])
            if sel:
                q = q[q[cgen].isin(sel)]
        if cage:
            opts = sorted([x for x in q[cage].unique().tolist() if str(x).strip()])
            sel = col4.multiselect("Age group", opts, default=[])
            if sel:
                q = q[q[cage].isin(sel)]

        st.caption(f"Filtered rows: {len(q):,} / {total:,}")

    # Timeline (start preferred, fallback to submission time)
    t = _time_series(q, COL_START, "Interviews over time (start)")
    if t is None:
        t = _time_series(q, COL_SUBMISSION, "Interviews over time (submission)")
    if t is not None:
        st.altair_chart(t, use_container_width=True)

    glass_divider()

    # Demographics
    st.markdown("### Demographics")
    d1, d2 = st.columns(2, gap="large")

    c = _col(q, COL_GENDER)
    if c:
        d1.altair_chart(_bar(_top_n_counts(q[c], 10), "Gender"), use_container_width=True)
    else:
        d1.info("Gender column not found.")

    c = _col(q, COL_AGE)
    if c:
        d2.altair_chart(_bar(_top_n_counts(q[c], 10), "Age group"), use_container_width=True)
    else:
        d2.info("Age group column not found.")

    d3, d4 = st.columns(2, gap="large")
    c = _col(q, COL_MARITAL)
    if c:
        d3.altair_chart(_bar(_top_n_counts(q[c], 12), "Marital status"), use_container_width=True)
    else:
        d3.info("Marital status column not found.")

    c = _col(q, COL_EDU)
    if c:
        d4.altair_chart(_bar(_top_n_counts(q[c], 12), "Education level"), use_container_width=True)
    else:
        d4.info("Education column not found.")

    glass_divider()

    # Sessions + kits
    st.markdown("### Sessions and kits")
    s1, s2 = st.columns(2, gap="large")

    ch = _yesno_bar(q, COL_HYGIENE_ATTEND, "Attended hygiene awareness sessions")
    if ch is not None:
        s1.altair_chart(ch, use_container_width=True)
    else:
        s1.info("Session attendance column not found.")

    ck = _yesno_bar(q, COL_KIT_RECEIVED, "Received a hygiene kit")
    if ck is not None:
        s2.altair_chart(ck, use_container_width=True)
    else:
        s2.info("Hygiene kit column not found.")

    kit_counts = _multiselect_prefix_counts(q, KIT_PREFIX)
    if not kit_counts.empty:
        st.altair_chart(_bar(kit_counts.head(15), "Kit items included (Yes counts)"), use_container_width=True)
    else:
        st.info("No kit item (multi-select) columns found or all counts are zero.")

    glass_divider()

    # Feedback mechanisms
    st.markdown("### Feedback and complaints mechanisms")
    f1, f2 = st.columns(2, gap="large")

    informed = _yesno_bar(q, COL_INFORMED_FEEDBACK, "Informed about feedback/complaints")
    if informed is not None:
        f1.altair_chart(informed, use_container_width=True)
    else:
        f1.info("Feedback info column not found.")

    trust = _yesno_bar(q, COL_TRUST, "Trust in mechanisms")
    if trust is not None:
        f2.altair_chart(trust, use_container_width=True)
    else:
        f2.info("Trust column not found.")

    mech_counts = _multiselect_prefix_counts(q, MECH_PREFIX)
    if not mech_counts.empty:
        st.altair_chart(_bar(mech_counts.head(12), "Mechanisms mentioned (Yes counts)"), use_container_width=True)
    else:
        st.info("No mechanisms (multi-select) columns found or all counts are zero.")

    glass_divider()

    # Data preview
    with st.expander("Data preview", expanded=False):
        show_cols = st.multiselect("Columns to show", list(q.columns), default=list(q.columns)[:12])
        st.dataframe(q[show_cols].head(500), use_container_width=True, height=520)

    liquid_glass_footer()