# Shanghai real-estate climate-risk model — reproduction package

Code, verbatim input data, frozen outputs and per-dataset provenance for the
study *"Compound climate risk of Shanghai's real-estate assets under
defence-gap and temperature-elasticity scenarios"* (submitted to
*npj Natural Hazards*).

The model couples a tropical-cyclone wind hazard (IBTrACS + CLIMADA), a
storm-surge hazard (ETOPO bathymetry + FABDEM onshore terrain + the municipal
shoreline), a building-level exposure layer, vulnerability functions with a
temperature-elasticity factor, a defence-gap sensitivity analysis, and a
finance-side climate-CVaR / risk-index layer.

| I want to… | go to |
|---|---|
| reproduce the paper end to end (≈26 min) | [`REPRODUCE.md`](REPRODUCE.md) |
| know where every dataset came from | [`DATA_SOURCES.md`](DATA_SOURCES.md) · [`provenance/`](provenance/) |
| get the eight files GitHub will not accept as git objects (18 assets incl. shapefile companions) | [`RELEASE_ASSETS.md`](RELEASE_ASSETS.md) · `fetch_release_assets.ps1` |
| verify that nothing has been altered | [`SHA256SUMS.txt`](SHA256SUMS.txt) · [`manifest.json`](manifest.json) |
| see the model code | `Climate/`, `Finance/`, `Composite/`, `run_v8.py` |
| see the reported numbers | `Climate/output/results/`, `Finance/output/results/`, `Composite/output/results/` |

**Nothing here was clipped, resampled or regenerated for publication.** Every
copied file is byte-identical to the one the published results were computed
from, and `sha256sum -c SHA256SUMS.txt` proves it.

---

> 以下为作者工作包的原始说明（原样保留，供追溯建模过程）。
> The authors' original working-package notes follow unchanged.

# Nature npj Natural Hazards · 自包含复现与投稿工作包

