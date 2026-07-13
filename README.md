# Dairy Horizon

牛舎の現在不足を確認し、「第1期」と「全数整備」を比較する暑熱対策の適応投資経路ナビゲーターです。
投資年を自動で推薦せず、次に確認すべき一つの情報を示します。

## 起動

Python 3.12で実行します。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

ブラウザで `http://127.0.0.1:8000/` を開きます。初期表示は千葉市・60頭・2列・既存10台です。

## 現在の範囲

- 地域・頭数・列数・既存ファン数から、列ごとの必要ファン数と不足を表示
- 現在・第1期・全数整備を牛舎表示で切替
- 未カバー推計牛と新たにカバーされる牛を確認
- 次の現場確認事項を一つ提示
- 末尾で標準仮定・計算根拠・出典区分を表示

この画面は投資判断・見積依頼を行いません。将来気候も背景情報であり、必要台数や投資時期の計算には使用しません。

## テスト

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
python -m compileall app tests
```
