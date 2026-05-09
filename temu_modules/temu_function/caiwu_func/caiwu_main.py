import os
import pickle
import re
import sys
import time
from collections import defaultdict
from typing import List, Tuple, Dict
from tqdm import tqdm
import pandas as pd
from loguru import logger
from rapidfuzz import fuzz
from config.middleware_config import db
from temu_modules.temu_function.caiwu_func.caiwu_calculate import read_excel_data, merge_all_excel_file, \
    start_merge_excel
from temu_modules.temu_function.caiwu_func.factory_excel import validate_and_merge_cost_table, merge_cost_with_improve_table
from temu_modules.temu_function.finance_excel import get_date_range_timestamps, extract_export_history_page, get_export_history_page, \
    get_search_purchase_order_list, extract_search_purchase_order_list
from temu_modules.temu_function.general_interface import get_goods_list, extract_goods_list
from utils.TemuBase import get_shop_info_db
from utils.url_downloader import download_seller_excel



def get_x_to_y_map(uid, df, shop_info) -> Tuple[Dict, Dict, Dict]:
    """
    基于交易结算总表生成SKU-SKC和备货单-厂家映射（仅被通用缓存函数调用）
    新增：为批量请求添加tqdm进度条，可视化处理进度
    返回：(sku_to_skc_map, purchaseSn_to_factoryName_map, sku_to_category_map)
    """
    # ========== 核心修改1：处理备货单号，多值时只取第一个 ==========
    # 先将备货单号转为字符串，避免非字符串类型报错
    df['备货单号'] = df['备货单号'].astype(str)
    # 分割逗号，取第一个值（处理空值/无逗号的情况）
    df['备货单号_处理后'] = df['备货单号'].apply(lambda x: x.split(',')[0].strip() if pd.notna(x) and x != '' else x)

    # 基于处理后的备货单号生成列表
    sku_id_list = df["SKU ID"].tolist()
    purchase_order_id_list = df["备货单号_处理后"].tolist()

    if len(sku_id_list) != len(purchase_order_id_list):
        logger.error("交易结算总表和卖家中心表数量不一致")

    # 计算分割后的组数
    total_batches_100 = (len(sku_id_list) + 100 - 1) // 100  # SKU按100个一批
    total_batches_20 = (len(purchase_order_id_list) + 20 - 1) // 20  # 备货单按20个一批

    # 1. 创建一个空字典，用于存储 {sku_id: 货号} 的映射关系
    sku_to_skc_map = {}
    purchaseSn_to_factoryName_map = {}
    sku_to_category_map = {}

    # ========== 备货单批量处理（20个/批）+ 进度条 ==========
    logger.info(f"\n📦 开始处理备货单映射：共{len(purchase_order_id_list)}个备货单，分{total_batches_20}批（每批20个）")
    # 初始化tqdm进度条
    purchase_pbar = tqdm(total=total_batches_20, desc="备货单厂家映射", unit="批", ncols=100)
    # 记录上一次输出的百分比（用于5%进度日志）
    last_logged_percent = -1

    for batch_idx in range(total_batches_20):
        start_idx = batch_idx * 20
        end_idx = min((batch_idx + 1) * 20, len(purchase_order_id_list))

        purchase_order_current_batch_list = purchase_order_id_list[start_idx:end_idx]

        while True:
            try:
                purchase_order_resp = get_search_purchase_order_list(
                    uid,
                    shop_info["headers"], shop_info["cookies"],
                    subPurchaseOrderSnList=purchase_order_current_batch_list
                )
                break
            except Exception as e:
                logger.error(f"第{batch_idx + 1}/{total_batches_20}批备货单请求异常，等待10秒后重试，错误：{e}")
                time.sleep(10)

        purchase_order_item_results = extract_search_purchase_order_list(purchase_order_resp)

        for item in purchase_order_item_results:
            got_order_id = item["order_id"]
            purchaseSn_to_factoryName_map[got_order_id] = item["factory_name"]
        
        # 调试信息：显示本批映射结果
        # logger.debug(f"    本批备货单映射结果：{len(purchase_order_item_results)}个")
        # for item in purchase_order_item_results[:3]:  # 只显示前3个
        #     logger.debug(f"      备货单号={item['order_id']} → 厂家={item['factory_name']}")

        # 更新进度条
        purchase_pbar.update(1)

        # 每5%或完成时输出进度日志
        processed_batches = batch_idx + 1
        current_percent = processed_batches / total_batches_20 * 100
        percent_integer = int(current_percent)
        # 跨过5%的边界时输出（如：上次输出3%，当前6%，跨越了5%边界）
        if percent_integer // 5 > last_logged_percent // 5:
            logger.info(f"备货单厂家映射进度：{processed_batches}/{total_batches_20} 批（{percent_integer}%）")
            last_logged_percent = percent_integer
    # 关闭进度条
    purchase_pbar.close()
    logger.info(f"✅ 备货单厂家映射完成：共{len(purchaseSn_to_factoryName_map)}个有效映射")

    # ========== SKU批量处理（100个/批）+ 进度条 ==========
    logger.info(f"\n📦 开始处理SKU-SKC映射：共{len(sku_id_list)}个SKU，分{total_batches_100}批（每批100个）")
    # 初始化tqdm进度条
    sku_pbar = tqdm(total=total_batches_100, desc="SKU-SKC货号映射", unit="批", ncols=100)
    # 记录上一次输出的百分比（用于5%进度日志）
    last_logged_percent = -1

    # 逐批分割并获取数据 获取skc货号 并且插入表格
    for batch_idx in range(total_batches_100):
        start_idx = batch_idx * 100
        end_idx = min((batch_idx + 1) * 100, len(sku_id_list))
        goods_current_batch_list = sku_id_list[start_idx:end_idx]

        # 2. 通过skuid 获取 skc货号
        goods_resp = get_goods_list(uid, shop_info["headers"], shop_info["cookies"],
                                    sku_id_list=goods_current_batch_list)

        goods_item_results = extract_goods_list(goods_resp)

        # 3. 解析json，将结果存入字典，而不是立即更新DataFrame
        for item in goods_item_results.get("data", []):
            spu_huohao = item.get("货号")
            leiming = item.get("类目名")
            if not spu_huohao:
                logger.warning(f"skuID {item['sku_id']} 的货号为空")
                continue

            for sku_item in item.get("sku_list", []):
                sku_id = sku_item.get('sku_id')
                if sku_id:
                    sku_to_skc_map[sku_id] = spu_huohao
                    sku_to_category_map[sku_id] = leiming

        # 更新进度条
        sku_pbar.update(1)

        # 每5%或完成时输出进度日志
        processed_batches = batch_idx + 1
        current_percent = processed_batches / total_batches_100 * 100
        percent_integer = int(current_percent)
        # 跨过5%的边界时输出（如：上次输出3%，当前6%，跨越了5%边界）
        if percent_integer // 5 > last_logged_percent // 5:
            logger.info(f"SKU-SKC货号映射进度：{processed_batches}/{total_batches_100} 批（{percent_integer}%）")
            last_logged_percent = percent_integer
    # 关闭进度条
    sku_pbar.close()
    logger.info(f"✅ SKU-SKC映射完成：共{len(sku_to_skc_map)}个有效映射")

    # ========== 核心修改2：清理临时列（可选，避免污染原DataFrame） ==========
    if '备货单号_处理后' in df.columns:
        df.drop(columns=['备货单号_处理后'], inplace=True)

    return sku_to_skc_map, purchaseSn_to_factoryName_map, sku_to_category_map


