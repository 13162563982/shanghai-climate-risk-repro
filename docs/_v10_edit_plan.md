# v10 改稿执行清单（WP7.2）

- 生成器：`tools/make_edit_plan.py`
- 来源：`docs/_数字变更对照表.md`（自动解析）+ 4 张显式 override 表（代码内）
- 机器可读版：`docs/_v10_edit_plan.csv`（**改写工具只认这个**）

## 摘要

| 项 | 数 |
|---|---:|
| 对照表条目 | 285 |
| 　CHANGE | 75 |
| 　same | 44 |
| 　watch | 7 |
| CHANGE 中因精度未变而 **无需改字** | 25 |
| CHANGE 中被表级 override 接管 | 4 |
| band 型仅作说明（文中无该串） | 0 |
| **最终编辑行数** | **82** |
| 　NUMERIC | 43 |
| 　ROUND-BOUNDARY | 1 |
| 　BAND | 3 |
| 　TABLE2-SWAP | 9 |
| 　TABLE8 | 17 |
| 　TEXT | 8 |
| 　WATCH-PROMOTED | 1 |

## `same` 行中 token 与登记值不对应（判为登记错位，不改）

| 位置 | token | 由 OLD 复算 | 由 NEW 复算 | 量 |
|---|---|---|---|---|
| `P4` | `66%` | `34%` | `34%` | Table 1 · T1 SSP5-8.5 (+0.5 m SLR) Reduction |
| `P4` | `40%` | `34%` | `34%` | Table 1 · T1 SSP5-8.5 (+0.5 m SLR) Reduction |
| `P19` | `0.38‰` | `0.39‰` | `0.39‰` | 2.6 派生文本量 · 全市平均 EAL/暴露（16 区均值） |
| `T4#r2c1` | `395` | `394` | `394` | Table 5 · T5 ssp245 p10 |

## 作废条目（不执行）

- `T8#r8c0` 原提议 `adj. B_old` — **NO-OP: the V_half symbol is an m:oMath object present in the XML; inserting literal LaTeX would duplicate it**

## 精度未变（CHANGE 但不用改字）

| 位置 | token | NEW | 量 |
|---|---|---:|---|
| `P4` | `24.2 billion` | 24.204 | 2.6 城市 EAL · 城市复合 EAL hist / nodef |
| `P4` | `21.5%` | 21.48 | 2.6 防御削减率 · 6 m 海塘削减率 hist |
| `P4` | `74%` | 74.12 | 2.6 风/潮占比 · 风损占比 hist/nodef |
| `P4` | `26%` | 25.88 | 2.6 风/潮占比 · 潮损占比 hist/nodef |
| `P6` | `63.3 trillion` | 63.3279 | 2.6 总暴露 · 总暴露 (T CNY) |
| `P9` | `63.3 trillion` | 63.3279 | 2.6 总暴露 · 总暴露 (T CNY) |
| `P14` | `24.2 billion` | 24.204 | 2.6 城市 EAL · 城市复合 EAL hist / nodef |
| `P14` | `17.9 billion` | 17.9404 | 2.6 派生文本量 · 风损 EAL hist/nodef (bn) |
| `P14` | `74%` | 74.12 | 2.6 风/潮占比 · 风损占比 hist/nodef |
| `P14` | `26%` | 25.88 | 2.6 风/潮占比 · 潮损占比 hist/nodef |
| `P14` | `19.0 billion` | 19.006 | 2.6 城市 EAL · 城市复合 EAL hist / def |
| `P14` | `21.5%` | 21.48 | 2.6 防御削减率 · 6 m 海塘削减率 hist |
| `P16` | `26.5 billion` | 26.519 | 2.6 城市 EAL · 城市复合 EAL ssp585 / def |
| `P19` | `0.77‰` | 0.7678 | 2.6 区级 EAL/暴露 · 杨浦区 EAL/暴露 |
| `P19` | `0.40‰` | 0.4043 | 2.6 区级 EAL/暴露 · 浦东新区 EAL/暴露 |
| `P49` | `130` | 129.778 | 2.6 CCHI · CCHI 2011-12 |
| `P49` | `313` | 313.437 | 2.6 CCHI · CCHI 2023-12 |
| `P49` | `399` | 399.128 | 2.6 CCHI · CCHI 2050 p50 hist |
| `P77` | `74%` | 74.12 | 2.6 风/潮占比 · 风损占比 hist/nodef |
| `P77` | `21.5%` | 21.48 | 2.6 防御削减率 · 6 m 海塘削减率 hist |
| `P79` | `21.5%` | 21.48 | 2.6 防御削减率 · 6 m 海塘削减率 hist |
| `P79` | `34.2%` | 34.19 | 2.6 防御削减率 · 6 m 海塘削减率 ssp585 |
| `P83` | `74%` | 74.12 | 2.6 风/潮占比 · 风损占比 hist/nodef |
| `P83` | `21.5%` | 21.48 | 2.6 防御削减率 · 6 m 海塘削减率 hist |
| `P83` | `26.5 billion` | 26.519 | 2.6 城市 EAL · 城市复合 EAL ssp585 / def |

