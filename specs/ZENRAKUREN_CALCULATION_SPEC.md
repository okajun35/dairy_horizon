# 全酪連方式：暑熱対策設備投資スクリーニング計算仕様

## 1. 掲載元

- 発行元：全国酪農業協同組合連合会（全酪連）
- 媒体：`COW BELL ─カウ・ベル─ No.178 2025秋季号`
- 記事：`暑熱対策の設備投資を考える`
- 執筆：全酪連 購買生産指導部 酪農生産指導室 研究員 田中眞二郎
- 該当ページ：6～8ページ
- 提供資料：`No178HP(1).pdf`
- 全酪連公式サイト：https://www.zenrakuren.or.jp/
- PDF直接URL：本パッケージ作成時点では公開URLを確認できていないため未記載

本仕様は、記事の数式と例示値をDairy Horizonで再現できる形へ構造化したものです。
原資料自体が、精密な経営判断ではなく、設備投資案を最初に「粗い網」で選別するための
スケッチとして説明しています。

---

## 2. 基本的な判定

暑熱対策投資によって防止できる乳量減少が、投資回収に必要な収支分岐点乳量より大きい場合、
設備投資の効果が見込めると判定します。

```text
防止できる乳量減少 > 収支分岐点乳量
```

Dairy Horizonでは、これを最終的な契約判断ではなく、見積取得や詳細検討へ進むための
一次スクリーニングとして使用します。

---

## 3. 入力項目

原資料が示す主要入力は次の7項目です。

1. 設備本体、インバーター、設置工事などの導入額
2. 基本料金、電力量料金などの運転資金
3. 暑熱対策の対象期間
4. 耐用年数
5. 乳飼比等による変動費率
6. 乳価
7. ファン1台が対象とする牛の頭数

Dairy Horizonでは、これらをすべて可変入力にします。

---

## 4. 計算式

### 4.1 ファン1台当たりの設備投資額

```text
fan_capex
= fan_body
+ inverter
+ installation
```

### 4.2 牛1頭当たりの設備投資額

```text
capex_per_cow
= fan_capex / cows_covered_per_fan
```

### 4.3 牛1頭・1年当たりの設備投資負担

単純償却方式：

```text
annualised_capex_per_cow
= capex_per_cow / useful_life_years
```

金利を加味する方式：

```text
CRF(r, n)
= r * (1 + r)^n / ((1 + r)^n - 1)

annualised_capex_per_cow
= capex_per_cow * CRF(r, n)
```

金利が0の場合、CRFは `1 / n` とします。

### 4.4 ファン1台当たりの年間基本料金

```text
annual_basic_charge_per_fan
= basic_charge_yen_per_kw_month
* rated_power_kw
* 12
```

### 4.5 ファン1台当たりの年間電力量料金

```text
annual_energy_charge_per_fan
= energy_charge_yen_per_kwh
* rated_power_kw
* hours_per_day
* active_days
* (1 - inverter_reduction_ratio)
```

### 4.6 牛1頭当たりの年間運転費

```text
annual_operation_per_cow
= (
    annual_basic_charge_per_fan
    + annual_energy_charge_per_fan
  )
  / cows_covered_per_fan
```

### 4.7 牛1頭当たりの年間負担額

```text
annual_burden_per_cow
= annualised_capex_per_cow
+ annual_operation_per_cow
```

### 4.8 収支分岐点売上高

```text
contribution_margin_ratio
= 1 - variable_cost_ratio

break_even_sales_per_cow
= annual_burden_per_cow
/ contribution_margin_ratio
```

変動費率が100%に達すると回収できないため、入力上限は100%未満とします。

### 4.9 年間の収支分岐点乳量

```text
break_even_milk_kg_per_cow_year
= break_even_sales_per_cow
/ milk_price_yen_per_kg
```

乳価が0円の場合は除算せず、次を返します。

```text
status = recovery_impossible_at_zero_price
```

