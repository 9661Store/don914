import streamlit as st
import pandas as pd
import yfinance as yf
import datetime
import requests
import warnings
import ssl
import urllib3
import os

# --- 破解 SSL 防火牆與限流設定 (政府 OpenAPI 與鉅亨網專用) ---
warnings.filterwarnings('ignore')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context
twse_session = requests.Session()
twse_session.verify = False
twse_session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
})

# --- 網頁介面設定 ---
st.set_page_config(page_title="小資投本比 旗艦終端機", page_icon="🚀", layout="wide")

# ==========================================
# 🛡️ 系統授權登入閘門
# ==========================================
AUTHORIZED_EMAILS = ["w184813740@hotmail.com"] 

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    st.title("🔒 小資投本比 - 終極防禦終端機")
    st.markdown("### ⚠️ 系統已上鎖，請驗證您的身份")
    login_email = st.text_input("請輸入授權的 E-mail 以解鎖系統")
    if st.button("🔑 登入系統", type="primary"):
        if login_email.strip() in AUTHORIZED_EMAILS:
            st.session_state['logged_in'] = True
            st.success("✅ 授權成功！正在為您啟動終端機...")
            st.rerun()
        else:
            st.error("❌ 查無授權。請確認您的 E-mail 是否正確或聯絡系統管理員。")
    st.stop()

# ==========================================
# 🚀 雙引擎資料快取區 (鉅亨網 + Yahoo 備援 + OpenAPI)
# ==========================================
def get_kline_data(code, market, days=120):
    """雙引擎 K 線抓取：優先使用鉅亨網，失敗則自動切換 Yahoo"""
    # 引擎 1：鉅亨網 (高速、不擋 IP)
    try:
        end_ts = int(datetime.datetime.now().timestamp())
        start_ts = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp())
        url = f"https://ws.api.cnyes.com/ws/api/v1/charting/history?symbol=TWS:{code}:STOCK&resolution=D&quote=1&from={start_ts}&to={end_ts}"
        res = requests.get(url, timeout=5, verify=False)
        if res.status_code == 200:
            data = res.json().get('data', {})
            if data and 't' in data:
                df = pd.DataFrame({
                    'Date': pd.to_datetime(data['t'], unit='s'),
                    'Open': data['o'],
                    'High': data['h'],
                    'Low': data['l'],
                    'Close': data['c'],
                    'Volume': data['v']
                })
                if df['Volume'].mean() > 10000:
                    df['Volume'] = df['Volume'] / 1000
                df.set_index('Date', inplace=True)
                df = df.dropna()
                if not df.empty and len(df) >= 20:
                    return df, "鉅亨網"
    except Exception:
        pass
        
    # 引擎 2：Yahoo Finance 備援機制
    try:
        symbol = f"{code}{market}"
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="6mo")
        if not df.empty and len(df) >= 20:
            return df, "Yahoo"
    except Exception:
        pass

    return pd.DataFrame(), "無資料"

@st.cache_data(ttl=86400)
def load_pe_data():
    pe_dict = {}
    try:
        res_twse = twse_session.get("https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL", verify=False, timeout=10)
        if res_twse.status_code == 200:
            for item in res_twse.json():
                try:
                    pe_str = str(item.get('PEratio', '0')).replace(',', '')
                    if pe_str == '-' or not pe_str: pe_str = '0'
                    pe_dict[item['Code'].strip()] = float(pe_str)
                except: pass
    except: pass
    
    try:
        res_tpex = twse_session.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis", verify=False, timeout=10)
        if res_tpex.status_code == 200:
            for item in res_tpex.json():
                try:
                    pe_str = str(item.get('PERatio', '0')).replace(',', '')
                    if pe_str == '-' or not pe_str: pe_str = '0'
                    pe_dict[item['SecuritiesCompanyCode'].strip()] = float(pe_str)
                except: pass
    except: pass
    return pe_dict

