# preprocess_clip_sla.py
# 将全球逐月海平面高度NetCDF数据裁剪到上海市行政区划范围，并转换为Excel格式
# 数据频率：月度；分辨率：0.125°；不做插值、不统一分辨率
# 注意：netCDF4不支持含中文字符的路径，故使用临时文件中转

import os
import re
import shutil
import tempfile
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.transform import from_bounds
from rasterio.mask import mask as rasterio_mask
import netCDF4

# ========== 参数设置 ==========
SHP_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..', 'data',
    '我国乡镇（街道）行政区划数据', '2021年我国乡镇（街道）边界数据.shp'
)
SRC_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..', 'data',
    'Hazard_data', '1993-2023年全球逐月海平面高度数据', '逐月'
)
OUT_DIR = os.path.dirname(__file__)
VARIABLE_NAME = 'sla'
OUT_EXCEL = os.path.join(OUT_DIR, 'sla_shanghai.xlsx')

# 上海bbox（用于从全球网格预筛选，加大缓冲以确保覆盖）
SH_LON_MIN, SH_LON_MAX = 120.5, 122.5
SH_LAT_MIN, SH_LAT_MAX = 30.3, 32.2

# ========== 读取上海行政边界 ==========
print("读取上海市行政边界...")
gdf = gpd.read_file(SHP_PATH)
shanghai = gdf[gdf['省'] == '上海市'].dissolve()
shanghai_geom = shanghai.geometry.values
print(f"上海边界范围: {shanghai.total_bounds}")

# ========== 获取所有NC文件 ==========
nc_files = sorted([
    f for f in os.listdir(SRC_DIR)
    if f.endswith('.nc') and f.startswith('dt_global_allsat_msla_h_')
])
print(f"共 {len(nc_files)} 个源文件待处理")

# 创建临时目录（避免netCDF4的中文路径问题）
tmp_dir = tempfile.mkdtemp(prefix='sla_clip_')
print(f"临时目录: {tmp_dir}")

all_records = []
try:
    for i, nc_name in enumerate(nc_files):
        # 从文件名提取日期: dt_global_allsat_msla_h_yYYYY_mMM.nc → YYYY-MM
        m = re.search(r'y(\d{4})_m(\d{2})', nc_name)
        if not m:
            print(f"  跳过无法解析的文件: {nc_name}")
            continue
        date_str = f"{m.group(1)}-{m.group(2)}"

        # 1) 拷贝NC到临时目录（绕过中文路径问题）
        src_nc = os.path.join(SRC_DIR, nc_name)
        tmp_nc = os.path.join(tmp_dir, nc_name)
        shutil.copy2(src_nc, tmp_nc)

        # 2) 读取NC并提取上海区域
        ds = netCDF4.Dataset(tmp_nc)
        lat_all = ds.variables['latitude'][:]
        lon_all = ds.variables['longitude'][:]
        sla_all = ds.variables['sla'][0, :, :]  # shape: (lat, lon)

        # 筛选上海bbox区域
        lat_mask = (lat_all >= SH_LAT_MIN) & (lat_all <= SH_LAT_MAX)
        lon_mask = (lon_all >= SH_LON_MIN) & (lon_all <= SH_LON_MAX)
        lat_sub = lat_all[lat_mask]
        lon_sub = lon_all[lon_mask]
        sla_sub = sla_all[np.ix_(lat_mask, lon_mask)]

        ds.close()
        os.remove(tmp_nc)

        if len(lat_sub) == 0 or len(lon_sub) == 0:
            print(f"  {date_str}: 上海区域无数据，跳过")
            continue

        # 3) 构造临时TIF用于rasterio mask
        # 注意：lat从北到南排列
        lat_sorted = np.sort(lat_sub)[::-1]  # 确保降序（北→南）
        lon_sorted = np.sort(lon_sub)
        # 如果lat已经是降序，直接用；否则翻转sla数组
        if lat_sub[0] > lat_sub[-1]:
            sla_oriented = sla_sub
        else:
            sla_oriented = sla_sub[::-1, :]
            lat_sorted = lat_sub[::-1]

        res_lat = abs(lat_sorted[0] - lat_sorted[1]) if len(lat_sorted) > 1 else 0.125
        res_lon = abs(lon_sorted[1] - lon_sorted[0]) if len(lon_sorted) > 1 else 0.125

        transform = from_bounds(
            lon_sorted[0] - res_lon / 2,
            lat_sorted[-1] - res_lat / 2,
            lon_sorted[-1] + res_lon / 2,
            lat_sorted[0] + res_lat / 2,
            len(lon_sorted),
            len(lat_sorted)
        )

        # 处理masked array
        sla_data = np.ma.filled(sla_oriented, fill_value=np.nan).astype(np.float32)

        tmp_tif = os.path.join(tmp_dir, f'sla_{date_str}.tif')
        meta = {
            'driver': 'GTiff',
            'height': len(lat_sorted),
            'width': len(lon_sorted),
            'count': 1,
            'dtype': 'float32',
            'crs': 'EPSG:4326',
            'transform': transform,
            'nodata': np.nan
        }
        with rasterio.open(tmp_tif, 'w', **meta) as dst:
            dst.write(sla_data[np.newaxis, :, :])

        # 4) 用上海边界裁剪
        with rasterio.open(tmp_tif) as src:
            out_image, out_transform = rasterio_mask(
                src, shanghai_geom, crop=True, nodata=np.nan, all_touched=True
            )
            out_meta = src.meta.copy()
            out_meta.update({
                'height': out_image.shape[1],
                'width': out_image.shape[2],
                'transform': out_transform,
                'nodata': np.nan
            })
        os.remove(tmp_tif)

        # 5) 保存裁剪后的TIF
        out_tif = os.path.join(OUT_DIR, f'sla_{date_str}.tif')
        with rasterio.open(out_tif, 'w', **out_meta) as dst:
            dst.write(out_image)

        # 6) 收集有效像素用于Excel
        data = out_image[0]
        rows, cols = np.where(~np.isnan(data))
        for r, c in zip(rows, cols):
            lon = out_transform.c + (c + 0.5) * out_transform.a
            lat = out_transform.f + (r + 0.5) * out_transform.e
            all_records.append({
                'date': date_str,
                'lon': round(float(lon), 6),
                'lat': round(float(lat), 6),
                VARIABLE_NAME: round(float(data[r, c]), 6)
            })

        if (i + 1) % 50 == 0 or (i + 1) == len(nc_files):
            print(f"  已处理 {i + 1}/{len(nc_files)}")

finally:
    # 清理临时目录
    shutil.rmtree(tmp_dir, ignore_errors=True)

# ========== 保存Excel ==========
print(f"生成Excel: {len(all_records)} 行数据...")
df = pd.DataFrame(all_records)
df.to_excel(OUT_EXCEL, index=False, engine='openpyxl')
print(f"完成! Excel已保存至: {OUT_EXCEL}")
print(f"TIF文件已保存至: {OUT_DIR}")
