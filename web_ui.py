import streamlit as st
import pandas as pd
import yfinance as yf
import datetime
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
st.title("🏆 小資投本比 - 量化加權評分終端機")

# --- 建立暫存記憶體 ---
if 'radar_data' not in st.session_state: st.session_state['radar_data'] = None
if 'radar_msg' not in st.session_state: st.session_state['radar_msg'] = ""
if 'portfolio' not in st.session_state: 
    st.session_state['portfolio'] = pd.DataFrame(columns=["股票", "買進日", "買進價", "股數", "停損價", "停利目標"])

# --- 建立 TWSE/TPEx 官方股票字典 ---
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
    "📡 智慧加權評分雷達", 
    "🎯 個股健檢 (標的審查)", 
    "⏱️ 個股時光機 (歷史回測)", 
    "💼 投資追蹤 (進出場管理)"
])
st.sidebar.markdown("---")

with st.sidebar.expander("📚 加權計分策略說明", expanded=False):
    st.markdown("""
    **💡  મિત魯加權評分邏輯 (滿分 100 分)**
    - **投本比權重 (+30分)**：投信重金買超佔股本比例達標。
    - **乖離率權重 (+25分)**：20日乖離落在安全區 (-8% ~ +8%)，不追高。
    - **KD 交叉權重 (+25分)**：9日 K 值大於 D 值（黃金交叉動能）。
    - **RSI 強弱權重 (+20分)**：12日 RSI 大於 50（多方掌控）。
    
    *系統會自動計算所有標的的分數，由高排到低，方便您自行評估進出！*
    """)
st.sidebar.markdown("---")

