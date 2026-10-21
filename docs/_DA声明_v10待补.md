# DA 声明改写稿（WP8-2）

> ⛔ **本文件已被 WP14 取代（2026-10-18）**，仅作历史留档，**不要再按它执行**。
> 现行做法：`docs\_数据溯源台账.csv` → `tools\make_availability_v2.py` → 两个声明 docx（v15），
> 由 `tools\_gate_g14.py` 断言「台账 ↔ 声明」双向一致。
> 取代原因：v14 之前的声明是手写的，把「房价」写成单一来源；WP14 查明它其实是
> **两套独立数据**（区县/市级面板 = 商业订阅；小区挂牌 = 商业房产平台），且漏了官方边界层、
> 气象/海平面/不透水面栅格、建筑底册、普查与海洋灾害公报共 9 个来源。

> 生成日期：2026-10-17
> 对象：`manuscript\PAPER_MANUSCRIPT_v11.docx` 的 `P253`（`Data availability.` 段，**单 run、832 字符、内部无 `m:oMath`**）
> 说明：v11 = v10 + 图注 keepNext 排版修复，**正文与 v10 逐字节相同**（见 `docs\_v11_排版修复报告.md`）；v10 原样保留作证据基线。
> 状态：**已备料，未落笔**。执行器 = `tools\patch_da_statement.py`（默认 dry-run）。
> 依据：`docs\_数据可公开性分级清单.md`（D01–D20）；skill `nature-data` 的 8 步流程。

---

## 1. 现文（v10 实况，逐字）

```
Data availability. The processed building exposure inventory (585,033 records), district-level loss
panels and index series generated in this study are available at [Zenodo DOI to be assigned].
Source data: IBTrACS v4r01 from NOAA NCEI (https://doi.org/10.25921/82ty-9e16); FABDEM V1-2 from
the University of Bristol data repository; LandScan population grids from Oak Ridge National
Laboratory (https://doi.org/10.48690/1524213); ETOPO 2022 from NOAA NCEI
(https://doi.org/10.25921/fd45-gt74); housing price data from [data provider, with access
conditions]. Code availability. All model code is implemented in Python using the CLIMADA platform
(https://github.com/CLIMADA-project/climada_python) and is available at [GitHub repository,
release version], including the fixed random seed (42) configuration for full reproducibility.
```

**现文的 3 个缺口**（按 nature-data 审计）：
1. **3 处占位符**在正文中可见 → 见 §4 槽位。
2. **缺官方区县边界层来源**（GS(2024)0650）—— 而这是全文区县归属/面积/底图的唯一依据（`Climate\00_config.py:35`）。
3. **缺「复用数据中不可转存部分」的说明** —— 气象/海平面/不透水面栅格与商业矢量件属 B/C 档，现文未声明其不转存，reader 会误以为全部可获取。

---

## 2. 新文（模板，渲染后**可整段替换**）

> 保留 `Data availability.` / `Code availability.` 两个标签原样；保留全部已印 DOI 与 CLIMADA 链接；
> 仅**新增 2 句** + **3 处槽位替换** + **首句按建筑清单公开性二选一**。

```
Data availability. {BUILDINGS_SENTENCE} District boundaries follow the official 2024 county-level
division product (Tianditu, map review no. GS(2024)0650); the boundary layer is not redistributed.
The gridded meteorological, sea-level and impervious-surface source rasters described in Methods are
third-party products and are not redistributed here. Source data: IBTrACS v4r01 from NOAA NCEI
(https://doi.org/10.25921/82ty-9e16); FABDEM V1-2 from the University of Bristol data repository;
LandScan population grids from Oak Ridge National Laboratory (https://doi.org/10.48690/1524213);
ETOPO 2022 from NOAA NCEI (https://doi.org/10.25921/fd45-gt74); housing price data from
{PRICE_PROVIDER}. Code availability. All model code is implemented in Python using the CLIMADA
platform (https://github.com/CLIMADA-project/climada_python) and is available at {REPO_URL}
({REPO_TAG}), including the fixed random seed (42) configuration for full reproducibility.
```

### 2.1 首句三态（`BUILDINGS_SENTENCE`）

| 态 | 触发 | 句子 |
|---|---|---|
| `unspecified`（**默认**） | 未传 `--buildings` | 与原句**逐字相同**：<br>`The processed building exposure inventory (585,033 records), district-level loss panels and index series generated in this study are available at {ZENODO_DOI}.` |
| `public` | `--buildings public` | 同上（作者确认清单可整体公开） |
| `restricted` | `--buildings restricted` | `The district-level loss panels and index series generated in this study are available at {ZENODO_DOI}; the full building-level inventory (585,033 records) cannot be redistributed because it derives from licensed commercial footprint and listing data.` |

> `unspecified` 与原句一致，故**不带参数跑一次 dry-run 时，DA 的语义变化只有新增的 2 句**，便于审阅。

### 2.2 槽位

