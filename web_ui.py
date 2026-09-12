import streamlit as st
import pandas as pd
import yfinance as yf
import datetime
import time
import requests
import warnings
import ssl
import urllib3

# --- 破解 SSL 防火牆與限流設定 ---
warnings.filterwarnings('ignore')
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context
session = requests.Session()
session.verify = False
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

# --- 網頁介面設定 ---
st.set_page_config(page_title="小資投本比 旗艦終端機", page_icon="🚀", layout="wide")
st.title("🏆 小資投本比 - 量化交易終端機")

# --- 🚀 建立暫存記憶體 ---
if 'radar_data' not in st.session_state: st.session_state['radar_data'] = None
if 'radar_msg' not in st.session_state: st.session_state['radar_msg'] = ""
if 'portfolio' not in st.session_state: 
    st.session_state['portfolio'] = pd.DataFrame(columns=["股票", "買進日", "買進價", "股數", "停損價", "停利目標"])

# --- 🌐 建立 TWSE/TPEx 官方股票字典 ---
@st.cache_data(ttl=86400)
def load_taiwan_stocks():
    stock_dict = {}
    try:
        res_twse = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", verify=False, timeout=5)
        if res_twse.status_code == 200:
            for item in res_twse.json():
                code, name = item.get('Code', ''), item.get('Name', '')
                if len(code) == 4 and code.isdigit(): stock_dict[f"{code} {name} (上市)"] = f"{code}.TW"
        res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", verify=False, timeout=5)
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

# --- 側邊欄：系統模式切換 ---
mode = st.sidebar.radio("切換系統模組", [
    "📡 實戰雷達 (今日選股)", 
    "🎯 個股健檢 (標的審查)", 
    "⏱️ 個股時光機 (歷史回測)", 
    "💼 投資追蹤 (進出場管理)"
])
st.sidebar.markdown("---")

# --- 📚 找回失去的技術說明書 ---
with st.sidebar.expander("📚 選股策略與技術指標說明", expanded=False):
    st.markdown("""
    **1. 投本比 (投信買超佔股本比例)**
    - **邏輯**：找出投信真正重金砸盤的中小型股。
    - **標準**：大於 0.4% 視為積極建倉，大於 1% 為狂熱買超。
    
    **2. 20日乖離率 (BIAS)**
    - **邏輯**：股價偏離月線的程度，用來避免追高或接刀。
    - **標準**：-8% ~ +8% 為安全區。超過 +10% 隨時可能拉回修正。
    
    **3. KD 指標 (9日)**
    - **邏輯**：判斷短線動能。K突破D為黃金交叉 (多頭)。
    - **標準**：數值在 20-80 之間最為健康，大於 80 提防超買。
    
    **4. RSI 指標 (12日)**
    - **邏輯**：買賣盤強弱力道。
    - **標準**：大於 50 偏多頭，低於 50 偏空頭。
    """)
st.sidebar.markdown("---")

# ==========================================
# 模組 1 & 2：共用技術指標濾網設定
# ==========================================
if mode in ["📡 實戰雷達 (今日選股)", "🎯 個股健檢 (標的審查)"]:
    st.sidebar.subheader("🎛️ 嚴格選股濾網設定")
    
    # 🎯 投本比靈魂濾網霸氣回歸！(置頂顯示)
    use_it_ratio = st.sidebar.checkbox("✅ 啟用【投本比】(雷達掃描專用)", True, help="大於 0.4% 通常代表投信積極建倉！")
    if use_it_ratio: ui_min_it_ratio = st.sidebar.slider("投本比下限 (%)", 0.1, 2.0, 0.4, 0.1)
    
    st.sidebar.markdown("---")
    use_bias = st.sidebar.checkbox("✅ 啟用【20日乖離率】", True)
    if use_bias: ui_bias_range = st.sidebar.slider("乖離率區間 (%)", -20.0, 30.0, (-8.0, 8.0), 1.0)
    
    use_kd = st.sidebar.checkbox("✅ 啟用【KD 指標】", True)
    if use_kd:
        ui_kd_golden = st.sidebar.checkbox("要求 K > D", True)
        ui_k_range = st.sidebar.slider("K值 區間", 0, 100, (20, 80), 5)
        
    use_rsi = st.sidebar.checkbox("✅ 啟用【RSI (12日)】", False)
    if use_rsi: ui_rsi_min = st.sidebar.slider("RSI 下限", 0, 100, 50, 5)