@st.cache_data(ttl=86400)
def load_company_info():
    info_dict = {}
    try:
        res_twse = twse_session.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", verify=False, timeout=15)
        if res_twse.status_code == 200:
            for item in res_twse.json():
                code = str(item.get('公司代號', '')).strip()
                cap_str = str(item.get('實收資本額', '0')).replace(',', '')
                if not cap_str or cap_str == '-': cap_str = '0'
                shares = float(cap_str) / 10
                info_dict[code] = {
                    "sector": str(item.get('產業類別', '未知')).strip(),
                    "business": str(item.get('主要經營業務', '未知')).strip(),
                    "shares": shares
                }
    except: pass
    try:
        res_tpex = twse_session.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", verify=False, timeout=15)
        if res_tpex.status_code == 200:
            for item in res_tpex.json():
                code = str(item.get('公司代號', item.get('SecuritiesCompanyCode', ''))).strip()
                cap_str = str(item.get('實收資本額', '0')).replace(',', '')
                if not cap_str or cap_str == '-': cap_str = '0'
                shares = float(cap_str) / 10
                info_dict[code] = {
                    "sector": str(item.get('產業類別', item.get('Industry', '未知'))).strip(),
                    "business": str(item.get('主要經營業務', item.get('MainBusiness', '未知'))).strip(),
                    "shares": shares
                }
    except: pass
    return info_dict

@st.cache_data(ttl=86400)
def load_taiwan_stocks():
    stock_dict = {}
    try:
        res_twse = twse_session.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", verify=False, timeout=15)
        if res_twse.status_code == 200:
            for item in res_twse.json():
                code, name = item.get('Code', ''), item.get('Name', '')
                if len(code) == 4 and code.isdigit(): stock_dict[f"{code} {name} (上市)"] = f"{code}.TW"
        res_tpex = twse_session.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", verify=False, timeout=15)
        if res_tpex.status_code == 200:
            for item in res_tpex.json():
                code, name = item.get('SecuritiesCompanyCode', ''), item.get('CompanyName', '')
                if len(code) == 4 and code.isdigit(): stock_dict[f"{code} {name} (上櫃)"] = f"{code}.TWO"
    except Exception: pass
    if not stock_dict:
        stock_dict["2327 國巨 (上市)"] = "2327.TW"
        stock_dict["4958 臻鼎-KY (上市)"] = "4958.TW"
        stock_dict["8996 高力 (上市)"] = "8996.TW"
    return stock_dict

STOCK_DICT = load_taiwan_stocks()
INFO_DICT = load_company_info()
PE_DICT = load_pe_data()

if len(STOCK_DICT) <= 3: load_taiwan_stocks.clear()
if not INFO_DICT: load_company_info.clear()
if not PE_DICT: load_pe_data.clear()

# ==========================================
# 🚀 終端機主程式 
# ==========================================
st.title("🏆 小資投本比 - 估值與波動度終極防禦終端機")

PORTFOLIO_FILE = "portfolio_data.csv"

if 'radar_data' not in st.session_state: st.session_state['radar_data'] = None
if 'radar_msg' not in st.session_state: st.session_state['radar_msg'] = ""
if 'chat_history' not in st.session_state:
    st.session_state['chat_history'] = [{"role": "assistant", "content": "您好！我是您的專屬量化助理。您可以問我基礎的指標名詞；若在左側輸入 Gemini API 金鑰，我將解鎖為全能 AI 顧問！"}]

if 'portfolio' not in st.session_state: 
    if os.path.exists(PORTFOLIO_FILE):
        st.session_state['portfolio'] = pd.read_csv(PORTFOLIO_FILE)
    else:
        st.session_state['portfolio'] = pd.DataFrame(columns=["股票", "買進日", "買進價", "股數", "停損價", "停利目標"])

# --- 側邊欄：系統模式 ---
mode = st.sidebar.radio("切換系統模組", [
    "📡 嚴選加權評分雷達", 
    "🎯 個股健檢 (標的審查)", 
    "⏱️ 個股時光機 (歷史回測)", 
    "💼 投資追蹤 (進出場管理)"
])
st.sidebar.markdown("---")

