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
st.title("🏆 小資投本比 - 估值與波動度終極防禦終端機")

# --- 建立暫存記憶體 ---
if 'radar_data' not in st.session_state: st.session_state['radar_data'] = None
if 'radar_msg' not in st.session_state: st.session_state['radar_msg'] = ""
if 'portfolio' not in st.session_state: 
    st.session_state['portfolio'] = pd.DataFrame(columns=["股票", "買進日", "買進價", "股數", "停損價", "停利目標"])
if 'chat_history' not in st.session_state:
    st.session_state['chat_history'] = [{"role": "assistant", "content": "您好！我是您的專屬量化助理。您可以問我基礎的指標名詞；若在左側輸入 Gemini API 金鑰，我將解鎖為全能 AI 顧問，隨時為您分析大盤與個股！"}]

# 🌟 雙核心 AI 問答引擎 (V47 穩定對接 3.5 Flash-Lite)
def get_bot_answer(prompt, api_key=""):
    def rule_based_answer(text):
        if any(k in text for k in ['核心籌碼', '投本比', '籌碼']): return "**【核心籌碼 / 投本比】**\n指的是「投信買超張數佔公司發行股本的比例」。因為投信屬於主力法人，重金砸在中小型股時容易推升股價。系統要求投本比達標，就是確認這檔股票「有大人在照顧」。"
        elif any(k in text for k in ['乖離率', 'bias', '位階']): return "**【乖離率 (BIAS)】**\n指的是「目前股價距離 20 日均線的百分比」。正乖離太大容易追高被套；負乖離太大代表弱勢破底。限制在 ±8% 內，是為了確保買在安全的起漲點。"
        elif any(k in text for k in ['本益比', 'pe', '估值']): return "**【本益比 (PE Ratio)】**\n公式是「股價 ÷ 每股盈餘 (EPS)」。系統淘汰本益比過高的股票，是為了避免買到沒有基本面獲利支撐的「高空煙火股」。"
        elif any(k in text for k in ['振幅', '牛皮', '死魚', '波動']): return "**【5日均振幅】**\n指的是「最近5天內，每天最高價與最低價的差距比例」。如果股票每天上下波動不到 1% (牛皮股)，扣掉手續費就沒肉吃。設定下限是為了確保股票夠活潑。"
        elif any(k in text for k in ['kd', 'k值', 'd值']): return "**【KD 隨機指標】**\n判斷短線動能。K 值向上突破 D 值（黃金交叉）代表買盤強勁會加分；但若 K 值 > 80 進入超買區，系統會減少給分防禦追高風險。"
        elif 'rsi' in text: return "**【RSI 相對強弱指標】**\n大於 50 代表近期買盤強過賣盤，股票處於「多方控盤」的強勢格局，系統會給予 20 分趨勢加分。"
        elif any(k in text for k in ['淘汰', '為什麼淘汰']): return "**【為什麼會被淘汰？】**\n系統採用極度嚴格的雙殺機制。只要「投本比未達標」、「乖離率過高」、「本益比太貴」或「振幅太小」，只要踩中一個地雷，不管技術面多漂亮都會被無情淘汰。"
        else: return "這個問題很專業！不過我目前只載入了基礎記憶。如果您想讓我回答任意問題或分析個股，請在左側側邊欄輸入您的 Gemini API Key 喔！"

    if api_key:
        clean_key = api_key.strip()
        try:
            # 🚀 確實對準最新的 gemini-3.5-flash-lite 模型端點
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={clean_key}"
            sys_prompt = "你是一位精通台股、量化交易與程式碼的頂級交易助理。請用簡潔、專業且帶有一點實戰幽默的口吻，回答用戶的問題。用戶提問："
            payload = {"contents": [{"parts": [{"text": sys_prompt + prompt}]}]}
            
            # 使用 requests.post 並關閉 SSL 驗證 (verify=False)，避開企業防火牆干擾
            res = requests.post(url, headers={'Content-Type': 'application/json'}, json=payload, timeout=15, verify=False)
            
            if res.status_code == 200:
                return res.json()['candidates'][0]['content']['parts'][0]['text']
            else:
                return f"⚠️ 連結外星大腦失敗 (代碼: {res.status_code})。\n\n**Google 伺服器拒絕原因：**\n`{res.text}`\n\n切換為本地內建記憶：\n\n" + rule_based_answer(prompt.lower())
        except Exception as e:
            return f"⚠️ AI 腦神經連線異常 ({str(e)})，切換為本地內建記憶：\n\n" + rule_based_answer(prompt.lower())
    else:
        return rule_based_answer(prompt.lower())

