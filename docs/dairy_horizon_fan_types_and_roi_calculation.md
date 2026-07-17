# Dairy Horizon 送風ファン分類・投資計算 実装メモ

## 0. 目的

この文書は、Dairy Horizonで送風ファンを比較し、暑熱対策投資の単純回収条件を計算するための実装基準をまとめたものである。

初回実装で答える問いは次のとおり。

> このファン構成を導入した場合、年間いくらかかり、暑熱による乳量低下を1頭1日何kg防げれば回収できるか。

このモデルで比較的正確に計算できるのは、主に以下である。

- ファン本体費
- コントローラー・インバーター費
- 設置工事費
- 消費電力
- 電気基本料金
- 電力量料金
- 年換算設備費
- 投資回収に必要な乳量低下防止量

一方、次の値はカタログだけでは確定できない。

- 牛体付近で実際に得られる風速
- 風速2m/s以上となる範囲
- 1台で実際にカバーできる頭数
- 乳量低下を何kg防げるか
- 繁殖、疾病、淘汰への金銭効果

したがって、初回実装は「実際の効果を断定するモデル」ではなく、**必要な効果を逆算する投資スクリーニングモデル**とする。

---

# 1. ファンの用途分類

## 1.1 牛体送風用ファン

### 目的

- 牛へ直接風を当てる
- 牛体表面からの熱放散を助ける
- ソーカーで濡れた牛体を乾かす
- 横臥時の牛のき甲部へ風を届ける

### 主な候補

- 直径約100cmの軸流ファン
- 有圧換気扇を牛床方向へ設置した構成
- 60～100cm級の壁掛け・吊下げファン
- 既存ファン間へ追加する中型ファン

### 実装上の標準モデル

```yaml
category: cow_body_airflow
diameter_cm: 100
rated_power_kw: 0.4
target_air_speed_mps: 2.0
preferred_air_speed_mps: 3.0
default_covered_cows: 3
```

### 注意

「3頭に1台」は、牛体付近で必要な風速を確保するための目安であり、どの100cmファンでも自動的に3頭をカバーできるという意味ではない。

実際には以下で変わる。

- ファン風量
- ファンの径
- 設置高
- 傾き
- ファン間隔
- 牛床の向き
- 柱、梁、壁などの障害物
- 50Hz／60Hz
- ファンの汚れや経年劣化

---

## 1.2 小型・中型スポットファン

### 目的

- 風のよどみを補う
- 牛舎端部や柱周辺を補完する
- 待機場所や高リスク区画を限定的に冷却する
- 既存ファンの死角を埋める

### おおよその分類

```text
羽根径：30～80cm程度
消費電力：100～400W程度
風量：製品差が大きい
```

### 向いている用途

- 全面整備前の段階導入
- 未カバー区画の補完
- 待機室
- 分娩・乾乳区画
- 壁や設備によって風が遮られる場所

### 注意

小型ファンを牛舎全体の必要台数へ単純換算しない。

100cmファンの「3頭に1台」という基準を、60cmファンや30cmファンへそのまま適用してはいけない。

---

## 1.3 標準100cm級軸流ファン

Dairy Horizonの初回比較に最も適しているクラス。

資材一覧には、羽根径100cm前後の製品が多数掲載されている。

掲載製品の仕様には幅があり、おおむね以下の範囲が確認できる。

```text
羽根径：約100cm
風量：約240～840m³/分程度
消費電力：約220～420W程度
```

一部には、これより高風量・高消費電力の製品もある。

### 初回の比較軸

- 取得価格
- 消費電力
- 風量
- 取付方式
- インバーター対応
- 電源
- 防塵・防水性
- 清掃性
- 重量
- 既存設備との置換可否

### 推奨用途

```text
標準型：
本体価格・電力・風量のバランスを優先

省電力型：
同等の必要風速を確保できることを前提に電力を重視

高風量型：
設置可能台数が限られる場所、長い到達距離が必要な場所
```

---

## 1.4 大型・高風量軸流ファン

資材一覧には、羽根径150cm級、風量1,000m³/分を超える製品も掲載されている。

```text
羽根径：約150cm
風量：1,000m³/分超の製品あり
消費電力：約1kW以上の製品あり
```

### 利点

- 1台当たりの風量が大きい
- 条件によっては台数を減らせる可能性がある
- 牛舎全体の空気移動やリレー送風へ使いやすい

### 欠点

- 消費電力が大きい
- 重量、寸法、支持構造の制約が大きい
- 1台当たりのカバー頭数をカタログ風量だけでは決められない
- 強い風が局所的に集中する可能性がある

