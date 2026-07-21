import streamlit as st
import pandas as pd
import datetime
import uuid
import gspread
from google.oauth2.service_account import Credentials
import json

# --- GOOGLE SHEETS CONFIGURATION ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1brbbJmWgFCSp70X0yKQo2QYTUrNtd6bNKwIpfM-su5c/edit?usp=sharing" # <-- UPDATE THIS

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

# --- SETTINGS & PAGE CONFIG ---
st.set_page_config(page_title="Delta Plants Task Tracker", page_icon="📋", layout="wide")
st.title("📋 Delta Plants Maintenance Task Tracker")

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
    required_cols = ['ID', 'Task', 'Plant', 'Sub-plant', 'Task Owner', 'Due Date', 
                     'Category', 'Impact', 'Status', 'State', 'Completion Notes', 'Release Date']
    for col in required_cols:
        if col not in df.columns:
            df[col] = ""
            
    df['State'] = df['State'].replace("", "Active")
    df['ID'] = df['ID'].apply(lambda x: f"T-{str(uuid.uuid4())[:6].upper()}" if x == "" else x)
    return df

def load_data():
    try:
        data = worksheet.get_all_records()
        if not data:
            return pd.DataFrame(columns=['ID', 'Task', 'Plant', 'Sub-plant', 'Task Owner', 'Due Date', 
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

def save_data(df):
    try:
        clean_df = df.fillna("").astype(str)
        data_to_upload = [clean_df.columns.values.tolist()] + clean_df.values.tolist()
        worksheet.clear()
        worksheet.update(values=data_to_upload)
    except Exception as e:
        st.error(f"Failed to save data to Google Sheets: {e}")

df = load_data()

with st.sidebar:
    st.header("🔄 Cloud Sync")
    st.write("Data is synced directly to Google Sheets.")
    if st.button("Refresh Data Now"):
        st.rerun()

tab1, tab2, tab3 = st.tabs(["📝 Active Tasks", "✅ Task Completion & Release", "📜 History"])

with tab1:
    st.subheader("➕ Add a New Task")
    with st.form("task_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            task_name = st.text_input("Task Description", placeholder="e.g., Replace extruder bearings")
            plants = st.multiselect("Plant", options=["EP", "PC"])
            sub_plants = st.multiselect("Sub-plant", options=["Processing", "Packaging"])
            task_owners = st.multiselect("Task Owner(s)", options=["Saad Gad Alla", "Hamed Nassar"])
            
        with col2:
            due_date = st.date_input("Due Date", value=datetime.date.today())
            category = st.radio("Category", options=["Planned", "Unplanned"], horizontal=True)
            impact = st.multiselect("Impact", options=["Quality", "Safety", "Reliability"])
            
        submit_button = st.form_submit_button("Save Task to Sheet")
        
        if submit_button:
            if not task_name.strip() or not plants or not sub_plants or not task_owners or not impact:
                st.warning("Please fill out all required fields before saving.")
            else:
                new_task = pd.DataFrame({
                    'ID': [f"T-{str(uuid.uuid4())[:6].upper()}"],
                    'Task': [task_name],
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
                
                latest_df = load_data()
                updated_df = pd.concat([latest_df, new_task], ignore_index=True)
                save_data(updated_df)
                st.success("Task added and synced to Google Sheets successfully!")
                st.rerun()

    st.divider()
    st.subheader("📊 Active Tasks List")
    active_df = df[df['State'] == 'Active']
    
    if active_df.empty:
        st.info("No active tasks found.")
    else:
        st.dataframe(active_df.drop(columns=['State', 'Completion Notes', 'Release Date']), use_container_width=True, hide_index=True)


with tab2:
    st.subheader("🔓 Release Completed Tasks")
    
    active_df = df[df['State'] == 'Active']
    
    if active_df.empty:
        st.info("No active tasks available to release.")
    else:
        with st.form("release_form", clear_on_submit=True):
            task_options = active_df['ID'] + " - " + active_df['Task']
            selected_task_string = st.selectbox("Select Task to Release", options=task_options)
            completion_notes = st.text_area("Owner Completion Notes", placeholder="Detail operational changes made...")
            
            st.divider()
            st.markdown("**Management Sign-off**")
            manager_password = st.text_input("Manager Password", type="password")
            
            release_button = st.form_submit_button("Authorize & Release Task")
            
            if release_button:
                if manager_password == "Ff@111222333":
                    selected_id = selected_task_string.split(" - ")[0]
                    latest_df = load_data()
                    
                    if selected_id in latest_df['ID'].values:
                        idx = latest_df.index[latest_df['ID'] == selected_id].tolist()[0]
                        
                        latest_df.at[idx, 'State'] = 'Released'
                        latest_df.at[idx, 'Completion Notes'] = completion_notes
                        latest_df.at[idx, 'Release Date'] = str(datetime.date.today())
                        latest_df.at[idx, 'Status'] = "✅ Completed"
                        
                        save_data(latest_df)
                        st.success(f"Task {selected_id} successfully released to history!")
                        st.rerun()
                    else:
                        st.error("Task ID not found. The sheet may have been updated elsewhere.")
                else:
                    st.error("Incorrect password. Release denied.")

with tab3:
    st.subheader("📜 Task History")
    history_df = df[df['State'] == 'Released']
    
    if history_df.empty:
        st.info("No tasks have been released to history yet.")
    else:
        display_history = history_df.drop(columns=['State'])
        st.dataframe(display_history, use_container_width=True, hide_index=True)
