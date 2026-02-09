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
SYSTEM_VERSION = "v2.3.1 (盤點拍照優化版)"
UPDATE_LOG = """
- **調整**: 「營業-隨機盤點庫存」改為強制拍照
- **說明**: 盤點需拍攝前一日庫存表單(含圈選、日期與簽名)
- **維持**: 零用金確認維持輸入金額模式
"""
COPYRIGHT_TEXT = "Ⓒ馬尼通訊 門市每日職責系統"
SHEET_NAME = "馬尼通訊即時回報系統_DB"

# ⚠️⚠️⚠️ 請填入【共用雲端硬碟】裡的資料夾 ID ⚠️⚠️⚠️
IMAGE_FOLDER_ID = "1ttjU6wyHl93w-v16cQhku2rnqQe3pgLI" 

# ⚠️⚠️⚠️ 請填入您的 Google Sheet 網址 ⚠️⚠️⚠️
SHEET_URL = "https://docs.google.com/spreadsheets/d/13kUwwjkiPo-C5kBCxpV0JRLtB_dD6zgTwcDLAZAOu90/edit"

# --- 3. 定義說明書內容 ---
USER_MANUAL = """
### 🚀 如何安裝到手機桌面？
**為了方便快速回報，請務必執行此動作：**
* **🍎 iPhone (iOS)**：
    1. 使用 Safari 開啟網址
    2. 點擊下方「分享按鈕」 (正方形箭頭)
    3. 選擇「加入主畫面」
* **🤖 Android**：
    1. 使用 Chrome 開啟網址
    2. 點擊右上角「三個點」選單
    3. 選擇「加到主畫面」或「安裝應用程式」

### 📝 員工回報流程
1. **登入**：選擇門市並輸入密碼。
2. **填寫**：
    * **選擇任務**：系統會自動切換顯示「拍照」或「輸入金額」欄位。
    * **輸入姓名**：請填寫執行人員全名 (視同盤簽)。
    * **拍照**：開店任務、隨機盤點需拍攝現場。
3. **送出**：點擊回報按鈕。

### ⚠️ 違規扣點規則
* **純扣分制**：一項不合格記 1 點違規 (單日上限 5 點)。
"""

# --- 4. 連線設定 ---
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

# --- 5. Google Drive 上傳函式 ---
def upload_file_to_drive(file_obj, filename, file_type="image"):
    drive_service = init_drive_service()
    if not drive_service:
        return "上傳失敗: 無權限"
    
    try:
        if file_type == "video":
            mimetype = 'video/mp4'
        else:
            mimetype = 'image/jpeg'

        file_metadata = {'name': filename, 'parents': [IMAGE_FOLDER_ID]}
        media = MediaIoBaseUpload(file_obj, mimetype=mimetype)
        
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()
        return file.get('webViewLink')
    except Exception as e:
        return f"上傳失敗: {str(e)}"

# --- 6. 資料庫操作 ---
def load_data():
    client = init_sheet_client()
    if client:
        try:
            sheet = client.open(SHEET_NAME).sheet1
            data = sheet.get_all_records()
            return pd.DataFrame(data)
        except Exception as e:
            return pd.DataFrame()
    return pd.DataFrame()

def save_to_sheet(data_list):
    client = init_sheet_client()
    if client:
        sheet = client.open(SHEET_NAME).sheet1
        sheet.append_row(data_list)

# --- 7. 門市與任務資料 (關鍵修改) ---
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

# 【修改說明】: 
# 1. 開店任務: photo (強制)
# 2. 零用金: none (純文字+金額)
# 3. 隨機盤點: photo (強制, 修改說明)
# 4. 庫存表上傳: none (純文字)
task_definitions = {
    "開店-儀容自檢": {
        "desc": "請確認：1. 穿著制服且整潔 2. 配戴識別證 3. 頭髮儀容整齊。", 
        "media_type": "photo", 
        "required": True
    },
    "開店-環境清掃": {
        "desc": "請執行：1. 地板掃拖 2. 展示櫃擦拭 3. 櫃台桌面整理 4. 門口玻璃清潔。", 
        "media_type": "photo", 
        "required": True
    },
    "營業-零用金確認": {
        "desc": "請確實點算收銀機內零用金，並輸入盤點金額與簽名。", 
        "media_type": "none", 
        "required": False
    },
    "營業-隨機盤點庫存": {
        "desc": "需要拍攝，拍下前一日庫存表單圈選所隨機盤點品項以及簽上日期與簽名。", 
        "media_type": "photo", # 👈 改為拍照
        "required": True       # 👈 改為強制
    },
    "閉店-庫存表上傳": {
        "desc": "請確認本日進銷存報表已結算，並將庫存表匯出上傳。", 
        "media_type": "none", 
        "required": False
    }
}