st.sidebar.subheader("🧠 AI 大腦連線設定")
ui_gemini_key = st.sidebar.text_input("🔑 輸入 Gemini API Key (選填)", type="password", help="填入後解鎖全能 AI 顧問")
st.sidebar.markdown("---")

if mode in ["📡 嚴選加權評分雷達", "🎯 個股健檢 (標的審查)"]:
    st.sidebar.subheader("🎛️ 嚴格核心過濾門檻")
    # 🔓 解放極限：下限降至 0.0，包容微量買超
    ui_min_it_ratio = st.sidebar.slider("投本比絕對下限 (%)", 0.0, 2.0, 0.1, 0.01, help="未達此標準直接剔除")
    ui_bias_max = st.sidebar.slider("乖離率容忍上限 (%)", 3.0, 15.0, 8.0, 0.5, help="超出此區間直接剔除")
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("🛡️ 估值與波動度防禦")
    # 🔓 解放極限：上限拉至 500，包容高本益比強勢股
    ui_max_pe = st.sidebar.slider("本益比上限 (倍)", 5.0, 500.0, 60.0, 1.0, help="防禦估值過高飆股")
    ui_min_amplitude = st.sidebar.slider("5日均振幅下限 (%)", 1.0, 10.0, 3.5, 0.5, help="剔除股性死魚的標的")
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("💧 流動性與體質防禦")
    ui_min_vol = st.sidebar.slider("5日均量下限 (張)", 100, 5000, 800, 100)
    ui_max_cap = st.sidebar.slider("股本上限 (億)", 10, 500, 200, 10)

elif mode == "⏱️ 個股時光機 (歷史回測)":
    st.sidebar.header("🎛️ 回測紀律設定")
    ui_capital = st.sidebar.number_input("初始本金 (元)", value=20000, step=5000)
    ui_tp = st.sidebar.number_input("啟動防守獲利門檻 (元)", value=5000, step=1000)
    ui_drawdown = st.sidebar.number_input("獲利回吐出場限制 (元)", value=2000, step=500)
    ui_sl = st.sidebar.number_input("強制停損比例 (%)", value=10, step=1)

