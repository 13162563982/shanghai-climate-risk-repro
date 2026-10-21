# WP7.2 执行勘误与裁定备案（v10 改稿）

- 生成：2026-10-17 22:2x
- 适用：`manuscript\PAPER_MANUSCRIPT_v10.docx`（由 `PAPER_MANUSCRIPT_FINAL.docx` 改写，底稿未动）
- 操作清单：`docs\_v10_edit_plan.csv`（82 条）；工具：`tools\make_edit_plan.py` → `rewrite_manuscript_v10.py` → `rebuild_docx_figures.py` → `_gate_g7.py`
- 闸门：`docs\_执行日志.md` §17（G7 **13/13 PASS**）

本文只记"为什么不完全照 `docs\_数字变更对照表.md` 执行"。对照表本身是 WP7.1 的生成物，**未手工改动**。

---

## 1. 五处偏离（全部实测驱动）

### 1.1 `T8#r8c0` 补 `$V_{half}$` —— **作废，不执行**

对照表 §2.5 列："T8 第 8/9/10/11 行与第 13/14 行的 $V_{half}$/α/κ 符号在提取中缺失，属公式损坏"。

**实测**：Table 8 第 1 列有 **13 个单元 `has_math=True`**（r3–r11、r13–r15、r20），
OMML 对象（`m:oMath`）**确实存在于 XML 中**；只是 `m:oMath` 在文本层不产出任何字符，
所以提取器的文本层看到的是 `" adj. B_old (pre-2001 mid-rise)"`。

→ 文档本身没坏。照该条执行会把 `$V_{half}$` 当作正文字符串插到已有公式旁边，**造成符号重复**。
**处置：不执行**（`make_edit_plan.py` 的 `VOIDED_ITEMS` 常量，报告中单列"作废条目"）。

### 1.2 Table 2 第 3/4 行 —— **整行互换**，而不是"只换标签"或"只换数值"

两处指令互相矛盾且单独都不成立：

| 来源 | 指令 | 单独执行的结果 |
|---|---|---|
| 对照表 §1 `t2_r3_*` / `t2_r4_*` | 区留在原行，更新数值（Xuhui 2.3→2.2、4.1→4.0；Minhang 2.3→2.3、8.0→8.0） | 表不再按 EAL 降序（2.2 排在 2.3 之前） |
| 对照表 §2.5 `T1#r3c0` / `T1#r4c0` | 只把标签 Xuhui↔Minhang 互换 | 标签与数值错配（Minhang 配到 Xuhui 的暴露 4.0） |

**实测**：A 基线 闵行 2.2685 bn > 徐汇 2.2211 bn（旧层是徐汇 2.2898 > 闵行 2.2530），
即 3/4 名互换。表格按 EAL 降序排列，**必须整行互换**：

| 行 | District | EAL | Exposure | Ratio |
|---|---|---|---|---|
| r1 | Pudong | 6.0 | 14.8 | 0.40 |
| r2 | Yangpu | 2.6 | 3.4 | 0.77 |
| **r3** | **Minhang** | 2.3 | **8.0** | **0.28** |
| **r4** | **Xuhui** | **2.2** | **4.0** | **0.56** |
| r5 | Hongkou | 1.7 | 2.0 | **0.82** |

→ 执行 `TABLE2_CELLS` 9 格（含 r1c1 `5.9→6.0`、r5c3 `0.83→0.82`）。
**注意**：因整行互换，提取器按"格→区"归属会把这 6 格判成残余 CHANGE —— 闸门里已列为白名单并注明原因。

### 1.3 `P19` 的 `0.38‰` —— 由 `same` **升级为改动**

对照表判 `same`（登记值 OLD 0.39 / NEW 0.39，看不出变化）。但**稿件正文印的是 0.38‰**，
即稿子本来就跟自己的模型差一位（旧层也是 0.39）。
→ 按作者"所有数据都对齐最新模型结果"的指令改为 **0.39‰**（`WATCH_PROMOTED`）。
句中 "roughly twice the city-wide average" 仍成立（Hongkou 0.8214 / 0.39 = 2.1×）。

### 1.4 `T4#r2c1`（Table 5 SSP2-4.5 p10）`395` → `394`

