"""
CMIP6 数据下载速度测试脚本
测试从 ESGF 节点下载一份小型 CMIP6 文件，测量下载速度
"""
import urllib.request
import urllib.error
import time
import os
import sys
import json

# ===================== 配置 =====================
TEST_DIR = os.path.join(os.path.dirname(__file__), "cmip6_test_download")
os.makedirs(TEST_DIR, exist_ok=True)

# 测试文件列表（从小到大，来自不同 ESGF 节点）
# 选择 IPSL-CM6A-LR 的 tos 月值 — 低分辨率模型，文件较小
TEST_FILES = [
    {
        "name": "IPSL-CM6A-LR tos historical",
        "url": (
            "http://esgf-data1.ceda.ac.uk/thredds/fileServer/esg_cmip6/CMIP6/CMIP/"
            "IPSL/IPSL-CM6A-LR/historical/r1i1p1f1/Omon/tos/gr/v20180803/"
            "tos_Omon_IPSL-CM6A-LR_historical_r1i1p1f1_gn_185001-201412.nc"
        ),
    },
    {
        "name": "IPSL-CM6A-LR tos historical (ESGF-Index)",
        "url": (
            "https://esgf-data1.llnl.gov/thredds/fileServer/css03_data/CMIP6/CMIP/"
            "IPSL/IPSL-CM6A-LR/historical/r1i1p1f1/Omon/tos/gr/v20180803/"
            "tos_Omon_IPSL-CM6A-LR_historical_r1i1p1f1_gn_185001-201412.nc"
        ),
    },
    {
        "name": "IPSL-CM6A-LR tos historical (DKRZ)",
        "url": (
            "http://esgf3.dkrz.de/thredds/fileServer/cmip6/CMIP/"
            "IPSL/IPSL-CM6A-LR/historical/r1i1p1f1/Omon/tos/gr/v20180803/"
            "tos_Omon_IPSL-CM6A-LR_historical_r1i1p1f1_gn_185001-201412.nc"
        ),
    },
    {
        "name": "CMCC-CM2-SR5 tos historical (更小文件)",
        "url": (
            "http://esgf-data1.ceda.ac.uk/thredds/fileServer/esg_cmip6/CMIP6/CMIP/"
            "CMCC/CMCC-CM2-SR5/historical/r1i1p1f1/Omon/tos/gn/v20200731/"
            "tos_Omon_CMCC-CM2-SR5_historical_r1i1p1f1_gn_185001-201412.nc"
        ),
    },
]

# ===================== 下载函数 =====================
def download_file(url, dest_path, timeout=300):
    """下载文件并测量速度，返回 (success, size_mb, speed_mbps, duration_sec, error)"""
    print(f"   URL: {url}")
    print(f"   目标: {os.path.basename(dest_path)}")

    start = time.time()
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'CMIP6-Test-Script/1.0')

        with urllib.request.urlopen(req, timeout=timeout) as response:
            size = int(response.headers.get('Content-Length', 0))
            if size > 0:
                print(f"   文件大小: {size / 1024 / 1024:.1f} MB")

            downloaded = 0
            chunk_size = 1024 * 1024  # 1MB chunks
            last_report = start
            with open(dest_path, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    # 每5秒报告进度
                    now = time.time()
                    if now - last_report >= 5:
                        elapsed = now - start
                        speed = downloaded / elapsed / 1024 / 1024
                        pct = downloaded / size * 100 if size > 0 else 0
                        print(f"   进度: {downloaded / 1024 / 1024:.1f} MB "
                              f"({pct:.0f}%) | {speed:.2f} MB/s")
                        last_report = now

        elapsed = time.time() - start
        actual_size = os.path.getsize(dest_path)
        speed = actual_size / elapsed / 1024 / 1024

        return True, actual_size / 1024 / 1024, speed, elapsed, None

    except urllib.error.HTTPError as e:
        return False, 0, 0, 0, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, 0, 0, 0, f"URL Error: {e.reason}"
    except Exception as e:
        return False, 0, 0, 0, str(e)


def search_esgf(variable="tos", experiment="historical", limit=5):
    """查询 ESGF Solr API 获取可用文件列表"""
    base = "https://esgf-node.llnl.gov/esg-search/search"
    params = (
        f"?type=File&project=CMIP6"
        f"&variable_id={variable}"
        f"&experiment_id={experiment}"
        f"&table_id=Omon"
        f"&limit={limit}"
        f"&format=application/solr+json"
    )
    url = base + params
    print(f"\n查询 ESGF: {url}")

    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'CMIP6-Test-Script/1.0')
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        docs = data.get("response", {}).get("docs", [])
        print(f"   找到 {len(docs)} 个文件")

        results = []
        for doc in docs[:limit]:
            # 获取下载 URL
            urls = []
            for access in doc.get("access", []):
                if isinstance(access, str):
                    urls.append(access)

            url_str = ""
            if "url" in doc:
                url_vals = doc["url"]
                if isinstance(url_vals, list):
                    # 提取 HTTP URLs（去掉 globus:// 等）
                    for u in url_vals:
                        u = u.strip().strip('|')
                        if u.startswith("http"):
                            url_str = u
                            break

            results.append({
                "title": doc.get("title", "N/A"),
                "size": doc.get("size", 0),
                "source": doc.get("source", "N/A"),
                "url": url_str,
                "instance": doc.get("instance_id", "N/A"),
            })

        return results

    except Exception as e:
        print(f"   ESGF 查询失败: {e}")
        return []


