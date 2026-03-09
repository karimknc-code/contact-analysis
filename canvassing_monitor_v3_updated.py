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
    .alert-warning {
        background-color: #fef3c7;
        border-left: 4px solid #f59e0b;
        padding: 1rem;
        border-radius: 4px;
        margin: 1rem 0;
    }
    .alert-critical {
        background-color: #fee2e2;
        border-left: 4px solid #ef4444;
        padding: 1rem;
        border-radius: 4px;
        margin: 1rem 0;
    }
    .alert-success {
        background-color: #d1fae5;
        border-left: 4px solid #10b981;
        padding: 1rem;
        border-radius: 4px;
        margin: 1rem 0;
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
        
        # Find Contact Rate column flexibly
        cr_col = next((c for c in topline_df.columns if 'contact' in c.lower() and 'rate' in c.lower()), None)
        if cr_col:
            topline_df['Contact_Rate_Pct'] = (topline_df[cr_col].astype(float) * 100).round(1)
        else:
            st.error(f"Can't find Contact Rate. Columns: {list(topline_df.columns)}")
            st.stop()
        
        st.session_state.topline_data = topline_df
        
        # Calculate team benchmarks
        benchmarks = {
            'avg_doors': topline_df['Doors'].mean(),
            'avg_contact_rate': topline_df['Contact_Rate_Pct'].mean(),
            'avg_canvassed': topline_df['Canvassed'].mean(),
            'top_performer': topline_df.loc[topline_df['Contact_Rate_Pct'].idxmax()]['Canvasser']
        }
        
        st.markdown("## 📊 Team Overview")
        
        # Team metrics - FIX #2: Show contact rate as percentage
        metric_cols = st.columns(4)
        with metric_cols[0]:
            st.metric("Team Size", len(topline_df))
        with metric_cols[1]:
            st.metric("Avg Doors", f"{benchmarks['avg_doors']:.0f}")
        with metric_cols[2]:
            st.metric("Avg Contact Rate", f"{benchmarks['avg_contact_rate']:.1f}%")  # FIXED: Added %
        with metric_cols[3]:
            st.metric("Top Performer", benchmarks['top_performer'])
        
        # Team leaderboard
        with st.expander("📋 View Team Leaderboard"):
            leaderboard = topline_df[['Canvasser', 'Doors', 'Canvassed', 'Contact_Rate_Pct', 'Not Home']].sort_values('Doors', ascending=False)
            leaderboard.columns = ['Canvasser', 'Doors', 'Canvassed', 'Contact Rate %', 'Not Home']
            st.dataframe(leaderboard, use_container_width=True, hide_index=True)
        
    except Exception as e:
        st.error(f"Error loading topline: {e}")

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
            
            # ID column
            if 'ID' not in col_mapping:
                if (col_stripped in ['ID', 'ID ', ' ID', 'Voter File VANID'] or 
                    (col_lower == 'id') or 
                    ('vanid' in col_lower) or
                    (col_stripped.startswith('ID') and len(col_stripped) <= 4)):
                    col_mapping['ID'] = col
            
            # CanvassedBy
            if 'CanvassedBy' not in col_mapping and 'canvassed' in col_lower and 'by' in col_lower:
                col_mapping['CanvassedBy'] = col
            
            # Question
            if 'Question' not in col_mapping and 'question' in col_lower and 'long' in col_lower:
                col_mapping['Question'] = col
            
            # Response
            if 'Response' not in col_mapping and 'response' in col_lower and 'name' in col_lower:
                col_mapping['Response'] = col
            
            # Date
            if 'Date' not in col_mapping and 'date' in col_lower and 'canvassed' in col_lower:
                col_mapping['Date'] = col
        
        # Verify required columns
        if 'ID' not in col_mapping:
            st.error(f"Could not find ID column. Available: {list(survey_df.columns)}")
            st.stop()
        if 'CanvassedBy' not in col_mapping:
            st.error(f"Could not find CanvassedBy column. Available: {list(survey_df.columns)}")
            st.stop()
        
        # Rename columns
        survey_df = survey_df[list(col_mapping.values())].copy()
        survey_df.columns = list(col_mapping.keys())
        survey_df['CanvassedBy'] = survey_df['CanvassedBy'].str.strip()
        
        st.session_state.survey_data = survey_df
        
        st.markdown("---")
        st.markdown("## 📋 Survey Response Analysis")
        
        # FIX #3: Removed "Total Surveys" card - just show canvassers
        st.metric("Active Canvassers", survey_df['CanvassedBy'].nunique())
        
        # Survey response table
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
            
            # Team totals
            team_row = {'Canvasser': '📊 TEAM TOTAL'}
            for qr in questions:
                team_row[qr] = len(survey_df[survey_df['Q_R'] == qr])
            table_data.append(team_row)
            
            result_df = pd.DataFrame(table_data)
            st.dataframe(result_df, use_container_width=True, hide_index=True)
        
        # FIX #4: Activity Timeline (Fixed)
        if 'Date' in survey_df.columns:
            st.markdown("### ⏱️ Activity Status")
            
            survey_df['DateCanvassed_parsed'] = pd.to_datetime(survey_df['Date'], errors='coerce')
            current_time = survey_df['DateCanvassed_parsed'].max()
            
            st.info(f"📸 Data snapshot as of: {current_time.strftime('%B %d, %Y at %I:%M%p')}")
            
            # Calculate activity for each canvasser
            activity_data = []
            for canvasser in canvassers:
                canv_data = survey_df[survey_df['CanvassedBy'] == canvasser]
                last_activity = canv_data['DateCanvassed_parsed'].max()
                minutes_ago = (current_time - last_activity).total_seconds() / 60
                
                status = "🟢 ACTIVE" if minutes_ago <= 30 else "🔴 IDLE"
                
                activity_data.append({
                    'Canvasser': canvasser,
                    'Last Activity': last_activity.strftime('%I:%M%p'),
                    'Minutes Ago': int(minutes_ago),
                    'Status': status,
                    'Surveys': len(canv_data)
                })
            
            activity_df = pd.DataFrame(activity_data)
            activity_df = activity_df.sort_values('Minutes Ago', ascending=False)
            
            st.dataframe(activity_df, use_container_width=True, hide_index=True)
            
            # Summary
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

# STEP 3: Process Individual Agent Data
# FIX #5: Support 2 file uploads and merge them
if (individual_file_1 or individual_file_2) and st.session_state.topline_data is not None:
    
    st.markdown("---")
    st.markdown("## 👤 Individual Agent Analysis")
    
    # Function to load individual file
    def load_individual_file(file):
        df_individual = None
        last_error = None
        for encoding in ['utf-8', 'utf-16', 'utf-8-sig']:
            for skiprows in [0, 1]:
                try:
                    file.seek(0)
                    test_df = pd.read_csv(file, encoding=encoding, skiprows=skiprows)
                    if len(test_df.columns) >= 5 and len(test_df) > 0:
                        df_individual = test_df
                        break
                except Exception as e:
                    last_error = e
                    continue
            if df_individual is not None:
                break
        
        if df_individual is None:
            raise Exception(f"Could not read file: {last_error}")
        
        df_individual.columns = df_individual.columns.str.replace('\ufeff', '').str.strip()
        return df_individual
    
    # Load files
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
        
        # Merge datasets
        df_individual = pd.concat(dfs_to_merge, ignore_index=True)
        st.info(f"📊 Combined total: {len(df_individual)} records across {len(dfs_to_merge)} turf(s)")
        
        # Process dates
        df_individual['Date Canvassed'] = pd.to_datetime(df_individual['Date Canvassed'], errors='coerce')
        if df_individual['Date Canvassed'].dt.tz is not None:
            df_individual['Date Canvassed'] = df_individual['Date Canvassed'].dt.tz_localize(None)
        df_individual = df_individual.sort_values('Date Canvassed')
        
        # Get agent name from survey data
        agent_name = None
        id_column = 'VanID' if 'VanID' in df_individual.columns else ('ID' if 'ID' in df_individual.columns else None)
        
        if id_column and st.session_state.survey_data is not None:
            individual_ids = df_individual[id_column].unique()
            survey_df = st.session_state.survey_data
            matching = survey_df[survey_df['ID'].isin(individual_ids)]
            
            if len(matching) > 0:
                agent_name = matching['CanvassedBy'].mode()[0]
            else:
                agent_name = "Unknown Agent"
        else:
            agent_name = "Unknown Agent"
        
        st.markdown(f"### {agent_name}")
        
        # FIX #6: Break out all non-contact types
        st.markdown("### 📊 Performance Snapshot")
        
        unique_doors = df_individual[id_column].nunique() if id_column else len(df_individual)
        
        # Get all unique contact results
        contact_results = df_individual['Contact Result'].value_counts()
        
        # Categorize
        contact_types = []
        non_contact_types = []
        
        for result, count in contact_results.items():
            result_lower = str(result).lower()
            if any(word in result_lower for word in ['not home', 'refused', 'moved', 'inaccessible', 'no answer', 'unavailable']):
                non_contact_types.append((result, count))
            else:
                contact_types.append((result, count))
        
        total_contacts = sum([c[1] for c in contact_types])
        total_non_contacts = sum([c[1] for c in non_contact_types])
        contact_rate = (total_contacts / unique_doors * 100) if unique_doors > 0 else 0
        
        # Display metrics
        metric_cols = st.columns(3)
        with metric_cols[0]:
            st.metric("Doors Knocked", unique_doors)
        with metric_cols[1]:
            st.metric("Contact Rate", f"{contact_rate:.1f}%")  # FIXED: Added %
        with metric_cols[2]:
            st.metric("Total Attempts", len(df_individual))
        
        # Break out non-contact types
        st.markdown("#### Non-Contact Breakdown")
        non_contact_cols = st.columns(min(len(non_contact_types), 4))
        for idx, (result_type, count) in enumerate(non_contact_types):
            with non_contact_cols[idx % 4]:
                st.metric(result_type, count)
        
        # Survey validation
        if id_column and st.session_state.survey_data is not None:
            st.markdown("### 📋 Survey Validation")
            
            contacted_ids = df_individual[df_individual['Contact Result'].str.lower().str.contains('not home|refused|moved|inaccessible')==False][id_column].unique()
            survey_ids = matching['ID'].unique()
            
            has_surveys = len([i for i in contacted_ids if i in survey_ids])
            missing = len(contacted_ids) - has_surveys
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Contacts with Surveys", has_surveys)
            with col2:
                st.metric("Missing Surveys", missing)
            
            if missing > 0:
                st.warning(f"⚠️ {missing} contacts marked but no surveys logged")
        
    except Exception as e:
        st.error(f"Error loading individual files: {e}")
        import traceback
        st.code(traceback.format_exc())

elif (individual_file_1 or individual_file_2) and st.session_state.topline_data is None:
    st.warning("⚠️ Please upload Topline Data first to enable team comparisons.")
