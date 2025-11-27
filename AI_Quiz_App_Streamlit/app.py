import streamlit as st
import json
import random
import os
from PIL import Image
from google import genai
from google.genai.errors import APIError

# --- 配置區 ---
# ⚠️ 注意：請確保此處的金鑰是您有效的 Gemini API 金鑰
API_KEY = "AIzaSyCd214KXU0JCD_FRx1IEpCAiC9R39z7H1M" 
MODEL_NAME = "gemini-2.5-flash"
DATA_FILE = "quiz_data.json" # 數據儲存檔案名稱

# 初始化 Gemini 客戶端
try:
    client = genai.Client(api_key=API_KEY)
except ValueError:
    st.error("❌ API 金鑰無效。請檢查程式碼中的 API_KEY 設定！")
    st.stop()

# ----------------------------------------------------
# A. 數據持久化函數
# ----------------------------------------------------

def load_data():
    """啟動時，從 JSON 檔案讀取所有題目數據。"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            st.warning("⚠️ 數據檔案損壞，將從空數據開始。")
            return {}
    return {}

def save_data(data):
    """有變動時，將數據寫入 JSON 檔案。"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"❌ 數據保存失敗: {e}")

# ----------------------------------------------------
# B. 全局狀態初始化 (使用 st.session_state)
# ----------------------------------------------------

def initialize_session_state():
    """初始化 Streamlit Session State，並讀取持久化數據。"""
    
    persisted_data = load_data()
    
    if 'SUBJECT_DATA' not in st.session_state:
        st.session_state.SUBJECT_DATA = persisted_data 
    
    if 'app_state' not in st.session_state:
        st.session_state.app_state = "SELECT_SUBJECT" 
        
    if 'CURRENT_SUBJECT' not in st.session_state:
        st.session_state.CURRENT_SUBJECT = None
    if 'CURRENT_CATEGORY' not in st.session_state:
        st.session_state.CURRENT_CATEGORY = None
    if 'CURRENT_UNIT' not in st.session_state:      
        st.session_state.CURRENT_UNIT = None
    
    if 'quiz_mode' not in st.session_state:
        st.session_state.quiz_mode = 'quiz_all' 
    if 'current_quiz_index' not in st.session_state:
        st.session_state.current_quiz_index = 0 
    if 'current_quiz_list' not in st.session_state:
        st.session_state.current_quiz_list = [] 
    
    # 文字輸入框的初始值 (用於自動清空)
    if 'manual_quiz_input' not in st.session_state:
        st.session_state.manual_quiz_input = ""
    
    if 'edit_quiz_index' not in st.session_state:
        st.session_state.edit_quiz_index = None

initialize_session_state()

# ----------------------------------------------------
# C. 核心功能：Gemini 提取和數據訪問
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

def find_quiz_location(quiz):
    """根據題目內容反向查找該題目在 SUBJECT_DATA 中的位置"""
    for sub, sub_data in st.session_state.SUBJECT_DATA.items():
        for cat, cat_data in sub_data.items():
            for unit, unit_data in cat_data.items():
                # 檢查 all 和 wrong 清單
                if quiz in unit_data['all']:
                    return sub, cat, unit, 'all'
                if quiz in unit_data['wrong']:
                    return sub, cat, unit, 'wrong'
    return None, None, None, None

def get_quizzes_by_scope(scope_subject, scope_category=None, scope_unit=None):
    """根據範圍返回所有題目 (all 和 wrong)"""
    all_quizzes = []
    wrong_quizzes = []
    
    if scope_subject not in st.session_state.SUBJECT_DATA:
        return [], []
    
    for category_name, category_data in st.session_state.SUBJECT_DATA[scope_subject].items():
        if scope_category and category_name != scope_category:
            continue
        
        for unit_name, unit_data in category_data.items():
            if scope_unit and unit_name != scope_unit:
                continue
            
            all_quizzes.extend(unit_data['all'])
            wrong_quizzes.extend(unit_data['wrong'])
            
    return all_quizzes, wrong_quizzes