def get_x_to_y_map0(uid, df, shop_info) -> Tuple[Dict, Dict]:
    """
    基于交易结算总表生成SKU-SKC和备货单-厂家映射（仅被通用缓存函数调用）
    """
    # ========== 核心修改1：处理备货单号，多值时只取第一个 ==========
    # 先将备货单号转为字符串，避免非字符串类型报错
    df['备货单号'] = df['备货单号'].astype(str)
    # 分割逗号，取第一个值（处理空值/无逗号的情况）
    df['备货单号_处理后'] = df['备货单号'].apply(lambda x: x.split(',')[0].strip() if pd.notna(x) and x != '' else x)

    # 基于处理后的备货单号生成列表
    sku_id_list = df["SKU ID"].tolist()
    purchase_order_id_list = df["备货单号_处理后"].tolist()

    if len(sku_id_list) != len(purchase_order_id_list):
        logger.error("交易结算总表和卖家中心表数量不一致")

    # 计算分割后的组数
    total_batches_100 = (len(sku_id_list) + 100 - 1) // 100
    total_batches_20 = (len(purchase_order_id_list) + 20 - 1) // 20

    # 1. 创建一个空字典，用于存储 {sku_id: 货号} 的映射关系
    sku_to_skc_map = {}
    sku_to_category_map = {}
    purchaseSn_to_factoryName_map = {}

    for batch_idx in range(total_batches_20):
        start_idx = batch_idx * 20
        end_idx = min((batch_idx + 1) * 20, len(purchase_order_id_list))

        purchase_order_current_batch_list = purchase_order_id_list[start_idx:end_idx]

        while True:
            try:
                purchase_order_resp = get_search_purchase_order_list(
                    uid,
                    shop_info["headers"], shop_info["cookies"],
                    subPurchaseOrderSnList=purchase_order_current_batch_list
                )
                break
            except Exception as e:
                logger.error(f"获取备货单异常，等待10秒后重试，错误：{e}")
                time.sleep(10)

        purchase_order_item_results = extract_search_purchase_order_list(purchase_order_resp)

        for item in purchase_order_item_results:
            got_order_id = item["order_id"]
            # logger.info(item)
            purchaseSn_to_factoryName_map[got_order_id] = item["factory_name"]

    # 逐批分割并获取数据 获取skc货号 并且插入表格
    for batch_idx in range(total_batches_100):
        start_idx = batch_idx * 100
        end_idx = min((batch_idx + 1) * 100, len(sku_id_list))
        goods_current_batch_list = sku_id_list[start_idx:end_idx]

        # 2. 通过skuid 获取 skc货号
        goods_resp = get_goods_list(uid, shop_info["headers"], shop_info["cookies"],
                                    sku_id_list=goods_current_batch_list)

        goods_item_results = extract_goods_list(goods_resp)

        # 3. 解析json，将结果存入字典，而不是立即更新DataFrame
        for item in goods_item_results.get("data", []):
            spu_huohao = item.get("货号")
            leiming = item.get("类目名")
            if not spu_huohao:
                logger.warning(f"skuID {item['sku_id']} 的货号为空")
                continue

            for sku_item in item.get("sku_list", []):
                sku_id = sku_item.get('sku_id')
                if sku_id:
                    sku_to_skc_map[sku_id] = spu_huohao
                    sku_to_category_map[sku_id] = leiming

    # ========== 核心修改2：清理临时列（可选，避免污染原DataFrame） ==========
    if '备货单号_处理后' in df.columns:
        df.drop(columns=['备货单号_处理后'], inplace=True)

    return sku_to_skc_map, purchaseSn_to_factoryName_map