def translate_to_zh(text):
    if not text or text in ['未知', '官方暫無資料，請參考證交所公開資訊觀測站。']: return text
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-TW&dt=t&q={requests.utils.quote(text)}"
        res = session.get(url, timeout=5)
        if res.status_code == 200:
            return "".join([sentence[0] for sentence in res.json()[0] if sentence[0]])
    except: pass
    return text 

@st.cache_data(ttl=86400)
def load_taiwan_stocks():
    stock_dict = {}
    try:
        res_twse = session.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", verify=False, timeout=15)
        if res_twse.status_code == 200:
            for item in res_twse.json():
                code, name = item.get('Code', ''), item.get('Name', '')
                if len(code) == 4 and code.isdigit(): stock_dict[f"{code} {name} (上市)"] = f"{code}.TW"
        res_tpex = session.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", verify=False, timeout=15)
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

@st.cache_data(ttl=86400)
def load_company_info():
    info_dict = {}
    try:
        res_twse = session.get("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", verify=False, timeout=15)
        if res_twse.status_code == 200:
            for item in res_twse.json():
                info_dict[str(item.get('公司代號', '')).strip()] = {
                    "sector": str(item.get('產業類別', '未知')).strip(),
                    "business": str(item.get('主要經營業務', '未知')).strip()
                }
    except: pass
    try:
        res_tpex = session.get("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", verify=False, timeout=15)
        if res_tpex.status_code == 200:
            for item in res_tpex.json():
                code = str(item.get('公司代號', item.get('SecuritiesCompanyCode', ''))).strip()
                info_dict[code] = {
                    "sector": str(item.get('產業類別', item.get('Industry', '未知'))).strip(),
                    "business": str(item.get('主要經營業務', item.get('MainBusiness', '未知'))).strip()
                }
    except: pass
    return info_dict

STOCK_DICT = load_taiwan_stocks()
INFO_DICT = load_company_info()

if len(STOCK_DICT) <= 3: load_taiwan_stocks.clear()
if not INFO_DICT: load_company_info.clear()

# --- 側邊欄：系統模式 ---
mode = st.sidebar.radio("切換系統模組", [
    "📡 嚴選加權評分雷達", 
    "🎯 個股健檢 (標的審查)", 
    "⏱️ 個股時光機 (歷史回測)", 
    "💼 投資追蹤 (進出場管理)"
])
st.sidebar.markdown("---")

st.sidebar.subheader("🧠 AI 大腦連線設定")
ui_gemini_key = st.sidebar.text_input("🔑 輸入 Gemini API Key (選填)", type="password", help="填入後，健檢底部的問答小助理將升級為無所不知的全能 AI 顧問！留空則使用內建基礎量化字典。")
st.sidebar.markdown("---")

