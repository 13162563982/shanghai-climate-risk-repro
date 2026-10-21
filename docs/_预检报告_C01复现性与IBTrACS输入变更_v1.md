# 预检报告：C01 复现性与 IBTrACS 输入变更

**性质**：`_执行方案_官方边界重跑与稿件更新_v1.md` 的前置探针报告。它**改变方案的关键假设**，必须在 WP0 之前处理。
**日期**：2026-10-16
**执行**：C01 决定性探针（隔离重跑 ×2 + 旧版 IBTrACS 快照重跑 ×1），全部输出重定向至 `_c01_probe\`，未改写任何权威产物。

---

## 0. 结论摘要（先看这一节）

方案 §2.4 的前提是：**"替换边界层是本轮唯一的操作性变更"**。本次探针**证伪了该前提**。

真实情况是：**权威 C01 台风输入文件 `IBTrACS.WP.v04r01.nc` 已于 2026-07-25 被原地更新**，而稿件与既有产物取自 2026-03-28 的旧版输入。用当前文件重跑 C01 得到：

| 量 | 既有产物（对应稿件） | 当前文件重跑 | 影响 |
|---|---|---|---|
| 历史台风事件数 | **107** | **108** | 稿件 P17 的 "107 historical TC events" 失效 |
| 合成实现数 | **1,177**（=107×11） | **1,188**（=108×11） | 稿件 P17 的 "1,070"（=107×10，仅生成项）失效 |
| 每个事件频率 | 1/81 = 0.0123457 | **1/82 = 0.0121951** | **全部**事件频率统一 **−1.23%** |

频率口径从 1/81 变到 1/82，意味着**所有**历史与合成事件的泊松频率整体下降 1.23%。这**比边界替换造成的城市 EAL 变动（0.2099%）大一个数量级**。

### 最终结论（探针已跑完，无需再跑）

把 `IBTRACS_FILE` 钉到已保存的旧版快照后，**C01 的全部数值与 2026-03-28 权威产物逐位一致**
—— `haz_TC_hist` / `haz_TC_synth` / `haz_TC_ssp245` 的 `intensity` 稀疏矩阵、`date`、`event_id`、
`frequency`、`event_name`、`centroids` lat/lon，以及两个轨道 pkl 的全部变量，**均逐位相同**；
唯一差异是库版本造成的序列化 schema 与整型位宽（详见 §5）。

**因此方案的前提恢复成立**：
- 边界层即**唯一**变量 → A1/A2 归因干净（方案 §1 验收标准有效）
- C01 确定性成立 → **WP4/WP5 可做两条独立全链**，无需启用 §2.3.1 的"共用 C01 产物"备用策略
- 稿件改动范围**不变**（仍只改边界相关数字）→ 方案 §5 文件清单与 §8 时间预算（17–20 h）**均不变**

**两个必须落实的动作**：① 钉住 `IBTRACS_FILE` 与 Knutson 因子 1.0324 / 1.0442；
② **立即备份 `_old_202510.nc`**（107 事件口径的唯一副本）。**可直接进入 WP0。**

因此存在两条互斥路线（见 §4）：
- **路线 A（✅ 作者已裁定采用，2026-10-16）**：把 `IBTRACS_FILE` 钉到已保存的旧版快照，**使"边界层"重新成为唯一变量**，稿件只需按原方案改边界相关的数字。**探针已确认该快照恰好重现 107 事件与 1,177 条合成轨道**（见 §2.2）。
- **路线 B**：接受新版 IBTrACS，则稿件必须**同时**为"台风目录变更"与"边界层替换"两件事改数字，且 `AAL pred/obs = 0.9999` 的验证结论会失效（见 §2.7）。

---

## 1. 触发原因

按方案 §2.3.1，"C01 是否逐位可复现"决定 WP4/WP5 能否作为两条独立全链。探针设计为：把 `INTERMEDIATE_DIR` 派生出的 7 个叶子输出路径经 `V8_PARAM_OVERRIDES` 重定向到隔离目录，连跑两次 C01，比对 SHA256 与数值。

跑第一次时日志即出现：

```
20:26:56 [INFO] Hist wind: 108 events, max=55.5 m/s
20:27:15 [INFO] Synthetic: 1188 tracks (orig 108 + synth)
```

而已知既有产物为 107 / 1,177。故立即转入溯源。

---

## 2. 证据链

### 2.1 事件集合差异（直接读取 HDF5 与 pkl）

`Climate\output\intermediate\haz_TC_hist.hdf5`（权威）vs `_c01_probe\run1\haz_TC_hist.hdf5`（本次重跑）：

| 属性 | 权威（2026-03-28） | 本次重跑 |
|---|---|---|
| `event_name` 条数 | **107** | **108** |
| `frequency[0]` | 0.01234568 (=1/81) | 0.01219512 (=1/82) |
| `date` 范围 | 710281 – 739455 | 710281 – **739798** |
| `intensity` nnz | 715,417 | 728,848 |
| `intensity` max | 55.5429 | 55.5429 |
| `intensity` min | 17.5000 | 17.5000 |
| `intensity` sum | 1.6231e7 | 1.6535e7 |

轨道集合（`tc_tracks_shanghai.pkl`，按 `sid` 比对）：

```
shipped n=107   probe n=108
仅在权威（2 条）: 2025194N31124, 2025204N19121
仅在本次（3 条）: 2025193N30123, 2025203N20124, 2026182N09163
共有            : 105
```

**读数**：两条 2025 年风暴的编号/定位被修订（`...194N31124`→`...193N30123`、`...204N19121`→`...203N20124`），并**新增一条 2026 年风暴 `2026182N09163`**（182 = 2026 年第 182 天 ≈ 7 月初）。107 − 2 + 2 + 1 = **108**。

新增 2026 年事件把记录跨度从 1945–2025（81 年）拉到 1945–**2026**（82 年），故 `frequency = 1/82`。这是 IBTrACS 作为"活数据集"被修订的典型表现。

### 2.2 输入文件溯源

| 文件 | 字节数 | mtime | SHA256 |
|---|---|---|---|
| `data\Hazard_data\WP台风数据\IBTrACS.WP.v04r01.nc`（现行） | 7,722,045 | **2026-07-25 14:10:05** | `2A9C84745BF8344CED56AD435163ECC1E7F446106CCE9F5B55E252B6AF23C780` |
| `…\IBTrACS.WP.v04r01_old_202510.nc`（快照） | **8,904,634** | 2026-02-13 12:16:52 | `DA05013357E6ADFC11DAE72C5830BED602A6C2AAFC3F3C228653850BA8DEF91D` |
| `期刊投稿\Nature-JF投稿\CLIMADA改进\快速通道\input_data\ibtracs\IBTrACS.WP.v04r01.nc` | 7,722,045 | 2026-07-25 14:10:05 | 与现行**同哈希** |
| 上级工程 `复现公报台风研究结果\data\Hazard_data\WP台风数据\IBTrACS.WP.v04r01.nc`（原始出处） | — | — | **已不存在** |

决定性provenance证据来自 `data\Hazard_data\WP台风数据\preprocess_copy_typhoon.log`：

```
2026-03-07 14:42:20,218 [INFO] 正在复制: …\复现公报台风研究结果\data\Hazard_data\WP台风数据\IBTrACS.WP.v04r01.nc
                              → …\model_房地产风险_v6\data\Hazard_data\WP台风数据\IBTrACS.WP.v04r01.nc