def get_current_unit_lists():
    """返回當前選定單元的題目和錯題清單"""
    sub = st.session_state.CURRENT_SUBJECT
    cat = st.session_state.CURRENT_CATEGORY
    unit = st.session_state.CURRENT_UNIT
    
    if sub and cat and unit:
        if sub in st.session_state.SUBJECT_DATA and \
           cat in st.session_state.SUBJECT_DATA[sub] and \
           unit in st.session_state.SUBJECT_DATA[sub][cat]:
            
            data = st.session_state.SUBJECT_DATA[sub][cat][unit]
            return data['all'], data['wrong']
            
    return [], []

def navigate_to(state):
    st.session_state.app_state = state
    st.rerun()

def navigate_home():
    """導航到最上層科目選擇頁面"""
    st.session_state.CURRENT_SUBJECT = None
    st.session_state.CURRENT_CATEGORY = None
    st.session_state.CURRENT_UNIT = None
    navigate_to("SELECT_SUBJECT")

# ----------------------------------------------------
# D. 介面函數 (多頁面流程)
# ----------------------------------------------------

def show_select_subject():
    """主頁面：選擇科目/考試類型"""
    st.title("📚 AI 智慧錯題本")
    st.header("步驟 1：選擇科目/考試類型")
    st.markdown("---")
    
    subjects = list(st.session_state.SUBJECT_DATA.keys())
    
    if not subjects:
        st.info("您尚未創建任何科目。請使用左側邊欄創建第一個科目。")
        return

    cols = st.columns(3)
    for i, sub_name in enumerate(subjects):
        with cols[i % 3]:
            total_quizzes_in_sub, _ = get_quizzes_by_scope(sub_name)
            
            if st.button(f"🎓 {sub_name} ({len(total_quizzes_in_sub)} 題)", key=f"select_sub_{sub_name}", use_container_width=True):
                st.session_state.CURRENT_SUBJECT = sub_name
                st.session_state.CURRENT_CATEGORY = None
                st.session_state.CURRENT_UNIT = None
                navigate_to("SELECT_CATEGORY")

def show_select_category():
    """步驟 2：選擇類別/分卷"""
    sub_name = st.session_state.CURRENT_SUBJECT
    st.title(f"科目：{sub_name}")
    st.header("步驟 2：選擇類別")
    st.markdown("---")
    
    categories = list(st.session_state.SUBJECT_DATA.get(sub_name, {}).keys())
    
    if st.button("⬅️ 返回科目選擇"):
        navigate_to("SELECT_SUBJECT")
        return
        
    if not categories:
        st.info(f"科目 '{sub_name}' 下沒有任何類別。請使用左側邊欄創建第一個類別。")
        return

    cols = st.columns(3)
    for i, cat_name in enumerate(categories):
        with cols[i % 3]:
            total_quizzes_in_cat, total_wrong_in_cat = get_quizzes_by_scope(sub_name, cat_name)
            
            if st.button(f"📚 {cat_name} ({len(total_quizzes_in_cat)} 題)", key=f"select_cat_{cat_name}", use_container_width=True):
                st.session_state.CURRENT_CATEGORY = cat_name
                st.session_state.CURRENT_UNIT = None
                navigate_to("UNIT_DETAIL")
            
            if st.button(f"📝 測驗類別 ({len(total_quizzes_in_cat)})", key=f"test_cat_{cat_name}", use_container_width=True, type="secondary", disabled=(len(total_quizzes_in_cat) == 0)):
                start_quiz(total_quizzes_in_cat, 'quiz_all')
                
            if st.button(f"🔁 複習類別錯題 ({len(total_wrong_in_cat)})", key=f"review_cat_{cat_name}", use_container_width=True, disabled=(len(total_wrong_in_cat) == 0)):
                start_quiz(total_wrong_in_cat, 'review_wrong')


