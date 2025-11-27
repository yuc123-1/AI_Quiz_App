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
    """初始化 Streamlit Session State"""
    # 結構: { '科目': { '類別': { '單元': { 'all': [題目], 'wrong': [錯題] } } } }
    if 'SUBJECT_DATA' not in st.session_state:
        st.session_state.SUBJECT_DATA = {} 
    
    # 設定當前選中的層級
    if 'CURRENT_SUBJECT' not in st.session_state:
        st.session_state.CURRENT_SUBJECT = None
    if 'CURRENT_CATEGORY' not in st.session_state: # 新增：類別層級
        st.session_state.CURRENT_CATEGORY = None
    if 'CURRENT_UNIT' not in st.session_state:      # 新增：單元層級
        st.session_state.CURRENT_UNIT = None
    
    # 頁面導航和測驗狀態
    if 'page' not in st.session_state:
        st.session_state.page = "dashboard" 
    if 'quiz_mode' not in st.session_state:
        st.session_state.quiz_mode = 'quiz_all' 
    if 'current_quiz_index' not in st.session_state:
        st.session_state.current_quiz_index = 0 
    if 'current_quiz_list' not in st.session_state:
        st.session_state.current_quiz_list = [] 
    
    # 1. 設置文字輸入框的初始值為空 (實現自動清空)
    if 'manual_quiz_input' not in st.session_state:
        st.session_state.manual_quiz_input = ""

initialize_session_state()

# ----------------------------------------------------
# B. 核心功能：Gemini 題目提取 (支持圖片和文字)
# ----------------------------------------------------

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
            "explanation": {"type": "string", "description": "題目中提供的詳細解析內容"}
        },
        "required": ["question", "options", "correct_answer", "explanation"]
    }
}

def call_gemini_extraction(contents, source_id):
    """通用函數：呼叫 Gemini 提取題目，並處理錯誤。"""
    try:
        if isinstance(contents[0], str) and contents[0].startswith("TEXT_INPUT:"):
            extraction_prompt = contents[0].replace("TEXT_INPUT:", "你是一位專業的教育 AI 助手。請根據以下多選題格式，將其轉換為 JSON 格式。")
        else:
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
             quiz_data['source_image'] = source_id 
        return quiz_list
        
    except APIError as e:
        st.error(f"API 呼叫錯誤 ({source_id}): 請檢查您的 API 金鑰或配額。")
        st.exception(e)
        return []
    except Exception as e:
        st.warning(f"處理來源 {source_id} 時發生錯誤。請檢查輸入內容和格式。")
        st.exception(e)
        return []

def get_current_unit_lists():
    """返回當前選定單元的題目和錯題清單"""
    sub = st.session_state.CURRENT_SUBJECT
    cat = st.session_state.CURRENT_CATEGORY
    unit = st.session_state.CURRENT_UNIT
    
    if sub and cat and unit:
        # 檢查路徑是否存在
        if sub in st.session_state.SUBJECT_DATA and \
           cat in st.session_state.SUBJECT_DATA[sub] and \
           unit in st.session_state.SUBJECT_DATA[sub][cat]:
            
            data = st.session_state.SUBJECT_DATA[sub][cat][unit]
            return data['all'], data['wrong']
            
    return [], []

def get_quizzes_by_scope(scope_subject, scope_category=None, scope_unit=None):
    """(新增功能) 根據範圍返回所有題目"""
    all_quizzes = []
    
    if scope_subject not in st.session_state.SUBJECT_DATA:
        return []
    
    for category_name, category_data in st.session_state.SUBJECT_DATA[scope_subject].items():
        if scope_category and category_name != scope_category:
            continue
        
        for unit_name, unit_data in category_data.items():
            if scope_unit and unit_name != scope_unit:
                continue
            
            # 將單元中的所有題目加入總清單
            all_quizzes.extend(unit_data['all'])
            
    return all_quizzes

# ----------------------------------------------------
# C. 網站分頁和邏輯
# ----------------------------------------------------

