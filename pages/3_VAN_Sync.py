"""
Civic Operations Group — VAN Data Sync
One-click sync from SmartVAN Activity Report to cantrack.pro.
Supports both overview (all canvassers) and detail (individual canvasser) data.
"""
import streamlit as st
import json
import os
import glob
import base64
import urllib.request
import urllib.error
from datetime import datetime

# ── Page config ──────────────────────────────────────────────────────────
st.set_page_config(page_title="VAN Sync", page_icon="🔄", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #fafafa; }
    .sync-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border-radius: 12px; padding: 2rem; text-align: center;
        margin-bottom: 1.5rem; border: 1px solid #30363d;
    }
    .sync-header h1 { color: #ffffff; margin: 0; font-size: 2rem; }
    .sync-header p { color: #8b949e; margin: 0.5rem 0 0 0; }
    .status-bar {
        background: #161b22; border-left: 4px solid #238636;
        padding: 1rem 1.5rem; border-radius: 8px; margin-bottom: 1.5rem;
        font-size: 0.95rem;
    }
    .status-bar strong { color: #58a6ff; }
    .step-card {
        background: #161b22; border: 1px solid #30363d;
        border-radius: 10px; padding: 1.5rem; height: 100%;
    }
    .step-card h4 { color: #58a6ff; margin-top: 0; }
    .step-card code {
        background: #0d1117; padding: 2px 6px; border-radius: 4px;
        color: #7ee787; font-size: 0.85rem;
    }
    .bookmarklet-box {
        background: #0d1117; border: 2px dashed #30363d;
        border-radius: 10px; padding: 1.5rem; text-align: center;
        margin: 1rem 0;
    }
    .section-divider {
        border: none; border-top: 1px solid #30363d;
        margin: 2rem 0;
    }
    div[data-testid="stTextArea"] textarea {
        background-color: #0d1117 !important; color: #c9d1d9 !important;
        border: 1px solid #30363d !important; font-family: monospace;
    }
    .footer {
        text-align: center; color: #484f58; font-size: 0.8rem;
        margin-top: 3rem; padding-top: 1rem;
        border-top: 1px solid #21262d;
    }
</style>
""", unsafe_allow_html=True)

# ── GitHub helpers ────────────────────────────────────────────────────────
GITHUB_REPO = "karimknc-code/contact-analysis"
GITHUB_FILE = "overview_data.json"

def get_github_token():
    """Get token from environment variable."""
    return os.environ.get("GITHUB_PAT", "")

def push_to_github(json_content, file_path, commit_message="Sync data from VAN"):
    """Push JSON content to a file in GitHub repo via API."""
    token = get_github_token()
    if not token:
        return False, "GITHUB_PAT environment variable not set"

    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{file_path}"

    # Get current file SHA (if it exists)
    sha = None
    req = urllib.request.Request(api_url, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    })
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            sha = data.get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return False, f"GitHub API error: {e.code}"

    # Push updated content
    content_b64 = base64.b64encode(json_content.encode()).decode()
    body = {
        "message": commit_message,
        "content": content_b64
    }
    if sha:
        body["sha"] = sha

    put_data = json.dumps(body).encode()
    req = urllib.request.Request(api_url, data=put_data, method="PUT", headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    })
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            return True, result.get("commit", {}).get("sha", "unknown")[:7]
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        return False, f"Push failed ({e.code}): {body_text[:200]}"

# ── Data validators ──────────────────────────────────────────────────────
def validate_overview_json(raw_text):
    """Validate pasted JSON matches expected overview format."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"

    if isinstance(data, list):
        if len(data) == 0:
            return None, "Empty array"
        sample = data[0]
        required = {"canvasser", "attempts", "doors", "canvassed", "notHome"}
        if not required.issubset(set(sample.keys())):
            missing = required - set(sample.keys())
            return None, f"Missing fields: {missing}"
        return data, None

    if isinstance(data, dict):
        if "canvassers" in data:
            return data, None
        return None, "Expected 'canvassers' array in object"

    return None, "Expected JSON array or object with 'canvassers'"


def validate_detail_json(raw_text):
    """Validate pasted JSON matches expected canvasser detail format."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"

    if isinstance(data, list):
        if len(data) == 0:
            return None, "Empty array"
        sample = data[0]
        required = {"vanid", "name", "address", "contact_result", "date_canvassed"}
        if not required.issubset(set(sample.keys())):
            missing = required - set(sample.keys())
            return None, f"Missing fields in contacts: {missing}"
        return data, None

    if isinstance(data, dict):
        if "contacts" in data and "canvasser" in data:
            return data, None
        return None, "Expected object with 'canvasser' and 'contacts' keys"

    return None, "Expected JSON array of contacts or detail object"


def build_overview_json(canvassers):
    """Build overview_data.json from raw canvasser array."""
    total_attempts = sum(c.get("attempts", 0) for c in canvassers)
    total_doors = sum(c.get("doors", 0) for c in canvassers)
    total_canvassed = sum(c.get("canvassed", 0) for c in canvassers)
    total_not_home = sum(c.get("notHome", 0) for c in canvassers)
    contact_rate = f"{round(total_canvassed / total_attempts * 100)}%" if total_attempts else "0%"
    now = datetime.utcnow()
    return {
        "scraped_at": now.isoformat() + "Z",
        "sync_date": now.strftime("%-m/%-d/%y"),
        "report_summary": {
            "total_attempts": total_attempts,
            "total_doors": total_doors,
            "total_canvassed": total_canvassed,
            "total_not_home": total_not_home,
            "contact_rate": contact_rate
        },
        "total_records": len(canvassers),
        "canvassers": canvassers
    }


def build_detail_json(contacts, canvasser_name, list_name):
    """Build detail JSON for a single canvasser."""
    now = datetime.utcnow()
    return {
        "canvasser": canvasser_name,
        "list_name": list_name,
        "scraped_at": now.isoformat() + "Z",
        "total_contacts": len(contacts),
        "contacts": contacts
    }


# ── Load current overview data ───────────────────────────────────────────
data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "overview_data.json")
current_data = None
try:
    with open(data_path, "r") as f:
        current_data = json.load(f)
except Exception:
    pass

# Count existing detail files
details_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "details")
detail_count = 0
if os.path.exists(details_dir):
    detail_count = len(glob.glob(os.path.join(details_dir, "*.json")))

# ── Bookmarklet JavaScript ───────────────────────────────────────────────
OVERVIEW_BOOKMARKLET_JS = r"""javascript:void(function(){var t=document.querySelectorAll('table.rgMasterTable tbody tr, table[id*="Grid"] tbody tr');if(!t.length){alert('No table found. Open SmartVAN Activity Report first.');return}var d=[];t.forEach(function(r){var c=r.querySelectorAll('td');if(c.length>=8){var name=c[1]?c[1].innerText.trim():'';if(name&&name!==''){d.push({canvasser:name,listName:c[0]?c[0].innerText.trim():'',attempts:parseInt(c[2]?c[2].innerText.trim():0)||0,doors:parseInt(c[3]?c[3].innerText.trim():0)||0,canvassed:parseInt(c[4]?c[4].innerText.trim():0)||0,notHome:parseInt(c[5]?c[5].innerText.trim():0)||0,moved:parseInt(c[6]?c[6].innerText.trim():0)||0,refused:parseInt(c[7]?c[7].innerText.trim():0)||0,status:c[8]?c[8].innerText.trim():'P'})}}});if(!d.length){alert('No data rows found.');return}var prev=localStorage.getItem('van_scrape');if(prev){try{var old=JSON.parse(prev);d=old.concat(d)}catch(e){}}localStorage.setItem('van_scrape',JSON.stringify(d));var more=confirm('Scraped '+d.length+' rows total (this page: '+t.length+').\n\nMore pages? Click Cancel to accumulate, OK to copy & finish.');if(more){var txt=JSON.stringify(d);navigator.clipboard.writeText(txt).then(function(){localStorage.removeItem('van_scrape');alert('Copied '+d.length+' canvassers to clipboard.\nPaste into cantrack.pro/VAN_Sync')}).catch(function(){localStorage.removeItem('van_scrape');prompt('Copy this JSON:',txt)})}})()"""

DETAIL_BOOKMARKLET_JS = r"""javascript:void(function(){var t=document.querySelectorAll('table.rgMasterTable tbody tr, table[id*="Grid"] tbody tr');if(!t.length){alert('No detail table found. Open a canvasser detail report first.');return}var pageTitle=document.title||'';var canvasserName='';var listName='';var listMatch=pageTitle.match(/List\s+([\d-]+)/);if(listMatch){listName='List '+listMatch[1]}var nameMatch=pageTitle.match(/[\d-]+,\s*(.+)/);if(nameMatch){canvasserName=nameMatch[1].trim()}var d=[];t.forEach(function(r){var c=r.querySelectorAll('td');if(c.length>=6){var vanid=c[0]?c[0].innerText.trim():'';if(vanid&&/^\d+$/.test(vanid)){d.push({vanid:vanid,name:c[1]?c[1].innerText.trim():'',address:c[2]?c[2].innerText.trim():'',contact_result:c[3]?c[3].innerText.trim():'',list_name:c[4]?c[4].innerText.trim():'',date_canvassed:c[5]?c[5].innerText.trim():''})}}});if(!d.length){alert('No contact rows found.');return}var prev=localStorage.getItem('van_detail_scrape');if(prev){try{var old=JSON.parse(prev);d=old.concat(d)}catch(e){}}localStorage.setItem('van_detail_scrape',JSON.stringify(d));var more=confirm('Scraped '+d.length+' contacts total.\n\nMore pages? Click Cancel to accumulate, OK to copy & finish.');if(more){var out={canvasser:canvasserName,list_name:listName,contacts:d};var txt=JSON.stringify(out);navigator.clipboard.writeText(txt).then(function(){localStorage.removeItem('van_detail_scrape');alert('Copied '+d.length+' contacts for '+canvasserName+'.\nPaste into cantrack.pro/VAN_Sync Detail tab')}).catch(function(){localStorage.removeItem('van_detail_scrape');prompt('Copy this JSON:',txt)})}})()"""

# ── Header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="sync-header">
    <h1>VAN Data Sync</h1>
    <p>Sync SmartVAN Activity Report data to cantrack.pro in seconds</p>
</div>
""", unsafe_allow_html=True)

# ── Status bar ───────────────────────────────────────────────────────────
if current_data:
    summary = current_data.get("report_summary", {})
    sync_date = current_data.get("sync_date", "—")
    records = current_data.get("total_records", 0)
    attempts = f"{summary.get('total_attempts', 0):,}"
    rate = summary.get("contact_rate", "—")
    scraped = current_data.get("scraped_at", "")
    detail_info = f" | <strong>Detail Files:</strong> {detail_count}" if detail_count > 0 else ""
    st.markdown(f"""
    <div class="status-bar">
        <strong>Last Sync:</strong> {sync_date} &nbsp;|&nbsp;
        <strong>Records:</strong> {records} &nbsp;|&nbsp;
        <strong>Attempts:</strong> {attempts} &nbsp;|&nbsp;
        <strong>Contact Rate:</strong> {rate}{detail_info}<br>
        <span style="color:#484f58; font-size:0.85rem;">Scraped: {scraped}</span>
    </div>
    """, unsafe_allow_html=True)

# ── Tabs for Overview vs Detail ──────────────────────────────────────────
tab_overview, tab_detail = st.tabs(["📊 Overview Sync", "🔍 Detail Sync"])

# ═══════════════════════════════════════════════════════════════════════════════════════════════
# TAB 1: OVERVIEW SYNC
# ═══════════════════════════════════════════════════════════════════════════
with tab_overview:
    st.markdown("### How It Works")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("""
        <div class="step-card">
            <h4>Step 1: Scrape VAN</h4>
            <p>Click the bookmarklet while on SmartVAN's Activity Report. It
            scrapes the table and copies JSON to your clipboard.</p>
            <code>Handles pagination</code>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown("""
        <div class="step-card">
            <h4>Step 2: Paste Here</h4>
            <p>Paste the JSON into the text box below and hit <strong>Push to GitHub</strong>.</p>
            <code>Auto-validates format</code>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown("""
        <div class="step-card">
            <h4>Step 3: Auto-Deploy</h4>
            <p>Railway detects the GitHub push and redeploys cantrack.pro
            automatically. Done.</p>
            <code>~30 seconds</code>
        </div>
        """, unsafe_allow_html=True)

    # Bookmarklet
    st.markdown("### Bookmarklet")
    st.markdown(f"""
    <div class="bookmarklet-box">
        <a href='{OVERVIEW_BOOKMARKLET_JS}' style="
            display: inline-block; padding: 12px 28px;
            background: #d29922; color: #000; font-weight: bold;
            border-radius: 8px; text-decoration: none; font-size: 1rem;
        ">📋 Scrape VAN</a>
        <p style="color:#8b949e; margin-top:0.75rem; font-size:0.85rem;">
            Drag this button to your bookmarks bar. Then click it when you're on SmartVAN's Activity Report.
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="background:#161b22; border:1px solid #30363d; border-radius:8px; padding:1rem 1.5rem; margin:1rem 0;">
        <strong style="color:#58a6ff;">Multi-page reports:</strong><br>
        <span style="color:#c9d1d9;">
        1. Open SmartVAN Activity Report<br>
        2. Click the bookmarklet on page 1 → click <strong>Cancel</strong> in the dialog<br>
        3. Click <strong>Next</strong> to go to page 2 → click the bookmarklet again → <strong>Cancel</strong><br>
        4. Repeat for page 3 → click the bookmarklet → click <strong>OK</strong> to copy all data
        </span>
    </div>
    """, unsafe_allow_html=True)

    # Paste area
    st.markdown("### Sync Data")
    overview_mode = st.radio(
        "Data format",
        ["Paste scraped JSON (from bookmarklet)", "Paste full overview_data.json"],
        horizontal=True,
        key="overview_mode"
    )

    overview_text = st.text_area(
        "Paste JSON data here",
        height=200,
        placeholder="Paste the JSON copied by the bookmarklet, or a full overview_data.json...",
        key="overview_paste"
    )

    col_push, col_clear = st.columns([1, 4])
    with col_push:
        push_overview = st.button("🚀 Push to GitHub", type="primary", key="push_overview")
    with col_clear:
        if st.button("Clear", key="clear_overview"):
            st.rerun()

    if push_overview and overview_text.strip():
        parsed, error = validate_overview_json(overview_text.strip())
        if error:
            st.error(f"Validation failed: {error}")
        else:
            if isinstance(parsed, list):
                final = build_overview_json(parsed)
                st.info(f"Building overview from {len(parsed)} canvassers...")
            else:
                final = parsed
                st.info(f"Using provided overview ({final.get('total_records', '?')} records)")

            json_str = json.dumps(final, indent=2)

            with st.expander("Preview JSON", expanded=False):
                st.code(json_str[:2000] + ("..." if len(json_str) > 2000 else ""), language="json")

            with st.spinner("Pushing to GitHub..."):
                success, result = push_to_github(json_str, GITHUB_FILE,
                    f"Sync overview: {final.get('total_records', '?')} records, "
                    f"{final.get('report_summary', {}).get('contact_rate', '?')} contact rate")

            if success:
                st.success(f"✅ Pushed to GitHub (commit {result}). Railway will auto-deploy in ~30 seconds.")
                st.balloons()
            else:
                st.error(f"❌ Push failed: {result}")

    elif push_overview:
        st.warning("Paste JSON data first.")

# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: DETAIL SYNC
# ═══════════════════════════════════════════════════════════════════════════
with tab_detail:
    st.markdown("### How It Works")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("""
        <div class="step-card">
            <h4>Step 1: Open Canvasser</h4>
            <p>Click a canvasser name in the SmartVAN Activity Report to open
            their individual detail page.</p>
            <code>Door-by-door data</code>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown("""
        <div class="step-card">
            <h4>Step 2: Scrape Detail</h4>
            <p>Click the <strong>Scrape Detail</strong> bookmarklet. It grabs every
            contact row — VanID, address, result, timestamp.</p>
            <code>Handles pagination</code>
        </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown("""
        <div class="step-card">
            <h4>Step 3: Paste &amp; Push</h4>
            <p>Paste below and push. Unlocks <strong>time analysis</strong>,
            <strong>walking map</strong>, and <strong>fraud detection</strong>
            on the main dashboard.</p>
            <code>Powers integrity engine</code>
        </div>
        """, unsafe_allow_html=True)

    # Detail bookmarklet
    st.markdown("### Bookmarklet")
    st.markdown(f"""
    <div class="bookmarklet-box">
        <a href='{DETAIL_BOOKMARKLET_JS}' style="
            display: inline-block; padding: 12px 28px;
            background: #388bfd; color: #fff; font-weight: bold;
            border-radius: 8px; text-decoration: none; font-size: 1rem;
        ">🔍 Scrape Detail</a>
        <p style="color:#8b949e; margin-top:0.75rem; font-size:0.85rem;">
            Drag to your bookmarks bar. Click on any canvasser's detail report page in SmartVAN.
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="background:#161b22; border:1px solid #30363d; border-radius:8px; padding:1rem 1.5rem; margin:1rem 0;">
        <strong style="color:#58a6ff;">Multi-page detail reports:</strong><br>
        <span style="color:#c9d1d9;">
        Same as overview — click bookmarklet on each page, <strong>Cancel</strong> to accumulate,
        <strong>OK</strong> on the last page to copy all contacts.
        </span>
    </div>
    """, unsafe_allow_html=True)

    # Paste area for detail
    st.markdown("### Sync Detail Data")

    detail_text = st.text_area(
        "Paste canvasser detail JSON here",
        height=200,
        placeholder='{"canvasser": "Last, First", "list_name": "List XXXXX-XXXXX", "contacts": [...]}',
        key="detail_paste"
    )

    col_push_d, col_clear_d = st.columns([1, 4])
    with col_push_d:
        push_detail = st.button("🚀 Push Detail", type="primary", key="push_detail")
    with col_clear_d:
        if st.button("Clear", key="clear_detail"):
            st.rerun()

    if push_detail and detail_text.strip():
        parsed, error = validate_detail_json(detail_text.strip())
        if error:
            st.error(f"Validation failed: {error}")
        else:
            # Build detail JSON
            if isinstance(parsed, list):
                # Raw contacts array — need canvasser name and list
                if parsed and parsed[0].get("list_name"):
                    list_name = parsed[0]["list_name"]
                else:
                    list_name = "Unknown"

                canvasser_name = st.text_input(
                    "Canvasser name (auto-detected from bookmarklet if available)",
                    value="",
                    key="canvasser_name_input"
                )
                if not canvasser_name:
                    st.warning("Enter the canvasser name above to continue.")
                    st.stop()

                final = build_detail_json(parsed, canvasser_name, list_name)
            else:
                final = parsed
                if "contacts" not in final:
                    st.error("Missing 'contacts' array in detail data")
                    st.stop()
                canvasser_name = final.get("canvasser", "Unknown")
                list_name = final.get("list_name", "Unknown")
                # Ensure metadata
                if "scraped_at" not in final:
                    final["scraped_at"] = datetime.utcnow().isoformat() + "Z"
                if "total_contacts" not in final:
                    final["total_contacts"] = len(final["contacts"])

            # Build file path: details/{list_name}.json matching load_detail_data()
            safe_name = list_name.replace(" ", "_").replace("/", "_")
            detail_file_path = f"details/{safe_name}.json"

            st.info(f"**{canvasser_name}** — {len(final['contacts'])} contacts → `{detail_file_path}`")

            with st.expander("Preview contacts", expanded=False):
                for i, c in enumerate(final["contacts"][:10]):
                    st.text(f"  {c.get('date_canvassed','')} | {c.get('address','')} | {c.get('contact_result','')}")
                if len(final["contacts"]) > 10:
                    st.text(f"  ... and {len(final['contacts']) - 10} more")

            json_str = json.dumps(final, indent=2)

            with st.spinner("Pushing detail to GitHub..."):
                success, result = push_to_github(json_str, detail_file_path,
                    f"Sync detail: {canvasser_name}, {len(final['contacts'])} contacts")

            if success:
                st.success(f"✅ Detail pushed (commit {result}). Time analysis, walking map, and fraud detection now available for {canvasser_name}.")
                st.balloons()
            else:
                st.error(f"❌ Push failed: {result}")

    elif push_detail:
        st.warning("Paste detail JSON data first.")

# ── Footer ───────────────────────────────────────────────────────────────
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
st.markdown("""
<div class="footer">
    Civic Operations Group (NJ) — VAN Sync powered by GitHub API + Railway Auto-Deploy
</div>
""", unsafe_allow_html=True)
