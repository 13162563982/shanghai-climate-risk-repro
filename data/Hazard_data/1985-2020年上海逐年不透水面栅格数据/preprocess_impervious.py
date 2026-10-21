#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
不透水面数据预处理脚本
========================================================
将 GAIA (Global Artificial Impervious Area) 全球30米分辨率
逐年不透水面栅格数据裁剪到上海市范围，并重采样到模型网格分辨率(0.01°≈1km)。

输入:
  1985-2020年全球30米分辨率逐年不透水面栅格数据/
    {year}/{year}/GAIA_{year}_120_35.tif   (覆盖上海的瓦片)

  GAIA数据说明:
    - 原始分辨率: ~30m (0.000269°)
    - CRS: EPSG:4326
    - 像素值: 0=非不透水面, 1=不透水面 (binary mask)
    - 每个瓦片覆盖5°×5°

输出:
  impervious_shanghai/
    impervious_ratio_{year}.tif   裁剪+重采样(0.01°)后的上海不透水面比例
                                   值域: 0.0 ~ 1.0 (面积占比)

与模型的对接:
  - 输出与 typhoon_risk_reproduction_v3.py 中的网格对齐:
    SH_BOUNDS = (120.85, 30.65, 122.00, 31.90)
    GRID_RES  = 0.01°
  - 模型中通过 load_impervious_surface() 函数读取本脚本的输出

可独立运行:
  python preprocess_impervious.py
========================================================
"""

import os
import sys
import glob
import numpy as np

# GDAL_DATA 环境变量设置 (需在 import rasterio 之前)
_GDAL_DATA_CANDIDATE = r'C:\Users\Jack\miniforge3\envs\climada_env\Library\share\gdal'
if os.path.isdir(_GDAL_DATA_CANDIDATE):
    os.environ['GDAL_DATA'] = _GDAL_DATA_CANDIDATE

import rasterio
from rasterio.windows import from_bounds
from rasterio.transform import from_bounds as transform_from_bounds
from rasterio.enums import Resampling

# ============================================================
# 配置参数 — 与模型 typhoon_risk_reproduction_v3.py 保持一致
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 上海边界 (与模型完全一致)
SH_BOUNDS = (120.85, 30.65, 122.00, 31.90)  # (lon_min, lat_min, lon_max, lat_max)
LON_MIN, LAT_MIN, LON_MAX, LAT_MAX = SH_BOUNDS

# 目标网格分辨率 (与模型完全一致, 度)
GRID_RES = 0.01

# GAIA 瓦片命名: GAIA_{year}_{lon}_{lat}.tif
# 上海 (lon~120-122, lat~30.65-31.9) 落在 tile 120_35 内
# (tile bounds: lon 120-125, lat 30-35)
GAIA_TILE_LON = 120
GAIA_TILE_LAT = 35

# 可用年份 (数据为每5年一期)
AVAILABLE_YEARS = [1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020]

# 输出目录
OUTPUT_DIR = os.path.join(SCRIPT_DIR, '1985-2020年上海逐年不透水面栅格数据')

# ============================================================
# 核心处理函数
# ============================================================

def get_tile_path(year):
    """获取指定年份覆盖上海的 GAIA 瓦片路径"""
    tile_name = f'GAIA_{year}_{GAIA_TILE_LON}_{GAIA_TILE_LAT}.tif'
    path = os.path.join(SCRIPT_DIR, str(year), str(year), tile_name)
    if not os.path.exists(path):
        raise FileNotFoundError(f'[ERROR] 找不到 GAIA 瓦片: {path}')
    return path


def clip_and_resample(tile_path, year):
    """
    从全球30m瓦片中裁剪上海范围，并通过区域平均重采样到0.01°网格。
    
    原理:
    - 原始数据为 binary (0/1)，30m分辨率
    - 在0.01°(~1km)网格内包含约 37×37 ≈ 1369 个原始像素
    - 对这些像素取均值 → 得到不透水面面积比例 (0.0 ~ 1.0)
    - 使用 rasterio.read() 的 out_shape + Resampling.average 实现高效重采样
    
    Returns:
        np.ndarray: shape = (n_lat, n_lon)，值为不透水面比例
    """
    with rasterio.open(tile_path) as src:
        # 计算裁剪窗口 (基于上海边界)
        window = from_bounds(LON_MIN, LAT_MIN, LON_MAX, LAT_MAX, src.transform)
        
        # 先读取上海范围的原始分辨率数据
        data_raw = src.read(1, window=window).astype(np.float32)
        
        # 计算目标网格尺寸
        n_lon = int(round((LON_MAX - LON_MIN) / GRID_RES))
        n_lat = int(round((LAT_MAX - LAT_MIN) / GRID_RES))
        
        print(f'  原始裁剪区域形状: {data_raw.shape} (lat×lon pixels)')
        print(f'  目标网格形状: ({n_lat}, {n_lon}) (lat×lon cells)')
        print(f'  原始→目标聚合比: ~{data_raw.shape[0]/n_lat:.0f}×{data_raw.shape[1]/n_lon:.0f} pixels/cell')
        
    # 方法: 手动区域平均 (更准确，因为 binary 数据的 average resampling 
    #        在某些 GDAL 版本中可能有边界效应)
    # 先将原始数据划分为 n_lat × n_lon 个块，每块取均值
    raw_h, raw_w = data_raw.shape
    block_h = raw_h / n_lat   # 每个目标格点包含的原始像素行数
    block_w = raw_w / n_lon   # 每个目标格点包含的原始像素列数
    
    result = np.full((n_lat, n_lon), np.nan, dtype=np.float32)
    
    for i in range(n_lat):
        r0 = int(round(i * block_h))
        r1 = int(round((i + 1) * block_h))
        for j in range(n_lon):
            c0 = int(round(j * block_w))
            c1 = int(round((j + 1) * block_w))
            block = data_raw[r0:r1, c0:c1]
            if block.size > 0:
                result[i, j] = block.mean()
    
    # 统计信息
    valid = ~np.isnan(result)
    print(f'  不透水面比例统计: min={result[valid].min():.4f}, '
          f'max={result[valid].max():.4f}, mean={result[valid].mean():.4f}')
    print(f'  不透水面覆盖率>50%的网格数: {(result[valid] > 0.5).sum()}/{valid.sum()}')
    
    return result


def write_output(data_2d, year, n_lat, n_lon):
    """将重采样结果写为 GeoTIFF"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f'impervious_ratio_{year}.tif')
    
    # 构建 transform: 与模型网格对齐
    # 注意: GeoTIFF 的行方向是从北向南（纬度递减）
    transform = transform_from_bounds(LON_MIN, LAT_MIN, LON_MAX, LAT_MAX, n_lon, n_lat)
    
    out_data = np.where(np.isfinite(data_2d), data_2d, -9999.0).astype(np.float32)
    
    with rasterio.open(
        out_path, 'w', driver='GTiff',
        height=n_lat, width=n_lon,
        count=1, dtype='float32',
        crs='EPSG:4326',
        transform=transform,
        nodata=-9999.0,
        compress='lzw',
    ) as dst:
        dst.write(out_data, 1)
    
    print(f'  输出: {out_path}')
    return out_path