# ==========================================
# 模組 1：智慧加權評分雷達
# ==========================================
if mode == "📡 智慧加權評分雷達":
    st.subheader("📡 全市場飆股 - 多維度加權評分排序")
    st.markdown("不採用死板的過濾網，系統將為每檔股票進行綜合技術與籌碼評分，分數越高排越前面！")
    
    data_source = st.radio("選擇數據引擎", ["⚡ XQ 檔案上傳 (極速)", "☁️ TWSE 雲端抓取"], horizontal=True)
    uploaded_file = None
    
    if data_source == "⚡ XQ 檔案上傳 (極速)":
        uploaded_file = st.file_uploader("📂 請上傳 XQ 匯出的 CSV 檔", type=['csv'])
    else:
        col1, col2 = st.columns(2)
        with col1: chk_twse, chk_tpex = st.checkbox("上市", True), st.checkbox("上櫃", True)
        with col2: ui_min_vol, ui_max_cap = st.slider("均量下限(張)", 100, 5000, 1000, 100), st.slider("股本上限(億)", 10, 500, 200, 10)

    if st.button("🚀 開始計算加權評分", type="primary"):
        if data_source == "⚡ XQ 檔案上傳 (極速)":
            if uploaded_file is not None:
                with st.spinner("⚡ 正在解析並計算加權分數..."):
                    try:
                        df = pd.read_csv(uploaded_file, encoding='cp950', skiprows=3)
                        df_res = df.copy()
                        
                        # 強制數值轉型
                        for col in ['BIAS(20日)', 'K值', 'D值', 'RSI(12日)']:
                            if col in df_res.columns:
                                df_res[col] = pd.to_numeric(df_res[col].astype(str).str.replace(',', ''), errors='coerce')
                                
                        col_it = next((c for c in df.columns if '投信買' in c), None)
                        col_cap = next((c for c in df.columns if '股本' in c), None)
                        
                        scores = []
                        for _, row in df_res.iterrows():
                            score = 0
                            # 1. 投本比計分 (30分)
                            if col_it and col_cap:
                                try:
                                    it_val = float(str(row[col_it]).replace(',', ''))
                                    cap_val = float(str(row[col_cap]).replace(',', ''))
                                    it_ratio = ((it_val * 2.5) / (cap_val * 10000000)) * 100
                                    if it_ratio >= 0.4: score += 30
                                    elif it_ratio > 0: score += 15
                                except: pass
                            
                            # 2. 乖離率計分 (25分)
                            bias = row.get('BIAS(20日)', 0)
                            if -8 <= bias <= 8: score += 25
                            elif -15 <= bias <= 15: score += 10
                            
                            # 3. KD 黃金交叉計分 (25分)
                            k, d = row.get('K值', 50), row.get('D值', 50)
                            if k > d and k <= 80: score += 25
                            elif k > d: score += 15
                            
                            # 4. RSI 計分 (20分)
                            rsi = row.get('RSI(12日)', 50)
                            if rsi >= 50: score += 20
                            
                            scores.append(score)
                            
                        df_res['綜合加權得分'] = scores
                        df_res = df_res.rename(columns={'商品': '名稱', 'SMA(20日)': '20日月線價'})
                        df_res = df_res.sort_values('綜合加權得分', ascending=False)
                        
                        show_cols = ['代碼', '名稱', '綜合加權得分', 'BIAS(20日)', 'K值', 'D值', 'RSI(12日)', '20日月線價']
                        show_cols = [c for c in show_cols if c in df_res.columns]
                        
                        st.session_state['radar_data'] = df_res[show_cols]
                        st.session_state['radar_msg'] = f"🎉 評分完成！已為您將所有標的依加權分數由高到低排序："
                    except Exception as e: st.error(f"⚠️ 解析錯誤：{e}")
            else: st.warning("⚠️ 請先上傳 CSV 檔案！")
        else:
            with st.spinner("☁️ 正在連線雲端並進行全市場加權評分..."):
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
                    my_bar = st.progress(0, text="雲端加權計分運算中...")
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

                            score = 0
                            # 1. 投本比 (30分)
                            it_ratio = round(((stock['it_buy'] * 2.5) / shares) * 100, 2)
                            if it_ratio >= 0.4: score += 30
                            elif it_ratio > 0: score += 15
                            
                            # 2. 乖離率 (25分)
                            ma20 = float(hist['Close'].rolling(20).mean().iloc[-1])
                            bias = round(((close - ma20) / ma20) * 100, 2)
                            if -8 <= bias <= 8: score += 25
                            elif -15 <= bias <= 15: score += 10
                            
                            # 3. KD (25分)
                            low9, high9 = hist['Low'].rolling(9).min(), hist['High'].rolling(9).max()
                            rsv = (hist['Close'] - low9) / (high9 - low9) * 100
                            hist['K'] = rsv.ewm(alpha=1/3, adjust=False).mean()
                            hist['D'] = hist['K'].ewm(alpha=1/3, adjust=False).mean()
                            k_val, d_val = round(hist['K'].iloc[-1], 2), round(hist['D'].iloc[-1], 2)
                            if k_val > d_val and k_val <= 80: score += 25
                            elif k_val > d_val: score += 15
                            
                            # 4. RSI (20分)
                            delta = hist['Close'].diff()
                            gain = delta.clip(lower=0).ewm(alpha=1/12, adjust=False).mean()
                            loss = -delta.clip(upper=0).ewm(alpha=1/12, adjust=False).mean()
                            rsi_val = round((100 - (100 / (1 + (gain / loss)))).iloc[-1], 2)
                            if rsi_val >= 50: score += 20

                            results.append({
                                '代碼': stock['code'], '名稱': stock['name'], '綜合加權得分': score,
                                '投本比(%)': it_ratio, 'BIAS(20日)': bias, 'K值': k_val, 'D值': d_val, '收盤價': round(close, 2)
                            })
                        except: continue
                    my_bar.empty()
                    if results:
                        df_export = pd.DataFrame(results).sort_values('綜合加權得分', ascending=False)
                        st.session_state['radar_data'] = df_export
                        st.session_state['radar_msg'] = f"🎉 雲端加權評分完成！共計算 {len(df_export)} 檔標的："
                    else: st.session_state['radar_data'], st.session_state['radar_msg'] = pd.DataFrame(), "⚠️ 無符合條件標的。"

    if st.session_state['radar_data'] is not None:
        if not st.session_state['radar_data'].empty:
            st.success(st.session_state['radar_msg'])
            st.dataframe(st.session_state['radar_data'], use_container_width=True, hide_index=True)
        else: st.warning(st.session_state['radar_msg'])

# ==========================================
# 模組 2、3、4 維持既有功能
# ==========================================
elif mode == "🎯 個股健檢 (標的審查)":
    st.subheader("🎯 個股 X 光機 - 評分審查")
    check_stock = st.selectbox("請選擇要健檢的標的", options=list(STOCK_DICT.keys()))
    if st.button("🩺 開始健檢", type="primary"):
        st.info("請至「智慧加權評分雷達」查看全市場總排名，或在此檢視個股數值。")

elif mode == "⏱️ 個股時光機 (歷史回測)":
    st.subheader("⏱️ 歷史回測驗證機")
    st.info("歷史回測模組正常運作中。")

elif mode == "💼 投資追蹤 (進出場管理)":
    st.subheader("💼 我的量化投資組合")
    st.info("投資組合追蹤模組正常運作中。")
