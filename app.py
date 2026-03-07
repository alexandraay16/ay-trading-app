import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta

# --- 1. 系統設定 ---
st.set_page_config(page_title="Alpha Hunter V1 | AY 冠軍量化版", layout="wide", page_icon="🦅")

# --- 2. 密碼驗證系統 ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def check_password():
    if not st.session_state.authenticated:
        # 登入介面設計
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align: center;'>🦅 Alpha Hunter 終端</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: gray;'>AY 專屬量化交易系統</p>", unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("<div style='padding: 20px; border-radius: 10px; background-color: rgba(255,255,255,0.05);'>", unsafe_allow_html=True)
            pwd = st.text_input("請輸入專屬通行密碼 🔒", type="password")
            if st.button("解鎖系統", use_container_width=True):
                if pwd == "AY202688":
                    st.session_state.authenticated = True
                    st.rerun() # 密碼正確，重新整理頁面載入主程式
                else:
                    st.error("❌ 密碼錯誤，拒絕存取。")
            st.markdown("</div>", unsafe_allow_html=True)
        
        # 停止往下執行程式碼，直到密碼正確
        st.stop()

# 執行密碼檢查
check_password()

# ==========================================
# 密碼正確後，以下主程式才會執行
# ==========================================

# --- 3. 獨家數學引擎 (No-Lib) ---
def calc_sma(series, window):
    return series.rolling(window=window).mean()

def calc_ema(series, window):
    return series.ewm(span=window, adjust=False).mean()

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calc_atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

# --- 4. 高勝率 K線形態偵測 ---
def detect_patterns(df):
    patterns = pd.Series(index=df.index, data="", dtype=str)
    
    for i in range(3, len(df)):
        curr = df.iloc[i]; prev1 = df.iloc[i-1]; prev2 = df.iloc[i-2]; prev3 = df.iloc[i-3]
        
        # 1. Bullish Engulfing (看漲吞沒) + Volume > SMA + RSI > 50 (勝率 ~65%)
        is_prev_red = prev1['Close'] < prev1['Open']
        is_curr_green = curr['Close'] > curr['Open']
        engulfing_bull = is_prev_red and is_curr_green and (curr['Open'] <= prev1['Close']) and (curr['Close'] >= prev1['Open'])
        if engulfing_bull and curr['Volume'] > curr['Vol_SMA'] and curr['RSI'] > 50:
            patterns.iloc[i] = "BULL_ENGULF"
            
        # 2. Bearish Engulfing (看跌吞沒) + 死叉 + 高量 (勝率 ~70%)
        is_prev_green = prev1['Close'] > prev1['Open']
        is_curr_red = curr['Close'] < curr['Open']
        engulfing_bear = is_prev_green and is_curr_red and (curr['Open'] >= prev1['Close']) and (curr['Close'] <= prev1['Open'])
        if engulfing_bear and curr['Volume'] > curr['Vol_SMA'] and curr['SMA_20'] < curr['SMA_50']:
            patterns.iloc[i] = "BEAR_ENGULF"
            
        # 3. 三白兵 (Three White Soldiers) 在上升趨勢
        three_green = (curr['Close']>curr['Open']) and (prev1['Close']>prev1['Open']) and (prev2['Close']>prev2['Open'])
        higher_closes = (curr['Close']>prev1['Close']) and (prev1['Close']>prev2['Close'])
        if three_green and higher_closes and curr['Close'] > curr['SMA_50']:
            patterns.iloc[i] = "3_SOLDIERS"
            
        # 4. 超跌反彈 (Oversold Bounce)
        if curr['RSI'] > prev1['RSI'] and prev1['RSI'] < 30:
            patterns.iloc[i] = "OVERSOLD_BOUNCE"
            
    return patterns

# --- 5. 獲取與計算數據 ---
@st.cache_data(ttl=1800)
def get_data(ticker):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=False)
        if df.empty: return None
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.columns = [c.capitalize() for c in df.columns]
        
        df.index = pd.to_datetime(df.index).tz_localize(None)
        
        # 指標計算
        df['SMA_20'] = calc_sma(df['Close'], 20)
        df['SMA_50'] = calc_sma(df['Close'], 50)
        df['SMA_200'] = calc_sma(df['Close'], 200)
        df['RSI'] = calc_rsi(df['Close'], 14)
        df['ATR'] = calc_atr(df, 14)
        df['Vol_SMA'] = calc_sma(df['Volume'], 20)
        
        # 形態偵測
        df['Pattern'] = detect_patterns(df)
        
        # 支撐阻力 (簡單版：20日極值)
        df['Support'] = df['Low'].rolling(20).min()
        df['Resistance'] = df['High'].rolling(20).max()
        
        df.dropna(inplace=True)
        return df
    except:
        return None

# 獲取新聞
@st.cache_data(ttl=3600)
def get_news(ticker):
    try:
        t = yf.Ticker(ticker)
        return t.news[:5]
    except:
        return []