def show_unit_details():
    """步驟 3/4：單元詳情與測驗範圍選擇"""
    sub_name = st.session_state.CURRENT_SUBJECT
    cat_name = st.session_state.CURRENT_CATEGORY
    
    st.title(f"{sub_name} - {cat_name}")
    st.header("步驟 3：單元選擇與測驗")
    st.markdown("---")
    
    units = list(st.session_state.SUBJECT_DATA.get(sub_name, {}).get(cat_name, {}).keys())
    
    if st.button("⬅️ 返回類別選擇"):
        navigate_to("SELECT_CATEGORY")
        return

    if not units:
        st.info(f"類別 '{cat_name}' 下沒有任何單元。請使用左側邊欄創建第一個單元。")
        return
        
    # 主頁面統計與測驗
    st.subheader("測驗範圍選擇：")
    
    total_cat_quizzes, total_cat_wrong = get_quizzes_by_scope(sub_name, cat_name)
    
    scope_options = [
        f"📚 測驗本類別所有單元 ({len(total_cat_quizzes)} 題)",
    ] + [f"單獨測驗單元: {u}" for u in units]
    
    selected_scope = st.selectbox("選擇測驗範圍：", scope_options)
    
    test_button_col, review_button_col = st.columns(2)
    
    quiz_scope = []
    if selected_scope.startswith("📚 測驗"):
        quiz_scope = total_cat_quizzes
    elif selected_scope.startswith("單獨測驗單元:"):
        unit_name = selected_scope.split(': ')[1]
        quiz_scope, _ = get_quizzes_by_scope(sub_name, cat_name, unit_name)

        
    if test_button_col.button("📝 開始範圍測驗", use_container_width=True, type="primary", disabled=(len(quiz_scope) == 0)):
        start_quiz(quiz_scope, 'quiz_all')
        
    if review_button_col.button(f"🔁 複習類別錯題 ({len(total_cat_wrong)} 題)", use_container_width=True, disabled=(len(total_cat_wrong) == 0)):
        start_quiz(total_cat_wrong, 'review_wrong')

    st.markdown("---")
    st.subheader("單元列表與管理：")
    
    for unit_name in units:
        unit_data = st.session_state.SUBJECT_DATA[sub_name][cat_name][unit_name]
        all_count = len(unit_data['all'])
        wrong_count = len(unit_data['wrong'])
        
        col1, col2, col3, col4 = st.columns([0.45, 0.18, 0.18, 0.18])
        
        col1.markdown(f"**📑 {unit_name}** (總題數: {all_count} / 錯題: {wrong_count})")
        
        with col2:
            if col2.button("👁️ 瀏覽題目", key=f"browse_unit_{unit_name}", use_container_width=True, disabled=(all_count == 0)):
                st.session_state.CURRENT_UNIT = unit_name
                navigate_to("BROWSE_UNIT")
        
        with col3:
            if col3.button("➕ 新增題目", key=f"add_to_{unit_name}", use_container_width=True):
                st.session_state.CURRENT_UNIT = unit_name
                navigate_to("ADD_QUESTION")
        
        with col4:
            if col4.button("測驗單元", key=f"test_unit_{unit_name}", use_container_width=True, type="secondary", disabled=(all_count == 0)):
                st.session_state.CURRENT_UNIT = unit_name
                start_quiz(unit_data['all'], 'quiz_all')

def show_browse_unit_page():
    """新增頁面：瀏覽單元內全部題目與答案"""
    sub = st.session_state.CURRENT_SUBJECT
    cat = st.session_state.CURRENT_CATEGORY
    unit = st.session_state.CURRENT_UNIT

    if st.button("⬅️ 返回單元列表"):
        navigate_to("UNIT_DETAIL")
        return
        
    st.title(f"👁️ 瀏覽題目：{unit}")
    st.caption(f"科目：{sub} / 類別：{cat}")
    st.markdown("---")
    
    CURRENT_ALL_QUIZZES, _ = get_current_unit_lists()
    
    if not CURRENT_ALL_QUIZZES:
        st.info("該單元目前沒有題目。")
        return

    for i, quiz in enumerate(CURRENT_ALL_QUIZZES):
        st.subheader(f"題號 {i + 1} (來源: {quiz.get('source_image', '手動輸入')})")
        
        st.markdown(f"**{quiz['question']}**")

        options_map = ["A", "B", "C", "D"]
        for j, option_text in enumerate(quiz['options']):
            prefix = "🟢" if options_map[j] == quiz['correct_answer'].upper() else "⚫"
            st.markdown(f" {prefix} **{options_map[j]}.** {option_text.lstrip('ABCD. ')}")

        with st.expander("📖 查看詳解 / 編輯題目"):
            st.markdown(f"**✅ 正確答案：** {quiz['correct_answer'].upper()}")
            st.markdown(f"**完整解析：** {quiz['explanation']}")
            
            if st.button("✏️ 編輯題目內容", key=f"edit_browse_{i}"):
                st.session_state.edit_quiz_index = i
                st.session_state.edit_quiz_list_key = 'all' 
                navigate_to("EDIT_QUIZ")
                
        st.markdown("---")