| 槽位 | 参数 | 未传时保留（= 现状原文） |
|---|---|---|
| `{ZENODO_DOI}` | `--zenodo-doi` | `[Zenodo DOI to be assigned]` |
| `{REPO_URL}` `{REPO_TAG}` | `--repo-url` `--repo-tag` | `[GitHub repository, release version]` |
| `{PRICE_PROVIDER}` | `--provider` | `[data provider, with access conditions]` |

**任一槽位未传 → 逐字保留原占位符，绝不猜。** 这也是 `_gate_g8.py` 判定 PENDING 的依据。

> **作者裁定（2026-10-18）**：数据来源以**实际获取来源**为准 —— 房价/小区数据来自 **Anjuke（安居客）**
> （`data\Exposure_data\房屋\上海小区数据（链家）\` 的目录名与 `LIANJIA_POI_DIR` 常量名是早期命名的历史遗留）。
> → `{PRICE_PROVIDER}` 建议渲染为：
> `Anjuke under a commercial data licence; the raw listings are not redistributed here`
> （仍待作者确认访问条件的措辞，见 `docs\_待决事项.md` A4）。

---

## 3. 逐句改动对照（人工复核用）

| # | 位置 | 动作 | 新内容要点 | 依据 |
|---|---|---|---|---|
| 1 | 首句 | 条件改写 | 建筑清单公开性二选一 | 分级清单 §3-①（作者输入 #5） |
| 2 | 首句后 | **新增** | 官方边界层 GS(2024)0650 + 「boundary layer is not redistributed」 | 分级清单 D15；`_SOURCE.txt` |
| 3 | 第 2 新句后 | **新增** | 气象/海平面/不透水面栅格为第三方产品、不转存 | 分级清单 D07–D10（C 档） |
| 4 | `Source data:` 列表 | 保留 | IBTrACS / FABDEM / LandScan / ETOPO 四条**逐字不动** | 已核实，含 3 个 DOI |
| 5 | 房价项 | 槽位替换 | 提供方 = **Anjuke（安居客，作者 2026-10-18 裁定）+ 访问条件** | 分级清单 D12 / D14（作者输入 A4） |
| 6 | `Code availability.` | 槽位替换 | 仓库 URL + release/tag | 分级清单 D19（作者输入 #3） |

**不做的事**：不改 `Data availability.` / `Code availability.` 标签；不动 CLIMADA 链接；不新增未核 DOI；不写 "available upon request"。

---

## 4. 执行方式（`tools\patch_da_statement.py`）

```powershell
# dry-run（默认）：落到 output_archive\wp8_da_dryrun_<ts>\，正文零改动
& ".\env\run.ps1" tools\patch_da_statement.py

# 只填 DOI（其余仍 PENDING），验证单槽位行为
& ".\env\run.ps1" tools\patch_da_statement.py --zenodo-doi 10.5281/zenodo.XXXXXXX

# 作者 4 项齐备后正式落笔
& ".\env\run.ps1" tools\patch_da_statement.py --apply `
    --zenodo-doi 10.5281/zenodo.XXXXXXX `
    --repo-url https://github.com/<owner>/<repo> --repo-tag v1.0.0 `
    --provider "Lianjia/Anjuke, <access conditions>" `
    --buildings restricted

# 落笔后必须回归
& ".\env\run.ps1" tools\_gate_g7.py     # 期望 14/14
& <bundled python> tools\_gate_g8.py    # 期望 6/6
```

**执行器不变量**（与 `rewrite_manuscript_v10.py` 同口径）：
1. 只改 `P253` 那**一个 `<w:t>` 的文本**，`<w:r>`/`rPr` 原样保留 → 字体字号不变。
2. 段数仍 **409**、`m:oMath` 仍 **131**、`m:oMathPara` 仍 **41**、表 **11**、`w:drawing` **37**。
3. zip 条目顺序不变；`word/` 下**非 document.xml 部件字节不变**。
4. `--apply` 前自动备份 `manuscript\_frozen\PAPER_MANUSCRIPT_v10_preDA_<ts>.docx`。
5. 幂等：同一参数重复执行结果字节相同；若检测到已是新文（含 `GS(2024)0650`）则拒绝二次套模板并 exit 3。

---

## 5. 已排除的假缺陷（记录，避免后人重犯）

> 曾疑似 `P192`「adopting an effective shelf width of  km and a mean depth of  m」丢失两个数值。
> **实为误判**：该处是内联 OMML 公式 `L_shelf = 550` 与 `h_shelf = 55`，
> `python-docx` 的 `.text` 不渲染 OMML，故显示为空白。**正文无缺损，不需要任何修改。**
> （与 `docs\_WP7.2执行勘误.md` 记录的「66 个段落文本层为空」是同一陷阱。）

**推论**：本包内对 docx 的一切「数字缺失/数字异常」判断，都必须先查 `m:oMath`，否则会误报。
