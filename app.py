import streamlit as st
import pandas as pd
from datetime import datetime
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

# --- 1. 頁面基本設定 ---
st.set_page_config(page_title="馬尼通訊職責系統", page_icon="📱", layout="centered")

# --- 2. 系統全域設定 ---
SYSTEM_VERSION = "v1.5.0 (連續回報優化版)"
UPDATE_LOG = """
- **介面**: 「今日已回報紀錄」移至頁面最頂部，方便即時確認
- **優化**: 送出回報後自動清空欄位並更新紀錄，可立即執行下一項任務
- **功能**: 維持雲端資料庫連線與 Google Drive 圖片上傳
"""
COPYRIGHT_TEXT = "Ⓒ馬尼通訊 門市每日職責系統"
SHEET_NAME = "馬尼通訊即時回報系統_DB"

# ⚠️⚠️⚠️ 請確認您的 Google Drive 資料夾 ID 是否正確 ⚠️⚠️⚠️
IMAGE_FOLDER_ID = "您的資料夾ID請貼在這裡" 

# --- 3. 連線設定 ---
@st.cache_resource
def get_creds():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
        except FileNotFoundError:
            st.error("❌ 錯誤：找不到金鑰！")
            return None
    return creds

def init_sheet_client():
    creds = get_creds()
    if creds:
        return gspread.authorize(creds)
    return None

def init_drive_service():
    creds = get_creds()
    if creds:
        return build('drive', 'v3', credentials=creds)
    return None

# --- 4. Google Drive 上傳函式 ---
def upload_image_to_drive(file_obj, filename):
    drive_service = init_drive_service()
    if not drive_service:
        return "上傳失敗_無權限"
    
    try:
        file_metadata = {'name': filename, 'parents': [IMAGE_FOLDER_ID]}
        media = MediaIoBaseUpload(file_obj, mimetype='image/jpeg')
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()
        return file.get('webViewLink')
    except Exception as e:
        st.error(f"圖片上傳失敗: {e}")
        return "上傳失敗"

# --- 5. 資料庫操作 ---
# 注意：這裡不快取資料 (remove cache)，確保每次重整都能抓到最新的一筆
def load_data():
    client = init_sheet_client()
    if client:
        try:
            sheet = client.open(SHEET_NAME).sheet1
            data = sheet.get_all_records()
            return pd.DataFrame(data)
        except Exception as e:
            # st.error(f"讀取資料庫失敗: {e}") # 暫時隱藏錯誤以免干擾
            return pd.DataFrame()
    return pd.DataFrame()

def save_to_sheet(data_list):
    client = init_sheet_client()
    if client:
        sheet = client.open(SHEET_NAME).sheet1
        sheet.append_row(data_list)

# --- 6. 門市與任務資料 ---
users_db = {
    "文賢店": {"password": "111", "role": "User"},
    "東門店": {"password": "222", "role": "User"},
    "小西門店": {"password": "333", "role": "User"},
    "永康店": {"password": "444", "role": "User"},
    "歸仁店": {"password": "555", "role": "User"},
    "安中店": {"password": "666", "role": "User"},
    "鹽行店": {"password": "777", "role": "User"},
    "五甲店": {"password": "888", "role": "User"},
    "總管理處": {"password": "8888", "role": "Admin"}
}

task_definitions = {
    "開店-儀容自檢": {"desc": "請確認：1. 穿著制服且整潔 2. 配戴識別證 3. 頭髮儀容整齊。", "photo_required": True},
    "開店-環境清掃": {"desc": "請執行：1. 地板掃拖 2. 展示櫃擦拭 3. 櫃台桌面整理 4. 門口玻璃清潔。", "photo_required": True},
    "營業-零用金確認": {"desc": "請點算收銀機內零用金是否與報表金額相符，如有差異請立即回報。", "photo_required": False},
    "營業-隨機盤點庫存": {"desc": "請隨機抽選 3-5 樣高單價商品或熱銷配件進行實物盤點。", "photo_required": False},
    "閉店-庫存表上傳": {"desc": "請確認本日進銷存報表已結算，並將庫存表匯出上傳。", "photo_required": False}
}

# --- 7. 輔助函式 ---
def show_footer():
    st.markdown("---")
    st.markdown(f"<div style='text-align: center; color: gray; font-size: 12px;'>{COPYRIGHT_TEXT} | {SYSTEM_VERSION}</div>", unsafe_allow_html=True)

# --- 8. 登入畫面 ---
def login():
    st.markdown("## 👋 馬尼通訊即時回報")
    st.info("請選擇門市並輸入密碼")
    
    with st.form("login_form"):
        store_list = [""] + list(users_db.keys())
        selected_store = st.selectbox("請選擇門市", store_list)
        password = st.text_input("輸入密碼", type="password")
        submit = st.form_submit_button("登入系統")
        
        if submit:
            if selected_store == "":
                st.error("⚠️ 請選擇一個門市")
            elif selected_store in users_db and users_db[selected_store]["password"] == password:
                st.session_state['logged_in'] = True
                st.session_state['user_store'] = selected_store
                st.session_state['user_role'] = users_db[selected_store]['role']
                st.success(f"{selected_store} 登入成功！")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("❌ 密碼錯誤，請重新輸入")
    
    with st.expander(f"ℹ️ 系統公告 ({SYSTEM_VERSION})", expanded=False):
        st.markdown(UPDATE_LOG)
    show_footer()