### 4.10 暑熱期間1日当たりの収支分岐点乳量

```text
break_even_milk_kg_per_cow_day
= break_even_milk_kg_per_cow_year
/ active_days
```

---

## 5. 原資料の例示値

| 項目 | 例示値 |
|---|---:|
| ファン本体 | 100,000円/台 |
| インバーター | 10,000円/台 |
| 設置工事 | 110,000円/台 |
| 消費電力 | 0.4kW |
| 基本料金 | 1,300円/kW・月 |
| 電力量単価 | 27円/kWh |
| 運転時間 | 24時間/日 |
| 対象期間 | 4か月、計算上120日 |
| インバーター削減率 | 25% |
| 耐用年数 | 7年 |
| 変動費率 | 60% |
| 乳価 | 135円/kg |
| 対象頭数 | 3頭/台 |
| 目標牛体風速 | 2m/s以上 |

Dairy Horizonで丸め前の値を再計算すると、収支分岐点は次のとおりです。

```text
3.1377 kg/頭/日
```

原資料の誌面では途中の金額を丸めて計算しており、最終値を `3.2kg/頭/日` と表示しています。
アプリでは計算結果には丸め前の値を使い、説明画面には誌面の3.2kgも併記します。

---

## 6. 乳価の可変入力

計算内部の標準単位は `円/kg` とします。

```text
入力範囲：0～300円/kg
基準値：135円/kg
基準値からの変更：-100～+100円/kg
```

0円を入力可能にしますが、0円では売上による回収が成立しないため、
収支分岐乳量は数値表示しません。

農家が円/Lで考える場合に備えて、参考換算を提供します。

```text
円/L = 円/kg * 乳の密度kg/L
```

デモ用密度は `1.032kg/L` とします。この換算値は精算書の実値ではないため、
UIでは参考値と表示します。

---

## 7. 消費税の扱い

原資料は、設備費や乳価について、税込・税抜のどちらを使ってもよいが、
**すべて同じ基準に統一すること**を求めています。

Dairy Horizonの中核計算では、消費税率を機械的に全項目へ掛けません。

理由：

- 取引ごとに税の扱いが異なり得る
- 事業者の課税方式によってキャッシュフローの意味が変わる
- 税抜価格と税込価格が混在する方が大きな誤差になる

入力として次を持ちます。

```text
consumption_tax_rate_pct: 0～20%
tax_basis:
  - tax_exclusive
  - tax_inclusive
```

税率1%等のシナリオ比較を行う場合は、売上・設備・電力の各項目にどのように税を適用するかを
別の税務ポリシーとして定義してから計算します。単純に全金額へ同じ率を掛ける実装はしません。

---

## 8. つなぎ牛舎への適用

原資料の例示では、牛の横臥時のき甲部に2m/s以上の風を当てることを意識し、
3頭に1台以上のファンを基準としています。

Dairy Horizonの必要ファン台数は、牛舎全体で単純に割るのではなく、
列ごとに計算します。

```text
target_fans
= sum(
    ceil(cows_in_row / cows_covered_per_fan)
  )
```

例：

```text
60頭・2列（30頭＋30頭）
= ceil(30 / 3) + ceil(30 / 3)
= 20台
```

```text
75頭・2列（38頭＋37頭）
= ceil(38 / 3) + ceil(37 / 3)
= 26台
```

---

## 9. 制約と非対象

この計算だけでは次を評価できません。

- 繁殖成績への影響
- 疾病、死亡、淘汰
- 乾乳期暑熱の次期乳期への影響
- 牛体風速と乳量の厳密な因果関係
- 税務上の最終的な手取り
- 設備の残存価値
- 補助金
- 牛舎改築の構造費
- 実際の電源容量
- 個別農家の精算乳価

したがって、Dairy Horizonではこの式を、公開気象、将来気候、牛舎配置、
本人の継続・承継条件と組み合わせますが、最終投資判断や金融助言とは表示しません。
