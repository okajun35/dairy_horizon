# Dairy Horizon

牛舎の現在不足を確認し、「第1期」と「全数整備」を比較する暑熱対策の適応投資経路ナビゲーターです。
投資年を自動で推薦せず、次に確認すべき一つの情報を示します。

## 起動

Python 3.12で実行します。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
python -m uvicorn app.main:app --reload
```

ブラウザで `http://127.0.0.1:8000/` を開きます。初期表示は千葉市・60頭・2列・既存10台です。
自然文入力を使う場合は、`.env` の `OPENAI_API_KEY` にプロジェクト用APIキーを設定します。`.env` はGit管理対象外です。

## 現在の範囲

- 千葉市・頭数・1〜6列の牛床列数・既存ファン数から、頭数基準の台数目安と現在との差を表示
- 気温データが千葉市分のみのため地域欄は固定表示。ほかの地域はデータ追加後に拡張予定
- 自然文から4項目の候補を抽出し、利用者が確認した値だけを計算へ接続
- 自然文の地域が未入力または未対応なら千葉市の試算であることを明示し、既存台数が不明でも頭数基準の参考台数を入力済みにして不足を評価（参考値は増減可能）
- 参考台数でも、参考値のまま・第1期・頭数目安まで追加した牛舎を比較
- 現在・第1期・全数整備を牛舎表示で切替
- 未カバー推計牛と新たにカバーされる牛を確認
- 全酪連の標準例を使い、第1期と頭数目安案の増分設備費・年間増分電気代・回収に必要な防止乳量を比較表示
- 払える設備費、見積額との差、標準仮定は必要な場合だけ折りたたみで確認
- 次の現場確認事項を一つ提示
- 末尾で標準仮定・計算根拠・出典区分を表示

この画面は投資判断・見積依頼を行いません。保存済みの将来THIデータはまだ画面へ未接続であり、接続後も背景情報として扱い、必要台数や投資時期をTHIだけから決めません。

## 設計判断

- [Architecture Decision Records](docs/adr/README.md)
- [ADR-0001: ファン台数、気候・運転期間、財務計算、AI補完の責務を分離する](docs/adr/0001-separate-fan-climate-finance-and-ai-responsibilities.md)

## テスト

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
python -m compileall app tests
```

OpenAI APIを呼ぶ結合テストは既定でスキップします。明示的に実行する場合だけ、次を実行します。

```bash
set -a
source .env
set +a
RUN_OPENAI_INTEGRATION_TESTS=1 python -m unittest tests.test_natural_input.OpenAINaturalInputLiveTest -v
```

ブラウザの黄金経路は、アプリを起動した状態でChromiumを別ターミナルからデバッグ起動し、Node.jsの検証スクリプトを接続します。

```bash
chromium --headless --disable-gpu --no-sandbox --remote-debugging-port=9224 \
  --user-data-dir=/tmp/dairy-horizon-browser-check http://127.0.0.1:8000/
```

```bash
node tests/browser_golden_path.mjs
```