### 実装上の扱い

大型ファンは「標準ファン何台分」と自動換算しない。

```yaml
coverage:
  calculation_mode: measured_or_scenario
  default_covered_cows: null
```

牛体付近2m/s以上となる実測範囲、またはメーカーの到達風速資料がなければ、カバー頭数を確定しない。

---

## 1.5 換気・排気用ファン

### 目的

- 舎内の熱気を排出する
- 湿気を排出する
- 外気を取り込む
- トンネル換気や横断換気を成立させる

### 牛体送風との違い

```text
換気：
牛舎全体の空気を入れ替える

送風：
牛体へ直接風を当てる
```

換気ファンの風量が大きくても、牛体付近で2m/s以上の風が得られるとは限らない。

反対に、牛体送風ファンを増やしても、入排気口が不足していれば熱と湿気が舎内へ残る。

### 入力項目

```yaml
category: ventilation_exhaust
airflow_m3_per_min: null
static_pressure_pa: null
inlet_area_m2: null
outlet_area_m2: null
air_changes_per_hour: null
```

換気量と牛体送風効果は別の計算結果として保持する。

---

## 1.6 循環・リレー送風用ファン

### 目的

- 長い牛舎内で風をつなぐ
- よどみを減らす
- 大空間の空気を循環させる
- 主ファンから遠い区画を補完する

### 注意

循環ファンは、必ずしも各牛へ直接2m/s以上を当てるための機器ではない。

Dairy Horizonでは以下を分ける。

```yaml
effects:
  ventilation_support: true
  cow_body_direct_airflow: unknown
```

---

## 1.7 ファンコントローラー・インバーター

ファン本体とは別カテゴリで管理する。

### 種類

```text
手動ON/OFF
温度連動ON/OFF
多段制御
インバーターによる連続回転数制御
複数ファン一括制御
```

### 期待できる効果

- 気温に応じた自動運転
- 電力消費の削減
- 夜間冷却の維持
- ファンの急停止・急始動の抑制
- 運転状況の標準化

### 回転数と消費電力の簡易関係

適用可能なファンとインバーターでは、概算として次の関係を使える。

\[
rac{P}{P_0}
pprox
\left(rac{n}{n_0}ight)^3
\]

- \(P\)：制御後の消費電力
- \(P_0\)：定格時の消費電力
- \(n\)：制御後の回転数
- \(n_0\)：定格回転数

例：

\[
0.8^3 = 0.512
\]

回転数80％では、理論上の消費電力は約51.2％となる。

ただし、以下の場合は単純適用しない。

- インバーター非対応モーター
- 内蔵制御が独自方式
- 静圧条件が大きく変わる
- 最低回転数制限がある
- メーカーが別の制御曲線を示している

---

# 2. ファン製品データモデル

## 2.1 推奨スキーマ

```yaml
fan_product:
  id: string
  manufacturer: string
  model: string
  category:
    - cow_body_airflow
    - spot_airflow
    - ventilation_exhaust
    - circulation_relay
    - large_airflow

  diameter_cm: number | null
  dimensions_cm:
    width: number | null
    height: number | null
    depth: number | null

  rated_airflow_m3_per_min: number | null
  airflow_measurement_method: string | null

  rated_power_w: number | null
  voltage_v: number | null
  phase: single | three | unknown
  frequency_hz:
    - 50
    - 60

  reference_price_yen: number | null
  price_date: "2024-12"
  price_includes_installation: false

  inverter_compatible: true | false | unknown
  controller_required: true | false | unknown

  installation:
    mounting: hanging | wall | ceiling | other
    weight_kg: number | null
    minimum_height_m: number | null

  coverage:
    measured_air_speed_mps: null
    measured_distance_m: null
    covered_cows: null
    source_type: scenario_assumption

  provenance:
    source_type: manufacturer_spec
    source_document: "乳牛の暑熱対策チャレンジ ガイドブックin十勝 資材一覧"
    verified_by_extension_center: false
```

## 2.2 風量値の注意

資材一覧では、風量の測定方法が製品によって異なる場合がある。

そのため、風量値だけで製品順位を決めない。

```text
不適切：
風量600m³/分なので、風量500m³/分の製品より必ず優れている

適切：
測定方法、消費電力、設置条件、必要風速範囲を合わせて比較する
```

---

# 3. 投資計算

## 3.1 計算の基本思想

暑熱対策ファンは、乳量を新たに増やす設備ではなく、暑熱による乳量低下を防ぐ設備として評価する。

判定式は次のとおり。