# --- 8. 輔助函式 ---
def show_footer():
    st.markdown("---")
    st.markdown(f"<div style='text-align: center; color: gray; font-size: 12px;'>{COPYRIGHT_TEXT} | {SYSTEM_VERSION}</div>", unsafe_allow_html=True)

# 積分計算
def calculate_scores_v2(df):
    if df.empty or '檢核狀態' not in df.columns or '日期' not in df.columns or '門市' not in df.columns:
        return pd.DataFrame()

    scores_list = []
    grouped = df.groupby(['日期', '門市'])
    for (date, store), group in grouped:
        mistakes = len(group[group['檢核狀態'] == '不合格'])
        daily_penalty = min(mistakes, 5)
        if daily_penalty > 0:
            scores_list.append({'門市': store, '單日違規點數': daily_penalty})
    
    scores_df = pd.DataFrame(scores_list)
    if not scores_df.empty:
        final_scores = scores_df.groupby('門市')['單日違規點數'].sum().reset_index(name='累積扣點(越少越好)')
        final_scores = final_scores.sort_values(by='累積扣點(越少越好)', ascending=True)
        return final_scores
    else:
        return pd.DataFrame(columns=['門市', '累積扣點(越少越好)'])

# --- 9. 登入畫面 ---
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
    
    with st.expander("📖 系統使用說明書 (點擊展開)", expanded=False):
        st.markdown(USER_MANUAL)

    with st.expander(f"ℹ️ 系統公告 ({SYSTEM_VERSION})", expanded=False):
        st.markdown(UPDATE_LOG)
    
    show_footer()