def show_dashboard():
    """顯示主頁儀表板和統計數據"""
    st.title("📚 AI 智慧錯題本")
    st.header("🏠 儀表板")
    st.markdown("---")
    
    # 獲取當前選定單元的題目數據
    CURRENT_ALL_QUIZZES, CURRENT_WRONG_QUIZZES = get_current_unit_lists()
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
    
    # 4. 範圍測驗選擇邏輯 (取代舊的測驗按鈕)
    st.subheader("範圍測驗選擇：")
    
    current_sub = st.session_state.CURRENT_SUBJECT
    current_cat = st.session_state.CURRENT_CATEGORY
    current_unit = st.session_state.CURRENT_UNIT
    
    # 測驗範圍下拉選單
    if current_sub and current_cat:
        
        # 1. 測驗類別下的所有單元
        all_units_in_category = list(st.session_state.SUBJECT_DATA[current_sub][current_cat].keys())
        
        scope_options = [
            f"🎯 測驗當前單元 ({current_unit})",
            f"📚 測驗 '{current_cat}' 類別所有單元 ({len(all_units_in_category)} 個)"
        ] + [f"單獨測驗單元: {u}" for u in all_units_in_category if u != current_unit]
        
        selected_scope = st.selectbox("選擇測驗範圍：", scope_options)
        
        # 準備測驗按鈕
        test_button_col, review_button_col = st.columns(2)
        
        if test_button_col.button("📝 開始範圍測驗", use_container_width=True, type="primary"):
            
            quiz_scope = None
            if selected_scope.startswith("🎯 測驗當前單元"):
                quiz_scope = get_quizzes_by_scope(current_sub, current_cat, current_unit)
            elif selected_scope.startswith("📚 測驗"):
                quiz_scope = get_quizzes_by_scope(current_sub, current_cat)
            elif selected_scope.startswith("單獨測驗單元:"):
                unit_name = selected_scope.split(': ')[1]
                quiz_scope = get_quizzes_by_scope(current_sub, current_cat, unit_name)
            
            if quiz_scope:
                st.session_state.page = "quiz"
                st.session_state.quiz_mode = 'quiz_all'
                st.session_state.current_quiz_list = random.sample(quiz_scope, len(quiz_scope))
                st.session_state.current_quiz_index = 0
                st.rerun()
            else:
                st.warning("所選範圍內沒有題目。")
                
        if review_button_col.button(f"🔁 複習當前單元錯題 ({total_wrong} 題)", use_container_width=True, disabled=(total_wrong == 0)):
            st.session_state.page = "quiz"
            st.session_state.quiz_mode = 'review_wrong'
            st.session_state.current_quiz_list = random.sample(CURRENT_WRONG_QUIZZES, len(CURRENT_WRONG_QUIZZES))
            st.session_state.current_quiz_index = 0
            st.rerun()
            
    else:
        st.warning("請在左側邊欄選擇完整的科目、類別和單元，才能進行測驗範圍選擇。")

    st.markdown("---")
    # 顯示題目清單 (除錯用)
    with st.expander(f"🔍 查看當前單元 ({current_unit}) 所有題目"):
        st.json(CURRENT_ALL_QUIZZES)
        
def show_add_quiz_page():
    """處理圖片上傳、文字輸入和題目提取頁面"""
    st.header("➕ 新增題目：圖片或文字輸入")
    
    CURRENT_ALL_QUIZZES, _ = get_current_unit_lists()
    st.caption(f"題目將新增至當前單元 '{st.session_state.CURRENT_UNIT}'，目前總題數：**{len(CURRENT_ALL_QUIZZES)}** 題")
    st.markdown("---")

    tab1, tab2 = st.tabs(["🖼️ 圖片上傳 (推薦)", "✍️ 文字輸入 (單題/多題)"])

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
    # TAB 2: 文字輸入邏輯 (實現自動清空)
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
        
        # 使用 st.session_state.manual_quiz_input 來綁定 text_area 的內容
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
                    quizzes = call_gemini_extraction([f"TEXT_INPUT:\n{text_input}"], "Manual_Input")
                    
                    if quizzes:
                        CURRENT_ALL_QUIZZES.extend(quizzes)
                        st.success(f"🎉 文字內容成功提取 **{len(quizzes)}** 道題目。")
                        st.caption(f"當前單元總題數：{len(CURRENT_ALL_QUIZZES)}")
                        
                        # 1. 實現自動清空：將綁定的 session_state 變數設為空字串
                        st.session_state.manual_quiz_input = "" 
                        st.rerun() 
                    else:
                        st.error("⚠️ 無法從您輸入的文字中提取出結構化的題目。請檢查格式是否正確。")

    st.markdown("---")
    if st.button("⬅️ 返回儀表板"):
        st.session_state.page = "dashboard"
        st.rerun()


