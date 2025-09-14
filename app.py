import yfinance as yf
import pandas as pd
import requests
import time
import streamlit as st
from tqdm import tqdm

st.title("東証プライム市場 割安株スクリーニング")

# 1. 東証プライム市場リスト取得
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

st.write(f"対象銘柄数: {len(codes)}")

# 2. 株価データ取得（バッチ）
def fetch_price_data(tickers, batch_size=100):
    all_data = {}
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        data = yf.download(batch, period="5y", group_by="ticker", threads=True)
        for t in batch:
            try:
                all_data[t] = data[t]["Close"].dropna()
            except Exception:
                pass
        time.sleep(2)
    return all_data

if st.button("スクリーニング実行"):
    st.write("株価データ取得中...")
    all_data = fetch_price_data(tickers)

    results = []
    for code in tqdm(codes, desc="谷判定処理"):
        ticker = f"{code}.T"
        if ticker not in all_data:
            continue
        hist = all_data[ticker]
        if hist.empty:
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
            "現在株価": round(latest_price, 2),
            "200日平均": round(ma200, 2),
            "5年安値": round(low_5y, 2),
            "5年高値": round(high_5y, 2),
            "谷判定": in_valley,
            "PER": None,
            "PBR": None
        })

    df = pd.DataFrame(results)
    valley_df = df[df["谷判定"] == True].copy()
    st.write(f"谷判定された銘柄数: {len(valley_df)}")

    # PER/PBR計算（谷銘柄のみ）
    for i, row in valley_df.iterrows():
        ticker = f"{row['銘柄コード']}.T"
        try:
            stock = yf.Ticker(ticker)
            financials = stock.financials.T if stock.financials is not None else pd.DataFrame()
            balance = stock.balance_sheet.T if stock.balance_sheet is not None else pd.DataFrame()

            if not financials.empty and not balance.empty:
                net_income = financials.get("Net Income")
                shares = balance.get("Ordinary Shares Number")
                equity = balance.get("Total Equity Gross Minority Interest")

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
            time.sleep(1.0)
        except Exception:
            pass

    df_ranked = valley_df.dropna(subset=["PER", "PBR"]).copy()
    df_ranked["割安スコア"] = df_ranked["PER"] + df_ranked["PBR"]

    st.subheader("◆ 割安スコア順 TOP10")
    st.dataframe(df_ranked.sort_values("割安スコア").head(10)[["銘柄コード", "銘柄名", "現在株価", "PER", "PBR", "割安スコア"]])
