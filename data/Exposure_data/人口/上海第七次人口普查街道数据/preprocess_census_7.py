# preprocess_census_7.py
# 预处理第七次人口普查街道数据 —— 格式已较规整, 仅做标准化清理
# 输入: Excel格式的数据/上海市_七普乡镇（街道）人口.xlsx (单行表头, 无合并单元格)
# 输出: census_7_cleaned.csv (统一列名格式, 去除空白)

import os
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_XLSX = os.path.join(SCRIPT_DIR, 'Excel格式的数据', '上海市_七普乡镇（街道）人口.xlsx')
OUT_CSV = os.path.join(SCRIPT_DIR, 'census_7_cleaned.csv')

# ========== 标准化列名映射 ==========
COL_RENAME = {
    '地区': '地区',
    '总人口': '总人口_合计',
    '0-14 岁': '0-14岁',
    '15-59岁': '15-59岁',
    '60岁及以上(包括65岁及以上人口)': '60岁及以上',
    '65岁及以上': '65岁及以上',
    '居住本乡、 镇、街道， 户口在本乡、 镇、街 道': '居住本地户口在本地',
    '地区行政层级': '行政层级_原始',
    '备注': '备注',
}

print("=" * 60)
print("  预处理: 第七次人口普查街道数据")
print("=" * 60)
print(f"输入: {os.path.basename(SRC_XLSX)}")

df = pd.read_excel(SRC_XLSX)
print(f"原始: {len(df)} 行, {len(df.columns)} 列")
print(f"原始列名: {list(df.columns)}")

# ========== 重命名列 ==========
# 处理列名中可能的多余空格
df.columns = [c.strip() for c in df.columns]
rename_map = {}
for orig_col in df.columns:
    for pattern, new_name in COL_RENAME.items():
        # 去掉空格、换行后比较
        if orig_col.replace(' ', '').replace('\n', '').replace('\u3000', '') == \
           pattern.replace(' ', '').replace('\n', '').replace('\u3000', ''):
            rename_map[orig_col] = new_name
            break

df = df.rename(columns=rename_map)

# ========== 清理 ==========
df['地区'] = df['地区'].astype(str).str.strip().str.replace(r'\s+', '', regex=True)

# 删除备注列 (全为空)
if '备注' in df.columns:
    df = df.drop(columns=['备注'])

# 标准化行政层级
if '行政层级_原始' in df.columns:
    level_map = {
        '省份层级': '全市合计',
        '地级市层级': '市辖分类',
        '区县层级': '区县',
        '乡镇（街道）层级': '街道/乡镇',
    }
    df['行政层级'] = df['行政层级_原始'].map(level_map)
    df = df.drop(columns=['行政层级_原始'])

# 数值列转换
num_cols = [c for c in df.columns if c not in ('地区', '行政层级')]
for col in num_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce')

# 检查缺失值
miss = df.isnull().sum()
miss_any = miss[miss > 0]
if len(miss_any) > 0:
    print(f"⚠ 仍有缺失的列: {dict(miss_any)}")
else:
    print("✓ 无缺失值")

df['普查'] = '七普'
df['普查年份'] = 2020

# 输出
df.to_csv(OUT_CSV, index=False, encoding='utf-8-sig')
print(f"\n输出: {os.path.basename(OUT_CSV)}")
print(f"  行数: {len(df)}, 列数: {len(df.columns)}")
print(f"  行政层级分布: {df['行政层级'].value_counts().to_dict()}")
print(f"  列名: {list(df.columns)}")
print("\n数据预览 (前5行):")
print(df.head().to_string(index=False))
print("\n[完成]")