\[
M_{	ext{avoided}}
>
M_{	ext{break-even}}
\]

- \(M_{	ext{avoided}}\)：実際またはシナリオ上、防止できる乳量低下
- \(M_{	ext{break-even}}\)：投資回収に必要な乳量低下防止量

---

## 3.2 初期投資額

### 1台当たり

\[
I_{	ext{unit}}
=
C_{	ext{fan}}
+
C_{	ext{controller}}
+
C_{	ext{installation}}
+
C_{	ext{electrical}}
+
C_{	ext{structure}}
\]

- \(C_{	ext{fan}}\)：ファン本体
- \(C_{	ext{controller}}\)：インバーター・コントローラー
- \(C_{	ext{installation}}\)：取付工事
- \(C_{	ext{electrical}}\)：配線・分電盤・電気工事
- \(C_{	ext{structure}}\)：梁補強・取付金具など

### 全体

\[
I_{	ext{total}}
=
I_{	ext{unit}}
	imes N_{	ext{fans}}
\]

既存設備を再利用する場合は、追加分だけを計算する。

---

## 3.3 年間電力費

### 電力量料金

\[
C_{	ext{energy}}
=
N_{	ext{fans}}
	imes P_{	ext{kW}}
	imes H_{	ext{day}}
	imes D_{	ext{heat}}
	imes U
	imes E_{	ext{yen/kWh}}
\]

- \(P_{	ext{kW}}\)：1台の消費電力
- \(H_{	ext{day}}\)：1日稼働時間
- \(D_{	ext{heat}}\)：暑熱対策日数
- \(U\)：平均負荷率
- \(E_{	ext{yen/kWh}}\)：電力量単価

### 基本料金

\[
C_{	ext{demand}}
=
N_{	ext{fans}}
	imes P_{	ext{kW}}
	imes B_{	ext{yen/kW/month}}
	imes 12
\]

契約電力が既に十分あり、ファン追加で基本料金が増えない場合は、増分基本料金を0円とする。

### 年間電力費

\[
C_{	ext{electricity}}
=
C_{	ext{energy}}
+
C_{	ext{demand}}
\]

---

## 3.4 年間設備負担

### 定額法

\[
C_{	ext{capex,annual}}
=
rac{I_{	ext{total}}}{L}
\]

- \(L\)：耐用年数

### 金利込み

\[
CRF(r,n)
=
rac{r(1+r)^n}{(1+r)^n-1}
\]

\[
C_{	ext{capex,annual}}
=
I_{	ext{total}}
	imes CRF(r,n)
\]

---

## 3.5 年間総費用

\[
C_{	ext{annual}}
=
C_{	ext{capex,annual}}
+
C_{	ext{electricity}}
+
C_{	ext{maintenance}}
\]

---

## 3.6 収支分岐点売上高

\[
R_{	ext{break-even}}
=
rac{C_{	ext{annual}}}{1-v}
\]

- \(v\)：変動費率

---

## 3.7 収支分岐点乳量

### 年間

\[
M_{	ext{break-even,annual}}
=
rac{R_{	ext{break-even}}}{P_{	ext{milk}}}
\]

- \(P_{	ext{milk}}\)：乳価、円/kg

### 1頭1日

\[
M_{	ext{break-even,cow,day}}
=
rac{
M_{	ext{break-even,annual}}
}{
N_{	ext{covered cows}}
	imes D_{	ext{heat}}
}
\]

ここで使う頭数は、原則として**設備によって実際に新規カバーされる牛の頭数**である。

```text
誤り：
牛群60頭だから、常に60頭で割る

正しい：
追加ファン5台が3頭ずつを新規カバーするなら、15頭で割る
```

---

# 4. 全酪連例の再現

## 4.1 入力

```yaml
fan:
  price_yen: 100000
  controller_yen: 10000
  installation_yen: 110000
  power_kw: 0.4
  count: 1
  covered_cows: 3

operation:
  hours_per_day: 24
  heat_days: 120
  average_load_factor: 0.75
  electricity_yen_per_kwh: 27
  demand_yen_per_kw_month: 1300

finance:
  useful_life_years: 7
  variable_cost_rate: 0.60
  milk_price_yen_per_kg: 135
```

## 4.2 牛1頭当たり初期投資

資料の丸め値：

\[
34,000
+
4,000
+
37,000
=
75,000円/頭
\]

## 4.3 年間設備費

\[
75,000
\div 7
pprox
10,700円/頭・年
\]

## 4.4 年間電気負担

資料例：

```text
基本料金：約2,000円/頭・年
電力量料金：約8,000円/頭・年
```