def get_sku_skc_mapping_from_middleware(uid: str, month: str, shop_info: dict) -> Tuple[Dict, Dict, Dict]:
    """
    通用缓存函数：优先读取中间件缓存 → 缓存无效则基于交易结算总表重建 → 落地缓存
    :param uid: 店铺UID
    :param month: 月份（如2025.10）
    :param shop_info: 店铺信息（含shop_abbr）
    :return: (sku_to_skc_map, purchaseSn_to_factoryName_map, sku_to_category_map)
    """
    shop_abbr = shop_info['shop_abbr']
    base_dir = f"配置文件_结算导出/{shop_abbr}"
    middleware_root = f"{base_dir}/{month}/中间件存储"
    os.makedirs(middleware_root, exist_ok=True)

    # 缓存文件路径
    middleware_map_file = f"{middleware_root}/订单厂家成本映射字典_{month}.pkl"
    settle_excel_path = f"{base_dir}/{month}/交易结算总表_{month}.xlsx"

    # 1. 优先读取中间件缓存
    cache_valid = False
    sku_to_skc_map, purchaseSn_to_factoryName_map, sku_to_category_map = None, None, None
    if os.path.exists(middleware_map_file) and os.path.getsize(middleware_map_file) > 0:
        try:
            with open(middleware_map_file, 'rb') as f:
                cached_data = pickle.load(f)
                if len(cached_data) == 2:
                    sku_to_skc_map, purchaseSn_to_factoryName_map = cached_data
                    sku_to_category_map = {}
                else:
                    sku_to_skc_map, purchaseSn_to_factoryName_map, sku_to_category_map = cached_data
            if isinstance(sku_to_skc_map, dict) and isinstance(purchaseSn_to_factoryName_map, dict):
                cache_valid = True
                logger.info(f"📌 从中间件缓存加载{month}月份SKU-SKC映射成功（{len(sku_to_skc_map)}个映射）")
        except (EOFError, pickle.UnpicklingError, Exception) as e:
            logger.warning(f"⚠️ {month}月份中间件缓存损坏，错误：{e}，将重建")

    # 2. 缓存无效则基于交易结算总表重建
    if not cache_valid:
        if not os.path.exists(settle_excel_path):
            logger.error(f"❌ {month}月份交易结算总表不存在：{settle_excel_path}，无法重建映射")
            raise FileNotFoundError(f"交易结算总表缺失：{settle_excel_path}")

        # 读取交易结算总表并重建映射
        settle_df = read_excel_data(file_path=settle_excel_path, sheet_name=0)
        sku_to_skc_map, purchaseSn_to_factoryName_map, sku_to_category_map = get_x_to_y_map(uid, settle_df, shop_info)
        logger.info(f"✅ 基于交易结算总表重建{month}月份映射：{len(sku_to_skc_map)}个SKU-SKC | {len(purchaseSn_to_factoryName_map)}个厂家映射")

        # 落地缓存到中间件目录
        with open(middleware_map_file, 'wb') as f:
            pickle.dump((sku_to_skc_map, purchaseSn_to_factoryName_map, sku_to_category_map), f)
        logger.info(f"📥 {month}月份映射已落地到中间件缓存：{middleware_map_file}")
    else:
        # 3. 缓存有效，但检测是否有新SKU需要增量补全
        if os.path.exists(settle_excel_path):
            settle_df = read_excel_data(file_path=settle_excel_path, sheet_name=0)
            if 'SKU ID' in settle_df.columns:
                # 检查交易表中的SKU是否都在缓存中
                settle_skus = set()
                for sku in settle_df['SKU ID'].dropna().unique():
                    if pd.api.types.is_integer_dtype(settle_df['SKU ID']):
                        settle_skus.add(int(sku))
                    else:
                        settle_skus.add(str(sku))
                
                # 根据交易表的SKU ID类型，统一转换缓存中的键类型
                if pd.api.types.is_integer_dtype(settle_df['SKU ID']):
                    cache_skus = {int(k) for k in sku_to_skc_map.keys()}
                else:
                    cache_skus = {str(k) for k in sku_to_skc_map.keys()}
                
                new_skus = settle_skus - cache_skus
                
                if new_skus:
                    logger.warning(f"⚠️ 检测到{len(new_skus)}个新SKU不在缓存中，开始增量补全")
                    logger.warning(f"    新SKU示例：{list(new_skus)[:5]}")
                    
                    # 增量获取缺失的SKU映射
                    new_sku_to_skc_map, new_sku_to_category_map = get_missing_sku_mapping(uid, list(new_skus), shop_info)
                    
                    # 合并到现有映射中
                    sku_to_skc_map.update(new_sku_to_skc_map)
                    sku_to_category_map.update(new_sku_to_category_map)
                    logger.info(f"✅ 增量补全完成：新增{len(new_sku_to_skc_map)}个SKU-SKC映射")
                    
                    # 落地缓存到中间件目录
                    with open(middleware_map_file, 'wb') as f:
                        pickle.dump((sku_to_skc_map, purchaseSn_to_factoryName_map, sku_to_category_map), f)
                    logger.info(f"📥 {month}月份映射已更新到中间件缓存：{middleware_map_file}")

    return sku_to_skc_map, purchaseSn_to_factoryName_map, sku_to_category_map


def get_missing_sku_mapping(uid: str, missing_sku_list: list, shop_info: dict) -> Tuple[Dict, Dict]:
    """
    增量获取缺失的SKU-SKC映射（只获取缺失的SKU，避免重复获取）
    :param uid: 店铺UID
    :param missing_sku_list: 缺失的SKU列表
    :param shop_info: 店铺信息
    :return: (SKU到SKC的映射字典, SKU到类目名的映射字典)
    """
    from tqdm import tqdm
    
    sku_to_skc_map = {}
    sku_to_category_map = {}
    total_batches = (len(missing_sku_list) + 99) // 100  # 每100个一批
    
    logger.info(f"🔄 开始增量获取{len(missing_sku_list)}个缺失SKU的SKC映射，分{total_batches}批")
    
    # 初始化进度条
    sku_pbar = tqdm(total=total_batches, desc="增量获取SKU-SKC映射", unit="批", ncols=100)
    
    for batch_idx in range(total_batches):
        start_idx = batch_idx * 100
        end_idx = min((batch_idx + 1) * 100, len(missing_sku_list))
        current_batch = missing_sku_list[start_idx:end_idx]
        
        try:
            # 调用API获取这批SKU的SKC货号
            goods_resp = get_goods_list(uid, shop_info["headers"], shop_info["cookies"], 
                                       sku_id_list=current_batch)
            goods_item_results = extract_goods_list(goods_resp)
            
            # 解析结果
            for item in goods_item_results.get("data", []):
                spu_huohao = item.get("货号")
                leiming = item.get("类目名")
                if not spu_huohao:
                    logger.warning(f"SKU ID {item['sku_id']} 的货号为空")
                    continue
                
                for sku_item in item.get("sku_list", []):
                    sku_id = sku_item.get('sku_id')
                    if sku_id:
                        sku_to_skc_map[sku_id] = spu_huohao
                        sku_to_category_map[sku_id] = leiming
            
            # logger.debug(f"  批次{batch_idx+1}/{total_batches}：获取到{len(current_batch)}个SKU中的{len([s for s in current_batch if s in sku_to_skc_map])}个映射")
            
        except Exception as e:
            logger.error(f"❌ 批次{batch_idx+1}获取失败：{e}，等待10秒后重试")
            time.sleep(10)
            # 重试一次
            try:
                goods_resp = get_goods_list(uid, shop_info["headers"], shop_info["cookies"], 
                                           sku_id_list=current_batch)
                goods_item_results = extract_goods_list(goods_resp)
                
                for item in goods_item_results.get("data", []):
                    spu_huohao = item.get("货号")
                    leiming = item.get("类目名")
                    if not spu_huohao:
                        continue
                    
                    for sku_item in item.get("sku_list", []):
                        sku_id = sku_item.get('sku_id')
                        if sku_id:
                            sku_to_skc_map[sku_id] = spu_huohao
                            sku_to_category_map[sku_id] = leiming
            except Exception as retry_e:
                logger.error(f"❌ 批次{batch_idx+1}重试失败：{retry_e}")
        
        sku_pbar.update(1)
    
    sku_pbar.close()
    logger.info(f"✅ 增量获取完成：成功获取{len(sku_to_skc_map)}/{len(missing_sku_list)}个SKU-SKC映射")
    
    return sku_to_skc_map, sku_to_category_map