def process_year(year):
    """处理单年数据"""
    print(f'\n[{year}] 处理 GAIA 不透水面数据...')
    tile_path = get_tile_path(year)
    print(f'  输入瓦片: {os.path.basename(tile_path)}')
    
    data = clip_and_resample(tile_path, year)
    
    n_lat, n_lon = data.shape
    write_output(data, year, n_lat, n_lon)
    
    return data


def main():
    """主函数: 处理所有可用年份"""
    print('=' * 60)
    print('GAIA 不透水面数据预处理 → 上海市范围')
    print('=' * 60)
    print(f'上海边界: lon [{LON_MIN}, {LON_MAX}], lat [{LAT_MIN}, {LAT_MAX}]')
    print(f'目标分辨率: {GRID_RES}° (~{GRID_RES * 111:.1f} km)')
    print(f'输出目录: {OUTPUT_DIR}')
    print(f'待处理年份: {AVAILABLE_YEARS}')
    
    results = {}
    for year in AVAILABLE_YEARS:
        try:
            results[year] = process_year(year)
        except FileNotFoundError as e:
            print(f'  !! 跳过: {e}')
    
    # 输出时序变化总结
    if len(results) >= 2:
        print('\n' + '=' * 60)
        print('上海不透水面时序变化总结')
        print('=' * 60)
        for year, data in sorted(results.items()):
            valid = ~np.isnan(data)
            mean_ratio = data[valid].mean()
            high_ratio = (data[valid] > 0.5).sum() / valid.sum() * 100
            print(f'  {year}: 平均不透水面比例={mean_ratio:.4f}, '
                  f'高密度(>50%)格点占比={high_ratio:.1f}%')
    
    print('\n[DONE] 预处理完成，输出文件在:', OUTPUT_DIR)


if __name__ == '__main__':
    main()