> **这是什么**：一个**自包含、可搬家、可冷启动复现**的投稿工作包。
> 目标期刊：*npj Natural Hazards*（投稿信为 `Cover_Letter_npjNaturalHazards_*`）。
> 底稿：`manuscript\PAPER_MANUSCRIPT_FINAL.docx`（冻结，只读）。
>
> **权威来源**：本包的全部代码与数据自 `model_房地产风险_v8\`（下称 **V8ROOT**）归集而来。
> V8ROOT **只读、未被改动**（唯一例外是 WP0 新增的 `_snapshot_before_<ts>\` 安全网目录）。
>
> **当前状态**：**WP0–WP5 全部完成（WP5 = A 版，即终稿口径）**。G0–G4 全部 **PASS**
> （G4 = 旧层基线 60/60 逐位一致）。潮损 −13% 复核完成，定性为**边界层制图概化导致的几何伪影**
> （官方层导出岸线仅 **96.2 km** vs 真实 **347.9 km**）。
>
> **选项 A（解耦岸线来源）已实施、已重跑、已验证、已归档**：官方层继续管归属/面积/底图，
> **仅岸线**改用细层 → `building_coast_distance_m.npy` 与旧层基线**逐字节相同**，
> 城市潮损 EAL 5.3930 → **6.2631 bn（+0.26%）**，城市复合 EAL 残余偏移收敛到 **0.2099%**，
> 对照从第三档升为**第二档**（采用官方层 + 逐项更新受影响数字）。
> A 版结果归档于 `output_archive\boundary_official_A_20261016_230820\`。
>
> 👉 **恢复施工请读 `docs\_继续施工_断点记录_v1.md`（**v7**，断点恢复的唯一入口）**。
>
> **进度**：**WP0–WP14 全部完成**。稿件仍是 **`manuscript\PAPER_MANUSCRIPT_v14.docx`**
> （28,192,778 B / SHA `C34F42F875FD341D…`，= v13 − 2 段：数据/代码可用性声明已移出稿件）。
> **WP14 重写了两个独立声明文件（v15），稿件未动**：
> `manuscript\Data_Availability_Statement.docx`（38,540 B / 14 段）、
> `Code_Availability_Statement.docx`（37,005 B / 6 段），二者**由 `docs\_数据溯源台账.csv` 渲染**，不再手写。
> **G14 14/14 PASS**（覆盖 100% / 标识 12 个全核实 / 台账↔声明双向 / 未用数据不入声明 / 稿件不变 /
> v15 数字台账 1,520/1,520）；G13 29/29（⚠ 必须用 `env\run.ps1` 跑）、G12 14/14、G7(v11) 14/14。
>
> **WP14 数据溯源（2026-10-18）**：`data\` **15,286 文件 / 15,285,545,582 B 100% 归属**到 **28 个逻辑数据集**；
> 等级 强 15 / 中 6 / 弱 5 / 无 2；**16 个进入运行、2 个仅出图、6 个完全不参与运行**。
> 关键结论：**没有「在用却完全没来源」的数据**；最弱三类（岸线层 / 房价面板 / 小区挂牌）已在声明里承认不确定性且不转存；
> 整包 14.236 GB 中 **10.9 GB（D08 全国逐日气温母产品）从不被读取**，不应上传。
> 台账：`docs\_数据溯源台账.csv/.md`；总表 `docs\数据溯源与可用性声明.xlsx`（7 表）；报告 `docs\_执行日志.md` §23。
> **待作者**：`docs\_DA_填写值.json`（Zenodo DOI、GitHub URL+tag）+ `docs\_待决事项.md` §E 的 A8–A16。
>
> - **WP13 全量数字核对（2026-10-18）**：**1,486 个数字 = 1,476（v14 稿件内）+ 10（旧声明文件）**，全部逐条核到权威源 → 数字层 0 错。WP14 后重算为 **1,520 = 1,476 稿件 + 44 声明（v15）**，仍 100%。

>
> - **WP6 灵敏度全量重跑已完成**（2026-10-17 00:52→21:54，**≈21 h**）：
>   `17 sweep / 85 取值`、主链 **11/11 步 rc=0**、基线复位 `RESULT: READY`、
>   归档 `output_archive\wp6_sensitivity_20261017_215456\`、41 图重出。
> - **WP7.1 数值提取器已完成**：`docs\_数字变更对照表.md` 共 **126 个位置**
>   （**75 CHANGE / 44 same / 7 watch**），Table 8 的 17 行已由 WP6 填充、**无 pending**。
> - **Table 8 重算**：`docs\_Table8_WP6重算.md` —— 17 个参数行里 baseline 改 3 行、
>   range 改 10 行、max-dev 只有 4 行是真实数值变化。**不要机械重写 max-dev 列**
>   （边界切换只让 CRI 动 ~0.3%，大部分是排版差异）。
> - 作者已裁定：Table 8 的 `Volatility window` 与 `CFCI target ρ` 两格**按重算值改**；
>   `V_HALF_ADJ_C` **保留稿件 `0%`**。已固化进 `tools\extract_manuscript_numbers.py`
>   的 `AUTHOR_RULINGS` / `AUTHOR_KEEP`。
> - **WP7.2–7.5 改稿已完成**（2026-10-17 22:13→23:43）：82 条编辑全部落地
>   （`docs\_v10_edit_plan.csv`），37 张图按槽位重排并刷新为 A 基线渲染
>   （`docs\_图件替换报告.md`）。期间修好一个**底稿级缺陷**：
>   **Figure 24–38 的图片原本整体错位一格**（第 k 格装第 k+1 图的图），
>   连带的显示框宽高比与替代文本图号一并修正。另按作者批准把
>   `Data Availability Statement` 标题下移归位（原先与正文被 15 个图块隔开）。
>   5 处偏离对照表的裁决见 `docs\_WP7.2执行勘误.md`。
> - **WP9 路径无关性（A3）已完成**：重跑 C03–C04 后 4 个产物**逐字节复现**、
>   基线 `RESULT: READY`；但 `Path(__file__).resolve()` 会把 `subst X:` 规范化回真实路径，
>   该测试不具区分力 —— 真正的依据是"流水线内零硬编码绝对路径 + 从不触网"。
>   整包搬家演练（复制 14 GB 后重跑）留到 WP10 前。
> - **投稿 PDF 请用 Word 另存**：`PAPER_MANUSCRIPT_v11.pdf` / `_v10.pdf` 均为 LibreOffice 预览，
>   该渲染把本文档版面按 1.5× 排版（冻结底稿同样如此），不可作投稿版。
> - **WP8 投稿要件已完成（非阻塞部分）**：
>   ① `docs\_数据可公开性分级清单.md` —— 16 个外部数据集 A/B/C 分档 + 4 组自产（**20 行**），
>   含官方边界层「可引可绘、矢量件不转存」的判定；
>   ② `docs\_DA声明_v10待补.md` + `tools\patch_da_statement.py` —— DA 改写稿已备料、执行器已 dry-run 验证
>   （**v10 零写入**，等作者 4 项输入后一条命令落笔）；
>   ③ `manuscript\Cover_Letter_npjNaturalHazards_v2.docx` —— 投稿信 6 处数字/措辞对齐 v10
>   （`33.3→33.4`、`40.2→40.3`、`undefended→defended baseline`、`0.83→0.82‰`、`0.68→0.67‰`、`0.38→0.39‰`），
>   17 段 / 495 词 / 1 页，`check_office` pass；
>   ④ `manuscript\review_notes\` —— 18 篇审稿问答（字节一致）+ `README.md` 索引 + v10 核对表；
>   ⑤ `docs\_待决事项.md` —— A1–A7 输入、B1–B5 待点头、G8 定义、已裁定清单；
>   ⑥ `tools\_gate_g8.py` → **5 PASS / 1 PENDING**。
> - **✅ v11 排版修复（2026-10-18）**：作者发现 v10 预览里「Figure 14 长图注下面没有图」。
>   核查结论：**图没丢**（`word/media/image14.png` 与源图逐字节相同，画在 p15），
>   丢的是「长图注 ↔ 图」的绑定 —— 图块第三段（长图注，样式 `a0`）不在 keepNext 链上，
>   而 WP7.2 把图 14 的纵横比从「纵向压扁 15.5%」修正为真实比例后图块**长高 0.726 in**，
>   长图注被挤到下一页（下一页 `Discussion` 恰是 keepNext 链，整页只剩那两行字）。
>   修复 = 给 **37 个图注短标签段落**各加 `<w:keepNext/>`（纯段落属性、零文字变化），
>   产出 `PAPER_MANUSCRIPT_v11.docx`；**G11 18/18**、**G7 14/14**、预览 62→64 页、
>   **0 个「只剩图注」页**。详见 `docs\_v11_排版修复报告.md`。
> - **✅ WP11 全量对齐核查（2026-10-18）**：把 v11 的 **1,385 个数字 token** 逐个归类
>   （**584 个模型/参数/数据类全部绑定到 758 条真值指标**并按稿件精度逐字比对），
>   另核 11 张表、37 张图、16 条排序/恒等式断言与内部一致性。
>   发现 **6 项**：4 类共 **15 个数字**错/旧（P42 六个旧百分位、Knutson 因子 1.05/1.10→**1.0324/1.0442**、
>   表 8 末行偏差带 −0.2%/+0.6%→**−0.4%/+0.2%**、表 8 r9 +18%→**+17%**）、
>   图 14 图注超范围、P49 统计量误标。**6 项已全部修入 v12**，末项按作者裁定 A1-a 只改表述、
>   数字不动；另执行 A2（去掉 `0.9999` 伪精度）与 A3（6 段正文误用标题样式 → Body Text），
>   共 **12 处文字 + 6 处样式编辑**。完整记录见 `docs\_wp11待裁清单.md` 与 `docs\_wp11对齐核查报告.md`。
>   **G12 14/14 PASS**，v12 复验 **0 发现**。另按作者指示执行 A2（去掉 0.9999 的伪精度）与
>   A3（6 段正文误用标题样式 → Body Text，分页 64→63 页）。详见 `docs\_wp11对齐核查报告.md`。
> - **✅ 作者裁定（2026-10-18）：数据来源以「实际获取来源」为准。**
>   稿件 `P194`（3 处）/`P204`（1 处）写 **Anjuke（安居客）**，这是**数据实际来源**；
>   而 `Climate\00_config.py:71` 的 `LIANJIA_POI_DIR = …\上海小区数据（链家）` 只是**早期命名的历史遗留**
>   （当年先按平台名建目录，后查明抓取网址来自安居客）。
>   → **稿件不改**（本来就是对的）、**代码不改**（保持与归档结果逐位一致）；
>   映射记在 `docs\_数据可公开性分级清单.md` D12 与 `docs\_待决事项.md` A6。
> - **WP8 假缺陷排除**：`P192`「shelf width of  km」看似缺数，实为内联 OMML `L_shelf=550` / `h_shelf=55`，
>   python-docx 的 `.text` 不渲染数学层。**本包内判断数字缺失必须先查 `m:oMath`**。
> - **WP10 尚未开始**（`SHA256SUMS.csv`、`_v11_基线清单.json`、`REPRODUCE.md`、交付清单、搬家演练）。

---

## 归档说明（历史报告哪些是「当前口径」、哪些是「伪影证据」）

> 本项目保留**全部失败的校验报告**（不删除、不覆盖），以便审稿人复核判定过程。
> 读取时请按下表区分口径，**不要**把 preA 伪影轮的数字当结论。

| 文件 / 目录 | 属于哪一轮 | 口径 |
|---|---|---|
| `docs\_基线复现校验报告.md` | WP4 旧乡镇层 | 历史基线（复现已 PASS） |
| `docs\_基线复现校验报告_WP5-official.md` | WP5 官方层（未解耦岸线） | ⚠️ **preA 伪影轮** |
| `docs\_潮损偏移复核报告_伪影证据.md` | 潮损 −13% 归因 | ⚠️ **伪影证据**（结论：几何伪影） |
| `docs\_潮损偏移复核报告.md` | 同上（当前保留版） | 归因说明 |
| `docs\_边界差异对照.md` | preA | ⚠️ **伪影轮对照** |
| `docs\_边界差异对照_A解耦.md` | **选项 A** | ✅ **当前口径** |
| `output_archive\boundary_official_20261016_220941\` | WP5 preA 全链输出 | ⚠️ **已作废，仅作证据** |
| `output_archive\boundary_official_A_20261016_230820\` | WP5-A | ✅ **A 基线（终稿口径）+ 回滚点** |
| `output_archive\baseline_legacy_20261016_212711\` | WP4 旧层 | 历史基线归档 |
| `output_archive\wp6_sensitivity_20261017_215456\` | WP6 | 灵敏度全量重跑归档 |
| `output_archive\_wp8_da_dryrun_*\`、`_wp8_letter_*\` | WP8 | DA 补丁器 dry-run 与投稿信渲染快照（非交付件） |
| `output_archive\_wp8_fig14_keepnext_*\` | WP8 | v10/v11 预览页与图 14 图片取证（图注分离缺陷的 before/after） |

**判据**：凡是文件名/目录名含 `_伪影`、`_WP5-official`、`boundary_official_2026…220941` 的，一律是 preA 轮；
凡是含 `A解耦`、`boundary_official_A_…230820`、`wp6_sensitivity` 的，才是当前口径。

---

## 0. 三步上手

```powershell
# 1) 环境自检（必过）
env\run.ps1 tools\_env_selfcheck.py         # 期望末行：G3 SELF-CHECK = PASS