def show_add_quiz_page():
    """新增題目頁面 (圖片或文字)"""
    sub = st.session_state.CURRENT_SUBJECT
    cat = st.session_state.CURRENT_CATEGORY
    unit = st.session_state.CURRENT_UNIT
    
    if st.button("⬅️ 返回單元列表"):
        navigate_to("UNIT_DETAIL")
        return
        
    st.title(f"新增題目到：{unit}")
    st.caption(f"科目：{sub} / 類別：{cat}")
    st.markdown("---")
    
    CURRENT_ALL_QUIZZES, _ = get_current_unit_lists()
    st.caption(f"當前單元 '{unit}' 總題數：**{len(CURRENT_ALL_QUIZZES)}** 題")
    st.markdown("---")

    tab1, tab2 = st.tabs(["🖼️ 圖片上傳 (推薦)", "✍️ 文字輸入 (單題/多題)"])

    # ... (圖片上傳邏輯)
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
                save_data(st.session_state.SUBJECT_DATA)
                st.success(f"🎉 處理完成！總共新增 **{len(new_quizzes)}** 道題目。")
                st.caption(f"當前單元總題數：{len(CURRENT_ALL_QUIZZES)}")


    # ... (文字輸入邏輯)
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
                    quizzes = call_gemini_extraction([f"TEXT_INPUT:\n{text_input}"], "Manual_Input")
                    
                    if quizzes:
                        CURRENT_ALL_QUIZZES.extend(quizzes)
                        save_data(st.session_state.SUBJECT_DATA)
                        st.success(f"🎉 文字內容成功提取 **{len(quizzes)}** 道題目。")
                        st.caption(f"當前單元總題數：{len(CURRENT_ALL_QUIZZES)}")
                        
                        st.session_state.manual_quiz_input = "" 
                        st.rerun() 
                    else:
                        st.error("⚠️ 無法從您輸入的文字中提取出結構化的題目。請檢查格式是否正確。")

def show_edit_quiz_page():
    """手動編輯題目內容 (新增)"""
    
    st.title("✏️ 編輯題目內容")
    st.caption("用於修正 AI 偵測錯誤的題目、答案或解析。")
    st.markdown("---")
    
    quiz_index = st.session_state.edit_quiz_index
    list_key = st.session_state.edit_quiz_list_key

    if list_key == 'all':
        quiz_list, _ = get_current_unit_lists()
    elif list_key == 'current_quiz_list':
        quiz_list = st.session_state.current_quiz_list
    else:
        st.error("編輯狀態錯誤，找不到要編輯的題目清單。")
        if st.button("返回"): navigate_to("UNIT_DETAIL")
        return

    if 0 <= quiz_index < len(quiz_list):
        quiz_to_edit = quiz_list[quiz_index]
    else:
        st.error("找不到該索引的題目。")
        if st.button("返回"): navigate_to("UNIT_DETAIL")
        return

    st.subheader(f"編輯來源：{quiz_to_edit.get('source_image', '手動輸入')}")
    st.markdown("---")
    
    # 🌟 修正點 1：安全設置 SelectBox 的起始值
    options_map = ["A", "B", "C", "D"]
    correct_answer_upper = quiz_to_edit['correct_answer'].upper()
    
    try:
        initial_index = options_map.index(correct_answer_upper)
    except ValueError:
        initial_index = 0
        st.warning(f"⚠️ 偵測到無效答案 '{correct_answer_upper}'，已預設為 A。請手動修正。")


    with st.form(key="edit_quiz_form"):
        new_question = st.text_area("題目內容:", value=quiz_to_edit['question'])

        new_options = []
        for i in range(4):
            new_options.append(st.text_input(f"選項 {['A','B','C','D'][i]}:", value=quiz_to_edit['options'][i], key=f"option_{i}"))

        new_correct_answer = st.selectbox("正確答案:", options=options_map, index=initial_index)

        new_explanation = st.text_area("詳細解析:", value=quiz_to_edit['explanation'])

        submit_edit = st.form_submit_button("✅ 儲存修改", type="primary")

    if submit_edit:
        # 執行更新
        quiz_list[quiz_index]['question'] = new_question
        quiz_list[quiz_index]['options'] = new_options
        quiz_list[quiz_index]['correct_answer'] = new_correct_answer
        quiz_list[quiz_index]['explanation'] = new_explanation
        
        save_data(st.session_state.SUBJECT_DATA)
        st.success("🎉 題目內容已成功更新！")
        
        # 導航回原來的頁面
        if list_key == 'all':
            navigate_to("BROWSE_UNIT")
        elif list_key == 'current_quiz_list':
            st.session_state.current_quiz_index = quiz_index 
            navigate_to("QUIZ")


    if st.button("⬅️ 取消/返回"):
        if list_key == 'all':
            navigate_to("BROWSE_UNIT")
        elif list_key == 'current_quiz_list':
            navigate_to("QUIZ")

