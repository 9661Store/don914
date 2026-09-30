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

st.set_page_config(page_title="小資投本比 旗艦終端機", page_icon="👑", layout="wide")

# ==========================================
# 🛡️ 檔案持久化與超級管理員設定
# ==========================================
SUPER_ADMIN = "w184813740@hotmail.com"
AUTH_FILE = "auth_list.txt"
PORTFOLIO_FILE = "portfolio_data.csv"

def get_auth_list():
    if not os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, "w") as f:
            f.write(SUPER_ADMIN + "\n")
    with open(AUTH_FILE, "r") as f:
        return [line.strip().lower() for line in f.readlines() if line.strip()]

if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'role' not in st.session_state: st.session_state['role'] = 'guest'
if 'user_email' not in st.session_state: st.session_state['user_email'] = ''

# 登入閘門
if not st.session_state['logged_in']:
    st.title("🔒 小資投本比 - 量化終端機")
    st.markdown("### ⚠️ 請驗證您的身份以解鎖系統權限")
    login_email = st.text_input("請輸入您的 E-mail").strip().lower()
    
    if st.button("🔑 驗證並登入", type="primary"):
        auth_list = get_auth_list()
        if login_email in auth_list:
            st.session_state['logged_in'] = True
            st.session_state['user_email'] = login_email
            # 判斷權限角色
            st.session_state['role'] = 'admin' if login_email == SUPER_ADMIN else 'user'
            st.success(f"✅ 登入成功！歡迎，您的權限級別為：{'超級管理員 👑' if st.session_state['role'] == 'admin' else '一般使用者 🚀'}")
            st.rerun()
        else:
            st.error("❌ 查無授權。請聯絡系統管理員 (w184813740@hotmail.com) 為您開通。")
    st.stop()

# ==========================================
# 🚀 雙引擎與資料庫快取 (強化容錯與補救)
# ==========================================
def get_kline_data(code, market, days=180):
    try:
        end_ts = int(datetime.datetime.now().timestamp())
        start_ts = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp())
        url = f"https://ws.api.cnyes.com/ws/api/v1/charting/history?symbol=TWS:{code}:STOCK&resolution=D&quote=1&from={start_ts}&to={end_ts}"
        res = requests.get(url, timeout=5, verify=False)
        if res.status_code == 200:
            data = res.json().get('data', {})
            if data and 't' in data:
                df = pd.DataFrame({'Date': pd.to_datetime(data['t'], unit='s'), 'Open': data['o'], 'High': data['h'], 'Low': data['l'], 'Close': data['c'], 'Volume': data['v']})
                if df['Volume'].mean() > 10000: df['Volume'] = df['Volume'] / 1000
                df.set_index('Date', inplace=True)
                df = df.dropna()
                if not df.empty and len(df) >= 10: return df, "鉅亨網"
    except: pass
    try:
        symbol = f"{code}{market}"
        df = yf.Ticker(symbol).history(period="1y")
        if not df.empty and len(df) >= 10: return df, "Yahoo"
    except: pass
    return pd.DataFrame(), "無資料"

@st.cache_data(ttl=86400)
def load_pe_data():
    pe_dict = {}
    for url in ["https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL", "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"]:
        try:
            res = twse_session.get(url, verify=False, timeout=10)
            if res.status_code == 200:
                for item in res.json():
                    code = item.get('Code', item.get('SecuritiesCompanyCode', '')).strip()
                    pe_str = str(item.get('PEratio', item.get('PERatio', '0'))).replace(',', '')
                    pe_dict[code] = float(pe_str) if pe_str and pe_str != '-' else 0.0
        except: pass
    return pe_dict

