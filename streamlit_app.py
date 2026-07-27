import streamlit as st
import pandas as pd
import datetime
import uuid
import gspread
from google.oauth2.service_account import Credentials
import json

# --- SETTINGS & PAGE CONFIG ---
st.set_page_config(page_title="Delta Plants Task Tracker", page_icon="📋", layout="wide")

# --- SESSION STATE & LOGIN LOGIC ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.department = ""

if not st.session_state.logged_in:
    st.title("🔐 Department Login")
    st.write("Please select your department and enter the password to access your secure workspace.")
    
    with st.form("login_form"):
        dept_choice = st.selectbox("Department", ["Maintenance", "Production"])
        pwd_input = st.text_input("Password", type="password")
        login_btn = st.form_submit_button("Login")
        
        if login_btn:
            if dept_choice == "Maintenance" and pwd_input == "main":
                st.session_state.logged_in = True
                st.session_state.department = "Maintenance"
                st.rerun()
            elif dept_choice == "Production" and pwd_input == "prod":
                st.session_state.logged_in = True
                st.session_state.department = "Production"
                st.rerun()
            else:
                st.error("Incorrect password. Please try again.")
    
    # Stop the rest of the script from running until logged in
    st.stop()


# --- GOOGLE SHEETS CONFIGURATION ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1brbbJmWgFCSp70X0yKQo2QYTUrNtd6bNKwIpfM-su5c/edit?usp=sharing"

# Authenticate securely using Streamlit Secrets
scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
try:
    creds_dict = json.loads(st.secrets["gcp_service_account_json"])
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_url(SHEET_URL)
    worksheet = sh.sheet1
except Exception as e:
    st.error(f"Authentication failed. Check your Streamlit Secrets. Error: {e}")
    st.stop()

st.title(f"📋 Delta Plants {st.session_state.department} Task Tracker")

# --- HELPER FUNCTIONS ---
def get_status_bulb(due_date):
    if pd.isna(due_date) or due_date == "":
        return ""
    if isinstance(due_date, str):
        try:
            due_date = datetime.datetime.strptime(due_date, "%Y-%m-%d").date()
        except ValueError:
            return ""
            
    today = datetime.date.today()
    delta = (due_date - today).days
    
    if delta < 0:
        return "🔴 Overdue"
    elif 0 <= delta <= 3:
        return "🟠 Near Due"
    else:
        return "🟢 Far Due"

def ensure_columns(df):
    required_cols = ['ID', 'Department', 'Task', 'Task Issuer', 'Plant', 'Sub-plant', 'Task Owner', 'Due Date', 
                     'Category', 'Impact', 'Status', 'State', 'Completion Notes', 'Release Date']
    for col in required_cols:
        if col not in df.columns:
            # If Department column is missing from old data, default it to Maintenance
            if col == 'Department':
                df[col] = 'Maintenance'
            else:
                df[col] = ""
            
    df['State'] = df['State'].replace("", "Active")
    df['ID'] = df['ID'].apply(lambda x: f"T-{str(uuid.uuid4())[:6].upper()}" if x == "" else x)
    return df

def load_all_data():
    """Loads ALL data from the sheet (needed for saving without overwriting other departments)"""
    try:
        data = worksheet.get_all_records()
        if not data:
            return pd.DataFrame(columns=['ID', 'Department', 'Task', 'Task Issuer', 'Plant', 'Sub-plant', 'Task Owner', 'Due Date', 
                                         'Category', 'Impact', 'Status', 'State', 'Completion Notes', 'Release Date'])
        
        df = pd.DataFrame(data)
        df = ensure_columns(df)
        df['Due Date'] = df['Due Date'].astype(str)
        
        mask = df['State'] == 'Active'
        if not df[mask].empty:
            df.loc[mask, 'Status'] = df.loc[mask, 'Due Date'].apply(get_status_bulb)
        return df
    except Exception as e:
        st.error(f"Error loading Google Sheets data: {e}")
        return pd.DataFrame()

def load_dept_data():
    """Loads only the data for the currently logged-in department"""
    df = load_all_data()
    if not df.empty:
        return df[df['Department'] == st.session_state.department].copy()
    return df

def save_data(df):
    """Writes data instantly back to Google Sheets."""
    try:
        clean_df = df.fillna("").astype(str)
        data_to_upload = [clean_df.columns.values.tolist()] + clean_df.values.tolist()
        worksheet.clear()
        worksheet.update(values=data_to_upload)
    except Exception as e:
        st.error(f"Failed to save data to Google Sheets: {e}")

# --- MAIN APP EXECUTION ---
# Pull fresh department data on every interaction
df = load_dept_data()

with st.sidebar:
    st.header("👤 User Profile")
    st.write(f"Logged in as: **{st.session_state.department}**")
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.department = ""
        st.rerun()
        
    st.divider()
    st.header("🔄 Cloud Sync")
    st.write("Data is synced directly to Google Sheets.")
    if st.button("Refresh Data Now"):
        st.rerun()

