"""
WP台风数据 → 复制到模型数据目录

功能说明：
    将IBTrACS西太平洋台风轨迹数据复制到模型工作目录。
    台风轨迹为点数据，空间筛选（仅保留影响上海的台风）在模型建模阶段完成，
    此处仅做数据复制以保证模型目录结构完整。

数据来源：
    原始数据: data/Hazard_data/WP台风数据/IBTrACS.WP.v04r01.nc
    数据格式: NetCDF (IBTrACS v04r01 西太平洋子集)

输出说明：
    输出目录: model_房地产风险_v6/data/Hazard_data/WP台风数据/
    直接复制原始文件，不做任何修改

依赖环境：
    Python标准库 (shutil)
"""

import os
import sys
import shutil
import logging
import time

# ============================================================
# 参数配置区
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# 原始数据目录
SRC_DIR = os.path.join(
    SCRIPT_DIR, os.pardir, os.pardir, os.pardir, os.pardir,
    "data", "Hazard_data", "WP台风数据"
)

# 输出目录
DST_DIR = SCRIPT_DIR

# 需要复制的文件列表
FILES_TO_COPY = ["IBTrACS.WP.v04r01.nc"]

# 日志文件
LOG_FILE = os.path.join(SCRIPT_DIR, "preprocess_copy_typhoon.log")

# ============================================================
# 日志配置
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ============================================================
# 核心逻辑
# ============================================================

def main():
    t_start = time.time()

    src_dir = os.path.normpath(SRC_DIR)
    if not os.path.isdir(src_dir):
        logger.error("原始数据目录不存在: %s", src_dir)
        sys.exit(1)

    os.makedirs(DST_DIR, exist_ok=True)

    for fname in FILES_TO_COPY:
        src_path = os.path.join(src_dir, fname)
        dst_path = os.path.join(DST_DIR, fname)

        if not os.path.exists(src_path):
            logger.error("源文件不存在: %s", src_path)
            sys.exit(1)

        if os.path.exists(dst_path):
            src_size = os.path.getsize(src_path)
            dst_size = os.path.getsize(dst_path)
            if src_size == dst_size:
                logger.info("跳过(已存在且大小一致): %s", fname)
                continue

        logger.info("正在复制: %s → %s", src_path, dst_path)
        shutil.copy2(src_path, dst_path)
        logger.info("复制完成: %s (%.1f MB)", fname, os.path.getsize(dst_path) / 1e6)

    elapsed = time.time() - t_start
    logger.info("总耗时 %.1f秒", elapsed)


if __name__ == "__main__":
    main()