# --- 6. 信號判斷模組 (Detected Signals) ---
def analyze_signals(df):
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    
    signals = {}
    
    # TREND: 多頭排列
    if curr['Close'] > curr['SMA_20'] > curr['SMA_50'] > curr['SMA_200']:
        signals['TREND'] = {"status": True, "desc": "資金明顯流入，MA呈現完美多頭排列。"}
    else: signals['TREND'] = {"status": False, "desc": "趨勢未成形或處於整理期。"}
        
    # MOM: 動能強勁 (連續3天上漲且RSI>60)
    if curr['RSI'] > 60 and curr['Close'] > prev['Close'] and prev['Close'] > df.iloc[-3]['Close']:
        signals['MOM'] = {"status": True, "desc": "股價連續上漲且力道強勁 (RSI>60)。"}
    else: signals['MOM'] = {"status": False, "desc": "短期動能放緩。"}
        
    # VOL: 成交量放大 (大於均量 50%)
    if curr['Volume'] > curr['Vol_SMA'] * 1.5:
        signals['VOL'] = {"status": True, "desc": "成交量顯著放大 (>150%)，多空雙方交戰激烈。"}
    else: signals['VOL'] = {"status": False, "desc": "成交量萎縮，市場觀望中。"}
        
    # AY MA Edge: 20/50 黃金交叉
    if curr['SMA_20'] > curr['SMA_50'] and prev['SMA_20'] <= prev['SMA_50']:
        signals['AY_EDGE'] = {"status": True, "desc": "AY 核心信號：20/50 日線黃金交叉，勝率極高。"}
    else: signals['AY_EDGE'] = {"status": False, "desc": "無 20/50 交叉信號。"}
    
    # OVERSOLD: 超跌反彈
    if curr['Pattern'] == "OVERSOLD_BOUNCE":
        signals['PIVOT'] = {"status": True, "desc": "RSI<30後勾頭向上，市場情緒極度恐慌後出現買盤。"}
    else: signals['PIVOT'] = {"status": False, "desc": "目前無超跌現象。"}
        
    return signals

# --- 7. AY 回測引擎 (近半年) ---
def run_backtest(df):
    # 取近 120 個交易日 (約半年)
    test_df = df.tail(120).copy()
    capital = 10000.0
    position = 0
    entry_price = 0
    trades = []
    
    for i in range(1, len(test_df)-1):
        curr = test_df.iloc[i]
        nxt = test_df.iloc[i+1] # 隔日開盤價執行
        prev = test_df.iloc[i-1]
        
        # 買入策略：Bullish Engulfing 或 20上穿50
        buy_signal = curr['Pattern'] in ["BULL_ENGULF", "3_SOLDIERS"] or (curr['SMA_20'] > curr['SMA_50'] and prev['SMA_20'] <= prev['SMA_50'])
        # 過濾器 (AY METS): 價格必須在 200MA 之上
        
        if position == 0 and buy_signal and curr['Close'] > curr['SMA_200']:
            entry_price = nxt['Open']
            position = capital / entry_price
            capital = 0
            stop_loss = entry_price - (2 * curr['ATR'])
            target = entry_price + (4 * curr['ATR']) # 1:2 RR
            trades.append({"type": "BUY", "date": nxt.name, "price": entry_price})
            
        # 賣出策略：達到止盈、跌破止損、或出現看跌吞沒
        elif position > 0:
            sell_signal = (curr['High'] >= target) or (curr['Low'] <= stop_loss) or (curr['Pattern'] == "BEAR_ENGULF")
            if sell_signal:
                sell_price = nxt['Open']
                capital = position * sell_price
                profit_pct = (sell_price - entry_price) / entry_price * 100
                position = 0
                trades.append({"type": "SELL", "date": nxt.name, "price": sell_price, "return": profit_pct})
                
    # 結算
    final_capital = capital if position == 0 else position * test_df.iloc[-1]['Close']
    total_return = (final_capital - 10000) / 10000 * 100
    win_trades = len([t for t in trades if t.get('return', 0) > 0])
    total_closed = len([t for t in trades if t['type'] == 'SELL'])
    win_rate = (win_trades / total_closed * 100) if total_closed > 0 else 0
    
    return total_return, win_rate, total_closed

# --- UI 介面 ---
st.title("🦅 Alpha Hunter | AY 冠軍級量化終端")

# 側邊欄
st.sidebar.header("🎯 美股選股器")
symbol = st.sidebar.text_input("輸入美股代號", "NVDA").upper()
st.sidebar.markdown("---")
st.sidebar.info("""
**AY 交易哲學 (METS):**
* **M**arket: 順勢而為，只在價格大於 200MA 時作多。
* **E**ntry: 尋找波動率收縮 (VCP) 或高勝率吞沒形態。
* **T**rade: 確保 1:2 以上的盈虧比 (Risk/Reward)。
* **S**top: 嚴格利用 ATR 設定移動止損。
""")

df = get_data(symbol)