def record_skc_to_table(uid, months_list):
    """
    为履约保障表补充SKC货号：复用中间件缓存（基于交易结算总表），不再重复重建
    """
    shop_info = get_shop_info_db(uid)
    shop_abbr = shop_info['shop_abbr']
    base_dir = f"配置文件_结算导出/{shop_abbr}"

    for month in months_list:
        original_excel_path = f"{base_dir}/{month}/履约保障售后问题总表_{month}.xlsx"
        if not os.path.exists(original_excel_path):
            logger.error(f"❌ {month}月份履约保障表不存在：{original_excel_path}，跳过")
            continue

        # 1. 读取履约保障表
        try:
            df = read_excel_data(file_path=original_excel_path, sheet_name=0)
            if 'SKU ID' not in df.columns:
                logger.error(f"❌ {month}月份履约保障表缺失SKU ID列，跳过")
                continue
            original_columns = df.columns.tolist()
            logger.info(f"✅ 读取{month}月份履约保障表成功：{len(df)}行，{len(df['SKU ID'].unique())}个SKU")
        except Exception as e:
            logger.error(f"❌ 读取{month}月份履约保障表失败：{e}，跳过")
            continue

        # 2. 调用通用函数获取SKU-SKC映射（复用中间件缓存）
        try:
            sku_to_skc_map, _, sku_to_category_map = get_sku_skc_mapping_from_middleware(uid, month, shop_info)
        except Exception as e:
            logger.error(f"❌ 获取{month}月份SKU-SKC映射失败：{e}，跳过该月份")
            continue

        # 3. 匹配SKC货号并保存
        if pd.api.types.is_integer_dtype(df['SKU ID']):
            sku_to_skc_map = {int(k): v for k, v in sku_to_skc_map.items()}
            sku_to_category_map = {int(k): v for k, v in sku_to_category_map.items()}
        else:
            sku_to_skc_map = {str(k): v for k, v in sku_to_skc_map.items()}
            sku_to_category_map = {str(k): v for k, v in sku_to_category_map.items()}

        df['SKC货号'] = df['SKU ID'].map(sku_to_skc_map).fillna('未匹配到SKC')
        df['类目名'] = df['SKU ID'].map(sku_to_category_map).fillna('未匹配到类目')
        new_columns = []
        if 'SKC货号' not in original_columns:
            new_columns.append('SKC货号')
        if '类目名' not in original_columns:
            new_columns.append('类目名')
        if new_columns:
            df = df[original_columns + new_columns]

        # 保存到原表
        try:
            with pd.ExcelWriter(original_excel_path, engine='openpyxl', mode='w') as writer:
                df.to_excel(writer, index=False, sheet_name='Sheet1')
            logger.success(f"✅ {month}月份履约保障表SKC货号补充完成：{original_excel_path}")
        except Exception as e:
            logger.error(f"❌ 保存{month}月份履约保障表失败：{e}")

    logger.success(f"🎉 所有存在的月份履约保障表SKC货号补充完成！核心目录：{base_dir}")