2026-03-07 14:42:20,225 [INFO] 复制完成: IBTrACS.WP.v04r01.nc (8.9 MB)
```

2026-03-07 复制进来的文件是 **8.9 MB**；快照 `_old_202510.nc` 恰为 8,904,634 B = **8.9 MB**，而现行文件是 7.7 MB。**因此 `_old_202510.nc` 极可能就是产出 107 事件的那一份输入。**

**已用探针验证（决定性证据）**：

```
旧版快照：20:30:01 [INFO] Filtered: 107/2304 tracks affect Shanghai
          20:30:20 [INFO] Hist wind: 107 events, max=55.5 m/s
          20:30:39 [INFO] Synthetic: 1177 tracks (orig 107 + synth)

现行文件：20:26:40 [INFO] Filtered: 108/2310 tracks affect Shanghai
          20:26:56 [INFO] Hist wind: 108 events, max=55.5 m/s
          20:27:15 [INFO] Synthetic: 1188 tracks (orig 108 + synth)
```

两点均吻合：旧版快照给出 **107 事件 / 1,177 合成轨道**（=107×11），与权威产物**完全一致**；现行文件给出 108 / 1,188。同时 `tc_all.size` 由 2304 增至 2310（多 6 条轨道），亦为 IBTrACS 被修订的旁证。

**结论：路线 A 可行。** `IBTRACS_FILE` 一旦钉到 `_old_202510.nc`，边界层即恢复为唯一变量。

### 2.3 代码归属：v7 与 v8 的 C01 代码逐字节相同

2026-03-28 的 C01 日志中出现：

```
01:30:03 [INFO] [alpha_temp] Saved: …\model_房地产风险_v7\Climate\output\intermediate\alpha_temp_series.csv
```

即权威产物实际由 **v7** 生成后被带入 v8。为确认这不会引入第二个变量，做了 v7/v8 源码比对：

| 文件 | 结果 |
|---|---|
| `Climate\01_hazard_tc.py` | **完全相同**（各 241 行，mtime 均为 2026-03-24 20:32:35） |
| `Climate\climate_functions.py` | **完全相同**（各 610 行） |
| `Climate\02_hazard_surge.py` | **完全相同**（各 228 行） |
| `Climate\00_config.py` | 36 行不同（v7 372 行 / v8 396 行） |

`00_config.py` 的差异全部是 v8 的新增与注释改写：
- v8 新增 `apply_sensitivity_overrides()`（方案依赖的重定向机制）
- v8 把 `SURGE_MDR_CALIBRATION_SCALE = 0.176` 的注释改写为"raw HAZUS → 运行时标定"
- **v7 有 `TC_WIND_MITIGATION_FACTOR = 0.35`，v8 删除**

**结论**：v8 的 C01 与产出权威产物的 v7 代码**同源同字节**，因此"107 → 108"**不可能**由 v8 的代码改动造成，**只能**归因于 IBTrACS 输入文件被更新。这使归因非常干净。

**附带确认**：`TC_WIND_MITIGATION_FACTOR` 在 v8 的**任何 `.py` 文件中均无引用**（grep 仅命中 `docs\TABLE_AUDIT_REPORT.md`、若干 `_sensitivity_results\*.csv` 备份与日志）。故 v8 删除该常量是安全的，不会引发 `AttributeError`。

### 2.4 Knutson 缩放因子：实测值与 config 兜底不一致

2026-03-28 权威日志：

```
01:29:59 [INFO] SSP2-4.5: intensity factor = 1.0324
01:30:00 [INFO] SSP5-8.5: intensity factor = 1.0442
```

而 `00_config.py` 的兜底值为：

```python
SSP_TC_INTENSITY_FACTOR_2050 = {'SSP2-4.5': 1.05, 'SSP5-8.5': 1.1}
```

`01_hazard_tc.py:137-147` 是"先联网取 Knutson 表，`except` 静默回退到 config 常量"。**实测 1.0324 / 1.0442 ≠ 兜底 1.05 / 1.10。**

这直接回答了方案 §2.3.1 遗留项 2，并且是**比原判断更严重的结论**：
- 原判断："能跑通 ≠ 结果一致"，风险待查。
- 实测结论：**联网与断网会产生不同的 SSP 情景结果**（强度因子差 1.7% / 5.4%）。若申请"断网可复现"（A8），必须**同时**把这两个因子钉进配置或离线表，否则 `haz_TC_ssp245/585.hdf5` 不可复现。

### 2.5 HDF5 schema 差异（影响"逐位相同"的判据）

| | 权威 | 本次重跑 |
|---|---|---|
| 根组 | 15 个，含 **`intensity_thres`** | 14 个，**无 `intensity_thres`** |

`intensity_thres` 是 climada 版本差异导致的写出差异（当前环境在阈值为默认值时不写该组）。含义：**"逐位相同"不是合适的验收判据**，应以数值比对（`_c01_probe\compare_values.py` 已实现）为准。这与方案 §6 已有的"parquet/序列化漂移按数值判断"原则一致，但需扩展到 HDF5。

### 2.6 校准是固定常数，`0.9999` 不会自愈

`00_config.py:259-271`：

```python
TC_V_HALF_BASE_SCALE = 1.0        # WP3 regional calibration baseline
SURGE_MDR_CALIBRATION_SCALE = 0.176
# Period-matched validation (v6 04b): AAL pred/obs = 0.9999 for 1995-2023.
```

`04_vulnerability.py:45,71` 使用 climada 的 `calibrated_regional_vhalf(calibration_approach="TDR")` 与固定的 `SURGE_MDR_CALIBRATION_SCALE`。

**含义**：模型**没有**运行时重解标定。`AAL pred/obs = 0.9999` 是 v6 时期用旧台风目录**一次算出的验证结果**，写在注释里、并被稿件正文引用（P17）。一旦台风目录变为 108 事件 / 频率 1/82，该比值**必然改变**，且**不会自动回到 0.9999**。

这是路线 B 的第三个独立代价（另两个是事件数与频率）。

### 2.7 边界层重定向机制已验证可用（顺带完成，结论：PASS）

`_c01_probe\check_boundary_override.py` 验证 `V8_PARAM_OVERRIDES` 能真正改掉 `ADMIN_BOUNDARY_SHP`：

| 检查项 | 实测 | 期望 | |
|---|---|---|---|
| features | 16 | 16 | ✅ |
| CRS | EPSG:4326 | — | ✅ |
| 列名含 `县` | 是 | 是（`spatial_join_to_district` 依赖） | ✅ |
| 16 个区名 | 全部标准名 | — | ✅ |
| 几何类型 | Polygon / MultiPolygon | — | ✅ |
| 全部有效 | True | True | ✅ |
| 顶点总数 | **780** | 780 | ✅ |
| 总面积 (EPSG:32651) | **7,205.07 km²** | 7,205.07 | ✅ |
| 区与区两两重叠面积 | 0.00000000 deg² | ≈0 | ✅ |

**副产物（潜在陷阱，需记录）**：DBF 字段名有 10 字符上限，`build_admin_boundary.py:78` 的 `RENAME` 映射 `市代码→adcode_city`、`省代码→adcode_prov` **在落盘时被静默截断为 `adcode_cit` / `adcode_pro`**（内存中的 GDF 仍是全名，故 builder 自身的 `L119` 校验会通过）。已 grep 确认这两个列名**不被任何下游 v8 代码引用**，故当前无害；但应在 README 中记为已知陷阱，避免他人误读。

---

### 2.8 探针自身的失败：并发跑两个 C01 会 OOM（重要运维约束）

第一次探针中 `run1` 在合成风场阶段崩溃（`run_probe.ps1` 记录 `rc=1`，`elapsed=225.5s`）：

```
multiprocess.pool.RemoteTraceback:
  climada\hazard\trop_cyclone\trop_cyclone_windfields.py, line 614, in _x_holland_2010
    x_n = np.log(v_n / v_max_s) / np.log(r_max_norm * np.exp(1 - r_max_norm))