## 逐位置编辑

### `P4` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 1 | `40.2 billion` | `40.3 billion` | NUMERIC | 2.6 城市 EAL · 城市复合 EAL ssp585 / nodef |
| 1 | 2 | `52%` | `53%` | NUMERIC | 2.6 派生文本量 · CCHI SSP5-8.5 相对 2023 末值增幅 |

### `P14` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 3 | `6.2 billion` | `6.3 billion` | NUMERIC | 2.6 风/潮占比 · 潮损 EAL hist/nodef (bn) |

### `P16` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 4 | `33.3 billion` | `33.4 billion` | NUMERIC | 2.6 城市 EAL · 城市复合 EAL ssp245 / nodef |
| 1 | 5 | `40.2 billion` | `40.3 billion` | NUMERIC | 2.6 城市 EAL · 城市复合 EAL ssp585 / nodef |
| 1 | 6 | `6.2 billion` | `6.3 billion` | NUMERIC | 2.6 风/潮占比 · 潮损 EAL hist/nodef (bn) |
| 1 | 7 | `above the historical no-defence level` | `above the historical defended level` | TEXT | 39.5% = 26.5185/19.0056-1, i.e. vs the historical DEFENDED residual |

### `P19` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 8 | `5.9 billion` | `6.0 billion` | NUMERIC | 2.6 区级 Top5 EAL · 区级 EAL #1 浦东新区 |
| 1 | 9 | `0.83‰` | `0.82‰` | NUMERIC | 2.6 区级 EAL/暴露 · 虹口区 EAL/暴露 |
| 1 | 10 | `0.68‰` | `0.67‰` | NUMERIC | 2.6 区级 EAL/暴露 · 黄浦区 EAL/暴露 |
| 1 | 11 | `0.38‰` | `0.39‰` | WATCH-PROMOTED | 16-district mean EAL/exposure; both the old and the A baseline give 0.39 |

### `P21` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 12 | `1.57‰` | `1.56‰` | NUMERIC | 2.6 派生文本量 · SSP5-8.5 区级 EAL/暴露 Yangpu |
| 1 | 13 | `1.73‰` | `1.72‰` | NUMERIC | 2.6 派生文本量 · SSP5-8.5 区级 EAL/暴露 Hongkou |

### `P24` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 14 | `Pudong, Yangpu, and Xuhui` | `Pudong, Yangpu, and Minhang` | TEXT | A-baseline top-3 contributors: Minhang replaces Xuhui |

### `P41` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 15 | `438.9` | `440.3` | NUMERIC | 2.6 CRI · CRI 2023-12 |

### `P42` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 16 | `599` | `601` | NUMERIC | 2.6 CRI · CRI 2050 p50 hist |
| 1 | 17 | `673` | `675` | NUMERIC | 2.6 CRI · CRI 2050 p50 ssp245 |
| 1 | 18 | `742` | `745` | NUMERIC | 2.6 CRI · CRI 2050 p50 ssp585 |
| 1 | 19 | `±1.8% / −1.8% to +1.1%` | `±1.8% / ±1.8%` | BAND | Table 8 派生带 · CRI 构造参数带（P42 的 ±2%） |

### `P49` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 20 | `439` | `441` | NUMERIC | 2.6 CCHI · CCHI 2050 p50 ssp245 |
| 1 | 21 | `477` | `479` | NUMERIC | 2.6 CCHI · CCHI 2050 p50 ssp585 |
| 1 | 22 | `52%` | `53%` | NUMERIC | 2.6 派生文本量 · CCHI SSP5-8.5 相对 2023 末值增幅 |

