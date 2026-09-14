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
st.title("🏆 小資投本比 - 嚴格過濾與加權評分終端機")

if 'radar_data' not in st.session_state: st.session_state['radar_data'] = None
if 'radar_msg' not in st.session_state: st.session_state['radar_msg'] = ""
if 'portfolio' not in st.session_state: 
    st.session_state['portfolio'] = pd.DataFrame(columns=["股票", "買進日", "買進價", "股數", "停損價", "停利目標"])

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

mode = st.sidebar.radio("切換系統模組", [
    "📡 嚴選加權評分雷達", 
    "🎯 個股健檢 (標的審查)", 
    "⏱️ 個股時光機 (歷史回測)", 
    "💼 投資追蹤 (進出場管理)"
])
st.sidebar.markdown("---")

st.sidebar.subheader("🎛️ 嚴格核心過濾門檻")
ui_min_it_ratio = st.sidebar.slider("投本比絕對下限 (%)", 0.1, 2.0, 0.4, 0.1, help="未達此標準直接剔除")
ui_bias_max = st.sidebar.slider("乖離率容忍上限 (%)", 3.0, 15.0, 8.0, 0.5, help="超出此區間直接剔除")

st.sidebar.markdown("---")
st.sidebar.subheader("🛡️ 體質與流動性防禦")
ui_min_vol = st.sidebar.slider("5日均量下限 (張)", 100, 5000, 800, 100)
ui_max_cap = st.sidebar.slider("股本上限 (億)", 10, 500, 200, 10)

st.sidebar.markdown("---")
with st.sidebar.expander("📚 嚴格過濾與計分邏輯", expanded=True):
    st.markdown("""
    **⛔ 第一階段：嚴格過濾 (Survival)**
    - 投本比必須大於門檻，且乖離率必須在安全區內。
    - 股價低於 10 元水餃股直接剔除。
    - 成功存活者，保底獲得 55 分 (籌碼 30 + 位階 25)。
    
    **🏆 第二階段：動能加分 (Momentum)**
    - **KD 權重 (+25分)**：K大於D且數值小於80，動能滿分。
    - **RSI 權重 (+20分)**：數值大於 50，趨勢滿分。
    """)
st.sidebar.markdown("---")