numpy._core._exceptions._ArrayMemoryError: Unable to allocate 2.02 MiB
                                     for an array with shape (264703,) and data type float64
```

**这不是数据或代码问题，是我自己的并发造成的**：当时同时跑了两个 C01（主探针 + 旧快照探针），每个都开 `ProcessPool(ncpus=4)` 且 `MAX_MEMORY_GB = 4.0`。机器 32,132 MB 物理内存，两者相加超过可用提交量，于是连 **2.02 MiB** 都分配不出。

因此 `run1` 只写出了 `haz_TC_hist.hdf5` 与 `tc_tracks_shanghai.pkl` 两个文件，`run2` 根本没启动 → **`run1` vs `run2` 的"逐位可复现"结论仍然欠奉**（但已由 §2.2 的 `oldnc` vs 权威比对替代回答，见 §5）。

**必须写入方案 §6 的运维约束**：
1. **同一时刻只允许一个 C01 在跑。** 机器 32 GB 内存，`01_hazard_tc.py` 的合成风场阶段（1188 轨道 × 14,616 中心点 × 4 worker）接近内存上限。
2. WP4/WP5 若要跑两条全链，**必须串行**，不能并行；且每次跑前确认没有残留 `python.exe`。
3. 崩溃后可能留下**孤儿 worker 进程**持续占 CPU，需在启动下一步前清理（本次即观察到 4 个 20:26:40 启动的进程在父进程已退出后仍在跑）。
4. 顺带：`_v8_logs\run_20261016_202621.jsonl` 记录了 `{"step_id":"C01","return_code":1,"elapsed_s":225.38}`，可作崩溃取证。

---

### 2.9 发现 v8 权威代码的潜在缺陷：`V8_PARAM_OVERRIDES` 无法重定向 HDF5 输出路径

旧快照重跑在合成风场与 ssp245 写出**都成功之后**，于 `01_hazard_tc.py:161` 崩溃：

```
20:34:57 [INFO] SSP2-4.5: intensity factor = 1.0324
Traceback (most recent call last):
  File "...\Climate\01_hazard_tc.py", line 161, in <module>
    logger.info(f"{ssp_label} saved: {hdf5_path.name}")