if mode in ["📡 嚴選加權評分雷達", "🎯 個股健檢 (標的審查)"]:
    st.sidebar.subheader("🎛️ 嚴格核心過濾門檻")
    ui_min_it_ratio = st.sidebar.slider("投本比絕對下限 (%)", 0.1, 2.0, 0.4, 0.1, help="未達此標準直接剔除")
    ui_bias_max = st.sidebar.slider("乖離率容忍上限 (%)", 3.0, 15.0, 8.0, 0.5, help="超出此區間直接剔除")
    
    st.sidebar.markdown("---")
    st.sidebar.subheader("🛡️ 估值與波動度防禦")
    ui_max_pe = st.sidebar.slider("本益比上限 (倍)", 5.0, 60.0, 20.0, 1.0, help="防禦估值過高飆股")
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
    data_source = st.radio("選擇數據引擎", ["⚡ XQ 檔案上傳 (極速)", "☁️ TWSE 雲端抓取 (智慧回溯)"], horizontal=True)
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
            with st.spinner("☁️ 正在雲端進行波動度與嚴格過濾..."):
                stock_list, target_date = [], datetime.datetime.now()
                for _ in range(3):
                    try:
                        if chk_twse:
                            res = session.get(f"https://www.twse.com.tw/fund/T86?response=json&date={target_date.strftime('%Y%m%d')}&selectType=ALL", verify=False, timeout=15)
                            if res.status_code == 200 and 'data' in res.json():
                                for row in res.json()['data']:
                                    code, name, it_buy = row[0].strip(), row[1].strip(), int(row[10].replace(',', ''))
                                    if len(code) == 4 and not (code.startswith('00') or code.startswith('28')) and it_buy > 0: stock_list.append({'code': code, 'name': name, 'market': '.TW', 'it_buy': it_buy})
                        if chk_tpex and not stock_list:
                            res2 = session.get(f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={target_date.year - 1911}/{target_date.strftime('%m/%d')}", verify=False, timeout=15)
                            if res2.status_code == 200 and 'aaData' in res2.json():
                                for row in res2.json()['aaData']:
                                    code, name, it_buy = str(row[0]).strip(), str(row[1]).strip(), int(str(row[7]).replace(',', '').split('.')[0])
                                    if len(code) == 4 and not (code.startswith('00') or code.startswith('28')) and it_buy > 0: stock_list.append({'code': code, 'name': name, 'market': '.TWO', 'it_buy': it_buy})
                    except: pass
                    if stock_list: break
                    target_date -= datetime.timedelta(days=1)

                if not stock_list: st.session_state['radar_data'], st.session_state['radar_msg'] = pd.DataFrame(), "⚠️ 雲端暫無投信買超紀錄。"
                else:
                    my_bar, results = st.progress(0, text="執行估值與波動度防禦網中..."), []
                    for i, stock in enumerate(stock_list):
                        if i % max(1, (len(stock_list) // 10)) == 0: my_bar.progress((i + 1) / len(stock_list))
                        try:
                            ticker = yf.Ticker(f"{stock['code']}{stock['market']}", session=session)
                            info = ticker.info
                            pe_ratio = info.get('trailingPE') or info.get('forwardPE') or 0
                            if pe_ratio <= 0 or pe_ratio > ui_max_pe: continue
                            hist = ticker.history(start=(target_date - datetime.timedelta(days=60)).strftime('%Y-%m-%d'))
                            if len(hist) < 20 or float(hist['Close'].iloc[-1]) < 10.0: continue
                            avg_amp = round((((hist['High'] - hist['Low']) / hist['Close'].shift(1)) * 100).tail(5).mean(), 2)
                            if avg_amp < ui_min_amplitude: continue 
                            shares = info.get('sharesOutstanding', 0)
                            if not shares or shares <= 0 or round(shares / 10000000, 2) > ui_max_cap or (float(hist['Volume'].rolling(5).mean().iloc[-1]) / 1000) < ui_min_vol: continue
                            it_ratio = round(((stock['it_buy'] * 2.5) / shares) * 100, 2)
                            if it_ratio < ui_min_it_ratio: continue
                            bias = round(((float(hist['Close'].iloc[-1]) - float(hist['Close'].rolling(20).mean().iloc[-1])) / float(hist['Close'].rolling(20).mean().iloc[-1])) * 100, 2)
                            if not (-ui_bias_max <= bias <= ui_bias_max): continue
                            score = 55
                            low9, high9 = hist['Low'].rolling(9).min(), hist['High'].rolling(9).max()
                            hist['K'] = ((hist['Close'] - low9) / (high9 - low9) * 100).ewm(alpha=1/3, adjust=False).mean()
                            hist['D'] = hist['K'].ewm(alpha=1/3, adjust=False).mean()
                            k_val, d_val = round(hist['K'].iloc[-1], 2), round(hist['D'].iloc[-1], 2)
                            if k_val > d_val and k_val <= 80: score += 25
                            elif k_val > d_val: score += 15
                            delta = hist['Close'].diff()
                            rsi_val = round((100 - (100 / (1 + (delta.clip(lower=0).ewm(alpha=1/12, adjust=False).mean() / -delta.clip(upper=0).ewm(alpha=1/12, adjust=False).mean())))).iloc[-1], 2)
                            if rsi_val >= 50: score += 20
                            results.append({'代碼': stock['code'], '名稱': stock['name'], '綜合得分': score, '投本比(%)': it_ratio, '本益比': round(pe_ratio, 2), '5日均振幅(%)': avg_amp, 'BIAS(20日)': bias, 'K值': k_val, 'RSI(12日)': rsi_val})
                        except: continue
                    my_bar.empty()
                    if results:
                        st.session_state['radar_data'] = pd.DataFrame(results).sort_values('綜合得分', ascending=False)
                        st.session_state['radar_msg'] = f"🎉 嚴選完成！排除牛皮股後，共存活 {len(st.session_state['radar_data'])} 檔標的："
                    else: st.session_state['radar_data'], st.session_state['radar_msg'] = pd.DataFrame(), "⚠️ 條件過於嚴格，本次無標的存活。"

    if st.session_state['radar_data'] is not None:
        if not st.session_state['radar_data'].empty:
            st.success(st.session_state['radar_msg'])
            st.dataframe(st.session_state['radar_data'], use_container_width=True, hide_index=True)
        else: st.warning(st.session_state['radar_msg'])

# ==========================================
# 模組 2：個股健檢 (標的審查)
# ==========================================
elif mode == "🎯 個股健檢 (標的審查)":
    st.subheader("🎯 個股 X 光機 - 六大維度與基本面審查")
    st.markdown("比對左側的濾網標準，為您診斷是否具備實戰條件。")
    check_stock = st.selectbox("請選擇要健檢的標的", options=list(STOCK_DICT.keys()))
    
    if st.button("🩺 開始健檢", type="primary"):
        yahoo_ticker = STOCK_DICT[check_stock]
        stock_code = check_stock.split(" ")[0]
        market = ".TW" if "(上市)" in check_stock else ".TWO"
        
        with st.spinner(f"正在為 {check_stock} 進行基本面與技術面掃描..."):
            try:
                ticker = yf.Ticker(yahoo_ticker, session=session)
                hist = ticker.history(period="3mo")
                info = ticker.info
                
                if hist.empty: st.error("⚠️ 無法取得歷史資料。")
                else:
                    close = round(hist['Close'].iloc[-1], 2)
                    ma20 = hist['Close'].rolling(window=20).mean()
                    bias = round(((hist['Close'] - ma20) / ma20).iloc[-1] * 100, 2)
                    pe_ratio = info.get('trailingPE') or info.get('forwardPE') or 0
                    hist['Amplitude'] = ((hist['High'] - hist['Low']) / hist['Close'].shift(1)) * 100
                    avg_amp = round(hist['Amplitude'].tail(5).mean(), 2)
                    low9, high9 = hist['Low'].rolling(9).min(), hist['High'].rolling(9).max()
                    hist['K'] = ((hist['Close'] - low9) / (high9 - low9) * 100).ewm(alpha=1/3, adjust=False).mean()
                    hist['D'] = hist['K'].ewm(alpha=1/3, adjust=False).mean()
                    k_val, d_val = round(hist['K'].iloc[-1], 2), round(hist['D'].iloc[-1], 2)
                    delta = hist['Close'].diff()
                    rsi_val = round((100 - (100 / (1 + (delta.clip(lower=0).ewm(alpha=1/12, adjust=False).mean() / -delta.clip(upper=0).ewm(alpha=1/12, adjust=False).mean())))).iloc[-1], 2)
                    
                    it_buy, target_date = 0, datetime.datetime.now()
                    for _ in range(3):
                        try:
                            if market == ".TW":
                                twse_data = session.get(f"https://www.twse.com.tw/fund/T86?response=json&date={target_date.strftime('%Y%m%d')}&selectType=ALL", verify=False, timeout=15).json()
                                for row in twse_data.get('data', []):
                                    if row[0].strip() == stock_code: it_buy = int(row[10].replace(',', '')); break
                            else:
                                tpex_data = session.get(f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={target_date.year - 1911}/{target_date.strftime('%m/%d')}", verify=False, timeout=15).json()
                                for row in tpex_data.get('aaData', []):
                                    if str(row[0]).strip() == stock_code: it_buy = int(str(row[7]).replace(',', '').split('.')[0]); break
                        except: pass
                        if it_buy > 0: break
                        target_date -= datetime.timedelta(days=1)
                        
                    shares = info.get('sharesOutstanding', 0)
                    real_it_ratio = round(((it_buy * 2.5) / shares) * 100, 2) if shares > 0 and it_buy > 0 else 0.0
                    
                    st.markdown(f"### 📊 【{check_stock}】 目前現價: {close} 元")
                    
                    with st.expander("📖 公司基本面與業務簡介", expanded=True):
                        comp_info = INFO_DICT.get(stock_code, {})
                        sector_tw, business_tw = comp_info.get('sector', ''), comp_info.get('business', '')
                        if not sector_tw or sector_tw == '未知':
                            st.warning("🔄 啟用備援資料庫：正在為您將外文業務說明自動翻譯成繁體中文...")
                            raw_sector, raw_business = info.get('sector', '未知'), info.get('longBusinessSummary', '未知')
                            sector_tw = translate_to_zh(raw_sector) if raw_sector != '未知' else raw_sector
                            business_tw = translate_to_zh(raw_business) if raw_business != '未知' else raw_business
                        market_cap = info.get('marketCap', 0)
                        st.markdown(f"**🏭 產業類別：** {sector_tw}\n\n**💰 預估市值：** {round(market_cap / 100000000, 2)} 億台幣" if market_cap else "未知")
                        st.markdown(f"**📝 主要業務：** {business_tw}")
                    
                    pass_all = True
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        status = "✅ 過關" if real_it_ratio >= ui_min_it_ratio else "❌ 淘汰"
                        if status == "❌ 淘汰": pass_all = False
                        st.metric(f"投本比 (>{ui_min_it_ratio}%)", f"{real_it_ratio}%", status)
                    with col2:
                        status = "✅ 過關" if -ui_bias_max <= bias <= ui_bias_max else "❌ 淘汰"
                        if status == "❌ 淘汰": pass_all = False
                        st.metric(f"BIAS (±{ui_bias_max}%)", f"{bias}%", status)
                    with col3:
                        status = "✅ 過關" if 0 < pe_ratio <= ui_max_pe else "❌ 淘汰"
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

    # 🤖 雙核心聊天機器人 UI 區塊
    st.markdown("---")
    st.subheader("🤖 AI 健檢問答助理")
    if ui_gemini_key:
        st.caption("🟢 已連線 Gemini 大腦！您可以問我任何關於台股、技術分析或財報的問題。")
    else:
        st.caption("🟡 目前使用本地字典。想要更聰明的回答？請在左側輸入您的 Gemini API Key！")
    
    for msg in st.session_state['chat_history']:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    if prompt := st.chat_input("想了解什麼指標或是個股呢？交給我吧！"):
        st.session_state['chat_history'].append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        
        answer = get_bot_answer(prompt, ui_gemini_key)
        
        st.session_state['chat_history'].append({"role": "assistant", "content": answer})
        with st.chat_message("assistant"): st.markdown(answer)

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
# 模組 4：投資追蹤 (進出場管理)
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
                t_price = st.number_input("買進均價", min_value=0.01, value=50.0, step=1.0)
            with col2:
                t_shares = st.number_input("買進股數", min_value=1, value=1000, step=1000)
                t_sl = st.number_input("設定停損價位", min_value=0.0, step=1.0)
                t_tp = st.number_input("絕對金額停利啟動線 (元)", value=5000, step=1000)
                
            if st.form_submit_button("📝 存入投資組合"):
                new_trade = {"股票": t_stock, "買進日": t_date.strftime("%Y-%m-%d"), "買進價": t_price, "股數": t_shares, "停損價": t_sl, "停利目標": t_tp}
                st.session_state['portfolio'] = pd.concat([st.session_state['portfolio'], pd.DataFrame([new_trade])], ignore_index=True)
                st.success(f"✅ 成功將 {t_stock} 登錄至投資組合！")
                st.rerun()

    if not st.session_state['portfolio'].empty:
        st.markdown("### 📊 庫存部位監控")
        df_p = st.session_state['portfolio'].copy()
        with st.spinner("🔄 正在連線交易所取得最新報價..."):
            live_prices = []
            for idx, row in df_p.iterrows():
                try:
                    hist = yf.Ticker(STOCK_DICT.get(row['股票'], "2330.TW"), session=session).history(period="5d")
                    live_prices.append(round(hist['Close'].iloc[-1], 2) if not hist.empty else row['買進價'])
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
            st.rerun()
    else: st.info("目前投資組合為空，請點擊上方「新增交易紀錄」開始管理您的庫存。")