## 4.5 年間総負担

\[
10,700 + 2,000 + 8,000
=
20,700円/頭・年
\]

## 4.6 必要売上高

\[
20,700
\div (1-0.60)
=
51,750円/頭・年
\]

## 4.7 必要乳量

\[
51,800
\div 135
pprox
380kg/頭・年
\]

\[
380
\div 120
pprox
3.2kg/頭・日
\]

したがって、この例では次の判定になる。

> 暑熱期間中の乳量低下を平均3.2kg/頭・日以上防げるなら、乳量だけを使った単純回収上は投資効果がある。

---

# 5. ファン種類別の比較方法

## 5.1 比較指標

| 指標 | 用途 |
|---|---|
| 本体価格 | 初期投資 |
| 設置・電気工事費 | 初期投資 |
| 消費電力 | 運転費 |
| 風量 | 製品能力の参考 |
| 羽根径 | 設置性と風の広がり |
| 風速2m/s到達距離 | 牛体冷却の主要指標 |
| 風速2m/sの幅 | カバー頭数の主要指標 |
| 電源・相 | 設置可否 |
| 重量 | 梁・金具の設計 |
| インバーター対応 | 電力費と制御 |
| 清掃性 | 実効風量維持 |
| 防塵・耐腐食性 | 牛舎環境への適合 |

## 5.2 標準型と大型型の運転費比較例

### 標準100cm型

```yaml
power_kw: 0.4
```

1台を120日、24時間、平均負荷75％で稼働する例：

\[
0.4
	imes 24
	imes 120
	imes 0.75
	imes 27
=
23,328円/年
\]

基本料金例：

\[
0.4
	imes 1,300
	imes 12
=
6,240円/年
\]

合計：

\[
29,568円/台・年
\]

### 大型150cm型の例

```yaml
power_kw: 1.055
```

同条件での電力量料金：

\[
1.055
	imes 24
	imes 120
	imes 0.75
	imes 27
pprox
61,528円/年
\]

基本料金：

\[
1.055
	imes 1,300
	imes 12
pprox
16,458円/年
\]

合計：

\[
約77,986円/台・年
\]

大型型は標準0.4kW型の約2.6倍の運転費となる。

ただし、大型型が標準型の何台分を代替できるかは、風量値ではなく、牛体付近2m/s以上の実測範囲で判断する。

---

# 6. 初回の代表ファンモデル

全商品を登録せず、初回は以下の4種類に正規化する。

## 6.1 Standard 100

```yaml
id: standard_100
name: 標準100cm級
category: cow_body_airflow
diameter_cm: 100
rated_power_kw: 0.4
reference_airflow_m3_per_min: 300
covered_cows: 3
coverage_source: demo_default
```

用途：

- 全酪連例の再現
- 段階導入
- 全面導入
- 初回デモの中心

## 6.2 Efficient 100

```yaml
id: efficient_100
name: 省電力100cm級
category: cow_body_airflow
diameter_cm: 100
rated_power_kw: 0.25
reference_airflow_m3_per_min: null
covered_cows: null
coverage_source: requires_validation
```

用途：

- 電力費重視
- 標準型との感度比較

注意：

同じ3頭をカバーできることを確認するまでは、標準型と同じ効果を設定しない。

## 6.3 Spot 60

```yaml
id: spot_60
name: スポット60cm級
category: spot_airflow
diameter_cm: 60
rated_power_kw: 0.3
covered_cows: null
coverage_source: requires_measurement
```

用途：

- 風の死角
- 待機場所
- 高リスク区画
- 柱周辺

## 6.4 Large 150

```yaml
id: large_150
name: 大型150cm級
category: large_airflow
diameter_cm: 150
rated_power_kw: 1.055
covered_cows: null
coverage_source: requires_measurement
```

用途：

- 大空間
- リレー送風
- 台数制約のある牛舎
- 換気補助

---

# 7. シナリオ比較

## 7.1 60頭・既存10台の例

```yaml
farm:
  milking_cows: 60
  existing_fans: 10
  target_fans: 20
```

比較案：

```yaml
scenarios:
  - id: current
    name: 現状維持
    added_fans: 0

  - id: phase_1
    name: 標準100cm級を5台追加
    product_id: standard_100
    added_fans: 5
    newly_covered_cows: 15

  - id: full
    name: 標準100cm級を10台追加
    product_id: standard_100
    added_fans: 10
    newly_covered_cows: 30

  - id: large_trial
    name: 大型ファンによる代替案
    product_id: large_150
    added_fans: 3
    newly_covered_cows: null
```