def show_quiz_page():
    """互動式測驗頁面 (通用於所有題目和錯題複習)"""
    
    _, CURRENT_WRONG_QUIZZES = get_current_unit_lists()
    
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

    quiz = quiz_list[current_index]
    
    mode_text = "🎯 範圍測驗" if st.session_state.quiz_mode == 'quiz_all' else "🧠 錯題複習模式"
    st.header(f"{mode_text} (第 {current_index + 1} / {total_quizzes} 題)")
    st.caption(f"來源：**{quiz['source_image']}**")
    st.markdown("---")

    st.subheader("📝 題目內容：")
    st.markdown(f"**{quiz['question']}**")

    options_map = ["A", "B", "C", "D"]
    options_with_label = [f"{options_map[i]}. {text.lstrip('ABCD. ')}" for i, text in enumerate(quiz['options'])]
    
    selected_option = st.radio("請選擇答案：", options_with_label, key=f"user_answer_radio_{current_index}")
    
    if st.button("✅ 提交答案", key=f"submit_button_{current_index}"):
        
        selected_letter = selected_option.split('.')[0]
        correct_answer_letter = quiz['correct_answer'].upper().strip()
        
        if selected_letter == correct_answer_letter:
            st.success("🎉 恭喜！答案正確！")
            
            if st.session_state.quiz_mode == 'review_wrong':
                for i, wrong_quiz in enumerate(CURRENT_WRONG_QUIZZES):
                    if wrong_quiz['question'] == quiz['question'] and wrong_quiz['source_image'] == quiz['source_image']:
                        del CURRENT_WRONG_QUIZZES[i]
                        st.toast("👏 該錯題已掌握，從錯題清單中移除。")
                        break
                        
        else:
            st.error(f"❌ 抱歉，答案錯誤。您選擇了 **{selected_letter}**。")
            
            is_already_wrong = any(w['question'] == quiz['question'] for w in CURRENT_WRONG_QUIZZES)
            if st.session_state.quiz_mode == 'quiz_all' and not is_already_wrong:
                CURRENT_WRONG_QUIZZES.append(quiz)
                st.toast("😥 題目已加入錯題清單。")
            
        # 顯示詳解卡片
        with st.expander("📖 查看詳細解析", expanded=True):
            st.info(f"**✅ 正確答案：** {correct_answer_letter}")
            st.markdown("#### 完整解析：")
            st.markdown(quiz['explanation'])

        st.markdown("---")
        if st.button("➡️ 下一題", type="primary"):
            st.session_state.current_quiz_index += 1
            st.rerun()
            
    if st.button("🏠 返回儀表板", key=f"back_to_dash_{current_index}"):
        st.session_state.page = "dashboard"
        st.rerun()

# ----------------------------------------------------
# D. 應用程式主入口
# ----------------------------------------------------