### `P66` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 23 | `−0.8% to ≈0%` | `−0.2% to +0.6%` | BAND | Table 8 派生带 · CFCI 目标 ρ 带（P66 的 −0.8% to ≈0%） |
| 1 | 24 | `52%` | `53%` | NUMERIC | 2.6 派生文本量 · CCHI SSP5-8.5 相对 2023 末值增幅 |

### `P77` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 25 | `599` | `601` | NUMERIC | 2.6 CRI · CRI 2050 p50 hist |
| 1 | 26 | `742` | `745` | NUMERIC | 2.6 CRI · CRI 2050 p50 ssp585 |
| 1 | 27 | `52%` | `53%` | NUMERIC | 2.6 派生文本量 · CCHI SSP5-8.5 相对 2023 末值增幅 |

### `P79` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 28 | `±1.8% / −1.8% to +1.1%` | `±1.8% / ±1.8%` | BAND | Table 8 派生带 · CRI 构造参数带（P42 的 ±2%） |

### `P83` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 29 | `599` | `601` | NUMERIC | 2.6 CRI · CRI 2050 p50 hist |
| 1 | 30 | `742` | `745` | NUMERIC | 2.6 CRI · CRI 2050 p50 ssp585 |
| 1 | 31 | `52%` | `53%` | NUMERIC | 2.6 派生文本量 · CCHI SSP5-8.5 相对 2023 末值增幅 |

### `P194` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 32 | `Lianjia` | `Anjuke` | TEXT | figure-1 caption / exposure source: url host is anjuke.com |
| 2 | 33 | `Lianjia` | `Anjuke` | TEXT | occurrence 2 of 3 |
| 3 | 34 | `Lianjia` | `Anjuke` | TEXT | occurrence 3 of 3 |

### `P204` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 35 | `Lianjia (Beike)` | `Anjuke` | TEXT | housing-market source: url host is anjuke.com |

### `T0#r2c1` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 36 | `33.3` | `33.4` | NUMERIC | Table 1 · T1 SSP2-4.5 (+0.3 m SLR) No Defence |

### `T0#r2c2` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 37 | `23.8` | `23.9` | NUMERIC | Table 1 · T1 SSP2-4.5 (+0.3 m SLR) Current 6 m |

### `T0#r3c1` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 38 | `40.2` | `40.3` | NUMERIC | Table 1 · T1 SSP5-8.5 (+0.5 m SLR) No Defence |

### `T1#r1c1` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 39 | `5.9` | `6.0` | TABLE2-SWAP | Pudong 5.9286 -> 5.9944 (1 dp) |

### `T1#r3c0` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 40 | `Xuhui` | `Minhang` | TABLE2-SWAP | row swap: A-baseline rank 3 = Minhang |

### `T1#r3c2` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 41 | `4.1` | `8.0` | TABLE2-SWAP | row swap: Minhang exposure 8.0 T |

### `T1#r3c3` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 42 | `0.56` | `0.28` | TABLE2-SWAP | row swap: Minhang ratio 0.2825 permille |

### `T1#r4c0` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 43 | `Minhang` | `Xuhui` | TABLE2-SWAP | row swap: A-baseline rank 4 = Xuhui |

### `T1#r4c1` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 44 | `2.3` | `2.2` | TABLE2-SWAP | row swap: Xuhui EAL 2.2211 bn |

### `T1#r4c2` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 45 | `8.0` | `4.0` | TABLE2-SWAP | row swap: Xuhui exposure 3.98 T |

### `T1#r4c3` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 46 | `0.28` | `0.56` | TABLE2-SWAP | row swap: Xuhui ratio 0.5575 permille |

### `T1#r5c3` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 47 | `0.83` | `0.82` | TABLE2-SWAP | Hongkou 0.8266 -> 0.8214 permille |

### `T2#r1c1` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 48 | `490` | `491` | NUMERIC | Table 3 · T3 hist p10 |

### `T2#r1c2` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 49 | `599` | `601` | NUMERIC | Table 3 · T3 hist p50 |

### `T2#r1c3` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 50 | `689` | `692` | NUMERIC | Table 3 · T3 hist p90 |

### `T2#r2c1` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 51 | `564` | `565` | NUMERIC | Table 3 · T3 ssp245 p10 |

### `T2#r2c2` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 52 | `673` | `675` | NUMERIC | Table 3 · T3 ssp245 p50 |

### `T2#r2c3` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 53 | `768` | `770` | NUMERIC | Table 3 · T3 ssp245 p90 |