# ==========================================
# 模組 1：嚴選加權評分雷達
# ==========================================
if mode == "📡 嚴選加權評分雷達":
    st.subheader("📡 全市場飆股 - 嚴格過濾與綜合評分排序")
    data_source = st.radio("選擇數據引擎", ["⚡ XQ 檔案上傳 (極速)", "☁️ 雙引擎直連雲端抓取 (智慧回溯)"], horizontal=True)
    uploaded_file = None
    if data_source == "⚡ XQ 檔案上傳 (極速)":
        uploaded_file = st.file_uploader("📂 請上傳 XQ 匯出的 CSV 檔 (需包含最高、最低、本益比)", type=['csv'])
    else:
        col1, col2 = st.columns(2)
        with col1: chk_twse, chk_tpex = st.checkbox("上市", True), st.checkbox("上櫃", True)

    if st.button("🚀 啟動嚴選評分", type="primary"):
        if data_source == "⚡ XQ 檔案上傳 (極速)":
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
            with st.spinner("☁️ 正在連線政府資料庫與雙引擎運算 (完美備援版)..."):
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
                            # 1. 政府 OpenAPI 取得本益比與股本
                            pe_ratio = PE_DICT.get(code, 0)
                            if pe_ratio > ui_max_pe and pe_ratio != 0:
                                debug_logs.append(f"{code} {stock['name']} ❌ 遭淘汰：本益比過高 ({pe_ratio} > {ui_max_pe})")
                                continue
                            
                            shares = INFO_DICT.get(code, {}).get('shares', 0)
                            it_ratio = 0.0
                            if shares > 0:
                                it_ratio = round(((stock['it_buy'] * 2.5) / shares) * 100, 2)
                                if it_ratio < ui_min_it_ratio:
                                    debug_logs.append(f"{code} {stock['name']} ❌ 遭淘汰：投本比未達標 ({it_ratio}%)")
                                    continue
                                if round(shares / 10000000, 2) > ui_max_cap:
                                    debug_logs.append(f"{code} {stock['name']} ❌ 遭淘汰：股本過大")
                                    continue
                            else:
                                it_ratio = 99.9
                                
                            # 2. 雙引擎 K 線抓取
                            stock_df, source_name = get_kline_data(code, stock['market'], days=90)
                            
                            if stock_df.empty:
                                debug_logs.append(f"{code} {stock['name']} ❌ 遭淘汰：雙引擎皆無法取得 K 線資料")
                                continue
                                
                            stock_close = stock_df['Close']
                            stock_high = stock_df['High']
                            stock_low = stock_df['Low']
                            stock_vol = stock_df['Volume']
                            
                            current_vol = float(stock_vol.tail(5).mean())
                            if current_vol < ui_min_vol:
                                debug_logs.append(f"{code} {stock['name']} ❌ 遭淘汰：均量低於 {ui_min_vol} 千張 (目前: {round(current_vol)} 張)")
                                continue
                            
                            avg_amp = round((((stock_high - stock_low) / stock_close.shift(1)) * 100).tail(5).mean(), 2)
                            if avg_amp < ui_min_amplitude:
                                debug_logs.append(f"{code} {stock['name']} ❌ 遭淘汰：5日振幅太小 ({avg_amp}%)")
                                continue 
                            
                            ma20 = stock_close.rolling(20).mean().iloc[-1]
                            bias = round(((float(stock_close.iloc[-1]) - float(ma20)) / float(ma20)) * 100, 2)
                            if not (-ui_bias_max <= bias <= ui_bias_max):
                                debug_logs.append(f"{code} {stock['name']} ❌ 遭淘汰：乖離率超標 ({bias}%)")
                                continue
                            
                            score = 55
                            low9, high9 = stock_low.rolling(9).min(), stock_high.rolling(9).max()
                            k_series = ((stock_close - low9) / (high9 - low9) * 100).ewm(alpha=1/3, adjust=False).mean()
                            d_series = k_series.ewm(alpha=1/3, adjust=False).mean()
                            k_val, d_val = round(k_series.iloc[-1], 2), round(d_series.iloc[-1], 2)
                            if k_val > d_val and k_val <= 80: score += 25
                            elif k_val > d_val: score += 15
                            
                            delta = stock_close.diff()
                            rsi_series = 100 - (100 / (1 + (delta.clip(lower=0).ewm(alpha=1/12, adjust=False).mean() / -delta.clip(upper=0).ewm(alpha=1/12, adjust=False).mean())))
                            rsi_val = round(rsi_series.iloc[-1], 2)
                            if rsi_val >= 50: score += 20
                            
                            results.append({
                                '代碼': stock['code'], 
                                '名稱': stock['name'], 
                                '綜合得分': score, 
                                '投本比(%)': it_ratio if it_ratio != 99.9 else 'N/A', 
                                '本益比': round(pe_ratio, 2) if pe_ratio > 0 else 'N/A', 
                                '5日均振幅(%)': avg_amp, 
                                'BIAS(20日)': bias, 
                                'K值': k_val, 
                                '引擎': source_name
                            })
                            debug_logs.append(f"{code} {stock['name']} ✅ 成功過關存活！(來源: {source_name})")
                        except Exception as e: 
                            debug_logs.append(f"{code} {stock['name']} ⚠️ 發生程式錯誤：{e}")
                            continue 
                            
                    my_bar.empty()
                    st.session_state['debug_logs'] = debug_logs
                    
                    if results:
                        st.session_state['radar_data'] = pd.DataFrame(results).sort_values('綜合得分', ascending=False)
                        st.session_state['radar_msg'] = f"🎉 嚴選完成！雙引擎飆速過濾後，共存活 {len(st.session_state['radar_data'])} 檔菁英標的："
                    else: 
                        st.session_state['radar_data'], st.session_state['radar_msg'] = pd.DataFrame(), "⚠️ 條件過於嚴格，本次無標的存活。"

    if st.session_state['radar_data'] is not None:
        if not st.session_state['radar_data'].empty:
            st.success(st.session_state['radar_msg'])
            st.dataframe(st.session_state['radar_data'], use_container_width=True, hide_index=True)
        else: 
            st.warning(st.session_state['radar_msg'])
            
        if 'debug_logs' in st.session_state and st.session_state['debug_logs']:
            with st.expander("🛠️ 開發者透視眼 (點擊查看：每檔股票為何被淘汰？)"):
                for log in st.session_state['debug_logs']:
                    st.write(log)