# 2) 闸门复核（G0 安全网 / G1 代码 / G2 数据）
env\run.ps1 tools\_gates.py                 # 期望末行：OVERALL (G0-G2) = PASS

# 3) 跑全链（11 步，约 25–30 分钟）——  ⚠️ 阅读 §4 前置条件后再执行
env\run.ps1 run_v8.py
```

---

## 1. 目录结构

```
Nature npj Natural Hazards\
├─ README.md                     ← 本文件
├─ run_v8.py                     ← 权威编排器（11 步）
├─ run_sensitivity.py            ← 灵敏度编排器（17 sweep / 85 取值，实测 ≈21 h）
├─ Climate\                      ← C01–C07 + 依赖（流水线主体）
│   ├─ 00_config.py              ← 路径与参数中枢（本次仅改 4 处，见 docs\_代码归集说明.md）
│   ├─ 01_hazard_tc.py … 07_climate_index.py
│   ├─ climate_functions.py / district_price_data.py
│   ├─ build_admin_boundary.py   ← 官方边界层加工脚本
│   ├─ generate_figures_new.py   ← 30 张图（依赖本地包 Climate\visualization\）
│   ├─ visualization\
│   └─ output\  intermediate / results / figures_new / logs
├─ Finance\                      ← F01–F03 + generate_figures.py（4 张图）
├─ Composite\                    ← X01 + generate_figures.py（3 张图）
├─ config\sensitivity_sweep.json ← 17 个灵敏度 sweep / 85 个取值
├─ data\                         ← 原始输入，全量 15,286 文件 / 14.236 GB
├─ env\                          ← 环境固化（唯一入口）
│   ├─ run.ps1  bootstrap.py  sitecustomize.py
│   ├─ requirements_frozen.txt   ← pip freeze（229 行 / 232 包）
│   └─ ENV.md                    ← 四个必处理的坑
├─ tools\                        ← 分析/审计/绘图辅助（非流水线）
│   ├─ freeze_baseline.py  audit_manuscript_consistency.py
│   ├─ compare_boundary_impact.py  gen_sensitivity_figures.py
│   ├─ _gates.py  _env_selfcheck.py  _wp0_safety_net.py  _wp1_collect_code.py
│   ├─ _diagnostics\             ← 一次性诊断脚本（留档）
│   └─ _nonpipeline\             ← CMIP6 下载、DID 实验等非流水线脚本（留档）
├─ output_archive\               ← 每次跑批的冻结快照（只增不改）
├─ _sensitivity_results\         ← 灵敏度产出（当前仅含最新合并件）
├─ _v8_logs\                     ← run_v8.py 的 JSONL 运行记录
├─ manuscript\
│   ├─ PAPER_MANUSCRIPT_FINAL.docx   ← 冻结底稿（= 根层同名文件，只读）
│   ├─ _frozen\PAPER_MANUSCRIPT_FINAL.docx
│   ├─ figures\  review_notes\
└─ docs\                         ← 中文说明与全部对照/校验报告
```

---

## 2. 数据（`data\`）

| 项 | 规模 |
|---|---|
| 文件数 / 字节 | **15,286 / 15,285,545,582 B（14.236 GB）**，与来源**逐字节一致**（G2 断言） |
| 内容 | `Exposure_data\`（建筑矢量、房价、人口、公共设施）、`Hazard_data\`（IBTrACS、FABDEM、风暴潮、海平面、不透水面、风/降水/气温栅格、ETOPO）、`我国乡镇（街道）行政区划数据\`、中国海洋灾害公报 |

### 2.1 行政边界层（**本轮的变更变量**）

| 层 | 路径 | 用途 |
|---|---|---|
| **官方层（正式出数）** | `data\我国乡镇（街道）行政区划数据\_官方_天地图GS2024-0650\上海_区级_GS2024-0650.shp` | 天地图 **GS(2024)0650** 号县级区划，经 `Climate\build_admin_boundary.py` 加工。SHA256 `d2eb3fc0…72932` |
| 旧乡镇层（仅基线回归） | `data\我国乡镇（街道）行政区划数据\2021年我国乡镇（街道）边界数据.shp` | 复现 A1 基线用；正式结果不使用 |

### 2.2 ⚠️ 台风输入必须钉住（否则必失败）

`IBTrACS.WP.v04r01.nc` 是**活数据集，已于 2026-07-25 被原地更新**：用现行文件会得到
**108** 事件、频率 **1/82**，而稿件口径是 **107** 事件、**1/81**。

**权威口径 = 钉住旧版快照**（作者 2026-10-16 裁定，路线 A）：

```
data\Hazard_data\WP台风数据\IBTrACS.WP.v04r01_old_202510.nc
  8,904,634 B   SHA256 DA05013357E6ADFC11DAE72C5830BED602A6C2AAFC3F3C228653850BA8DEF91D
