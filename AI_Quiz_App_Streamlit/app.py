import streamlit as st
import json
import random
from PIL import Image
from google import genai
from google.genai.errors import APIError

# --- 配置區 ---
# ⚠️ 注意：請確保此處的金鑰是您有效的 Gemini API 金鑰
API_KEY = "AIzaSyCd214KXU0JCD_FRx1IEpCAiC9R39z7H1M" 
MODEL_NAME = "gemini-2.5-flash"

# 初始化 Gemini 客戶端
try:
    client = genai.Client(api_key=API_KEY)
except ValueError:
    st.error("❌ API 金鑰無效。請檢查程式碼中的 API_KEY 設定！")
    st.stop()

# ----------------------------------------------------
# A. 全局狀態初始化 (使用 st.session_state)
# ----------------------------------------------------

def initialize_session_state():
    """初始化 Streamlit Session State，用於儲存題目和錯題清單"""
    # 結構: { '科目名稱': { '清單名稱': { 'all': [題目清單], 'wrong': [錯題清單] } } }
    if 'SUBJECT_DATA' not in st.session_state:
        st.session_state.SUBJECT_DATA = {} 
    
    # 設定當前選中的科目和清單
    if 'CURRENT_SUBJECT' not in st.session_state:
        st.session_state.CURRENT_SUBJECT = None
    if 'CURRENT_LIST' not in st.session_state:
        st.session_state.CURRENT_LIST = None
    
    # 頁面導航和測驗狀態
    if 'page' not in st.session_state:
        st.session_state.page = "dashboard" 
    if 'quiz_mode' not in st.session_state:
        st.session_state.quiz_mode = 'quiz_all' 
    if 'current_quiz_index' not in st.session_state:
        st.session_state.current_quiz_index = 0 
    if 'current_quiz_list' not in st.session_state:
        st.session_state.current_quiz_list = [] 

initialize_session_state()

# ----------------------------------------------------
# B. 核心功能：Gemini 題目提取 (支持圖片和文字)
# ----------------------------------------------------

# 統一的 JSON 輸出結構 (用於圖片和文字提取)
RESPONSE_SCHEMA_QUIZ = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "完整的題目文字"},
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "四個選項的文字內容"
            },
            "correct_answer": {"type": "string", "description": "正確答案，例如 A, B, C 或 D"},
            "explanation": {"type": "string", "description": "題目中提供的詳細解析文字"}
        },
        "required": ["question", "options", "correct_answer", "explanation"]
    }
}

def call_gemini_extraction(contents, source_id):
    """通用函數：呼叫 Gemini 提取題目，並處理錯誤。"""
    try:
        # 根據輸入內容類型調整 Prompt
        if isinstance(contents[0], str) and contents[0].startswith("TEXT_INPUT:"):
            # 這是文字輸入，我們假設使用者已經提供了格式
            extraction_prompt = contents[0].replace("TEXT_INPUT:", "你是一位專業的教育 AI 助手。請根據以下多選題格式，將其轉換為 JSON 格式。")
        else:
            # 這是圖片輸入
            extraction_prompt = "你是一位專業的教育 AI 助手，專門從圖片中提取選擇題。請仔細分析這張圖片中的**所有獨立選擇題**。請確保你的輸出是一個包含所有提取出題目的 JSON 清單 (Array)，不要包含任何額外的文字或說明。"
        
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[extraction_prompt] + ([contents[1]] if len(contents) > 1 else []),
            config={
                "response_mime_type": "application/json",
                "response_schema": RESPONSE_SCHEMA_QUIZ
            }
        )
        
        quiz_list = json.loads(response.text)
        
        for quiz_data in quiz_list:
             quiz_data['source_image'] = source_id # 紀錄來源
        return quiz_list
        
    except APIError as e:
        st.error(f"API 呼叫錯誤 ({source_id}): 請檢查您的 API 金鑰或配額。")
        st.exception(e)
        return []
    except Exception as e:
        st.warning(f"處理來源 {source_id} 時發生錯誤。可能 AI 返回的 JSON 格式不正確。")
        st.exception(e)
        return []

# ----------------------------------------------------
# C. 網站分頁和邏輯
# ----------------------------------------------------

def get_current_quiz_lists():
    """返回當前選定科目和單元的題目和錯題清單"""
    sub = st.session_state.CURRENT_SUBJECT
    lst = st.session_state.CURRENT_LIST
    
    if sub and lst and lst in st.session_state.SUBJECT_DATA[sub]:
        data = st.session_state.SUBJECT_DATA[sub][lst]
        return data['all'], data['wrong']
    return [], []