# ==========================================
# 模組 1：實戰雷達
# ==========================================
if mode == "📡 實戰雷達 (今日選股)":
    st.subheader("📡 全市場飆股掃描")
    data_source = st.radio("選擇數據引擎", ["⚡ XQ 檔案上傳 (極速/包含投本比)", "☁️ TWSE 雲端抓取 (自動計算投本比)"], horizontal=True)
    
    uploaded_file = None
    if data_source == "⚡ XQ 檔案上傳 (極速/包含投本比)":
        uploaded_file = st.file_uploader("📂 請上傳 XQ 匯出的 CSV 檔", type=['csv'])
    else:
        col1, col2 = st.columns(2)
        with col1: chk_twse, chk_tpex = st.checkbox("上市", True), st.checkbox("上櫃", True)
        with col2: ui_min_vol, ui_max_cap = st.slider("均量下限(張)", 100, 5000, 1000, 100), st.slider("股本上限(億)", 10, 500, 200, 10)

    if st.button("🚀 啟動雷達掃描", type="primary"):
        if data_source == "⚡ XQ 檔案上傳 (極速/包含投本比)":
            if uploaded_file is not None:
                with st.spinner("⚡ 正在解析檔案並強制轉換數值..."):
                    try:
                        df = pd.read_csv(uploaded_file, encoding='cp950', skiprows=3)
                        filtered_df = df.copy()
                        display_cols = ['代碼', '商品', '投本比(%)', 'SMA(20日)', 'BIAS(20日)', 'K值', 'D值', 'RSI(12日)']
                        
                        for col in ['BIAS(20日)', 'K值', 'D值', 'RSI(12日)']:
                            if col in filtered_df.columns:
                                filtered_df[col] = pd.to_numeric(filtered_df[col].astype(str).str.replace(',', ''), errors='coerce')
                        
                        if use_it_ratio:
                            col_it, col_cap = next((c for c in df.columns if '投信買' in c), None), next((c for c in df.columns if '股本' in c), None)
                            if col_it and col_cap:
                                filtered_df[col_it] = pd.to_numeric(filtered_df[col_it].astype(str).str.replace(',', ''), errors='coerce')
                                filtered_df[col_cap] = pd.to_numeric(filtered_df[col_cap].astype(str).str.replace(',', ''), errors='coerce')
                                filtered_df['投本比(%)'] = ((filtered_df[col_it] * 2.5) / (filtered_df[col_cap] * 10000000)) * 100
                                filtered_df = filtered_df[filtered_df['投本比(%)'].round(2) >= ui_min_it_ratio]
                        
                        if use_bias and 'BIAS(20日)' in filtered_df.columns:
                            filtered_df = filtered_df[(filtered_df['BIAS(20日)'] >= ui_bias_range[0]) & (filtered_df['BIAS(20日)'] <= ui_bias_range[1])]
                        if use_kd and 'K值' in filtered_df.columns and 'D值' in filtered_df.columns:
                            filtered_df = filtered_df[(filtered_df['K值'] >= ui_k_range[0]) & (filtered_df['K值'] <= ui_k_range[1])]
                            if ui_kd_golden: filtered_df = filtered_df[filtered_df['K值'] > filtered_df['D值']]
                        if use_rsi and 'RSI(12日)' in filtered_df.columns:
                            filtered_df = filtered_df[filtered_df['RSI(12日)'] >= ui_rsi_min]
                            
                        display_cols = [c for c in display_cols if c in filtered_df.columns]
                        if not filtered_df.empty:
                            filtered_df = filtered_df.rename(columns={'商品': '名稱', 'SMA(20日)': '20日月線價'})
                            if '投本比(%)' in filtered_df.columns: filtered_df = filtered_df.sort_values('投本比(%)', ascending=False)
                            st.session_state['radar_data'] = filtered_df[[c if c != '商品' else '名稱' for c in display_cols if c != 'SMA(20日)'] + ['20日月線價'] if 'SMA(20日)' in display_cols else display_cols]
                            st.session_state['radar_msg'] = f"🎉 掃描完成！為您精選出 {len(filtered_df)} 檔標的："
                        else:
                            st.session_state['radar_data'], st.session_state['radar_msg'] = pd.DataFrame(), "⚠️ 本次無符合條件標的。"
                    except Exception as e: st.error(f"⚠️ 解析錯誤：{e}")
            else: st.warning("⚠️ 請先上傳 CSV 檔案！")
        else:
            with st.spinner("☁️ 正在連線 TWSE 雲端抓取與計算投本比..."):
                today = datetime.datetime.now()
                last_date = today - datetime.timedelta(days=1) if today.weekday() < 5 else today - datetime.timedelta(days=today.weekday()-4)
                twse_date = last_date.strftime('%Y%m%d')
                tpex_date = f"{last_date.year - 1911}/{last_date.strftime('%m/%d')}"
                
                stock_list = []
                def fetch_data(url):
                    try: return requests.get(url, timeout=5, verify=False).json()
                    except: return None

                if chk_twse:
                    twse_data = fetch_data(f"https://www.twse.com.tw/fund/T86?response=json&date={twse_date}&selectType=ALL")
                    if twse_data:
                        for row in twse_data.get('data', []):
                            code, name = row[0].strip(), row[1].strip()
                            if code.startswith('00') or code.startswith('28'): continue
                            it_buy = int(row[10].replace(',', ''))
                            if len(code) == 4 and it_buy > 0: stock_list.append({'code': code, 'name': name, 'market': '.TW', 'it_buy': it_buy})
                if chk_tpex:
                    tpex_data = fetch_data(f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={tpex_date}")
                    if tpex_data:
                        for row in tpex_data.get('aaData', []):
                            code, name = str(row[0]).strip(), str(row[1]).strip()
                            if code.startswith('00') or code.startswith('28'): continue
                            it_buy = int(str(row[7]).replace(',', '').split('.')[0])
                            if len(code) == 4 and it_buy > 0: stock_list.append({'code': code, 'name': name, 'market': '.TWO', 'it_buy': it_buy})

                if not stock_list: st.session_state['radar_data'], st.session_state['radar_msg'] = pd.DataFrame(), "⚠️ 今日無投信買超紀錄。"
                else:
                    my_bar = st.progress(0, text="雲端技術面與投本比運算中...")
                    results = []
                    for i, stock in enumerate(stock_list):
                        if i % max(1, (len(stock_list) // 10)) == 0: my_bar.progress((i + 1) / len(stock_list))
                        try:
                            ticker = yf.Ticker(f"{stock['code']}{stock['market']}", session=session)
                            hist = ticker.history(start=(last_date - datetime.timedelta(days=60)).strftime('%Y-%m-%d'))
                            if len(hist) < 20: continue
                            close = float(hist['Close'].iloc[-1])
                            vol5 = float(hist['Volume'].rolling(5).mean().iloc[-1]) / 1000
                            shares = ticker.info.get('sharesOutstanding', 0)
                            if not shares or shares <= 0: continue
                            if round(shares / 10000000, 2) > ui_max_cap or vol5 < ui_min_vol: continue

                            pass_bias, pass_kd, pass_rsi, pass_it = True, True, True, True
                            data_dict = {'代碼': stock['code'], '名稱': stock['name'], '收盤價': round(close, 2)}
                            
                            # 🎯 TWSE 雲端投本比運算回歸！
                            real_it_ratio = round(((stock['it_buy'] * 2.5) / shares) * 100, 2)
                            data_dict['投本比(%)'] = real_it_ratio
                            if use_it_ratio and real_it_ratio < ui_min_it_ratio: pass_it = False
                            
                            ma20 = float(hist['Close'].rolling(20).mean().iloc[-1])
                            bias = round(((close - ma20) / ma20) * 100, 2)
                            data_dict['BIAS(20日)'] = bias
                            if use_bias and not (ui_bias_range[0] <= bias <= ui_bias_range[1]): pass_bias = False
                                
                            low9, high9 = hist['Low'].rolling(9).min(), hist['High'].rolling(9).max()
                            rsv = (hist['Close'] - low9) / (high9 - low9) * 100
                            hist['K'] = rsv.ewm(alpha=1/3, adjust=False).mean()
                            hist['D'] = hist['K'].ewm(alpha=1/3, adjust=False).mean()
                            k_val, d_val = round(hist['K'].iloc[-1], 2), round(hist['D'].iloc[-1], 2)
                            data_dict['K值'], data_dict['D值'] = k_val, d_val
                            if use_kd:
                                if not (ui_k_range[0] <= k_val <= ui_k_range[1]): pass_kd = False
                                if ui_kd_golden and (k_val <= d_val): pass_kd = False
                            
                            if pass_bias and pass_kd and pass_rsi and pass_it: results.append(data_dict)
                        except: continue
                    my_bar.empty()
                    if results:
                        df_export = pd.DataFrame(results)
                        df_export = df_export.sort_values('投本比(%)', ascending=False)
                        st.session_state['radar_data'] = df_export
                        st.session_state['radar_msg'] = f"🎉 雲端運算完成！共發現 {len(df_export)} 檔符合標的："
                    else: st.session_state['radar_data'], st.session_state['radar_msg'] = pd.DataFrame(), "⚠️ 根據嚴格標準，今日無符合條件標的。"

    if st.session_state['radar_data'] is not None:
        if not st.session_state['radar_data'].empty:
            st.success(st.session_state['radar_msg'])
            st.dataframe(st.session_state['radar_data'], use_container_width=True, hide_index=True)
        else: st.warning(st.session_state['radar_msg'])

# ==========================================
# 模組 2：個股健檢 (標的審查)
# ==========================================
elif mode == "🎯 個股健檢 (標的審查)":
    st.subheader("🎯 個股 X 光機 - 嚴格審查")
    st.markdown("輸入任何一檔股票，系統將比對左側的濾網標準，立刻為您診斷是否達到進場條件。")
    check_stock = st.selectbox("請選擇要健檢的標的", options=list(STOCK_DICT.keys()))
    
    if st.button("🩺 開始健檢", type="primary"):
        yahoo_ticker = STOCK_DICT[check_stock]
        with st.spinner(f"正在為 {check_stock} 進行全身技術面檢查..."):
            try:
                ticker = yf.Ticker(yahoo_ticker, session=session)
                hist = ticker.history(period="3mo")
                if hist.empty: st.error("⚠️ 無法取得歷史資料。")
                else:
                    close = round(hist['Close'].iloc[-1], 2)
                    ma20 = hist['Close'].rolling(window=20).mean()
                    bias = round(((hist['Close'] - ma20) / ma20).iloc[-1] * 100, 2)
                    
                    low9, high9 = hist['Low'].rolling(9).min(), hist['High'].rolling(9).max()
                    rsv = (hist['Close'] - low9) / (high9 - low9) * 100
                    hist['K'] = rsv.ewm(alpha=1/3, adjust=False).mean()
                    hist['D'] = hist['K'].ewm(alpha=1/3, adjust=False).mean()
                    k_val, d_val = round(hist['K'].iloc[-1], 2), round(hist['D'].iloc[-1], 2)
                    
                    delta = hist['Close'].diff()
                    gain = delta.clip(lower=0).ewm(alpha=1/12, adjust=False).mean()
                    loss = -delta.clip(upper=0).ewm(alpha=1/12, adjust=False).mean()
                    rs = gain / loss
                    rsi_val = round((100 - (100 / (1 + rs))).iloc[-1], 2)
                    
                    st.markdown(f"### 📊 【{check_stock}】 目前現價: {close} 元")
                    
                    pass_all = True
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if use_bias:
                            status = "✅ 通過" if ui_bias_range[0] <= bias <= ui_bias_range[1] else "❌ 失敗"
                            if status == "❌ 失敗": pass_all = False
                            st.metric("BIAS(20日)", f"{bias}%", status)
                        else: st.metric("BIAS(20日)", f"{bias}%", "未啟用濾網")
                            
                    with col2:
                        if use_kd:
                            status = "✅ 通過"
                            if not (ui_k_range[0] <= k_val <= ui_k_range[1]): status = "❌ 數值不在區間"
                            if ui_kd_golden and k_val <= d_val: status = "❌ 空頭排列"
                            if "❌" in status: pass_all = False
                            st.metric("KD 狀態", f"K:{k_val} D:{d_val}", status)
                        else: st.metric("KD 狀態", f"K:{k_val} D:{d_val}", "未啟用濾網")
                            
                    with col3:
                        if use_rsi:
                            status = "✅ 通過" if rsi_val >= ui_rsi_min else "❌ 失敗"
                            if status == "❌ 失敗": pass_all = False
                            st.metric("RSI(12日)", f"{rsi_val}", status)
                        else: st.metric("RSI(12日)", f"{rsi_val}", "未啟用濾網")
                            
                    st.markdown("---")
                    if pass_all: st.success("🎉 **診斷結果：完美！** 該檔股票完全符合您左側設定的所有技術面標準！")
                    else: st.error("⚠️ **診斷結果：未達標。** 目前尚未完全符合進場紀律，建議耐心等候訊號出現。")
            except Exception as e: st.error(f"健檢過程發生錯誤: {e}")

# ==========================================
# 模組 3：個股時光機
# ==========================================
elif mode == "⏱️ 個股時光機 (歷史回測)":
    st.sidebar.header("🎛️ 回測紀律設定")
    ui_capital = st.sidebar.number_input("初始本金 (元)", value=20000, step=5000)
    ui_tp = st.sidebar.number_input("啟動防守獲利門檻 (元)", value=5000, step=1000)
    ui_drawdown = st.sidebar.number_input("獲利回吐出場限制 (元)", value=2000, step=500)
    ui_sl = st.sidebar.number_input("強制停損比例 (%)", value=10, step=1)
    
    st.subheader("⏱️ 歷史回測驗證機")
    selected_stock = st.selectbox("選擇回測標的", options=list(STOCK_DICT.keys()))
    col_start, col_end = st.columns(2)
    with col_start: start_date = st.date_input("起始日", datetime.date(2025, 1, 1))
    with col_end: end_date = st.date_input("結束日", datetime.date.today())

    if st.button("🚀 啟動回測", type="primary"):
        yahoo_ticker = STOCK_DICT[selected_stock]
        with st.spinner("正在下載資料並回測..."):
            try:
                ticker = yf.Ticker(yahoo_ticker, session=session)
                hist = ticker.history(start=(start_date - datetime.timedelta(days=40)).strftime("%Y-%m-%d"))
                if hist.empty: st.error("⚠️ 抓不到資料！")
                else:
                    hist['MA20'] = hist['Close'].rolling(20).mean()
                    hist['BIAS20'] = ((hist['Close'] - hist['MA20']) / hist['MA20']) * 100
                    low9, high9 = hist['Low'].rolling(9).min(), hist['High'].rolling(9).max()
                    hist['K'] = ((hist['Close'] - low9) / (high9 - low9) * 100).ewm(alpha=1/3, adjust=False).mean()
                    hist['D'] = hist['K'].ewm(alpha=1/3, adjust=False).mean()
                    backtest_data = hist.loc[start_date.strftime("%Y-%m-%d") : end_date.strftime("%Y-%m-%d")]
                    current_capital, is_holding, current_trade, trade_history = ui_capital, False, {}, []
                    
                    for date, row in backtest_data.iterrows():
                        date_str = date.strftime("%Y-%m-%d")
                        if pd.isna(row['MA20']) or pd.isna(row['K']): continue
                        high, low, close = row['High'], row['Low'], row['Close']
                        
                        if not is_holding:
                            prev_row = hist.loc[:date_str].iloc[-2]
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
                        st.success(f"📊 總損益: {round(net_profit):,} 元 | 總報酬率: {(net_profit / ui_capital) * 100:.2f}%")
                        st.dataframe(df_report, use_container_width=True)
                    else: st.warning("未觸發任何進場條件。")
            except Exception as e: st.error(f"發生錯誤：{e}")

# ==========================================
# 模組 4：投資追蹤
# ==========================================
elif mode == "💼 投資追蹤 (進出場管理)":
    st.subheader("💼 我的量化投資組合")
    st.markdown("在此紀錄您跟隨系統買進的標的，系統將自動為您連線計算最新獲利狀態。")
    
    with st.expander("➕ 新增交易紀錄", expanded=False):
        with st.form("add_trade_form"):
            col1, col2 = st.columns(2)
            with col1:
                t_stock = st.selectbox("選擇買進標的", options=list(STOCK_DICT.keys()))
                t_date = st.date_input("買進日期", datetime.date.today())
                t_price = st.number_input("買進均價", min_value=0.0, step=1.0)
            with col2:
                t_shares = st.number_input("買進股數", min_value=1, value=1000, step=1000)
                t_sl = st.number_input("設定停損價位", min_value=0.0, step=1.0)
                t_tp = st.number_input("絕對金額停利啟動線 (元)", value=5000, step=1000)
                
            submitted = st.form_submit_button("📝 存入投資組合")
            if submitted:
                new_trade = {"股票": t_stock, "買進日": t_date.strftime("%Y-%m-%d"), "買進價": t_price, "股數": t_shares, "停損價": t_sl, "停利目標": t_tp}
                st.session_state['portfolio'] = pd.concat([st.session_state['portfolio'], pd.DataFrame([new_trade])], ignore_index=True)
                st.success(f"✅ 成功將 {t_stock} 登錄至投資組合！")
                st.rerun()

    if not st.session_state['portfolio'].empty:
        st.markdown("### 📊 庫存部位監控")
        df_p = st.session_state['portfolio'].copy()
        
        with st.spinner("🔄 正在連線交易所取得最新報價..."):
            live_prices = []
            for sym in df_p['股票']:
                try:
                    yahoo_ticker = STOCK_DICT.get(sym, "2330.TW")
                    ticker = yf.Ticker(yahoo_ticker, session=session)
                    live_p = ticker.history(period="1d")['Close'].iloc[-1]
                    live_prices.append(round(live_p, 2))
                except:
                    live_prices.append(0)
            
            df_p['最新現價'] = live_prices
            df_p['未實現損益(元)'] = ((df_p['最新現價'] - df_p['買進價']) * df_p['股數']).astype(int)
            df_p['報酬率(%)'] = (((df_p['最新現價'] - df_p['買進價']) / df_p['買進價']) * 100).round(2)
            
            status_list = []
            for _, row in df_p.iterrows():
                if row['最新現價'] <= row['停損價']: status_list.append("🔴 破停損，請平倉")
                elif row['未實現損益(元)'] >= row['停利目標']: status_list.append("🟢 達標，啟動移動鎖利")
                else: status_list.append("⏳ 紀律持股中")
            df_p['目前狀態'] = status_list
            
        st.dataframe(df_p, use_container_width=True, hide_index=True)
        if st.button("🗑️ 清空所有紀錄", type="secondary"):
            st.session_state['portfolio'] = pd.DataFrame(columns=["股票", "買進日", "買進價", "股數", "停損價", "停利目標"])
            st.rerun()
    else:
        st.info("目前投資組合為空，請點擊上方「新增交易紀錄」開始管理您的庫存。")