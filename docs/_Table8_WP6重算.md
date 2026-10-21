# Table 8 重算（WP6 灵敏度全量重跑后）

- 生成时间：2026-10-17 21:56:46
- 扫描数据：`sensitivity_results_20261017_212732.csv`（17 个 sweep / 85 个取值）
- 旧值来源：`PAPER_MANUSCRIPT_FINAL.docx` 的 Table 8 单元格（只读，未修改）
- 记账口径：`tools/audit_manuscript_consistency.py:build_table8_row()`
  （baseline = `is_baseline` 行；range = 5 个取值的 min–max；dev = (min/max − baseline)/baseline）

## 0. 摘要

| 项 | 17 行中改变 |
|---|---:|
| Baseline value 列 | **3** |
| Range of index 列 | **10** |
| Max deviation 列（字面差异） | 6 |
| 　其中**真实数值改变** | **4** |
| 　其中仅格式不同（数值兼容） | 1 |
| 　其中稿件手写值（未重算） | 1 |

> **Max deviation 列的判读**：本列对格式极敏感（`−6.3% to +6.3%` vs `−6% to +6%`）。
> 边界切换只让 CRI 动 ~0.3%，所以绝大多数行是**格式差异**而不是数值变化。
> 只有判定为 `CHANGE` 的行才需要改；`format-only` 行保持稿件原写法即可。

> 参数名、Baseline、Range tested、Primary index 四列不随扫描变化，无需改。

## 1. 逐行对照（17 个参数行）

| # | 参数 | 主指标 | OLD baseline | NEW baseline | OLD range | NEW range | OLD max dev | NEW max dev | dev 判读 |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | Surge MDR calibration scale | EAL | 24.2B | 24.2B | 21.5–28.6B | 21.5–28.6B | −11% to +18% | −11% to +18% | same |
| 2 | TC $V_{half}$ base scale | EAL | 24.2B | 24.2B | **21.1–28.1B** | **21.1–28.2B** | −13% to +16% | −13% to +16% | same |
| 3 | TC onset threshold $V_{thresh}$ | EAL | 24.2B | 24.2B | **18.7–31.6B** | **18.7–31.7B** | −23% to +31% | −23% to +31% | same |
| 4 | Surge vulnerability index $\gamma_{SVI}$ | EAL | 24.2B | 24.2B | **22.6–25.7B** | **22.6–25.8B** | −6.3% to +6.3% | **−6% to +6%** | CHANGE |
| 5 | $V_{half}$ adj. A\_old (pre-02 low-rise) | EAL | 24.2B | 24.2B | **22.6–27.5B** | **22.7–27.6B** | −6% to +14% | −6% to +14% | same |
| 6 | $V_{half}$ adj. A\_new (02+ low-rise) | EAL | 24.2B | 24.2B | **23.1–26.4B** | **23.1–26.5B** | −4% to +9% | −4% to +9% | same |
| 7 | $V_{half}$ adj. B\_old (pre-10 mid-rise) | EAL | 24.2B | 24.2B | **22.0–28.7B** | **22.1–28.7B** | −9% to +19% | −9% to +19% | same |
| 8 | $V_{half}$ adj. B\_new (10+ mid-rise) | EAL | 24.2B | 24.2B | 22.2–28.4B | 22.2–28.4B | −8% to +18% | −8% to +18% | same |
| 9 | $V_{half}$ adj. C (high-rise) | EAL | 24.2B | 24.2B | 24.2–24.2B | 24.2–24.2B | 0% | **$\approx$0%** | CHANGE |
| 10 | $V_{half}$ adj. D (commercial) | EAL | 24.2B | 24.2B | 23.5–25.5B | 23.5–25.5B | −3% to +5% | −3% to +5% | same |
| 11 | CRI EWMA decay ($\alpha$) | CRI | **599** | **601** | **594–610** | **596–612** | ±1.8% | ±1.8% | same |
| 12 | CRI damage boost cap ($\kappa_d$) | CRI | **599** | **601** | **588–606** | **590–607** | −1.8% to +1.1% | ±1.8% | format-only |
| 13 | HP filter $\lambda$ | FRI | 265 | 265 | 259–276 | 259–276 | −2.3% to +4.2% | **−2% to +4%** | CHANGE |
| 14 | Volatility window | FRI | 265 | 265 | 265–272 | 265–272 | ≈0% to +2.6% | **−0.1% to +2.6%** | CHANGE |
| 15 | Hazard SLA weight | CRI | **599** | **601** | **574–631** | **576–633** | −4.1% to +5.3% | −4.1% to +5.3% | same |
| 16 | FRI sub-indicator weights | FRI | 265 | 265 | 225–311 | 225–311 | −15% to +17% | −15% to +17% | same |
| 17 | CFCI target $\rho$ | CFCI | 399 | 399 | **396–399** | **397–400** | −0.8% to ≈0% | −0.2% to +0.6% | manuscript-hardcoded |

