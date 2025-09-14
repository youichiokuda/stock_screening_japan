import yfinance as yf
import pandas as pd
import requests
import time
import streamlit as st

st.set_page_config(page_title="東証プライム市場 割安株スクリーニング", layout="wide")

# ===========================
# サービスの概要を表示
# ===========================
st.title("📉 東証プライム市場 割安株スクリーニング")

st.markdown("""
### このサービスについて
東証プライム市場に上場する **全銘柄** を対象に、  
**株価が「谷」にある企業**を探し出し、さらに  
**PER / PBR / ROE / 売上成長率** を用いて割安度をランキングします。  

👉 投資アイデアのヒントを得たい方向けのサービスです。  
（※本サービスは情報提供を目的としたものであり、投資判断は自己責任でお願いします）
""")

with st.expander("🔍 スクリーニング条件（クリックで展開）"):
    st.markdown("""
    1. **株価データ**: 直近5年の株価を使用  
    2. **谷判定条件**:
       - 株価が **5年高値～安値レンジの下位20%** に位置  
       - 株価が **200日移動平均線を下回っている**  
    3. **バリュエーション指標**:
       - **PER** = 株価 ÷ EPS  
       - **PBR** = 株価 ÷ BPS  
       - **ROE** = 当期純利益 ÷ 自己資本  
       - **売上成長率** = 直近2期の売上増加率  
    4. **割安スコア** = PER + PBR （小さいほど割安）
    """)

# ===========================
# 東証プライム市場リスト取得
# ===========================
@st.cache_data(ttl=86400)
def load_stock_list():
    xls_url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    response = requests.get(xls_url)
    response.raise_for_status()
    with open("prime_list.xls", "wb") as f:
        f.write(response.content)
    df_list = pd.read_excel("prime_list.xls")
    df_stocks = df_list[df_list["市場・商品区分"] == "プライム（内国株式）"].copy()
    df_stocks["コード"] = df_stocks["コード"].astype(str).str.zfill(4)
    return df_stocks

df_stocks = load_stock_list()
codes = df_stocks["コード"].tolist()
tickers = [f"{c}.T" for c in codes]
code_to_name = dict(zip(df_stocks["コード"], df_stocks["銘柄名"]))
code_to_sector = dict(zip(df_stocks["コード"], df_stocks["33業種区分"]))

st.write(f"対象銘柄数: **{len(codes)}**")

# ===========================
# 株価データ取得
# ===========================
def fetch_price_data(tickers, batch_size=100):
    all_data = {}
    progress = st.progress(0, text="📊 株価データ取得中...")
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        data = yf.download(batch, period="5y", group_by="ticker", threads=True)
        for t in batch:
            try:
                all_data[t] = data[t]["Close"].dropna()
            except Exception:
                pass
        progress.progress(min((i+batch_size)/len(tickers), 1.0))
        time.sleep(2)
    progress.empty()
    return all_data

# ===========================
# メイン処理
# ===========================
if st.button("🚀 スクリーニング実行"):
    all_data = fetch_price_data(tickers)

    results = []
    progress = st.progress(0, text="⏳ 谷判定処理中...")
    for idx, code in enumerate(codes):
        ticker = f"{code}.T"
        if ticker not in all_data:
            progress.progress((idx+1)/len(codes))
            continue
        hist = all_data[ticker]
        if hist.empty:
            progress.progress((idx+1)/len(codes))
            continue

        ma200 = hist.rolling(200).mean().iloc[-1]
        latest_price = hist.iloc[-1]
        low_5y = hist.min()
        high_5y = hist.max()
        threshold = low_5y + (high_5y - low_5y) * 0.2
        in_valley = (latest_price < threshold) and (latest_price < ma200)

        results.append({
            "銘柄コード": code,
            "銘柄名": code_to_name.get(code, ""),
            "業種": code_to_sector.get(code, ""),
            "現在株価": round(latest_price, 2),
            "200日平均": round(ma200, 2),
            "5年安値": round(low_5y, 2),
            "5年高値": round(high_5y, 2),
            "谷判定": in_valley,
            "PER": None,
            "PBR": None,
            "ROE": None,
            "売上成長率": None
        })
        progress.progress((idx+1)/len(codes))
    progress.empty()

    df = pd.DataFrame(results)
    valley_df = df[df["谷判定"] == True].copy()
    st.success(f"✅ 谷判定された銘柄数: {len(valley_df)}")

    # ===========================
    # PER/PBR/ROE/売上成長率計算
    # ===========================
    progress = st.progress(0, text="📑 財務データ取得中...")
    for idx, (i, row) in enumerate(valley_df.iterrows()):
        ticker = f"{row['銘柄コード']}.T"
        try:
            stock = yf.Ticker(ticker)
            fin = stock.financials.T if stock.financials is not None else pd.DataFrame()
            bs = stock.balance_sheet.T if stock.balance_sheet is not None else pd.DataFrame()

            if not fin.empty and not bs.empty:
                net_income = fin.get("Net Income")
                revenue = fin.get("Total Revenue")
                shares = bs.get("Ordinary Shares Number")
                equity = bs.get("Total Equity Gross Minority Interest")

                if net_income is not None and shares is not None and equity is not None:
                    net_income = net_income.iloc[-1]
                    shares = shares.iloc[-1]
                    equity = equity.iloc[-1]

                    if shares and shares > 0:
                        eps = net_income / shares
                        if eps > 0:
                            valley_df.at[i, "PER"] = round(row["現在株価"] / eps, 2)
                        bps = equity / shares
                        if bps > 0:
                            valley_df.at[i, "PBR"] = round(row["現在株価"] / bps, 2)
                        if equity > 0:
                            roe = net_income / equity
                            valley_df.at[i, "ROE"] = round(roe * 100, 2)

                if revenue is not None and len(revenue) >= 2:
                    latest = revenue.iloc[-1]
                    prev = revenue.iloc[-2]
                    if prev > 0:
                        growth = (latest - prev) / prev
                        valley_df.at[i, "売上成長率"] = round(growth * 100, 2)

            time.sleep(1.0)
        except Exception:
            pass
        progress.progress((idx+1)/len(valley_df))
    progress.empty()

    # ===========================
    # 結果表示
    # ===========================
    df_ranked = valley_df.dropna(subset=["PER", "PBR"]).copy()
    df_ranked["割安スコア"] = df_ranked["PER"] + df_ranked["PBR"]

    st.subheader("◆ 割安スコア順 TOP10")
    st.dataframe(df_ranked.sort_values("割安スコア").head(10)[
        ["銘柄コード", "銘柄名", "業種", "現在株価", "PER", "PBR", "ROE", "売上成長率", "割安スコア"]
    ])

    st.subheader("◆ 業種別 集計（谷銘柄数）")
    sector_count = valley_df.groupby("業種").size().sort_values(ascending=False)
    st.bar_chart(sector_count)

    st.info("""
💡 **指標の解釈のヒント**
- **PER が低い** → 利益に対して株価が安い  
- **PBR が低い** → 資産に対して株価が安い  
- **ROE が高い** → 資本を効率よく利益に変えている  
- **売上成長率 がプラス** → 成長性あり  
""")