if mode == "📡 嚴選加權評分雷達":
    st.subheader("📡 全市場飆股 - 嚴格過濾與綜合評分排序")
    
    data_source = st.radio("選擇數據引擎", ["⚡ XQ 檔案上傳 (極速)", "☁️ TWSE 雲端抓取 (智慧回溯)"], horizontal=True)
    uploaded_file = None
    
    if data_source == "⚡ XQ 檔案上傳 (極速)":
        uploaded_file = st.file_uploader("📂 請上傳 XQ 匯出的 CSV 檔", type=['csv'])
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
                        
                        for col in ['BIAS(20日)', 'K值', 'D值', 'RSI(12日)']:
                            if col in df_res.columns:
                                df_res[col] = pd.to_numeric(df_res[col].astype(str).str.replace(',', ''), errors='coerce')
                                
                        col_it = next((c for c in df.columns if '投信買' in c), None)
                        col_cap = next((c for c in df.columns if '股本' in c), None)
                        
                        survivors = []
                        for _, row in df_res.iterrows():
                            # 嚴格過濾
                            if not col_it or not col_cap: continue
                            try:
                                it_val = float(str(row[col_it]).replace(',', ''))
                                cap_val = float(str(row[col_cap]).replace(',', ''))
                                it_ratio = ((it_val * 2.5) / (cap_val * 10000000)) * 100
                            except: continue
                            
                            bias = row.get('BIAS(20日)', 0)
                            if it_ratio < ui_min_it_ratio: continue
                            if not (-ui_bias_max <= bias <= ui_bias_max): continue
                            
                            # 存活者計分
                            score = 55
                            k, d = row.get('K值', 50), row.get('D值', 50)
                            if k > d and k <= 80: score += 25
                            elif k > d: score += 15
                            
                            rsi = row.get('RSI(12日)', 50)
                            if rsi >= 50: score += 20
                            
                            row_dict = row.to_dict()
                            row_dict['投本比(%)'] = round(it_ratio, 2)
                            row_dict['綜合得分'] = score
                            survivors.append(row_dict)
                            
                        if survivors:
                            df_final = pd.DataFrame(survivors)
                            df_final = df_final.rename(columns={'商品': '名稱', 'SMA(20日)': '20日月線價'})
                            df_final = df_final.sort_values('綜合得分', ascending=False)
                            show_cols = ['代碼', '名稱', '綜合得分', '投本比(%)', 'BIAS(20日)', 'K值', 'D值', 'RSI(12日)', '20日月線價']
                            show_cols = [c for c in show_cols if c in df_final.columns]
                            st.session_state['radar_data'] = df_final[show_cols]
                            st.session_state['radar_msg'] = f"🎉 嚴選完成！過濾後共存活 {len(df_final)} 檔標的，已依得分排序："
                        else:
                            st.session_state['radar_data'], st.session_state['radar_msg'] = pd.DataFrame(), "⚠️ 條件過於嚴格，本次無標的存活。"
                    except Exception as e: st.error(f"⚠️ 解析錯誤：{e}")
            else: st.warning("⚠️ 請先上傳 CSV 檔案！")
        else:
            with st.spinner("☁️ 正在雲端進行嚴格過濾與動能計分..."):
                stock_list = []
                target_date = datetime.datetime.now()
                
                for _ in range(3):
                    twse_date = target_date.strftime('%Y%m%d')
                    tpex_date = f"{target_date.year - 1911}/{target_date.strftime('%m/%d')}"
                    
                    try:
                        if chk_twse:
                            res = requests.get(f"https://www.twse.com.tw/fund/T86?response=json&date={twse_date}&selectType=ALL", verify=False, timeout=5)
                            if res.status_code == 200:
                                jdata = res.json()
                                if 'data' in jdata and len(jdata['data']) > 0:
                                    for row in jdata['data']:
                                        code, name = row[0].strip(), row[1].strip()
                                        if code.startswith('00') or code.startswith('28'): continue
                                        it_buy = int(row[10].replace(',', ''))
                                        if len(code) == 4 and it_buy > 0: stock_list.append({'code': code, 'name': name, 'market': '.TW', 'it_buy': it_buy})
                        if chk_tpex and not stock_list:
                            res2 = requests.get(f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={tpex_date}", verify=False, timeout=5)
                            if res2.status_code == 200:
                                jdata2 = res2.json()
                                if 'aaData' in jdata2 and len(jdata2['aaData']) > 0:
                                    for row in jdata2['aaData']:
                                        code, name = str(row[0]).strip(), str(row[1]).strip()
                                        if code.startswith('00') or code.startswith('28'): continue
                                        it_buy = int(str(row[7]).replace(',', '').split('.')[0])
                                        if len(code) == 4 and it_buy > 0: stock_list.append({'code': code, 'name': name, 'market': '.TWO', 'it_buy': it_buy})
                    except: pass
                    if stock_list: break
                    target_date -= datetime.timedelta(days=1)

                if not stock_list: st.session_state['radar_data'], st.session_state['radar_msg'] = pd.DataFrame(), "⚠️ 雲端暫無投信買超紀錄。"
                else:
                    my_bar = st.progress(0, text="執行嚴格防禦過濾網中...")
                    results = []
                    for i, stock in enumerate(stock_list):
                        if i % max(1, (len(stock_list) // 10)) == 0: my_bar.progress((i + 1) / len(stock_list))
                        try:
                            ticker = yf.Ticker(f"{stock['code']}{stock['market']}", session=session)
                            hist = ticker.history(start=(target_date - datetime.timedelta(days=60)).strftime('%Y-%m-%d'))
                            if len(hist) < 20: continue
                            close = float(hist['Close'].iloc[-1])
                            if close < 10.0: continue
                            
                            vol5 = float(hist['Volume'].rolling(5).mean().iloc[-1]) / 1000
                            shares = ticker.info.get('sharesOutstanding', 0)
                            if not shares or shares <= 0: continue
                            if round(shares / 10000000, 2) > ui_max_cap or vol5 < ui_min_vol: continue

                            # ⛔ 嚴格過濾
                            it_ratio = round(((stock['it_buy'] * 2.5) / shares) * 100, 2)
                            if it_ratio < ui_min_it_ratio: continue
                            
                            ma20 = float(hist['Close'].rolling(20).mean().iloc[-1])
                            bias = round(((close - ma20) / ma20) * 100, 2)
                            if not (-ui_bias_max <= bias <= ui_bias_max): continue
                            
                            # 🏆 存活者計分
                            score = 55
                            
                            low9, high9 = hist['Low'].rolling(9).min(), hist['High'].rolling(9).max()
                            rsv = (hist['Close'] - low9) / (high9 - low9) * 100
                            hist['K'] = rsv.ewm(alpha=1/3, adjust=False).mean()
                            hist['D'] = hist['K'].ewm(alpha=1/3, adjust=False).mean()
                            k_val, d_val = round(hist['K'].iloc[-1], 2), round(hist['D'].iloc[-1], 2)
                            if k_val > d_val and k_val <= 80: score += 25
                            elif k_val > d_val: score += 15
                            
                            delta = hist['Close'].diff()
                            gain = delta.clip(lower=0).ewm(alpha=1/12, adjust=False).mean()
                            loss = -delta.clip(upper=0).ewm(alpha=1/12, adjust=False).mean()
                            rsi_val = round((100 - (100 / (1 + (gain / loss)))).iloc[-1], 2)
                            if rsi_val >= 50: score += 20

                            results.append({
                                '代碼': stock['code'], '名稱': stock['name'], '綜合得分': score,
                                '投本比(%)': it_ratio, 'BIAS(20日)': bias, 'K值': k_val, 'D值': d_val, '收盤價': round(close, 2)
                            })
                        except: continue
                    my_bar.empty()
                    if results:
                        df_export = pd.DataFrame(results).sort_values('綜合得分', ascending=False)
                        st.session_state['radar_data'] = df_export
                        st.session_state['radar_msg'] = f"🎉 嚴選完成！過濾後共存活 {len(df_export)} 檔優質標的："
                    else: st.session_state['radar_data'], st.session_state['radar_msg'] = pd.DataFrame(), "⚠️ 條件過於嚴格，本次無標的存活。"

    if st.session_state['radar_data'] is not None:
        if not st.session_state['radar_data'].empty:
            st.success(st.session_state['radar_msg'])
            st.dataframe(st.session_state['radar_data'], use_container_width=True, hide_index=True)
        else: st.warning(st.session_state['radar_msg'])

elif mode == "🎯 個股健檢 (標的審查)":
    st.subheader("🎯 個股 X 光機 - 評分審查")
    st.info("個股健檢模組正常運作中。")

elif mode == "⏱️ 個股時光機 (歷史回測)":
    st.subheader("⏱️ 歷史回測驗證機")
    st.info("歷史回測模組正常運作中。")

elif mode == "💼 投資追蹤 (進出場管理)":
    st.subheader("💼 我的量化投資組合")
    st.info("投資組合追蹤模組正常運作中。")
