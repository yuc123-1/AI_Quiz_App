import streamlit as st
import json
import random
from PIL import Image
from google import genai
from google.genai.errors import APIError

# --- 配置區 ---
# 請替換成你的實際 Gemini API 金鑰
# 這是運行網站的關鍵！
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
    if 'all_quizzes' not in st.session_state:
        st.session_state.all_quizzes = []  # 總題目清單
    if 'wrong_quizzes' not in st.session_state:
        st.session_state.wrong_quizzes = [] # 錯題清單
    if 'page' not in st.session_state:
        st.session_state.page = "dashboard" # 預設顯示儀表板
    if 'quiz_mode' not in st.session_state:
        st.session_state.quiz_mode = 'quiz_all' # 測驗模式：'quiz_all' 或 'review_wrong'
    if 'current_quiz_index' not in st.session_state:
        st.session_state.current_quiz_index = 0 # 當前測驗題號
    if 'current_quiz_list' not in st.session_state:
        st.session_state.current_quiz_list = [] # 本次測驗的題目清單

initialize_session_state()

# ----------------------------------------------------
# B. 核心功能：Gemini 題目提取 (支持多題)
# ----------------------------------------------------

# 輸出結構和 Prompt 沿用 Colab 修正版 (支持單圖多題)
PROMPT = (
    "你是一位專業的教育 AI 助手，專門從圖片中提取選擇題。 "
    "請仔細分析這張圖片中的**所有獨立選擇題**。 "
    "請確保你的輸出是一個包含所有提取出題目的 **JSON 清單** (Array)，不要包含任何額外的文字或說明。"
)
RESPONSE_SCHEMA_MULTI_QUIZ = {
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
            "explanation": {"type": "string", "description": "圖片中提供的詳細解析文字"}
        },
        "required": ["question", "options", "correct_answer", "explanation"]
    }
}

def extract_quizzes_from_image(image_file):
    """處理單個上傳檔案，呼叫 Gemini API 提取題目。"""
    
    try:
        img = Image.open(image_file)
        
        with st.spinner(f"🧠 AI 正在分析圖片: {image_file.name}..."):
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=[PROMPT, img],
                config={
                    "response_mime_type": "application/json",
                    "response_schema": RESPONSE_SCHEMA_MULTI_QUIZ
                }
            )
        
        quiz_list = json.loads(response.text)
        
        for quiz_data in quiz_list:
             quiz_data['source_image'] = image_file.name 
        return quiz_list
        
    except APIError as e:
        st.error(f"API 呼叫錯誤 ({image_file.name}): 請檢查您的 API 金鑰或配額。")
        st.exception(e)
        return []
    except Exception as e:
        st.warning(f"處理圖片 {image_file.name} 時發生錯誤。可能 AI 返回的 JSON 格式不正確。")
        st.exception(e)
        return []

# ----------------------------------------------------
# C. 網站分頁邏輯
# ----------------------------------------------------

def show_dashboard():
    """顯示主頁儀表板和統計數據"""
    st.title("📚 AI 智慧錯題本")
    st.header("🏠 儀表板")
    st.markdown("---")
    
    total_quizzes = len(st.session_state.all_quizzes)
    total_wrong = len(st.session_state.wrong_quizzes)

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
        if st.button("➕ 新增題目 (上傳圖片)", use_container_width=True, type="primary"):
            st.session_state.page = "add"
            st.rerun()

    with b_col2:
        if total_quizzes > 0 and st.button("📝 開始測驗所有題目", use_container_width=True):
            st.session_state.page = "quiz"
            st.session_state.quiz_mode = 'quiz_all'
            # 隨機打亂題目順序
            st.session_state.current_quiz_list = random.sample(st.session_state.all_quizzes, len(st.session_state.all_quizzes))
            st.session_state.current_quiz_index = 0
            st.rerun()
        elif total_quizzes == 0:
            st.button("📝 開始測驗所有題目", use_container_width=True, disabled=True)


    with b_col3:
        if total_wrong > 0 and st.button(f"🔁 複習錯題 ({total_wrong} 題)", use_container_width=True):
            st.session_state.page = "quiz"
            st.session_state.quiz_mode = 'review_wrong'
            # 隨機打亂錯題順序
            st.session_state.current_quiz_list = random.sample(st.session_state.wrong_quizzes, len(st.session_state.wrong_quizzes))
            st.session_state.current_quiz_index = 0
            st.rerun()
        else:
            st.button(f"🔁 複習錯題 (0 題)", use_container_width=True, disabled=True)
            
    # 顯示題目清單 (除錯用)
    with st.expander("🔍 查看所有題目清單 (點擊展開)"):
        st.json(st.session_state.all_quizzes)
        