def search_and_download_esgf(variable="tos", experiment="historical", limit=5):
    """通过 ESGF API 搜索文件并尝试下载"""
    results = search_esgf(variable, experiment, limit)

    for i, r in enumerate(results):
        if not r["url"]:
            continue

        filename = r["title"].split("/")[-1] if "/" in r["title"] else r["title"]
        dest = os.path.join(TEST_DIR, filename)

        print(f"\n[{i+1}/{len(results)}] {r['title'][:80]}...")
        size_mb = r["size"] / 1024 / 1024 if r["size"] else 0
        print(f"   大小: {size_mb:.1f} MB | 数据节点: {r['source']}")

        success, sz, speed, dur, err = download_file(r["url"], dest, timeout=300)
        if success:
            print(f"   ✓ 完成! {sz:.1f} MB in {dur:.0f}s = {speed:.2f} MB/s")

            # 估算完整数据集下载时间
            for scenario_size_gb in [5, 50, 250]:
                est_hours = scenario_size_gb * 1024 / speed / 3600
                print(f"   → 预估 {scenario_size_gb} GB 数据集: {est_hours:.1f} 小时 "
                      f"({est_hours/24:.1f} 天)")
            break
        else:
            print(f"   ✗ 失败: {err}")

    return results


# ===================== 主程序 =====================
if __name__ == "__main__":
    print("=" * 60)
    print("CMIP6 数据下载速度测试")
    print(f"测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"保存目录: {TEST_DIR}")
    print("=" * 60)

    # Step 1: 尝试直接下载已知文件
    print("\n--- 方法 1: 直接 URL 下载测试 ---")
    for tf in TEST_FILES:
        print(f"\n测试: {tf['name']}")
        dest = os.path.join(TEST_DIR, os.path.basename(tf["url"]))
        success, sz, speed, dur, err = download_file(tf["url"], dest, timeout=60)

        if success:
            print(f"  ✓ 成功! {sz:.1f} MB in {dur:.0f}s = {speed:.2f} MB/s")

            # 速度估算
            print(f"  ── 基于此速度的预估 ──")
            for gb, label in [(5, "最小集(月值SST)"), (50, "核心集(+日值)"),
                               (120, "压缩完整集"), (250, "完整集")]:
                hours = gb * 1024 / speed / 3600
                print(f"  {label:20s} {gb:4d} GB → {hours:5.1f} 小时 ({hours/24:.2f} 天)")
            break
        else:
            print(f"  ✗ 失败: {err}")

    # Step 2: 通过 ESGF API 搜索并下载
    print("\n--- 方法 2: ESGF API 搜索 + 下载 ---")
    search_and_download_esgf("tos", "historical", limit=10)

    print("\n" + "=" * 60)
    print("测试完成")
    print(f"下载的文件保存在: {TEST_DIR}")
    print("=" * 60)