def record_all_need_colum_to_excel(uid, months_list):
    """
    交易结算表补充成本等列：复用中间件缓存，避免重复重建映射
    """
    shop_info = get_shop_info_db(uid)
    shop_abbr = shop_info['shop_abbr']
    cb_path = "配置文件_成本"
    calc_cost_dir = f"{cb_path}/计算成本"
    os.makedirs(calc_cost_dir, exist_ok=True)
    COST_FILE_ROOT = f"{cb_path}/{shop_abbr}_成本.xlsx"
    if not os.path.exists(COST_FILE_ROOT):
        # 新版成本表结构：厂家名称, SKC货号, SKU属性, jit成本, vmi成本
        pd.DataFrame(columns=['厂家名称', 'SKC货号', 'SKU属性', 'jit成本', 'vmi成本']).to_excel(COST_FILE_ROOT, index=False)
        logger.info(f"根目录成本表不存在，已创建：{COST_FILE_ROOT}")

    for month in months_list:
        # 路径定义
        base_dir = f"配置文件_结算导出/{shop_abbr}"
        excel_path = f"{base_dir}/{month}/交易结算总表_{month}.xlsx"
        cost_path = f"{calc_cost_dir}/{shop_abbr}_成本.xlsx"
        cost_improve_path = f"{base_dir}/{month}/成本完善表_{month}.xlsx"
        middleware_root = f"{base_dir}/{month}/中间件存储"
        os.makedirs(middleware_root, exist_ok=True)
        middleware_file = f"{middleware_root}/订单厂家成本对应表_{month}.xlsx"

        FACTORY_FILE = f"{cb_path}/相同厂家配置表.xlsx"
        COST_FILE = COST_FILE_ROOT
        OUTPUT_FILE = f"{calc_cost_dir}/{shop_abbr}_成本.xlsx"

        # 前置融合成本表
        if not os.path.exists(cost_improve_path):
            # 新版成本完善表结构：厂家名称, SKC货号, SKU属性, jit成本, vmi成本
            pd.DataFrame(columns=['厂家名称', 'SKC货号', 'SKU属性', 'jit成本', 'vmi成本']).to_excel(cost_improve_path, index=False)
        merge_cost_with_improve_table(cost_table_path=cost_path, improve_table_path=cost_improve_path, output_path=cost_path)
        validate_and_merge_cost_table(factory_mapping_file=FACTORY_FILE, cost_file=COST_FILE, output_file=OUTPUT_FILE)
        start_merge_excel(merge_file_list=[cost_path], sheet_name=0, out_sheet_name="成本", output_path=cost_path, unique_cols=None)

        # 读取交易结算表
        if not os.path.exists(excel_path):
            logger.error(f"❌ {month}月份交易结算表不存在：{excel_path}，跳过")
            continue
        df = read_excel_data(file_path=excel_path, sheet_name=0)
        cost_df = read_excel_data(file_path=cost_path, sheet_name=0)

        # 核心：调用通用函数获取映射（复用中间件缓存）
        try:
            sku_to_skc_map, purchaseSn_to_factoryName_map, sku_to_category_map = get_sku_skc_mapping_from_middleware(uid, month, shop_info)
            logger.info(f"📊 {month}月份映射获取成功：SKU→SKC映射数={len(sku_to_skc_map)}, 备货单号→厂家映射数={len(purchaseSn_to_factoryName_map)}")
        except Exception as e:
            logger.error(f"❌ 获取{month}月份映射失败：{e}，跳过")
            continue

        # 匹配SKC货号和厂家名称
        if 'SKC货号' not in df.columns:
            df['SKC货号'] = pd.Series(dtype='string')
        if '类目名' not in df.columns:
            df['类目名'] = pd.Series(dtype='string')
        if '厂家名称' not in df.columns:
            df['厂家名称'] = pd.Series(dtype='string')

        df['备货单号'] = df['备货单号'].astype(str)
        if pd.api.types.is_integer_dtype(df['SKU ID']):
            sku_to_skc_map = {int(k): v for k, v in sku_to_skc_map.items()}
            sku_to_category_map = {int(k): v for k, v in sku_to_category_map.items()}
        else:
            sku_to_skc_map = {str(k): v for k, v in sku_to_skc_map.items()}
            sku_to_category_map = {str(k): v for k, v in sku_to_category_map.items()}

        logger.info(f"📊 开始匹配SKC货号：交易表行数={len(df)}, SKU ID类型={df['SKU ID'].dtype}")
        logger.info(f"    SKU→SKC映射样本：前3个映射")
        sku_sample = list(sku_to_skc_map.items())[:3]
        for i, (sku, skc) in enumerate(sku_sample):
            logger.info(f"      [{i}] SKU={sku} (类型={type(sku).__name__}) → SKC={skc}")

        # 显示交易表中的SKU ID样本
        logger.info(f"    交易表SKU ID样本：前5个")
        for i in range(min(5, len(df))):
            sku_val = df.iloc[i]['SKU ID']
            logger.info(f"      [{i}] SKU={sku_val} (类型={type(sku_val).__name__})")

        # 检查未映射的SKU是否在映射字典中
        unmapped_skus = df[df['SKU ID'].map(sku_to_skc_map).isna()]['SKU ID'].tolist()
        if unmapped_skus:
            logger.info(f"    检查未映射的SKU是否在映射字典中：")
            for i, sku in enumerate(unmapped_skus[:5]):
                # 尝试不同的键类型
                sku_int = int(sku) if isinstance(sku, str) and sku.isdigit() else sku
                sku_str = str(sku)
                found_int = sku_int in sku_to_skc_map
                found_str = sku_str in sku_to_skc_map
                logger.info(f"      [{i}] SKU={sku} (int存在={found_int}, str存在={found_str})")
                if found_int:
                    logger.info(f"         int键对应的SKC={sku_to_skc_map[sku_int]}")
                if found_str:
                    logger.info(f"         str键对应的SKC={sku_to_skc_map[sku_str]}")

        df.loc[:, 'SKC货号'] = df['SKU ID'].map(sku_to_skc_map)
        df.loc[:, '类目名'] = df['SKU ID'].map(sku_to_category_map)
        
        # 统计SKC匹配结果
        skc_mapped_count = df['SKC货号'].notna().sum()
        skc_unmapped_count = len(df) - skc_mapped_count
        logger.info(f"📊 SKC货号匹配结果：成功映射={skc_mapped_count}, 未映射={skc_unmapped_count}")
        
        # 统计类目名匹配结果
        category_mapped_count = df['类目名'].notna().sum()
        category_unmapped_count = len(df) - category_mapped_count
        logger.info(f"📊 类目名匹配结果：成功映射={category_mapped_count}, 未映射={category_unmapped_count}")
        
        if skc_unmapped_count > 0:
            logger.warning(f"⚠️ 有{skc_unmapped_count}个SKU未映射到SKC货号，显示前5个未映射的SKU：")
            unmapped_skus = df[df['SKC货号'].isna()]['SKU ID'].head(5).tolist()
            for i, sku in enumerate(unmapped_skus):
                logger.warning(f"    [{i}] SKU={sku}")
        
        df['厂家名称'] = df['厂家名称'].astype('object')
        df.loc[:, '厂家名称'] = df['备货单号'].map(purchaseSn_to_factoryName_map)
        
        # 统计厂家名称匹配结果
        factory_mapped_count = df['厂家名称'].notna().sum()
        factory_unmapped_count = len(df) - factory_mapped_count
        logger.info(f"📊 厂家名称匹配结果：成功映射={factory_mapped_count}, 未映射={factory_unmapped_count}")
        
        if factory_unmapped_count > 0:
            logger.warning(f"⚠️ 有{factory_unmapped_count}个备货单号未映射到厂家名称，显示前5个未映射的备货单号：")
            unmapped_orders = df[df['厂家名称'].isna()]['备货单号'].head(5).tolist()
            for i, order in enumerate(unmapped_orders):
                logger.warning(f"    [{i}] 备货单号={order}")

        # 成本匹配
        df, cost_improve_df = execute_cost_write_excel(df, cost_df)
        cost_improve_df.to_excel(cost_improve_path, index=False)

        # 后置融合成本表
        merge_cost_with_improve_table(cost_table_path=cost_path, improve_table_path=cost_improve_path, output_path=cost_path)

        # 保存结果
        df.to_excel(excel_path, index=False)
        df_middleware = df.copy()
        df_middleware.to_excel(middleware_file, index=False)
        logger.success(f"✅ {month}月份交易结算表处理完成：{excel_path}")

    logger.success(f"🎉 所有月份交易结算表补充完成！核心目录：{base_dir}")


