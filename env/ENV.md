# ENV · 环境固化说明

> 本文件记录**唯一可用**的运行环境与四个必须处理的坑。
> 入口脚本：`env\run.ps1`（**唯一入口**，不要直接 `python xxx.py`）。

---

## 1. 权威环境（已实测）

| 项 | 值 |
|---|---|
| conda 环境 | `C:\Users\Jack\miniforge3\envs\climada_env` |
| Python | **3.11.13**（conda-forge, MSC v.1943 64-bit） |
| 包总数 | **232**（`pip list` 实测；`pip freeze` 输出 229 行，差值来自 `pip`/`setuptools` 等自举包的 freeze 行为，不影响复现） |
| 冻结清单 | `env\requirements_frozen.txt` |
| 机器 | 32 GB 内存、24 逻辑核、`D:` 盘 |

> ⛔ **`C:\Users\Jack\anaconda3\envs\climada` 是废的**（无 climada、无 geopandas），**不要用**。
> `env\run.ps1` 会把 PATH 中所有含 `anaconda3` 的项剔除。

### 关键包版本

```
climada 6.1.0     GDAL 3.10.3       geopandas 1.1.3   rasterio 1.4.4
shapely 2.1.2     fiona 1.10.1      pyproj 3.7.2      numpy 2.3.5
pandas 2.3.3      scipy 1.15.2      scikit-learn 1.7.2 statsmodels 0.14.5
xarray 2025.6.1   netCDF4 1.7.4     h5py 3.16.0       pyarrow 21.0.0
tables 3.11.1     Cartopy 0.25.0    contextily 1.6.2  geopy 2.4.1
pathos 0.3.4      matplotlib 3.10.6 numba 0.62.1      openpyxl 3.1.5
```

---

## 2. 入口

```powershell
# 从包根目录运行
env\run.ps1 run_v8.py                       # 全链 11 步
env\run.ps1 run_v8.py --only C01            # 单步
env\run.ps1 run_v8.py --from C03 --to C04   # 区间
env\run.ps1 run_sensitivity.py              # 灵敏度（≈10.5 h）
env\run.ps1 Climate\generate_figures_new.py --only basic_facts
env\run.ps1 tools\_env_selfcheck.py         # 环境自检（G3）
env\run.ps1 tools\_gates.py                 # 闸门 G0–G2
```

`env\run.ps1` 做五件事：① 钉 `CONDA_PREFIX`；② 剔除 `anaconda3` 并前置 conda 目录；
③ 设 `GDAL_DATA`/`PROJ_DATA`/`PROJ_LIB`/`SSL_CERT_FILE`；④ 把 `env\` 放进 `PYTHONPATH`
（使 `sitecustomize.py` 的 SSL 补丁生效）；⑤ 经 `bootstrap.py` 预加载 DLL 后分发。

> `env\run.ps1` **必须保持纯 ASCII**：Windows PowerShell 5.1 会按系统 ANSI 代码页读取
> `.ps1` 内容，非 ASCII（含中文路径）会变乱码。所有路径都由 `$PSScriptRoot` / `CONDA_PREFIX` 推导。

---

## 3. 四个必须处理的坑（不改则必失败）

| # | 症状 | 原因 | 处置（已固化在哪） |
|---|---|---|---|
| 1 | `rasterio.errors.CRSError: proj.db … LAYOUT.VERSION.MINOR = 5 whereas a number >= 6 is expected`（崩在 `03_exposure.py` 的 LandScan 裁剪处） | 未设 `CONDA_PREFIX` → `init_environment()` 不写 `GDAL_DATA`/`PROJ_DATA` | `env\run.ps1` 设变量；**并且** `Climate\00_config.py:init_environment()` 增加了"由 `sys.executable` 反推环境根"的回退分支，同时补写 `PROJ_LIB` |
| 2 | 同名库被 anaconda3 版本抢先加载 → 各类诡异导入错误 | PATH 中含 `anaconda3` | `env\run.ps1` 剔除并前置 `Library\bin`、`Library\usr\bin`、`Library\mingw-w64\bin`、环境根、`Scripts` |
| 3 | `ssl.SSLError: [ASN1: NOT_ENOUGH_DATA]`（`import climada` → `contextily` → `geopy` → `ssl.create_default_context()`） | Windows 证书库状态相关，**间歇性** | `env\sitecustomize.py` 包裹 `ssl.SSLContext.load_default_certs`，异常静默并补载 certifi 根证书。**不关闭证书校验** |
| 4 | `fiona`/`pyarrow` 找不到 `gdal.dll` / `arrow*.dll` | DLL 不随包分发 | `env\bootstrap.py` 用 `ctypes.CDLL(绝对路径)` 预加载 `gdal.dll`、`arrow*.dll`。**不预加载** `hdf5.dll`（h5py 自带）、`netcdf.dll`（netCDF4 自带） |

> **关于坑 4 的实现选择（与方案原文的偏离，已实测）**：方案 §4 WP3.2 写的是
> `os.add_dll_directory(Library\bin)`。原 `run_sensitivity.py` 的注释记录了一条实测结论：
> `os.add_dll_directory()` 会让进程进入 secure DLL-search mode，**反而**使 h5py / rasterio /
> fiona 无法从各自子包目录加载自带 DLL。因此 `bootstrap.py` 采用**已验证有效**的做法
> （`ctypes.CDLL` 全路径预加载 + PATH 前置），语义等价而不触发该副作用。

---

## 4. 迁移到别的机器

1. 复制整个包目录（含 `data\`，共约 16 GB）。
2. 在新机用 `env\requirements_frozen.txt` 重建同名 conda 环境：
   `conda create -n climada_env -c conda-forge --file env\requirements_frozen.txt`
3. 改 `env\run.ps1` 顶部的**唯一一行** `$env:CONDA_PREFIX`。
4. 跑 `env\run.ps1 tools\_env_selfcheck.py`，须输出 `G3 SELF-CHECK = PASS`。

> 路径无关性已由设计保证：`00_config.py` 的 `PROJECT_ROOT = Path(__file__).parent.parent`、
> `DATA_DIR = PROJECT_ROOT/"data"` 全为相对推导；流水线脚本中绝对盘符路径命中数为 **0**
> （由 `tools\_gates.py` 的 G1 断言）。