## 2. 可直接粘贴的新 Table 8（BibTeX 风格 LaTeX 行）

```latex
Surge MDR calibration scale & 0.176 & 0.10–0.30 & EAL & 24.2B & 21.5–28.6B & −11% to +18% \\
TC $V_{half}$ base scale & 1.0 & 0.85–1.15 & EAL & 24.2B & 21.1–28.2B & −13% to +16% \\
TC onset threshold $V_{thresh}$ & 25.7 m/s & 23.0–28.5 & EAL & 24.2B & 18.7–31.7B & −23% to +31% \\
Surge vulnerability index $\gamma_{SVI}$ & 0.15 & 0.00–0.30 & EAL & 24.2B & 22.6–25.8B & −6% to +6% \\
$V_{half}$ adj. A\_old (pre-02 low-rise) & 0.80 & 0.68–0.92 & EAL & 24.2B & 22.7–27.6B & −6% to +14% \\
$V_{half}$ adj. A\_new (02+ low-rise) & 0.90 & 0.77–1.03 & EAL & 24.2B & 23.1–26.5B & −4% to +9% \\
$V_{half}$ adj. B\_old (pre-10 mid-rise) & 0.95 & 0.81–1.09 & EAL & 24.2B & 22.1–28.7B & −9% to +19% \\
$V_{half}$ adj. B\_new (10+ mid-rise) & 1.00 & 0.85–1.15 & EAL & 24.2B & 22.2–28.4B & −8% to +18% \\
$V_{half}$ adj. C (high-rise) & 1.05 & 0.89–1.21 & EAL & 24.2B & 24.2–24.2B & $\approx$0% \\
$V_{half}$ adj. D (commercial) & 1.10 & 0.94–1.27 & EAL & 24.2B & 23.5–25.5B & −3% to +5% \\
CRI EWMA decay ($\alpha$) & 0.85 & 0.70–0.95 & CRI & 601 & 596–612 & ±1.8% \\
CRI damage boost cap ($\kappa_d$) & 0.50 & 0.00–1.00 & CRI & 601 & 590–607 & ±1.8% \\
HP filter $\lambda$ & 129,600 & 14,400–518,400 & FRI & 265 & 259–276 & −2% to +4% \\
Volatility window & 12 mo & 6–24 mo & FRI & 265 & 265–272 & −0.1% to +2.6% \\
Hazard SLA weight & 0.25 & 0.10–0.50 & CRI & 601 & 576–633 & −4.1% to +5.3% \\
FRI sub-indicator weights & Equal & See note & FRI & 265 & 225–311 & −15% to +17% \\
CFCI target $\rho$ & 0.411 & 0.0–0.8 & CFCI & 399 & 397–400 & −0.2% to +0.6% \\
```

## 3. 记账细节（供复核）