# ==========================================
# 模組 2：個股健檢 (標的審查)
# ==========================================
elif mode == "🎯 個股健檢 (標的審查)":
    st.subheader("🎯 個股 X 光機 - 六大維度與基本面審查")
    st.markdown("比對左側的濾網標準，為您診斷是否具備實戰條件。")
    check_stock = st.selectbox("請選擇要健檢的標的", options=list(STOCK_DICT.keys()))
    
    if st.button("🩺 開始健檢", type="primary"):
        stock_code = check_stock.split(" ")[0]
        market = ".TW" if "(上市)" in check_stock else ".TWO"
        
        with st.spinner(f"正在為 {check_stock} 進行雙引擎基本面與技術面掃描..."):
            try:
                hist, source_name = get_kline_data(stock_code, market, days=90)
                
                if hist.empty: st.error("⚠️ 雙引擎皆無法取得歷史資料。請確認網路或稍後再試。")
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
                                twse_data = twse_session.get(f"https://www.twse.com.tw/fund/T86?response=json&date={target_date.strftime('%Y%m%d')}&selectType=ALL", verify=False, timeout=10).json()
                                for row in twse_data.get('data', []):
                                    if row[0].strip() == stock_code: it_buy = int(row[10].replace(',', '')); break
                            else:
                                tpex_data = twse_session.get(f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={target_date.year - 1911}/{target_date.strftime('%m/%d')}", verify=False, timeout=10).json()
                                for row in tpex_data.get('aaData', []):
                                    if str(row[0]).strip() == stock_code: it_buy = int(str(row[7]).replace(',', '').split('.')[0]); break
                        except: pass
                        if it_buy > 0: break
                        target_date -= datetime.timedelta(days=1)
                        
                    shares = INFO_DICT.get(stock_code, {}).get('shares', 0)
                    real_it_ratio = round(((it_buy * 2.5) / shares) * 100, 2) if shares > 0 and it_buy > 0 else 0.0
                    
                    st.markdown(f"### 📊 【{check_stock}】 目前現價: {close} 元 (資料源: {source_name})")
                    
                    with st.expander("📖 公司基本面與業務簡介", expanded=True):
                        comp_info = INFO_DICT.get(stock_code, {})
                        sector_tw, business_tw = comp_info.get('sector', ''), comp_info.get('business', '')
                        if not sector_tw or sector_tw == '未知':
                            st.warning("🔄 啟用備援資料庫：無官方業務簡介。")
                        st.markdown(f"**🏭 產業類別：** {sector_tw}")
                        st.markdown(f"**📝 主要業務：** {business_tw}")
                    
                    pass_all = True
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        status = "✅ 過關" if real_it_ratio >= ui_min_it_ratio else "❌ 淘汰"
                        if shares == 0: status, real_it_ratio = "✅ 放行(無股數)", "N/A"
                        if status == "❌ 淘汰": pass_all = False
                        st.metric(f"投本比 (>{ui_min_it_ratio}%)", f"{real_it_ratio}%" if real_it_ratio != "N/A" else "N/A", status)
                    with col2:
                        status = "✅ 過關" if -ui_bias_max <= bias <= ui_bias_max else "❌ 淘汰"
                        if status == "❌ 淘汰": pass_all = False
                        st.metric(f"BIAS (±{ui_bias_max}%)", f"{bias}%", status)
                    with col3:
                        status = "✅ 過關" if (0 < pe_ratio <= ui_max_pe) or pe_ratio == 0 else "❌ 淘汰"
                        if status == "❌ 淘汰": pass_all = False
                        st.metric(f"本益比 (<{ui_max_pe})", f"{round(pe_ratio, 2)} 倍" if pe_ratio > 0 else "無/虧損", status)
                        
                    st.markdown("---")
                    col4, col5, col6 = st.columns(3)
                    with col4:
                        status = "✅ 過關" if avg_amp >= ui_min_amplitude else "❌ 淘汰(太牛皮)"
                        if status == "❌ 淘汰(太牛皮)": pass_all = False
                        st.metric(f"5日均振幅 (>{ui_min_amplitude}%)", f"{avg_amp}%", status)
                    with col5:
                        st.metric("KD 狀態", f"K:{k_val}", "🔥 加分" if k_val > d_val else "➖ 未加分")
                    with col6:
                        st.metric("RSI(12日)", f"{rsi_val}", "🔥 加分" if rsi_val >= 50 else "➖ 未加分")
                            
                    st.markdown("---")
                    if pass_all: 
                        score = 55 + (25 if k_val > d_val and k_val <= 80 else 15 if k_val > d_val else 0) + (20 if rsi_val >= 50 else 0)
                        st.success(f"🎉 **診斷結果：強勢存活！** 該檔具備籌碼、低估值與高波動，綜合得分為 **{score} 分**！")
                    else: st.error("⚠️ **診斷結果：淘汰。** 核心籌碼、位階、估值或振幅未達標準。")
            except Exception as e: st.error(f"健檢過程發生錯誤: {e}")

# ==========================================
# 模組 3：個股時光機 (歷史回測)
# ==========================================
elif mode == "⏱️ 個股時光機 (歷史回測)":
    st.subheader("⏱️ 歷史回測驗證機")
    selected_stock = st.selectbox("選擇回測標的", options=list(STOCK_DICT.keys()))
    col_start, col_end = st.columns(2)
    with col_start: start_date = st.date_input("起始日", datetime.date(2025, 1, 1))
    with col_end: end_date = st.date_input("結束日", datetime.date.today())

    if st.button("🚀 啟動回測", type="primary"):
        stock_code = selected_stock.split(" ")[0]
        market = ".TW" if "(上市)" in selected_stock else ".TWO"
        
        with st.spinner("正在自雙引擎下載資料並回測..."):
            try:
                hist, source_name = get_kline_data(stock_code, market, days=400) 
                if hist.empty: st.error("⚠️ 雙引擎皆抓不到資料！")
                else:
                    hist['MA20'] = hist['Close'].rolling(20).mean()
                    hist['BIAS20'] = ((hist['Close'] - hist['MA20']) / hist['MA20']) * 100
                    low9, high9 = hist['Low'].rolling(9).min(), hist['High'].rolling(9).max()
                    hist['K'] = ((hist['Close'] - low9) / (high9 - low9) * 100).ewm(alpha=1/3, adjust=False).mean()
                    hist['D'] = hist['K'].ewm(alpha=1/3, adjust=False).mean()
                    
                    try:
                        backtest_data = hist.loc[start_date.strftime("%Y-%m-%d") : end_date.strftime("%Y-%m-%d")]
                    except:
                        backtest_data = hist
                        
                    current_capital, is_holding, current_trade, trade_history = ui_capital, False, {}, []
                    for date, row in backtest_data.iterrows():
                        date_str = date.strftime("%Y-%m-%d")
                        if pd.isna(row['MA20']) or pd.isna(row['K']): continue
                        high, low, close = row['High'], row['Low'], row['Close']
                        if not is_holding:
                            try:
                                prev_row = hist.loc[:date_str].iloc[-2]
                            except: continue
                            
                            if (row['K'] > row['D'] and prev_row['K'] <= prev_row['D']) and (-8 <= row['BIAS20'] <= 8):
                                shares = int(current_capital // close)
                                if shares > 0:
                                    current_trade = {'buy_date': date_str, 'buy_price': close, 'shares': shares, 'sl_price': close * (1 - (ui_sl / 100)), 'tp_active': False, 'max_profit': 0}
                                    is_holding = True
                        else:
                            buy_price, shares = current_trade['buy_price'], current_trade['shares']
                            profit_high, profit_low = (high - buy_price) * shares, (low - buy_price) * shares
                            exit_status, exit_price = "", 0
                            if low <= current_trade['sl_price'] and not current_trade['tp_active']:
                                exit_price, exit_status = current_trade['sl_price'], f"🔴 停損 (-{ui_sl}%)"
                            if profit_high >= ui_tp: current_trade['tp_active'] = True
                            if current_trade['tp_active']:
                                current_trade['max_profit'] = max(current_trade['max_profit'], profit_high)
                                if profit_low <= current_trade['max_profit'] - ui_drawdown:
                                    exit_price, exit_status = min(buy_price + ((current_trade['max_profit'] - ui_drawdown) / shares), high), "🟢 鎖利出場"
                            if exit_status:
                                profit = (exit_price - buy_price) * shares
                                current_capital += profit
                                trade_history.append({'買進日': current_trade['buy_date'], '賣出日': date_str, '買進價': round(buy_price, 2), '賣出價': round(exit_price, 2), '損益(元)': round(profit, 0), '餘額(元)': round(current_capital, 0), '原因': exit_status})
                                is_holding = False
                    if is_holding:
                        profit = (backtest_data.iloc[-1]['Close'] - current_trade['buy_price']) * current_trade['shares']
                        current_capital += profit
                        trade_history.append({'買進日': current_trade['buy_date'], '賣出日': '未平倉', '買進價': round(current_trade['buy_price'], 2), '賣出價': round(backtest_data.iloc[-1]['Close'], 2), '損益(元)': round(profit, 0), '餘額(元)': round(current_capital, 0), '原因': '⏳ 持股中'})
                    if trade_history:
                        df_report = pd.DataFrame(trade_history)
                        net_profit = current_capital - ui_capital
                        st.success(f"📊 總損益: {round(net_profit):,} 元 | 總報酬率: {(net_profit / ui_capital) * 100:.2f}% (資料源: {source_name})")
                        st.dataframe(df_report, use_container_width=True)
                    else: st.warning("未觸發任何進場條件。")
            except Exception as e: st.error(f"發生錯誤：{e}")

# ==========================================
# 模組 4：投資追蹤 (進出場管理)
# ==========================================
elif mode == "💼 投資追蹤 (進出場管理)":
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
                st.success(f"✅ 成功將 {t_stock} 登錄至投資組合！已自動存檔。")
                st.rerun()

    if not st.session_state['portfolio'].empty:
        st.markdown("### 📊 庫存部位監控")
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
                elif row['未實現損益(元)'] >= row['停利目標']: status_list.append("🟢 達標，啟動移動鎖利")
                else: status_list.append("⏳ 紀律持股中")
            df_p['目前狀態'] = status_list
            
        st.dataframe(df_p, use_container_width=True, hide_index=True)
        if st.button("🗑️ 清空所有紀錄", type="secondary"):
            st.session_state['portfolio'] = pd.DataFrame(columns=["股票", "買進日", "買進價", "股數", "停損價", "停利目標"])
            st.session_state['portfolio'].to_csv(PORTFOLIO_FILE, index=False, encoding='utf-8-sig')
            st.rerun()
    else: st.info("目前投資組合為空，請點擊上方「新增交易紀錄」開始管理您的庫存。")