def show_dashboard():
    """顯示主頁儀表板和統計數據"""
    st.title("📚 AI 智慧錯題本")
    st.header("🏠 儀表板")
    st.markdown("---")
    
    # 取得當前選定單元的題目數據
    CURRENT_ALL_QUIZZES, CURRENT_WRONG_QUIZZES = get_current_quiz_lists()
    total_quizzes = len(CURRENT_ALL_QUIZZES)
    total_wrong = len(CURRENT_WRONG_QUIZZES)

    # 狀態卡片
    col1, col2, col3 = st.columns(3)
    with col1:
        st.info(f"總題目數\n\n# {total_quizzes}", icon="📊")
    with col2:
        st.warning(f"待複習錯題\n\n# {total_wrong}", icon="❌")
    with col3:
        st.success(f"已掌握題數\n\n# {total_quizzes - total_wrong}", icon="✅")

    st.markdown("---")
    st.subheader("功能選單：")
    
    # 按鈕排版
    b_col1, b_col2, b_col3 = st.columns(3)

    with b_col1:
        if st.button("➕ 新增題目 (圖片/文字)", use_container_width=True, type="primary"):
            st.session_state.page = "add"
            st.rerun()

    with b_col2:
        if total_quizzes > 0 and st.button("📝 開始測驗所有題目", use_container_width=True):
            st.session_state.page = "quiz"
            st.session_state.quiz_mode = 'quiz_all'
            # 隨機打亂題目順序
            st.session_state.current_quiz_list = random.sample(CURRENT_ALL_QUIZZES, len(CURRENT_ALL_QUIZZES))
            st.session_state.current_quiz_index = 0
            st.rerun()
        elif total_quizzes == 0:
            st.button("📝 開始測驗所有題目", use_container_width=True, disabled=True)


    with b_col3:
        if total_wrong > 0 and st.button(f"🔁 複習錯題 ({total_wrong} 題)", use_container_width=True):
            st.session_state.page = "quiz"
            st.session_state.quiz_mode = 'review_wrong'
            # 隨機打亂錯題順序
            st.session_state.current_quiz_list = random.sample(CURRENT_WRONG_QUIZZES, len(CURRENT_WRONG_QUIZZES))
            st.session_state.current_quiz_index = 0
            st.rerun()
        else:
            st.button(f"🔁 複習錯題 (0 題)", use_container_width=True, disabled=True)
            
    # 顯示題目清單 (除錯用)
    with st.expander(f"🔍 查看當前單元 ({st.session_state.CURRENT_LIST}) 所有題目"):
        st.json(CURRENT_ALL_QUIZZES)
        
def show_add_quiz_page():
    """處理圖片上傳、文字輸入和題目提取頁面"""
    st.header("➕ 新增題目：圖片或文字輸入")
    
    CURRENT_ALL_QUIZZES, _ = get_current_quiz_lists()
    st.caption(f"當前單元 '{st.session_state.CURRENT_LIST}' 總題數：**{len(CURRENT_ALL_QUIZZES)}** 題")
    st.markdown("---")

    tab1, tab2 = st.tabs(["🖼️ 圖片上傳 (推薦)", "✍️ 文字輸入 (單題手動)"])

    # ----------------------------------------------------
    # TAB 1: 圖片上傳邏輯
    # ----------------------------------------------------
    with tab1:
        uploaded_files = st.file_uploader(
            "🖼️ 請選擇一或多個包含選擇題的圖片檔案上傳", 
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True
        )
        
        if uploaded_files:
            st.subheader(f"將處理 {len(uploaded_files)} 個檔案：")
            
            progress_bar = st.progress(0, text="開始處理圖片...")
            
            new_quizzes = []
            for i, file in enumerate(uploaded_files):
                progress_bar.progress((i + 1) / len(uploaded_files), text=f"正在分析圖片 {file.name}...")
                
                # 圖片提取
                img = Image.open(file)
                quizzes = call_gemini_extraction([f"IMAGE_INPUT: {file.name}", img], file.name)
                new_quizzes.extend(quizzes)
                
                if quizzes:
                    st.success(f"✅ 圖片 **{file.name}** 成功提取 **{len(quizzes)}** 道題目。")
                else:
                    st.warning(f"⚠️ 圖片 **{file.name}** 未提取到任何題目，請檢查圖片清晰度。")

            progress_bar.empty()

            if new_quizzes:
                CURRENT_ALL_QUIZZES.extend(new_quizzes)
                st.success(f"🎉 處理完成！總共新增 **{len(new_quizzes)}** 道題目。")
                st.caption(f"當前單元總題數：{len(CURRENT_ALL_QUIZZES)}")

    # ----------------------------------------------------
    # TAB 2: 文字輸入邏輯 (新增部分)
    # ----------------------------------------------------
    with tab2:
        st.markdown("##### 請依照以下格式，輸入單一或多道選擇題：")
        st.code("""
題目1: [題目內容]
選項A: [選項A內容]
選項B: [選項B內容]
選項C: [選項C內容]
選項D: [選項D內容]
答案: [A/B/C/D]
解析: [詳細解析內容]
---
題目2: [題目內容]
...
(題目間用 --- 分隔)
""")
        
        text_input = st.text_area(
            "請在這裡貼上或輸入題目內容",
            height=300,
            key="manual_quiz_input"
        )
        
        if st.button("📤 提交文字題目並提取", type="secondary"):
            if not text_input:
                st.warning("請先輸入題目內容。")
            else:
                with st.spinner("🧠 AI 正在分析您的文字內容..."):
                    # 文字提取
                    quizzes = call_gemini_extraction([f"TEXT_INPUT:\n{text_input}"], "Manual_Input")
                    
                    if quizzes:
                        CURRENT_ALL_QUIZZES.extend(quizzes)
                        st.success(f"🎉 文字內容成功提取 **{len(quizzes)}** 道題目。")
                        st.caption(f"當前單元總題數：{len(CURRENT_ALL_QUIZZES)}")
                        # 清空輸入框 (需要使用一個簡單的 trick 來清空 text_area)
                        st.session_state.manual_quiz_input = "" 
                        st.rerun() # 刷新頁面顯示清空後的輸入框
                    else:
                        st.error("⚠️ 無法從您輸入的文字中提取出結構化的題目。請檢查格式是否正確。")


    st.markdown("---")
    if st.button("⬅️ 返回儀表板"):
        st.session_state.page = "dashboard"
        st.rerun()