@st.cache_data(ttl=86400)
def load_company_info():
    info_dict = {}
    for url in ["https://openapi.twse.com.tw/v1/opendata/t187ap03_L", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"]:
        try:
            res = twse_session.get(url, verify=False, timeout=15)
            if res.status_code == 200:
                for item in res.json():
                    code = str(item.get('公司代號', item.get('SecuritiesCompanyCode', ''))).strip()
                    cap_str = str(item.get('實收資本額', '0')).replace(',', '')
                    info_dict[code] = {
                        "sector": str(item.get('產業類別', item.get('Industry', '未知'))).strip(),
                        "shares": float(cap_str) / 10 if cap_str and cap_str != '-' else 0
                    }
        except: pass
    return info_dict

@st.cache_data(ttl=86400)
def load_taiwan_stocks():
    stock_dict = {}
    for url, market, label in [("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", ".TW", "(上市)"), ("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", ".TWO", "(上櫃)")]:
        try:
            res = twse_session.get(url, verify=False, timeout=15)
            if res.status_code == 200:
                for item in res.json():
                    code = item.get('Code', item.get('SecuritiesCompanyCode', ''))
                    name = item.get('Name', item.get('CompanyName', ''))
                    if len(code) == 4 and code.isdigit(): stock_dict[f"{code} {name} {label}"] = f"{code}{market}"
        except: pass
    return stock_dict if stock_dict else {"2327 國巨 (上市)": "2327.TW"}

STOCK_DICT = load_taiwan_stocks()
INFO_DICT = load_company_info()
PE_DICT = load_pe_data()

# ==========================================
# 🚀 終端機介面 (依據角色動態顯示)
# ==========================================
st.title("🏆 小資投本比 - 雙引擎量化終端機")
st.caption(f"目前登入身份：{st.session_state['user_email']} ({'👑 管理員' if st.session_state['role'] == 'admin' else '👤 授權使用者'})")

# 根據角色決定能看到的模組
if st.session_state['role'] == 'admin':
    mode = st.sidebar.radio("切換系統模組", ["📡 嚴選加權評分雷達", "🎯 個股健檢 (標的審查)", "💼 投資追蹤 (進出場管理)", "🔐 授權管理中心"])
else:
    mode = st.sidebar.radio("切換系統模組", ["📡 嚴選加權評分雷達", "🎯 個股健檢 (標的審查)"])
    
if st.sidebar.button("🚪 登出系統"):
    st.session_state['logged_in'] = False
    st.rerun()

st.sidebar.markdown("---")

if mode in ["📡 嚴選加權評分雷達", "🎯 個股健檢 (標的審查)"]:
    st.sidebar.subheader("🎛️️ 黃金實戰參數")
    ui_min_it_ratio = st.sidebar.slider("投本比絕對下限 (%)", 0.0, 2.0, 0.15, 0.01)
    ui_bias_max = st.sidebar.slider("乖離率容忍上限 (%)", 3.0, 20.0, 12.0, 0.5)
    
    st.sidebar.markdown("---")
    ui_max_pe = st.sidebar.slider("本益比上限 (倍)", 5.0, 500.0, 40.0, 1.0)
    ui_min_amplitude = st.sidebar.slider("5日均振幅下限 (%)", 1.0, 10.0, 3.0, 0.5)
    
    st.sidebar.markdown("---")
    ui_min_vol = st.sidebar.slider("5日均量下限 (張)", 100, 5000, 800, 100)
    ui_max_cap = st.sidebar.slider("股本上限 (億)", 10, 500, 200, 10)

# ==========================================
# 模組 1：🔐 授權管理中心 (僅管理員可見)
# ==========================================
if mode == "🔐 授權管理中心":
    st.subheader("🔐 分享版使用者授權管理")
    st.markdown("在此新增或刪除 E-mail。因雙方共用同一個 App，名單修改後，朋友立刻就能登入。")
    
    auth_list = get_auth_list()
        
    col1, col2 = st.columns(2)
    with col1:
        new_email = st.text_input("輸入欲授權的 E-mail").strip().lower()
        if st.button("➕ 新增授權", type="primary"):
            if new_email and new_email not in auth_list:
                with open(AUTH_FILE, "a") as f: f.write(new_email + "\n")
                st.success(f"已成功授權給：{new_email}")
                st.rerun()
            else: st.warning("信箱為空或已存在授權名單中。")
            
    with col2:
        st.markdown("**目前已授權名單：**")
        for email in auth_list:
            cols = st.columns([4, 1])
            cols[0].write(f"✅ {email}")
            if email != SUPER_ADMIN:
                if cols[1].button("刪除", key=email):
                    auth_list.remove(email)
                    with open(AUTH_FILE, "w") as f:
                        for e in auth_list: f.write(e + "\n")
                    st.rerun()

# ==========================================
# 模組 2：📡 嚴選加權評分雷達
# ==========================================
elif mode == "📡 嚴選加權評分雷達":
    # 只有管理員可以選擇 XQ 上傳
    if st.session_state['role'] == 'admin':
        data_source = st.radio("選擇數據引擎", ["☁️ 雙引擎直連雲端抓取", "⚡ XQ 檔案上傳 (管理員專屬)"], horizontal=True)
    else:
        data_source = "☁️ 雙引擎直連雲端抓取"
        st.markdown("☁️ **目前使用：雙引擎直連雲端抓取**")
        
    uploaded_file = None
    if data_source == "⚡ XQ 檔案上傳 (管理員專屬)":
        uploaded_file = st.file_uploader("📂 請上傳 XQ 匯出的 CSV 檔", type=['csv'])
    else:
        col1, col2 = st.columns(2)
        with col1: chk_twse = st.checkbox("掃描上市股票", True)
        with col2: chk_tpex = st.checkbox("掃描上櫃股票", True)
    
    if st.button("🚀 啟動嚴選評分", type="primary"):
        if data_source == "⚡ XQ 檔案上傳 (管理員專屬)":
            if uploaded_file is not None:
                with st.spinner("⚡ 正在嚴格篩選並計算加權分數..."):
                    try:
                        df = pd.read_csv(uploaded_file, encoding='cp950', skiprows=3)
                        df_res = df.copy()
                        for col in ['BIAS(20日)', 'K值', 'D值', 'RSI(12日)', '本益比', '最高', '最低', '昨收']:
                            if col in df_res.columns: df_res[col] = pd.to_numeric(df_res[col].astype(str).str.replace(',', ''), errors='coerce')
                        col_it = next((c for c in df.columns if '投信買' in c), None)
                        col_cap = next((c for c in df.columns if '股本' in c), None)
                        col_pe = next((c for c in df.columns if '本益比' in c), None)
                        col_high, col_low, col_prev = next((c for c in df.columns if '最高' in c), None), next((c for c in df.columns if '最低' in c), None), next((c for c in df.columns if '昨收' in c), None)
                        survivors = []
                        for _, row in df_res.iterrows():
                            if not col_it or not col_cap: continue
                            try: it_ratio = ((float(str(row[col_it]).replace(',', '')) * 2.5) / (float(str(row[col_cap]).replace(',', '')) * 10000000)) * 100
                            except: continue
                            if it_ratio < ui_min_it_ratio: continue
                            bias = row.get('BIAS(20日)', 0)
                            if not (-ui_bias_max <= bias <= ui_bias_max): continue
                            if col_pe:
                                pe_val = row.get(col_pe, 0)
                                if pd.isna(pe_val) or pe_val <= 0 or pe_val > ui_max_pe: continue
                            amp_val = 0
                            if col_high and col_low and col_prev and row.get(col_prev, 0) > 0:
                                amp_val = ((row.get(col_high, 0) - row.get(col_low, 0)) / row.get(col_prev, 0)) * 100
                                if amp_val < ui_min_amplitude: continue
                            score = 55
                            k, d = row.get('K值', 50), row.get('D值', 50)
                            if k > d and k <= 80: score += 25
                            elif k > d: score += 15
                            rsi = row.get('RSI(12日)', 50)
                            if rsi >= 50: score += 20
                            row_dict = row.to_dict()
                            row_dict.update({'投本比(%)': round(it_ratio, 2), '振幅(%)': round(amp_val, 2), '綜合得分': score})
                            survivors.append(row_dict)
                        if survivors:
                            df_final = pd.DataFrame(survivors).rename(columns={'商品': '名稱', 'SMA(20日)': '20日月線價'}).sort_values('綜合得分', ascending=False)
                            st.session_state['radar_data'] = df_final[[c for c in ['代碼', '名稱', '綜合得分', '投本比(%)', 'BIAS(20日)', '本益比', '振幅(%)', 'K值', 'RSI(12日)'] if c in df_final.columns]]
                            st.session_state['radar_msg'] = f"🎉 嚴選完成！過濾後共存活 {len(df_final)} 檔標的："
                        else: st.session_state['radar_data'], st.session_state['radar_msg'] = pd.DataFrame(), "⚠️ 條件過於嚴格，本次無標的存活。"
                    except Exception as e: st.error(f"⚠️ 解析錯誤：{e}")
            else: st.warning("⚠️ 請先上傳 CSV 檔案！")
        else:
            with st.spinner("☁️ 正在連線政府資料庫與雙引擎運算..."):
                stock_list, target_date = [], datetime.datetime.now()
                for _ in range(7):
                    try:
                        if chk_twse:
                            res = twse_session.get(f"https://www.twse.com.tw/fund/T86?response=json&date={target_date.strftime('%Y%m%d')}&selectType=ALL", verify=False, timeout=10)
                            if res.status_code == 200 and 'data' in res.json():
                                for row in res.json()['data']:
                                    code, name, it_buy = row[0].strip(), row[1].strip(), int(row[10].replace(',', ''))
                                    if len(code) == 4 and not (code.startswith('00') or code.startswith('28')) and it_buy > 0: stock_list.append({'code': code, 'name': name, 'market': '.TW', 'it_buy': it_buy})
                        if chk_tpex and not stock_list:
                            res2 = twse_session.get(f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={target_date.year - 1911}/{target_date.strftime('%m/%d')}", verify=False, timeout=10)
                            if res2.status_code == 200 and 'aaData' in res2.json():
                                for row in res2.json()['aaData']:
                                    code, name, it_buy = str(row[0]).strip(), str(row[1]).strip(), int(str(row[7]).replace(',', '').split('.')[0])
                                    if len(code) == 4 and not (code.startswith('00') or code.startswith('28')) and it_buy > 0: stock_list.append({'code': code, 'name': name, 'market': '.TWO', 'it_buy': it_buy})
                    except: pass
                    if stock_list: break
                    target_date -= datetime.timedelta(days=1)

                debug_logs = []
                
                if not stock_list: 
                    st.session_state['radar_data'], st.session_state['radar_msg'] = pd.DataFrame(), "⚠️ 雲端完全抓不到今日或近期的投信買賣超紀錄。"
                else:
                    my_bar, results = st.progress(0, text=f"🚀 發現 {len(stock_list)} 檔標的，透過雙引擎高速解析中..."), []
                    for i, stock in enumerate(stock_list):
                        my_bar.progress((i + 1) / len(stock_list), text=f"🧮 正在檢查 {stock['code']} ({i+1}/{len(stock_list)}) ...")
                        code = stock['code']
                        try:
                            pe_ratio = PE_DICT.get(code, 0)
                            shares = INFO_DICT.get(code, {}).get('shares', 0)
                            
                            # Yahoo 備援修復缺失的本益比與股本
                            if shares == 0 or pe_ratio == 0:
                                try:
                                    tk = yf.Ticker(f"{code}{stock['market']}")
                                    info = tk.info
                                    if shares == 0 and info.get('sharesOutstanding'): shares = info.get('sharesOutstanding') / 10
                                    if pe_ratio == 0 and info.get('trailingPE'): pe_ratio = info.get('trailingPE')
                                except: pass
                            
                            if pe_ratio <= 0 or pe_ratio > ui_max_pe:
                                debug_logs.append(f"{code} {stock['name']} ❌ 淘汰：本益比過高或無資料 ({round(pe_ratio,2)} > {ui_max_pe})")
                                continue
                            
                            if shares <= 0:
                                debug_logs.append(f"{code} {stock['name']} ❌ 淘汰：無股本資料可算投本比")
                                continue
                                
                            it_ratio = round(((stock['it_buy'] * 2.5) / shares) * 100, 2)
                            if it_ratio < ui_min_it_ratio:
                                debug_logs.append(f"{code} {stock['name']} ❌ 淘汰：投本比未達標 ({it_ratio}%)")
                                continue
                                
                            if round(shares / 10000000, 2) > ui_max_cap:
                                debug_logs.append(f"{code} {stock['name']} ❌ 淘汰：股本過大")
                                continue
                                
                            stock_df, source_name = get_kline_data(code, stock['market'], days=180)
                            if stock_df.empty:
                                debug_logs.append(f"{code} {stock['name']} ❌ 淘汰：雙引擎皆無K線")
                                continue
                                
                            stock_close, stock_high, stock_low, stock_vol = stock_df['Close'], stock_df['High'], stock_df['Low'], stock_df['Volume']
                            current_vol = float(stock_vol.tail(5).mean())
                            if current_vol < ui_min_vol:
                                debug_logs.append(f"{code} {stock['name']} ❌ 淘汰：均量過低 ({round(current_vol)} 張)")
                                continue
                            
                            avg_amp = round((((stock_high - stock_low) / stock_close.shift(1)) * 100).tail(5).mean(), 2)
                            if avg_amp < ui_min_amplitude:
                                debug_logs.append(f"{code} {stock['name']} ❌ 淘汰：振幅太小 ({avg_amp}%)")
                                continue 
                            
                            ma20 = stock_close.rolling(20).mean().iloc[-1]
                            bias = round(((float(stock_close.iloc[-1]) - float(ma20)) / float(ma20)) * 100, 2)
                            if not (-ui_bias_max <= bias <= ui_bias_max):
                                debug_logs.append(f"{code} {stock['name']} ❌ 淘汰：乖離率超標 ({bias}%)")
                                continue
                            
                            score = 55
                            low9, high9 = stock_low.rolling(9).min(), stock_high.rolling(9).max()
                            k_series = ((stock_close - low9) / (high9 - low9) * 100).ewm(alpha=1/3, adjust=False).mean()
                            d_series = k_series.ewm(alpha=1/3, adjust=False).mean()
                            k_val, d_val = round(k_series.iloc[-1], 2), round(d_series.iloc[-1], 2)
                            if k_val > d_val and k_val <= 80: score += 25
                            elif k_val > d_val: score += 15
                            
                            delta = stock_close.diff()
                            rsi_val = round((100 - (100 / (1 + (delta.clip(lower=0).ewm(alpha=1/12, adjust=False).mean() / -delta.clip(upper=0).ewm(alpha=1/12, adjust=False).mean())))).iloc[-1], 2)
                            if rsi_val >= 50: score += 20
                            
                            results.append({
                                '代碼': stock['code'], '名稱': stock['name'], '綜合得分': score, 
                                '投本比(%)': it_ratio, '本益比': round(pe_ratio, 2), 
                                '5日均振幅(%)': avg_amp, 'BIAS(20日)': bias, 'K值': k_val, '引擎': source_name
                            })
                            debug_logs.append(f"{code} {stock['name']} ✅ 成功過關存活！({source_name})")
                        except Exception as e: 
                            debug_logs.append(f"{code} {stock['name']} ⚠️ 錯誤：{e}")
                            
                    my_bar.empty()
                    st.session_state['debug_logs'] = debug_logs
                    if results:
                        st.session_state['radar_data'] = pd.DataFrame(results).sort_values('綜合得分', ascending=False)
                        st.session_state['radar_msg'] = f"🎉 嚴選完成！雙引擎飆速過濾後，共存活 {len(st.session_state['radar_data'])} 檔菁英標的："
                    else: st.session_state['radar_data'], st.session_state['radar_msg'] = pd.DataFrame(), "⚠️ 條件過於嚴格，本次無標的存活。"

    if st.session_state['radar_data'] is not None:
        if not st.session_state['radar_data'].empty:
            st.success(st.session_state['radar_msg'])
            st.dataframe(st.session_state['radar_data'], use_container_width=True, hide_index=True)
        else: st.warning(st.session_state['radar_msg'])
        
        # 開發者透視眼僅管理員可見，避免朋友看到太多複雜資訊
        if st.session_state['role'] == 'admin' and 'debug_logs' in st.session_state and st.session_state['debug_logs']:
            with st.expander("🛠️ 開發者透視眼 (點擊查看：每檔股票為何被淘汰？)"):
                for log in st.session_state['debug_logs']: st.write(log)

# ==========================================
# 模組 3：🎯 個股健檢 (標的審查)
# ==========================================
elif mode == "🎯 個股健檢 (標的審查)":
    st.subheader("🎯 個股 X 光機 - 雙引擎基本面掃描")
    check_stock = st.selectbox("請選擇要健檢的標的", options=list(STOCK_DICT.keys()))
    if st.button("🩺 開始健檢", type="primary"):
        stock_code, market = check_stock.split(" ")[0], ".TW" if "(上市)" in check_stock else ".TWO"
        with st.spinner(f"正在掃描 {check_stock} ..."):
            try:
                hist, source_name = get_kline_data(stock_code, market, days=180)
                if hist.empty: st.error("⚠️ 雙引擎皆無法取得歷史資料。")
                else:
                    close = round(float(hist['Close'].iloc[-1]), 2)
                    ma20 = hist['Close'].rolling(window=20).mean()
                    bias = round(((float(hist['Close'].iloc[-1]) - ma20.iloc[-1]) / ma20.iloc[-1]) * 100, 2)
                    pe_ratio = PE_DICT.get(stock_code, 0)
                    hist['Amplitude'] = ((hist['High'] - hist['Low']) / hist['Close'].shift(1)) * 100
                    avg_amp = round(hist['Amplitude'].tail(5).mean(), 2)
                    low9, high9 = hist['Low'].rolling(9).min(), hist['High'].rolling(9).max()
                    hist['K'] = ((hist['Close'] - low9) / (high9 - low9) * 100).ewm(alpha=1/3, adjust=False).mean()
                    hist['D'] = hist['K'].ewm(alpha=1/3, adjust=False).mean()
                    k_val, d_val = round(hist['K'].iloc[-1], 2), round(hist['D'].iloc[-1], 2)
                    delta = hist['Close'].diff()
                    rsi_val = round((100 - (100 / (1 + (delta.clip(lower=0).ewm(alpha=1/12, adjust=False).mean() / -delta.clip(upper=0).ewm(alpha=1/12, adjust=False).mean())))).iloc[-1], 2)
                    
                    it_buy, target_date = 0, datetime.datetime.now()
                    for _ in range(7):
                        try:
                            if market == ".TW":
                                for row in twse_session.get(f"https://www.twse.com.tw/fund/T86?response=json&date={target_date.strftime('%Y%m%d')}&selectType=ALL", verify=False, timeout=10).json().get('data', []):
                                    if row[0].strip() == stock_code: it_buy = int(row[10].replace(',', '')); break
                            else:
                                for row in twse_session.get(f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={target_date.year - 1911}/{target_date.strftime('%m/%d')}", verify=False, timeout=10).json().get('aaData', []):
                                    if str(row[0]).strip() == stock_code: it_buy = int(str(row[7]).replace(',', '').split('.')[0]); break
                        except: pass
                        if it_buy > 0: break
                        target_date -= datetime.timedelta(days=1)
                        
                    shares = INFO_DICT.get(stock_code, {}).get('shares', 0)
                    
                    # 啟動備援修復
                    if shares == 0 or pe_ratio == 0:
                        try:
                            tk = yf.Ticker(f"{stock_code}{market}")
                            info = tk.info
                            if shares == 0 and info.get('sharesOutstanding'): shares = info.get('sharesOutstanding') / 10
                            if pe_ratio == 0 and info.get('trailingPE'): pe_ratio = info.get('trailingPE')
                        except: pass
                    
                    st.markdown(f"### 📊 【{check_stock}】 目前現價: {close} 元 (資料源: {source_name})")
                    pass_all = True
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if shares > 0:
                            real_it_ratio = round(((it_buy * 2.5) / shares) * 100, 2)
                            status_it = "✅ 過關" if real_it_ratio >= ui_min_it_ratio else "❌ 淘汰"
                        else:
                            real_it_ratio, status_it = "N/A", "❌ 淘汰(缺股數)"
                        if "淘汰" in status_it: pass_all = False
                        st.metric(f"投本比 (>{ui_min_it_ratio}%)", f"{real_it_ratio}%" if real_it_ratio != "N/A" else "N/A", status_it)
                        
                    with col2:
                        status_bias = "✅ 過關" if -ui_bias_max <= bias <= ui_bias_max else "❌ 淘汰"
                        if status_bias == "❌ 淘汰": pass_all = False
                        st.metric(f"BIAS (±{ui_bias_max}%)", f"{bias}%", status_bias)
                        
                    with col3:
                        if pe_ratio > 0:
                            status_pe = "✅ 過關" if pe_ratio <= ui_max_pe else "❌ 淘汰"
                        else:
                            status_pe = "❌ 淘汰(虧損或無資料)"
                        if "淘汰" in status_pe: pass_all = False
                        st.metric(f"本益比 (<{ui_max_pe})", f"{round(pe_ratio, 2)} 倍" if pe_ratio > 0 else "無/虧損", status_pe)
                        
                    st.markdown("---")
                    col4, col5, col6 = st.columns(3)
                    with col4:
                        status_amp = "✅ 過關" if avg_amp >= ui_min_amplitude else "❌ 淘汰(太牛皮)"
                        if status_amp == "❌ 淘汰(太牛皮)": pass_all = False
                        st.metric(f"5日均振幅 (>{ui_min_amplitude}%)", f"{avg_amp}%", status_amp)
                    with col5:
                        st.metric("KD 狀態", f"K:{k_val}", "🔥 加分" if k_val > d_val else "➖ 未加分")
                    with col6:
                        st.metric("RSI(12日)", f"{rsi_val}", "🔥 加分" if rsi_val >= 50 else "➖ 未加分")
                            
                    st.markdown("---")
                    if pass_all: 
                        score = 55 + (25 if k_val > d_val and k_val <= 80 else 15 if k_val > d_val else 0) + (20 if rsi_val >= 50 else 0)
                        st.success(f"🎉 **診斷結果：強勢存活！** 綜合得分為 **{score} 分**！")
                    else: st.error("⚠️ **診斷結果：淘汰。** 核心指標未達標準。")
            except Exception as e: st.error(f"健檢發生錯誤: {e}")

# ==========================================
# 模組 4：💼 投資追蹤 (進出場管理) - 僅管理員可見
# ==========================================
elif mode == "💼 投資追蹤 (進出場管理)" and st.session_state['role'] == 'admin':
    if 'portfolio' not in st.session_state: 
        if os.path.exists(PORTFOLIO_FILE): st.session_state['portfolio'] = pd.read_csv(PORTFOLIO_FILE)
        else: st.session_state['portfolio'] = pd.DataFrame(columns=["股票", "買進日", "買進價", "股數", "停損價", "停利目標"])
        
    st.subheader("💼 我的量化投資組合")
    with st.expander("➕ 新增交易紀錄", expanded=False):
        with st.form("add_trade_form"):
            col1, col2 = st.columns(2)
            with col1:
                t_stock = st.selectbox("選擇買進標的", options=list(STOCK_DICT.keys()))
                t_date = st.date_input("買進日期", datetime.date.today())
                t_price = st.number_input("買進均價", min_value=0.01, value=50.0, step=1.0)
            with col2:
                t_shares = st.number_input("買進股數", min_value=1, value=1000, step=1000)
                t_sl = st.number_input("設定停損價位", min_value=0.0, step=1.0)
                t_tp = st.number_input("絕對金額停利啟動線 (元)", value=5000, step=1000)
            if st.form_submit_button("📝 存入投資組合"):
                new_trade = {"股票": t_stock, "買進日": t_date.strftime("%Y-%m-%d"), "買進價": t_price, "股數": t_shares, "停損價": t_sl, "停利目標": t_tp}
                st.session_state['portfolio'] = pd.concat([st.session_state['portfolio'], pd.DataFrame([new_trade])], ignore_index=True)
                st.session_state['portfolio'].to_csv(PORTFOLIO_FILE, index=False, encoding='utf-8-sig')
                st.success(f"✅ 成功登錄！")
                st.rerun()

    if not st.session_state['portfolio'].empty:
        df_p = st.session_state['portfolio'].copy()
        with st.spinner("🔄 正在連線雙引擎取得最新報價..."):
            live_prices = []
            for idx, row in df_p.iterrows():
                try:
                    stock_code = row['股票'].split(" ")[0]
                    market = ".TW" if "(上市)" in row['股票'] else ".TWO"
                    hist, _ = get_kline_data(stock_code, market, days=10)
                    live_prices.append(round(float(hist['Close'].iloc[-1]), 2) if not hist.empty else row['買進價'])
                except: live_prices.append(row['買進價'])
            df_p['最新現價'] = live_prices
            df_p['未實現損益(元)'] = ((df_p['最新現價'] - df_p['買進價']) * df_p['股數']).astype(int)
            df_p['報酬率(%)'] = df_p.apply(lambda x: round(((x['最新現價'] - x['買進價']) / x['買進價']) * 100, 2) if x['買進價'] > 0 else 0, axis=1)
            
            status_list = []
            for _, row in df_p.iterrows():
                if row['最新現價'] <= row['停損價']: status_list.append("🔴 破停損，請平倉")
                elif row['未實現損益(元)'] >= row['停利目標']: status_list.append("🟢 達標，移動鎖利")
                else: status_list.append("⏳ 紀律持股中")
            df_p['目前狀態'] = status_list
            
        st.dataframe(df_p, use_container_width=True, hide_index=True)
        if st.button("🗑️ 清空所有紀錄", type="secondary"):
            st.session_state['portfolio'] = pd.DataFrame(columns=["股票", "買進日", "買進價", "股數", "停損價", "停利目標"])
            st.session_state['portfolio'].to_csv(PORTFOLIO_FILE, index=False, encoding='utf-8-sig')
            st.rerun()
