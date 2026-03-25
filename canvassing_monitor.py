"""
Civic Operations Group -- Field Canvassing Monitor
On-demand canvasser lookup with survey cross-reference and fraud detection.
"""

import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import io
import re
from datetime import datetime, timedelta
from collections import Counter

# --- Page Config ---
st.set_page_config(
    page_title="Field Canvassing Monitor",
    page_icon="\U0001f5f3\ufe0f",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Custom CSS ---
st.markdown("""
<style>
    /* Clean, modern look */
    .main .block-container { max-width: 1100px; padding-top: 2rem; }

    /* Status badges */
    .badge-ok {
        background: #d4edda; color: #155724; padding: 4px 14px;
        border-radius: 20px; font-weight: 600; font-size: 0.85rem;
        display: inline-block;
    }
    .badge-attention {
        background: #f8d7da; color: #721c24; padding: 4px 14px;
        border-radius: 20px; font-weight: 600; font-size: 0.85rem;
        display: inline-block;
    }

    /* Card styling */
    .canvasser-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5f8a 100%);
        color: white; padding: 1.5rem 2rem; border-radius: 12px;
        margin-bottom: 1.5rem;
    }
    .canvasser-header h2 { color: white; margin: 0 0 0.3rem 0; }
    .canvasser-header .meta { opacity: 0.85; font-size: 0.9rem; }

    /* Metric cards */
    .metric-row {
        display: flex; gap: 1rem; margin-bottom: 1rem;
    }
    .metric-card {
        flex: 1; background: #f8f9fa; border-radius: 10px;
        padding: 1rem 1.2rem; text-align: center;
        border: 1px solid #e9ecef;
    }
    .metric-card .value {
        font-size: 1.8rem; font-weight: 700; color: #1e3a5f;
    }
    .metric-card .label {
        font-size: 0.8rem; color: #6c757d; text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* Flag items */
    .flag-item {
        padding: 0.6rem 1rem; margin: 0.3rem 0;
        border-left: 4px solid #dc3545; background: #fff5f5;
        border-radius: 0 6px 6px 0; font-size: 0.9rem;
    }
    .flag-ok {
        border-left-color: #28a745; background: #f0fff4;
    }

    /* Section headers */
    .section-header {
        font-size: 1.1rem; font-weight: 600; color: #1e3a5f;
        border-bottom: 2px solid #e9ecef; padding-bottom: 0.5rem;
        margin: 1.5rem 0 1rem 0;
    }

    /* Hide default streamlit padding */
    .stExpander { border: 1px solid #e9ecef; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)


# DATA LOADING HELPERS

def load_minivan_csv(uploaded_file):
    """
    Parse a MiniVAN Canvasser Activity Report CSV.
    Handles UTF-16 with BOM + SEP=, header line.
    """
    raw = uploaded_file.read()

    # Try UTF-16 first (MiniVAN default), fall back to UTF-8
    for enc in ["utf-16", "utf-8-sig", "utf-8", "latin-1"]:
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        st.error("Could not decode the file. Please check the encoding.")
        return None

    # Strip SEP=, line if present
    lines = text.splitlines()
    if lines and lines[0].strip().upper().startswith("SEP="):
        lines = lines[1:]
    text = "\n".join(lines)

    # Read as CSV
    try:
        df = pd.read_csv(io.StringIO(text), sep=",")
    except Exception:
        try:
            df = pd.read_csv(io.StringIO(text), sep="\t")
        except Exception as e:
            st.error(f"Could not parse CSV: {e}")
            return None

    # Normalize column names
    col_map = {
        "VanID": "VanID", "Vanid": "VanID", "vanid": "VanID",
        "VANID": "VanID", "Voter File VANID": "VanID",
        "Contact Result": "ContactResult", "ContactResult": "ContactResult",
        "Date Canvassed": "DateCanvassed", "DateCanvassed": "DateCanvassed",
        "List Name": "ListName", "ListName": "ListName",
        "Name": "Name", "Address": "Address", "Status": "Status",
        "Phone": "Phone",
    }
    df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

    # Parse timestamps
    if "DateCanvassed" in df.columns:
        df["DateCanvassed"] = pd.to_datetime(df["DateCanvassed"], errors="coerce")

    return df


def load_survey_csv(uploaded_file):
    """
    Parse a VAN Survey Response export (UTF-8).
    """
    raw = uploaded_file.read()
    for enc in ["utf-8-sig", "utf-8", "utf-16", "latin-1"]:
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        return None

    lines = text.splitlines()
    if lines and lines[0].strip().upper().startswith("SEP="):
        lines = lines[1:]
    text = "\n".join(lines)

    df = pd.read_csv(io.StringIO(text))

    # Normalize VANID column
    for col in df.columns:
        if "vanid" in col.lower():
            df.rename(columns={col: "VanID"}, inplace=True)
            break

    return df


# ANALYSIS FUNCTIONS

def compute_performance(contact_df):
    """Compute performance metrics from contact data."""
    total_contacts = len(contact_df)
    unique_doors = contact_df["VanID"].nunique() if "VanID" in contact_df.columns else total_contacts

    canvassed = contact_df[contact_df["ContactResult"] == "Canvassed"] if "ContactResult" in contact_df.columns else pd.DataFrame()
    not_home = contact_df[contact_df["ContactResult"] == "Not Home"] if "ContactResult" in contact_df.columns else pd.DataFrame()
    refused = contact_df[contact_df["ContactResult"] == "Refused"] if "ContactResult" in contact_df.columns else pd.DataFrame()
    moved = contact_df[contact_df["ContactResult"] == "Moved"] if "ContactResult" in contact_df.columns else pd.DataFrame()
    inaccessible = contact_df[contact_df["ContactResult"] == "Inaccessible"] if "ContactResult" in contact_df.columns else pd.DataFrame()

    people_canvassed = len(canvassed)
    contact_rate = round(people_canvassed / unique_doors * 100, 1) if unique_doors > 0 else 0

    return {
        "doors": unique_doors,
        "canvassed": people_canvassed,
        "contact_rate": contact_rate,
        "not_home": len(not_home),
        "refused": len(refused),
        "moved": len(moved),
        "inaccessible": len(inaccessible),
    }


def compute_time_analysis(contact_df):
    """Analyze timestamps for idle periods and active/total time."""
    if "DateCanvassed" not in contact_df.columns:
        return None

    df = contact_df.dropna(subset=["DateCanvassed"]).sort_values("DateCanvassed")
    if len(df) < 2:
        return None

    timestamps = df["DateCanvassed"].tolist()
    start_time = timestamps[0]
    end_time = timestamps[-1]
    total_time = (end_time - start_time).total_seconds()

    if total_time <= 0:
        return None

    # Compute gaps between consecutive contacts
    gaps = []
    for i in range(1, len(timestamps)):
        gap_seconds = (timestamps[i] - timestamps[i-1]).total_seconds()
        gaps.append({
            "from_time": timestamps[i-1],
            "to_time": timestamps[i],
            "gap_seconds": gap_seconds,
            "from_address": df.iloc[i-1].get("Address", ""),
            "to_address": df.iloc[i].get("Address", ""),
        })

    # Idle = gaps > 10 minutes (600 seconds)
    idle_threshold = 600
    idle_gaps = [g for g in gaps if g["gap_seconds"] > idle_threshold]
    total_idle = sum(g["gap_seconds"] for g in idle_gaps)
    active_time = total_time - total_idle

    # Average pace (excluding idle gaps)
    active_gaps = [g for g in gaps if g["gap_seconds"] <= idle_threshold]
    avg_pace = np.mean([g["gap_seconds"] for g in active_gaps]) if active_gaps else 0

    # Contacts per active hour
    active_hours = active_time / 3600
    contacts_per_hour = len(df) / active_hours if active_hours > 0 else 0

    return {
        "start_time": start_time,
        "end_time": end_time,
        "total_time_min": round(total_time / 60, 1),
        "active_time_min": round(active_time / 60, 1),
        "idle_time_min": round(total_idle / 60, 1),
        "idle_pct": round(total_idle / total_time * 100, 1) if total_time > 0 else 0,
        "idle_gaps": idle_gaps,
        "avg_pace_sec": round(avg_pace, 0),
        "contacts_per_hour": round(contacts_per_hour, 1),
        "total_contacts": len(df),
    }


def cross_reference_surveys(contact_df, survey_df):
    """
    Cross-reference canvassed contacts against survey responses.
    Finds VANIDs marked as Canvassed but missing from survey data.
    """
    if contact_df is None or survey_df is None:
        return None

    # Get VANIDs marked as Canvassed
    canvassed = contact_df[contact_df["ContactResult"] == "Canvassed"] if "ContactResult" in contact_df.columns else pd.DataFrame()
    if canvassed.empty:
        return {"canvassed_count": 0, "with_survey": 0, "missing_survey": 0, "missing_details": []}

    canvassed_vanids = set(canvassed["VanID"].dropna().astype(int).astype(str))

    # Get VANIDs that have survey responses
    survey_vanids = set(survey_df["VanID"].dropna().astype(int).astype(str)) if "VanID" in survey_df.columns else set()

    # Find mismatches
    missing = canvassed_vanids - survey_vanids
    matched = canvassed_vanids & survey_vanids

    # Details of missing
    missing_details = []
    for vid in missing:
        row = canvassed[canvassed["VanID"].astype(str) == vid].iloc[0]
        missing_details.append({
            "VanID": vid,
            "Name": row.get("Name", "Unknown"),
            "Address": row.get("Address", "Unknown"),
            "DateCanvassed": str(row.get("DateCanvassed", "")),
        })

    return {
        "canvassed_count": len(canvassed_vanids),
        "with_survey": len(matched),
        "missing_survey": len(missing),
        "missing_details": missing_details,
    }


def compute_status(perf, time_analysis, survey_xref):
    """
    Determine OK vs Needs Attention status.
    Triggers:
    - Low contact rate (< 15%)
    - High idle time (> 30% of total)
    - Missing surveys (> 20% of canvassed contacts)
    """
    flags = []

    # Contact rate check
    if perf["contact_rate"] < 15 and perf["doors"] > 10:
        flags.append(f"Low contact rate: {perf['contact_rate']}% (threshold: 15%)")

    # Idle time check
    if time_analysis and time_analysis["idle_pct"] > 30:
        flags.append(f"High idle time: {time_analysis['idle_pct']}% of shift idle (threshold: 30%)")

    # Survey cross-reference check
    if survey_xref and survey_xref["canvassed_count"] > 0:
        missing_pct = survey_xref["missing_survey"] / survey_xref["canvassed_count"] * 100
        if missing_pct > 20:
            flags.append(f"Survey gaps: {survey_xref['missing_survey']}/{survey_xref['canvassed_count']} canvassed contacts missing survey responses ({missing_pct:.0f}%)")

    # Speed check -- impossibly fast pace
    if time_analysis and time_analysis["avg_pace_sec"] > 0 and time_analysis["avg_pace_sec"] < 20:
        flags.append(f"Suspiciously fast pace: avg {time_analysis['avg_pace_sec']:.0f}s between contacts")

    status = "ok" if len(flags) == 0 else "attention"
    return status, flags


def format_duration(minutes):
    """Format minutes into Xh Ym string."""
    if minutes < 60:
        return f"{minutes:.0f}m"
    hours = int(minutes // 60)
    mins = int(minutes % 60)
    return f"{hours}h {mins}m"


# SESSION STATE

if "survey_repository" not in st.session_state:
    st.session_state.survey_repository = None
    st.session_state.survey_filename = None

if "contact_data" not in st.session_state:
    st.session_state.contact_data = None
    st.session_state.contact_canvasser = None


# SIDEBAR -- Survey Repository

with st.sidebar:
    st.markdown("### Survey Repository")
    st.caption("Upload your VAN survey response export to enable fraud detection.")

    survey_file = st.file_uploader(
        "Upload Survey CSV",
        type=["csv", "txt"],
        key="survey_upload",
        help="Export survey responses from VAN and upload here."
    )

    if survey_file:
        survey_df = load_survey_csv(survey_file)
        if survey_df is not None:
            st.session_state.survey_repository = survey_df
            st.session_state.survey_filename = survey_file.name
            unique_vanids = survey_df["VanID"].nunique() if "VanID" in survey_df.columns else 0
            unique_canvassers = survey_df["CanvassedBy"].nunique() if "CanvassedBy" in survey_df.columns else 0
            st.success(f"Loaded: {len(survey_df)} responses")
            st.caption(f"{unique_vanids} unique voters - {unique_canvassers} canvassers")

    if st.session_state.survey_repository is not None:
        st.markdown("---")
        st.markdown(f"**Active:** {st.session_state.survey_filename}")
        if st.button("Clear Survey Data"):
            st.session_state.survey_repository = None
            st.session_state.survey_filename = None
            st.rerun()


# MAIN LAYOUT

st.markdown("# Field Canvassing Monitor")
st.caption("Civic Operations Group (NJ - Master Statewide)")

st.markdown("---")

# Upload contact data
st.markdown("### Look Up a Canvasser")
st.caption("Upload a MiniVAN Canvasser Activity Report (download from the individual canvasser page in SmartVAN).")

col_upload, col_name = st.columns([2, 1])
with col_upload:
    contact_file = st.file_uploader(
        "Upload MiniVAN Contact Data",
        type=["csv", "txt"],
        key="contact_upload",
        help="Download from SmartVAN: MiniVAN Activity Report > click canvasser > Export As > CSV"
    )

with col_name:
    canvasser_name = st.text_input(
        "Canvasser Name",
        placeholder="e.g., lianet moreno",
        help="Enter the canvasser name for the report header."
    )

if contact_file:
    contact_df = load_minivan_csv(contact_file)
    if contact_df is not None:
        st.session_state.contact_data = contact_df
        if canvasser_name:
            st.session_state.contact_canvasser = canvasser_name
        else:
            st.session_state.contact_canvasser = "Unknown Canvasser"


# DASHBOARD -- Only show when data is loaded

if st.session_state.contact_data is not None:
    df = st.session_state.contact_data
    name = st.session_state.contact_canvasser or "Unknown Canvasser"

    # Compute all metrics
    perf = compute_performance(df)
    time_analysis = compute_time_analysis(df)
    survey_xref = cross_reference_surveys(df, st.session_state.survey_repository)
    status, flags = compute_status(perf, time_analysis, survey_xref)

    # Last sync timestamp
    if "DateCanvassed" in df.columns and df["DateCanvassed"].notna().any():
        last_sync = df["DateCanvassed"].max()
        last_sync_str = last_sync.strftime("%b %d, %Y at %I:%M %p")
    else:
        last_sync_str = "Unknown"

    # Canvasser Header Card
    status_badge = (
        '<span class="badge-ok">OK</span>' if status == "ok"
        else '<span class="badge-attention">Needs Attention</span>'
    )

    st.markdown(f"""
    <div class="canvasser-header">
        <h2>{name.title()} {status_badge}</h2>
        <div class="meta">Last Activity: {last_sync_str}</div>
    </div>
    """, unsafe_allow_html=True)

    # Flags (if any)
    if flags:
        for flag in flags:
            st.markdown(f'<div class="flag-item">{flag}</div>', unsafe_allow_html=True)
        st.markdown("")

    # 1. PERFORMANCE SNAPSHOT

    with st.expander("Performance Snapshot", expanded=True):
        cols = st.columns(4)
        with cols[0]:
            st.metric("Doors Knocked", perf["doors"])
        with cols[1]:
            st.metric("People Canvassed", perf["canvassed"])
        with cols[2]:
            st.metric("Contact Rate", f"{perf['contact_rate']}%")
        with cols[3]:
            survey_count = survey_xref["canvassed_count"] if survey_xref else "---"
            st.metric("Survey Responses", survey_count if survey_xref else "No data")

        # Result breakdown
        st.markdown("**Result Breakdown**")
        result_data = {
            "Not Home": perf["not_home"],
            "Canvassed": perf["canvassed"],
            "Refused": perf["refused"],
        }
        if perf["moved"] > 0:
            result_data["Moved"] = perf["moved"]
        if perf["inaccessible"] > 0:
            result_data["Inaccessible"] = perf["inaccessible"]

        result_df = pd.DataFrame(list(result_data.items()), columns=["Result", "Count"])
        result_df["Pct"] = (result_df["Count"] / result_df["Count"].sum() * 100).round(1)
        result_df["Pct"] = result_df["Pct"].astype(str) + "%"

        st.dataframe(result_df, use_container_width=True, hide_index=True)


    # 2. SURVEY CROSS-REFERENCE

    with st.expander("Survey Cross-Reference", expanded=True):
        if survey_xref is None:
            st.info("Upload survey data in the sidebar to enable fraud detection.")
        elif survey_xref["canvassed_count"] == 0:
            st.info("No contacts marked as Canvassed found in the data.")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Contacts Canvassed", survey_xref["canvassed_count"])
            with col2:
                st.metric("With Survey Response", survey_xref["with_survey"],
                          delta=None)
            with col3:
                st.metric("Missing Survey", survey_xref["missing_survey"],
                          delta=f"-{survey_xref['missing_survey']}" if survey_xref["missing_survey"] > 0 else "0",
                          delta_color="inverse")

            if survey_xref["missing_survey"] > 0:
                st.markdown("")
                st.warning(f"**{survey_xref['missing_survey']} contacts** were marked as Canvassed but have no matching survey response. This may indicate data entry issues or potential fraud.")

                missing_df = pd.DataFrame(survey_xref["missing_details"])
                if not missing_df.empty:
                    st.markdown("**Missing Survey Details:**")
                    st.dataframe(missing_df, use_container_width=True, hide_index=True)
            else:
                st.success("All canvassed contacts have matching survey responses.")

    # 3. TIME ANALYSIS

    with st.expander("Time Analysis", expanded=True):
        if time_analysis is None:
            st.info("Timestamp data not available or insufficient for analysis.")
        else:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Time", format_duration(time_analysis["total_time_min"]))
            with col2:
                st.metric("Active Time", format_duration(time_analysis["active_time_min"]))
            with col3:
                st.metric("Idle Time", format_duration(time_analysis["idle_time_min"]),
                          delta=f"{time_analysis['idle_pct']}%",
                          delta_color="inverse" if time_analysis["idle_pct"] > 30 else "normal")
            with col4:
                st.metric("Contacts/Hour", time_analysis["contacts_per_hour"])

            st.markdown(f"**Shift:** {time_analysis['start_time'].strftime('%I:%M %p')} to {time_analysis['end_time'].strftime('%I:%M %p')}")
            st.markdown(f"**Avg Pace:** {time_analysis['avg_pace_sec']:.0f} seconds between doors")

            # Idle gap details
            if time_analysis["idle_gaps"]:
                st.markdown("**Idle Periods (gaps > 10 min):**")
                idle_rows = []
                for gap in time_analysis["idle_gaps"]:
                    idle_rows.append({
                        "From": gap["from_time"].strftime("%I:%M %p"),
                        "To": gap["to_time"].strftime("%I:%M %p"),
                        "Duration": format_duration(gap["gap_seconds"] / 60),
                        "Last Address": gap.get("from_address", ""),
                        "Next Address": gap.get("to_address", ""),
                    })
                st.dataframe(pd.DataFrame(idle_rows), use_container_width=True, hide_index=True)

            # Timeline visualization
            st.markdown("**Activity Timeline**")
            if "DateCanvassed" in df.columns:
                timeline_df = df.dropna(subset=["DateCanvassed"]).sort_values("DateCanvassed")
                if not timeline_df.empty:
                    timeline_df["Hour"] = timeline_df["DateCanvassed"].dt.floor("15min")
                    hourly = timeline_df.groupby("Hour").size().reset_index(name="Contacts")
                    st.bar_chart(hourly.set_index("Hour"), y="Contacts", use_container_width=True)


    # 4. ROUTE MAP

    with st.expander("Route Map", expanded=False):
        st.caption("Plots canvassing route in walk order based on timestamps.")

        if "Address" in df.columns and "DateCanvassed" in df.columns:
            route_df = df.dropna(subset=["DateCanvassed", "Address"]).sort_values("DateCanvassed")

            if not route_df.empty:
                # Check if coordinates are available in the data
                has_coords = "Latitude" in route_df.columns and "Longitude" in route_df.columns

                if has_coords:
                    map_df = route_df[["Latitude", "Longitude"]].dropna()
                    map_df.columns = ["lat", "lon"]
                    st.map(map_df, use_container_width=True)
                else:
                    st.info("Address coordinates not available in the data. To enable the map, upload a coordinates file with VANID, Latitude, and Longitude columns.")

                    coord_file = st.file_uploader("Upload Coordinates CSV (optional)", type=["csv"], key="coord_upload")
                    if coord_file:
                        try:
                            coord_df = pd.read_csv(coord_file)
                            # Normalize VanID column
                            for col in coord_df.columns:
                                if "vanid" in col.lower():
                                    coord_df.rename(columns={col: "VanID"}, inplace=True)
                                    break

                            # Merge coordinates
                            route_with_coords = route_df.merge(
                                coord_df[["VanID", "Latitude", "Longitude"]],
                                on="VanID", how="left"
                            )
                            map_data = route_with_coords[["Latitude", "Longitude"]].dropna()
                            if not map_data.empty:
                                map_data.columns = ["lat", "lon"]
                                st.map(map_data, use_container_width=True)
                                st.success(f"Mapped {len(map_data)}/{len(route_df)} addresses.")
                            else:
                                st.warning("No matching coordinates found.")
                        except Exception as e:
                            st.error(f"Error loading coordinates: {e}")

                # Show address list in walk order
                st.markdown("**Walk Order:**")
                walk_df = route_df[["DateCanvassed", "Address", "Name", "ContactResult"]].copy()
                walk_df["Time"] = walk_df["DateCanvassed"].dt.strftime("%I:%M:%S %p")
                walk_df = walk_df[["Time", "Address", "Name", "ContactResult"]]
                walk_df.columns = ["Time", "Address", "Voter", "Result"]
                st.dataframe(walk_df, use_container_width=True, hide_index=True)
        else:
            st.info("Address and timestamp data required for route mapping.")

    # 5. RAW DATA

    with st.expander("Raw Contact Data", expanded=False):
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Download button
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        st.download_button(
            "Download as CSV",
            csv_buffer.getvalue(),
            file_name=f"{name.replace(' ', '_')}_contacts.csv",
            mime="text/csv"
        )

else:
    # Empty state
    st.markdown("")
    st.markdown("""
    <div style="text-align: center; padding: 3rem; color: #6c757d;">
        <h3>Upload a canvasser MiniVAN report to get started</h3>
        <p>
            Go to SmartVAN then MiniVAN Activity Report then Click a canvasser list then
            Export As then CSV then Upload here
        </p>
        <p style="font-size: 0.85rem; margin-top: 1rem;">
            For fraud detection, also upload survey response data via the sidebar.
        </p>
    </div>
    """, unsafe_allow_html=True)


# Footer
st.markdown("---")
st.caption("Field Canvassing Monitor - Civic Operations Group - Built for quality assurance")
