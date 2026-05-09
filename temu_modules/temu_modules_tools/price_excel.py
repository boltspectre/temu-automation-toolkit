import sys

import pandas as pd
from loguru import logger


def load_price_data(file_path):
    # 读取Excel文件（根据实际情况调整sheet_name）
    df = pd.read_excel(file_path, sheet_name=0)

    # 构建价格缓存，兼容列名缺失/空值
    price_cache = {}
    for _, row in df.iterrows():
        # 1. 提取主键（货号/类目 + sku属性），兼容列名缺失
        product_no = row.get("货号/类目", "").strip() if pd.notna(row.get("货号/类目")) else ""
        sku_attr = row.get("sku属性", "").strip() if pd.notna(row.get("sku属性")) else ""
        key = (product_no, sku_attr)

        # 2. 处理底价：兼容列名缺失/空值/非数字
        base_price_val = row.get("底价")  # 用get避免KeyError
        base_price = None
        if pd.notna(base_price_val):  # 先判值是否非空
            try:
                base_price = float(base_price_val)
            except (ValueError, TypeError):
                base_price = None  # 非数字也置空

        # 3. 处理理想价：兼容列名缺失/空值/非数字（核心修复）
        ideal_price_val = row.get("理想价")  # 用get替代[]，列不存在返回None
        ideal_price = None
        if pd.notna(ideal_price_val):  # 列存在且值非空
            try:
                ideal_price = float(ideal_price_val)
            except (ValueError, TypeError):
                ideal_price = None  # 非数字置空

        # 存入缓存
        price_cache[key] = (base_price, ideal_price)

    return price_cache


def get_price_info(price_cache: dict, huohao: str, sku_attr: str) -> tuple[float | None, float | None]:
    """
    根据缓存字典、货号/类目和sku属性查询底价和理想价（无全局依赖）。

    Args:
        price_cache: load_price_data 返回的缓存字典
        huohao: 货号/类目
        sku_attr: SKU属性

    Returns:
        tuple[float | None, float | None]: (底价, 理想价)
    """
    if not isinstance(price_cache, dict):
        raise RuntimeError("缓存字典格式错误！请传入 load_price_data 返回的字典")

    key = (huohao.strip(), sku_attr.strip())
    return price_cache.get(key, (None, None))


def load_activity_price_data(file_path):
    """
    读取Excel文件的"报活动_底价"分页，构建报活动底价缓存。

    Args:
        file_path: Excel文件路径

    Returns:
        dict: 缓存字典，key为(SKC货号, 尺寸)，value为最低价
    """
    df = pd.read_excel(file_path, sheet_name="报活动_底价")

    activity_price_cache = {}
    for _, row in df.iterrows():
        skc_code = row.get("SKC货号\n(不填写默认是全部)", "").strip() if pd.notna(row.get("SKC货号\n(不填写默认是全部)")) else ""
        size = row.get("尺寸", "").strip() if pd.notna(row.get("尺寸")) else ""
        key = (skc_code, size)

        min_price_val = row.get("最低价\n（活动参考价格低于该阈值不报名）")
        min_price = None
        if pd.notna(min_price_val):
            try:
                min_price = float(min_price_val)
            except (ValueError, TypeError):
                min_price = None

        activity_price_cache[key] = min_price

    return activity_price_cache


def get_activity_price_info(activity_price_cache: dict, skc_code: str, size: str) -> float | None:
    """
    根据缓存字典、SKC货号和尺寸查询报活动底价（无全局依赖）。

    Args:
        activity_price_cache: load_activity_price_data 返回的缓存字典
        skc_code: SKC货号
        size: 尺寸

    Returns:
        float | None: 最低价
    """
    if not isinstance(activity_price_cache, dict):
        raise RuntimeError("缓存字典格式错误！请传入 load_activity_price_data 返回的字典")

    key = (skc_code.strip(), size.strip())
    return activity_price_cache.get(key, None)


# ======================
# 使用示例
# ======================
if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="TRACE")

    dianpu = "S"
    file_path = rf"D:\PythonProject\ikun_temu_system\配置文件_工具配置表\{dianpu}_工具配置表.xlsx"

    try:
        price_cache = load_price_data(file_path)
        activity_price_cache = load_activity_price_data(file_path)

        test_cases = [
            ("EQC", "前排2座"),
            ("SXJ", "31.4*15.7inch(80X40cm)"),
            ("SXJ", "24*12inch(60*30cm)"),
            ("ABC", "unknown"),
        ]

        for huohao, attr in test_cases:
            print(attr)
            base_price, ideal_price = get_price_info(price_cache, huohao, attr)

            if base_price is not None or ideal_price is not None:
                base_price_str = f"{base_price:.2f}" if base_price else "无"
                ideal_price_str = f"{ideal_price:.2f}" if ideal_price else "无"
                logger.trace(f"✅ {huohao} + {attr} → 底价: {base_price_str} 理想价: {ideal_price_str}")
            else:
                logger.error(f"❌ 未找到匹配项: {huohao} + {attr}")

        logger.info("=" * 80)
        logger.info("报活动底价测试")

        activity_test_cases = [
            ("CPT", "37*28inches(95*73cm)"),
            ("CPT", "59*51inches(150*130cm)"),
            ("CPT", "78*59inches(200*150cm)"),
            ("ECB", "14.96*14.96inch(38*38cm)"),
            ("ECZ", "15.75*11.8inch(45*30cm)"),
            ("SXJ", "31.4*15.7inches(80X40cm)"),
            ("ABC", "unknown"),
        ]

        for skc_code, size in activity_test_cases:
            min_price = get_activity_price_info(activity_price_cache, skc_code, size)

            if min_price is not None:
                logger.trace(f"✅ {skc_code} + {size} → 最低价: {min_price:.2f}")
            else:
                logger.error(f"❌ 未找到匹配项: {skc_code} + {size}")
    except Exception as e:
        logger.error(f"程序执行失败: {e}")