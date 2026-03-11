import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
from datetime import datetime
import io

st.set_page_config(page_title="Team Dashboard", layout="wide", initial_sidebar_state="collapsed")

# ─── STYLES ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    .dash-title { font-family:'Syne',sans-serif; font-size:2rem; font-weight:800; letter-spacing:-0.5px; margin-bottom:0; }
    .dash-sub { font-size:0.8rem; color:#94a3b8; letter-spacing:2px; text-transform:uppercase; margin-bottom:1.5rem; }
    .canvasser-name { font-family:'Syne',sans-serif; font-size:1.1rem; font-weight:700; margin-bottom:4px; }
    .flag-tag { display:inline-block; padding:3px 10px; border-radius:20px; font-size:0.7rem; font-weight:500; margin:2px 3px 2px 0; }
    .flag-red    { background:#ef444420; color:#ef4444; border:1px solid #ef444440; }
    .flag-yellow { background:#f59e0b20; color:#f59e0b; border:1px solid #f59e0b40; }
    .flag-green  { background:#22c55e20; color:#22c55e; border:1px solid #22c55e40; }
    .flag-blue   { background:#3b82f620; color:#3b82f6; border:1px solid #3b82f640; }
    .integrity-clean   { color:#22c55e; font-size:0.75rem; font-weight:600; }
    .integrity-watch   { color:#f59e0b; font-size:0.75rem; font-weight:600; }
    .integrity-flagged { color:#ef4444; font-size:0.75rem; font-weight:600; }
    .section-header { font-family:'Syne',sans-serif; font-size:1.4rem; font-weight:700; margin:2rem 0 1rem 0; padding-bottom:0.5rem; border-bottom:1px solid #1e2d4a; }
    .impossible-box { background:#ef444412; border:1px solid #ef444440; border-radius:8px; padding:10px 14px; font-size:0.75rem; color:#ef4444; margin:4px 0; }
    .upload-hint { font-size:0.75rem; color:#64748b; margin-top:4px; }
    div[data-testid="stMetricValue"] { font-family:'Syne',sans-serif !important; }
</style>
""", unsafe_allow_html=True)

# ─── SCRIPT BRANCHING RULES ───────────────────────────────────────────────────
Q1  = "Q1. Narcan Kit Ask"
Q1B = "Q1B Mentalhealth_988"
Q2  = "Q2: NJFam/Medicaid"
QA2 = "QA2. workreq/renewal"
QA3 = "QA3 Uninsured/unsure"
Q4A = "26_DHS_Demo"
Q4B = "26_DHS_Age"
Q4C = "26_DHS_Gender"
Q5  = "26_Contact_Info"

QA2_TRIGGERS = ["private insurance", "nj familycare", "njfamily", "insured", "yes curr"]
QA3_TRIGGERS = ["uninsured", "unsure", "no -"]

def validate_resident_path(resp):
    violations = []
    qs = set(resp.keys())
    if Q1 not in qs:
        violations.append("Missing Q1 — survey never started properly")
    if Q1 in qs and Q1B not in qs:
        violations.append("Q1B (988) skipped — required after Q1")
    if Q2 not in qs and Q1 in qs:
        violations.append("Missing Q2 (Insurance) — required for all contacts")
    if Q2 in qs:
        q2 = resp[Q2].lower()
        if QA2 in qs and not any(t in q2 for t in QA2_TRIGGERS):
            violations.append("IMPOSSIBLE PATH: Has QA2 but Q2='" + resp[Q2] + "' — QA2 only for insured residents")
        if QA3 in qs and not any(t in q2 for t in QA3_TRIGGERS):
            violations.append("IMPOSSIBLE PATH: Has QA3 but Q2='" + resp[Q2] + "' — QA3 only for uninsured/unsure")
        if QA2 in qs and QA3 in qs:
            violations.append("IMPOSSIBLE PATH: Has both QA2 and QA3 — mutually exclusive per script")
    if Q1 in qs and Q2 in qs:
        missing_demos = [n for q, n in [(Q4A,"Race"),(Q4B,"Age"),(Q4C,"Gender")] if q not in qs]
        if missing_demos:
            violations.append("Demographics skipped: " + ", ".join(missing_demos))
    return violations

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def load_van_file(uploaded_file):
    raw = uploaded_file.read()
    for enc in ["utf-16", "utf-8-sig", "utf-8", "latin-1"]:
        try:
            text = raw.decode(enc)
            # Strip all BOM variants
            text = text.lstrip("\ufeff\ufffe\xef\xbb\xbf")
            df = pd.read_csv(io.StringIO(text), sep="\t", dtype=str)
            # Aggressively clean column names — strip spaces, BOM, invisible chars
            df.columns = df.columns.str.strip().str.replace("\ufeff","",regex=False).str.replace("\ufffe","",regex=False).str.replace("\u200b","",regex=False)
            if len(df.columns) > 1:
                return df
        except Exception:
            continue
    for enc in ["utf-8-sig", "utf-8", "latin-1"]:
        try:
            text = raw.decode(enc)
            df = pd.read_csv(io.StringIO(text), dtype=str)
            df.columns = df.columns.str.strip().str.replace("\ufeff","",regex=False).str.replace("\ufffe","",regex=False).str.replace("\u200b","",regex=False)
            if len(df.columns) > 1:
                return df
        except Exception:
            continue
    return None

def parse_dates(series):
    return pd.to_datetime(series, errors="coerce").dt.normalize()

def get_week_key(series):
    dates = pd.to_datetime(series, errors="coerce")
    return dates.dt.to_period("W-SUN").dt.start_time.dt.strftime("%Y-%m-%d")

def fmt_week(wk):
    try:
        return datetime.strptime(wk, "%Y-%m-%d").strftime("Week of %b %d")
    except Exception:
        return wk

COLORS = ["#3b82f6","#22c55e","#f59e0b","#a78bfa","#ef4444","#06b6d4","#f97316"]

def base_layout(height=260):
    return dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#94a3b8", size=11), height=height,
        margin=dict(t=30, b=20, l=0, r=10),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#1e293b")
    )

# ─── INTEGRITY ENGINE ─────────────────────────────────────────────────────────
def compute_integrity(name, c_df, s_df, team_c_df):
    r = dict(score="clean", perf_flags=[], integrity_flags=[], script_violations=[],
             doors=0, contacted=0, not_home_pct=0, surveys=0, days_active=0,
             avg_per_day=0, contact_rate=0, impossible_count=0, skip_rate=0, total_surveyed=0)

    if c_df.empty:
        return r

    doors     = len(c_df)
    contacted = len(c_df[c_df["ResultShortName"] == "Canvassed"]) if "ResultShortName" in c_df.columns else 0
    not_home  = len(c_df[c_df["ResultShortName"] == "Not Home"])  if "ResultShortName" in c_df.columns else 0
    not_home_pct = round(not_home / doors * 100, 1) if doors > 0 else 0
    contact_rate = round(contacted / doors * 100, 1) if doors > 0 else 0
    unique_surveys = s_df["Voter File VANID"].nunique() if not s_df.empty and "Voter File VANID" in s_df.columns else 0

    # Days active — parse properly to avoid counting same day twice
    if "DateCanvassed" in c_df.columns:
        parsed = parse_dates(c_df["DateCanvassed"]).dropna()
        days_active = int(parsed.nunique())
        avg_per_day = round(doors / days_active, 1) if days_active > 0 else 0
        daily = parsed.value_counts()
        if len(daily) > 1 and daily.mean() > 0:
            cv = daily.std() / daily.mean()
            if cv > 0.8:
                r["perf_flags"].append(("⚠️ Inconsistent Daily Output", "flag-yellow"))
    else:
        days_active = 0
        avg_per_day = 0

    # Team averages
    team_doors = len(team_c_df)
    n_canv = team_c_df["CanvassedBy"].nunique() if "CanvassedBy" in team_c_df.columns else 1
    avg_team_doors = team_doors / n_canv if n_canv > 0 else 0
    team_contacted = len(team_c_df[team_c_df["ResultShortName"] == "Canvassed"]) if "ResultShortName" in team_c_df.columns else 0
    team_rate = round(team_contacted / team_doors * 100, 1) if team_doors > 0 else 0

    if doors > avg_team_doors * 1.2:
        r["perf_flags"].append(("🟢 Top Performer", "flag-green"))
    if not_home_pct > 70:
        r["perf_flags"].append(("🔴 Low Contact Rate", "flag-red"))
    if unique_surveys == 0 and doors > 3:
        r["perf_flags"].append(("🔴 No Surveys", "flag-red"))

    r.update(dict(doors=doors, contacted=contacted, not_home_pct=not_home_pct,
                  contact_rate=contact_rate, surveys=unique_surveys,
                  days_active=days_active, avg_per_day=avg_per_day))

    if s_df.empty or "SurveyQuestionLongName" not in s_df.columns:
        return r

    # Script path validation
    try:
        pivoted = s_df.pivot_table(
            index="Voter File VANID",
            columns="SurveyQuestionLongName",
            values="SurveyResponseName",
            aggfunc="first"
        )
    except Exception:
        return r

    total = len(pivoted)
    imp_count = 0

    for vanid, row in pivoted.iterrows():
        resident_resp = {q: v for q, v in row.items() if pd.notna(v)}
        viols = validate_resident_path(resident_resp)
        if viols:
            has_imp = any("IMPOSSIBLE PATH" in v for v in viols)
            if has_imp:
                imp_count += 1
            r["script_violations"].append({"vanid": vanid, "violations": viols, "impossible": has_imp})

    skip_rate = round(len(r["script_violations"]) / total * 100, 1) if total > 0 else 0
    r["impossible_count"] = imp_count
    r["skip_rate"] = skip_rate
    r["total_surveyed"] = total

    # Integrity flags
    if imp_count > 0:
        r["integrity_flags"].append(("🚩 " + str(imp_count) + " impossible script path" + ("s" if imp_count > 1 else ""), "flag-red"))

    for q in s_df["SurveyQuestionLongName"].unique():
        vals = s_df[s_df["SurveyQuestionLongName"] == q]["SurveyResponseName"]
        if len(vals) >= 5:
            top_pct = vals.value_counts().iloc[0] / len(vals)
            if top_pct >= 0.92:
                top_r = vals.value_counts().index[0]
                r["integrity_flags"].append(("⚠️ Uniform on '" + q + "': " + str(round(top_pct*100)) + "% → '" + top_r + "'", "flag-yellow"))

    if abs(contact_rate - team_rate) > 25:
        direction = "above" if contact_rate > team_rate else "below"
        r["integrity_flags"].append(("⚠️ Contact rate " + str(contact_rate) + "% vs team " + str(team_rate) + "% (" + direction + ")", "flag-yellow"))

    if doors >= 5 and unique_surveys / doors > 0.85:
        r["integrity_flags"].append(("⚠️ Survey/door ratio " + str(round(unique_surveys/doors*100)) + "% — unusually high", "flag-yellow"))

    if "DateCanvassed" in s_df.columns:
        by_day = s_df.groupby(parse_dates(s_df["DateCanvassed"])).size()
        if len(by_day) > 0 and by_day.sum() >= 5:
            max_pct = by_day.max() / by_day.sum()
            if max_pct >= 0.85:
                max_d = by_day.idxmax()
                day_str = max_d.strftime("%b %d") if hasattr(max_d, "strftime") else str(max_d)
                r["integrity_flags"].append(("⚠️ " + str(round(max_pct*100)) + "% of surveys on single date (" + day_str + ")", "flag-yellow"))

    if imp_count > 0 or len(r["integrity_flags"]) >= 2:
        r["score"] = "flagged"
    elif len(r["integrity_flags"]) >= 1 or skip_rate > 15:
        r["score"] = "watch"

    return r

# ─── SESSION STATE ────────────────────────────────────────────────────────────
for k, v in [("contact_history", pd.DataFrame()), ("survey_history", pd.DataFrame())]:
    if k not in st.session_state:
        st.session_state[k] = v

# ─── HEADER ───────────────────────────────────────────────────────────────────
st.markdown('<div class="dash-title">Team Dashboard</div>', unsafe_allow_html=True)
st.markdown('<div class="dash-sub">Field Operations · NJ</div>', unsafe_allow_html=True)
st.divider()

# ─── UPLOAD ───────────────────────────────────────────────────────────────────
with st.expander("📂 Upload This Week's VAN Exports", expanded=st.session_state.contact_history.empty):
    st.caption("Upload both files each week — duplicates are automatically skipped.")
    uc1, uc2 = st.columns(2)
    with uc1:
        st.markdown("**Contact History**")
        st.markdown('<div class="upload-hint">File with ResultShortName / CanvassedBy</div>', unsafe_allow_html=True)
        contact_file = st.file_uploader("Contact history", type=["xls","csv","tsv","txt"], key="cu", label_visibility="collapsed")
    with uc2:
        st.markdown("**Survey Responses**")
        st.markdown('<div class="upload-hint">File with SurveyQuestionLongName / SurveyResponseName</div>', unsafe_allow_html=True)
        survey_file = st.file_uploader("Survey export", type=["xls","csv","tsv","txt"], key="su", label_visibility="collapsed")

    if st.button("Add to Dashboard", type="primary", disabled=(contact_file is None and survey_file is None)):
        added_c = added_s = 0
        if contact_file:
            df = load_van_file(contact_file)
            if df is not None:
                if "IsCanvasser" in df.columns:
                    df = df[df["IsCanvasser"].str.upper().str.strip() == "TRUE"]
                if not st.session_state.contact_history.empty:
                    key_cols = [c for c in ["Voter File VANID","DateCanvassed","ResultShortName"] if c in df.columns]
                    if key_cols:
                        existing = set(st.session_state.contact_history[key_cols].apply(tuple, axis=1))
                        df = df[~df[key_cols].apply(tuple, axis=1).isin(existing)]
                st.session_state.contact_history = pd.concat([st.session_state.contact_history, df], ignore_index=True)
                added_c = len(df)
        if survey_file:
            df = load_van_file(survey_file)
            if df is not None:
                if "IsCanvasser" in df.columns:
                    df = df[df["IsCanvasser"].str.upper().str.strip() == "TRUE"]
                if not st.session_state.survey_history.empty:
                    key_cols = [c for c in ["Voter File VANID","SurveyQuestionLongName","DateCanvassed"] if c in df.columns]
                    if key_cols:
                        existing = set(st.session_state.survey_history[key_cols].apply(tuple, axis=1))
                        df = df[~df[key_cols].apply(tuple, axis=1).isin(existing)]
                st.session_state.survey_history = pd.concat([st.session_state.survey_history, df], ignore_index=True)
                added_s = len(df)
        st.success("Added " + str(added_c) + " contact records + " + str(added_s) + " survey responses")
        st.rerun()

    if not st.session_state.contact_history.empty:
        if st.button("Clear All Data"):
            st.session_state.contact_history = pd.DataFrame()
            st.session_state.survey_history  = pd.DataFrame()
            st.rerun()

# ─── GUARD ────────────────────────────────────────────────────────────────────
if st.session_state.contact_history.empty:
    st.info("Upload your VAN exports above to get started.")
    st.stop()

req_cols = ["ResultShortName","CanvassedBy","DateCanvassed","Voter File VANID"]
# Show available columns for debugging
available = st.session_state.contact_history.columns.tolist()
missing_cols = [c for c in req_cols if c not in available]
if missing_cols:
    st.error("Contact history file is missing columns: " + ", ".join(missing_cols))
    st.info("Columns found in your file: " + ", ".join(available))
    st.caption("If you see the column name above but slightly different (extra space, symbol), the file may have encoding issues. Try re-exporting from VAN.")
    st.stop()

# ─── PREP DATA ────────────────────────────────────────────────────────────────
contact_df = st.session_state.contact_history.copy()
survey_df  = st.session_state.survey_history.copy()

contact_df["WeekKey"] = get_week_key(contact_df["DateCanvassed"])
if not survey_df.empty:
    date_col = "DateCanvassed" if "DateCanvassed" in survey_df.columns else "DateCreated"
    if date_col in survey_df.columns:
        survey_df["WeekKey"] = get_week_key(survey_df[date_col])

all_weeks = sorted(contact_df["WeekKey"].dropna().unique(), reverse=True)

if len(all_weeks) > 1:
    selected_week = st.selectbox("Viewing week:", options=all_weeks, format_func=fmt_week)
else:
    selected_week = all_weeks[0] if all_weeks else None
    if selected_week:
        st.caption("Showing: " + fmt_week(selected_week))

if not selected_week:
    st.warning("No date information found in uploaded files.")
    st.stop()

wk_contacts = contact_df[contact_df["WeekKey"] == selected_week].copy()
wk_surveys  = survey_df[survey_df["WeekKey"] == selected_week].copy() if "WeekKey" in survey_df.columns else survey_df.copy()

sorted_weeks  = sorted(all_weeks)
prev_weeks    = [w for w in sorted_weeks if w < selected_week]
prev_week     = prev_weeks[-1] if prev_weeks else None
prev_contacts = contact_df[contact_df["WeekKey"] == prev_week] if prev_week else pd.DataFrame()

# ─── CAMPAIGN TOTALS ──────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Campaign Overview</div>', unsafe_allow_html=True)

total_doors      = len(wk_contacts)
total_contacted  = len(wk_contacts[wk_contacts["ResultShortName"] == "Canvassed"])
total_surveys    = wk_surveys["Voter File VANID"].nunique() if not wk_surveys.empty and "Voter File VANID" in wk_surveys.columns else 0
total_canvassers = wk_contacts["CanvassedBy"].nunique()
contact_rate_all = round(total_contacted / total_doors * 100, 1) if total_doors > 0 else 0
prev_doors_n     = len(prev_contacts)
wow_doors        = total_doors - prev_doors_n if prev_week else None

m1, m2, m3, m4 = st.columns(4)
with m1:
    delta_str = ("+" + str(wow_doors) if wow_doors > 0 else str(wow_doors)) if wow_doors is not None else None
    st.metric("Total Doors", str(total_doors), delta=delta_str)
with m2:
    st.metric("Contacted", str(total_contacted), delta=str(contact_rate_all) + "% contact rate")
with m3:
    st.metric("Surveys Completed", str(total_surveys))
with m4:
    st.metric("Active Canvassers", str(total_canvassers))

# ─── BUILD CANVASSER DATA ─────────────────────────────────────────────────────
canvasser_names = sorted(wk_contacts["CanvassedBy"].dropna().unique())
all_results = {}
for name in canvasser_names:
    c = wk_contacts[wk_contacts["CanvassedBy"] == name]
    s = wk_surveys[wk_surveys["CanvassedBy"] == name] if not wk_surveys.empty and "CanvassedBy" in wk_surveys.columns else pd.DataFrame()
    all_results[name] = compute_integrity(name, c, s, wk_contacts)

# ─── IMPOSSIBLE PATH ALERT STRIP ─────────────────────────────────────────────
flagged_names = [n for n in canvasser_names if all_results[n]["impossible_count"] > 0]
if flagged_names:
    st.markdown('<div class="section-header">🚩 Impossible Script Paths Detected</div>', unsafe_allow_html=True)
    st.caption("These canvassers have residents whose survey responses follow paths that are impossible per the script logic.")
    for name in flagged_names:
        r = all_results[name]
        imp_viols = [v for v in r["script_violations"] if v["impossible"]]
        with st.expander("🚩 " + name + " — " + str(r["impossible_count"]) + " impossible path" + ("s" if r["impossible_count"] > 1 else "")):
            for v in imp_viols:
                for viol in v["violations"]:
                    if "IMPOSSIBLE PATH" in viol:
                        st.markdown('<div class="impossible-box">VANID ' + str(v["vanid"]) + ': ' + viol + '</div>', unsafe_allow_html=True)

# ─── SORT & FILTER ────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Canvasser Cards</div>', unsafe_allow_html=True)

ctrl1, ctrl2, ctrl3 = st.columns([1,1,2])
with ctrl1:
    sort_by = st.selectbox("Sort by", ["Doors","Contacted","Surveys","Integrity","Avg Doors/Day"])
with ctrl2:
    filter_by = st.selectbox("Filter", ["All","Flagged / Watch","Clean only"])
with ctrl3:
    search = st.text_input("Search", placeholder="Canvasser name...")

score_order = {"flagged":0,"watch":1,"clean":2}

def sort_key(n):
    r = all_results[n]
    if sort_by == "Doors":          return -r["doors"]
    if sort_by == "Contacted":      return -r["contacted"]
    if sort_by == "Surveys":        return -r["surveys"]
    if sort_by == "Integrity":      return score_order.get(r["score"], 2)
    if sort_by == "Avg Doors/Day":  return -r["avg_per_day"]
    return 0

display_names = sorted(canvasser_names, key=sort_key)
if filter_by == "Flagged / Watch":
    display_names = [n for n in display_names if all_results[n]["score"] in ("flagged","watch")]
elif filter_by == "Clean only":
    display_names = [n for n in display_names if all_results[n]["score"] == "clean"]
if search:
    display_names = [n for n in display_names if search.lower() in n.lower()]

st.caption("Showing " + str(len(display_names)) + " of " + str(len(all_results)) + " canvassers")

# ─── CANVASSER CARDS ──────────────────────────────────────────────────────────
int_labels = {
    "clean":   ("● Data looks clean",  "integrity-clean"),
    "watch":   ("● Worth monitoring",  "integrity-watch"),
    "flagged": ("● Integrity concern", "integrity-flagged"),
}

for name in display_names:
    r = all_results[name]

    if prev_week and not prev_contacts.empty:
        prev_n    = len(prev_contacts[prev_contacts["CanvassedBy"] == name])
        wow       = r["doors"] - prev_n
        wow_str   = ("▲ " if wow > 0 else "▼ " if wow < 0 else "— ") + str(abs(wow)) + " vs last week"
        wow_color = "#22c55e" if wow > 0 else "#ef4444" if wow < 0 else "#64748b"
    else:
        wow_str = wow_color = None

    int_label, int_class = int_labels[r["score"]]

    with st.container():
        n_col, w_col = st.columns([4,1])
        with n_col:
            st.markdown('<div class="canvasser-name">' + name + '</div>', unsafe_allow_html=True)
            st.markdown('<span class="' + int_class + '">' + int_label + '</span>', unsafe_allow_html=True)
            flags_html = "".join(
                '<span class="flag-tag ' + fc + '">' + ft + '</span>'
                for ft, fc in (r["perf_flags"] + r["integrity_flags"][:2])
            )
            if flags_html:
                st.markdown(flags_html, unsafe_allow_html=True)
        with w_col:
            if wow_str:
                st.markdown(
                    '<div style="text-align:right;font-size:0.85rem;color:' + wow_color + ';font-weight:600;padding-top:8px;">' + wow_str + '</div>',
                    unsafe_allow_html=True
                )

        mc1,mc2,mc3,mc4,mc5,mc6 = st.columns(6)
        mc1.metric("Doors",          r["doors"])
        mc2.metric("Contacted",      r["contacted"])
        mc3.metric("Surveys",        r["surveys"])
        mc4.metric("Not Home %",     str(r["not_home_pct"]) + "%")
        mc5.metric("Avg Doors/Day",  r["avg_per_day"])
        mc6.metric("Days Active",    r["days_active"])

        with st.expander("🔍 Deep dive — " + name.split(",")[0].strip()):
            c_df = wk_contacts[wk_contacts["CanvassedBy"] == name]
            s_df = wk_surveys[wk_surveys["CanvassedBy"] == name] if not wk_surveys.empty and "CanvassedBy" in wk_surveys.columns else pd.DataFrame()

            ch1, ch2 = st.columns(2)
            with ch1:
                if "ResultShortName" in c_df.columns:
                    rc = c_df["ResultShortName"].value_counts().reset_index()
                    rc.columns = ["Result","Count"]
                    cmap = {"Canvassed":"#22c55e","Not Home":"#6b7fa3","Refused":"#f59e0b",
                            "Inaccessible":"#a78bfa","Hostile":"#ef4444","Other Language":"#06b6d4"}
                    fig = go.Figure(go.Bar(
                        x=rc["Result"], y=rc["Count"],
                        marker_color=[cmap.get(x,"#64748b") for x in rc["Result"]],
                        text=rc["Count"], textposition="outside"
                    ))
                    fig.update_layout(title="Contact Results", showlegend=False, **base_layout())
                    st.plotly_chart(fig, use_container_width=True)

            with ch2:
                if "DateCanvassed" in c_df.columns:
                    c2 = c_df.copy()
                    c2["_d"] = parse_dates(c2["DateCanvassed"])
                    daily = c2.groupby("_d").size().reset_index()
                    daily.columns = ["Date","Doors"]
                    daily["Date"] = daily["Date"].dt.strftime("%b %d")
                    fig2 = go.Figure(go.Scatter(
                        x=daily["Date"], y=daily["Doors"],
                        mode="lines+markers+text",
                        line=dict(color="#3b82f6", width=2),
                        marker=dict(size=7),
                        text=daily["Doors"], textposition="top center",
                        textfont=dict(size=10)
                    ))
                    fig2.update_layout(title="Doors Per Day", **base_layout())
                    st.plotly_chart(fig2, use_container_width=True)

            # Survey response table — one question at a time, clean progress column
            if not s_df.empty and "SurveyQuestionLongName" in s_df.columns:
                st.markdown("**Survey Responses**")
                for q in s_df["SurveyQuestionLongName"].dropna().unique():
                    q_data = s_df[s_df["SurveyQuestionLongName"] == q]["SurveyResponseName"].value_counts()
                    total_q = q_data.sum()
                    st.markdown(
                        '<div style="font-size:0.72rem;color:#64748b;font-weight:600;text-transform:uppercase;'
                        'letter-spacing:1px;margin:12px 0 6px 0;">' + q + '</div>',
                        unsafe_allow_html=True
                    )
                    rows = [{"Response": resp, "Count": int(cnt), "%": round(cnt/total_q*100)}
                            for resp, cnt in q_data.items()]
                    st.dataframe(
                        pd.DataFrame(rows),
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "%": st.column_config.ProgressColumn("%", min_value=0, max_value=100, format="%d%%")
                        }
                    )

            # Script violations
            viols = r.get("script_violations", [])
            if viols:
                imp   = [v for v in viols if v["impossible"]]
                other = [v for v in viols if not v["impossible"]]
                if imp:
                    st.error("🚩 " + str(len(imp)) + " impossible script path" + ("s" if len(imp) > 1 else ""))
                    for v in imp[:5]:
                        for viol in v["violations"]:
                            if "IMPOSSIBLE PATH" in viol:
                                st.markdown('<div class="impossible-box">VANID ' + str(v["vanid"]) + ': ' + viol + '</div>', unsafe_allow_html=True)
                    if len(imp) > 5:
                        st.caption("... and " + str(len(imp)-5) + " more")
                if other:
                    with st.expander("⚠️ " + str(len(other)) + " incomplete/skipped surveys"):
                        for v in other[:10]:
                            st.caption("VANID " + str(v["vanid"]) + ": " + " | ".join(v["violations"]))
                        if len(other) > 10:
                            st.caption("... and " + str(len(other)-10) + " more")
            elif not s_df.empty:
                st.success("✅ All surveyed residents followed correct script paths")

            st.caption("→ For timestamps, idle periods & street analysis open Agent Monitor with " + name.split(",")[0].strip() + "'s individual file.")

        st.divider()

# ─── SURVEY ANALYTICS ─────────────────────────────────────────────────────────
st.markdown('<div class="section-header">📊 Data Analytics — Survey Response Trends</div>', unsafe_allow_html=True)

if survey_df.empty or "SurveyQuestionLongName" not in survey_df.columns:
    st.info("Upload a survey file to see response analytics.")
    st.stop()

questions_all = sorted(survey_df["SurveyQuestionLongName"].dropna().unique())
selected_q    = st.selectbox("Select survey question", questions_all)

if selected_q:
    qa1, qa2 = st.columns([1, 1.6])

    with qa1:
        st.markdown("**Overall distribution — all weeks**")
        dist = survey_df[survey_df["SurveyQuestionLongName"] == selected_q]["SurveyResponseName"].value_counts().reset_index()
        dist.columns = ["Response","Count"]
        dist["Pct"] = (dist["Count"] / dist["Count"].sum() * 100).round(1)
        fig = go.Figure(go.Bar(
            y=dist["Response"], x=dist["Count"], orientation="h",
            marker_color=COLORS[:len(dist)],
            text=[str(p)+"%" for p in dist["Pct"]], textposition="outside"
        ))
        layout = base_layout(max(200, len(dist)*45))
        layout["margin"] = dict(t=10, b=10, l=0, r=60)
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True)

    with qa2:
        if len(all_weeks) > 1:
            st.markdown("**Week-over-week trend**")
            trend_rows = []
            for wk in sorted(all_weeks):
                if "WeekKey" in survey_df.columns:
                    wk_q = survey_df[(survey_df["WeekKey"] == wk) & (survey_df["SurveyQuestionLongName"] == selected_q)]
                    for resp, cnt in wk_q["SurveyResponseName"].value_counts().items():
                        trend_rows.append({"Week": fmt_week(wk), "Response": resp, "Count": cnt})
            if trend_rows:
                tdf = pd.DataFrame(trend_rows)
                fig2 = px.bar(tdf, x="Week", y="Count", color="Response",
                              color_discrete_sequence=COLORS, barmode="stack")
                fig2.update_layout(**base_layout(300))
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Upload multiple weeks of data to see trends over time.")

    st.markdown("**Canvasser response comparison — _" + selected_q + "_**")
    st.caption("Canvassers with very different distributions vs the team are worth investigating.")
    if "CanvassedBy" in wk_surveys.columns and not wk_surveys.empty:
        comp = wk_surveys[wk_surveys["SurveyQuestionLongName"] == selected_q]
        if not comp.empty:
            pivot = comp.pivot_table(index="CanvassedBy", columns="SurveyResponseName",
                                     values="Voter File VANID", aggfunc="count", fill_value=0).reset_index()
            pivot.columns.name = None
            resp_cols = [c for c in pivot.columns if c != "CanvassedBy"]
            fig3 = go.Figure()
            for i, resp in enumerate(resp_cols):
                fig3.add_trace(go.Bar(name=resp, x=pivot["CanvassedBy"], y=pivot[resp],
                                      marker_color=COLORS[i % len(COLORS)]))
            layout3 = base_layout(320)
            layout3["margin"] = dict(t=10, b=80, l=0, r=0)
            layout3["barmode"] = "stack"
            layout3["xaxis"] = dict(showgrid=False, tickangle=-30)
            layout3["legend"] = dict(font=dict(size=10))
            fig3.update_layout(**layout3)
            st.plotly_chart(fig3, use_container_width=True) 