对照表记 `395 | 394 | 394 | same`。登记值 394.50 / 393.73 在"取整"口径下都写 394，
看起来不变；但稿件印的是 **395**（394.50 半进位），而 A 基线 **393.73 只能印 394**。
→ 显式 override（`ROUND_BOUNDARY_CELLS`），类别 `ROUND-BOUNDARY`。

### 1.5 `P16` 的 39.5% —— **只改措辞，数字不动**

原判 `watch`（"39.5% 无法复现，须作者确认定义"）。实测可以复现：

```
26.5185 / 19.0056 − 1 = +39.53%     ← 分母是历史"有防御"残余 EAL
26.5185 / 24.2035 − 1 = +9.56%      ← 分母是历史"无防御"EAL（原句口径）
```

即 **39.5% 是"相对历史有防御残余"**，而 P16 写成 "above the historical **no-defence** level"。
P79 "residual risk still grows by 39.5%"（防御→防御）与 P83 "exceeds today's undefended baseline"
（+9.6%）**原文都正确**。
→ 只把 P16 的 `no-defence level` 改为 `defended level`，数字 39.5% 保留。

---

## 2. 核实后确认"不改"的 4 项

| 位置 | 原文 | 实测 | 结论 |
|---|---|---|---|
| `P16` | "roughly CNY 16 billion" | 潮损 EAL SSP5-8.5 = 15.9401 bn | 印 `16` 正确，不改 |
| `P17` | "1,070 storm realisations" | 合成路径 1,070（= 107×10）；总事件 1,177 = 107 历史 + 1,070 合成 | 措辞指合成集，正确，不改 |
| `P17` | "calibration fit ratio of 0.9999" | 0.9999（A 基线未变） | 不改 |
| `P49/P62` | "ρ = 0.358" | `Composite\00_config.py` 常量 0.358（`deviation_override` 亦为 0.358） | 稿件正确，原疑点排除 |

---

---

## 3. 结构修复：`Data Availability Statement` 标题位置（作者已批准）

底稿里标题与它管的正文被 15 个图块隔开：

```
P204  §2.9 Housing market prices（正文最后一段）
P205  Data Availability Statement          ← 标题在这里
P206–P250  Figure 24 … Figure 38（15 个图块）
P253  Data availability. … at [Zenodo DOI to be assigned] …
P254  References
```

**处置**：把 P205 这一整段**下移**到 P253 之前（只搬段，不新增/删除，段数仍 409）。
实现于 `rewrite_manuscript_v10.py` 的 `MOVE_PARAGRAPHS` 常量，闸门 G7-6c 断言
"标题后面紧跟 `Data availability.` 正文段"（实测 heading 落在 P252，正文在其后）。

---

## 4. 图件：底稿的 Figure 24–38 错位一格（**本轮最重的发现**）
| 证据 | 内容 |
|---|---|
| 二进制 | 24 号槽位载荷 SHA256 == `s_0101_tc_tracks_synthetic.png`；38 号槽位 == `df_01_defense_evidence.png` |
| 目视 | 24 号槽位渲染为西太合成路径图，而其图注写 "Defence evidence figure"；38 号槽位渲染为防御证据分面柱图，而其图注写 "SS MDR sensitivity" |
| 系统枚举 | `rebuild_docx_figures.py` 逐槽比对：**15 个槽位**（24–38）装的是"下一号图"的文件，第 38 格装第 24 图的文件（环形右移 1 位） |
| 三重旁证 | 图注标签 `Figure N:`、T10 图表索引、`pic:cNvPr` 图源路径 三者一致指向"该格应放哪个文件"；而**载荷 + `wp:docPr` 图号 + `wp:extent` 显示框**一起装错了 |

**处置**：按槽位语义（图注标签）重新赋值，一次解决"错位"与"陈旧"两个问题。
Figure 1–23 本来是对的（16 格哈希命中 + 6 格画布尺寸吻合）。

**连带 1：显示框**。因为框跟着错误图片走，11 个槽位的 `wp:extent` 宽高比与应放图不符（最大 169.5%），
只换载荷会压扁；其中 **Figure 14 在底稿里本来就是被拉伸的**（−15.5%）。
→ 保留宽度 `cx`，按新图重算 `cy = cx·h/w`，共重设 **12** 个。

**连带 2：替代文本**。`wp:docPr descr` 的图号从第 1 张起就是错的（第 1 张标 `Figure 10`）；
`pic:cNvPr descr` 的图源路径也跟着图片错位。
→ 统一改为与图注一致的 `Figure N: <图注标题>` + 该图正确的原始路径串（原样复用，不新造）。