大型案は、カバー頭数が未確定なため、投資回収に必要な乳量を確定表示しない。

---

# 8. 許容投資上限

実績またはシナリオ上の乳量低下防止量から、払える設備費を逆算できる。

## 8.1 年間に使える限界利益

\[
A_{	ext{available}}
=
M_{	ext{avoided}}
	imes N_{	ext{covered cows}}
	imes D_{	ext{heat}}
	imes P_{	ext{milk}}
	imes (1-v)
\]

## 8.2 設備費へ回せる年額

\[
A_{	ext{capex}}
=
A_{	ext{available}}
-
C_{	ext{electricity}}
-
C_{	ext{maintenance}}
\]

## 8.3 許容初期投資上限

定額法：

\[
I_{	ext{max}}
=
A_{	ext{capex}}
	imes L
\]

金利込み：

\[
I_{	ext{max}}
=
rac{A_{	ext{capex}}}{CRF(r,n)}
\]

出力名称は「許容投資上限」より、次の表現を優先する。

> この条件で払える設備・工事費の目安

---

# 9. 推測と確定値の区分

| 項目 | 区分 |
|---|---|
| カタログ本体価格 | 参考価格 |
| カタログ消費電力 | メーカー仕様 |
| カタログ風量 | メーカー仕様 |
| 電力費 | 計算値 |
| 設置工事費 | 見積または全酪連例 |
| 3頭に1台 | 公開資料上の目安 |
| 牛体付近2m/s | 実測または設計目標 |
| 大型ファンのカバー頭数 | 未確定 |
| 乳量低下防止量 | 農場実績またはシナリオ仮定 |
| 繁殖・疾病便益 | 初回計算対象外 |

画面上では次のラベルを付ける。

```text
［公開資料］
［メーカー仕様］
［参考価格］
［見積］
［農場実測］
［計算値］
［仮定］
［未確認］
```

---

# 10. 自動テスト

## 10.1 費用

- ファン台数が増えたとき、初期投資額が減らない
- 消費電力が増えたとき、年間電力量料金が減らない
- 電力単価が上がったとき、年間運転費が減らない
- 耐用年数が短くなったとき、年間設備負担が減らない

## 10.2 回収条件

- 乳価が上がったとき、必要乳量が増えない
- 変動費率が上がったとき、必要乳量が減らない
- 対象日数が増えたとき、1日当たり必要乳量が増えない
- 新規カバー頭数が増えたとき、1頭当たり必要乳量が増えない

## 10.3 製品比較

- カバー頭数が未確認の製品では、1頭当たりROIを確定しない
- 測定方法が異なる風量値を単純順位化しない
- 小型ファンへ3頭/台を自動適用しない
- 大型ファンを標準型の台数へ自動換算しない

---

# 11. 初回実装の推奨範囲

## 実装する

- 標準100cm級ファン
- 省電力100cm級ファン
- 60cm級スポットファン
- 150cm級大型ファン
- インバーター・コントローラー
- 初期投資
- 電力費
- 年換算費用
- 収支分岐点乳量
- 許容設備費
- 根拠区分

## 初回では実装しない

- 全製品からの自動最適化
- カタログ風量からの自動カバー頭数推定
- CFD
- ファンによる乳量改善量の一点予測
- 繁殖・疾病・淘汰の完全な金銭換算
- 製品の優劣ランキング

---

# 12. 参考資料と利用上の注意

## 全酪連

『COW BELL No.178 2025秋季号』
「暑熱対策の設備投資を考える」

主な利用箇所：

- 標準ファン：直径約1m、0.4kW
- 風速2m/s以上
- 3頭に1台以上
- 本体・インバーター・設置費
- 電力費
- 耐用年数
- 変動費率
- 乳価
- 収支分岐点乳量
- 3.2kg/頭・日の例

この計算は精密な事業計画ではなく、投資案を粗くふるい分ける「スケッチ」である。

## 十勝農業改良普及センター

『乳牛の暑熱対策チャレンジ ガイドブック in 十勝 資材一覧』

主な利用箇所：

- 100cm級軸流ファン
- 60cm級ファン
- 150cm級大型ファン
- 循環・リレー送風ファン
- ファンコントローラー
- メーカー仕様
- 令和6年12月時点の参考価格

注意：

- 掲載順は優劣を表さない
- 価格は実際の流通価格と異なる可能性がある
- 価格は変更される可能性がある
- セールスポイントはメーカーコメントを含む
- 効果や耐用年数は普及センターの実証値とは限らない
- 全製品を網羅していない
