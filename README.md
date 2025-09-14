# 東証プライム市場 割安株スクリーニング

## セットアップ
```
pip install -r requirements.txt
```

## 実行
```
streamlit run app.py
```

## Renderデプロイ手順
1. GitHubにpush
2. Renderで「New Web Service」からリポジトリを選択
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `streamlit run app.py --server.port=$PORT --server.address=0.0.0.0`