def execute_cost_write_excel(df, cost_df, sku_threshold=95, factory_threshold=95, total_threshold=95):
    """
    成本匹配逻辑（严格分层+厂家全局最优匹配+多阈值控制）
    支持根据备货单类型（JIT/VMI）匹配不同的成本
    """
    logger.info("=" * 80)
    logger.info(
        f"📊 开始成本匹配（分层精准+模糊+备货类型区分）| 阈值：SKU={sku_threshold} | 厂家={factory_threshold} | 综合={total_threshold}")
    logger.info("=" * 80)

    df_result = df.copy()
    df_result['订单总成本'] = 0.0
    df_result['模糊匹配度'] = 0.0
    df_result['备注'] = ""

    # 初始化成本完善表（新版：包含jit成本和vmi成本）
    cost_improve_cols = ['厂家名称', 'SKC货号', 'SKU属性', 'jit成本', 'vmi成本']
    cost_improve_df = pd.DataFrame(columns=cost_improve_cols)

    required_cols = ['SKC货号', 'SKU属性', '厂家名称']
    for col in required_cols:
        if col not in df.columns:
            logger.info(f"❌ 交易表缺失必要列：{col}")
            return df_result, cost_improve_df
    
    # 检查成本表是否有jit成本和vmi成本列
    if 'jit成本' not in cost_df.columns or 'vmi成本' not in cost_df.columns:
        # 兼容旧版成本表（只有"成本"列）
        if '成本' in cost_df.columns:
            cost_df['jit成本'] = cost_df['成本']
            cost_df['vmi成本'] = cost_df['成本']
            # 删除旧的"成本"列，确保只使用jit成本和vmi成本
            cost_df = cost_df.drop(columns=['成本'])
            logger.info("📌 检测到旧版成本表，已将'成本'列拆分为'jit成本'和'vmi成本'，并删除原'成本'列")
        else:
            logger.info(f"❌ 成本表缺失'jit成本'和'vmi成本'列")
            return df_result, cost_improve_df

    # 检查交易表是否有备货单类型列
    has_stock_type = '备货单类型' in df.columns
    if has_stock_type:
        logger.info(f"📌 检测到'备货单类型'列，将根据JIT/VMI匹配不同成本")
    else:
        logger.warning(f"⚠️ 交易表缺失'备货单类型'列，将统一使用jit成本")

    # 预处理成本表
    cost_clean = cost_df.copy()
    cost_clean.rename(columns={'skc货号': 'SKC货号', 'sku属性': 'SKU属性'}, inplace=True)

    # 厂家名称拆分
    if '厂家名称' in cost_clean.columns:
        cost_clean['厂家名称'] = cost_clean['厂家名称'].astype(str).str.strip() \
            .str.replace(r'\s*[,，]+\s*', ',', regex=True)
        cost_clean = cost_clean.assign(厂家名称=cost_clean['厂家名称'].str.split(',')).explode('厂家名称', ignore_index=True)
        cost_clean['厂家名称'] = cost_clean['厂家名称'].str.strip()
        cost_clean = cost_clean[cost_clean['厂家名称'] != '']

    # 标准化函数
    def standardize_text(text):
        if pd.isna(text):
            return ""
        text_str = str(text).strip().replace(" ", "").replace("　", "")
        text_str = text_str.translate(str.maketrans(
            '０１２３４５６７８９ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ',
            '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
        ))
        return text_str.lower()

    # 标准化关键列
    for col in required_cols:
        if col in cost_clean.columns:
            cost_clean[f'{col}_原始'] = cost_clean[col].astype(str).str.strip()
            cost_clean[f'{col}_key'] = cost_clean[col].apply(standardize_text)

    # 过滤无效数据（jit成本和vmi成本都需要）
    cost_clean = cost_clean.dropna(subset=required_cols)
    cost_clean['jit成本'] = pd.to_numeric(cost_clean['jit成本'], errors='coerce')
    cost_clean['vmi成本'] = pd.to_numeric(cost_clean['vmi成本'], errors='coerce')
    cost_clean = cost_clean.dropna(subset=['jit成本', 'vmi成本']).reset_index(drop=True)

    # 构建SKC索引（同时存储jit成本和vmi成本）
    skc_index = defaultdict(list)
    for idx, row in cost_clean.iterrows():
        skc_key = row['SKC货号_key']
        skc_index[skc_key].append(row.to_dict())

    # 处理交易表
    df_work = df.copy()
    for col in required_cols:
        df_work[f'{col}_原始'] = df_work[col].astype(str).str.strip()
        df_work[f'{col}_key'] = df_work[col].apply(standardize_text)
    df_work['数量_数值'] = pd.to_numeric(df_work['数量'], errors='coerce').fillna(0)

    # 调试信息：显示交易表和成本表的样本数据
    logger.info(f"📊 交易表样本数据（前3行）：")
    for i in range(min(3, len(df_work))):
        logger.info(f"  [{i}] SKC={df_work.iloc[i]['SKC货号_原始']}, SKU={df_work.iloc[i]['SKU属性_原始']}, 厂家={df_work.iloc[i]['厂家名称_原始']}, 厂家_key={df_work.iloc[i]['厂家名称_key']}")
    
    logger.info(f"📊 成本表样本数据（前3行）：")
    sample_cost_keys = list(skc_index.keys())[:3]
    for i, skc_key in enumerate(sample_cost_keys):
        candidates = skc_index[skc_key]
        logger.info(f"  [{i}] SKC_key={skc_key}, 候选数={len(candidates)}")
        for j, cand in enumerate(candidates[:2]):
            logger.info(f"      [{j}] 厂家={cand.get('厂家名称_原始', 'N/A')}, 厂家_key={cand.get('厂家名称_key', 'N/A')}, SKU={cand.get('SKU属性_原始', 'N/A')}, SKU_key={cand.get('SKU属性_key', 'N/A')}")

    # 初始化统计
    matched_count = 0
    fuzzy_count = 0
    fail_count = 0

    # 逐行匹配
    for idx, row in df_work.iterrows():
        orig_skc = row['SKC货号_原始']
        orig_sku = row['SKU属性_原始']
        orig_factory = row['厂家名称_原始']
        skc_key = row['SKC货号_key']
        sku_key = row['SKU属性_key']
        factory_key = row['厂家名称_key']
        qty = row['数量_数值']

        # 获取备货单类型，决定使用哪个成本列
        stock_type = row.get('备货单类型', 'JIT') if has_stock_type else 'JIT'
        stock_type = str(stock_type).upper().strip()
        cost_col_name = 'jit成本' if stock_type == 'JIT' else 'vmi成本'

        # print(f"处理第{idx+1}行：SKC={orig_skc}，SKU={orig_sku}，厂家={orig_factory}，数量={qty}，备货类型={stock_type}")
        # print(f"  标准化后：skc_key={skc_key}，sku_key={sku_key}，factory_key={factory_key}")
        # candidates = skc_index.get(skc_key, [])
        # print(f"SKC索引候选数：{len(candidates)}")
        # if candidates:
        #     print(f"候选记录示例（前3条）：")
        #     for i, cand in enumerate(candidates[:3]):
        #         print(f"  [{i}] SKU_key={cand.get('SKU属性_key', 'N/A')}, 厂家_key={cand.get('厂家名称_key', 'N/A')}")

        # SKC精确匹配
        candidates = skc_index.get(skc_key, [])
        if not candidates:
            fail_reason = f"SKC匹配失败：原始SKC={orig_skc} → 成本表无此SKC"
            df_result.at[idx, '备注'] = fail_reason
            cost_improve_df.loc[len(cost_improve_df)] = [orig_factory, orig_skc, orig_sku, "", ""]
            fail_count += 1
            # logger.debug(f"❌ SKC匹配失败：原始SKC={orig_skc}, 标准化SKC_key={skc_key}, 候选数量=0")
            continue

        # SKU+厂家精准匹配
        exact_match = None
        for cand in candidates:
            if (cand['SKU属性_key'] == sku_key) and (cand['厂家名称_key'] == factory_key):
                exact_match = cand
                break
        
        # 调试信息：显示匹配失败的详细信息
        if not exact_match:
            # logger.debug(f"❌ SKU+厂家精准匹配失败：")
            # logger.debug(f"    原始数据：SKC={orig_skc}, SKU={orig_sku}, 厂家={orig_factory}")
            # logger.debug(f"    标准化数据：SKC_key={skc_key}, SKU_key={sku_key}, 厂家_key={factory_key}")
            # logger.debug(f"    候选数量：{len(candidates)}")
            if candidates:
                # logger.debug(f"    候选厂家列表：{[c.get('厂家名称_原始', 'N/A') for c in candidates[:5]]}")
                # logger.debug(f"    候选SKU列表：{[c.get('SKU属性_原始', 'N/A') for c in candidates[:5]]}")
                pass
            # logger.debug(f"    匹配条件：SKU_key完全匹配 AND 厂家_key完全匹配")
            # logger.debug(f"    所有候选的SKU_key：{[c.get('SKU属性_key', 'N/A') for c in candidates[:3]]}")
            # logger.debug(f"    所有候选的厂家_key：{[c.get('厂家名称_key', 'N/A') for c in candidates[:3]]}")
        
        if exact_match:
            unit_cost = exact_match[cost_col_name]
            total_cost = round(unit_cost * qty, 2)
            df_result.at[idx, '订单总成本'] = total_cost
            df_result.at[idx, '模糊匹配度'] = 100.0
            df_result.at[idx, '备注'] = f"精确匹配成功：SKC={orig_skc}；SKU={orig_sku}；厂家={orig_factory}；备货类型={stock_type}；使用{cost_col_name}={unit_cost}"
            matched_count += 1
            # logger.debug(f"✅ 精确匹配成功：SKC={orig_skc}, SKU={orig_sku}, 厂家={orig_factory}, 备货类型={stock_type}, 成本列={cost_col_name}, 单位成本={unit_cost}, 总成本={total_cost}")
            continue

        # 全局模糊匹配
        best_score = 0.0
        best_cand = None
        best_sku_sim = 0.0
        best_factory_sim = 0.0
        
        # logger.debug(f"🔍 开始模糊匹配：原始SKC={orig_skc}, 原始SKU={orig_sku}, 原始厂家={orig_factory}")
        # logger.debug(f"    标准化：SKC_key={skc_key}, SKU_key={sku_key}, 厂家_key={factory_key}")
        # logger.debug(f"    备货类型：{stock_type}，将使用成本列：{cost_col_name}")
        # logger.debug(f"    候选数量：{len(candidates)}")
        
        for cand in candidates:
            sku_sim = fuzz.ratio(sku_key, cand['SKU属性_key'])
            factory_sim = fuzz.ratio(factory_key, cand['厂家名称_key'])
            total_sim = (sku_sim * 0.6 + factory_sim * 0.4)
            if total_sim > best_score:
                best_score = total_sim
                best_cand = cand
                best_sku_sim = sku_sim
                best_factory_sim = factory_sim

        print(f"  模糊匹配最佳：SKU相似度={best_sku_sim:.1f}%, 厂家相似度={best_factory_sim:.1f}%, 综合={best_score:.1f}%")
        if best_cand:
            print(f"    最佳候选：SKU={best_cand['SKU属性_原始']}, 厂家={best_cand['厂家名称_原始']}")
        
        # logger.debug(f"    模糊匹配结果：最佳SKU相似度={best_sku_sim:.2f}%, 最佳厂家相似度={best_factory_sim:.2f}%, 综合相似度={best_score:.2f}%")
        if best_cand:
            # logger.debug(f"    最佳匹配：SKU={best_cand['SKU属性_原始']}, 厂家={best_cand['厂家名称_原始']}, {cost_col_name}={best_cand[cost_col_name]}")
            pass

        # 阈值判断
        threshold_check = {
            "SKU相似度": (best_sku_sim >= sku_threshold),
            "厂家相似度": (best_factory_sim >= factory_threshold),
            "综合相似度": (best_score >= total_threshold)
        }
        all_threshold_pass = all(threshold_check.values())

        if all_threshold_pass and best_cand is not None:
            unit_cost = best_cand[cost_col_name]
            total_cost = round(unit_cost * qty, 2)
            df_result.at[idx, '订单总成本'] = total_cost
            df_result.at[idx, '模糊匹配度'] = round(best_score, 1)
            df_result.at[idx, '备注'] = (
                f"模糊匹配成功：SKC={orig_skc}；原始SKU={orig_sku} → 匹配SKU={best_cand['SKU属性_原始']}（相似度{round(best_sku_sim, 1)}%）；"
                f"原始厂家={orig_factory} → 匹配厂家={best_cand['厂家名称_原始']}（相似度{round(best_factory_sim, 1)}%）；"
                f"综合相似度={round(best_score, 1)}%；备货类型={stock_type}；使用{cost_col_name}={unit_cost}"
            )
            fuzzy_count += 1
            # logger.debug(f"✅ 模糊匹配成功：SKC={orig_skc}, 总成本={total_cost}, 匹配度={round(best_score, 1)}%")
        else:
            fail_reason = f"匹配失败："
            fail_detail = []
            if not threshold_check["SKU相似度"]:
                fail_detail.append(f"SKU相似度{round(best_sku_sim, 1)}% < {sku_threshold}%")
            if not threshold_check["厂家相似度"]:
                fail_detail.append(f"厂家相似度{round(best_factory_sim, 1)}% < {factory_threshold}%")
            if not threshold_check["综合相似度"]:
                fail_detail.append(f"综合相似度{round(best_score, 1)}% < {total_threshold}%")
            fail_reason += " | ".join(fail_detail)
            df_result.at[idx, '备注'] = fail_reason
            # logger.debug(f"❌ 模糊匹配失败：{fail_reason}")
            cost_improve_df.loc[len(cost_improve_df)] = [orig_factory, orig_skc, orig_sku, "", ""]
            fail_count += 1

    # 统计输出
    total_rows = len(df)
    logger.info(f"\n✅ 匹配完成！")
    logger.info(f"  - 总行数：{total_rows}")
    logger.info(f"  - 精确匹配：{matched_count} 行")
    logger.info(f"  - 模糊匹配：{fuzzy_count} 行")
    logger.info(f"  - 匹配失败：{fail_count} 行")
    logger.info(f"  - 总成本合计：{df_result['订单总成本'].sum():.2f} CNY")
    logger.info("=" * 80)

    # 调整列顺序
    other_cols = [col for col in df_result.columns if col not in ['订单总成本', '模糊匹配度', '备注']]
    df_result = df_result[other_cols + ['订单总成本', '模糊匹配度', '备注']]

    # 去重成本完善表（包含jit成本和vmi成本）
    cost_improve_df = cost_improve_df.drop_duplicates(subset=['厂家名称', 'SKC货号', 'SKU属性'], keep='first').reset_index(drop=True)

    return df_result, cost_improve_df


