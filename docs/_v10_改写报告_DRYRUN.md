# v10 改写报告

- 底稿：`PAPER_MANUSCRIPT_FINAL.docx`（只读）
- 计划行数 82；应用 80；band 说明 2；披露追加 2；致命 0
- 结构计数：`{"paragraphs": 409, "tables": 11, "m_oMath": 131, "m_oMathPara": 41, "w_drawing": 37}`

## band 行（文中无该串，仅作说明）

- seq 19 `P42`: `±1.8% / −1.8% to +1.1%` → `±1.8% / ±1.8%`（Table 8 派生带 · CRI 构造参数带（P42 的 ±2%））
- seq 28 `P79`: `±1.8% / −1.8% to +1.1%` → `±1.8% / ±1.8%`（Table 8 派生带 · CRI 构造参数带（P42 的 ±2%））

## 逐行结果

| seq | 位置 | 次 | 类别 | 状态 | OLD | NEW |
|---:|---|---:|---|---|---|---|
| 1 | `P4` | 1 | NUMERIC | applied | `40.2 billion` | `40.3 billion` |
| 2 | `P4` | 1 | NUMERIC | applied | `52%` | `53%` |
| 3 | `P14` | 1 | NUMERIC | applied | `6.2 billion` | `6.3 billion` |
| 4 | `P16` | 1 | NUMERIC | applied | `33.3 billion` | `33.4 billion` |
| 5 | `P16` | 1 | NUMERIC | applied | `40.2 billion` | `40.3 billion` |
| 6 | `P16` | 1 | NUMERIC | applied | `6.2 billion` | `6.3 billion` |
| 7 | `P16` | 1 | TEXT | applied | `above the historical no-defence level` | `above the historical defended level` |
| 8 | `P19` | 1 | NUMERIC | applied | `5.9 billion` | `6.0 billion` |
| 9 | `P19` | 1 | NUMERIC | applied | `0.83‰` | `0.82‰` |
| 10 | `P19` | 1 | NUMERIC | applied | `0.68‰` | `0.67‰` |
| 11 | `P19` | 1 | WATCH-PROMOTED | applied | `0.38‰` | `0.39‰` |
| 12 | `P21` | 1 | NUMERIC | applied | `1.57‰` | `1.56‰` |
| 13 | `P21` | 1 | NUMERIC | applied | `1.73‰` | `1.72‰` |
| 14 | `P24` | 1 | TEXT | applied | `Pudong, Yangpu, and Xuhui` | `Pudong, Yangpu, and Minhang` |
| 15 | `P41` | 1 | NUMERIC | applied | `438.9` | `440.3` |
| 16 | `P42` | 1 | NUMERIC | applied | `599` | `601` |
| 17 | `P42` | 1 | NUMERIC | applied | `673` | `675` |
| 18 | `P42` | 1 | NUMERIC | applied | `742` | `745` |
| 19 | `P42` | 1 | BAND | band-info | `±1.8% / −1.8% to +1.1%` | `±1.8% / ±1.8%` |
| 20 | `P49` | 1 | NUMERIC | applied | `439` | `441` |
| 21 | `P49` | 1 | NUMERIC | applied | `477` | `479` |
| 22 | `P49` | 1 | NUMERIC | applied | `52%` | `53%` |
| 23 | `P66` | 1 | BAND | applied | `−0.8% to ≈0%` | `−0.2% to +0.6%` |
| 24 | `P66` | 1 | NUMERIC | applied | `52%` | `53%` |
| 25 | `P77` | 1 | NUMERIC | applied | `599` | `601` |
| 26 | `P77` | 1 | NUMERIC | applied | `742` | `745` |
| 27 | `P77` | 1 | NUMERIC | applied | `52%` | `53%` |
| 28 | `P79` | 1 | BAND | band-info | `±1.8% / −1.8% to +1.1%` | `±1.8% / ±1.8%` |
| 29 | `P83` | 1 | NUMERIC | applied | `599` | `601` |
| 30 | `P83` | 1 | NUMERIC | applied | `742` | `745` |
| 31 | `P83` | 1 | NUMERIC | applied | `52%` | `53%` |
| 32 | `P194` | 1 | TEXT | applied | `Lianjia` | `Anjuke` |
| 33 | `P194` | 2 | TEXT | applied | `Lianjia` | `Anjuke` |
| 34 | `P194` | 3 | TEXT | applied | `Lianjia` | `Anjuke` |
| 35 | `P204` | 1 | TEXT | applied | `Lianjia (Beike)` | `Anjuke` |
| 36 | `T0#r2c1` | 1 | NUMERIC | applied | `33.3` | `33.4` |
| 37 | `T0#r2c2` | 1 | NUMERIC | applied | `23.8` | `23.9` |
| 38 | `T0#r3c1` | 1 | NUMERIC | applied | `40.2` | `40.3` |
| 39 | `T1#r1c1` | 1 | TABLE2-SWAP | applied | `5.9` | `6.0` |
| 40 | `T1#r3c0` | 1 | TABLE2-SWAP | applied | `Xuhui` | `Minhang` |
| 41 | `T1#r3c2` | 1 | TABLE2-SWAP | applied | `4.1` | `8.0` |
| 42 | `T1#r3c3` | 1 | TABLE2-SWAP | applied | `0.56` | `0.28` |
| 43 | `T1#r4c0` | 1 | TABLE2-SWAP | applied | `Minhang` | `Xuhui` |
| 44 | `T1#r4c1` | 1 | TABLE2-SWAP | applied | `2.3` | `2.2` |
| 45 | `T1#r4c2` | 1 | TABLE2-SWAP | applied | `8.0` | `4.0` |
| 46 | `T1#r4c3` | 1 | TABLE2-SWAP | applied | `0.28` | `0.56` |
| 47 | `T1#r5c3` | 1 | TABLE2-SWAP | applied | `0.83` | `0.82` |
| 48 | `T2#r1c1` | 1 | NUMERIC | applied | `490` | `491` |
| 49 | `T2#r1c2` | 1 | NUMERIC | applied | `599` | `601` |
| 50 | `T2#r1c3` | 1 | NUMERIC | applied | `689` | `692` |
| 51 | `T2#r2c1` | 1 | NUMERIC | applied | `564` | `565` |
| 52 | `T2#r2c2` | 1 | NUMERIC | applied | `673` | `675` |
| 53 | `T2#r2c3` | 1 | NUMERIC | applied | `768` | `770` |
| 54 | `T2#r3c1` | 1 | NUMERIC | applied | `641` | `643` |
| 55 | `T2#r3c2` | 1 | NUMERIC | applied | `742` | `745` |
| 56 | `T2#r3c3` | 1 | NUMERIC | applied | `837` | `840` |
| 57 | `T4#r1c1` | 1 | NUMERIC | applied | `351` | `354` |
| 58 | `T4#r1c3` | 1 | NUMERIC | applied | `456` | `457` |
| 59 | `T4#r2c1` | 1 | ROUND-BOUNDARY | applied | `395` | `394` |
| 60 | `T4#r2c2` | 1 | NUMERIC | applied | `439` | `441` |
| 61 | `T4#r2c3` | 1 | NUMERIC | applied | `498` | `499` |
| 62 | `T4#r3c2` | 1 | NUMERIC | applied | `477` | `479` |
| 63 | `T4#r3c3` | 1 | NUMERIC | applied | `533` | `534` |
| 64 | `T8#r3c5` | 1 | TABLE8 | applied | `21.1–28.1B` | `21.1–28.2B` |
| 65 | `T8#r4c5` | 1 | TABLE8 | applied | `18.7–31.6B` | `18.7–31.7B` |
| 66 | `T8#r5c5` | 1 | TABLE8 | applied | `22.6–25.7B` | `22.6–25.8B` |
| 67 | `T8#r5c6` | 1 | TABLE8 | applied | `−6.3% to +6.3%` | `−6% to +6%` |
| 68 | `T8#r6c5` | 1 | TABLE8 | applied | `22.6–27.5B` | `22.7–27.6B` |
| 69 | `T8#r7c5` | 1 | TABLE8 | applied | `23.1–26.4B` | `23.1–26.5B` |
| 70 | `T8#r8c5` | 1 | TABLE8 | applied | `22.0–28.7B` | `22.1–28.7B` |
| 71 | `T8#r13c4` | 1 | TABLE8 | applied | `599` | `601` |
| 72 | `T8#r13c5` | 1 | TABLE8 | applied | `594–610` | `596–612` |
| 73 | `T8#r14c4` | 1 | TABLE8 | applied | `599` | `601` |
| 74 | `T8#r14c5` | 1 | TABLE8 | applied | `588–606` | `590–607` |
| 75 | `T8#r15c6` | 1 | TABLE8 | applied | `−2.3% to +4.2%` | `−2% to +4%` |
| 76 | `T8#r16c6` | 1 | TABLE8 | applied | `≈0% to +2.6%` | `−0.1% to +2.6%` |
| 77 | `T8#r17c4` | 1 | TABLE8 | applied | `599` | `601` |
| 78 | `T8#r17c5` | 1 | TABLE8 | applied | `574–631` | `576–633` |
| 79 | `T8#r20c5` | 1 | TABLE8 | applied | `396–399` | `397–400` |
| 80 | `T8#r20c6` | 1 | TABLE8 | applied | `−0.8% to ≈0%` | `−0.2% to +0.6%` |
| 81 | `T10#r8c2` | 1 | TEXT | applied | `fi_01_housing_stress_index.png` | `fi_01_finance_risk_index.png` |
| 82 | `T10#r11c2` | 1 | TEXT | applied | `fi_04_hsi_vs_cri_overlay.png` | `fi_04_fri_vs_cri_overlay.png` |
| 0 | `P178` | 1 | DISCLOSURE | applied | `` | `The administrative boundary layer used throughout this study ...` |
| 0 | `P202` | 1 | DISCLOSURE | applied | `` | `Monthly mean temperature is computed as the arithmetic mean  ...` |