# --- MAIN TABS ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📝 Active Tasks", "📈 Track Tasks", "🛠️ Task Execution", "🔒 Manager Release", "📜 History"])

# ==========================================
# TAB 1: ACTIVE TASKS (LIST FIRST, THEN ADD)
# ==========================================
with tab1:
    st.subheader("📊 Active Tasks List")
    active_df = df[df['State'] == 'Active'].copy()
    
    # SLICERS / FILTERS
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    search_query = col_f1.text_input("🔍 Search Task Description")
    plant_filter = col_f2.multiselect("Filter by Plant", options=["EP", "PC"])
    owner_filter = col_f3.multiselect("Filter by Owner", options=["Saad Gad Alla", "Hamed Nassar"])
    issuer_filter = col_f4.text_input("Filter by Issuer")

    # Apply filters
    filtered_df = active_df.copy()
    if search_query:
        filtered_df = filtered_df[filtered_df['Task'].str.contains(search_query, case=False, na=False)]
    if plant_filter:
        pattern = '|'.join(plant_filter)
        filtered_df = filtered_df[filtered_df['Plant'].str.contains(pattern, case=False, na=False)]
    if owner_filter:
        pattern = '|'.join(owner_filter)
        filtered_df = filtered_df[filtered_df['Task Owner'].str.contains(pattern, case=False, na=False)]
    if issuer_filter:
        filtered_df = filtered_df[filtered_df['Task Issuer'].str.contains(issuer_filter, case=False, na=False)]

    if filtered_df.empty:
        st.info("No active tasks match your filters.")
    else:
        # Hide Department column from the UI to keep it clean
        st.dataframe(filtered_df.drop(columns=['State', 'Completion Notes', 'Release Date', 'Department']), use_container_width=True, hide_index=True)

    st.divider()

    # ADD NEW TASK SECTION
    st.subheader("➕ Add a New Task")
    with st.form("task_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            task_name = st.text_input("Task Description", placeholder="e.g., Replace extruder bearings")
            task_issuer = st.text_input("Task Issuer", value="Mohamed Alsayed Morgan")
            plants = st.multiselect("Plant", options=["EP", "PC"])
            sub_plants = st.multiselect("Sub-plant", options=["Processing", "Packaging"])
            task_owners = st.multiselect("Task Owner(s)", options=["Saad Gad Alla", "Hamed Nassar"])
            
        with col2:
            due_date = st.date_input("Due Date", value=datetime.date.today())
            category = st.radio("Category", options=["Planned", "Unplanned"], horizontal=True)
            impact = st.multiselect("Impact", options=["Quality", "Safety", "Reliability"])
            
        submit_button = st.form_submit_button("Save Task to Sheet")
        
        if submit_button:
            if not task_name.strip() or not task_issuer.strip() or not plants or not sub_plants or not task_owners or not impact:
                st.warning("Please fill out all required fields before saving.")
            else:
                new_task = pd.DataFrame({
                    'ID': [f"T-{str(uuid.uuid4())[:6].upper()}"],
                    'Department': [st.session_state.department],
                    'Task': [task_name],
                    'Task Issuer': [task_issuer],
                    'Plant': [", ".join(plants)],
                    'Sub-plant': [", ".join(sub_plants)],
                    'Task Owner': [", ".join(task_owners)],
                    'Due Date': [str(due_date)],
                    'Category': [category],
                    'Impact': [", ".join(impact)],
                    'Status': [get_status_bulb(due_date)],
                    'State': ['Active'],
                    'Completion Notes': [""],
                    'Release Date': [""]
                })
                
                # Fetch ALL latest data (both departments) before appending so we don't overwrite the other dept
                latest_all_df = load_all_data()
                updated_all_df = pd.concat([latest_all_df, new_task], ignore_index=True)
                save_data(updated_all_df)
                st.success(f"Task added successfully to {st.session_state.department} tracker!")
                st.rerun()

# ==========================================
# TAB 2: TRACK TASKS
# ==========================================
with tab2:
    st.subheader("📈 Task Tracking & Metrics")
    
    expanded_df = df.copy()
    expanded_df['Task Owner'] = expanded_df['Task Owner'].fillna("").str.split(', ')
    expanded_df = expanded_df.explode('Task Owner')
    expanded_df['Task Owner'] = expanded_df['Task Owner'].str.strip()
    expanded_df = expanded_df[expanded_df['Task Owner'] != ""]

    active_counts = expanded_df[expanded_df['State'] == 'Active']['Task Owner'].value_counts().reset_index()
    active_counts.columns = ['Task Owner', 'Active Tasks']
    
    closed_counts = expanded_df[expanded_df['State'] == 'Released']['Task Owner'].value_counts().reset_index()
    closed_counts.columns = ['Task Owner', 'Closed Tasks']
    
    metrics_df = pd.merge(active_counts, closed_counts, on='Task Owner', how='outer').fillna(0)
    if not metrics_df.empty:
        metrics_df['Active Tasks'] = metrics_df['Active Tasks'].astype(int)
        metrics_df['Closed Tasks'] = metrics_df['Closed Tasks'].astype(int)
    
    col_m1, col_m2 = st.columns([1, 2])
    with col_m1:
        st.markdown("**Tasks per Owner**")
        if metrics_df.empty:
            st.info("No data to calculate metrics.")
        else:
            st.dataframe(metrics_df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("📅 Active Tasks Sorted by Nearest Due Date")
    
    active_tasks = df[df['State'] == 'Active'].copy()
    
    if active_tasks.empty:
        st.info("No active tasks to display.")
    else:
        active_tasks['Sort Date'] = pd.to_datetime(active_tasks['Due Date'], errors='coerce')
        active_tasks = active_tasks.sort_values(by='Sort Date', ascending=True).drop(columns=['Sort Date'])
        
        st.dataframe(
            active_tasks.drop(columns=['State', 'Completion Notes', 'Release Date', 'Department']), 
            use_container_width=True, 
            hide_index=True
        )

# ==========================================
# TAB 3: TASK EXECUTION (Hamed / Saad)
# ==========================================
with tab3:
    st.subheader("🛠️ Task Execution")
    st.write("Task owners: Fill out completion notes to submit the task for managerial confirmation.")
    
    active_df = df[df['State'] == 'Active']
    
    if active_df.empty:
        st.info("No active tasks available to execute.")
    else:
        with st.form("execution_form", clear_on_submit=True):
            task_options = active_df['ID'] + " - " + active_df['Task']
            selected_task_string = st.selectbox("Select Task to Complete", options=task_options)
            completion_notes = st.text_area("Completion Notes", placeholder="Detail operational changes made...")
            
            submit_execution_button = st.form_submit_button("Submit for Confirmation")
            
            if submit_execution_button:
                if not completion_notes.strip():
                    st.warning("Please provide completion notes before submitting.")
                else:
                    selected_id = selected_task_string.split(" - ")[0]
                    # Must load ALL data to safely update the row without losing the other department
                    latest_all_df = load_all_data()
                    
                    if selected_id in latest_all_df['ID'].values:
                        idx = latest_all_df.index[latest_all_df['ID'] == selected_id].tolist()[0]
                        
                        latest_all_df.at[idx, 'State'] = 'Pending Confirmation'
                        latest_all_df.at[idx, 'Completion Notes'] = completion_notes
                        latest_all_df.at[idx, 'Status'] = "⏳ Pending"
                        
                        save_data(latest_all_df)
                        st.success(f"Task {selected_id} submitted for confirmation!")
                        st.rerun()
                    else:
                        st.error("Task ID not found.")

# ==========================================
# TAB 4: MANAGER RELEASE
# ==========================================
with tab4:
    st.subheader("🔒 Manager Release")
    st.write("Review tasks pending confirmation and authorize release to history.")
    
    pending_df = df[df['State'] == 'Pending Confirmation']
    
    if pending_df.empty:
        st.info("No tasks are currently pending confirmation.")
    else:
        st.dataframe(pending_df[['ID', 'Task', 'Task Owner', 'Completion Notes']], use_container_width=True, hide_index=True)
        
        st.divider()
        with st.form("release_form", clear_on_submit=True):
            pending_task_options = pending_df['ID'] + " - " + pending_df['Task']
            selected_pending_task = st.selectbox("Select Task to Authorize", options=pending_task_options)
            
            manager_password = st.text_input("Manager Password", type="password")
            release_button = st.form_submit_button("Authorize & Release Task")
            
            if release_button:
                if manager_password == "Ff@111222333":
                    selected_id = selected_pending_task.split(" - ")[0]
                    
                    latest_all_df = load_all_data()
                    
                    if selected_id in latest_all_df['ID'].values:
                        idx = latest_all_df.index[latest_all_df['ID'] == selected_id].tolist()[0]
                        
                        latest_all_df.at[idx, 'State'] = 'Released'
                        latest_all_df.at[idx, 'Release Date'] = str(datetime.date.today())
                        latest_all_df.at[idx, 'Status'] = "✅ Completed"
                        
                        save_data(latest_all_df)
                        st.success(f"Task {selected_id} successfully released to history!")
                        st.rerun()
                    else:
                        st.error("Task ID not found.")
                else:
                    st.error("Incorrect password. Release denied.")

# ==========================================
# TAB 5: HISTORY
# ==========================================
with tab5:
    st.subheader("📜 Task History")
    history_df = df[df['State'] == 'Released']
    
    if history_df.empty:
        st.info("No tasks have been released to history yet.")
    else:
        display_history = history_df.drop(columns=['State', 'Department'])
        st.dataframe(display_history, use_container_width=True, hide_index=True)
