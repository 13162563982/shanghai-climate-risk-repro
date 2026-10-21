#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
暴露度数据预处理脚本 — 房屋 & 人口
========================================================
将全国尺度的房屋和人口数据截取到上海地区，
已经是上海数据的文件夹直接复制。

处理清单:
  房屋 (源目录名 → 输出目录名):
    1. 1975-2020年我国城市建成区矢量数据   → 1975-2020年上海城市建成区矢量数据  (空间裁剪)
    2. 2011-2025年我国地级市逐月二手房房价数据 → 2011-2025年上海逐月二手房房价数据  (属性筛选 省名=上海市)
    3. 2015-2025年我国逐月区县二手房房价数据   → 2015-2025年上海逐月区县二手房房价数据  (属性筛选 省名=上海市)
    4. 2024年我国多属性建筑矢量数据         → 2024年上海多属性建筑矢量数据  (已有上海子目录, 直接复制)
    5. 上海小区数据（链家）                → 上海小区数据（链家）  (直接复制)
    6. 上海小区数据（高德）                → 上海小区数据（高德）  (直接复制)

  人口 (源目录名 → 输出目录名):
    1. 2000-2024年1km精度人口分布栅格数据   → 2000-2024年上海1km精度人口分布栅格数据  (已是上海数据, 直接复制)
    2. 2000-2024年我国逐年乡镇人口数量数据   → 2000-2024年上海逐年乡镇人口数量数据  (属性筛选 Province=上海市)
    3. 上海第七次人口普查街道数据           → 上海第七次人口普查街道数据  (直接复制)
    4. 上海第五次人口普查街道数据           → 上海第五次人口普查街道数据  (直接复制)
    5. 上海第六次人口普查街道数据           → 上海第六次人口普查街道数据  (直接复制)
    6. 我国区县层级的人口受教育情况-五六七普人口 → 上海区县层级的人口受教育情况-五六七普人口  (按行提取上海数据)

输入: data/Exposure_data/
输出: model_房地产风险_v6/data/Exposure_data/

可独立运行:
  python preprocess_exposure.py
