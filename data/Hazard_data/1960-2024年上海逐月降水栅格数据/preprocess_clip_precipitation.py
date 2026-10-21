# preprocess_clip_precipitation.py
# 将全国逐月降水栅格数据裁剪到上海市行政区划范围，并转换为Excel格式
# 数据频率：月度；分辨率：0.1°；不做插值、不统一分辨率

import os
import re
import glob
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.mask import mask as rasterio_mask

# ========== 参数设置 ==========
SHP_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..', 'data',
    '我国乡镇（街道）行政区划数据', '2021年我国乡镇（街道）边界数据.shp'
)
SRC_DIR = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..', 'data',
    'Hazard_data', '1960-2024年我国0.1°分辨率逐日逐月逐年降水栅格数据', '逐月'
)
OUT_DIR = os.path.dirname(__file__)
VARIABLE_NAME = 'precipitation'
OUT_EXCEL = os.path.join(OUT_DIR, 'precipitation_shanghai.xlsx')

# ========== 读取上海行政边界 ==========
print("读取上海市行政边界...")
gdf = gpd.read_file(SHP_PATH)
shanghai = gdf[gdf['省'] == '上海市'].dissolve()
shanghai_geom = shanghai.geometry.values
print(f"上海边界范围: {shanghai.total_bounds}")

# ========== 裁剪所有月度降水TIF ==========
tif_files = sorted(glob.glob(os.path.join(SRC_DIR, 'prec_*.tif')))
print(f"共 {len(tif_files)} 个源文件待处理")

all_records = []
for i, tif_path in enumerate(tif_files):
    fname = os.path.basename(tif_path)
    # 从文件名提取日期: prec_YYYY_MM.tif → YYYY-MM
    m = re.search(r'prec_(\d{4})_(\d{2})', fname)
    if not m:
        print(f"  跳过无法解析的文件: {fname}")
        continue
    date_str = f"{m.group(1)}-{m.group(2)}"

    with rasterio.open(tif_path) as src:
        out_image, out_transform = rasterio_mask(
            src, shanghai_geom, crop=True, nodata=np.nan, all_touched=True
        )
        out_meta = src.meta.copy()
        out_meta.update({
            'driver': 'GTiff',
            'height': out_image.shape[1],
            'width': out_image.shape[2],
            'transform': out_transform,
            'nodata': np.nan,
            'dtype': 'float32'
        })

    # 保存裁剪后的TIF
    out_tif = os.path.join(OUT_DIR, f'prec_{date_str}.tif')
    with rasterio.open(out_tif, 'w', **out_meta) as dst:
        dst.write(out_image.astype(np.float32))

    # 收集有效像素用于Excel
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

    if (i + 1) % 100 == 0 or (i + 1) == len(tif_files):
        print(f"  已处理 {i + 1}/{len(tif_files)}")

# ========== 保存Excel ==========
print(f"生成Excel: {len(all_records)} 行数据...")
df = pd.DataFrame(all_records)
df.to_excel(OUT_EXCEL, index=False, engine='openpyxl')
print(f"完成! Excel已保存至: {OUT_EXCEL}")
print(f"TIF文件已保存至: {OUT_DIR}")
