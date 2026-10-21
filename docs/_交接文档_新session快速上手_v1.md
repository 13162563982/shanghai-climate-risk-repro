# 交接文档 · 新 session 快速上手（v1）

> **本文件的作用**：让一个**零上下文**的新 session 在 10 分钟内开始施工。
> 它是一份**路由 + 易失事实清单**，**不是**方案的替代品。详细施工要求以
> `_执行方案_官方边界重跑与稿件更新_v1.md` 为准，2026-10-16 实测修正以
> `_预检报告_C01复现性与IBTrACS输入变更_v1.md` 为准。
>
> **生成时间**：2026-10-16　**生成者**：上一 session（完成全部预检，**未执行任何 WP**）

---

## 0. 30 秒上手

**任务**：在 `NEWROOT` 里建成一个**自包含、可搬家、可冷启动复现**的投稿工作包，四项交付：
① 归类清晰的 v8 建模代码　② 用**官方行政边界层**重跑的最新输出　③ 一份可投稿稿件
④ 完整原始输入数据。稿件以 `PAPER_MANUSCRIPT_FINAL.docx` 为底稿，**只换数字、图件与相关文字**。

**当前进度**：预检全部完成，**WP0 尚未开始**。V8ROOT 与稿件**均未被改动**。

**你的第一个动作**：执行 **WP0**（`SHA256SUMS_before.csv` + 整目录快照 + 冻结 docx）。
WP0 **只新增、不改写任何既有文件** → 风险纯增量，**可无条件立刻做，不必等任何前端决策**。
**真正的写操作从 WP1 开始**（往 NEWROOT 复制/改代码），WP5 起的全链重跑才会覆盖 `output\`。

---

## 1. 必读顺序（严格按序，读完即可开工）

| 序 | 文件（相对 NEWROOT） | 用途 | 读完的判据 |
|---|---|---|---|
| 0 | `docs\_预检报告_C01复现性与IBTrACS输入变更_v1.md` | **先读这个**。它推翻了方案的原始假设并给出修正 | 你知道**必须钉住台风输入**，否则 WP4 必失败 |
| 1 | `docs\_执行方案_官方边界重跑与稿件更新_v1.md` §1 | 目标与 A1–A8 验收标准 | 能复述 8 条验收 |
| 2 | 同上 §2 | 事实基线（路径/环境/流水线/边界链/冻结参考值/稿件结构/图件链/灵敏度） | **不必再自行调研任何环境问题** |
| 3 | 同上 §4（WP0–WP10）与 §6 | 阶段、闸门、失败模式 | 知道每个 WP 的闸门是什么 |
| 4 | 同上 §12 | 冷启动启动包（含已实测的环境自检命令） | 能跑通环境自检 |
| 5 | 同上 §5、§7、§8、§9、§10、§11 | 文件级变更清单、预期值、时间预算、待决事项、假设、禁区 | 知道**不该做什么** |

> ⚠️ 方案 §2.3.1 开头有一个 **⛔ 实测更新块**，它**优先于**该节后续的静态分析。
> 方案 §10 假设 5 已被**证伪并修正**，不要按旧文理解。

**既有证据文件**（需要追溯时再看，不必通读）：
- `V8ROOT\_边界替换回归报告.md` —— 边界替换的实际偏移（**下界**）
- `V8ROOT\期刊投稿\Nature-JF投稿\Nature Cities\提交审稿人\_边界几何裁决报告.md`
- `V8ROOT\期刊投稿\Nature-JF投稿\Nature Cities\提交审稿人\_figure_relabel\修改报告_v9_图内改名.md` —— **33 处改名映射（FRI→HSI / CFCI→CCHI），权威**
- `V8ROOT\_v8_logs\run_20261016_*.jsonl` —— 证明上一次只跑了 C03–C06
- `V8ROOT\_c01_probe\` —— 2026-10-16 预检的全部脚本与产物
- `V8ROOT\data\Hazard_data\WP台风数据\preprocess_copy_typhoon.log` —— 台风输入溯源关键证据

---

## 2. 硬事实基线（**直接采用，不要重新调研**）

### 2.1 路径

| 项 | 绝对路径 |
|---|---|
| **V8ROOT**（权威代码与数据，**只读**） | `D:\桌面real\陈剑老师研究工作\Shanghai_Climate_Risk_Analysis\复现公报台风研究结果\model_房地产风险_v8\` |
| **NEWROOT**（本次交付目标） | `…\model_房地产风险_v8\期刊投稿\Nature-JF投稿\Nature npj Natural Hazards\` |
| 权威 python | `C:\Users\Jack\miniforge3\envs\climada_env\python.exe` |
| 雪花输入快照（**关键**） | `V8ROOT\data\Hazard_data\WP台风数据\IBTrACS.WP.v04r01_old_202510.nc` |

> `…\model_房地产风险_v8\期刊投稿\Nature-JF投稿\Nature Cities\提交审稿人\` 是**上一轮**的工作目录，
> 只作为证据来源读取，**不是**本次的施工目标。

### 2.2 环境（唯一可用，已实测）

- conda env：`C:\Users\Jack\miniforge3\envs\climada_env`（Python 3.11.13，232 包）
- **`C:\Users\Jack\anaconda3\envs\climada` 是废的**（无 climada、无 geopandas），**不要用**
- 关键包：climada 6.1.0、GDAL 3.10.3、geopandas 1.1.3、rasterio 1.4.4、shapely 2.1.2、pandas 2.3.3、numpy 2.3.5
- 机器：**32 GB 内存**（可用约 13 GB）、24 逻辑核、`D:` 盘可用约 **347 GB**
- **PowerShell 是 5.1，不是 7**

### 2.3 流水线（11 步，顺序固定）

```
C01 → C03 → C02 → C04 → C05 → C06 → C07 → F01 → F02 → F03 → X01
```

- 入口：`run_v8.py`，支持 `--only <ID>` / `--from` / `--to` / `--strict-compare`
- `run_v8.py` 用 `env=None`，即**继承父进程环境** → 必须先在 shell 里设好环境变量
- 灵敏度入口：`run_sensitivity.py` + `config\sensitivity_sweep.json`（10 个参数，全量重跑 ≈ **10.5 h**）

**实测耗时**（干净环境下）：

| 步 | 时长 | 步 | 时长 |
|---|---|---|---|
| C01 | ~285 s | C07 | 6 s |
| C03 | 30 s | F01 | 223 s |
| C02 | 2.5–4 min | F02 | 1 s |
| C04 | 5–15 s | F03 | 2 s |
| C05 | 240–257 s | X01 | 1.7 s |
| C06 | 568–685 s | **全链** | **约 25–30 min** |

### 2.4 无关但要知道的数

- 建筑 585,033 栋；CNY 63.327 万亿；16 个区；107 个历史台风事件（**见 §3 约束 1**）；seed 42
- `data\` = **15,286 文件 / 14.236 GB**
- 稿件：409 段、11 表、37 内嵌图、**131 个 `m:oMath` + 41 个 `m:oMathPara`**

---

## 3. 六条硬约束（**违反会静默出错**）

### 约束 1 · 必须钉住台风输入，否则 WP4 必然失败

现行 `IBTrACS.WP.v04r01.nc` 已于 **2026-07-25 被原地更新**，会给出 **108** 事件、频率 **1/82**，
而稿件口径是 **107** 事件、**1/81**。频率口径差异会让**所有**事件频率整体 **−1.23%**。

**WP4/WP5 必须覆盖 `IBTRACS_FILE`** 指向：

```
V8ROOT\data\Hazard_data\WP台风数据\IBTrACS.WP.v04r01_old_202510.nc
  (8,904,634 B, SHA256 DA05013357E6ADFC11DAE72C5830BED602A6C2AAFC3F3C228653850BA8DEF91D)