def main_app():
    st.set_page_config(layout="wide", page_title="AI 智慧錯題本")
    
    all_subjects = list(st.session_state.SUBJECT_DATA.keys())
    current_subject = st.session_state.CURRENT_SUBJECT
    
    st.sidebar.title("📚 AI 智慧錯題本")
    st.sidebar.header("📝 數據管理區")

    # --- 1. 科目管理 ---
    with st.sidebar.expander("🎓 管理科目/考試類型"):
        new_subject_name = st.text_input("輸入新科目名稱", key="new_subject_name")
        if st.button("創建新科目", key="create_subject_btn"):
            if new_subject_name and new_subject_name not in st.session_state.SUBJECT_DATA:
                st.session_state.SUBJECT_DATA[new_subject_name] = {}
                st.success(f"科目 '{new_subject_name}' 創建成功！")
                st.session_state.CURRENT_SUBJECT = new_subject_name
                st.rerun()
            elif new_subject_name:
                st.error("科目名稱已存在！")

    # 2. 選擇科目 (自動將最近創建的科目放在最前)
    sorted_subjects = [current_subject] + [s for s in all_subjects if s != current_subject] if current_subject in all_subjects else all_subjects
    
    selected_subject = st.sidebar.selectbox(
        "選擇要操作的科目",
        options=["請選擇"] + sorted_subjects,
        index=0 if not current_subject or current_subject not in all_subjects else 1
    )

    if selected_subject != "請選擇":
        st.session_state.CURRENT_SUBJECT = selected_subject
    elif current_subject in all_subjects:
        # 如果用戶取消選擇，保持當前狀態
        pass
    else:
        st.warning("請先創建或選擇一個科目。")
        if st.session_state.page != "dashboard": st.session_state.page = "dashboard"
        show_dashboard() 
        return 
        
    st.sidebar.info(f"當前科目：**{current_subject}**")
    
    # --- 3. 類別管理 (新增層級) ---
    current_categories = list(st.session_state.SUBJECT_DATA[current_subject].keys())

    with st.sidebar.expander(f"📚 管理類別 ({current_subject})"):
        new_category_name = st.text_input("輸入新類別名稱 (例如：法規/實務)", key="new_category_name")
        if st.button("創建新類別", key="create_category_btn"):
            if new_category_name and new_category_name not in current_categories:
                st.session_state.SUBJECT_DATA[current_subject][new_category_name] = {}
                st.success(f"類別 '{new_category_name}' 創建成功！")
                st.session_state.CURRENT_CATEGORY = new_category_name
                st.rerun()
            elif new_category_name:
                st.error("類別名稱已存在！")

    # 4. 選擇類別
    sorted_categories = [st.session_state.CURRENT_CATEGORY] + [c for c in current_categories if c != st.session_state.CURRENT_CATEGORY] if st.session_state.CURRENT_CATEGORY in current_categories else current_categories

    selected_category = st.sidebar.selectbox(
        "選擇要操作的類別",
        options=["請選擇"] + sorted_categories,
        index=0 if not st.session_state.CURRENT_CATEGORY or st.session_state.CURRENT_CATEGORY not in current_categories else 1
    )

    if selected_category != "請選擇":
        st.session_state.CURRENT_CATEGORY = selected_category
    elif st.session_state.CURRENT_CATEGORY in current_categories:
        pass
    else:
        st.warning("請創建或選擇一個類別。")
        if st.session_state.page != "dashboard": st.session_state.page = "dashboard"
        show_dashboard() 
        return

    st.sidebar.info(f"當前類別：**{st.session_state.CURRENT_CATEGORY}**")
    
    # --- 5. 單元管理 (單元是最低層級) ---
    current_units = list(st.session_state.SUBJECT_DATA[current_subject][st.session_state.CURRENT_CATEGORY].keys())

    with st.sidebar.expander(f"📑 管理單元 ({st.session_state.CURRENT_CATEGORY})"):
        new_unit_name = st.text_area("輸入新單元名稱", key="new_unit_name", height=50) # 為了輸入單元名稱
        if st.button("創建新單元", key="create_unit_btn"):
            if new_unit_name and new_unit_name not in current_units:
                # 這是最低層級，包含 all 和 wrong 兩個清單
                st.session_state.SUBJECT_DATA[current_subject][st.session_state.CURRENT_CATEGORY][new_unit_name] = {'all': [], 'wrong': []}
                st.success(f"單元 '{new_unit_name}' 創建成功！")
                st.session_state.CURRENT_UNIT = new_unit_name
                st.rerun()
            elif new_unit_name:
                st.error("單元名稱已存在！")

    # 6. 選擇單元
    sorted_units = [st.session_state.CURRENT_UNIT] + [u for u in current_units if u != st.session_state.CURRENT_UNIT] if st.session_state.CURRENT_UNIT in current_units else current_units

    selected_unit = st.sidebar.selectbox(
        "選擇要操作的單元",
        options=["請選擇"] + sorted_units,
        index=0 if not st.session_state.CURRENT_UNIT or st.session_state.CURRENT_UNIT not in current_units else 1
    )

    if selected_unit != "請選擇":
        st.session_state.CURRENT_UNIT = selected_unit
        st.sidebar.success(f"當前單元：**{selected_unit}**")
    elif st.session_state.CURRENT_UNIT in current_units:
        pass
    else:
        st.warning("請創建或選擇一個單元，才能上傳題目。")
        if st.session_state.page != "dashboard": st.session_state.page = "dashboard"
        show_dashboard() 
        return

    # ----------------------------------------------------
    # 主頁面導航
    # ----------------------------------------------------
    
    if st.sidebar.button("🏠 返回儀表板", key="sidebar_dash"):
         st.session_state.page = "dashboard"
         st.rerun()

    if st.session_state.page == "dashboard":
        show_dashboard()
    elif st.session_state.page == "add":
        show_add_quiz_page()
    elif st.session_state.page == "quiz":
        show_quiz_page()

if __name__ == "__main__":
    main_app()