AttributeError: 'str' object has no attribute 'name'
```

**成因**：`V8_PARAM_OVERRIDES` 走 JSON，值只能是 `str`/数，而 `apply_sensitivity_overrides()` 直接 `globals()[key] = val`。于是 `config.HAZ_TC_SSP245_HDF5` 变成 `str`；第 160 行 `haz_ssp.write_hdf5(str(hdf5_path))` 因 `str()` 而正常，第 161 行的 `hdf5_path.name` 则要求 `Path`，故抛错。

**影响面（重要且有限）**：
- **不影响本方案**：WP4/WP5 只用 `V8_PARAM_OVERRIDES` 重定向**输入**路径（`ADMIN_BOUNDARY_SHP`、`IBTRACS_FILE`），这两处分别经 `gpd.read_file(...)` 与 `str(...)` 使用，字符串完全可用。
- **不影响 `run_sensitivity.py`**：`config\sensitivity_sweep.json` 的 10 个参数全是数值，不含路径键。
- **影响**：任何试图用 `V8_PARAM_OVERRIDES` 做**输出目录隔离**的人都会踩到（本次探针即是）。崩溃点在第 161 行，故 `haz_TC_ssp245.hdf5` 已写、`haz_TC_ssp585.hdf5` 与 `alpha_temp_series.csv` 未写 —— **失败是静默侧的**（前一步产物已落盘），容易误判为部分成功。

**处置建议（不修改权威代码，按方案 §11）**：在 `docs\` 与 README 中记为已知陷阱；若将来确需重定向输出，正确做法是**整目录复制代码**后在副本上改，而不是靠 `V8_PARAM_OVERRIDES` 改路径。

---

## 3. 对稿件的具体影响（路线 B 下）

除方案 §5 已列的边界相关改动外，还需**追加**：

| 位置 | 现值 | 需改为 | 依据 |
|---|---|---|---|
| P17 | `107 historical TC events` | 108 | §2.1 |
| P17 | `1,070`（合成实现） | 1,080 | §2.1 |
| P17 | `0.9999`（AAL pred/obs） | **需重新推导** | §2.6 |
| P4/P14/P79 等全部 EAL | 24.2 / 21.5% … | 再叠加 **−1.23% 频率效应**与新增风暴贡献 | §0 |
| 方法/Table B1 | 台风目录与年限描述 | 需写明 IBTrACS 快照版本与 1945–2026 跨度 | §2.2 |
| Table 8 | 敏感性行 | 因基准变化需整体重算 | — |
| 全部 CRI/HSI/CCHI | 现值 | 因 `risk_total` 变化而变 | — |

**注意**：这条路线下，"边界替换"与"台风目录变更"两件事的效果会**混叠**，方案 §1 的 A1/A2 验收标准（"差异 100% 归因于边界层"）**不再成立**。

---

## 4. 两条互斥路线

### 路线 A（✅ 作者已裁定）：钉住旧版 IBTrACS，恢复"单变量"实验

做法：在 WP4/WP5 的运行配置中固定
`IBTRACS_FILE = data\Hazard_data\WP台风数据\IBTrACS.WP.v04r01_old_202510.nc`
（并同时钉住 Knutson 因子 1.0324 / 1.0442，见 §2.4）。

| | |
|---|---|
| ✅ | 边界层重新成为**唯一**变量，A1/A2 归因重新成立 |
| ✅ | 稿件的 107 / 1,070 / 0.9999 及全部既有数字**仍然有效**，改动范围回到方案 §5 原样 |
| ✅ | 符合用户既定目标："复现已投稿结果，只改边界引起的数字/图/数据/描述" |
| ✅ | 科学上站得住：IBTrACS 是活数据集，Methods 明确写快照版本是**规范做法** |
| ⚠️ | 必须验证快照确实给出 107（探针进行中，见 §5） |
| ⚠️ | 快照是**唯一副本**，必须立即备份（见 §7） |

### 路线 B（❌ 作者已明确排除）：接受新版 IBTrACS（108 事件 / 1/82）

| | |
|---|---|
| ✅ | 使用"最新"官方数据 |
| ❌ | 稿件需为**两件**独立变更改数字，改动面显著扩大 |
| ❌ | `AAL pred/obs = 0.9999` 验证结论失效，需重算或删除 |
| ❌ | 边界效应的归因被污染，A1/A2 验收标准作废，方案 §7 的期望值全部要重估 |
| ❌ | WP6 的 10.5 小时敏感性重跑**需重做一次**（基准变了） |

---

## 5. 探针清单与运行状态

所有产物位于 `model_房地产风险_v8\_c01_probe\`：

| 文件 | 作用 |
|---|---|
| `run_probe.ps1` | 连跑 C01 ×2（现行 IBTrACS），输出到 `run1\` `run2\` |
| `run_probe_oldnc.ps1` | 用旧版快照跑 C01 ×1，输出到 `oldnc\` |
| `compare_values.py` | HDF5/CSV/pkl **数值**级比对（不依赖字节） |
| `check_boundary_override.py` | 边界层重定向验证（已完成，PASS） |
| `inspect_shipped_hazards.py` | 权威 vs 探针事件集合比对与溯源（已完成） |
| `output_manifest_BEFORE.csv` | `Climate\output` 822 文件的运行前清单，用于证明未干扰权威产物 |
| `sha_compare.csv` | 三次运行的 SHA256 对照表 |

**探针结果（已全部填齐）**：

| # | 问题 | 结论 | 证据 |
|---|---|---|---|
| 1 | `run1` vs `run2`：C01 是否**数值可复现**？ | ✅ **是（更强形式已验证）** —— `run2` 因 OOM 未跑成（§2.8），但改用**更强的检验**：用旧版输入重跑一次，与 2026-03-28 的权威产物逐值比对，**全部数值完全一致** | `value_compare.txt` + `verify_skipped.py` 输出 |
| 2 | 旧版快照是否**恰好重现 107 事件与相同事件集合**？ | ✅ **是** —— 107 事件 / 1,177 合成轨道 / 事件集合逐条相同 | §2.2 日志；`inspect_shipped_hazards.py` |

**第 1 项的完整证据（`_c01_probe\oldnc\` vs 权威产物）**：

| 文件 | 事件数 | 数值比对结果 |
|---|---|---|
| `haz_TC_hist.hdf5` | 107 vs 107 | `date`/`event_id`/`category`/`frequency`/`event_name`/`orig` **全部数值相同**；`intensity` 稀疏矩阵 **逐位相同**（nnz 715,417, max 55.5429）；`centroids` lat/lon **逐位相同**（14,616 点） |
| `haz_TC_synth.hdf5` | 1,177 vs 1,177 | 同上全部相同；`intensity` 逐位相同 |
| `haz_TC_ssp245.hdf5` | 1,177 vs 1,177 | 同上全部相同；`intensity` 逐位相同 |
| `tc_tracks_shanghai.pkl` | 107 vs 107 | `lat`/`lon`/`max_sustained_wind`/`central_pressure` **全部逐位相同** |
| `tc_tracks_all.pkl` | 1,177 vs 1,177 | 同上全部逐位相同 |

**唯一的差异全部是序列化层面的**（非数值）：
- `intensity_thres` 组：权威有、重跑无（climada 版本差异）
- `centroids` 的 pandas block 布局不同（pandas 版本差异）—— 已用 `Centroids.from_hdf5` 语义化比对绕开
- `date`/`event_id`/`category` 的整型位宽 `int32` vs `int64` —— 强制转型后数值相同

**由此得出的三条关键结论**：
1. **C01 是确定性的**：`ProcessPool` 的分块顺序稳定，`np.random.seed(42)` 生效，`H10` 风场逐位可复现。
2. **`ADMIN_BOUNDARY_SHP` 一旦是唯一变量，A1/A2 的归因就是干净的** —— 方案 §2.4 的前提**恢复成立**。
3. **WP4/WP5 可以做成两条独立全链**，**无需**启用 §2.3.1 的"共用 C01 产物"备用策略（该策略可放弃）。

**"逐位相同"不是合适的判据**：HDF5/pickle 会因库版本产生 schema 与整型位宽漂移。**一律用数值判据**（`compare_values.py` + `verify_skipped.py` 已实现）。

**残余缺口（低风险，由 WP4 复核）**：

| 缺口 | 原因 | 风险评估 |
|---|---|---|
| `alpha_temp_series.csv` 未产出 | 旧快照重跑在 L161 因 `str.name` bug（§2.9）中止于 Step 1.5 之前 | **低**：该步是纯确定性回归（读 528×2 个静态 GeoTIFF，无 RNG、无进程池、不依赖边界层）。权威日志已给出 `slope=0.066785 C/yr, alpha∈[0.9307,1.0744]` 作参照 |
| `haz_TC_ssp585.hdf5` 未产出 | 同上（写入 ssp245 后、写 ssp585 前中止） | **低**：机械变换 `intensity × 1.0442`，且 ssp245（×1.0324）已逐位验证通过 |

两者的最终确认放在 **WP4 的完整链**里，届时会走真实代码路径。

**结论：无需再跑任何探针。可以进入 WP0。**

---

## 6. 隔离性声明（**已用前后清单证明**）

本轮探针**没有改写任何权威产物**。做法与结果：
- 7 个 C01 叶子输出路径经 `V8_PARAM_OVERRIDES` 全部重定向到 `_c01_probe\`
- `LOGS_DIR` **刻意未重定向**，因为 `init_environment()` 会对目录常量调用 `.mkdir()`（传字符串会 `AttributeError`）。代价：`Climate\output\logs\` 新增时间戳日志文件，**纯增量、不覆盖**
- 运行前已存 `output_manifest_BEFORE.csv`，运行后存 `output_manifest_AFTER.csv` 并逐文件比对
- `TQDM_DISABLE=1` 仅影响进度条显示，不影响数值

**清单比对结果（`Climate\output` 全树）**：

| | |
|---|---|
| 运行前文件数 | 822 |
| 运行后文件数 | **824** |
| 新增 | **2 个**，均为时间戳日志：`logs\log_01_hazard_tc_20261016_202625.log`（1,416 B）、`logs\log_01_hazard_tc_20261016_202941.log`（1,930 B） |
| **修改** | **0 个** |
| **删除** | **0 个** |

即：除两个新增日志外，**822 个既有文件的长度与 mtime 全部未变**。

**另外**：`_v8_logs\` 新增两个 `run_20261016_*.jsonl`（`run_v8.py` 的标准行为，纯增量）。

---

## 7. 风险：旧版输入是唯一副本

上级工程 `复现公报台风研究结果\data\Hazard_data\WP台风数据\IBTrACS.WP.v04r01.nc`（`preprocess_copy_typhoon.py` 的 `SRC_DIR`）**已不存在**。`_old_202510.nc` 是目前**唯一**能重现 107 事件输入的副本。

**必须在 WP0 立即**：
1. 把 `_old_202510.nc` 复制到 NEWROOT 的 `data\` 内并纳入 `SHA256SUMS`
2. 在 `docs\` 记录其 SHA256 与出处
3. ~~备份到至少一个 `D:` 之外的介质~~ → **作者已裁定无需（2026-10-16）**，同盘副本即为接受的风险处置

**已完成（2026-10-16 预检期间）**：已在同盘建立安全副本，防止原文件被误删/被官方更新器覆盖：

| | |
|---|---|
| 副本路径 | `V8ROOT\_c01_probe\_CRITICAL_BACKUP\IBTrACS.WP.v04r01_old_202510.nc` |
| 字节数 | 8,904,634（与原文件一致） |
| SHA256 | `DA05013357E6ADFC11DAE72C5830BED602A6C2AAFC3F3C228653850BA8DEF91D`（**已复核一致**） |
| 校验记录 | 同目录 `SHA256.txt` |

⚠️ 该副本与原文件**同盘**，只能防误删、不能防磁盘故障。
**该剩余风险已经作者裁定接受（2026-10-16）：无需异地备份，本项关闭。** 本报告其余结论不受影响。

---

## 8. 建议（已按此执行并验证完毕）

1. ~~先确认 §5 的两个待填结果，再决定 A/B~~ → **已完成**：`oldnc` 重现 107 事件且**全部数值与权威产物一致** → ✅ **作者已裁定走路线 A（2026-10-16）**；路线 B 已排除。
2. **必须**把两个 Knutson 因子（1.0324 / 1.0442）显式钉住，否则 SSP 情景不可复现（联网实测值 ≠ config 兜底 1.05 / 1.10）。
3. ~~立即异地备份~~ → ✅ **作者已裁定无需异地备份（2026-10-16）**，本项关闭。仍须把 `_old_202510.nc` 复制进 NEWROOT 并纳入 `SHA256SUMS`。
4. 已把本条发现并入 `_执行方案_…_v1.md` 的 §2.3.1（实测更新块）、§2.11（裁定表）、§4 WP4（前置条件）、§6（两条新失败模式）、§9（作者决策第 9/10 条）、§10（假设 5 已证伪并修正）、§12（冷启动第 0 步）。
5. **WP4/WP5 两条全链可独立进行**（§5 结论 3），**必须串行**（§2.8 OOM 约束）。
6. **不要再跑 C01 探针** —— 问题已全部回答。下一步直接进 WP0。

---

## 9. 本次预检对方案的净影响

| 方面 | 变化 |
|---|---|
| 变更变量数 | 从"边界层"**1 个**（方案原假设）→ 实际有 **2 个**（边界层 + IBTrACS），**已通过钉住输入还原为 1 个** |
| 归因可信度 | **恢复成立**：C01 逐值可复现 → A1/A2 差异 100% 来自边界层 |
| WP4/WP5 编排 | **可独立全链**，不必共用 C01 产物；但**必须串行** |
| WP4 新增前置 | 钉 `IBTRACS_FILE` + 钉 Knutson 因子 + 确认快照已备份 |
| 新增失败模式 | 并发 C01 → OOM；IBTrACS 被静默更新；Knutson 静默回退 |
| 新增已知陷阱 | `V8_PARAM_OVERRIDES` 不能重定向 HDF5 输出路径（§2.9） |
| 工期影响 | **无**（路线 A 下 WP1–WP10 与 §8 时间预算不变） |
| 稿件影响 | **无**（路线 A 下仍只改边界相关数字，方案 §5 文件清单不变） |