```

已实测：用该快照重跑 C01，**全部数值与 2026-03-28 权威产物逐位一致**。

> **这是唯一副本**（上级工程原始出处已删）。已在 `V8ROOT\_c01_probe\_CRITICAL_BACKUP\` 建同盘副本。
> **异地备份经作者裁定无需**（2026-10-16，本项已关闭）—— 同盘副本即为接受的风险处置，**不要再追问作者**。
> WP0 仍必须把该快照复制进 NEWROOT 并纳入 `SHA256SUMS`。

### 约束 2 · 必须钉住 Knutson 强度因子

权威实测值 **`SSP2-4.5 = 1.0324`、`SSP5-8.5 = 1.0442`**，而 `00_config.py` 兜底是 **1.05 / 1.10**。
`01_hazard_tc.py:137-147` 是"先联网取，`except` 静默回退"→ **联网与断网结果不同**。
不钉住则 A8（断网可复现）不成立。每次跑完**核对日志里的 `intensity factor` 两行**。

### 约束 3 · 同一时刻只允许一个 C01

本机 32 GB 内存，每个 C01 有 4 个 `pathos` worker + `MAX_MEMORY_GB=4.0`。
**并发两个 C01 会 OOM**（预检 `run1` 即因此崩在 `Unable to allocate 2.02 MiB`）。
WP4/WP5 两条全链**必须串行**，启动前清理残留 `python.exe`。

### 约束 4 · 判据一律用数值，不用字节

HDF5 / parquet / pickle 会因库版本产生 schema 与整型位宽漂移（已实测：`intensity_thres` 组有无、
pandas block 布局、`int32` vs `int64`）。**字节不同不等于数值不同**。
预检已写好两个可复用脚本：`V8ROOT\_c01_probe\compare_values.py`、`verify_skipped.py`。

### 约束 5 · docx 只能做 run 级定向替换

稿件含 **131 个 `m:oMath` + 41 个 `m:oMathPara`**，`paragraph.text` **会丢掉公式**。
**禁止整段 `.text` 赋值**；用 run 级替换。改完必须验 `m:oMath` 计数仍为 131、zip 完整、图片可解。

### 约束 6 · 不修改 V8ROOT

方案 §11 明确：`V8ROOT` 只读 + 快照。所有改动发生在 **NEWROOT**。
（例外：预检已新增 2 个日志文件与 2 个 `_v8_logs\*.jsonl`，均纯增量、已被清单证明未覆盖任何文件。）

---

## 4. 当前状态（**忠实记录，避免重复劳动**）

| 项 | 状态 |
|---|---|
| WP0–WP10 | **全部未开始** |
| V8ROOT 代码 / 输出 / 稿件 | **未被改动**（`Climate\output` 822 → 824 文件，新增 2 个日志，**修改 0、删除 0**） |
| 稿件 docx | 完好，SHA `39240D38FCF71ADB72BEA285249AFE5757E0327F26253D48BE45FA899C772F14` |
| 官方边界层 | 完好，SHA `d2eb3fc013591050be1d45b0f834a8fcd1e12c0ec804da52f4be4f8624772932` |
| 边界重定向机制 | **已实测 PASS**（16 区 / 780 顶点 / 7,205.07 km² / 两两重叠 0） |
| C01 确定性 | **已验证**：钉住输入后逐位可复现 → **无需**启用"共用 C01 产物"备用策略 |
| 台风输入 | 已发现被更新，已定位唯一副本并备份 |
| NEWROOT 现有内容 | 仅 `PAPER_MANUSCRIPT_FINAL.docx` + `docs\` 三份 md |

> `V8ROOT\_c01_probe\` 是**预检证据，请保留**（**174.5 MB / 20 文件**，其中 `_CRITICAL_BACKUP\` 占 8.5 MB），不要删。

---

## 5. 启动动作（精确命令）

### 5.1 环境自检（**先跑，必过**）

> WP3 之前 `env\run.ps1` **还不存在**，所以现在用下面这段**直连命令**（已实测通过）。

```powershell
$e = 'C:\Users\Jack\miniforge3\envs\climada_env'
$env:CONDA_PREFIX = $e
$keep = ($env:PATH -split ';' | Where-Object { $_ -notmatch 'anaconda3' })
$env:PATH = "$e\Library\bin;$e\Library\usr\bin;$e\Library\mingw-w64\bin;$e;$e\Scripts;" + ($keep -join ';')
$env:GDAL_DATA = "$e\Library\share\gdal"
$env:PROJ_DATA = "$e\Library\share\proj"
$env:PROJ_LIB  = "$e\Library\share\proj"
$env:PYTHONIOENCODING = 'utf-8'
& "$e\python.exe" -c "import sys,climada,geopandas,rasterio; from rasterio.crs import CRS; print(sys.version); print(CRS.from_epsg(32651)); print('OK')"
```

**预期**：`3.11.13 …` / `EPSG:32651` / `OK`

**失败对照**：
- `CPLE_AppDefinedError … LAYOUT.VERSION.MINOR = 5` → `CONDA_PREFIX` 未生效（方案 §2.2 坑 1）
- `ssl.SSLError: [ASN1: NOT_ENOUGH_DATA]` → 间歇性，加 `$env:PYTHONPATH = "$V8ROOT\_env_patch"` 走 SSL 补丁（方案 §2.2 坑 3）

### 5.2 然后按方案 §12 从 WP0 开始

每过一个闸门，在 `NEWROOT\docs\_执行日志.md` **追加一行**：时间 / WP / 闸门 / 结论 / 证据文件。

---

## 6. WP0–WP10 速查 + 闸门

| WP | 做什么 | 闸门 | 关键提醒 |
|---|---|---|---|
| **WP0** | 记录 `SHA256SUMS_before.csv`（**必须含 `data\Hazard_data\WP台风数据\`，尤其 `_old_202510.nc`**）；**整目录**快照 `Climate\output`、`Finance\output`、`Composite\output`、`_sensitivity_results` → `V8ROOT\_snapshot_before_<ts>\`；冻结 docx 到 `NEWROOT\manuscript\_frozen\` | **G0** 快照文件数一致；docx SHA = `39240D38…`；`_old_202510.nc` SHA = `DA050133…` | **只新增、不改写既有文件**；**必须整目录快照**（旧教训：按需挑文件导致 27/822 被覆盖） |
| **WP1** | 代码归集到 NEWROOT；`00_config.py` **仅改 4 处**；改 v7→v8 注释；`tools\` 归集 | **G1** 全树 `*.py` 可 `ast.parse`；流水线脚本 grep `[A-Za-z]:[\\/]` 零命中 | 不收 `_regression_test.py` / `_v8_baseline_manifest.json`（**已证实失效**） |
| **WP2** | 全量复制 `data\`（14.24 GB） | **G2** 文件数/字节一致（15,286 / 14.236 GB）；官方层 SHA = `d2eb3fc0…` | 含 10.68 GB 逐日气温与 1.63 GB ETOPO（已裁定全量） |
| **WP3** | `env\`：`run.ps1`（唯一入口）、`bootstrap.py`、`sitecustomize.py`、`requirements_frozen.txt`、`ENV.md` | G3 入口可跑通 | `run_sensitivity.py:60-65` 与 `_test_integration.py:5-18` 里有**硬编码环境路径**，一并改造 |
| **WP4** | **先钉输入**（§3 约束 1、2）→ 用**乡镇旧层**跑完 11 步 | **G4 (=A1)** §2.6 全部冻结参考值四舍五入后一致 | **不通过就停止排查，不得继续**；先用小步验证（只跑 C01 数事件数） |
| **WP5** | 切**官方层**跑完 11 步 + 出 41 张图 | G5 (=A2/A4) OLD→NEW 差异表完整 | 6 张改名图必须**由生成脚本产出新标签**，不是像素手术 |
| **WP6** | 灵敏度 10 参数全量重跑 | G6 (=A7) Table 8 由新基线重算 | **约 10.5 h，必须做托管后台作业**；`run_sensitivity.py` 会在扫描间**恢复基线并覆盖主输出** → 跑完必须重跑主链并比对 |
| **WP7** | 稿件改写（数字/图/表/文字） | G7 (=A5/A6) 数值零残留；`m:oMath` 仍 131 | 见约束 5 |
| **WP8** | DA 声明与投稿要件 | G8 | **被 §9 待决事项阻塞**（需作者输入） |
| **WP9** | 路径无关验证（`subst` 换盘符跑 C03+C04） | G9 (=A3) 输出与 A2 一致 | — |
| **WP10** | 终检交付 | G10 | — |

**总工期约 17–20 h**（含 WP6 过夜）。**不要在 session 里前置等待 WP6。**

---

## 7. 坑表（症状 → 处置）

| 症状 | 真正原因 | 处置 |
|---|---|---|
| `Unable to allocate N MiB`（N 很小也算） | 并发 C01 / 内存耗尽 | 只跑一个 C01；清理残留 `python.exe` |
| C01 日志出现 108 事件、频率 1/81→1/82 | `IBTRACS_FILE` 没钉住 | 见约束 1 |
| 日志出现 `Knutson fallback to config`，或因子 = 1.0500/1.1000 | 联网失败静默回退 | 钉住因子，见约束 2 |
| `AttributeError: 'str' object has no attribute 'name'` @ `01_hazard_tc.py:161` | 用 `V8_PARAM_OVERRIDES` 重定向了 **HDF5 输出路径** | **不要**用覆盖机制改输出路径；只改**输入**路径。若必须隔离输出，整目录复制代码后在副本上改 |
| `KeyError: '市'` / `'县'` | 官方层 schema 不匹配 | 跑 `build_admin_boundary.py` 重建 |
| 建筑数 < 585,033 | 5 km 最近邻兜底失效 | **停止并上报** |
| `rasterio.errors.CRSError` / `LAYOUT.VERSION.MINOR` | `CONDA_PREFIX` 缺失 | 见 §5.1 失败对照 |
| docx 公式丢失 | 整段 `.text` 赋值 | 回滚到 `_frozen\`，改 run 级替换 |
| `_regression_test.py` 报 FAIL | **已知失效**，不纳入判据 | 用新建的 `tools\freeze_baseline.py` |
| parquet/HDF5 字节不同但标量相同 | 序列化漂移 | 判据用数值（约束 4） |

### 会话层面的坑（上一 session 踩过，省你时间）

1. **PowerShell 是 5.1**。`.ps1` **文件内容**里的非 ASCII（含中文路径）会被按 ANSI 读成乱码；
   `-Command` 里的中文没问题。对策：`.ps1` 保持**纯 ASCII**，CJK 路径用 `$PSScriptRoot` 推导，
   或用码点拼（例：`'WP' + (([char]0x53F0,[char]0x98CE,[char]0x6570,[char]0x636E) -join '')` 得 `WP台风数据`）。
2. **控制台中文乱码** → 设 `$env:PYTHONIOENCODING='utf-8'`。
3. **`(Get-Content $f).Count` 行数不可靠**（本机实测偏小）。要真实行数用
   `([System.IO.File]::ReadAllText($f) -split "``n").Count`。
4. **`pwsh -Command` 会吞双引号** → 用双单引号或 `@' … '@` here-string。
5. **`run_v8.py` 继承父环境**：必须先在 shell 里设好 `CONDA_PREFIX` 等，否则 C03 会在 LandScan 处崩。
6. 长输出（climada 的 `cyclostrophic` 警告会刷 ~80 KB）→ 用
   `2>&1 | Where-Object { $_ -notmatch 'cyclostrophic' }` 过滤。

---

## 8. 已裁定事项（**不要重新讨论**）

| 事项 | 裁定 |
|---|---|
| 边界层 | **采用官方层**（天地图 GS(2024)0650，经 `build_admin_boundary.py` 加工）；旧乡镇层仅用于 A1 基线与留档 |
| **台风输入口径** | ✅ **作者已确认（2026-10-16）路线 A：钉住旧版快照**（复现 107 事件稿口径，使边界层成为唯一变量）；路线 B 已排除。异地备份裁定无需 |
| Knutson 因子 | 钉住 **1.0324 / 1.0442** |
| 数据复制范围 | **全量 14.24 GB** |
| 房价小区数据来源 | 改写为**安居客（Anjuke）**，并说明文件夹名沿用旧标签（实为安居客，**不是链家/贝壳**） |
| 灵敏度扫描 | **全量重跑 10 参数（≈10.5 h）** |
| α(T) 温度源 | 保留 v8 单源 ½(Tmin+Tmax)，写档说明 v6 遗留（差 0.62 °C） |
| CRI heat 分量 | 保留 **Tmax** 与 28 °C 基温（改 Tmean 会使该分量近乎归零） |
| 边界偏移 | **先报告实际变动，不评估更高精度** |
| C01 并发 | **串行** |

---

## 9. 待作者确认（**只阻塞 WP8，不阻塞 WP0–WP7**）

**台风输入口径与备份两项已由作者裁定完毕（2026-10-16），不要再追问：**

| 事项 | 裁定 |
|---|---|
| 台风输入口径 | ✅ **路线 A**：钉住 `_old_202510.nc`，**107 事件口径**。**路线 B 已明确排除** |
| `_old_202510.nc` 异地备份 | ✅ **无需**；同盘副本即为接受的风险处置，本项关闭 |

**其余待作者提供**（方案 §9 第 1–8 条）：目标期刊（文件夹写 `Nature Cities` vs 投稿信 `npjNaturalHazards`）、
Zenodo DOI、代码仓库 URL 与 release/tag、房价数据访问措辞、585,033 建筑清单公开性、
6,341 km² 处理、`P205` DA 标题错位、历史 FAIL 报告归档。

这些**只阻塞 WP8 定稿**；WP0–WP7 可全程推进，遇到时先按方案 §7 的推荐值做、并留占位符。

---

## 10. 汇报规范

- 每过一个闸门 → `docs\_执行日志.md` 追加一行（时间 / WP / 闸门 / 结论 / 证据文件）
- 闸门不过 → **停止**，写清失败证据，**向作者报告，不擅自降级判据**
- 报告数字时**必须给出处**（哪个脚本、哪个 CSV、哪个日志行）
- 声称"已完成"前，先跑一次验证命令并贴出输出

---

## 11. 结论：可以立刻开工

预检已把**唯一的结构性不确定点**（C01 是否可复现、输入是否被改）彻底消掉，
并已把结论写进方案与预检报告。**不需要再跑任何前置探针。**

> 新 session 的第一条指令建议：
> 「读 `docs\_交接文档_新session快速上手_v1.md`，然后按方案 §12 从 **WP0** 开始施工，
> 每个闸门写 `docs\_执行日志.md`。」

---

## 附：本交接文档引用的文件与校验方式

| 文件 | 磁盘字节 | 行数 | SHA256 |
|---|---|---|---|
| `docs\_交接文档_新session快速上手_v1.md`（本文件） | 见清单 | 见清单 | 见清单 |
| `docs\_执行方案_官方边界重跑与稿件更新_v1.md` | 61,649 | 848 | `E8EACF31293969190BA5A9CC62DF6C601BA89B86D858583623FD5A9E0F5A7F56` |
| `docs\_预检报告_C01复现性与IBTrACS输入变更_v1.md` | 26,110 | 434 | `648C1F2B77E87A9858EBB82150E651265FEC4CFE47E285D502AA310E8B675170` |
| `PAPER_MANUSCRIPT_FINAL.docx` | 28,933,946 | — | `39240D38FCF71ADB72BEA285249AFE5757E0327F26253D48BE45FA899C772F14` |

> **为什么本文件自己不写哈希**：文件无法包含自身的最终哈希（自引用必然失效）。
> 四份文件的哈希统一记录在同目录的 **`_校验清单_SHA256SUMS.txt`**，用下面一条命令即可核对全部：

```powershell
$root = 'D:\桌面real\陈剑老师研究工作\Shanghai_Climate_Risk_Analysis\复现公报台风研究结果\model_房地产风险_v8\期刊投稿\Nature-JF投稿\Nature npj Natural Hazards'
Get-Content "$root\docs\_校验清单_SHA256SUMS.txt" | ForEach-Object {
    $h, $f = $_ -split '  ', 2
    $now = (Get-FileHash (Join-Path $root $f) -Algorithm SHA256).Hash
    '{0}  {1}' -f $(if ($now -eq $h) { 'OK  ' } else { 'FAIL' }), $f
}
```

清单里的路径**相对于 NEWROOT**（故搬家后仍可用）。

**若出现 FAIL**：说明该文件在交接后被修改过。方案与预检报告的结论应以**清单里的原始版本**为准；
若新 session 有意修改，请在 `docs\_执行日志.md` 记录原因。
