# DATA_SOURCES — where every file in this repository came from

One row per dataset. The authoritative, machine-readable version is
`provenance/Dxx.yaml` (one card per dataset); this table is its human-readable
rendering. Identifiers were resolved and checked when the ledger was frozen;
the `level` column says how strong the evidence is.

**Level key** — 强: producer + product/version + resolved identifier + an
on-disk artefact; 中: no resolved identifier; 弱: acquisition channel only;
无: upstream source could not be established.

| id | dataset | producer | upstream identifier | licence | level | files here |
|---|---|---|---|---|---|---|
| D01 | IBTrACS 台风最佳路径（WP 盆） | NOAA NCEI / WMO（IBTrACS Science Team） | https://doi.org/10.25921/82ty-9e16 | NOAA 开放数据（盘上无许可文本） | 强 | 4 / 15.9 MiB |
| D02 | FABDEM V1-2 森林冠层校正 DEM | University of Bristol（Hawker et al., 2022） | https://doi.org/10.1088/1748-9326/ac4d4f | 未记录（盘上无许可文本） | 中 | 61 / 611.9 MiB |
| D03 | ETOPO 2022 全球地形 | NOAA NCEI | https://doi.org/10.25921/fd45-gt74 | NOAA 开放数据 | 强 | 1 / 1549.6 MiB |
| D04 | LandScan 逐年人口栅格 | Oak Ridge National Laboratory（LandScan） | https://doi.org/10.48690/1524213 | ORNL LandScan 使用条款（需注册/许可；盘上无文本） | 强 | 126 / 7.2 MiB |
| D05 | 第五/六/七次全国人口普查 | 国家统计局（全国人口普查） | （政府出版物，无 DOI） | 公开统计资料 | 中 | 26 / 6.4 MiB |
| D06 | 逐年乡镇人口（LandScan 聚合派生） | ORNL LandScan → 立方按乡镇边界聚合 | （派生数据） | 同上 | 中 | 7 / 2.3 MiB |
| D07 | 逐月全风速栅格 | 清华大学地球系统科学系 阳坤团队（He et al.） | https://doi.org/10.11888/Atmos.tpdc.302088（供应方原文）；方法论文 https://doi.org/10.1038/s41597-020-0369-y | TPDC 使用条款（盘上无文本） | 强 | 891 / 4.2 MiB |
| D08 | 逐月平均气温栅格（含全国逐日母产品） | NOAA NCEI GSOD 站点 → 立方反距离权重插值 | （无 DOI；上游 https://www.ncei.noaa.gov/data/global-summary-of-the-day/archive/） | NOAA 开放数据 + 立方加工件 | 强 | — (not included) |
| D09 | 逐月降水栅格 | Hu & Miao（CHM_PRE） | https://doi.org/10.5281/zenodo.14634575 | Zenodo 开放许可（PDF 未列许可名） | 强 | 783 / 5.8 MiB |
| D10 | 逐月最低气温栅格 | NOAA NCEI（Global Surface Summary of the Day, GSOD 站点）→ 立方数据学社 IDW 插值 | https://www.ncei.noaa.gov/data/global-summary-of-the-day/archive/（GSOD 无 DOI） | 会员专享（不可再分发）；按其要求只引用 NOAA 原始来源 | 中 | 531 / 5.4 MiB |
| D11 | 逐月最高气温栅格 | NOAA NCEI（GSOD 站点）→ 立方数据学社 IDW 插值（同 D10，同一套流水线） | https://www.ncei.noaa.gov/data/global-summary-of-the-day/archive/（GSOD 无 DOI） | 会员专享（不可再分发）；按其要求只引用 NOAA 原始来源 | 中 | 531 / 7.1 MiB |
| D12 | 逐月海平面高度异常栅格 | Copernicus Marine Service（CMEMS / DUACS） | https://doi.org/10.48670/moi-00148 | CMEMS 许可（盘上无文本） | 强 | 375 / 1.3 MiB |
| D13 | 逐年不透水面比例栅格 | 中国农业大学 UEMM 团队（Gong et al., 2020, GAIA） | https://doi.org/10.1016/j.rse.2019.111510（论文；数据集本体无独立 DOI） | 开放（论文 CC BY；数据平台条款盘上无文本） | 强 | 10 / 2.5 MiB |
| D14 | 全市逐月二手房价格 | 聚汇数据（gotohui.com）· **作者 2026-10-18 声明** | https://www.gotohui.com（平台；无数据集级 DOI） | 会员条款（盘上无文本） | 中 | 7 / 1.5 MiB |
| D15 | 区县逐月二手房价格 | 聚汇数据（gotohui.com）· **作者 2026-10-18 声明** | https://www.gotohui.com（平台；无数据集级 DOI） | 会员条款（盘上无文本） | 中 | 7 / 1.7 MiB |
| D16 | 小区级小区资料（POI + 信息表，35 字段） | 安居客（Anjuke） | （无 DOI；`xiaoquurl` 指向 shanghai.anjuke.com） | 平台条款（盘上无文本） | 强 | 9 / 59.0 MiB |
| D16b | 小区逐月挂牌价（147,537 行） | 聚汇数据（gotohui.com）· **作者 2026-10-18 声明** | https://www.gotohui.com（平台；无数据集级 DOI） | 未知 | 中 | — (not included) |
| D17 | 2024 年多属性建筑矢量 | 清华大学 龙瀛团队（Zhang, Zhao & Long, 2025） | https://doi.org/10.1038/s41597-025-04730-5（论文）；https://doi.org/10.6084/m9.figshare.27992417（数据集） | 论文 CC BY；Figshare 条目许可盘上无文本 | 强 | 106 / 762.6 MiB |
| D18 | 1975–2020 城市建成区矢量 | 中国矿业大学 胡振琪团队（Han, Hu & Zhou, 2024） | https://doi.org/10.57760/sciencedb.11249 | 开放（SciDB） | 强 | 52 / 3.8 MiB |
| D19 | 官方区县边界层 GS(2024)0650 | 国家基础地理信息中心 / 国家地理信息公共服务平台（天地图） | https://cloudcenter.tianditu.gov.cn/administrativeDivision（无 DOI） | 官方审图产品：可引用、可绘示，矢量件**不转存** | 强 | 54 / 24.6 MiB |
| D20 | 乡镇（街道）边界层（文件名「2021」，**实测 2015 年前口径**；来源=立方 631 包） | **无上游**（分发方自述「没有明确来源，从互联网收集」） | （无） | **「只能用于个人练习，不得用于商业及其它目的」（分发方原文）** | 无 | 9 / 363.7 MiB |
| D21 | 《中国海洋灾害公报》与 1995–2023 损失转录表 | 自然资源部（国家海洋局）《中国海洋灾害公报》 | https://www.mnr.gov.cn/sj/sjfw/hy/gbgg/zghyzhgb/（政府出版物，无 DOI） | 公开政府信息 | 强 | 4 / 1.2 MiB |
| D22 | 高德 POI（公共设施 11 类 + 交通运输 3 类） | 高德地图（Amap） | （无） | 平台服务条款禁止批量转存 | 中 | 14 / 163.8 MiB |
| D23 | 高德 POI「商务住宅」 | 高德地图（Amap） | （无） | 平台服务条款禁止批量转存 | 中 | 6 / 40.8 MiB |
| D24 | 影响上海的台风名录 | 作者整理 | （无） | — | 无 | 1 / 0.0 MiB |
| D25 | 处理后面板与结果表（自产） | 本研究 | （待分配 Zenodo DOI） | 本研究授权（CC BY 4.0 建议） | 强 | 23 / 50.0 MiB |
| D26 | 图表源数据（自产） | 本研究 | （同 D25） | 本研究授权 | 强 | 37 / 31.1 MiB |
| D27 | 模型代码（自产） | 本研究 | （待分配 GitHub 仓库） | 本研究授权（建议 MIT/BSD-3） | 强 | 111 / 1.4 MiB |
| D28 | 随包携带的预处理脚本 | 本研究 | （随代码仓） | 本研究授权 | 强 | 12 / 0.1 MiB |

## Datasets that are *not* in this repository

| id | dataset | why not |
|---|---|---|
| D08 | 逐月平均气温栅格（含全国逐日母产品） | **不参与运行**（生成 tmean_shanghai.xlsx 后无人读取；热应激用 Tmax）；**占整包 71.6% 体积**；目录名 2005–2025 与 PDF 标题 1981–2024 不一致 |
| D16b | 小区逐月挂牌价（147,537 行） | **不参与运行**：全树 0 处代码读取「挂牌」；估值用的是 D16 的 POI `price` 字段。其 1 个文件已计入 D16 的 9 个文件内，此处不重复计数 |

## How the data reach the model

`provenance/Dxx.yaml` also lists, for every dataset, the exact files inside this
repository that belong to it (`package_paths`) and how the pipeline uses it
(`pipeline_usage`). `manifest.json` gives path, size and SHA-256 for every one of
them.

## Please cite the producers, not this repository

Reusing the data means citing the upstream producer named above (and their DOI
where one exists). The MIT licence in `LICENSE` covers the code only.
