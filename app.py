import streamlit as st
import yfinance as yf
import pandas as pd

# 1. 設定網頁的標題與圖示 (這會在 iPhone Safari 標籤頁顯示)
st.set_page_config(page_title="冠軍交易員 AI 訊號", page_icon="📈", layout="centered")

st.title("📈 冠軍交易員 AI 訊號中心")
st.markdown("每日盤後掃描，尋找 **1:3 高盈虧比** 且符合 VCP 收斂的強勢股。")
st.markdown("---")

# 2. 建立簡單的會員收費牆 (Paywall)
# 假設你這個月的密碼設定為 "AY2026"
USER_PASSWORD = "AY2026"

# 讓用戶輸入密碼
entered_password = st.text_input("🔒 請輸入本月專屬付費會員密碼：", type="password")

if entered_password == USER_PASSWORD:
    st.success("✅ 登入成功！歡迎回來大市分析。")
    st.markdown("### 🔥 今日強勢突破選股雷達")
    
    # 你要掃描的股票池
    watchlist = ["AAPL", "TSLA", "NVDA", "META", "PLTR"]
    
    # 建立一個進度條，讓用戶覺得 App 正在努力運算
    with st.spinner('AI 正在讀取華爾街最新數據...'):
        for symbol in watchlist:
            try:
                df = yf.download(symbol, period="6mo", progress=False)
                if df.empty: continue
                
                latest_close = round(df['Close'].iloc[-1].item(), 2)
                df['SMA_50'] = df['Close'].rolling(window=50).mean()
                sma_50 = round(df['SMA_50'].iloc[-1].item(), 2)
                
                # 判斷邏輯：只顯示站上 50MA 的強勢股
                if latest_close > sma_50:
                    stop_loss = round(latest_close * 0.92, 2) 
                    risk = latest_close - stop_loss
                    take_profit = round(latest_close + (risk * 3), 2)
                    
                    # 3. 使用 UI 卡片來顯示數據 (適合 iPhone 單手觀看)
                    st.info(f"🚀 **發現強勢標的：{symbol}**")
                    
                    # 將畫面切成三欄，顯示買入、止損、停利
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric(label="👉 建議買入價", value=f"${latest_close}")
                    with col2:
                        st.metric(label="🛑 嚴格止損", value=f"${stop_loss}", delta="-8% 風險", delta_color="inverse")
                    with col3:
                        st.metric(label="💰 獲利目標", value=f"${take_profit}", delta="1:3 盈虧比")
                    
                    st.markdown("---") # 分隔線
            except Exception as e:
                pass
                
else:
    if entered_password:
        st.error("❌ 密碼錯誤！請確認您是否已繳交本月會費。")