def show_quiz_page():
    """互動式測驗頁面 (通用於所有題目和錯題複習)"""
    
    # 取得當前選定單元的錯題清單 (用於增刪錯題紀錄)
    _, CURRENT_WRONG_QUIZZES = get_current_quiz_lists()
    
    quiz_list = st.session_state.current_quiz_list
    current_index = st.session_state.current_quiz_index
    total_quizzes = len(quiz_list)

    if current_index >= total_quizzes:
        st.header("🎉 測驗/複習結束！")
        st.subheader(f"本次共完成 {total_quizzes} 題。")
        st.markdown("---")
        st.session_state.current_quiz_index = 0
        if st.button("返回儀表板", type="primary"):
            st.session_state.page = "dashboard"
            st.rerun()
        return

    # 取得當前題目
    quiz = quiz_list[current_index]
    
    mode_text = "🎯 所有題目測驗" if st.session_state.quiz_mode == 'quiz_all' else "🧠 錯題複習模式"
    st.header(f"{mode_text} (第 {current_index + 1} / {total_quizzes} 題)")
    st.caption(f"來源：**{quiz['source_image']}**")
    st.markdown("---")

    # 顯示題目
    st.subheader("📝 題目內容：")
    st.markdown(f"**{quiz['question']}**")

    # 顯示選項 (使用 Streamlit 的 radio button)
    options_map = ["A", "B", "C", "D"]
    options_with_label = [f"{options_map[i]}. {text.lstrip('ABCD. ')}" for i, text in enumerate(quiz['options'])]
    
    # 儲存使用者選擇的答案
    selected_option = st.radio("請選擇答案：", options_with_label, key=f"user_answer_radio_{current_index}")
    
    # 提交和結果邏輯
    if st.button("✅ 提交答案", key=f"submit_button_{current_index}"):
        
        # 提取使用者選擇的字母 (從 "A. Option Text" 變成 "A")
        selected_letter = selected_option.split('.')[0]
        
        # 判斷結果
        correct_answer_letter = quiz['correct_answer'].upper().strip()
        
        # 顯示結果
        if selected_letter == correct_answer_letter:
            st.success("🎉 恭喜！答案正確！")
            
            # 如果是在複習錯題模式且答對了，將其從錯題清單中移除
            if st.session_state.quiz_mode == 'review_wrong':
                # 在 CURRENT_WRONG_QUIZZES 中移除
                for i, wrong_quiz in enumerate(CURRENT_WRONG_QUIZZES):
                    if wrong_quiz['question'] == quiz['question'] and wrong_quiz['source_image'] == quiz['source_image']:
                        del CURRENT_WRONG_QUIZZES[i]
                        st.toast("👏 該錯題已掌握，從錯題清單中移除。")
                        break
                        
        else:
            st.error(f"❌ 抱歉，答案錯誤。您選擇了 **{selected_letter}**。")
            
            # 如果是初次測驗，將其加入錯題清單 (只加一次)
            is_already_wrong = any(w['question'] == quiz['question'] for w in CURRENT_WRONG_QUIZZES)
            if st.session_state.quiz_mode == 'quiz_all' and not is_already_wrong:
                # 加入到當前清單的錯題區
                CURRENT_WRONG_QUIZZES.append(quiz)
                st.toast("😥 題目已加入錯題清單。")
            
        # 顯示詳解卡片
        with st.expander("📖 查看詳細解析", expanded=True):
            st.info(f"**✅ 正確答案：** {correct_answer_letter}")
            st.markdown("#### 完整解析：")
            st.markdown(quiz['explanation'])

        # 下一題按鈕 (放在提交結果後)
        st.markdown("---")
        if st.button("➡️ 下一題", type="primary"):
            st.session_state.current_quiz_index += 1
            st.rerun()
            
    # 返回儀表板
    if st.button("🏠 返回儀表板", key=f"back_to_dash_{current_index}"):
        st.session_state.page = "dashboard"
        st.rerun()