========================================================
"""

import os
import sys
import glob
import shutil
import numpy as np
import pandas as pd
import geopandas as gpd

# GDAL_DATA 环境变量
_GDAL_DATA_CANDIDATE = r'C:\Users\Jack\miniforge3\envs\climada_env\Library\share\gdal'
if os.path.isdir(_GDAL_DATA_CANDIDATE):
    os.environ['GDAL_DATA'] = _GDAL_DATA_CANDIDATE

# ============================================================
# 路径配置
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..', '..'))

SRC_EXPOSURE = os.path.join(PROJECT_ROOT, 'data', 'Exposure_data')
DST_EXPOSURE = SCRIPT_DIR  # model_房地产风险_v6/data/Exposure_data

# 上海行政边界 shapefile (用于空间裁剪)
SH_BOUNDARY_SHP = os.path.join(
    PROJECT_ROOT, 'data', '我国乡镇（街道）行政区划数据',
    '2021年我国乡镇（街道）边界数据.shp'
)

# ============================================================
# 工具函数
# ============================================================

def ensure_dir(path):
    """确保目录存在"""
    os.makedirs(path, exist_ok=True)


def copy_folder(src, dst):
    """复制整个文件夹 (若目标已存在则跳过)"""
    if os.path.exists(dst):
        print(f"  [跳过] 目标已存在: {os.path.basename(dst)}")
        return
    print(f"  [复制] {os.path.basename(src)} -> {os.path.basename(dst)}")
    shutil.copytree(src, dst)
    print(f"  [完成]")


def get_shanghai_boundary():
    """读取上海市行政边界并融合为单个多边形"""
    print("  读取上海行政边界...")
    gdf = gpd.read_file(SH_BOUNDARY_SHP)
    sh = gdf[gdf['省'] == '上海市']
    sh_dissolved = sh.dissolve()
    print(f"  上海边界: {len(sh)} 个街道/乡镇, CRS={sh_dissolved.crs}")
    return sh_dissolved


# ============================================================
# 房屋数据处理
# ============================================================

def process_housing_built_up_area():
    """1. 城市建成区矢量数据 → 空间裁剪到上海"""
    src_folder_name = '1975-2020年我国城市建成区矢量数据'
    dst_folder_name = '1975-2020年上海城市建成区矢量数据'
    src_dir = os.path.join(SRC_EXPOSURE, '房屋', src_folder_name)
    dst_dir = os.path.join(DST_EXPOSURE, '房屋', dst_folder_name)
    ensure_dir(dst_dir)

    print(f"\n{'='*60}")
    print(f"处理: {src_folder_name} -> {dst_folder_name}")
    print(f"{'='*60}")

    # 获取上海边界
    sh_boundary = get_shanghai_boundary()

    # 获取所有 shp 文件
    shp_files = sorted(glob.glob(os.path.join(src_dir, '*_shp_yzx.shp')))
    print(f"  找到 {len(shp_files)} 个年份 shapefile")

    for shp_path in shp_files:
        basename = os.path.basename(shp_path)
        year = basename.split('_')[0]
        print(f"  处理 {year} 年...")

        # 读取全国建成区
        gdf = gpd.read_file(shp_path)

        # 将上海边界投影到建成区的 CRS
        sh_reproj = sh_boundary.to_crs(gdf.crs)

        # 空间裁剪
        clipped = gpd.clip(gdf, sh_reproj)

        if len(clipped) == 0 or clipped.geometry.is_empty.all():
            print(f"    [警告] {year} 年裁剪结果为空")
            continue

        # 输出文件名: {year}_上海_shp.shp
        out_basename = f'{year}_上海_shp.shp'
        out_path = os.path.join(dst_dir, out_basename)
        clipped.to_file(out_path, encoding='utf-8')
        print(f"    保存: {out_basename}, {len(clipped)} 个要素")

    # 复制说明文件
    for ext in ['pdf', 'txt']:
        for f in glob.glob(os.path.join(src_dir, f'*.{ext}')):
            shutil.copy2(f, dst_dir)


def process_housing_city_price():
    """2. 地级市逐月二手房房价 → 筛选上海"""
    src_folder_name = '2011-2025年我国地级市逐月二手房房价数据'
    dst_folder_name = '2011-2025年上海逐月二手房房价数据'
    src_dir = os.path.join(SRC_EXPOSURE, '房屋', src_folder_name)
    dst_dir = os.path.join(DST_EXPOSURE, '房屋', dst_folder_name)
    ensure_dir(dst_dir)

    print(f"\n{'='*60}")
    print(f"处理: {src_folder_name} -> {dst_folder_name}")
    print(f"{'='*60}")

    # Excel
    src_xlsx = os.path.join(src_dir, 'excel格式的数据', '二手房价.xlsx')
    dst_xlsx_dir = os.path.join(dst_dir, 'excel格式的数据')
    ensure_dir(dst_xlsx_dir)

    df = pd.read_excel(src_xlsx)
    df_sh = df[df['省名'] == '上海市'].copy()
    out_xlsx = os.path.join(dst_xlsx_dir, '上海二手房价.xlsx')
    df_sh.to_excel(out_xlsx, index=False)
    print(f"  Excel: {len(df_sh)} 行上海数据")

    # Shapefile
    src_shp = os.path.join(src_dir, 'shp格式的数据', '二手房价.shp')
    dst_shp_dir = os.path.join(dst_dir, 'shp格式的数据')
    ensure_dir(dst_shp_dir)

    gdf = gpd.read_file(src_shp)
    # 检查列名, 筛选上海
    for col in gdf.columns:
        if gdf[col].dtype == 'object':
            match = gdf[gdf[col].str.contains('上海', na=False)]
            if len(match) > 0:
                gdf_sh = match
                print(f"  SHP: 通过列 [{col}] 筛选, {len(gdf_sh)} 个要素")
                break
    else:
        # 如果属性过滤找不到, 用空间裁剪
        sh_boundary = get_shanghai_boundary()
        sh_reproj = sh_boundary.to_crs(gdf.crs)
        gdf_sh = gpd.clip(gdf, sh_reproj)
        print(f"  SHP: 空间裁剪, {len(gdf_sh)} 个要素")

    out_shp = os.path.join(dst_shp_dir, '上海二手房价.shp')
    gdf_sh.to_file(out_shp, encoding='utf-8')

    # 说明文件
    for f in glob.glob(os.path.join(src_dir, '*.pdf')):
        shutil.copy2(f, dst_dir)


def process_housing_district_price():
    """3. 区县逐月二手房房价 → 筛选上海"""
    src_folder_name = '2015-2025年我国逐月区县二手房房价数据'
    dst_folder_name = '2015-2025年上海逐月区县二手房房价数据'
    src_dir = os.path.join(SRC_EXPOSURE, '房屋', src_folder_name)
    dst_dir = os.path.join(DST_EXPOSURE, '房屋', dst_folder_name)
    ensure_dir(dst_dir)

    print(f"\n{'='*60}")
    print(f"处理: {src_folder_name} -> {dst_folder_name}")
    print(f"{'='*60}")

    # Excel
    src_xlsx = os.path.join(src_dir, 'excel格式的数据', '二手房价.xlsx')
    dst_xlsx_dir = os.path.join(dst_dir, 'excel格式的数据')
    ensure_dir(dst_xlsx_dir)

    df = pd.read_excel(src_xlsx)
    df_sh = df[df['省名'] == '上海市'].copy()
    out_xlsx = os.path.join(dst_xlsx_dir, '上海二手房价.xlsx')
    df_sh.to_excel(out_xlsx, index=False)
    print(f"  Excel: {len(df_sh)} 行上海数据 (16个区)")

    # Shapefile
    src_shp = os.path.join(src_dir, 'shp格式的数据', '二手房价.shp')
    dst_shp_dir = os.path.join(dst_dir, 'shp格式的数据')
    ensure_dir(dst_shp_dir)

    gdf = gpd.read_file(src_shp)
    for col in gdf.columns:
        if gdf[col].dtype == 'object':
            match = gdf[gdf[col].str.contains('上海', na=False)]
            if len(match) > 0:
                gdf_sh = match
                print(f"  SHP: 通过列 [{col}] 筛选, {len(gdf_sh)} 个要素")
                break
    else:
        sh_boundary = get_shanghai_boundary()
        sh_reproj = sh_boundary.to_crs(gdf.crs)
        gdf_sh = gpd.clip(gdf, sh_reproj)
        print(f"  SHP: 空间裁剪, {len(gdf_sh)} 个要素")

    out_shp = os.path.join(dst_shp_dir, '上海二手房价.shp')
    gdf_sh.to_file(out_shp, encoding='utf-8')

    for f in glob.glob(os.path.join(src_dir, '*.pdf')):
        shutil.copy2(f, dst_dir)


def process_housing_building_vector():
    """4. 多属性建筑矢量数据 → 已有上海子目录, 复制"""
    src_folder_name = '2024年我国多属性建筑矢量数据'
    dst_folder_name = '2024年上海多属性建筑矢量数据'
    src_shanghai = os.path.join(SRC_EXPOSURE, '房屋', src_folder_name, 'shanghai', '上海市')
    dst_dir = os.path.join(DST_EXPOSURE, '房屋', dst_folder_name)

    print(f"\n{'='*60}")
    print(f"处理: {src_folder_name} -> {dst_folder_name}")
    print(f"{'='*60}")

    copy_folder(src_shanghai, dst_dir)


def process_housing_lianjia():
    """5. 链家小区数据 → 直接复制"""
    folder_name = '上海小区数据（链家）'
    src_dir = os.path.join(SRC_EXPOSURE, '房屋', folder_name)
    dst_dir = os.path.join(DST_EXPOSURE, '房屋', folder_name)

    print(f"\n{'='*60}")
    print(f"处理: {folder_name}")
    print(f"{'='*60}")

    copy_folder(src_dir, dst_dir)


def process_housing_gaode():
    """6. 高德小区数据 → 直接复制"""
    folder_name = '上海小区数据（高德）'
    src_dir = os.path.join(SRC_EXPOSURE, '房屋', folder_name)
    dst_dir = os.path.join(DST_EXPOSURE, '房屋', folder_name)

    print(f"\n{'='*60}")
    print(f"处理: {folder_name}")
    print(f"{'='*60}")

    copy_folder(src_dir, dst_dir)


# ============================================================
# 人口数据处理
# ============================================================

def process_pop_raster():
    """1. 1km人口栅格 → 已是上海数据, 复制"""
    src_folder_name = '2000-2024年1km精度人口分布栅格数据'
    dst_folder_name = '2000-2024年上海1km精度人口分布栅格数据'
    src_data = os.path.join(
        SRC_EXPOSURE, '人口', src_folder_name,
        '4.分城市的数据_立方数据学社', '【立方数据学社】上海市'
    )
    dst_dir = os.path.join(DST_EXPOSURE, '人口', dst_folder_name)

    print(f"\n{'='*60}")
    print(f"处理: {src_folder_name} -> {dst_folder_name}")
    print(f"{'='*60}")

    copy_folder(src_data, dst_dir)


def process_pop_township():
    """2. 乡镇人口数量数据 → 属性筛选 Province=上海市"""
    src_folder_name = '2000-2024年我国逐年乡镇人口数量数据'
    dst_folder_name = '2000-2024年上海逐年乡镇人口数量数据'
    src_dir = os.path.join(SRC_EXPOSURE, '人口', src_folder_name)
    dst_dir = os.path.join(DST_EXPOSURE, '人口', dst_folder_name)
    ensure_dir(dst_dir)

    print(f"\n{'='*60}")
    print(f"处理: {src_folder_name} -> {dst_folder_name}")
    print(f"{'='*60}")

    # Excel
    src_xlsx = os.path.join(src_dir, 'excel格式的数据', '乡镇层级_人口数.xlsx')
    dst_xlsx_dir = os.path.join(dst_dir, 'excel格式的数据')
    ensure_dir(dst_xlsx_dir)

    df = pd.read_excel(src_xlsx)
    df_sh = df[df['Province'] == '上海市'].copy()
    out_xlsx = os.path.join(dst_xlsx_dir, '上海乡镇层级_人口数.xlsx')
    df_sh.to_excel(out_xlsx, index=False)
    print(f"  Excel: {len(df_sh)} 行上海乡镇数据")

    # Shapefile
    src_shp = os.path.join(src_dir, 'shp格式的数据', '乡镇层级_人口数.shp')
    dst_shp_dir = os.path.join(dst_dir, 'shp格式的数据')
    ensure_dir(dst_shp_dir)

    gdf = gpd.read_file(src_shp)
    # 尝试属性过滤
    filtered = False
    for col in gdf.columns:
        if gdf[col].dtype == 'object':
            match = gdf[gdf[col].str.contains('上海', na=False)]
            if len(match) > 0:
                gdf_sh = match
                print(f"  SHP: 通过列 [{col}] 筛选, {len(gdf_sh)} 个要素")
                filtered = True
                break
    if not filtered:
        sh_boundary = get_shanghai_boundary()
        sh_reproj = sh_boundary.to_crs(gdf.crs)
        gdf_sh = gpd.clip(gdf, sh_reproj)
        print(f"  SHP: 空间裁剪, {len(gdf_sh)} 个要素")

    out_shp = os.path.join(dst_shp_dir, '上海乡镇层级_人口数.shp')
    gdf_sh.to_file(out_shp, encoding='utf-8')

    for f in glob.glob(os.path.join(src_dir, '*.pdf')):
        shutil.copy2(f, dst_dir)


def process_pop_census_7():
    """3. 第七次人口普查 → 直接复制"""
    folder_name = '上海第七次人口普查街道数据'
    src_dir = os.path.join(SRC_EXPOSURE, '人口', folder_name)
    dst_dir = os.path.join(DST_EXPOSURE, '人口', folder_name)

    print(f"\n{'='*60}")
    print(f"处理(直接复制): {folder_name}")
    print(f"{'='*60}")

    copy_folder(src_dir, dst_dir)


def process_pop_census_5():
    """4. 第五次人口普查 → 直接复制"""
    folder_name = '上海第五次人口普查街道数据'
    src_dir = os.path.join(SRC_EXPOSURE, '人口', folder_name)
    dst_dir = os.path.join(DST_EXPOSURE, '人口', folder_name)

    print(f"\n{'='*60}")
    print(f"处理(直接复制): {folder_name}")
    print(f"{'='*60}")

    copy_folder(src_dir, dst_dir)


def process_pop_census_6():
    """5. 第六次人口普查 → 直接复制"""
    folder_name = '上海第六次人口普查街道数据'
    src_dir = os.path.join(SRC_EXPOSURE, '人口', folder_name)
    dst_dir = os.path.join(DST_EXPOSURE, '人口', folder_name)

    print(f"\n{'='*60}")
    print(f"处理(直接复制): {folder_name}")
    print(f"{'='*60}")

    copy_folder(src_dir, dst_dir)


def process_pop_education():
    """6. 区县受教育情况 → 按行提取上海数据"""
    src_folder_name = '我国区县层级的人口受教育情况-五六七普人口'
    dst_folder_name = '上海区县层级的人口受教育情况-五六七普人口'
    src_sub = '【五六七普人口数据】我国区县层级的人口受教育情况'
    dst_sub = '【五六七普人口数据】上海区县层级的人口受教育情况'
    src_dir = os.path.join(SRC_EXPOSURE, '人口', src_folder_name, src_sub)
    dst_dir = os.path.join(DST_EXPOSURE, '人口', dst_folder_name, dst_sub)
    ensure_dir(dst_dir)

    print(f"\n{'='*60}")
    print(f"处理: {src_folder_name} -> {dst_folder_name}")
    print(f"{'='*60}")

    # 省级行政区名, 用于判断上海数据的结束边界
    PROVINCES = [
        '北京市', '天津市', '河北省', '山西省', '内蒙古自治区',
        '辽宁省', '吉林省', '黑龙江省', '上海市', '江苏省',
        '浙江省', '安徽省', '福建省', '江西省', '山东省',
        '河南省', '湖北省', '湖南省', '广东省', '广西壮族自治区',
        '海南省', '重庆市', '四川省', '贵州省', '云南省',
        '西藏自治区', '陕西省', '甘肃省', '青海省', '宁夏回族自治区',
        '新疆维吾尔自治区', '合计',
    ]

    def extract_shanghai_rows(file_path):
        """从人口教育 Excel 中提取表头 + 上海数据行"""
        df = pd.read_excel(file_path, header=None)

        # 找到 "上海市" 所在行
        col0 = df[0].astype(str)
        sh_idx = col0[col0 == '上海市'].index
        if len(sh_idx) == 0:
            print(f"  [警告] 未找到上海市: {os.path.basename(file_path)}")
            return None

        sh_start = sh_idx[0]

        # 找到下一个省级行政区 (上海之后的)
        sh_end = len(df)
        for i in range(sh_start + 1, len(df)):
            val = str(df.iloc[i, 0]).strip()
            if val in PROVINCES and val != '上海市':
                sh_end = i
                break
            # 遇到空行后又遇到省级名称的情况
            if pd.isna(df.iloc[i, 0]) and i > sh_start + 2:
                # 检查下一个非空行是否是其他省
                for j in range(i, min(i + 3, len(df))):
                    next_val = str(df.iloc[j, 0]).strip()
                    if next_val in PROVINCES and next_val != '上海市':
                        sh_end = i
                        break
                if sh_end != len(df):
                    break

        # 提取表头行 (前几行是标题)
        # 找到第一个省级名称行的位置作为数据起始
        data_start = 0
        for i in range(len(df)):
            val = str(df.iloc[i, 0]).strip()
            if val in PROVINCES:
                data_start = i
                break

        # 表头 = 第0行到data_start之前
        header = df.iloc[:data_start]
        # 上海数据
        shanghai_data = df.iloc[sh_start:sh_end]

        result = pd.concat([header, shanghai_data], ignore_index=True)
        return result

    # 处理三个人口普查文件
    census_files = [
        ('【七普】人口受教育情况.xlsx', '【七普】人口受教育情况.xlsx'),
        ('【五普】人口受教育情况.XLS', '【五普】人口受教育情况.xlsx'),  # 输出统一为xlsx
        ('【六普】人口受教育情况.xlsx', '【六普】人口受教育情况.xlsx'),
    ]

    for src_name, dst_name in census_files:
        src_path = os.path.join(src_dir, src_name)
        if not os.path.exists(src_path):
            print(f"  [跳过] 文件不存在: {src_name}")
            continue

        result = extract_shanghai_rows(src_path)
        if result is not None:
            out_path = os.path.join(dst_dir, dst_name)
            result.to_excel(out_path, index=False, header=False)
            n_data = len(result) - 3  # 减去表头行数 (约3行)
            print(f"  {src_name}: 提取 {n_data} 行上海数据 -> {dst_name}")

    # 复制说明文件
    for f in glob.glob(os.path.join(src_dir, '*.pdf')):
        shutil.copy2(f, dst_dir)
    # 复制上层pdf
    parent_dir = os.path.join(SRC_EXPOSURE, '人口', src_folder_name)
    parent_dst = os.path.join(DST_EXPOSURE, '人口', dst_folder_name)
    os.makedirs(parent_dst, exist_ok=True)
    for f in glob.glob(os.path.join(parent_dir, '*.pdf')):
        shutil.copy2(f, parent_dst)


# ============================================================
# 主流程
# ============================================================

def main():
    print("=" * 60)
    print("暴露度数据预处理: 房屋 & 人口 → 上海地区截取")
    print("=" * 60)
    print(f"源目录: {SRC_EXPOSURE}")
    print(f"输出目录: {DST_EXPOSURE}")
    print()

    # ---- 房屋 ----
    print("\n" + "#" * 60)
    print("# 房屋数据")
    print("#" * 60)

    process_housing_built_up_area()
    process_housing_city_price()
    process_housing_district_price()
    process_housing_building_vector()
    process_housing_lianjia()
    process_housing_gaode()

    # ---- 人口 ----
    print("\n" + "#" * 60)
    print("# 人口数据")
    print("#" * 60)

    process_pop_raster()
    process_pop_township()
    process_pop_census_7()
    process_pop_census_5()
    process_pop_census_6()
    process_pop_education()

    print("\n" + "=" * 60)
    print("全部处理完成!")
    print("=" * 60)


if __name__ == '__main__':
    main()