def start_quiz(quiz_scope, mode):
    """啟動測驗的輔助函數"""
    st.session_state.quiz_mode = mode
    st.session_state.current_quiz_list = random.sample(quiz_scope, len(quiz_scope))
    st.session_state.current_quiz_index = 0
    navigate_to("QUIZ")


def show_quiz_page():
    """互動式測驗頁面 (修復下一題功能，並增加編輯按鈕)"""
    
    quiz_list = st.session_state.current_quiz_list
    current_index = st.session_state.current_quiz_index
    total_quizzes = len(quiz_list)

    if current_index >= total_quizzes:
        st.header("🎉 測驗/複習結束！")
        st.subheader(f"本次共完成 {total_quizzes} 題。")
        st.markdown("---")
        st.session_state.current_quiz_index = 0
        if st.button("返回主介面", type="primary"):
            navigate_home()
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
    
    with st.container():
        
        submit_col, edit_col = st.columns([0.6, 0.4])
        submitted = submit_col.button("✅ 提交答案", type="primary", key=f"submit_button_{current_index}")

        if submitted:
            
            selected_letter = selected_option.split('.')[0]
            correct_answer_letter = quiz['correct_answer'].upper().strip()
            
            if selected_letter == correct_answer_letter:
                st.success("🎉 恭喜！答案正確！")
                
                if st.session_state.quiz_mode == 'review_wrong':
                    sub, cat, unit, list_key = find_quiz_location(quiz)
                    if sub and cat and unit and list_key == 'wrong':
                        wrong_list = st.session_state.SUBJECT_DATA[sub][cat][unit]['wrong']
                        try:
                            wrong_list.remove(quiz)
                            st.toast("👏 該錯題已掌握，從錯題清單中移除。")
                            save_data(st.session_state.SUBJECT_DATA)
                        except ValueError:
                            pass
                            
            else:
                st.error(f"❌ 抱歉，答案錯誤。您選擇了 **{selected_letter}**。")
                
                sub, cat, unit, _ = find_quiz_location(quiz)
                
                if sub and cat and unit:
                    wrong_list_target = st.session_state.SUBJECT_DATA[sub][cat][unit]['wrong']
                    is_already_wrong = any(w['question'] == quiz['question'] for w in wrong_list_target)

                    if st.session_state.quiz_mode == 'quiz_all' and not is_already_wrong:
                        wrong_list_target.append(quiz)
                        st.toast("😥 題目已加入原單元的錯題清單。")
                        save_data(st.session_state.SUBJECT_DATA)
                
            # 顯示詳解卡片
            with st.expander("📖 查看詳細解析", expanded=True):
                st.info(f"**✅ 正確答案：** {correct_answer_letter}")
                st.markdown("#### 完整解析：")
                st.markdown(quiz['explanation'])

            # 設置下一題按鈕狀態
            st.session_state[f'show_next_{current_index}'] = True
            
        
        # 手動編輯按鈕 (在 Form 外，但受提交狀態影響)
        if edit_col.button("✏️ 編輯題目", key=f"edit_quiz_{current_index}"):
             st.session_state.edit_quiz_index = current_index
             st.session_state.edit_quiz_list_key = 'current_quiz_list' 
             navigate_to("EDIT_QUIZ")
    
    # 下一題按鈕 (修復邏輯)
    if st.session_state.get(f'show_next_{current_index}', False):
        st.markdown("---")
        if st.button("➡️ 下一題", key=f"next_button_outside_{current_index}", type="primary"):
            st.session_state.current_quiz_index += 1
            st.session_state[f'show_next_{current_index}'] = False # 重置按鈕狀態
            st.rerun()

    if st.button("🏠 返回主介面", key=f"back_to_dash_{current_index}"):
        navigate_home()