def show_add_quiz_page():
    """處理圖片上傳和題目提取頁面"""
    st.header("➕ 新增題目：陸續增加照片")
    st.caption(f"目前總題數：**{len(st.session_state.all_quizzes)}** 題")
    st.markdown("---")

    uploaded_files = st.file_uploader(
        "🖼️ 請選擇一或多個包含選擇題的圖片檔案上傳", 
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True
    )
    
    if uploaded_files:
        st.subheader(f"將處理 {len(uploaded_files)} 個檔案：")
        
        progress_bar = st.progress(0, text="開始處理...")
        
        new_quizzes = []
        for i, file in enumerate(uploaded_files):
            progress_bar.progress((i + 1) / len(uploaded_files), text=f"正在分析圖片 {file.name}...")
            
            quizzes = extract_quizzes_from_image(file)
            new_quizzes.extend(quizzes)
            
            if quizzes:
                st.success(f"✅ 圖片 **{file.name}** 成功提取 **{len(quizzes)}** 道題目。")
            else:
                st.warning(f"⚠️ 圖片 **{file.name}** 未提取到任何題目，請檢查圖片清晰度。")

        progress_bar.empty()

        if new_quizzes:
            st.session_state.all_quizzes.extend(new_quizzes)
            st.success(f"🎉 處理完成！總共新增 **{len(new_quizzes)}** 道題目。")
            st.caption(f"當前總題數：{len(st.session_state.all_quizzes)}")

    st.markdown("---")
    if st.button("⬅️ 返回儀表板"):
        st.session_state.page = "dashboard"
        st.rerun()

def show_quiz_page():
    """互動式測驗頁面 (通用於所有題目和錯題複習)"""
    
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
    st.caption(f"來源圖片：**{quiz['source_image']}**")
    st.markdown("---")

    # 顯示題目
    st.subheader("📝 題目內容：")
    st.markdown(f"**{quiz['question']}**")

    # 確保選項的標籤格式為 A. B. C. D.
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
                # 注意：這裡需要找到並移除完全相同的字典物件
                for i, wrong_quiz in enumerate(st.session_state.wrong_quizzes):
                    if wrong_quiz['question'] == quiz['question'] and wrong_quiz['source_image'] == quiz['source_image']:
                        del st.session_state.wrong_quizzes[i]
                        st.toast("👏 該錯題已掌握，從錯題清單中移除。")
                        break
                        
        else:
            st.error(f"❌ 抱歉，答案錯誤。您選擇了 **{selected_letter}**。")
            
            # 如果是初次測驗，將其加入錯題清單
            is_already_wrong = any(w['question'] == quiz['question'] for w in st.session_state.wrong_quizzes)
            if st.session_state.quiz_mode == 'quiz_all' and not is_already_wrong:
                 st.session_state.wrong_quizzes.append(quiz)
                 st.toast("😥 題目已加入錯題清單。")
            
        # 顯示詳解卡片 (使用 Streamlit 的 expander 製作精美的詳解區)
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
    
    # 側邊欄導航
    st.sidebar.title("導航")
    
    page_selection = st.sidebar.radio(
        "選擇頁面",
        ["儀表板", "新增題目"],
        index=0 if st.session_state.page == "dashboard" else 1 if st.session_state.page == "add" else 0
    )

    # 頁面路由：控制顯示哪個頁面
    if page_selection == "儀表板":
        target_page = "dashboard"
    elif page_selection == "新增題目":
        target_page = "add"
    else:
        target_page = st.session_state.page # 保持在 quiz 頁面

    if st.session_state.page != target_page and st.session_state.page != "quiz":
        st.session_state.page = target_page
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