# ----------------------------------------------------
# D. 應用程式主入口
# ----------------------------------------------------

def main_app():
    # Streamlit 頁面配置
    st.set_page_config(layout="wide", page_title="AI 智慧錯題本")
    
    # ----------------------------------------------------
    # 左側邊欄：科目與清單管理
    # ----------------------------------------------------
    
    all_subjects = list(st.session_state.SUBJECT_DATA.keys())
    current_subject = st.session_state.CURRENT_SUBJECT
    
    st.sidebar.title("📚 AI 智慧錯題本")
    st.sidebar.header("📝 科目與清單管理")

    # --- 1. 科目管理 ---
    with st.sidebar.expander("🎓 管理科目/考試類型"):
        new_subject_name = st.text_input("輸入新科目名稱 (例如：期貨)", key="new_subject_name")
        if st.button("創建新科目", key="create_subject_btn"):
            if new_subject_name and new_subject_name not in st.session_state.SUBJECT_DATA:
                st.session_state.SUBJECT_DATA[new_subject_name] = {}
                st.success(f"科目 '{new_subject_name}' 創建成功！")
                st.session_state.CURRENT_SUBJECT = new_subject_name
                st.rerun()
            elif new_subject_name:
                st.error("科目名稱已存在！")

    # --- 2. 選擇科目 ---
    if not current_subject or current_subject not in all_subjects:
        selected_subject = st.sidebar.selectbox(
            "選擇要操作的科目",
            options=["請選擇"] + all_subjects,
            index=0,
            key="select_subject"
        )
        if selected_subject != "請選擇":
            st.session_state.CURRENT_SUBJECT = selected_subject
            st.rerun()
        else:
            st.warning("請先創建或選擇一個科目。")
            if st.session_state.page != "dashboard": st.session_state.page = "dashboard"
            show_dashboard() 
            return 

    st.sidebar.info(f"當前科目：**{current_subject}**")
    
    # --- 3. 清單/單元管理 ---
    subject_lists = list(st.session_state.SUBJECT_DATA[current_subject].keys())

    with st.sidebar.expander(f"📑 管理單元 ({current_subject})"):
        new_list_name = st.text_input("輸入新單元名稱 (例如：法規/實務)", key="new_list_name")
        if st.button("創建新單元", key="create_list_btn"):
            if new_list_name and new_list_name not in subject_lists:
                st.session_state.SUBJECT_DATA[current_subject][new_list_name] = {'all': [], 'wrong': []}
                st.success(f"單元 '{new_list_name}' 創建成功！")
                st.session_state.CURRENT_LIST = new_list_name
                st.rerun()
            elif new_list_name:
                st.error("單元名稱已存在！")

    # --- 4. 選擇清單 ---
    selected_list = st.sidebar.selectbox(
        "選擇要操作的單元",
        options=["請選擇"] + subject_lists,
        index=0 if st.session_state.CURRENT_LIST not in subject_lists else subject_lists.index(st.session_state.CURRENT_LIST) + 1
    )

    if selected_list != "請選擇":
        st.session_state.CURRENT_LIST = selected_list
        st.sidebar.success(f"當前單元：**{selected_list}**")
    else:
        st.warning("請創建或選擇一個單元，才能上傳題目。")
        if st.session_state.page != "dashboard": st.session_state.page = "dashboard"
        show_dashboard() 
        return 

    # ----------------------------------------------------
    # 主頁面導航
    # ----------------------------------------------------
    
    # 確保在選擇了科目和單元後，可以回到儀表板
    if st.sidebar.button("🏠 返回儀表板", key="sidebar_dash"):
         st.session_state.page = "dashboard"
         st.rerun()

    # 根據 session_state.page 變數顯示對應頁面
    if st.session_state.page == "dashboard":
        show_dashboard()
    elif st.session_state.page == "add":
        show_add_quiz_page()
    elif st.session_state.page == "quiz":
        show_quiz_page()

if __name__ == "__main__":
    main_app()