def find_monthly_folders(directory: str) -> List[str]:
    """
    查找指定目录下的月份文件夹（YYYY.M/YYYY.MM）并排序
    """
    month_pattern = re.compile(r'^(\d{4})\.(\d{1,2})$')
    monthly_folders_with_date = []

    if not os.path.isdir(directory):
        logger.info(f"错误：目录 '{directory}' 不存在。")
        return []

    for entry_name in os.listdir(directory):
        full_path = os.path.join(directory, entry_name)
        match = month_pattern.match(entry_name)
        if os.path.isdir(full_path) and match:
            try:
                year = int(match.group(1))
                month = int(match.group(2))
                if 1900 < year < 2100 and 1 <= month <= 12:
                    monthly_folders_with_date.append((year, month, entry_name))
            except ValueError:
                continue

    monthly_folders_with_date.sort()
    return [folder_name for (year, month, folder_name) in monthly_folders_with_date]


def merge_all_months_excel(uid, months_list, shop_info):
    """
    融合所有月份表格并校验结果
    """
    logger.info("开始融合所有月份表格")
    merge_all_excel_file(uid, months_list)

    success_count = 0
    shop_abbr = shop_info['shop_abbr']
    for month in months_list:
        expected_file = f"配置文件_结算导出/{shop_abbr}/{month}/交易结算总表_{month}.xlsx"
        if os.path.exists(expected_file):
            success_count += 1
            logger.info(f"✅ 月份 {month} 融合结果文件已生成: {expected_file}")
        else:
            logger.warning(f"⚠️ 月份 {month} 融合结果文件未生成: {expected_file}")

    if success_count == 0:
        msg = "❌ 所有月份的融合结果文件均未生成"
        return {"code": -1, "msg": msg}
    else:
        logger.info(f"✅ {success_count}/{len(months_list)} 个月份的融合结果文件已成功生成")

    return {"code": 1,
            "msg": f"融合表格执行成功！成功融合 {success_count}/{len(months_list)} 个月份"}




if __name__ == '__main__':
    logger.remove()
    logger.add(sys.stderr, level="TRACE")

    # 配置参数
    uid = "1"
    months_list = ["2025.10"]