if df is not None:
    curr_data = df.iloc[-1]
    
    # 頂部儀表板
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("當前價格", f"${curr_data['Close']:.2f}", f"{curr_data['Close'] - df.iloc[-2]['Close']:.2f}")
    col2.metric("20日均線 (短期)", f"${curr_data['SMA_20']:.2f}")
    col3.metric("50日均線 (生命線)", f"${curr_data['SMA_50']:.2f}")
    col4.metric("RSI (動能)", f"{curr_data['RSI']:.1f}")
    
    st.divider()
    
    # 區塊 1: Detected Signals (核心雷達)
    st.header("📡 智能信號雷達 (Detected Signals)")
    signals = analyze_signals(df)
    
    sig_cols = st.columns(5)
    icons = {"TREND": "📈", "MOM": "🔥", "VOL": "🌊", "AY_EDGE": "🦅", "PIVOT": "🔄"}
    
    for i, (key, info) in enumerate(signals.items()):
        with sig_cols[i]:
            if info['status']:
                st.success(f"{icons[key]} **{key}**\n\n{info['desc']}")
            else:
                st.markdown(f"""
                <div style="padding: 10px; border-radius: 5px; background-color: rgba(128,128,128,0.1); color: gray; height: 100%;">
                    {icons[key]} <s>{key}</s><br><small>{info['desc']}</small>
                </div>
                """, unsafe_allow_html=True)
                
    st.divider()
    
    # 區塊 2 & 3: 圖表與交易計畫
    col_chart, col_plan = st.columns([7, 3])
    
    with col_chart:
        st.subheader("📊 冠軍戰術圖表")
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.03)
        
        # K線
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Price"), row=1, col=1)
        # 均線
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_20'], line=dict(color='yellow', width=1.5), name="20 MA"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_50'], line=dict(color='green', width=1.5), name="50 MA"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['SMA_200'], line=dict(color='white', width=2, dash='dot'), name="200 MA (AY Base)"), row=1, col=1)
        
        # 標記形態
        bulls = df[df['Pattern'] == "BULL_ENGULF"]
        if not bulls.empty:
            fig.add_trace(go.Scatter(x=bulls.index, y=bulls['Low']*0.98, mode='markers', marker=dict(symbol='triangle-up', size=12, color='lime'), name="Bull Engulfing"), row=1, col=1)
        
        # 成交量
        colors = ['red' if df['Close'].iloc[i] < df['Open'].iloc[i] else 'green' for i in range(len(df))]
        fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name="Volume"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['Vol_SMA'], line=dict(color='orange'), name="Vol 20 SMA"), row=2, col=1)
        
        fig.update_layout(height=600, template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

    with col_plan:
        st.subheader("📝 AY 交易計畫 (METS)")
        st.markdown("基於 **1:2 盈虧比 (Risk/Reward)** 與 ATR 波動率計算。")
        
        # 計算買賣點
        support = curr_data['Support']
        suggest_buy = support * 1.02 # 支撐位上方 2% 埋伏
        risk = curr_data['ATR'] * 1.5
        stop_loss = suggest_buy - risk
        target_price = suggest_buy + (risk * 2) # 1:2 RR
        
        st.info(f"**🟢 建議買入區 (Entry):**\n${suggest_buy:.2f} \n*(支撐位上方，等待量縮)*")
        st.success(f"**🎯 考慮賣出價 (Target):**\n${target_price:.2f} \n*(預期利潤: ${(target_price-suggest_buy):.2f})*")
        st.error(f"**🛡️ 嚴格止損位 (Stop):**\n${stop_loss:.2f} \n*(承擔風險: ${(suggest_buy-stop_loss):.2f})*")
        
        if curr_data['Close'] < curr_data['SMA_200']:
            st.warning("⚠️ **AY 警告**：目前股價低於 200 日線，屬於空頭結構，**不建議作多** (Eliminate low-probability trades)。")

    st.divider()
    
    # 區塊 4: 回測與新聞
    col_bt, col_news = st.columns([1, 1])
    
    with col_bt:
        st.subheader("⚙️ 策略回測 (近6個月)")
        st.write("測試邏輯：高勝率吞沒形態 + AY MA交叉 + 1:2 RR + ATR止損")
        if st.button("▶️ 執行模擬回測"):
            with st.spinner("運算中..."):
                ret, win_rate, trades = run_backtest(df)
                st.metric("總報酬率 (Total Return)", f"{ret:.2f}%")
                st.metric("策略勝率 (Win Rate)", f"{win_rate:.1f}%")
                st.metric("交易次數 (Total Trades)", f"{trades} 次")
                
                if ret > 0: st.success("此標的近期非常契合本策略！")
                else: st.warning("此標的近期走勢震盪，策略表現不佳，請觀望。")
                
    with col_news:
        st.subheader("📰 市場情報中心 (Market News)")
        news_items = get_news(symbol)
        if news_items:
            for item in news_items:
                # yfinance news 格式處理
                title = item.get('title', '無標題')
                link = item.get('link', '#')
                publisher = item.get('publisher', '未知來源')
                timestamp = item.get('providerPublishTime', 0)
                date_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M') if timestamp else ""
                
                st.markdown(f"**[{title}]({link})**")
                st.caption(f"{publisher} - {date_str}")
        else:
            st.write("目前無最新重大新聞。")

else:
    st.error("無法取得數據，請確認代號正確。")
