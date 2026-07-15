# データ配置と利用区分

このディレクトリには、Webアプリからの外部取得ではなく、事前に保存・検証した参照データだけを置きます。

| パス | 内容 | 現在の画面での扱い |
|---|---|---|
| `observed/jma_chiba_daily_2020_2025.csv` | 気象庁・千葉（47682）の2020〜2025年日別観測 | 直近観測基準として保存済み。画面は未接続 |
| `observed/jma_chiba_thi_summary_2020_2025.json` | 日平均THI 72以上の日数と欠測範囲 | 年平均97.0〜97.5日。画面は未接続 |
| `derived/` | 観測値から算出したTHI、+1℃／+2℃の透明なデモ暑熱ストレス | 未接続 |
| `climate_profiles/` | 千葉の参照プロファイル | 未接続 |
| `climate_profiles/generated/` | 2025〜2034年のCMIP6複数モデル集計 | 2026〜2030年・2031〜2034年のTHI対象日数と電力費背景へ接続。投資年や必要台数には使用しない |
| `climate_profiles/generated/chiba_city_2020_2025.json` | 同一CMIP6モデルの直近モデル基準 | 将来期間との差分計算用。観測値としては扱わない |
| `provenance/sources.json` | 元資料と出典メタデータ | 出典確認用 |
| `farms/`、`scenarios/`、`generated/` | 過去デモの入力・生成物 | 現行ナビゲーターは未使用 |

現在のナビゲーターは、利用者入力、明示されたモデルケース、保存済み将来気候だけを使用します。将来気候は各モデルの期間内年平均を求めた後、モデル間の中央値と最小〜最大を表示し、必要台数ではなく運転日数と年間電力費へ接続します。

## 気候データの再生成

Webリクエスト中には実行せず、事前処理として実行します。

```bash
python scripts/fetch_jma_observations.py \
  --start-year 2020 --end-year 2025 --output-dir data/observed

python scripts/fetch_climate_profiles.py \
  --region-id chiba_city \
  --start-year 2020 --end-year 2025 \
  --period-role recent_model_baseline
```

JMA取得は、観測行がそろっていてもTHI計算に必要な値が欠測していれば終了コード2を返します。生成JSONの下限・上限と欠測日を確認してください。CMIP6の2020〜2025年値は過去の実測ではなく、将来期間と同じモデルの差分を求めるための基準です。