```

实测：用该快照重跑 C01，**全部数值与 2026-03-28 权威产物逐位一致**。

---

## 3. 环境

见 **`env\ENV.md`**。唯一入口是 `env\run.ps1`；唯一需要改的常量是它顶部的 `CONDA_PREFIX`。

---

## 4. 跑模型前必须满足的前置条件（任何主链重跑，含 WP4 / WP5-A / WP6 之后）

> **不满足则 G4 必然失败，且失败现象会误导你去排查环境。**

1. **钉住台风输入**：`V8_PARAM_OVERRIDES` 里设
   `IBTRACS_FILE = <NEWROOT>\data\Hazard_data\WP台风数据\IBTrACS.WP.v04r01_old_202510.nc`
2. **钉住 Knutson 强度因子**：`SSP2-4.5 = 1.0324`、`SSP5-8.5 = 1.0442`
   （`00_config.py` 兜底是 1.05 / 1.10；`01_hazard_tc.py` 先联网取、`except` 静默回退
   → **联网与断网结果不同**，不钉住则 A8「断网可复现」不成立）
3. **同一时刻只允许一个 C01**：32 GB 内存，并发两个 C01 会 OOM。
   各条全链**必须串行**，启动前清理残留 `python.exe`。
4. **判据一律用数值，不用字节**：HDF5/parquet/pickle 会因库版本产生 schema 与整型位宽漂移。
   **例外**：`.npy` 可逐字节比对 —— A 的验证就靠 `building_coast_distance_m.npy` 逐字节相同。
5. **`V8_PARAM_OVERRIDES` 不能重定向输出路径**：值只能是 `str`/数，改成路径会让
   `01_hazard_tc.py:161` 抛 `AttributeError: 'str' object has no attribute 'name'`。
   只改**输入**路径；要隔离输出请整目录复制代码。
6. **不要钉 `ADMIN_BOUNDARY_SHP`**（除非要做 WP4 式的旧层回归）：终稿口径下它必须是官方层；
   岸线已由 `COASTLINE_BOUNDARY_SHP` 独立控制。

> 推荐直接跑 `.\tools\_run_wp5_option_a.ps1`（或先加 `-DryRun` 只看预检）：
> 它会自动解析 CJK 路径、校验 IBTrACS 尺寸+SHA、确认 option-A 改动在位、确认无残留 `python.exe`。

---

## 5. 闸门状态（本次已通过的六个）

| 闸门 | 判据 | 结论 | 证据 |
|---|---|---|---|
| **G0** 安全网 | 970 文件清单；4 个输出目录整目录快照逐字节一致；冻结 docx SHA = `39240D38…`；钉住快照 SHA = `DA050133…` | **PASS** | `V8ROOT\_snapshot_before_20261016_205029\` |
| **G1** 代码归集 | 全树 62 个 `*.py` 可 `ast.parse`；流水线脚本绝对盘符路径命中 **0** | **PASS** | `tools\_gates.py` |
| **G2** 数据复制 | 15,286 文件 / 15,285,545,582 B 与来源一致；官方层 SHA = `d2eb3fc0…` | **PASS** | `docs\_wp2_robocopy.log` |
| **G3** 环境入口 | `env\run.ps1` 跑通自检 17/17：导入 climada/geopandas/rasterio 无 CRSError/SSLError，`CRS.from_epsg(32651)` 正常 | **PASS** | `tools\_env_selfcheck.py` |
| **G4** 基线可复现（A1） | 旧乡镇层全链 11 步；§2.6 冻结参考值 **60/60 逐位一致**（判据器已用运行前副本标定同为 60/60） | **PASS** | `tools\_gate_g4.py --label NEW`；`output_archive\baseline_legacy_20261016_212711\` |
| **G5** 边界切换（A2/A4） | 官方层全链 11 步；建筑数仍 585,033；41 张图由脚本重出且标签来自源码 | ⚠️ ~~第三档~~ → 被 A 取代 | `output_archive\boundary_official_20261016_220941\`（仅作伪影证据） |
| **G5-A** **终稿口径（选项 A）** | 静态核验 **23/23**；全链 11 步全 `rc=0`；C01 抠 107/2304、107 events、1177 tracks；A 专项验证 **9/9**（岸线回到 **347.9 km**，`building_coast_distance_m.npy` 与旧层基线**逐字节相同**，城市潮损 EAL **6.2631 bn / +0.26%**）；41 图重出后 HSI/CCHI 标签目视确认 | **PASS**；对照升为**第二档**（城 0.2099% / 区 3.0009%），Top5 换位须上报 | `tools\_check_option_a.py`、`tools\_verify_option_a_result.py`、`docs\_岸线解耦A验证报告.md`、`docs\_边界差异对照.md`、`output_archive\boundary_official_A_20261016_230820\` |

详细逐条记录见 **`docs\_执行日志.md`**。

---

## 6. 文档索引（`docs\`）

| 文件 | 作用 |
|---|---|
| `_交接文档_新session快速上手_v1.md` | 冷启动路由（**第一读**） |
| `_预检报告_C01复现性与IBTrACS输入变更_v1.md` | 推翻原假设的实测结论（**第二读**） |
| `_执行方案_官方边界重跑与稿件更新_v1.md` | 848 行执行方案（WP0–WP10 + 验收 A1–A8） |
| `_校验清单_SHA256SUMS.txt` | 上述三份 + 底稿的 SHA256 |
| `_执行日志.md` | 逐闸门记录（§13 = 选项 A 实施、重跑、验证、归档全过程） |
| `_边界差异对照.md` | OLD → **A** 对照（**第二档**）；A 版快照 `_边界差异对照_A解耦.md` |
| `_岸线解耦A验证报告.md` | 选项 A 专项验证（岸线 347.9 km、npy 逐字节、三段 EAL 对照，9/9 PASS） |
| `_潮损偏移复核报告_伪影证据.md` | −13% 伪影的证据（**已被守卫保护，勿覆盖**） |
| `_基线复现校验报告.md` | §2.6 60 项冻结参考值对照（label = `WP5-official-A`；**48 项变化 = WP7 改数清单**） |
| `_代码归集说明.md` | WP1 复制/排除/移位的完整清单与理由 |
| `_wp1_collect_report.json` / `_wp2_robocopy.log` | WP1/WP2 机器可读证据 |

---

## 7. 绝对不做的事

- 不修改 **V8ROOT** 下任何既有文件（只读 + 快照）
- 不修改 `manuscript\PAPER_MANUSCRIPT_FINAL.docx`（含 131 个 `m:oMath`；**禁止整段 `.text` 赋值**，只能 run 级替换）
- 不改模型参数、不重标定、不做更高精度边界层评估
- 不恢复 v6 的 tmean 优先级链；不把 CRI 的 heat 分量改成 Tmean
- 不重建已失效的 `_regression_test.py` / `_v8_baseline_manifest.json`