| sweep | 取值数 | baseline 原始值 | min | max | min 偏差% | max 偏差% | dev 来源 |
|---|---:|---:|---:|---:|---:|---:|---|
| SURGE_MDR_CALIBRATION_SCALE | 5 | 2.42035e+10 | 2.1499e+10 | 2.86162e+10 | -11.1741 | +18.2315 | recomputed (range0) |
| TC_V_HALF_BASE_SCALE | 5 | 2.42035e+10 | 2.11404e+10 | 2.81545e+10 | -12.6555 | +16.3242 | recomputed (range0) |
| TC_IMPACT_V_THRESH | 5 | 2.42035e+10 | 1.86928e+10 | 3.16918e+10 | -22.7683 | +30.9390 | recomputed (range0) |
| GAMMA_SVI | 5 | 2.42035e+10 | 2.26366e+10 | 2.57704e+10 | -6.4739 | +6.4739 | recomputed (range0) |
| V_HALF_ADJ_A_old | 5 | 2.42035e+10 | 2.26689e+10 | 2.75963e+10 | -6.3403 | +14.0179 | recomputed (range0) |
| V_HALF_ADJ_A_new | 5 | 2.42035e+10 | 2.3137e+10 | 2.6464e+10 | -4.4066 | +9.3397 | recomputed (range0) |
| V_HALF_ADJ_B_old | 5 | 2.42035e+10 | 2.20841e+10 | 2.87239e+10 | -8.7565 | +18.6765 | recomputed (range0) |
| V_HALF_ADJ_B_new | 5 | 2.42035e+10 | 2.22372e+10 | 2.84317e+10 | -8.1242 | +17.4694 | deviation_override（稿件手写，未随扫描重算） |
| V_HALF_ADJ_C | 5 | 2.42035e+10 | 2.42019e+10 | 2.42069e+10 | -0.0065 | +0.0141 | recomputed (approx0) |
| V_HALF_ADJ_D | 5 | 2.42035e+10 | 2.3543e+10 | 2.55171e+10 | -2.7290 | +5.4273 | recomputed (range0) |
| CRI_EWMA_ALPHA | 5 | 600.874 | 595.829 | 611.756 | -0.8397 | +1.8110 | recomputed (pm1) |
| CRI_DAMAGE_KAPPA | 5 | 600.874 | 590.001 | 607.416 | -1.8096 | +1.0887 | deviation_override（稿件手写，未随扫描重算） |
| HP_LAMBDA | 5 | 265.327 | 258.808 | 275.795 | -2.4569 | +3.9454 | recomputed (range0) |
| VOLATILITY_WINDOW | 5 | 265.327 | 265.063 | 272.194 | -0.0993 | +2.5883 | recomputed (range1) |
| CFI_WEIGHT_SLA | 5 | 600.874 | 576.234 | 632.592 | -4.1007 | +5.2786 | recomputed (range1) |
| FRI_WEIGHT_GAP | 5 | 265.327 | 225.338 | 311.475 | -15.0717 | +17.3931 | recomputed (range0) |
| CFCI_TARGET_RHO | 5 | 399.128 | 397.463 | 400.117 | -0.4171 | +0.2480 | deviation_override（稿件手写，未随扫描重算） |

## 4. Max deviation 列的全部候选格式（供作者选定）

| sweep | 稿件现值 | range0 | range1 | pm1 | approx0 |
|---|---|---|---|---|---|
| SURGE_MDR_CALIBRATION_SCALE | −11% to +18% | −11% to +18% | −11.2% to +18.2% | ±18.2% | $\approx$0% |
| TC_V_HALF_BASE_SCALE | −13% to +16% | −13% to +16% | −12.7% to +16.3% | ±16.3% | $\approx$0% |
| TC_IMPACT_V_THRESH | −23% to +31% | −23% to +31% | −22.8% to +30.9% | ±30.9% | $\approx$0% |
| GAMMA_SVI | −6.3% to +6.3% | −6% to +6% | −6.5% to +6.5% | ±6.5% | $\approx$0% |
| V_HALF_ADJ_A_old | −6% to +14% | −6% to +14% | −6.3% to +14.0% | ±14.0% | $\approx$0% |
| V_HALF_ADJ_A_new | −4% to +9% | −4% to +9% | −4.4% to +9.3% | ±9.3% | $\approx$0% |
| V_HALF_ADJ_B_old | −9% to +19% | −9% to +19% | −8.8% to +18.7% | ±18.7% | $\approx$0% |
| V_HALF_ADJ_B_new | −8% to +18% | −8% to +17% | −8.1% to +17.5% | ±17.5% | $\approx$0% |
| V_HALF_ADJ_C | 0% | −0% to +0% | −0.0% to +0.0% | ±0.0% | $\approx$0% |
| V_HALF_ADJ_D | −3% to +5% | −3% to +5% | −2.7% to +5.4% | ±5.4% | $\approx$0% |
| CRI_EWMA_ALPHA | ±1.8% | −1% to +2% | −0.8% to +1.8% | ±1.8% | $\approx$0% |
| CRI_DAMAGE_KAPPA | −1.8% to +1.1% | −2% to +1% | −1.8% to +1.1% | ±1.8% | $\approx$0% |
| HP_LAMBDA | −2.3% to +4.2% | −2% to +4% | −2.5% to +3.9% | ±3.9% | $\approx$0% |
| VOLATILITY_WINDOW | ≈0% to +2.6% | −0% to +3% | −0.1% to +2.6% | ±2.6% | $\approx$0% |
| CFI_WEIGHT_SLA | −4.1% to +5.3% | −4% to +5% | −4.1% to +5.3% | ±5.3% | $\approx$0% |
| FRI_WEIGHT_GAP | −15% to +17% | −15% to +17% | −15.1% to +17.4% | ±17.4% | $\approx$0% |
| CFCI_TARGET_RHO | −0.8% to ≈0% | −0% to +0% | −0.4% to +0.2% | ±0.4% | $\approx$0% |