# --- 9. 員工回報畫面 ---
def employee_page():
    store_name = st.session_state['user_store']
    st.title(f"📝 {store_name}")
    st.caption(f"目前時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # 【改動 1】將「本日已回報紀錄」移到最頂部，並自動讀取最新資料
    with st.expander("📋 點此查看「本日已回報紀錄」", expanded=True):
        # 這裡會從 Google Sheet 撈取最新資料
        df = load_data() 
        if not df.empty and '日期' in df.columns and '門市' in df.columns:
            today = datetime.now().strftime("%Y-%m-%d")
            # 篩選 本日 & 本門市
            my_records = df[ (df['門市'].astype(str) == store_name) & (df['日期'].astype(str) == today) ]
            
            if not my_records.empty:
                # 只顯示重點欄位，讓畫面乾淨點
                display_cols = ['時間', '任務', '說明', '檢核狀態']
                # 如果欄位有缺，就顯示所有欄位
                final_cols = [c for c in display_cols if c in my_records.columns]
                if not final_cols: final_cols = my_records.columns
                
                st.dataframe(my_records[final_cols], use_container_width=True, hide_index=True)
            else:
                st.info("尚無今日紀錄，請開始執行任務。")
        else:
            st.info("資料讀取中或尚無紀錄...")

    st.markdown("---")

    # 【回報區塊】
    st.subheader("🚀 執行任務回報")

    task_name = st.selectbox("📌 選擇任務項目", list(task_definitions.keys()))
    task_info = task_definitions[task_name]

    st.info(f"💡 **執行重點**：\n{task_info['desc']}")

    if task_info['photo_required']:
        st.warning("⚠️ **注意：此任務必須拍攝現場照片才能送出！**")
    else:
        st.success("ℹ️ 此任務不強制拍照")

    with st.form("report_form", clear_on_submit=True): # clear_on_submit 雖然會清空，但我們用 rerun 會更徹底
        note = st.text_area("備註說明 (選填)", placeholder="如有異常請在此說明...")
        st.markdown("📸 **現場拍照**")
        img_file = st.camera_input("點擊拍照", label_visibility="collapsed")
        
        submit_report = st.form_submit_button("✅ 完成任務並回報", use_container_width=True)

        if submit_report:
            if task_info['photo_required'] and img_file is None:
                st.error("⛔ 錯誤：本任務規定必須「拍攝現場照片」才能回報！")
            else:
                # 1. 上傳圖片
                drive_link = "無照片"
                if img_file:
                    with st.spinner("☁️ 正在上傳照片至雲端..."):
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"{timestamp}_{store_name}_{task_name}.jpg"
                        drive_link = upload_image_to_drive(img_file, filename)
                
                # 2. 寫入 Sheet
                current_time = datetime.now()
                row_data = [
                    current_time.strftime("%Y-%m-%d"),
                    current_time.strftime("%H:%M:%S"),
                    store_name,
                    task_name,
                    note,
                    drive_link,
                    "未審核"
                ]
                
                with st.spinner("正在寫入資料庫..."):
                    save_to_sheet(row_data)
                
                st.success("🎉 回報成功！資料已更新。")
                time.sleep(1) # 讓成功訊息顯示 1 秒
                st.rerun()    # 【關鍵】重新整理頁面：清空表單、更新上方紀錄、維持登入

    if st.button("登出系統"):
        st.session_state['logged_in'] = False
        st.rerun()     
    show_footer()

# --- 10. 管理者畫面 ---
def admin_page():
    st.sidebar.title("🔧 管理後台")
    st.sidebar.write(f"登入身分: {st.session_state['user_store']}")
    
    page = st.sidebar.radio("功能切換", ["即時戰情室", "歷史資料查詢"])
    df = load_data()

    if page == "即時戰情室":
        st.title("📊 營運戰情室")
        if not df.empty:
            col1, col2, col3 = st.columns(3)
            today = datetime.now().strftime("%Y-%m-%d")
            today_data = df[df['日期'].astype(str) == today]
            
            col1.metric("今日總回報數", len(today_data))
            col2.metric("異常備註", len(today_data[today_data['說明'] != ""]))
            col3.metric("活躍門市", today_data['門市'].nunique())
            
            st.markdown("### 📋 今日最新回報")
            st.dataframe(today_data, use_container_width=True)
        else:
            st.info("目前尚無資料")

    elif page == "歷史資料查詢":
        st.title("🗂️ 歷史資料查詢")
        all_stores = ["全部"] + list(users_db.keys())
        filter_store = st.selectbox("篩選門市", all_stores)
        
        if not df.empty:
            if filter_store != "全部":
                show_df = df[df['門市'] == filter_store]
            else:
                show_df = df
            st.dataframe(show_df, use_container_width=True)
        else:
            st.info("目前尚無資料")

    st.sidebar.markdown("---")
    if st.sidebar.button("登出"):
        st.session_state['logged_in'] = False
        st.rerun()
    show_footer()

# --- 11. 主程式 ---
def main():
    if 'logged_in' not in st.session_state or not st.session_state['logged_in']:
        login()
    else:
        role = st.session_state.get('user_role', 'User')
        if role == 'Admin':
            admin_page()
        else:
            employee_page()

if __name__ == "__main__":
    main()