# ----------------------------------------------------
# E. 應用程式主入口
# ----------------------------------------------------

def main_app():
    st.set_page_config(layout="wide", page_title="AI 智慧錯題本")
    
    # ----------------------------------------------------
    # 左側邊欄：管理功能 (創建新項目)
    # ----------------------------------------------------
    
    st.sidebar.title("📚 數據創建區")
    
    current_sub = st.session_state.CURRENT_SUBJECT
    current_cat = st.session_state.CURRENT_CATEGORY
    current_unit = st.session_state.CURRENT_UNIT

    # 1. 科目管理
    with st.sidebar.expander("🎓 創建新科目/考試類型"):
        new_subject_name = st.text_input("輸入新科目名稱", key="side_new_subject_name")
        if st.button("創建科目", key="side_create_subject_btn"):
            if new_subject_name and new_subject_name not in st.session_state.SUBJECT_DATA:
                st.session_state.SUBJECT_DATA[new_subject_name] = {}
                save_data(st.session_state.SUBJECT_DATA)
                st.success(f"科目 '{new_subject_name}' 創建成功！")
                st.session_state.CURRENT_SUBJECT = new_subject_name
                navigate_to("SELECT_SUBJECT")
            elif new_subject_name:
                st.error("科目名稱已存在！")
    
    # 2. 類別管理
    if current_sub:
        with st.sidebar.expander(f"📚 創建 {current_sub} 的類別"):
            new_category_name = st.text_input("輸入新類別名稱 (如：實務)", key="side_new_category_name")
            if st.button("創建類別", key="side_create_category_btn"):
                if new_category_name and new_category_name not in st.session_state.SUBJECT_DATA[current_sub]:
                    st.session_state.SUBJECT_DATA[current_sub][new_category_name] = {}
                    save_data(st.session_state.SUBJECT_DATA)
                    st.success(f"類別 '{new_category_name}' 創建成功！")
                    st.session_state.CURRENT_CATEGORY = new_category_name
                    navigate_to("SELECT_CATEGORY")
                elif new_category_name:
                    st.error("類別名稱已存在！")

    # 3. 單元管理
    if current_sub and current_cat:
        with st.sidebar.expander(f"📑 創建 {current_cat} 的單元"):
            new_unit_name = st.text_area("輸入新單元名稱", key="side_new_unit_name", height=50)
            if st.button("創建單元", key="side_create_unit_btn"):
                if new_unit_name and new_unit_name not in st.session_state.SUBJECT_DATA[current_sub][current_cat]:
                    st.session_state.SUBJECT_DATA[current_sub][current_cat][new_unit_name] = {'all': [], 'wrong': []}
                    save_data(st.session_state.SUBJECT_DATA)
                    st.success(f"單元 '{new_unit_name}' 創建成功！")
                    st.session_state.CURRENT_UNIT = new_unit_name
                    navigate_to("UNIT_DETAIL")
                elif new_unit_name:
                    st.error("單元名稱已存在！")
    
    # ----------------------------------------------------
    # 主頁面流程控制
    # ----------------------------------------------------
    
    # 4. 全局返回主畫面按鈕
    with st.container():
        st.markdown('<div style="position:fixed; top:10px; right:10px; z-index:1000;">', unsafe_allow_html=True)
        if st.button("🏠 回主畫面", key="global_home_button"):
            navigate_home()
        st.markdown('</div>', unsafe_allow_html=True)


    if st.session_state.app_state == "SELECT_SUBJECT":
        show_select_subject()
    elif st.session_state.app_state == "SELECT_CATEGORY":
        show_select_category()
    elif st.session_state.app_state == "UNIT_DETAIL":
        show_unit_details()
    elif st.session_state.app_state == "ADD_QUESTION":
        show_add_quiz_page()
    elif st.session_state.app_state == "BROWSE_UNIT":
        show_browse_unit_page()
    elif st.session_state.app_state == "EDIT_QUIZ":
        show_edit_quiz_page()
    elif st.session_state.app_state == "QUIZ":
        show_quiz_page()


if __name__ == "__main__":
    main_app()
