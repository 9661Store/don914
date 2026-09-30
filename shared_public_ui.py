import streamlit as st
import pandas as pd
import yfinance as yf
import datetime
import requests
import warnings
import ssl
import urllib3
import os

warnings.filterwarnings('ignore')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context
twse_session = requests.Session()
twse_session.verify = False
twse_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
})

st.set_page_config(page_title="小資投本比 - 嚴選終端機", page_icon="🚀", layout="wide")

# ==========================================
# 🛡️ 系統授權登入閘門 (讀取後台名單)
# ==========================================
AUTH_FILE = "auth_list.txt"

def check_auth(email):
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, "r") as f:
            valid_emails = [line.strip() for line in f.readlines() if line.strip()]
        return email in valid_emails
    return False

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.title("🔒 小資投本比 - 終端機 (受保護版本)")
    st.markdown("### ⚠️ 本系統不對外公開，請輸入授權 E-mail")
    login_email = st.text_input("請輸入您的 E-mail 以解鎖系統")
    if st.button("🔑 驗證並登入", type="primary"):
        if check_auth(login_email.strip()):
            st.session_state['logged_in'] = True
            st.success("✅ 授權成功！正在為您啟動...")
            st.rerun()
        else:
            st.error("❌ 查無授權。請聯絡系統擁有者為您開通權限。")
    st.stop()

# ==========================================
# 🚀 共用資料快取區 (省略重複，與專屬版相同)
# ==========================================
# (此處請貼上與專屬版相同的 get_kline_data, load_pe_data, load_company_info, load_taiwan_stocks)

# ==========================================
# 🚀 終端機主程式 (無 XQ 版)
# ==========================================
st.title("🏆 小資投本比 - 嚴選終端機")

mode = st.sidebar.radio("切換系統模組", ["📡 嚴選加權評分雷達", "🎯 個股健檢 (標的審查)"])
st.sidebar.markdown("---")

st.sidebar.subheader("🎛️ 嚴格核心過濾門檻")
ui_min_it_ratio = st.sidebar.slider("投本比絕對下限 (%)", 0.0, 2.0, 0.15, 0.01)
ui_bias_max = st.sidebar.slider("乖離率容忍上限 (%)", 3.0, 20.0, 12.0, 0.5)

st.sidebar.markdown("---")
st.sidebar.subheader("🛡️ 估值與波動度防禦")
ui_max_pe = st.sidebar.slider("本益比上限 (倍)", 5.0, 500.0, 40.0, 1.0)
ui_min_amplitude = st.sidebar.slider("5日均振幅下限 (%)", 1.0, 10.0, 3.0, 0.5)

st.sidebar.markdown("---")
st.sidebar.subheader("💧 流動性與體質防禦")
ui_min_vol = st.sidebar.slider("5日均量下限 (張)", 100, 5000, 800, 100)
ui_max_cap = st.sidebar.slider("股本上限 (億)", 10, 500, 200, 10)

if mode == "📡 嚴選加權評分雷達":
    st.subheader("📡 雲端雙引擎飆股雷達")
    col1, col2 = st.columns(2)
    with col1: chk_twse = st.checkbox("掃描上市股票", True)
    with col2: chk_tpex = st.checkbox("掃描上櫃股票", True)

    if st.button("🚀 啟動雙引擎嚴選", type="primary"):
        # 這裡直接執行雲端連線運算，拔除所有 XQ 相關的 if-else 邏輯
        st.info("系統掃描中... (請將前一版的雲端掃描邏輯貼於此處)")
