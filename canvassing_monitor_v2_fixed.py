import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import numpy as np
import re

# Page config
st.set_page_config(
    page_title="Field Canvassing Monitor v2",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        text-align: center;
        margin-bottom: 1rem;
        padding: 1rem;
        background: linear-gradient(90deg, #3b82f6 0%, #2563eb 100%);
        color: white;
        border-radius: 10px;
    }
    .warning-box {
        background-color: #fef3c7;
        border-left: 4px solid #f59e0b;
        padding: 0.75rem;
        border-radius: 4px;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'topline_data' not in st.session_state:
    st.session_state.topline_data = None
if 'survey_data' not in st.session_state:
    st.session_state.survey_data = None

# Helper functions
def extract_street_name(address):
    """Extract street name from full address"""
    if pd.isna(address):
        return "Unknown"
    addr = re.sub(r'(Apt|Unit|#|Suite).*', '', str(address), flags=re.IGNORECASE).strip()
    parts = addr.split(',')[0].strip()
    return parts

def calculate_speed_mph(time1, time2, dist_estimate=0.1):
    """Calculate speed between two timestamps"""
    if pd.isna(time1) or pd.isna(time2):
        return 0
    hours = abs((time2 - time1).total_seconds() / 3600)
    if hours == 0:
        return 0
    return dist_estimate / hours

# Header
st.markdown('<div class="main-header">🎯 Field Canvassing Monitor v2</div>', unsafe_allow_html=True)

# Upload sections
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### 📊 Step 1: Topline Data")
    topline_file = st.file_uploader("Team summary CSV", type=['csv'], key='topline')

with col2:
    st.markdown("### 📋 Step 2: Survey Questions")
    survey_file = st.file_uploader("Survey Q&A CSV", type=['csv'], key='survey')

with col3:
    st.markdown("### 👤 Step 3: Individual Agent Data")
    st.markdown("Upload up to 2 files if agent changed turfs")
    individual_file_1 = st.file_uploader("First turf", type=['csv'], key='ind1')
    individual_file_2 = st.file_uploader("Second turf (optional)", type=['csv'], key='ind2')

st.markdown("---")

# STEP 1: Topline
if topline_file:
    try:
        try:
            topline_df = pd.read_csv(topline_file, encoding='utf-16', skiprows=1)
        except:
            topline_df = pd.read_csv(topline_file, encoding='utf-8-sig')
        
        topline_df.columns = topline_df.columns.str.replace('\ufeff', '').str.strip()
        
        canvassed_col = next((c for c in topline_df.columns if 'canvassed' in c.lower()), 'Canvassed')
        doors_col = next((c for c in topline_df.columns if 'doors' in c.lower()), 'Doors')
        canvasser_col = next((c for c in topline_df.columns if 'canvasser' in c.lower()), 'Canvasser')
        
        topline_df['Contact_Rate_Pct'] = (topline_df[canvassed_col] / topline_df[doors_col] * 100).round(1)
        
        st.session_state.topline_data = topline_df
        
        st.markdown("## 📊 Team Overview")
        
        cols = st.columns(3)
        with cols[0]:
            st.metric("Team Size", len(topline_df))
        with cols[1]:
            st.metric("Avg Doors", f"{topline_df[doors_col].mean():.0f}")
        with cols[2]:
            st.metric("Avg Contact Rate", f"{topline_df['Contact_Rate_Pct'].mean():.1f}%")
        
        with st.expander("📋 View Team Leaderboard"):
            leaderboard = topline_df[[canvasser_col, doors_col, canvassed_col, 'Contact_Rate_Pct']].sort_values(doors_col, ascending=False).copy()
            leaderboard.columns = ['Canvasser', 'Doors', 'Canvassed', 'Contact Rate %']
            st.dataframe(leaderboard, use_container_width=True, hide_index=True)
        
    except Exception as e:
        st.error(f"Error loading topline: {e}")

# STEP 2: Survey Questions
if survey_file:
    try:
        try:
            survey_df = pd.read_csv(survey_file, encoding='utf-8')
        except:
            survey_df = pd.read_csv(survey_file, encoding='utf-16', skiprows=1)
        
        survey_df.columns = survey_df.columns.str.replace('\ufeff', '').str.strip()
        
        col_mapping = {}
        for col in survey_df.columns:
            col_lower = col.lower()
            if 'vanid' in col_lower and 'ID' not in col_mapping:
                col_mapping['ID'] = col
            if 'canvassedby' in col_lower:
                col_mapping['CanvassedBy'] = col
            if 'questionlong' in col_lower or col == 'SurveyQuestionLongName':
                col_mapping['Question'] = col
            if 'responsename' in col_lower or col == 'SurveyResponseName':
                col_mapping['Response'] = col
        
        if 'ID' not in col_mapping or 'CanvassedBy' not in col_mapping:
            st.error(f"Missing required columns. Available: {list(survey_df.columns)}")
            st.stop()
        
        survey_df = survey_df[list(col_mapping.values())].copy()
        survey_df.columns = list(col_mapping.keys())
        survey_df['CanvassedBy'] = survey_df['CanvassedBy'].str.strip()
        
        st.session_state.survey_data = survey_df
        
        st.markdown("---")
        st.markdown("## 📋 Survey Response Analysis")
        
        st.metric("Active Canvassers", survey_df['CanvassedBy'].nunique())
        
        if 'Question' in survey_df.columns and 'Response' in survey_df.columns:
            st.markdown("### Survey Response Counts by Canvasser")
            
            survey_df['Q_R'] = survey_df['Question'].astype(str) + ' - ' + survey_df['Response'].astype(str)
            canvassers = sorted(survey_df['CanvassedBy'].unique())
            questions = sorted(survey_df['Q_R'].unique())
            
            table_data = []
            for canvasser in canvassers:
                row = {'Canvasser': canvasser}
                canv_data = survey_df[survey_df['CanvassedBy'] == canvasser]
                for qr in questions:
                    row[qr] = len(canv_data[canv_data['Q_R'] == qr])
                table_data.append(row)
            
            team_row = {'Canvasser': '📊 TEAM TOTAL'}
            for qr in questions:
                team_row[qr] = len(survey_df[survey_df['Q_R'] == qr])
            table_data.append(team_row)
            
            result_df = pd.DataFrame(table_data)
            st.dataframe(result_df, use_container_width=True, hide_index=True, height=400)
        
    except Exception as e:
        st.error(f"Error loading survey: {e}")

# STEP 3: Individual
if (individual_file_1 or individual_file_2) and st.session_state.topline_data is not None:
    
    st.markdown("---")
    st.markdown("## 👤 Individual Agent Analysis")
    
    def load_individual_file(file):
        for encoding in ['utf-8', 'utf-16', 'utf-8-sig']:
            for skiprows in [0, 1]:
                try:
                    file.seek(0)
                    df = pd.read_csv(file, encoding=encoding, skiprows=skiprows)
                    if len(df.columns) >= 5:
                        df.columns = df.columns.str.replace('\ufeff', '').str.strip()
                        return df
                except:
                    continue
        raise Exception("Could not read file")
    
    try:
        dfs = []
        if individual_file_1:
            df1 = load_individual_file(individual_file_1)
            dfs.append(df1)
            st.success(f"✅ First turf: {len(df1)} records")
        
        if individual_file_2:
            df2 = load_individual_file(individual_file_2)
            dfs.append(df2)
            st.success(f"✅ Second turf: {len(df2)} records")
        
        df_ind = pd.concat(dfs, ignore_index=True)
        st.info(f"📊 Combined: {len(df_ind)} records")
        
        df_ind['Date Canvassed'] = pd.to_datetime(df_ind['Date Canvassed'], errors='coerce')
        if df_ind['Date Canvassed'].dt.tz is not None:
            df_ind['Date Canvassed'] = df_ind['Date Canvassed'].dt.tz_localize(None)
        df_ind = df_ind.sort_values('Date Canvassed')
        
        id_col = 'VanID' if 'VanID' in df_ind.columns else 'ID'
        
        agent_name = "Unknown Agent"
        if st.session_state.survey_data is not None:
            ind_ids = df_ind[id_col].unique()
            matching = st.session_state.survey_data[st.session_state.survey_data['ID'].isin(ind_ids)]
            if len(matching) > 0:
                agent_name = matching['CanvassedBy'].mode()[0]
        
        st.markdown(f"### {agent_name}")
        
        agent_topline = st.session_state.topline_data[
            st.session_state.topline_data['Canvasser'].str.strip().str.lower() == agent_name.strip().lower()
        ]
        
        # If no exact match, try partial matching
        if len(agent_topline) == 0:
            # Try matching last name
            agent_last = agent_name.split()[-1] if ',' not in agent_name else agent_name.split(',')[0]
            agent_topline = st.session_state.topline_data[
                st.session_state.topline_data['Canvasser'].str.lower().str.contains(agent_last.lower(), na=False)
            ]
        
        if len(agent_topline) > 0:
            contact_rate = agent_topline['Contact_Rate_Pct'].iloc[0]
            doors = agent_topline['Doors'].iloc[0]
        else:
            # Fallback: calculate from individual data
            contacted = len(df_ind[~df_ind['Contact Result'].str.lower().str.contains('not home|refused|moved|inaccessible', na=False)])
            doors = df_ind[id_col].nunique()
            contact_rate = (contacted / doors * 100) if doors > 0 else 0
        
        st.markdown("### 📊 Performance Snapshot")
        
        cols = st.columns(3)
        with cols[0]:
            st.metric("Doors Knocked", int(doors))
        with cols[1]:
            st.metric("Contact Rate", f"{contact_rate:.1f}%")
        with cols[2]:
            st.metric("Total Attempts", len(df_ind))
        
        contact_results = df_ind['Contact Result'].value_counts()
        non_contact = []
        for result, count in contact_results.items():
            if any(w in str(result).lower() for w in ['not home', 'refused', 'moved', 'inaccessible']):
                non_contact.append((result, count))
        
        if non_contact:
            st.markdown("#### Non-Contact Breakdown")
            ncols = st.columns(min(len(non_contact), 4))
            for idx, (result_type, count) in enumerate(non_contact):
                with ncols[idx % 4]:
                    st.metric(result_type, count)
        
        st.markdown("### ⏱️ Activity Timeline")
        
        df_valid = df_ind[df_ind['Date Canvassed'].notna()].copy()
        
        if len(df_valid) > 0:
            first_knock = df_valid['Date Canvassed'].min()
            last_knock = df_valid['Date Canvassed'].max()
            
            day_of_week = first_knock.dayofweek
            shift_start_hour = 12 if day_of_week == 5 else 13
            
            shift_start = first_knock.replace(hour=shift_start_hour, minute=0, second=0)
            shift_end = first_knock.replace(hour=19, minute=0, second=0)
            
            time_worked = last_knock - first_knock
            hours = int(time_worked.total_seconds() / 3600)
            minutes = int((time_worked.total_seconds() % 3600) / 60)
            
            st.info(f"⏰ Time on turf: {hours}h {minutes}m ({first_knock.strftime('%I:%M%p')} - {last_knock.strftime('%I:%M%p')})")
            
            df_valid_sorted = df_valid.sort_values('Date Canvassed')
            
            idle_periods = []
            for i in range(len(df_valid_sorted) - 1):
                current_time = df_valid_sorted.iloc[i]['Date Canvassed']
                next_time = df_valid_sorted.iloc[i + 1]['Date Canvassed']
                gap_minutes = (next_time - current_time).total_seconds() / 60
                
                if gap_minutes > 15:
                    idle_periods.append({
                        'start': current_time,
                        'end': next_time,
                        'minutes': int(gap_minutes)
                    })
            
            if idle_periods:
                st.markdown("#### 🔴 Idle Periods Detected")
                for period in idle_periods:
                    st.markdown(
                        f'<div class="warning-box">⚠️ {period["minutes"]} minute gap: '
                        f'{period["start"].strftime("%I:%M%p")} - {period["end"].strftime("%I:%M%p")}</div>',
                        unsafe_allow_html=True
                    )
            
            total_shift_minutes = (shift_end - shift_start).total_seconds() / 60
            active_minutes = (last_knock - first_knock).total_seconds() / 60
            idle_total = sum([p['minutes'] for p in idle_periods])
            working_minutes = active_minutes - idle_total
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Active Time", f"{int(working_minutes)}m")
            with col2:
                st.metric("Idle Time", f"{idle_total}m")
            with col3:
                pct = (working_minutes / total_shift_minutes * 100) if total_shift_minutes > 0 else 0
                st.metric("% of Shift Active", f"{pct:.0f}%")
        
        warnings = []
        
        if len(df_valid) > 1:
            speeds = []
            for i in range(len(df_valid) - 1):
                t1 = df_valid.iloc[i]['Date Canvassed']
                t2 = df_valid.iloc[i + 1]['Date Canvassed']
                speed = calculate_speed_mph(t1, t2)
                if speed > 5:
                    speeds.append(speed)
            
            if speeds:
                avg_speed = np.mean(speeds)
                warnings.append(f"⚠️ High movement speed detected ({avg_speed:.1f} mph avg between some doors)")
        
        df_ind['Street'] = df_ind['Address'].apply(extract_street_name)
        df_valid['Street'] = df_valid['Address'].apply(extract_street_name)
        street_times = []
        
        for street in df_valid['Street'].unique():
            street_data = df_valid[df_valid['Street'] == street].sort_values('Date Canvassed')
            if len(street_data) > 1:
                time_on_street = (street_data['Date Canvassed'].max() - street_data['Date Canvassed'].min()).total_seconds() / 60
                doors_on_street = len(street_data)
                avg_time_per_door = time_on_street / doors_on_street if doors_on_street > 0 else 0
                
                if avg_time_per_door > 5:
                    street_times.append((street, avg_time_per_door, doors_on_street))
        
        if street_times:
            for street, avg_time, door_count in street_times[:3]:
                warnings.append(f"⚠️ Extended time on {street} ({avg_time:.0f} min/door, {door_count} doors)")
        
        if warnings:
            st.markdown("### ⚠️ Review Recommended")
            for warning in warnings:
                st.markdown(f'<div class="warning-box">{warning}</div>', unsafe_allow_html=True)
        
        if st.session_state.survey_data is not None and len(matching) > 0:
            st.markdown("### 📋 Individual Survey Responses")
            
            if 'Question' in matching.columns and 'Response' in matching.columns:
                matching['Q_R'] = matching['Question'].astype(str) + ' - ' + matching['Response'].astype(str)
                response_counts = matching['Q_R'].value_counts().reset_index()
                response_counts.columns = ['Question - Response', 'Count']
                
                st.dataframe(response_counts, use_container_width=True, hide_index=True)
                st.metric("Total Surveys", len(matching))
        
        if st.session_state.survey_data is not None:
            st.markdown("### 📋 Survey Validation")
            
            contacted_ids = df_ind[
                ~df_ind['Contact Result'].str.lower().str.contains('not home|refused|moved|inaccessible', na=False)
            ][id_col].unique()
            
            survey_ids = matching['ID'].unique() if len(matching) > 0 else []
            has_surveys = len([i for i in contacted_ids if i in survey_ids])
            missing = len(contacted_ids) - has_surveys
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Contacts with Surveys", has_surveys)
            with col2:
                st.metric("Missing Surveys", missing)
            
            if missing > 0:
                st.warning(f"⚠️ {missing} contacts missing surveys")
            else:
                st.success("✅ All contacts have surveys!")
        
    except Exception as e:
        st.error(f"Error: {e}")
        import traceback
        st.code(traceback.format_exc())

elif (individual_file_1 or individual_file_2):
    st.warning("⚠️ Upload Topline Data first")