# --- 10. 員工回報畫面 ---
def employee_page():
    store_name = st.session_state['user_store']
    
    st.sidebar.title("功能選單")
    with st.sidebar.expander("📖 使用說明書", expanded=False):
        st.markdown(USER_MANUAL)
    
    if st.sidebar.button("登出系統"):
        st.session_state['logged_in'] = False
        st.rerun()

    st.title(f"📝 {store_name}")
    st.caption(f"目前時間: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    df = load_data()
    
    with st.expander("📋 點此查看「本日已回報紀錄」", expanded=True):
        if not df.empty and '日期' in df.columns and '門市' in df.columns:
            today = datetime.now().strftime("%Y-%m-%d")
            my_records = df[ (df['門市'].astype(str) == store_name) & (df['日期'].astype(str) == today) ]
            
            if not my_records.empty:
                display_cols = ['時間', '人員', '任務', '說明', '檢核狀態']
                final_cols = [c for c in display_cols if c in my_records.columns]
                st.dataframe(my_records[final_cols], use_container_width=True, hide_index=True)
            else:
                st.info("尚無今日紀錄，請開始執行任務。")
        else:
            if df.empty:
                st.warning("⚠️ 目前無資料，或 Google Sheet 連線異常。")
            else:
                st.error(f"❌ Google Sheet 格式錯誤！請確認已新增「人員」欄位。")

    st.markdown("---")
    st.subheader("🚀 執行任務回報")

    task_name = st.selectbox("📌 選擇任務項目", list(task_definitions.keys()))
    task_info = task_definitions[task_name]

    st.info(f"💡 **執行重點**：\n{task_info['desc']}")

    # 判斷任務設定
    media_required = task_info['required']
    media_type = task_info.get('media_type', 'none') # 預設 none

    # 根據是否需要拍照顯示不同提示
    if media_type != 'none':
        if media_required:
            st.warning("📷 **注意：此任務必須「拍照」才能送出！**")
        else:
            st.success("ℹ️ 此任務可選填拍照")
    else:
        st.success("ℹ️ 此任務為「純文字回報」，無需拍照")

    with st.form("report_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            # 這是共用的「人員盤簽」欄位
            reporter_name = st.text_input("👤 執行人員姓名 (盤簽)", placeholder="請輸入姓名")
        with col2:
            # 【新增】若是零用金確認，顯示金額輸入框
            cash_amount = None
            if task_name == "營業-零用金確認":
                cash_amount = st.number_input("💰 盤點金額", min_value=0, step=100)

        note = st.text_area("備註說明 (選填)", placeholder="如有異常請在此說明...")
        
        # 【核心修改】根據 media_type 決定是否顯示相機
        uploaded_file = None
        if media_type == 'photo':
            st.markdown("📷 **現場拍照**")
            uploaded_file = st.camera_input("點擊拍照", label_visibility="collapsed")
        elif media_type == 'video':
            # 目前邏輯沒有用到 video，但保留擴充性
            st.markdown("🎥 **上傳影片**")
            uploaded_file = st.file_uploader("選擇影片", type=['mp4', 'mov'])

        submit_report = st.form_submit_button("✅ 完成任務並回報", use_container_width=True)

        if submit_report:
            if not reporter_name.strip():
                st.error("⛔ 請填寫「執行人員姓名」以完成盤簽！")
            # 檢查強制拍照
            elif media_required and uploaded_file is None:
                st.error("⛔ 錯誤：本任務規定必須「拍照」！")
            else:
                drive_link = "無照片"
                if uploaded_file:
                    with st.spinner("☁️ 正在上傳照片至雲端..."):
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"{timestamp}_{store_name}_{reporter_name}_{task_name}.jpg"
                        drive_link = upload_file_to_drive(uploaded_file, filename, file_type='image')
                
                # 【資料整合】若有填寫金額，整合進「說明」欄位
                final_note = note
                if task_name == "營業-零用金確認":
                    final_note = f"盤點金額: {cash_amount} 元\n{note}"

                if "上傳失敗" in drive_link:
                    st.error(f"❌ {drive_link}")
                else:
                    current_time = datetime.now()
                    row_data = [
                        current_time.strftime("%Y-%m-%d"),
                        current_time.strftime("%H:%M:%S"),
                        store_name,
                        reporter_name,
                        task_name,
                        final_note, # 整合後的說明
                        drive_link,
                        "未審核"
                    ]
                    
                    with st.spinner("正在寫入資料庫..."):
                        save_to_sheet(row_data)
                    
                    st.success(f"🎉 {reporter_name} 回報成功！")
                    time.sleep(1)
                    st.rerun()
    
    show_footer()

# --- 11. 管理者畫面 ---
def admin_page():
    st.sidebar.title("🔧 管理後台")
    st.sidebar.write(f"登入身分: {st.session_state['user_store']}")
    
    if SHEET_URL.startswith("http"):
        st.sidebar.link_button("📑 前往 Google Sheet 審核", SHEET_URL)

    with st.sidebar.expander("📖 使用說明書", expanded=False):
        st.markdown(USER_MANUAL)

    page = st.sidebar.radio("功能切換", ["即時戰情室", "歷史資料查詢"])
    df = load_data()
    
    is_data_valid = not df.empty and '日期' in df.columns

    if page == "即時戰情室":
        st.title("📊 營運戰情室")
        if is_data_valid:
            col1, col2, col3 = st.columns(3)
            today = datetime.now().strftime("%Y-%m-%d")
            today_data = df[df['日期'].astype(str) == today]
            col1.metric("今日總回報數", len(today_data))
            
            if '說明' in df.columns:
                abnormal_count = len(today_data[today_data['說明'] != ""])
            else:
                abnormal_count = 0
            col2.metric("異常備註", abnormal_count)
            col3.metric("活躍門市", today_data['門市'].nunique())
            
            st.markdown("---")
            st.subheader("⚠️ 門市違規記點榜")
            st.info("💡 計分規則：一項不合格記 1 點違規 (單日上限 5 點)。點數越少表現越好。")
            
            score_df = calculate_scores_v2(df)
            if not score_df.empty:
                st.dataframe(score_df, use_container_width=True, hide_index=True)
            else:
                st.success("🎉 目前所有門市皆無違規紀錄！")

            st.markdown("---")
            st.markdown("### 📋 今日最新回報")
            st.dataframe(today_data, use_container_width=True)
        else:
            if df.empty:
                st.info("📭 目前尚無任何回報資料")
            else:
                st.error(f"❌ 格式錯誤！系統讀到的欄位是：\n{df.columns.tolist()}")

    elif page == "歷史資料查詢":
        st.title("🗂️ 歷史資料查詢")
        all_stores = ["全部"] + list(users_db.keys())
        filter_store = st.selectbox("篩選門市", all_stores)
        
        if is_data_valid:
            if filter_store != "全部":
                show_df = df[df['門市'] == filter_store]
            else:
                show_df = df
            st.dataframe(show_df, use_container_width=True)
        else:
            if df.empty:
                st.info("📭 目前尚無資料")
            else:
                st.error(f"❌ 格式錯誤！系統讀到的欄位是：\n{df.columns.tolist()}")

    st.sidebar.markdown("---")
    if st.sidebar.button("登出"):
        st.session_state['logged_in'] = False
        st.rerun()
    show_footer()

# --- 12. 主程式 ---
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