### `T2#r3c1` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 54 | `641` | `643` | NUMERIC | Table 3 · T3 ssp585 p10 |

### `T2#r3c2` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 55 | `742` | `745` | NUMERIC | Table 3 · T3 ssp585 p50 |

### `T2#r3c3` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 56 | `837` | `840` | NUMERIC | Table 3 · T3 ssp585 p90 |

### `T4#r1c1` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 57 | `351` | `354` | NUMERIC | Table 5 · T5 hist p10 |

### `T4#r1c3` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 58 | `456` | `457` | NUMERIC | Table 5 · T5 hist p90 |

### `T4#r2c1` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 59 | `395` | `394` | ROUND-BOUNDARY | Table 5 SSP2-4.5 p10: registry OLD 394.50 prints 395 under half-up rounding while WP7.1 recorded OLD/NEW as 394/394; the A baseline is 393.73, which prints 394 |

### `T4#r2c2` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 60 | `439` | `441` | NUMERIC | Table 5 · T5 ssp245 p50 |

### `T4#r2c3` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 61 | `498` | `499` | NUMERIC | Table 5 · T5 ssp245 p90 |

### `T4#r3c2` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 62 | `477` | `479` | NUMERIC | Table 5 · T5 ssp585 p50 |

### `T4#r3c3` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 63 | `533` | `534` | NUMERIC | Table 5 · T5 ssp585 p90 |

### `T8#r3c5` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 64 | `21.1–28.1B` | `21.1–28.2B` | TABLE8 | TC V_half base scale range |

### `T8#r4c5` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 65 | `18.7–31.6B` | `18.7–31.7B` | TABLE8 | TC V_thresh range |

### `T8#r5c5` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 66 | `22.6–25.7B` | `22.6–25.8B` | TABLE8 | GAMMA_SVI range |

### `T8#r5c6` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 67 | `−6.3% to +6.3%` | `−6% to +6%` | TABLE8 | GAMMA_SVI max dev |

### `T8#r6c5` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 68 | `22.6–27.5B` | `22.7–27.6B` | TABLE8 | V_HALF_ADJ_A_old range |

### `T8#r7c5` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 69 | `23.1–26.4B` | `23.1–26.5B` | TABLE8 | V_HALF_ADJ_A_new range |

### `T8#r8c5` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 70 | `22.0–28.7B` | `22.1–28.7B` | TABLE8 | V_HALF_ADJ_B_old range |

### `T8#r13c4` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 71 | `599` | `601` | TABLE8 | CRI_EWMA_ALPHA baseline (CRI 600.874 -> 601) |

### `T8#r13c5` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 72 | `594–610` | `596–612` | TABLE8 | CRI_EWMA_ALPHA range |

### `T8#r14c4` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 73 | `599` | `601` | TABLE8 | CRI_DAMAGE_KAPPA baseline |

### `T8#r14c5` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 74 | `588–606` | `590–607` | TABLE8 | CRI_DAMAGE_KAPPA range |

### `T8#r15c6` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 75 | `−2.3% to +4.2%` | `−2% to +4%` | TABLE8 | HP_LAMBDA max dev |

### `T8#r16c6` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 76 | `≈0% to +2.6%` | `−0.1% to +2.6%` | TABLE8 | VOLATILITY_WINDOW max dev [ruling 15] |

### `T8#r17c4` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 77 | `599` | `601` | TABLE8 | CFI_WEIGHT_SLA baseline |

### `T8#r17c5` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 78 | `574–631` | `576–633` | TABLE8 | CFI_WEIGHT_SLA range |

### `T8#r20c5` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 79 | `396–399` | `397–400` | TABLE8 | CFCI_TARGET_RHO range |

### `T8#r20c6` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 80 | `−0.8% to ≈0%` | `−0.2% to +0.6%` | TABLE8 | CFCI_TARGET_RHO max dev [ruling 14] |

### `T10#r8c2` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 81 | `fi_01_housing_stress_index.png` | `fi_01_finance_risk_index.png` | TEXT | stale figure filename in the figure index (WP5 rename) |

### `T10#r11c2` 

| # | 序 | OLD | NEW | 类别 | 说明 |
|---:|---:|---|---|---|---|
| 1 | 82 | `fi_04_hsi_vs_cri_overlay.png` | `fi_04_fri_vs_cri_overlay.png` | TEXT | stale figure filename in the figure index (WP5 rename) |
