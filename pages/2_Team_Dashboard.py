import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
from datetime import datetime, timedelta
import io

st.set_page_config(
    page_title="Team Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ─── STYLES ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }
    .dash-title {
        font-family: 'Syne', sans-serif;
        font-size: 2rem;
        font-weight: 800;
        letter-spacing: -0.5px;
        margin-bottom: 0;
    }
    .dash-sub {
        font-size: 0.8rem;
        color: #94a3b8;
        letter-spacing: 2px;
        text-transform: uppercase;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: #1e293b;
        border: 1px solid #1e3a5f;
        border-radius: 14px;
        padding: 1.2rem 1.4rem;
        margin-bottom: 0.5rem;
    }
    .metric-label {
        font-size: 0.65rem;
        font-weight: 500;
        letter-spacing: 2px;
        text-transform: uppercase;
        color: #64748b;
        margin-bottom: 4px;
    }
    .metric-value {
        font-family: 'Syne', sans-serif;
        font-size: 2rem;
        font-weight: 800;
        line-height: 1;
    }
    .metric-sub {
        font-size: 0.72rem;
        color: #64748b;
        margin-top: 4px;
    }
    .canvasser-card {
        background: #131827;
        border: 1px solid #1e2d4a;
        border-radius: 16px;
        padding: 1.4rem 1.6rem;
        margin-bottom: 1rem;
        transition: border-color 0.2s;
    }
    .canvasser-card.flagged {
        border-color: #ef444440;
        background: #1a1020;
    }
    .canvasser-card.watch {
        border-color: #f59e0b40;
        background: #1a1810;
    }
    .canvasser-card.clean {
        border-color: #22c55e30;
    }
    .canvasser-name {
        font-family: 'Syne', sans-serif;
        font-size: 1.1rem;
        font-weight: 700;
        margin-bottom: 6px;
    }
    .flag-tag {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.7rem;
        font-weight: 500;
        margin: 2px 3px 2px 0;
    }
    .flag-red { background: #ef444420; color: #ef4444; border: 1px solid #ef444440; }
    .flag-yellow { background: #f59e0b20; color: #f59e0b; border: 1px solid #f59e0b40; }
    .flag-green { background: #22c55e20; color: #22c55e; border: 1px solid #22c55e40; }
    .flag-blue { background: #3b82f620; color: #3b82f6; border: 1px solid #3b82f640; }
    .flag-purple { background: #a78bfa20; color: #a78bfa; border: 1px solid #a78bfa40; }
    .integrity-clean { color: #22c55e; font-size: 0.75rem; font-weight: 600; }
    .integrity-watch { color: #f59e0b; font-size: 0.75rem; font-weight: 600; }
    .integrity-flagged { color: #ef4444; font-size: 0.75rem; font-weight: 600; }
    .section-header {
        font-family: 'Syne', sans-serif;
        font-size: 1.4rem;
        font-weight: 700;
        margin: 2rem 0 1rem 0;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #1e2d4a;
    }
    .inline-bar-container {
        background: #1e293b;
        border-radius: 4px;
        height: 6px;
        margin-top: 4px;
        overflow: hidden;
    }
    .inline-bar-fill {
        height: 100%;
        border-radius: 4px;
    }
    .impossible-flag {
        background: #ef444415;
        border: 1px solid #ef444440;
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 0.72rem;
        color: #ef4444;
        margin-top: 6px;
    }
    .stExpander {
        border: 1px solid #1e2d4a !important;
        border-radius: 12px !important;
    }
    div[data-testid="stMetricValue"] {
        font-family: 'Syne', sans-serif !important;
    }
    .upload-hint {
        font-size: 0.75rem;
        color: #64748b;
        margin-top: 4px;
    }
</style>
""", unsafe_allow_html=True)

# ─── SCRIPT BRANCHING RULES ───────────────────────────────────────────────────
# Maps question names from VAN data to script logic
Q1   = "Q1. Narcan Kit Ask"
Q1B  = "Q1B Mentalhealth_988"
Q2   = "Q2: NJFam/Medicaid"
QA2  = "QA2. workreq/renewal"
QA3  = "QA3 Uninsured/unsure"
Q4A  = "26_DHS_Demo"
Q4B  = "26_DHS_Age"
Q4C  = "26_DHS_Gender"
Q5   = "26_Contact_Info"

# Q2 responses that should route to QA2
QA2_TRIGGERS = ["Private Insurance", "NJ FamilyCare"]
# Q2 responses that should route to QA3
QA3_TRIGGERS = ["No - Uninsured", "Unsure", "Uninsured"]

def validate_resident_path(resident_responses: dict) -> list:
    """
    Given a dict of {question: response} for one resident,
    return a list of script violation strings.
    """
    violations = []
    qs = set(resident_responses.keys())

    # Rule 1: Q1 must always be present
    if Q1 not in qs:
        violations.append("Missing Q1 (Narcan Kit) — survey never started properly")

    # Rule 2: Q1B must always follow Q1
    if Q1 in qs and Q1B not in qs:
        violations.append("Q1B (988) skipped — required after Q1 regardless of answer")

    # Rule 3: Q2 must always be present
    if Q2 not in qs and Q1 in qs:
        violations.append("Missing Q2 (Insurance) — required for all contacts")

    if Q2 in qs:
        q2_answer = resident_responses[Q2]

        # Rule 4: QA2 only valid for insured residents
        if QA2 in qs:
            if not any(t.lower() in q2_answer.lower() for t in QA2_TRIGGERS):
                violations.append(
                    f"IMPOSSIBLE PATH: Has QA2 (work requirements) but Q2='{q2_answer}' "
                    f"— QA2 only asked to insured residents"
                )

        # Rule 5: QA3 only valid for uninsured/unsure
        if QA3 in qs:
            if not any(t.lower() in q2_answer.lower() for t in QA3_TRIGGERS):
                violations.append(
                    f"IMPOSSIBLE PATH: Has QA3 (barriers) but Q2='{q2_answer}' "
                    f"— QA3 only asked to uninsured/unsure residents"
                )

        # Rule 6: QA2 and QA3 mutually exclusive
        if QA2 in qs and QA3 in qs:
            violations.append(
                "IMPOSSIBLE PATH: Has both QA2 and QA3 — mutually exclusive per script"
            )

        # Rule 8: Q5 flag for uninsured getting contact info ask
        # (soft flag — not impossible but worth noting)
        if Q5 in qs:
            if any(t.lower() in q2_answer.lower() for t in QA3_TRIGGERS):
                violations.append(
                    f"Q5 (contact info) collected for uninsured resident — "
                    f"script only routes insured residents to Q5"
                )

    # Rule 7: Demographics should always be present for completed surveys
    if Q1 in qs and Q2 in qs:
        missing_demos = []
        if Q4A not in qs: missing_demos.append("Race")
        if Q4B not in qs: missing_demos.append("Age")
        if Q4C not in qs: missing_demos.append("Gender")
        if missing_demos:
            violations.append(f"Demographics skipped: {', '.join(missing_demos)}")

    return violations


def compute_canvasser_integrity(name, contact_df, survey_df, team_contact_df):
    """Full integrity analysis for one canvasser."""
    results = {
        "score": "clean",
        "perf_flags": [],
        "integrity_flags": [],
        "impossible_paths": [],
        "script_violations": [],
        "skip_rate": 0,
        "impossible_rate": 0,
    }

    if len(contact_df) == 0:
        return results

    doors = len(contact_df)
    contacted = len(contact_df[contact_df["ResultShortName"] == "Canvassed"])
    not_home = len(contact_df[contact_df["ResultShortName"] == "Not Home"])
    not_home_pct = (not_home / doors * 100) if doors > 0 else 0
    unique_survey_ids = survey_df["Voter File VANID"].nunique() if len(survey_df) > 0 else 0

    # ── PERFORMANCE FLAGS ──────────────────────────────────────────────────────
    # Team averages
    team_doors = len(team_contact_df)
    team_canvassers = team_contact_df["CanvassedBy"].nunique()
    avg_doors = team_doors / team_canvassers if team_canvassers > 0 else 0
    team_contacted = len(team_contact_df[team_contact_df["ResultShortName"] == "Canvassed"])
    team_contact_rate = (team_contacted / team_doors * 100) if team_doors > 0 else 0
    my_contact_rate = (contacted / doors * 100) if doors > 0 else 0

    if doors > avg_doors * 1.2:
        results["perf_flags"].append(("🟢 Top Performer", "flag-green"))
    if not_home_pct > 70:
        results["perf_flags"].append(("🔴 Low Contact Rate", "flag-red"))
    if unique_survey_ids == 0 and doors > 3:
        results["perf_flags"].append(("🔴 No Surveys", "flag-red"))

    # Days active / avg per day
    if "DateCanvassed" in contact_df.columns:
        days_active = contact_df["DateCanvassed"].nunique()
        avg_per_day = doors / days_active if days_active > 0 else 0
        daily_counts = contact_df.groupby("DateCanvassed").size()
        if len(daily_counts) > 1:
            cv = daily_counts.std() / daily_counts.mean()
            if cv > 0.8:
                results["perf_flags"].append(("⚠️ Inconsistent Daily Output", "flag-yellow"))
    else:
        days_active = 0
        avg_per_day = 0

    results["days_active"] = days_active
    results["avg_per_day"] = round(avg_per_day, 1)
    results["doors"] = doors
    results["contacted"] = contacted
    results["not_home_pct"] = round(not_home_pct, 1)
    results["surveys"] = unique_survey_ids
    results["contact_rate"] = round(my_contact_rate, 1)

    if len(survey_df) == 0:
        return results

    # ── SCRIPT PATH VALIDATION ─────────────────────────────────────────────────
    pivoted = survey_df.pivot_table(
        index="Voter File VANID",
        columns="SurveyQuestionLongName",
        values="SurveyResponseName",
        aggfunc="first"
    )

    total_residents = len(pivoted)
    violation_count = 0
    impossible_count = 0

    for vanid, row in pivoted.iterrows():
        resident_resp = {q: v for q, v in row.items() if pd.notna(v)}
        violations = validate_resident_path(resident_resp)
        if violations:
            violation_count += 1
            has_impossible = any("IMPOSSIBLE PATH" in v for v in violations)
            if has_impossible:
                impossible_count += 1
            results["script_violations"].append({
                "vanid": vanid,
                "violations": violations,
                "impossible": has_impossible
            })

    results["skip_rate"] = round((violation_count / total_residents * 100), 1) if total_residents > 0 else 0
    results["impossible_rate"] = round((impossible_count / total_residents * 100), 1) if total_residents > 0 else 0
    results["total_surveyed"] = total_residents

    # ── DATA INTEGRITY FLAGS ───────────────────────────────────────────────────
    # Impossible paths
    if impossible_count > 0:
        results["integrity_flags"].append((
            f"🚩 {impossible_count} impossible script path{'s' if impossible_count > 1 else ''}",
            "flag-red"
        ))

    # Uniform responses per question
    for q in survey_df["SurveyQuestionLongName"].unique():
        q_responses = survey_df[survey_df["SurveyQuestionLongName"] == q]["SurveyResponseName"]
        if len(q_responses) >= 5:
            top_pct = q_responses.value_counts().iloc[0] / len(q_responses)
            if top_pct >= 0.92:
                top_resp = q_responses.value_counts().index[0]
                results["integrity_flags"].append((
                    f"⚠️ Uniform responses on '{q}': {round(top_pct*100)}% answered '{top_resp}'",
                    "flag-yellow"
                ))

    # Outlier contact rate
    if abs(my_contact_rate - team_contact_rate) > 25:
        direction = "above" if my_contact_rate > team_contact_rate else "below"
        results["integrity_flags"].append((
            f"⚠️ Contact rate {round(my_contact_rate)}% vs team avg {round(team_contact_rate)}% ({direction})",
            "flag-yellow"
        ))

    # Survey/door ratio anomaly
    if doors >= 5:
        ratio = unique_survey_ids / doors
        if ratio > 0.85:
            results["integrity_flags"].append((
                f"⚠️ Survey/door ratio {round(ratio*100)}% — unusually high",
                "flag-yellow"
            ))

    # Date clustering
    if "DateCanvassed" in survey_df.columns:
        by_day = survey_df.groupby("DateCanvassed").size()
        if len(by_day) > 0:
            max_day_pct = by_day.max() / len(survey_df)
            if max_day_pct >= 0.85 and len(survey_df) >= 5:
                max_day = by_day.idxmax()
                results["integrity_flags"].append((
                    f"⚠️ {round(max_day_pct*100)}% of surveys entered on single date ({max_day})",
                    "flag-yellow"
                ))

    # Score
    has_impossible = any("impossible" in f[0].lower() or "🚩" in f[0] for f in results["integrity_flags"])
    if has_impossible or results["impossible_rate"] > 0:
        results["score"] = "flagged"
    elif len(results["integrity_flags"]) >= 2 or results["skip_rate"] > 30:
        results["score"] = "flagged"
    elif len(results["integrity_flags"]) >= 1 or results["skip_rate"] > 15:
        results["score"] = "watch"
    else:
        results["score"] = "clean"

    return results


# ─── PARSE HELPERS ────────────────────────────────────────────────────────────
def load_van_file(uploaded_file):
    """Load a VAN export (.xls tab-separated, UTF-16 or UTF-8)."""
    raw = uploaded_file.read()
    for enc in ["utf-16", "utf-8-sig", "utf-8"]:
        try:
            text = raw.decode(enc)
            if text.startswith("\ufeff"):
                text = text[1:]
            df = pd.read_csv(io.StringIO(text), sep="\t", dtype=str)
            df.columns = df.columns.str.strip()
            return df
        except Exception:
            continue
    return None


def get_week_key(date_series):
    """Convert date strings to week-start (Monday) keys."""
    dates = pd.to_datetime(date_series, errors="coerce")
    return dates.dt.to_period("W-SUN").dt.start_time.dt.strftime("%Y-%m-%d")


# ─── SESSION STATE ────────────────────────────────────────────────────────────
if "contact_history" not in st.session_state:
    st.session_state.contact_history = pd.DataFrame()
if "survey_history" not in st.session_state:
    st.session_state.survey_history = pd.DataFrame()
if "weeks_loaded" not in st.session_state:
    st.session_state.weeks_loaded = []

# ─── HEADER ───────────────────────────────────────────────────────────────────
col_title, col_controls = st.columns([2, 1])
with col_title:
    st.markdown('<div class="dash-title">Team Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="dash-sub">Field Operations · NJ</div>', unsafe_allow_html=True)

with col_controls:
    dark_mode = st.toggle("Dark mode", value=True)
    if not dark_mode:
        st.markdown("""
        <style>
            .canvasser-card { background: #ffffff !important; border-color: #e2e8f0 !important; }
            .canvasser-card.flagged { background: #fff5f5 !important; }
            .canvasser-card.watch { background: #fffbeb !important; }
            .metric-card { background: #f8fafc !important; border-color: #e2e8f0 !important; }
            .metric-label { color: #94a3b8 !important; }
            .metric-value { color: #0f172a !important; }
            html, body, [class*="css"] { background-color: #f1f5f9 !important; color: #0f172a !important; }
        </style>
        """, unsafe_allow_html=True)

st.divider()

# ─── UPLOAD SECTION ───────────────────────────────────────────────────────────
with st.expander("📂 Upload This Week's VAN Exports", expanded=st.session_state.contact_history.empty):
    st.markdown("Upload both files each week — duplicate records are automatically skipped.")
    ucol1, ucol2 = st.columns(2)

    with ucol1:
        st.markdown("**Contact History**")
        st.markdown('<div class="upload-hint">The file with ResultShortName / CanvassedBy</div>', unsafe_allow_html=True)
        contact_file = st.file_uploader("Contact history export", type=["xls", "csv", "tsv", "txt"], key="contact_upload", label_visibility="collapsed")

    with ucol2:
        st.markdown("**Survey Responses**")
        st.markdown('<div class="upload-hint">The file with SurveyQuestionLongName / SurveyResponseName</div>', unsafe_allow_html=True)
        survey_file = st.file_uploader("Survey export", type=["xls", "csv", "tsv", "txt"], key="survey_upload", label_visibility="collapsed")

    if st.button("➕ Add to Dashboard", type="primary", disabled=(contact_file is None and survey_file is None)):
        added_contacts = 0
        added_surveys = 0

        if contact_file:
            df = load_van_file(contact_file)
            if df is not None:
                # Filter to real canvassers only
                if "IsCanvasser" in df.columns:
                    df = df[df["IsCanvasser"].str.upper() == "TRUE"]
                # Deduplicate
                if not st.session_state.contact_history.empty:
                    key = ["Voter File VANID", "DateCanvassed", "ResultShortName"]
                    key = [c for c in key if c in df.columns]
                    existing_keys = set(
                        st.session_state.contact_history[key].apply(tuple, axis=1)
                    )
                    df = df[~df[key].apply(tuple, axis=1).isin(existing_keys)]
                st.session_state.contact_history = pd.concat(
                    [st.session_state.contact_history, df], ignore_index=True
                )
                added_contacts = len(df)

        if survey_file:
            df = load_van_file(survey_file)
            if df is not None:
                if "IsCanvasser" in df.columns:
                    df = df[df["IsCanvasser"].str.upper() == "TRUE"]
                if not st.session_state.survey_history.empty:
                    key = ["Voter File VANID", "SurveyQuestionLongName", "DateCanvassed"]
                    key = [c for c in key if c in df.columns]
                    existing_keys = set(
                        st.session_state.survey_history[key].apply(tuple, axis=1)
                    )
                    df = df[~df[key].apply(tuple, axis=1).isin(existing_keys)]
                st.session_state.survey_history = pd.concat(
                    [st.session_state.survey_history, df], ignore_index=True
                )
                added_surveys = len(df)

        st.success(f"✅ Added {added_contacts:,} contact records + {added_surveys:,} survey responses")
        st.rerun()

    if not st.session_state.contact_history.empty:
        if st.button("🗑️ Clear All Data", type="secondary"):
            st.session_state.contact_history = pd.DataFrame()
            st.session_state.survey_history = pd.DataFrame()
            st.rerun()

# ─── STOP IF NO DATA ──────────────────────────────────────────────────────────
if st.session_state.contact_history.empty:
    st.info("Upload your contact history and survey exports above to get started.")
    st.stop()

# Validate expected columns exist
required_contact_cols = ["ResultShortName", "CanvassedBy", "DateCanvassed", "Voter File VANID"]
missing_cols = [c for c in required_contact_cols if c not in st.session_state.contact_history.columns]
if missing_cols:
    missing_str = ", ".join(missing_cols)
    available_str = ", ".join(st.session_state.contact_history.columns.tolist())
    st.error("Contact history file is missing expected columns: " + missing_str)
    st.caption("Available columns: " + available_str)
    st.stop()

# ─── WEEK SELECTOR ────────────────────────────────────────────────────────────
contact_df = st.session_state.contact_history.copy()
survey_df  = st.session_state.survey_history.copy()

if "DateCanvassed" in contact_df.columns:
    contact_df["WeekKey"] = get_week_key(contact_df["DateCanvassed"])
if "DateCanvassed" in survey_df.columns:
    survey_df["WeekKey"] = get_week_key(survey_df["DateCanvassed"])
elif "DateCreated" in survey_df.columns:
    survey_df["WeekKey"] = get_week_key(survey_df["DateCreated"])

all_weeks = sorted(contact_df["WeekKey"].dropna().unique(), reverse=True)
week_labels = {w: f"Week of {datetime.strptime(w, '%Y-%m-%d').strftime('%b %d')}" for w in all_weeks}

if len(all_weeks) > 1:
    selected_week = st.selectbox(
        "Viewing week:",
        options=all_weeks,
        format_func=lambda w: week_labels.get(w, w),
        index=0
    )
else:
    selected_week = all_weeks[0] if all_weeks else None
    if selected_week:
        st.caption(f"📅 {week_labels.get(selected_week, selected_week)}")

if not selected_week:
    st.warning("No date information found in uploaded files.")
    st.stop()

# Filter to selected week
wk_contacts = contact_df[contact_df["WeekKey"] == selected_week].copy()
wk_surveys  = survey_df[survey_df["WeekKey"] == selected_week].copy() if "WeekKey" in survey_df.columns else survey_df.copy()

# Previous week for WoW
prev_weeks = [w for w in all_weeks if w < selected_week]
prev_week = prev_weeks[0] if prev_weeks else None
prev_contacts = contact_df[contact_df["WeekKey"] == prev_week] if prev_week else pd.DataFrame()

# ─── CAMPAIGN TOTALS ──────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Campaign Overview</div>', unsafe_allow_html=True)

total_doors     = len(wk_contacts)
total_contacted = len(wk_contacts[wk_contacts["ResultShortName"] == "Canvassed"]) if "ResultShortName" in wk_contacts.columns else 0
total_surveys   = wk_surveys["Voter File VANID"].nunique() if not wk_surveys.empty and "Voter File VANID" in wk_surveys.columns else 0
total_canvassers = wk_contacts["CanvassedBy"].nunique() if "CanvassedBy" in wk_contacts.columns else 0
contact_rate    = (total_contacted / total_doors * 100) if total_doors > 0 else 0
prev_doors      = len(prev_contacts)
wow_doors       = total_doors - prev_doors if prev_week else None

m1, m2, m3, m4 = st.columns(4)

with m1:
    delta = f"{'+' if wow_doors and wow_doors > 0 else ''}{wow_doors}" if wow_doors is not None else None
    st.metric("Total Doors", f"{total_doors:,}", delta=delta)
with m2:
    st.metric("Contacted", f"{total_contacted:,}", delta=f"{contact_rate:.0f}% contact rate")
with m3:
    st.metric("Surveys Completed", f"{total_surveys:,}")
with m4:
    st.metric("Active Canvassers", total_canvassers)

# ─── SORT & FILTER CONTROLS ───────────────────────────────────────────────────
st.markdown('<div class="section-header">Canvasser Cards</div>', unsafe_allow_html=True)

ctrl1, ctrl2, ctrl3 = st.columns([1, 1, 2])
with ctrl1:
    sort_by = st.selectbox("Sort by", ["Doors", "Contacted", "Surveys", "Integrity Score", "Avg Doors/Day"])
with ctrl2:
    filter_by = st.selectbox("Filter", ["All", "Flagged / Watch", "Clean only"])
with ctrl3:
    search = st.text_input("Search canvasser", placeholder="Type a name...")

# ─── BUILD CANVASSER DATA ─────────────────────────────────────────────────────
canvasser_names = sorted(wk_contacts["CanvassedBy"].dropna().unique())

all_results = {}
for name in canvasser_names:
    c_df = wk_contacts[wk_contacts["CanvassedBy"] == name]
    s_df = wk_surveys[wk_surveys["CanvassedBy"] == name] if not wk_surveys.empty and "CanvassedBy" in wk_surveys.columns else pd.DataFrame()
    all_results[name] = compute_canvasser_integrity(name, c_df, s_df, wk_contacts)

# Sort
score_order = {"flagged": 0, "watch": 1, "clean": 2}
def sort_key(name):
    r = all_results[name]
    if sort_by == "Doors": return -r.get("doors", 0)
    if sort_by == "Contacted": return -r.get("contacted", 0)
    if sort_by == "Surveys": return -r.get("surveys", 0)
    if sort_by == "Integrity Score": return score_order.get(r.get("score", "clean"), 2)
    if sort_by == "Avg Doors/Day": return -r.get("avg_per_day", 0)
    return 0

canvasser_names = sorted(canvasser_names, key=sort_key)

# Filter
if filter_by == "Flagged / Watch":
    canvasser_names = [n for n in canvasser_names if all_results[n]["score"] in ("flagged", "watch")]
elif filter_by == "Clean only":
    canvasser_names = [n for n in canvasser_names if all_results[n]["score"] == "clean"]

if search:
    canvasser_names = [n for n in canvasser_names if search.lower() in n.lower()]

st.caption(f"Showing {len(canvasser_names)} of {len(all_results)} canvassers")

# ─── RENDER CARDS ─────────────────────────────────────────────────────────────
for name in canvasser_names:
    r = all_results[name]
    score = r["score"]
    card_class = f"canvasser-card {score}"

    # WoW for this canvasser
    if prev_week and not prev_contacts.empty:
        prev_n = len(prev_contacts[prev_contacts["CanvassedBy"] == name])
        wow = r["doors"] - prev_n
        wow_str = f"{'▲' if wow > 0 else '▼' if wow < 0 else '—'} {abs(wow)} vs last week"
        wow_color = "#22c55e" if wow > 0 else "#ef4444" if wow < 0 else "#64748b"
    else:
        wow_str = None
        wow_color = "#64748b"

    # Integrity label
    integrity_labels = {
        "clean":   ("● Data looks clean", "integrity-clean"),
        "watch":   ("● Worth monitoring", "integrity-watch"),
        "flagged": ("● Integrity concern", "integrity-flagged"),
    }
    int_label, int_class = integrity_labels[score]

    with st.container():
        st.markdown(f'<div class="{card_class}">', unsafe_allow_html=True)

        # Name row
        name_col, wow_col = st.columns([3, 1])
        with name_col:
            st.markdown(f'<div class="canvasser-name">{name}</div>', unsafe_allow_html=True)
            st.markdown(f'<span class="{int_class}">{int_label}</span>', unsafe_allow_html=True)

            # Performance flags
            flag_html = ""
            for flag_text, flag_class in r.get("perf_flags", []):
                flag_html += f'<span class="flag-tag {flag_class}">{flag_text}</span>'
            for flag_text, flag_class in r.get("integrity_flags", [])[:2]:
                flag_html += f'<span class="flag-tag {flag_class}">{flag_text}</span>'
            if flag_html:
                st.markdown(flag_html, unsafe_allow_html=True)

        with wow_col:
            if wow_str:
                st.markdown(
                    f'<div style="text-align:right; font-size:0.85rem; color:{wow_color}; '
                    f'font-weight:600; padding-top:6px;">{wow_str}</div>',
                    unsafe_allow_html=True
                )

        st.markdown("</div>", unsafe_allow_html=True)

        # Metrics row
        mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)
        with mc1:
            st.metric("Doors", r.get("doors", 0))
        with mc2:
            st.metric("Contacted", r.get("contacted", 0))
        with mc3:
            st.metric("Surveys", r.get("surveys", 0))
        with mc4:
            st.metric("Not Home %", f"{r.get('not_home_pct', 0)}%")
        with mc5:
            st.metric("Avg Doors/Day", r.get("avg_per_day", 0))
        with mc6:
            st.metric("Days Active", r.get("days_active", 0))

        # Expandable detail
        with st.expander(f"🔍 Deep dive — {name.split(',')[0]}"):

            d1, d2 = st.columns(2)

            with d1:
                # Contact results breakdown
                c_df = wk_contacts[wk_contacts["CanvassedBy"] == name]
                result_counts = c_df["ResultShortName"].value_counts().reset_index()
                result_counts.columns = ["Result", "Count"]
                color_map = {
                    "Canvassed": "#22c55e", "Not Home": "#6b7fa3",
                    "Refused": "#f59e0b", "Inaccessible": "#a78bfa",
                    "Hostile": "#ef4444", "Other Language": "#06b6d4"
                }
                fig = go.Figure(go.Bar(
                    x=result_counts["Result"],
                    y=result_counts["Count"],
                    marker_color=[color_map.get(r, "#64748b") for r in result_counts["Result"]],
                    text=result_counts["Count"],
                    textposition="outside"
                ))
                fig.update_layout(
                    title="Contact Results",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#94a3b8", size=11),
                    height=250,
                    margin=dict(t=40, b=20, l=0, r=0),
                    showlegend=False,
                    xaxis=dict(showgrid=False),
                    yaxis=dict(showgrid=True, gridcolor="#1e2d4a")
                )
                st.plotly_chart(fig, use_container_width=True)

            with d2:
                # Daily doors trend
                if "DateCanvassed" in c_df.columns:
                    daily = c_df.groupby("DateCanvassed").size().reset_index()
                    daily.columns = ["Date", "Doors"]
                    fig2 = go.Figure(go.Scatter(
                        x=daily["Date"], y=daily["Doors"],
                        mode="lines+markers+text",
                        line=dict(color="#3b82f6", width=2),
                        marker=dict(size=7, color="#3b82f6"),
                        text=daily["Doors"], textposition="top center",
                        textfont=dict(size=10)
                    ))
                    fig2.update_layout(
                        title="Doors Per Day",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#94a3b8", size=11),
                        height=250,
                        margin=dict(t=40, b=20, l=0, r=0),
                        xaxis=dict(showgrid=False),
                        yaxis=dict(showgrid=True, gridcolor="#1e2d4a")
                    )
                    st.plotly_chart(fig2, use_container_width=True)

            # Survey response breakdown
            s_df = wk_surveys[wk_surveys["CanvassedBy"] == name] if not wk_surveys.empty and "CanvassedBy" in wk_surveys.columns else pd.DataFrame()
            if not s_df.empty and "SurveyQuestionLongName" in s_df.columns:
                st.markdown("**Survey Responses**")
                q_cols = st.columns(3)
                questions = s_df["SurveyQuestionLongName"].unique()
                for i, q in enumerate(questions):
                    with q_cols[i % 3]:
                        q_data = s_df[s_df["SurveyQuestionLongName"] == q]["SurveyResponseName"].value_counts()
                        total_q = q_data.sum()
                        st.markdown(f"<div style='font-size:0.7rem;color:#64748b;margin-bottom:4px;'>{q}</div>", unsafe_allow_html=True)
                        COLORS = ["#3b82f6","#22c55e","#f59e0b","#a78bfa","#ef4444","#06b6d4"]
                        for j, (resp, cnt) in enumerate(q_data.items()):
                            pct = int(cnt / total_q * 100)
                            color = COLORS[j % len(COLORS)]
                            st.markdown(
                                f'<div style="display:flex;justify-content:space-between;font-size:0.72rem;margin-bottom:2px;">'
                                f'<span>{resp}</span><span style="color:#64748b">{pct}%</span></div>'
                                f'<div class="inline-bar-container"><div class="inline-bar-fill" style="width:{pct}%;background:{color};"></div></div>',
                                unsafe_allow_html=True
                            )

            # Script violations
            violations_list = r.get("script_violations", [])
            if violations_list:
                st.markdown(f"**Script Path Violations** — {r.get('skip_rate',0)}% of surveys had issues")
                impossible_only = [v for v in violations_list if v["impossible"]]
                other = [v for v in violations_list if not v["impossible"]]

                if impossible_only:
                    st.error(f"🚩 {len(impossible_only)} resident(s) with IMPOSSIBLE response paths:")
                    for v in impossible_only[:5]:
                        with st.container():
                            st.markdown(
                                f'<div class="impossible-flag">VANID {v["vanid"]}: '
                                + " | ".join(v["violations"]) + "</div>",
                                unsafe_allow_html=True
                            )
                    if len(impossible_only) > 5:
                        st.caption(f"... and {len(impossible_only) - 5} more")

                if other:
                    with st.expander(f"⚠️ {len(other)} skipped/incomplete surveys"):
                        for v in other[:10]:
                            st.caption(f"VANID {v['vanid']}: {' | '.join(v['violations'])}")
                        if len(other) > 10:
                            st.caption(f"... and {len(other) - 10} more")
            else:
                if not s_df.empty:
                    st.success("✅ All surveyed residents followed correct script paths")

            st.caption(f"→ For idle periods, pacing & street-level analysis, use the Agent Monitor page with {name.split(',')[0]}'s individual file.")

        st.divider()

# ─── SURVEY ANALYTICS SECTION ─────────────────────────────────────────────────
st.markdown('<div class="section-header">📊 Data Analytics — Survey Response Trends</div>', unsafe_allow_html=True)

if wk_surveys.empty or "SurveyQuestionLongName" not in wk_surveys.columns:
    st.info("Upload a survey file to see response analytics.")
    st.stop()

questions = sorted(wk_surveys["SurveyQuestionLongName"].dropna().unique())
selected_q = st.selectbox("Select survey question", questions)

if selected_q:
    qa1, qa2 = st.columns([1, 1.6])

    with qa1:
        st.markdown("**Overall distribution (all weeks)**")
        dist = survey_df[survey_df["SurveyQuestionLongName"] == selected_q]["SurveyResponseName"].value_counts().reset_index()
        dist.columns = ["Response", "Count"]
        dist["Pct"] = (dist["Count"] / dist["Count"].sum() * 100).round(1)
        COLORS = ["#3b82f6","#22c55e","#f59e0b","#a78bfa","#ef4444","#06b6d4","#f97316"]
        fig = go.Figure(go.Bar(
            y=dist["Response"], x=dist["Count"],
            orientation="h",
            marker_color=COLORS[:len(dist)],
            text=[f"{p}%" for p in dist["Pct"]],
            textposition="outside"
        ))
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94a3b8", size=11),
            height=max(200, len(dist) * 45),
            margin=dict(t=10, b=10, l=0, r=60),
            xaxis=dict(showgrid=True, gridcolor="#1e2d4a"),
            yaxis=dict(showgrid=False)
        )
        st.plotly_chart(fig, use_container_width=True)

    with qa2:
        if len(all_weeks) > 1:
            st.markdown("**Week-over-week trend**")
            trend_rows = []
            for wk in sorted(all_weeks):
                wk_q = survey_df[(survey_df.get("WeekKey", pd.Series(dtype=str)) == wk) &
                                 (survey_df["SurveyQuestionLongName"] == selected_q)]
                if "WeekKey" in survey_df.columns:
                    wk_q = survey_df[(survey_df["WeekKey"] == wk) & (survey_df["SurveyQuestionLongName"] == selected_q)]
                counts = wk_q["SurveyResponseName"].value_counts()
                for resp, cnt in counts.items():
                    trend_rows.append({"Week": week_labels.get(wk, wk), "Response": resp, "Count": cnt})

            if trend_rows:
                trend_df = pd.DataFrame(trend_rows)
                fig2 = px.bar(
                    trend_df, x="Week", y="Count", color="Response",
                    color_discrete_sequence=COLORS,
                    barmode="stack"
                )
                fig2.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#94a3b8", size=11),
                    height=300,
                    margin=dict(t=10, b=20, l=0, r=0),
                    legend=dict(font=dict(size=10)),
                    xaxis=dict(showgrid=False),
                    yaxis=dict(showgrid=True, gridcolor="#1e2d4a")
                )
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Upload multiple weeks of data to see trends over time.")

    # Canvasser comparison for this question
    st.markdown(f"**Canvasser response distribution for: _{selected_q}_**")
    if "CanvassedBy" in wk_surveys.columns:
        comp_data = wk_surveys[wk_surveys["SurveyQuestionLongName"] == selected_q]
        pivot = comp_data.pivot_table(
            index="CanvassedBy", columns="SurveyResponseName",
            values="Voter File VANID", aggfunc="count", fill_value=0
        ).reset_index()
        pivot.columns.name = None

        if len(pivot) > 0:
            fig3 = go.Figure()
            resp_cols = [c for c in pivot.columns if c != "CanvassedBy"]
            for i, resp in enumerate(resp_cols):
                fig3.add_trace(go.Bar(
                    name=resp, x=pivot["CanvassedBy"], y=pivot[resp],
                    marker_color=COLORS[i % len(COLORS)]
                ))
            fig3.update_layout(
                barmode="stack",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#94a3b8", size=11),
                height=300,
                margin=dict(t=10, b=60, l=0, r=0),
                legend=dict(font=dict(size=10)),
                xaxis=dict(showgrid=False, tickangle=-30),
                yaxis=dict(showgrid=True, gridcolor="#1e2d4a")
            )
            st.plotly_chart(fig3, use_container_width=True)
            st.caption("Outliers in this chart — canvassers with very different response distributions vs the team — are worth investigating.")
