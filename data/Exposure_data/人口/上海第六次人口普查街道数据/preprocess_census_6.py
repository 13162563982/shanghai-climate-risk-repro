# preprocess_census_6.py
# 预处理第六次人口普查街道数据 —— 处理多行表头、空行
# 输入: 上海市_六普乡镇（街道）人口.xls (4行表头, 空行分隔)
# 输出: census_6_cleaned.csv (平铺列名, 无空行, 无缺失)

import os
import xlrd
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_XLS = os.path.join(SCRIPT_DIR, '上海市_六普乡镇（街道）人口.xls')
OUT_CSV = os.path.join(SCRIPT_DIR, 'census_6_cleaned.csv')

# ========== 手工定义列名 (根据4行表头解析) ==========
# Row 1: 地区 | 总人口(B:D) | 家庭户(E) | 家庭户总人口(F:G) | 分年龄人口(H:J) | 居住本地户口在本地(K)
# Row 2:      | 合计|男|女  |           | 男|女             | 0-14岁|15-64岁|65岁及以上 |
# Row 3:      |             | 户数      |                   |       |       |           | 户口在本地
# Row 4: (空行)
COLUMNS = [
    '地区',
    '总人口_合计', '总人口_男', '总人口_女',
    '家庭户户数',
    '家庭户总人口_男', '家庭户总人口_女',
    '0-14岁', '15-64岁', '65岁及以上',
    '居住本地户口在本地',
]

print("=" * 60)
print("  预处理: 第六次人口普查街道数据")
print("=" * 60)
print(f"输入: {os.path.basename(SRC_XLS)}")

wb = xlrd.open_workbook(SRC_XLS)
ws = wb.sheet_by_index(0)
print(f"原始: {ws.nrows} 行, {ws.ncols} 列")

# ========== 提取数据行 ==========
# 数据从第5行(0-indexed: row 4)开始
records = []
for row_idx in range(4, ws.nrows):
    cell_a = ws.cell_value(row_idx, 0)
    cell_b = ws.cell_value(row_idx, 1)
    if cell_a == '' and (cell_b == '' or cell_b == 0):
        continue  # 跳过空行
    if cell_a == '':
        continue
    row_data = []
    for col_idx in range(ws.ncols):
        val = ws.cell_value(row_idx, col_idx)
        row_data.append(val if val != '' else None)
    records.append(row_data)

print(f"提取有效数据行: {len(records)}")

df = pd.DataFrame(records, columns=COLUMNS)

# ========== 清理 ==========
df['地区'] = df['地区'].astype(str).str.strip().str.replace(r'\s+', '', regex=True)

num_cols = [c for c in COLUMNS if c != '地区']
for col in num_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce')

# 检查缺失值
miss = df.isnull().sum()
miss_any = miss[miss > 0]
if len(miss_any) > 0:
    print(f"⚠ 仍有缺失的列: {dict(miss_any)}")
else:
    print("✓ 无缺失值")

# 添加行政层级列
def classify_level(name):
    if name in ('上海市',):
        return '全市合计'
    if name in ('市辖区', '县'):
        return '市辖分类'
    if name.endswith('区') or name.endswith('县'):
        return '区县'
    return '街道/乡镇'

df['行政层级'] = df['地区'].apply(classify_level)

df['普查'] = '六普'
df['普查年份'] = 2010

# 输出
df.to_csv(OUT_CSV, index=False, encoding='utf-8-sig')
print(f"\n输出: {os.path.basename(OUT_CSV)}")
print(f"  行数: {len(df)}, 列数: {len(df.columns)}")
print(f"  行政层级分布: {df['行政层级'].value_counts().to_dict()}")
print(f"  列名: {list(df.columns)}")
print("\n数据预览 (前5行):")
print(df.head().to_string(index=False))
print("\n[完成]")