**图源口径纠正**：`output_archive\boundary_official_A_20261016_230820\...\figures` 里的 37 张
是 **preA 旧图**（10/16 22:39–22:40 生成，`_run_wp5_option_a.ps1` 全脚本无 figure 生成调用），
**不能**当图件基准；现行 41 张（10/17 21:53–21:55，WP6 末次 restore 重出）才是 A 基线图，
且已用重跑验证 **78/78 哈希不变**。

---

## 5. PDF 说明（重要）

LibreOffice Kit 能正常转换（62 页、`missingFonts: []`），但它把本文档版面按 **1.5×** 排版，
内容右侧越出页面。**同一现象对冻结底稿完全一样**（底稿同样 61 页、同样越界），
说明是 LibreOffice 对该 docx 的既有渲染差异，**不是本次改动引入的**。
作者历史 PDF（`PAPER_MANUSCRIPT_整改版_v9.pdf`，66 页，Word 导出）版面正常。

→ **投稿用 PDF 请用 Word 另存**；`manuscript\PAPER_MANUSCRIPT_v10.pdf` 仅作内容核对。

---

## 6. 待作者确认（不阻塞交付，但需要一句话）

> **⚠️ 本表已升级**：权威清单见 **`docs\_待决事项.md`**（A1–A7 输入 / B1–B5 待点头 / G8 定义）。
> 本表保留为历史记录；其中第 5 项（3 个占位符）已在 `_待决事项.md` A2–A4 逐项展开，
> 另新增 **A6：稿件写 Anjuke、代码读链家**（WP8 新发现）。

| # | 事项 | 当前处置 |
|---:|---|---|
| 1 | `V_HALF_ADJ_C` 的 Max deviation 保留稿件 `0%` | ⏸ 已保留（重算 `≈0%`，数值等价） |
| 2 | 表 2 是否接受"整行互换"（即 3 名闵行、4 名徐汇） | 已按 A 口径执行 |
| 3 | `P19` 全市平均 `0.39‰`（原 `0.38‰`） | 已改 |
| 4 | `P16` "defended level" 措辞 | 已改 |
| 5 | `P253` 的三个占位符（Zenodo DOI / 房价数据提供方措辞 / GitHub release） | **待作者提供** |
| 6 | 投稿 PDF 是否由作者用 Word 导出 | 建议是 |

---

## 7. WP9 路径无关性（A3）—— 做了，附一条诚实结论

| 检查 | 结果 |
|---|---|
| `subst X:` 下重跑 C03–C04 | ⚠️ **该测试不具区分力**：`Path(__file__).resolve()` 把 `X:` 规范化回真实路径，运行日志里所有路径仍是 `D:\…` —— 虚拟盘并没有真正改变代码看到的根目录 |
| 重跑本身 | ✅ C03 + C02 + C04 全 rc=0（2m21s）；`building_skeleton.parquet`(41.7 MB)、`svi_by_district.csv`、`isr_panel.csv`、`delta_isr_by_district.csv` 与运行前快照 **逐字节相同** |
| 基线未被打扰 | ✅ `_wp6_readiness.py` → `RESULT: READY`（6 个 live 结果 CSV 仍与 A 归档一致） |
| 真正的证据①：静态扫描 | ✅ 流水线内部（`Climate/` `Finance/` `Composite/` `run_v8.py` `config/`）**零**硬编码绝对路径；仅 `env\run.ps1` 的 `CONDA_PREFIX`（设计上的唯一环境常量）、历史报告 JSON、WP0/WP1 一次性工具 |
| 真正的证据②：无网络依赖 | ✅ 三个模块目录 + `run_v8.py` 中 `urllib/requests/urlopen/socket` 命中 **0** —— 从不触网，故未做真实断网测试（没有可断的调用） |
| 快照 | `output_archive\wp9_pathindep_ref_20261017\`（4 文件 + `_snapshot_meta.json`） |
| 工具 | `tools\_verify_path_independence.py`（`snapshot` / `compare` 两个子命令） |

**结论**：路径无关性来自"代码里没有绝对路径 + 从不触网"，**不是**由 subst 运行证明的。
真正的搬家演练需要把整包复制到另一路径后重跑（约 14 GB），建议留到 WP10 交付前做一次。
