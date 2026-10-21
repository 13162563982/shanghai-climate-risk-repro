# preprocess_census_5.py
# 预处理第五次人口普查街道数据 —— 处理合并单元格、多行表头
# 输入: 上海市_五普乡镇（街道）人口.xlsx (含3层合并表头, 空行分隔)
# 输出: census_5_cleaned.csv (平铺列名, 无空行, 无缺失)

import os
import openpyxl
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_XLSX = os.path.join(SCRIPT_DIR, '上海市_五普乡镇（街道）人口.xlsx')
OUT_CSV = os.path.join(SCRIPT_DIR, 'census_5_cleaned.csv')

# ========== 手工定义列名 (根据3行合并表头解析) ==========
# Row 5: 地区别 | 总人口(合并B:D) | 家庭户户数 | 家庭户总人口(合并F:H) | 分年龄人口(合并I:Q) | 居住本地户口在本地
# Row 6:        | 合计 | 男 | 女 |           | 合计 | 男 | 女 | 0-14岁(I:K) | 15-64岁(L:N) | 65岁及以上(O:Q) |
# Row 7:        |      |    |    |           |      |    |    | 小计|男|女  | 小计|男|女   | 小计|男|女       |
COLUMNS = [
    '地区',
    '总人口_合计', '总人口_男', '总人口_女',
    '家庭户户数',
    '家庭户总人口_合计', '家庭户总人口_男', '家庭户总人口_女',
    '0-14岁_小计', '0-14岁_男', '0-14岁_女',
    '15-64岁_小计', '15-64岁_男', '15-64岁_女',
    '65岁及以上_小计', '65岁及以上_男', '65岁及以上_女',
    '居住本地户口在本地',
]

print("=" * 60)
print("  预处理: 第五次人口普查街道数据")
print("=" * 60)
print(f"输入: {os.path.basename(SRC_XLSX)}")

wb = openpyxl.load_workbook(SRC_XLSX, data_only=True)
ws = wb['Sheet1']
print(f"原始: {ws.max_row} 行, {ws.max_column} 列")

# ========== 提取数据行 ==========
# 数据区域从第9行开始 (跳过表头行1-7, 空行8)
# 筛选: 列A (地区) 非空 且 列B (总人口) 非空
records = []
for row_idx in range(9, ws.max_row + 1):
    cell_a = ws.cell(row=row_idx, column=1).value
    cell_b = ws.cell(row=row_idx, column=2).value
    if cell_a is None or cell_b is None:
        continue  # 跳过空行/分隔行
    row_data = []
    for col_idx in range(1, 19):  # 18列
        val = ws.cell(row=row_idx, column=col_idx).value
        row_data.append(val)
    records.append(row_data)

print(f"提取有效数据行: {len(records)}")

df = pd.DataFrame(records, columns=COLUMNS)

# ========== 清理 ==========
# 去掉"地区"列前后空格及全角空格
df['地区'] = df['地区'].astype(str).str.strip().str.replace(r'\s+', '', regex=True)

# 数值列转为整数 (原始数据无小数)
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

# 添加行政层级列 (根据地区名称的缩进/特征判断)
def classify_level(name):
    """根据原始五普地区名推断行政层级"""
    if name in ('合计',):
        return '全市合计'
    # 原始数据中: 无缩进=区县, 有缩进=街道/乡镇, "市辖区"/"市辖县"=市辖分类
    if name in ('市辖区', '市辖县'):
        return '市辖分类'
    # 包含"区"或"县"结尾的是区县
    if name.endswith('区') or name.endswith('县'):
        return '区县'
    return '街道/乡镇'

df['行政层级'] = df['地区'].apply(classify_level)

# 添加普查标识
df['普查'] = '五普'
df['普查年份'] = 2000

# 输出
df.to_csv(OUT_CSV, index=False, encoding='utf-8-sig')
print(f"\n输出: {os.path.basename(OUT_CSV)}")
print(f"  行数: {len(df)}, 列数: {len(df.columns)}")
print(f"  行政层级分布: {df['行政层级'].value_counts().to_dict()}")
print(f"  列名: {list(df.columns)}")
print("\n数据预览 (前5行):")
print(df.head().to_string(index=False))
print("\n[完成]")
