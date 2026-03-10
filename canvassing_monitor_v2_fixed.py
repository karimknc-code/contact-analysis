import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import numpy as np

# Page config
st.set_page_config(
    page_title="Field Canvassing Monitor",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS - optimized for light and dark mode
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
    .metric-card {
        padding: 1.5rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'topline_data' not in st.session_state:
    st.session_state.topline_data = None
if 'survey_data' not in st.session_state:
    st.session_state.survey_data = None

# Header
st.markdown('<div class="main-header">🎯 Field Canvassing Monitor</div>', unsafe_allow_html=True)

# Three-column upload
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### 📊 Step 1: Topline Data")
    topline_file = st.file_uploader("Team summary CSV", type=['csv'], key='topline')

with col2:
    st.markdown("### 📋 Step 2: Survey Responses")
    survey_file = st.file_uploader("Survey data CSV", type=['csv'], key='survey')

with col3:
    st.markdown("### 👤 Step 3: Individual Agent Data")
    st.markdown("Upload up to 2 files if agent changed turfs mid-shift")
    individual_file_1 = st.file_uploader("First turf", type=['csv'], key='individual_1')
    individual_file_2 = st.file_uploader("Second turf (optional)", type=['csv'], key='individual_2')

st.markdown("---")

# STEP 1: Process Topline
if topline_file:
    try:
        # Try UTF-16 (Excel export) with skiprows, then UTF-8
        try:
            topline_df = pd.read_csv(topline_file, encoding='utf-16', skiprows=1)
        except:
            try:
                topline_df = pd.read_csv(topline_file, encoding='utf-8-sig')
            except:
                topline_df = pd.read_csv(topline_file)
        
        topline_df.columns = topline_df.columns.str.replace('\ufeff', '').str.strip()
        
        # FIX #1: Calculate contact rate from Canvassed/Doors
        canvassed_col = next((c for c in topline_df.columns if 'canvassed' in c.lower()), 'Canvassed')
        doors_col = next((c for c in topline_df.columns if 'doors' in c.lower()), 'Doors')
        canvasser_col = next((c for c in topline_df.columns if 'canvasser' in c.lower()), 'Canvasser')
        
        topline_df['Contact_Rate_Pct'] = (topline_df[canvassed_col] / topline_df[doors_col] * 100).round(1)
        
        st.session_state.topline_data = topline_df
        
        # Calculate team benchmarks
        benchmarks = {
            'avg_doors': topline_df[doors_col].mean(),
            'avg_contact_rate': topline_df['Contact_Rate_Pct'].mean(),
        }
        
        st.markdown("## 📊 Team Overview")
        
        # FIX #2: Removed Top Performer
        metric_cols = st.columns(3)
        with metric_cols[0]:
            st.metric("Team Size", len(topline_df))
        with metric_cols[1]:
            st.metric("Avg Doors", f"{benchmarks['avg_doors']:.0f}")
        with metric_cols[2]:
            st.metric("Avg Contact Rate", f"{benchmarks['avg_contact_rate']:.1f}%")
        
        # Team leaderboard
        with st.expander("📋 View Team Leaderboard"):
            leaderboard = topline_df[[canvasser_col, doors_col, canvassed_col, 'Contact_Rate_Pct']].sort_values(doors_col, ascending=False).copy()
            leaderboard.columns = ['Canvasser', 'Doors', 'Canvassed', 'Contact Rate %']
            st.dataframe(leaderboard, use_container_width=True, hide_index=True)
        
    except Exception as e:
        st.error(f"Error loading topline: {e}")
        import traceback
        st.code(traceback.format_exc())

# STEP 2: Process Survey
if survey_file:
    try:
        # Try UTF-8 first, then UTF-16
        try:
            survey_df = pd.read_csv(survey_file, encoding='utf-8')
        except:
            try:
                survey_df = pd.read_csv(survey_file, encoding='utf-16', skiprows=1)
            except:
                survey_df = pd.read_csv(survey_file, encoding='utf-8-sig')
        
        survey_df.columns = survey_df.columns.str.replace('\ufeff', '').str.strip()
        
        # Find columns
        col_mapping = {}
        for col in survey_df.columns:
            col_lower = col.lower().strip()
            col_stripped = col.strip()
            
            if 'ID' not in col_mapping:
                if (col_stripped in ['ID', 'Voter File VANID'] or 'vanid' in col_lower):
                    col_mapping['ID'] = col
            
            if 'CanvassedBy' not in col_mapping and 'canvassed' in col_lower and 'by' in col_lower:
                col_mapping['CanvassedBy'] = col
            
            if 'Question' not in col_mapping and 'question' in col_lower and 'long' in col_lower:
                col_mapping['Question'] = col
            
            if 'Response' not in col_mapping and 'response' in col_lower and 'name' in col_lower:
                col_mapping['Response'] = col
            
            if 'Date' not in col_mapping and 'date' in col_lower and 'canvassed' in col_lower:
                col_mapping['Date'] = col
        
        if 'ID' not in col_mapping or 'CanvassedBy' not in col_mapping:
            st.error(f"Missing required columns. Available: {list(survey_df.columns)}")
            st.stop()
        
        # Rename columns
        survey_df = survey_df[list(col_mapping.values())].copy()
        survey_df.columns = list(col_mapping.keys())
        survey_df['CanvassedBy'] = survey_df['CanvassedBy'].str.strip()
        
        st.session_state.survey_data = survey_df
        
        st.markdown("---")
        st.markdown("## 📋 Survey Response Analysis")
        
        st.metric("Active Canvassers", survey_df['CanvassedBy'].nunique())
        
        # FIX #3: Restore survey response table
        if 'Question' in survey_df.columns and 'Response' in survey_df.columns:
            st.markdown("### Survey Response Counts by Canvasser")
            
            survey_df['Q_R'] = survey_df['Question'].astype(str) + ' - ' + survey_df['Response'].astype(str)
            canvassers = sorted(survey_df['CanvassedBy'].unique())
            questions = sorted(survey_df['Q_R'].unique())
            
            table_data = []
            for canvasser in canvassers:
                row = {'Canvasser': canvasser}
                canvasser_data = survey_df[survey_df['CanvassedBy'] == canvasser]
                
                for qr in questions:
                    count = len(canvasser_data[canvasser_data['Q_R'] == qr])
                    row[qr] = count
                
                table_data.append(row)
            
            team_row = {'Canvasser': '📊 TEAM TOTAL'}
            for qr in questions:
                team_row[qr] = len(survey_df[survey_df['Q_R'] == qr])
            table_data.append(team_row)
            
            result_df = pd.DataFrame(table_data)
            
            # FIX #5 & #6: Display with styling
            st.dataframe(result_df, use_container_width=True, hide_index=True, height=400)
        
        # FIX #7: Activity Timeline with correct time parsing
        if 'Date' in survey_df.columns:
            st.markdown("### ⏱️ Activity Status")
            
            # DEBUG: Show sample of raw date values
            with st.expander("🔍 Debug: Raw Date Samples"):
                st.write("First 5 date values from survey data:")
                st.write(survey_df['Date'].head())
            
            # Parse dates with multiple format attempts
            survey_df['DateCanvassed_parsed'] = pd.to_datetime(survey_df['Date'], errors='coerce', format='mixed')
            
            # Remove any rows with invalid dates
            survey_df_valid = survey_df[survey_df['DateCanvassed_parsed'].notna()].copy()
            
            if len(survey_df_valid) == 0:
                st.error("❌ No valid timestamps found in survey data. Check date format!")
            else:
                # Use the latest timestamp as "current time"
                current_time = survey_df_valid['DateCanvassed_parsed'].max()
                
                st.info(f"📸 Data snapshot as of: {current_time.strftime('%B %d, %Y at %I:%M %p')}")
                
                canvassers = survey_df_valid['CanvassedBy'].unique()
                
                activity_data = []
                for canvasser in canvassers:
                    canv_data = survey_df_valid[survey_df_valid['CanvassedBy'] == canvasser]
                    last_activity_dt = canv_data['DateCanvassed_parsed'].max()
                    
                    # Calculate minutes difference
                    time_diff = current_time - last_activity_dt
                    minutes_ago = int(time_diff.total_seconds() / 60)
                    
                    status = "🟢 ACTIVE" if minutes_ago <= 30 else "🔴 IDLE"
                    doors_count = canv_data['ID'].nunique()
                    
                    # Format time properly - handle timezone if present
                    if pd.api.types.is_datetime64tz_dtype(last_activity_dt):
                        last_activity_dt = last_activity_dt.tz_localize(None)
                    
                    activity_data.append({
                        'Canvasser': canvasser,
                        'Last Activity': last_activity_dt.strftime('%I:%M %p'),
                        'Minutes Ago': minutes_ago,
                        'Status': status,
                        'Doors': doors_count
                    })
                
                activity_df = pd.DataFrame(activity_data)
                activity_df = activity_df.sort_values('Minutes Ago', ascending=False)
                
                st.dataframe(activity_df, use_container_width=True, hide_index=True)
                
                active_count = len([d for d in activity_data if d['Minutes Ago'] <= 30])
                idle_count = len(activity_data) - active_count
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("🟢 Active", active_count)
                with col2:
                    st.metric("🔴 Idle (>30min)", idle_count)
        
    except Exception as e:
        st.error(f"Error loading survey: {e}")
        import traceback
        st.code(traceback.format_exc())

# STEP 3: Process Individual
if (individual_file_1 or individual_file_2) and st.session_state.topline_data is not None:
    
    st.markdown("---")
    st.markdown("## 👤 Individual Agent Analysis")
    
    def load_individual_file(file):
        df_individual = None
        for encoding in ['utf-8', 'utf-16', 'utf-8-sig']:
            for skiprows in [0, 1]:
                try:
                    file.seek(0)
                    test_df = pd.read_csv(file, encoding=encoding, skiprows=skiprows)
                    if len(test_df.columns) >= 5 and len(test_df) > 0:
                        df_individual = test_df
                        break
                except:
                    continue
            if df_individual is not None:
                break
        
        if df_individual is None:
            raise Exception("Could not read file")
        
        df_individual.columns = df_individual.columns.str.replace('\ufeff', '').str.strip()
        return df_individual
    
    try:
        dfs_to_merge = []
        
        if individual_file_1:
            df1 = load_individual_file(individual_file_1)
            dfs_to_merge.append(df1)
            st.success(f"✅ Loaded first turf: {len(df1)} records")
        
        if individual_file_2:
            df2 = load_individual_file(individual_file_2)
            dfs_to_merge.append(df2)
            st.success(f"✅ Loaded second turf: {len(df2)} records")
        
        df_individual = pd.concat(dfs_to_merge, ignore_index=True)
        st.info(f"📊 Combined total: {len(df_individual)} records")
        
        df_individual['Date Canvassed'] = pd.to_datetime(df_individual['Date Canvassed'], errors='coerce')
        if df_individual['Date Canvassed'].dt.tz is not None:
            df_individual['Date Canvassed'] = df_individual['Date Canvassed'].dt.tz_localize(None)
        
        id_column = 'VanID' if 'VanID' in df_individual.columns else 'ID'
        
        # Get agent name from survey
        agent_name = "Unknown Agent"
        if st.session_state.survey_data is not None:
            individual_ids = df_individual[id_column].unique()
            matching = st.session_state.survey_data[st.session_state.survey_data['ID'].isin(individual_ids)]
            
            if len(matching) > 0:
                agent_name = matching['CanvassedBy'].mode()[0]
        
        st.markdown(f"### {agent_name}")
        
        # FIX #8: Get contact rate from topline
        agent_topline = st.session_state.topline_data[
            st.session_state.topline_data['Canvasser'].str.strip().str.lower() == agent_name.strip().lower()
        ]
        
        if len(agent_topline) > 0:
            contact_rate = agent_topline['Contact_Rate_Pct'].iloc[0]
            doors = agent_topline['Doors'].iloc[0]
        else:
            contact_rate = 0
            doors = df_individual[id_column].nunique()
        
        st.markdown("### 📊 Performance Snapshot")
        
        metric_cols = st.columns(3)
        with metric_cols[0]:
            st.metric("Doors Knocked", int(doors))
        with metric_cols[1]:
            st.metric("Contact Rate", f"{contact_rate:.1f}%")
        with metric_cols[2]:
            st.metric("Total Attempts", len(df_individual))
        
        # Non-contact breakdown
        contact_results = df_individual['Contact Result'].value_counts()
        non_contact_types = []
        
        for result, count in contact_results.items():
            result_lower = str(result).lower()
            if any(word in result_lower for word in ['not home', 'refused', 'moved', 'inaccessible']):
                non_contact_types.append((result, count))
        
        if non_contact_types:
            st.markdown("#### Non-Contact Breakdown")
            non_contact_cols = st.columns(min(len(non_contact_types), 4))
            for idx, (result_type, count) in enumerate(non_contact_types):
                with non_contact_cols[idx % 4]:
                    st.metric(result_type, count)
        
        # FIX #4: Individual survey responses
        if st.session_state.survey_data is not None and len(matching) > 0:
            st.markdown("### 📋 Individual Survey Responses")
            
            agent_surveys = matching.copy()
            
            if 'Question' in agent_surveys.columns and 'Response' in agent_surveys.columns:
                agent_surveys['Q_R'] = agent_surveys['Question'].astype(str) + ' - ' + agent_surveys['Response'].astype(str)
                
                response_counts = agent_surveys['Q_R'].value_counts().reset_index()
                response_counts.columns = ['Question - Response', 'Count']
                
                st.dataframe(response_counts, use_container_width=True, hide_index=True)
                st.metric("Total Surveys", len(agent_surveys))
        
        # Survey validation
        if st.session_state.survey_data is not None:
            st.markdown("### 📋 Survey Validation")
            
            contacted_ids = df_individual[
                ~df_individual['Contact Result'].str.lower().str.contains('not home|refused|moved|inaccessible', na=False)
            ][id_column].unique()
            
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
