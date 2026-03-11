import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import numpy as np
import re
import io

st.set_page_config(page_title="Agent Monitor", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    .page-title { font-family:'Syne',sans-serif; font-size:2rem; font-weight:800; letter-spacing:-0.5px; }
    .page-sub   { font-size:0.8rem; color:#94a3b8; letter-spacing:2px; text-transform:uppercase; margin-bottom:1.5rem; }
    .section-header { font-family:'Syne',sans-serif; font-size:1.2rem; font-weight:700; margin:1.5rem 0 0.75rem 0; padding-bottom:0.4rem; border-bottom:1px solid #1e2d4a; }
    .warning-box { background:#fef3c720; border-left:4px solid #f59e0b; padding:0.75rem; border-radius:4px; margin:0.5rem 0; color:#f59e0b; font-size:0.85rem; }
    .impossible-box { background:#ef444412; border:1px solid #ef444440; border-radius:8px; padding:10px 14px; font-size:0.75rem; color:#ef4444; margin:4px 0; }
    .info-box { background:#3b82f615; border-left:4px solid #3b82f6; padding:0.75rem; border-radius:4px; margin:0.5rem 0; color:#94a3b8; font-size:0.85rem; }
    div[data-testid="stMetricValue"] { font-family:'Syne',sans-serif !important; }
</style>
""", unsafe_allow_html=True)

# ─── SCRIPT BRANCHING RULES (same as team dashboard) ─────────────────────────
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
def load_any_file(uploaded_file):
    raw = uploaded_file.read()
    for enc in ["utf-16", "utf-8-sig", "utf-8", "latin-1"]:
        try:
            text = raw.decode(enc)
            if text.startswith("\ufeff"):
                text = text[1:]
            df = pd.read_csv(io.StringIO(text), sep="\t", dtype=str)
            df.columns = df.columns.str.strip()
            if len(df.columns) > 1:
                return df
        except Exception:
            continue
    for enc in ["utf-8-sig", "utf-8", "latin-1"]:
        try:
            text = raw.decode(enc)
            df = pd.read_csv(io.StringIO(text), dtype=str)
            df.columns = df.columns.str.strip()
            if len(df.columns) > 1:
                return df
        except Exception:
            continue
    return None

def extract_street(address):
    if pd.isna(address):
        return "Unknown"
    addr = re.sub(r'(Apt|Unit|#|Suite).*', '', str(address), flags=re.IGNORECASE).strip()
    return addr.split(",")[0].strip()

def parse_dates(series):
    return pd.to_datetime(series, errors="coerce")

COLORS = ["#3b82f6","#22c55e","#f59e0b","#a78bfa","#ef4444","#06b6d4","#f97316"]

def base_layout(height=260):
    return dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#94a3b8", size=11), height=height,
        margin=dict(t=30, b=20, l=0, r=10),
        xaxis=dict(showgrid=False),
        yaxis=dict(showgrid=True, gridcolor="#1e293b")
    )

# ─── HEADER ───────────────────────────────────────────────────────────────────
st.markdown('<div class="page-title">🎯 Agent Monitor</div>', unsafe_allow_html=True)
st.markdown('<div class="page-sub">Individual Canvasser Deep Dive · Field Operations NJ</div>', unsafe_allow_html=True)
st.divider()

# ─── UPLOAD ───────────────────────────────────────────────────────────────────
st.markdown("Upload the individual agent file from VAN. If the agent covered multiple turfs, upload both.")
st.caption("Accepts .xls, .csv, .tsv, .txt — including UTF-16 VAN exports")

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("**Step 1: Survey File**")
    st.caption("File with SurveyQuestionLongName — used to identify the agent")
    survey_file = st.file_uploader("Survey file", type=["xls","csv","tsv","txt"], key="sf", label_visibility="collapsed")
with col2:
    st.markdown("**Step 2: Individual File (Turf 1)**")
    st.caption("File with Date Canvassed, Address, Contact Result")
    ind_file_1 = st.file_uploader("First turf", type=["xls","csv","tsv","txt"], key="if1", label_visibility="collapsed")
with col3:
    st.markdown("**Step 3: Individual File (Turf 2 — optional)**")
    st.caption("Upload if agent changed turfs during the shift")
    ind_file_2 = st.file_uploader("Second turf", type=["xls","csv","tsv","txt"], key="if2", label_visibility="collapsed")

st.divider()

if not ind_file_1 and not ind_file_2:
    st.info("Upload the agent's individual VAN file above to begin analysis.")
    st.stop()

# ─── LOAD SURVEY FILE ─────────────────────────────────────────────────────────
survey_df = None
if survey_file:
    survey_df = load_any_file(survey_file)
    if survey_df is not None:
        # Normalize column names
        col_map = {}
        for col in survey_df.columns:
            cl = col.lower().replace(" ","").replace("_","")
            if "vanid" in cl and "ID" not in col_map:
                col_map["ID"] = col
            if "canvassedby" in cl:
                col_map["CanvassedBy"] = col
            if "questionlong" in cl or col == "SurveyQuestionLongName":
                col_map["Question"] = col
            if "responsename" in cl or col == "SurveyResponseName":
                col_map["Response"] = col
        if "ID" in col_map and "CanvassedBy" in col_map:
            survey_df = survey_df.rename(columns={v: k for k, v in col_map.items()})
            if "IsCanvasser" in survey_df.columns:
                survey_df = survey_df[survey_df["IsCanvasser"].str.upper().str.strip() == "TRUE"]
            survey_df["CanvassedBy"] = survey_df["CanvassedBy"].str.strip()

# ─── LOAD INDIVIDUAL FILE(S) ──────────────────────────────────────────────────
dfs = []
for f, label in [(ind_file_1,"Turf 1"), (ind_file_2,"Turf 2")]:
    if f:
        df = load_any_file(f)
        if df is not None:
            st.success("✅ " + label + ": " + str(len(df)) + " records loaded")
            dfs.append(df)
        else:
            st.error("Could not parse " + label + " — check file format")

if not dfs:
    st.error("Could not load any individual files.")
    st.stop()

df_ind = pd.concat(dfs, ignore_index=True)
if len(dfs) > 1:
    st.info("Combined: " + str(len(df_ind)) + " records across both turfs")

# Normalize column names for individual file
# Handle "Date Canvassed" vs "DateCanvassed"
for old, new in [("Date Canvassed","DateCanvassed"),("Contact Result","ContactResult"),
                  ("VanID","VANID"),("Van ID","VANID")]:
    if old in df_ind.columns:
        df_ind = df_ind.rename(columns={old: new})

if "DateCanvassed" not in df_ind.columns:
    # Try to find any date-like column
    date_cols = [c for c in df_ind.columns if "date" in c.lower() or "canvass" in c.lower()]
    if date_cols:
        df_ind = df_ind.rename(columns={date_cols[0]: "DateCanvassed"})

if "ContactResult" not in df_ind.columns:
    result_cols = [c for c in df_ind.columns if "result" in c.lower() or "contact" in c.lower()]
    if result_cols:
        df_ind = df_ind.rename(columns={result_cols[0]: "ContactResult"})

# Parse dates
if "DateCanvassed" in df_ind.columns:
    df_ind["DateCanvassed"] = parse_dates(df_ind["DateCanvassed"])
    if df_ind["DateCanvassed"].dt.tz is not None:
        df_ind["DateCanvassed"] = df_ind["DateCanvassed"].dt.tz_localize(None)
    df_ind = df_ind.sort_values("DateCanvassed")

# ─── IDENTIFY AGENT ───────────────────────────────────────────────────────────
agent_name = "Unknown Agent"
matching_surveys = pd.DataFrame()

if survey_df is not None and "CanvassedBy" in survey_df.columns:
    # Find VANIDs from individual file
    id_col = next((c for c in ["VANID","Voter File VANID","VoterVANID"] if c in df_ind.columns), None)
    if id_col:
        ind_ids = df_ind[id_col].dropna().unique()
        id_survey_col = next((c for c in ["ID","Voter File VANID","VANID"] if c in survey_df.columns), None)
        if id_survey_col:
            matching_surveys = survey_df[survey_df[id_survey_col].isin(ind_ids)]
            if len(matching_surveys) > 0:
                agent_name = matching_surveys["CanvassedBy"].mode()[0]

st.markdown('<div class="section-header">Agent: ' + agent_name + '</div>', unsafe_allow_html=True)

# ─── PERFORMANCE SNAPSHOT ─────────────────────────────────────────────────────
st.markdown('<div class="section-header">📊 Performance Snapshot</div>', unsafe_allow_html=True)

total_attempts = len(df_ind)

if "ContactResult" in df_ind.columns:
    non_contact_words = ["not home","refused","moved","inaccessible","hostile","other language"]
    contacted_mask = ~df_ind["ContactResult"].str.lower().str.contains("|".join(non_contact_words), na=False)
    contacted_n = contacted_mask.sum()
    not_home_n  = df_ind["ContactResult"].str.lower().str.contains("not home", na=False).sum()
    refused_n   = df_ind["ContactResult"].str.lower().str.contains("refused", na=False).sum()
    contact_rate = round(contacted_n / total_attempts * 100, 1) if total_attempts > 0 else 0
else:
    contacted_n = not_home_n = refused_n = 0
    contact_rate = 0

id_col = next((c for c in ["VANID","Voter File VANID","VoterVANID"] if c in df_ind.columns), None)
doors = df_ind[id_col].nunique() if id_col else total_attempts

p1,p2,p3,p4 = st.columns(4)
p1.metric("Doors Knocked",  doors)
p2.metric("Contacted",      contacted_n)
p3.metric("Contact Rate",   str(contact_rate) + "%")
p4.metric("Total Attempts", total_attempts)

if "ContactResult" in df_ind.columns:
    result_counts = df_ind["ContactResult"].value_counts()
    non_contacts = [(r, c) for r, c in result_counts.items()
                    if any(w in str(r).lower() for w in non_contact_words)]
    if non_contacts:
        st.markdown("**Non-Contact Breakdown**")
        nc_cols = st.columns(min(len(non_contacts), 4))
        for idx, (res, cnt) in enumerate(non_contacts):
            nc_cols[idx % 4].metric(res, cnt)

# ─── CONTACT RESULTS CHART ────────────────────────────────────────────────────
if "ContactResult" in df_ind.columns:
    rc = df_ind["ContactResult"].value_counts().reset_index()
    rc.columns = ["Result","Count"]
    cmap = {"Canvassed":"#22c55e","Not Home":"#6b7fa3","Refused":"#f59e0b",
            "Inaccessible":"#a78bfa","Hostile":"#ef4444","Other Language":"#06b6d4"}
    fig = go.Figure(go.Bar(
        x=rc["Result"], y=rc["Count"],
        marker_color=[cmap.get(x,"#64748b") for x in rc["Result"]],
        text=rc["Count"], textposition="outside"
    ))
    fig.update_layout(title="Contact Results Breakdown", showlegend=False, **base_layout(250))
    st.plotly_chart(fig, use_container_width=True)

# ─── ACTIVITY TIMELINE ────────────────────────────────────────────────────────
if "DateCanvassed" in df_ind.columns:
    df_valid = df_ind[df_ind["DateCanvassed"].notna()].copy()

    if len(df_valid) > 0:
        st.markdown('<div class="section-header">⏱️ Activity Timeline</div>', unsafe_allow_html=True)

        first_knock = df_valid["DateCanvassed"].min()
        last_knock  = df_valid["DateCanvassed"].max()
        time_worked = last_knock - first_knock
        hours   = int(time_worked.total_seconds() / 3600)
        minutes = int((time_worked.total_seconds() % 3600) / 60)

        day_of_week  = first_knock.dayofweek
        shift_start_h = 12 if day_of_week == 5 else 13
        shift_start  = first_knock.replace(hour=shift_start_h, minute=0, second=0)
        shift_end    = first_knock.replace(hour=19, minute=0, second=0)

        st.markdown(
            '<div class="info-box">⏰ Time on turf: ' + str(hours) + 'h ' + str(minutes) + 'm  ('
            + first_knock.strftime("%I:%M %p") + ' – ' + last_knock.strftime("%I:%M %p") + ')</div>',
            unsafe_allow_html=True
        )

        # Doors per day chart
        df_valid["_date"] = df_valid["DateCanvassed"].dt.normalize()
        daily = df_valid.groupby("_date").size().reset_index()
        daily.columns = ["Date","Doors"]
        daily["DateStr"] = daily["Date"].dt.strftime("%b %d")

        fig_daily = go.Figure(go.Scatter(
            x=daily["DateStr"], y=daily["Doors"],
            mode="lines+markers+text",
            line=dict(color="#3b82f6", width=2),
            marker=dict(size=8),
            text=daily["Doors"], textposition="top center",
            textfont=dict(size=11)
        ))
        fig_daily.update_layout(title="Doors Per Day", **base_layout(220))
        st.plotly_chart(fig_daily, use_container_width=True)

        # Idle periods
        df_sorted = df_valid.sort_values("DateCanvassed")
        idle_periods = []
        for i in range(len(df_sorted) - 1):
            t1 = df_sorted.iloc[i]["DateCanvassed"]
            t2 = df_sorted.iloc[i+1]["DateCanvassed"]
            # Only flag gaps within the same day
            if t1.date() == t2.date():
                gap_min = (t2 - t1).total_seconds() / 60
                if gap_min > 15:
                    idle_periods.append({"start": t1, "end": t2, "minutes": int(gap_min)})

        total_shift_min  = (shift_end - shift_start).total_seconds() / 60
        active_min       = (last_knock - first_knock).total_seconds() / 60
        idle_total       = sum(p["minutes"] for p in idle_periods)
        working_min      = active_min - idle_total
        pct_active       = round(working_min / total_shift_min * 100) if total_shift_min > 0 else 0

        t1,t2,t3 = st.columns(3)
        t1.metric("Active Time",       str(int(working_min)) + "m")
        t2.metric("Idle Time",         str(idle_total) + "m")
        t3.metric("% of Shift Active", str(pct_active) + "%")

        if idle_periods:
            st.markdown("**🔴 Idle Periods (>15 min gaps)**")
            for p in idle_periods:
                st.markdown(
                    '<div class="warning-box">⚠️ ' + str(p["minutes"]) + ' min gap: '
                    + p["start"].strftime("%I:%M %p") + ' – ' + p["end"].strftime("%I:%M %p") + '</div>',
                    unsafe_allow_html=True
                )
        else:
            st.success("✅ No idle periods detected")

# ─── STREET LEVEL ANALYSIS ────────────────────────────────────────────────────
addr_col = next((c for c in ["Address","address","Street Address"] if c in df_ind.columns), None)
if addr_col and "DateCanvassed" in df_ind.columns:
    df_valid2 = df_ind[df_ind["DateCanvassed"].notna()].copy()
    df_valid2["Street"] = df_valid2[addr_col].apply(extract_street)

    st.markdown('<div class="section-header">🗺️ Street-Level Analysis</div>', unsafe_allow_html=True)

    street_stats = []
    for street in df_valid2["Street"].unique():
        s_data = df_valid2[df_valid2["Street"] == street].sort_values("DateCanvassed")
        if len(s_data) > 1:
            time_on = (s_data["DateCanvassed"].max() - s_data["DateCanvassed"].min()).total_seconds() / 60
            n_doors = len(s_data)
            avg_time = time_on / n_doors if n_doors > 0 else 0
            street_stats.append({"Street": street, "Doors": n_doors, "Avg Min/Door": round(avg_time,1)})

    if street_stats:
        street_df = pd.DataFrame(street_stats).sort_values("Avg Min/Door", ascending=False)
        flagged_streets = street_df[street_df["Avg Min/Door"] > 5]

        if not flagged_streets.empty:
            st.warning("⚠️ Extended time detected on the following streets (>5 min/door):")
            for _, row in flagged_streets.head(5).iterrows():
                st.markdown(
                    '<div class="warning-box">⚠️ ' + str(row["Street"]) + ': ' + str(row["Avg Min/Door"])
                    + ' min/door across ' + str(row["Doors"]) + ' doors</div>',
                    unsafe_allow_html=True
                )

        with st.expander("📋 Full Street Breakdown"):
            st.dataframe(street_df, use_container_width=True, hide_index=True)

# ─── SURVEY RESPONSES ─────────────────────────────────────────────────────────
if survey_df is not None and not matching_surveys.empty:
    st.markdown('<div class="section-header">📋 Survey Responses</div>', unsafe_allow_html=True)

    s1, s2 = st.columns([1,1])
    with s1:
        st.metric("Total Surveys Collected", len(matching_surveys[matching_surveys.get("Question") is not None] if "Question" in matching_surveys.columns else matching_surveys))

    if "Question" in matching_surveys.columns and "Response" in matching_surveys.columns:
        questions_list = matching_surveys["Question"].dropna().unique()
        for q in questions_list:
            q_data = matching_surveys[matching_surveys["Question"] == q]["Response"].value_counts()
            total_q = q_data.sum()
            st.markdown(
                '<div style="font-size:0.72rem;color:#64748b;font-weight:600;text-transform:uppercase;'
                'letter-spacing:1px;margin:12px 0 6px 0;">' + str(q) + '</div>',
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

    # ─── SCRIPT PATH VALIDATION ───────────────────────────────────────────────
    st.markdown('<div class="section-header">🔍 Script Path Validation</div>', unsafe_allow_html=True)

    id_survey_col = next((c for c in ["ID","Voter File VANID","VANID"] if c in matching_surveys.columns), None)

    if id_survey_col and "Question" in matching_surveys.columns and "Response" in matching_surveys.columns:
        # Check contacts missing surveys
        if "ContactResult" in df_ind.columns and id_col:
            contacted_ids = df_ind[~df_ind["ContactResult"].str.lower().str.contains(
                "not home|refused|moved|inaccessible", na=False
            )][id_col].unique()
            survey_ids = matching_surveys[id_survey_col].unique()
            has_survey = [i for i in contacted_ids if i in survey_ids]
            missing_surveys = len(contacted_ids) - len(has_survey)

            sv1, sv2 = st.columns(2)
            sv1.metric("Contacts with Surveys",  len(has_survey))
            sv2.metric("Contacts Missing Survey", missing_surveys)
            if missing_surveys > 0:
                st.warning("⚠️ " + str(missing_surveys) + " contacted residents are missing survey responses")
            else:
                st.success("✅ All contacted residents have survey responses")

        # Script branching validation
        try:
            pivoted = matching_surveys.pivot_table(
                index=id_survey_col,
                columns="Question",
                values="Response",
                aggfunc="first"
            )
            total_res = len(pivoted)
            violations_list = []
            imp_count = 0

            for vanid, row in pivoted.iterrows():
                resident_resp = {q: v for q, v in row.items() if pd.notna(v)}
                viols = validate_resident_path(resident_resp)
                if viols:
                    has_imp = any("IMPOSSIBLE PATH" in v for v in viols)
                    if has_imp:
                        imp_count += 1
                    violations_list.append({"vanid": vanid, "violations": viols, "impossible": has_imp})

            skip_rate = round(len(violations_list) / total_res * 100, 1) if total_res > 0 else 0

            sv3, sv4, sv5 = st.columns(3)
            sv3.metric("Total Residents Surveyed", total_res)
            sv4.metric("Impossible Paths",         imp_count)
            sv5.metric("Surveys with Issues",       str(skip_rate) + "%")

            imp_viols = [v for v in violations_list if v["impossible"]]
            other_viols = [v for v in violations_list if not v["impossible"]]

            if imp_viols:
                st.error("🚩 " + str(len(imp_viols)) + " resident(s) with IMPOSSIBLE response paths:")
                for v in imp_viols:
                    for viol in v["violations"]:
                        if "IMPOSSIBLE PATH" in viol:
                            st.markdown(
                                '<div class="impossible-box">VANID ' + str(v["vanid"]) + ': ' + viol + '</div>',
                                unsafe_allow_html=True
                            )
            else:
                st.success("✅ No impossible script paths detected")

            if other_viols:
                with st.expander("⚠️ " + str(len(other_viols)) + " surveys with skipped/missing questions"):
                    for v in other_viols[:15]:
                        st.caption("VANID " + str(v["vanid"]) + ": " + " | ".join(v["violations"]))
                    if len(other_viols) > 15:
                        st.caption("... and " + str(len(other_viols)-15) + " more")

        except Exception as e:
            st.warning("Could not run script validation: " + str(e))

elif ind_file_1 or ind_file_2:
    st.info("Upload the survey file (Step 1) to enable survey response analysis and script path validation.")
