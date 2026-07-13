# Dairy Horizon 千葉版データパッケージ v2

## ハッカソン版Webアプリ

Python 3.12を使用します。Ubuntu等ではシステムPythonへ直接インストールせず、仮想環境を使ってください。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

ブラウザで `http://127.0.0.1:8000/` を開きます。千葉市・60頭・2牛床列・既存10台のデモが初期表示されます。

主画面は精密な経営計画ではなく、30秒で行う投資スクリーニングです。農家が入力するのは、頭数・列数・既存ファン・乳価・守りたい年数だけです。標準仮定6件を明示し、「今」「おすすめ時期」「おすすめより3年後」を慎重／標準／改善の3ケースで比較します。Webアプリは外部APIを呼ばず、`data/climate_profiles/generated/` に保存済みのJSONだけを読みます。

## 将来気候プロファイルの更新

初回生成、地域追加、データ更新はWebサーバーを止めた状態で次を実行します。4モデル未満しか取得できない場合は、出力を作らず失敗します。

```bash
source .venv/bin/activate
python scripts/fetch_climate_profiles.py --region-id chiba_city
```

登録済み地域IDは `chiba_city`、`choshi`、`obihiro`、`kumamoto` です。任意の座標・年・出力先を指定する例：

```bash
python scripts/fetch_climate_profiles.py \
  --region-id chiba_city --latitude 35.6074 --longitude 140.1065 \
  --start-year 2026 --end-year 2050 \
  --output data/climate_profiles/generated/chiba_city_2026_2050.json
```

生成JSONには、モデルごとのリクエストURL、取得日時、返却座標・単位、成功/失敗、年別モデル値、中央値・最小・最大、集計規則と出典を保存します。日平均THIはスクリーニング用で、日最高THI、牛体付近の風速、個体の乳量実測を代替しません。屋外10m風速は投資計算に使用しません。

詳細試算では、実際の見積、電力量単価、変動費率、実測乳量差、消費税率・税込/税抜、金利、返済年数を標準仮定へ置き換えられます。融資・税務の最終判断は専門家へ確認してください。

Three.jsは `0.170.0` をローカルに同梱しています。配布元は `https://unpkg.com/three@0.170.0/`、取得日は2026-07-12、SHA-256は `08fd7545d13d2c7fb65ab691530a802dafefd638596501854f267d0fb13c39e7` です。MITライセンスは `static/vendor/three.LICENSE.txt` を参照してください。

v2では、60頭モデルを固定値から外し、可変つなぎ牛舎エンジンへ変更しました。

## 主な変更

- 頭数、列数、既存ファン数を可変化
- 必要ファン数を列ごとに自動計算
- 牛とファンの座標を自動生成
- 60頭モデルはデモシナリオとして分離
- 乳価を0～300円/kgで直接入力可能
- 基準乳価から-100～+100円/kgの変更が可能
- 円/Lの参考表示に対応
- 変動費率、消費税率、税込・税抜基準を入力化
- 全酪連方式の計算仕様と掲載元をMarkdown化
- 乳価0円、75頭等の境界ケースをテスト

## 構成

```text
templates/
  tie_stall_variable.json
  financial_input_schema.json

scenarios/
  chiba_60_cow_demo.json

generated/
  chiba_60_cow_layout.json
  chiba_60_cow_break_even.json

specs/
  ZENRAKUREN_CALCULATION_SPEC.md
  VARIABLE_MODEL_SPEC.md
```

## 60頭モデルを再生成

```bash
python scripts/generate_barn_layout.py   scenarios/chiba_60_cow_demo.json   generated/chiba_60_cow_layout.json
```

## 全酪連式を再計算

```bash
python scripts/calculate_zenrakuren_break_even.py   scenarios/chiba_60_cow_demo.json   generated/chiba_60_cow_break_even.json
```

## テスト

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
python -m compileall app scripts tests
```

## デフォルト計算

- 乳価: 135円/kg
- 収支分岐点: 3.1377kg/頭/日
- 参考換算乳価: 139.320円/L

原資料の丸め表示は3.2kg/頭/日です。

## 税について

計算エンジンは消費税を自動的に一律加算しません。
原資料の指示に従い、設備費・電力費・乳価を税込または税抜の同じ基準へ統一します。

詳細は `specs/ZENRAKUREN_CALCULATION_SPEC.md` を参照してください。


## Codexで実装を開始する

公式ガイドに沿って、計画と実装を分けます。

1. `prompts/CODEX_START_HERE.md`を読む
2. `/plan`で`prompts/CODEX_PLAN_PROMPT.md`を実行
3. 計画を確認・修正
4. `prompts/CODEX_BUILD_PROMPT.md`で実装
5. `specs/ACCEPTANCE_CRITERIA.md`で完成確認

恒久的な設計・品質ルールはルートの`AGENTS.md`にあります。
後続作業は`prompts/CODEX_PHASE_PROMPTS.md`から一つずつ実行します。

設計意図は`prompts/PROMPT_DESIGN_NOTES.md`にあります。
