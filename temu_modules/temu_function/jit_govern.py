from loguru import logger

from temu_modules.temu_function.general_interface import get_goods_list, extract_goods_list, get_up_new_lifecycle_list, \
    get_price_groups
from utils.log_utils import auto_print_logger
from utils.send_temu_req import send_req
from utils.multiThreading_log_manager import check_task_stopped, get_task_log_manager
import json


def get_jit_list(
        uid,
        headers: dict,
        cookies: dict,
        page_num: int,
        spu_id_list: list[int] = None,
        start_date: str = None,
        end_date: str = None,
        max_retries: int = 3,
        shop_abbr: str = "",
) -> dict[str, int | str]:
    """
    查询JIT商品列表
    
    Args:
        uid: 用户ID
        headers: 请求头
        cookies: cookies
        page_num: 页码
        spu_id_list: SPU ID列表，优先使用此参数筛选商品
        start_date: 开始日期，格式如 20260202（仅当spu_id_list为None时使用）
        end_date: 结束日期，格式如 20260208（仅当spu_id_list为None时使用）
        max_retries: 最大重试次数
        shop_abbr: 店铺简称
        
    Returns:
        dict: 包含操作结果的字典
    """
    if spu_id_list is None:
        spu_id_list = []
    
    # 将日期格式转换为时间戳
    # 日期格式：20260202 -> 2026-02-02
    time_begin = None
    time_end = None
    
    if start_date and end_date:
        start_year = int(start_date[:4])
        start_month = int(start_date[4:6])
        start_day = int(start_date[6:8])
        
        end_year = int(end_date[:4])
        end_month = int(end_date[4:6])
        end_day = int(end_date[6:8])
        
        # 确保开始日期小于结束日期，如果顺序不对则自动排序
        if (start_year, start_month, start_day) > (end_year, end_month, end_day):
            start_year, end_year = end_year, start_year
            start_month, end_month = end_month, start_month
            start_day, end_day = end_day, start_day
        
        # 创建datetime对象
        from datetime import datetime
        start_dt = datetime(start_year, start_month, start_day, 0, 0, 0)
        end_dt = datetime(end_year, end_month, end_day, 23, 59, 59)
        
        # 转换为毫秒时间戳
        time_begin = int(start_dt.timestamp() * 1000)
        time_end = int(end_dt.timestamp() * 1000) + 999  # 加上999毫秒

    # 调用get_up_new_lifecycle_list函数，使用JIT模式
    result = get_up_new_lifecycle_list(
        uid=uid,
        headers=headers,
        cookies=cookies,
        page_num=page_num,
        max_retries=max_retries,
        log=True,
        shop_abbr=shop_abbr,
        type="jit",
        spu_id_list=spu_id_list,
        time_type=1,  # 1-创建时间
        time_begin=time_begin,
        time_end=time_end
    )
    
    # 更新返回消息
    if result.get("code") == 1:
        result["msg"] = f"店铺{shop_abbr}：JIT商品查询成功"
    else:
        result["msg"] = f"店铺{shop_abbr}：JIT商品查询失败"
    
    return result


def get_jit_skc_spu_list(
        uid,
        headers: dict,
        cookies: dict,
        spu_id_list: list[int] = None,
        start_date: str = None,
        end_date: str = None,
        shop_abbr: str = "",
) -> dict[str, int | str]:
    """
    获取JIT商品列表（自动翻页获取所有数据）
    
    Args:
        uid: 用户ID
        headers: 请求头
        cookies: cookies
        spu_id_list: SPU ID列表，优先使用此参数筛选商品
        start_date: 开始日期，格式如 20260202（仅当spu_id_list为None时使用）
        end_date: 结束日期，格式如 20260208（仅当spu_id_list为None时使用）
        shop_abbr: 店铺简称
        
    Returns:
        dict: 包含操作结果和skc-spu对应表的字典
    """
    # 初始化变量
    all_data_list = []
    total_count = 0
    page_num = 1
    page_size = 100  # 每页100条数据
    
    # 循环获取所有页的数据
    while True:
        # 调用get_jit_list函数，指定页码
        jit_data_list = get_jit_list(uid, headers, cookies, page_num, spu_id_list, start_date, end_date, shop_abbr=shop_abbr)
        
        # 检查返回的数据是否有效
        if not jit_data_list or jit_data_list.get("code") != 1 or not jit_data_list.get("data"):
            if page_num == 1:  # 如果是第一页就失败，返回错误
                return {
                    "code": -1,
                    "msg": f"店铺{shop_abbr}：获取JIT商品列表失败",
                    "data": {},
                    "remarks": "响应数据无效",
                    "skc_spu_list": []
                }
            else:  # 如果是后续页失败，使用已获取的数据
                break
        
        # 获取当前页的数据
        data = jit_data_list["data"]
        if not data.get("result") or not data["result"].get("dataList"):
            if page_num == 1:  # 如果是第一页就没有数据，返回空结果
                return {
                    "code": 1,
                    "msg": f"店铺{shop_abbr}：获取JIT商品列表成功",
                    "data": data,
                    "remarks": "共0个商品",
                    "skc_spu_list": []
                }
            else:  # 如果是后续页没有数据，说明已经获取完所有数据
                break
        
        # 获取总数和当前页数据
        total_count = data["result"].get("total", 0)
        current_data_list = data["result"]["dataList"]
        
        # 将当前页数据添加到总列表中
        all_data_list.extend(current_data_list)
        
        # 检查是否已经获取完所有数据
        if len(all_data_list) >= total_count:
            break
            
        # 准备获取下一页
        page_num += 1
        
        # 如果当前页数据少于page_size，说明已经是最后一页
        if len(current_data_list) < page_size:
            break
    
    # 构建完整的数据结构
    complete_data = {
        "success": True,
        "result": {
            "total": total_count,
            "dataList": all_data_list
        }
    }
    
    # 获取price_groups中间产物，用于获取skc-spu对应表
    price_groups = get_price_groups(shop_abbr, complete_data)
    
    # 得到skc-spu对应表
    skc_spu_list = price_groups["skc_spu"] if price_groups.get("skc_spu") and type(price_groups.get("skc_spu")) == list else []

    return {
        "code": 1,
        "msg": f"店铺{shop_abbr}：获取JIT商品列表成功",
        "data": complete_data,
        "remarks": f"共{total_count}个商品",
        "skc_spu_list": skc_spu_list
    }



def do_open_jit(
        uid,
        headers: dict,
        cookies: dict,
        skc_spu_list: list,  # 必须提供列表参数
        max_retries: int = 3,
        shop_abbr: str = "",
) -> dict[str, int | str]:
    """
    开通JIT库存功能（支持批量开通）
    
    Args:
        uid: 用户ID
        headers: 请求头
        cookies: cookies
        skc_spu_list: SKC和SPU对应列表，格式: [{"skcId": 60920034417, "spuId": 6307893340}, ...]
        max_retries: 最大重试次数
        shop_abbr: 店铺简称
        
    Returns:
        dict: 包含操作结果的字典
    """
    result = {}
    url = "https://agentseller.temu.com/visage-agent-seller/product/skc/batchOpenJit"
    
    # 转换数据格式，将skcId/spuId转换为productSkcId/productId
    product_skcs = []
    for item in skc_spu_list:
        product_skcs.append({
            "productSkcId": item["skcId"],
            "productId": item["spuId"]
        })
    
    data = {
        "productSkcSubSellModeReqList": product_skcs
    }
    
    data = json.dumps(data, separators=(',', ':'))
    
    for attempt in range(1, max_retries + 1):
        response = send_req(
            method="POST",
            headers=headers,
            cookies=cookies,
            url=url,
            data=data,
            uid=uid,
        )
        
        # 检查响应是否有效
        if not response:
            result = {"code": -1, "msg": f"店铺{shop_abbr}：异常，响应结果为空", "data": {}, "remarks": ""}
            continue
        
        # 检查HTTP状态码
        if response.status_code != 200:
            try:
                resp_data = response.json()
            except:
                resp_data = {}
            result = {"code": -1, "msg": f"店铺{shop_abbr}：网络异常或请求被拦截，状态码:{response.status_code}", 
                     "data": resp_data, "remarks": ""}
            continue
        
        # 解析响应内容
        try:
            resp_json = response.json()

            if resp_json.get("success"):

                # 添加失败SKC列表
                failed_skc_list = resp_json.get("result", {}).get("handleProductFailedMsgList", [])

                result = {"code": 1, "msg": f"店铺{shop_abbr}：JIT库存开通成功", "data": resp_json, "remarks": "" if not failed_skc_list else f"开通JIT失败SKC列表{failed_skc_list}",
                          "failed_skc_list": failed_skc_list}

                break
            else:
                error_msg = resp_json.get("errorMsg", "未知错误")

                failed_skc_list = resp_json.get("result", {}).get("handleProductFailedMsgList", [])

                # 添加失败SKC列表
                result = {"code": 1, "msg": f"店铺{shop_abbr}：JIT库存开通失败: {error_msg}", "data": resp_json, "remarks": "" if not failed_skc_list else f"开通JIT失败SKC列表{failed_skc_list}",
                          "failed_skc_list": failed_skc_list}
                continue
        except Exception as e:
            result = {"code": -1, "msg": f"店铺{shop_abbr}：响应解析异常: {str(e)}", "data": {}, "remarks": ""}
            continue
    
    return result


def do_modify_govern(
        uid,
        headers: dict,
        cookies: dict,
        skc_id: int = None,
        final_num: int = None,
        max_retries: int = 3,
        shop_abbr: str = "",
        main_task_id: str = ""
) -> dict[str, int | str]:
    """
    维护库存
    """
    if skc_id is None:
        return {"code": -1, "msg": f"店铺{shop_abbr}：do_modify_govern未提供skc_id", "data": {}, "remarks": ""}

    # 如果final_num为空，从数据库获取默认值
    if final_num is None:
        try:
            from config.common_config import config_manager
            final_num = int(config_manager.get_or_set_config("jit_default_final_num", "500"))
            auto_print_logger(msg=f"店铺{shop_abbr}：使用默认库存数量 {final_num}", remarks="", main_task_id=main_task_id)
        except Exception as e:
            auto_print_logger(msg=f"店铺{shop_abbr}：获取默认库存数量失败，使用500", remarks=str(e), main_task_id=main_task_id)
            final_num = 500  # 如果获取失败，使用默认值500

    _result = {}
    for attempt in range(1, max_retries + 1):
        url = "https://agentseller.temu.com/darwin-mms/api/kiana/foredawn/sales/stock/updateMmsProductSalesStock"

        goods_resp = get_goods_list(uid, headers, cookies, skc_id_list=[skc_id])
        goods_item_results = extract_goods_list(goods_resp)

        # 检查是否获取到商品数据
        if not goods_item_results.get("data"):
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：未获取到商品数据", "data": {}, "remarks": ""}
            break

        # 构建新的JSON格式数据
        new_data = {
            "productId": goods_item_results["data"][0]["spu_id"],
            "skcVirtualStockChangeDTOList": []
        }

        # print(goods_item_results["data"])

        spu_item = goods_item_results["data"][0]
        # for spu_item in goods_item_results["data"]:
        skc_data = {
            "productSkcId": spu_item["skc_id"],
            "stockUpdateSource": 1,
            "skuVirtualStockChangeList": []
        }

        for sku_item in spu_item["sku_list"]:
            # 如果virtualStock为None，则将其视为0
            virtual_stock = sku_item["virtualStock"] if sku_item["virtualStock"] is not None else 0
            
            virtual_stock_diff = final_num - virtual_stock
            if virtual_stock_diff == 0:
                continue

            sku_data = {
                "productSkuId": sku_item["sku_id"],
                "currentStockAvailable": virtual_stock,
                "virtualStockDiff": virtual_stock_diff
            }
            skc_data["skuVirtualStockChangeList"].append(sku_data)

        # print("skc_data", skc_data.get("skuVirtualStockChangeList"))

        if not skc_data.get("skuVirtualStockChangeList"):
            _result = {"code": 1, "msg": f"店铺{shop_abbr}：SKC={skc_id} JIT库存保持不变", "data": {},
                       "remarks": f"无需修改，目标库存数量: {final_num}"}
            auto_print_logger(_result, main_task_id=main_task_id)
            return _result

        new_data["skcVirtualStockChangeDTOList"].append(skc_data)

        response = send_req(
            method="POST",
            headers=headers,
            cookies=cookies,
            url=url,
            json=new_data,
            uid=uid,
        )

        # 检查响应是否有效
        if not response:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：异常，响应结果为空", "data": {}, "remarks": ""}
            continue

        # 检查HTTP状态码
        if response.status_code != 200:
            try:
                resp_data = response.json()
            except:
                resp_data = {}
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：网络异常或请求被拦截，状态码:{response.status_code}", 
                      "data": resp_data, "remarks": ""}
            continue

        # 解析响应内容
        try:
            resp_json = response.json()
            remarks = resp_json.get("errorMsg", "") or ""
            
            if resp_json.get("success"):
                _result = {"code": 1, "msg": f"店铺{shop_abbr}：SKC={skc_id} JIT库存修改成功", "data": resp_json, "remarks": f"JIT库存修改成功，目标库存数量: {final_num} {remarks}"}
                break
            else:
                # 检查是否是"非JIT或定制品，或未签署相关协议"错误
                if "非JIT或定制品，或未签署相关协议" in remarks:
                    remarks = f"{remarks}，可能该商品尚未上传商品实拍图或商品实拍图识别结果有异常"
                
                _result = {"code": -1, "msg": f"店铺{shop_abbr}：SKC={skc_id} JIT库存修改失败", "data": resp_json, "remarks": f"JIT库存修改失败，目标库存数量: {final_num} {remarks}"}
                continue
        except Exception as e:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：响应解析异常: {str(e)}", "data": {}, "remarks": ""}
            continue

    auto_print_logger(_result, main_task_id=main_task_id)

    return _result



def jit_govern_thread(
        uid,
        headers,
        cookies,
        batch_idx,
        batch_size,
        skc_spu_list,
        final_num,
        shop_abbr,
        main_task_id=None,
):
    """单批JIT库存操作任务执行函数（适配分组提交）"""
    total_modified = 0
    total_failed = 0
    success_skcs = []
    failed_skcs = []
    
    logger.info(f"店铺{shop_abbr}：开始处理第 {batch_idx + 1} 批JIT库存任务...")
    
    try:
        # 计算当前批次的起始和结束索引
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, len(skc_spu_list))
        current_batch = skc_spu_list[start_idx:end_idx]
        
        auto_print_logger(msg=f"店铺{shop_abbr}：处理第{batch_idx + 1}批JIT库存", remarks=f"本批{len(current_batch)}个商品（索引{start_idx+1}-{end_idx}）", main_task_id=main_task_id)
        
        # 开通当前批次的JIT
        open_jit_result = do_open_jit(
            uid=uid,
            headers=headers,
            cookies=cookies,
            skc_spu_list=current_batch,
            max_retries=1,
            shop_abbr=shop_abbr,
        )

        # 记录JIT开通结果
        auto_print_logger(msg=open_jit_result.get('msg'), main_task_id=main_task_id)
        
        # 如果JIT开通失败，直接返回
        if open_jit_result.get("code") != 1:
            auto_print_logger(msg=f"店铺{shop_abbr}：第{batch_idx + 1}批JIT库存开通失败", remarks="跳过库存修改", main_task_id=main_task_id)
            failed_skcs = [int(skc_sku.get("skcId", 0)) for skc_sku in current_batch if skc_sku.get("skcId")]
            return {
                "code": -1,
                "msg": f"店铺{shop_abbr}：第{batch_idx + 1}批JIT库存开通失败",
                "success": 0,
                "failed": len(current_batch),
                "success_skcs": [],
                "failed_skcs": failed_skcs,
                "remarks": open_jit_result.get("remarks", "")
            }
        
        # 等待JIT开通生效，避免立即修改库存时后端还未处理完成
        import time
        wait_time = 10
        auto_print_logger(msg=f"店铺{shop_abbr}：等待JIT开通生效", remarks=f"等待{wait_time}秒后开始修改库存", main_task_id=main_task_id)
        time.sleep(wait_time)
        
        # 记录修改库存的结果
        batch_modify_results = []
        batch_failed_count = 0
        
        for skc_sku in current_batch:
            skc_id = int(skc_sku.get("skcId", 0))

            # 执行库存修改
            modify_govern_result = do_modify_govern(
                uid=uid,
                headers=headers,
                cookies=cookies,
                skc_id=skc_id,
                final_num=final_num,  # 设置目标库存数量
                max_retries=3,
                shop_abbr=shop_abbr,
                main_task_id=main_task_id
            )

            batch_modify_results.append({
                "skc_id": skc_id,
                "result": modify_govern_result
            })
            
            # 如果有修改失败的情况，记录但继续执行
            if modify_govern_result.get("code") != 1:
                batch_failed_count += 1
                total_failed += 1
                failed_skcs.append(skc_id)
            else:
                total_modified += 1
                success_skcs.append(skc_id)
        
        # 记录当前批次的处理结果
        batch_result = {
            "batch_index": batch_idx + 1,
            "batch_size": len(current_batch),
            "open_jit_result": open_jit_result,
            "modify_results": batch_modify_results,
            "failed_count": batch_failed_count,
            "total_modified": total_modified,
            "total_failed": total_failed
        }
        
        auto_print_logger(msg=f"店铺{shop_abbr}：第{batch_idx + 1}批JIT库存处理完成", remarks=f"成功{total_modified}个，失败或未修改{total_failed}个", main_task_id=main_task_id)
        
        return {
            "code": 1,
            "msg": f"店铺{shop_abbr}：第{batch_idx + 1}批JIT库存处理完成",
            "success": total_modified,
            "failed": total_failed,
            "success_skcs": success_skcs,
            "failed_skcs": failed_skcs,
            "remarks": f"本批{len(current_batch)}个商品，成功{total_modified}个，失败{total_failed}个"
        }
        
    except Exception as e:
        logger.error(f"店铺{shop_abbr}：第{batch_idx + 1}批JIT库存任务执行异常：{e}")
        return {
            "code": -1,
            "msg": f"店铺{shop_abbr}：第{batch_idx + 1}批JIT库存任务执行异常",
            "success": 0,
            "failed": len(current_batch) if 'current_batch' in locals() else 0,
            "success_skcs": [],
            "failed_skcs": [int(skc_sku.get("skcId", 0)) for skc_sku in current_batch if skc_sku.get("skcId")] if 'current_batch' in locals() else [],
            "remarks": str(e)
        }


def do_open_jit_modify_govern(uid: str, headers: dict, cookies: dict, skc_spu_list: list[dict[str, int]], final_num: int, main_task_id=None, shop_abbr: str = ""):
    """
    开通jit并修改库存（分批处理，每批100个商品）
    """
    result = {"code": 1, "msg": "", "data": {}, "remarks": ""}
    
    # 分批处理，每批100个商品
    batch_size = 100
    total_goods = len(skc_spu_list)
    total_batches = (total_goods + batch_size - 1) // batch_size  # 向上取整
    
    auto_print_logger(msg=f"店铺{shop_abbr}：开始分批处理JIT商品", remarks=f"共{total_goods}个商品，分{total_batches}批处理，每批最多{batch_size}个", main_task_id=main_task_id)
    
    # 记录所有批次的处理结果
    all_modify_results = []
    total_failed_count = 0
    
    for batch_idx in range(total_batches):
        # 计算当前批次的起始和结束索引
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, total_goods)
        current_batch = skc_spu_list[start_idx:end_idx]
        
        auto_print_logger(msg=f"店铺{shop_abbr}：处理第{batch_idx + 1}/{total_batches}批商品", remarks=f"本批{len(current_batch)}个商品（索引{start_idx+1}-{end_idx}）", main_task_id=main_task_id)
        
        # 开通当前批次的JIT
        open_jit_result = do_open_jit(
            uid=uid,
            headers=headers,
            cookies=cookies,
            skc_spu_list=current_batch,
            max_retries=1,
            shop_abbr=shop_abbr,
        )

        # 记录JIT开通结果
        auto_print_logger(msg=open_jit_result.get('msg'), remarks=f"{open_jit_result.get('remarks')}", main_task_id=main_task_id)
        
        # 如果有失败的SKC列表，输出详细信息
        failed_skc_list = open_jit_result.get("failed_skc_list", [])
        if failed_skc_list:
            failed_details = []
            for item in failed_skc_list:
                skc_id = item.get("productSkcId")
                error_msg = item.get("errorMsg", "")
                failed_details.append(f"skc={skc_id}，错误信息：{error_msg}")
            
            # 输出格式化的失败信息
            failed_info = "\n".join(failed_details)
            auto_print_logger(msg=f"店铺{shop_abbr}：第{batch_idx + 1}批开通JIT失败详情", remarks=failed_info, main_task_id=main_task_id)

        # 如果JIT开通失败，记录但继续处理下一批
        if open_jit_result.get("code") != 1:
            auto_print_logger(msg=f"店铺{shop_abbr}：第{batch_idx + 1}批JIT库存开通失败", remarks="跳过库存修改，继续下一批", main_task_id=main_task_id)
            total_failed_count += len(current_batch)
            continue

        # 等待JIT开通生效，避免立即修改库存时后端还未处理完成
        import time
        wait_time = 3
        auto_print_logger(msg=f"店铺{shop_abbr}：等待JIT开通生效", remarks=f"等待{wait_time}秒后开始修改库存", main_task_id=main_task_id)
        time.sleep(wait_time)

        # 记录修改库存的结果
        batch_modify_results = []
        batch_failed_count = 0
        
        for skc_sku in current_batch:
            skc_id = int(skc_sku.get("skcId", 0))

            # 执行库存修改
            modify_govern_result = do_modify_govern(
                uid=uid,
                headers=headers,
                cookies=cookies,
                skc_id=skc_id,
                final_num=final_num,  # 设置目标库存数量
                max_retries=3,
                shop_abbr=shop_abbr,
                main_task_id=main_task_id
            )

            batch_modify_results.append({
                "skc_id": skc_id,
                "result": modify_govern_result
            })
            
            # 如果有修改失败的情况，记录但继续执行
            if modify_govern_result.get("code") != 1:
                batch_failed_count += 1
        
        # 记录当前批次的处理结果
        batch_result = {
            "batch_index": batch_idx + 1,
            "batch_size": len(current_batch),
            "open_jit_result": open_jit_result,
            "modify_results": batch_modify_results,
            "failed_count": batch_failed_count
        }
        all_modify_results.append(batch_result)
        total_failed_count += batch_failed_count
        
        # 记录当前批次的完成情况
        if batch_failed_count == 0:
            auto_print_logger(msg=f"店铺{shop_abbr}：第{batch_idx + 1}批处理完成", remarks=f"本批{len(current_batch)}个商品全部成功", main_task_id=main_task_id)
        else:
            auto_print_logger(msg=f"店铺{shop_abbr}：第{batch_idx + 1}批处理完成", remarks=f"本批{len(current_batch) - batch_failed_count}个成功，{batch_failed_count}个失败", main_task_id=main_task_id)
    
    # 设置返回消息
    success_count = total_goods - total_failed_count
    if total_failed_count == 0:
        result["msg"] = f"店铺{shop_abbr}：JIT库存操作完成，{total_goods}个商品全部处理成功"
    else:
        result["code"] = -1
        result["msg"] = f"店铺{shop_abbr}：JIT库存操作完成，{success_count}个成功，{total_failed_count}个失败"
    
    result["data"] = {
        "total_goods": total_goods,
        "total_batches": total_batches,
        "success_count": success_count,
        "failed_count": total_failed_count,
        "batch_results": all_modify_results
    }
    auto_print_logger(result, main_task_id=main_task_id)
    return result



def do_all_open_jit_modify_govern(
        uid: str,
        headers: dict,
        cookies: dict,
        final_num: int = None,
        skc_spu_list: list[dict[str, int]] = None,
        spu_id_list: list[int] = None,
        start_date: str = None,
        end_date: str = None,
        shop_abbr: str = None,
        main_task_id: str = None,
        mall_id: str = None,
        wait_all_complete: bool = True,
        timeout: int = 3600,
):
    result = {"code": 1, "msg": "", "data": {}, "remarks": ""}
    task_ids = []

    # 第一步：获取 skc_spu_list
    if skc_spu_list:
        auto_print_logger(msg=f"店铺{shop_abbr}：使用指定SKC列表进行JIT库存操作", remarks=f"共{len(skc_spu_list)}个商品", main_task_id=main_task_id)
        filter_type = "skc_list"
        filter_info = f"SKC列表，共{len(skc_spu_list)}个商品"
    elif spu_id_list:
        auto_print_logger(msg=f"店铺{shop_abbr}：开始根据SPU列表获取JIT商品", remarks=f"共{len(spu_id_list)}个SPU", main_task_id=main_task_id)
        
        jit_skc_spu_list = get_jit_skc_spu_list(
            uid=uid,
            headers=headers,
            cookies=cookies,
            spu_id_list=spu_id_list,
            shop_abbr=shop_abbr,
        )

        if jit_skc_spu_list.get("code") != 1:
            result["code"] = -1
            result["msg"] = f"店铺{shop_abbr}：根据SPU列表获取JIT商品失败"
            result["data"] = jit_skc_spu_list
            auto_print_logger(result, main_task_id=main_task_id)
            return result

        skc_spu_list = jit_skc_spu_list.get("skc_spu_list", [])
        filter_type = "spu_list"
        filter_info = f"SPU列表，共{len(spu_id_list)}个SPU，获得{len(skc_spu_list)}个SKC"
    elif start_date and end_date:
        auto_print_logger(msg=f"店铺{shop_abbr}：开始根据日期范围获取JIT商品", remarks=f"开始日期：{start_date}，结束日期：{end_date}", main_task_id=main_task_id)
        
        jit_skc_spu_list = get_jit_skc_spu_list(
            uid=uid,
            headers=headers,
            cookies=cookies,
            start_date=start_date,
            end_date=end_date,
            shop_abbr=shop_abbr,
        )

        if jit_skc_spu_list.get("code") != 1:
            result["code"] = -1
            result["msg"] = f"店铺{shop_abbr}：根据日期范围获取JIT商品失败"
            result["data"] = jit_skc_spu_list
            auto_print_logger(result, main_task_id=main_task_id)
            return result

        skc_spu_list = jit_skc_spu_list.get("skc_spu_list", [])
        filter_type = "date_range"
        filter_info = f"日期范围，开始日期：{start_date}，结束日期：{end_date}，获得{len(skc_spu_list)}个SKC"
    else:
        result["code"] = -1
        result["msg"] = f"店铺{shop_abbr}：未提供SKC列表、SPU列表或日期范围"
        auto_print_logger(result, main_task_id=main_task_id)
        return result

    # 检查是否有商品需要处理
    if not skc_spu_list:
        result["code"] = 1
        result["msg"] = f"店铺{shop_abbr}：JIT库存操作完成"
        result["remarks"] = f"成功0个商品开通JIT维护库存"
        result["data"] = {
            "source": filter_type,
            "filter_info": filter_info,
            "jit_goods_count": 0,
            "total_batches": 0,
            "success": 0,
            "failed": 0,
            "success_skcs": [],
            "failed_skcs": [],
            "task_results": []
        }
        auto_print_logger(result, main_task_id=main_task_id)
        return result

    # 第二步：统一执行分批处理逻辑
    batch_size = 100
    total_goods = len(skc_spu_list)
    total_batches = (total_goods + batch_size - 1) // batch_size  # 向上取整
    
    auto_print_logger(msg=f"店铺{shop_abbr}：开始分批处理JIT商品", remarks=f"共{total_goods}个商品，分{total_batches}批处理，每批最多{batch_size}个", main_task_id=main_task_id)
    
    # ========== 检查任务是否被停止 ==========
    if main_task_id:
        check_task_stopped(get_task_log_manager(), main_task_id)
    
    # 如果只有1批，直接执行
    if total_batches <= 1:
        logger.info(f"店铺{shop_abbr}：JIT库存批数为1批，仅主线程执行")
        task_kwargs = {
            "uid": uid,
            "headers": headers,
            "cookies": cookies,
            "batch_idx": 0,
            "batch_size": batch_size,
            "skc_spu_list": skc_spu_list,
            "final_num": final_num,
            "shop_abbr": shop_abbr,
            "main_task_id": main_task_id,
        }
        batch_result = jit_govern_thread(**task_kwargs)
        
        # 收集单批执行的结果
        if batch_result.get("code") == 1:
            total_modified = batch_result.get("success", 0)
            total_failed = batch_result.get("failed", 0)
            success_skcs = batch_result.get("success_skcs", [])
            failed_skcs = batch_result.get("failed_skcs", [])
            task_results = [batch_result]
        else:
            total_modified = 0
            total_failed = batch_result.get("failed", 0)
            success_skcs = []
            failed_skcs = batch_result.get("failed_skcs", [])
            task_results = [batch_result]
        
        logger.info(f"店铺{shop_abbr}：单批任务完成")
        
        # 单批执行直接返回结果
        result["data"] = {
            "source": filter_type,
            "filter_info": filter_info,
            "jit_goods_count": total_goods,
            "total_batches": total_batches,
            "success": total_modified,
            "failed": total_failed,
            "success_skcs": success_skcs,
            "failed_skcs": failed_skcs,
            "task_results": task_results
        }
        
        if total_failed > 0:
            result["code"] = 1
            result["msg"] = f"店铺{shop_abbr}：JIT库存操作完成（部分失败）"
            result["remarks"] = f"成功{total_modified}个，失败{total_failed}个"
        else:
            result["code"] = 1
            result["msg"] = f"店铺{shop_abbr}：JIT库存操作成功"
            result["remarks"] = f"成功{total_modified}个商品开通JIT维护库存"
        
        auto_print_logger(result, main_task_id=main_task_id)
        return result
    else:
        # 提交所有批的任务（按店铺_JIT库存分组）
        for batch_idx in range(total_batches):
            task_kwargs = {
                "uid": uid,
                "headers": headers,
                "cookies": cookies,
                "batch_idx": batch_idx,
                "batch_size": batch_size,
                "skc_spu_list": skc_spu_list,
                "final_num": final_num,
                "shop_abbr": shop_abbr,
                "main_task_id": main_task_id,
            }
            task_id = get_task_log_manager().add_task(
                target_func=jit_govern_thread, **task_kwargs,
                task_group=f"{shop_abbr}_JIT库存",
                mall_id=mall_id,
                parent_task_id=main_task_id,
                is_main_task=0,
            )

            if task_id:
                task_ids.append(task_id)
                remarks = f"店铺{shop_abbr}：成功提交第{batch_idx + 1}批JIT库存任务 | 任务ID：{task_id}"
                auto_print_logger(remarks=remarks, success_type="i", main_task_id=main_task_id)
            else:
                remarks = f"店铺{shop_abbr}：提交第{batch_idx + 1}批JIT库存任务失败"
                auto_print_logger(remarks=remarks, success_type="e", main_task_id=main_task_id)
                continue
    
    # 如果不等待任务完成，直接返回
    if not wait_all_complete:
        # 多批执行，返回任务ID
        remarks = f"店铺{shop_abbr}：共提交 {len(task_ids)} 个JIT库存任务（总批数：{total_batches}），任务执行中"
        result["data"] = {"task_ids": task_ids, "total_batches": total_batches}
        result["msg"] = remarks
        result["remarks"] = remarks
        
        auto_print_logger(result, main_task_id=main_task_id)
        return result
    
    # 等待所有任务完成
    if total_batches > 1:
        total_modified = 0
        total_failed = 0
        task_results = []
        success_skcs = []
        failed_skcs = []
        
        logger.info(f"店铺{shop_abbr}：开始等待 {len(task_ids)} 个JIT库存任务完成...")
        
        for idx, task_id in enumerate(task_ids):
            try:
                result = get_task_log_manager().get_task_result(
                    task_id=task_id,
                    timeout=timeout
                )
                task_results.append(result)
                
                batch_success = result.get("success", 0)
                batch_failed = result.get("failed", 0)
                
                logger.info(f"店铺{shop_abbr}：第{idx + 1}个任务结果 | task_id: {task_id} | 成功: {batch_success} | 失败: {batch_failed}")
                
                if result.get("code") == 1:
                    total_modified += batch_success
                    total_failed += batch_failed
                    success_skcs.extend(result.get("success_skcs", []))
                    failed_skcs.extend(result.get("failed_skcs", []))
                else:
                    total_failed += result.get("failed", 0)
                    failed_skcs.extend(result.get("failed_skcs", []))
                    
            except Exception as e:
                logger.error(f"店铺{shop_abbr}：获取任务{task_id}结果失败：{e}")
                total_failed += batch_size
        
        logger.info(f"店铺{shop_abbr}：所有任务完成")
    
    # 设置返回结果
    result["data"] = {
        "source": filter_type,
        "filter_info": filter_info,
        "jit_goods_count": total_goods,
        "total_batches": total_batches,
        "success": total_modified,
        "failed": total_failed,
        "success_skcs": success_skcs,
        "failed_skcs": failed_skcs,
        "task_results": task_results
    }
    
    if total_failed > 0:
        result["code"] = 1
        result["msg"] = f"店铺{shop_abbr}：JIT库存操作完成（部分失败）"
        result["remarks"] = f"成功{total_modified}个，失败{total_failed}个"
    else:
        result["code"] = 1
        result["msg"] = f"店铺{shop_abbr}：JIT库存操作成功"
        result["remarks"] = f"成功{total_modified}个商品开通JIT维护库存"

    auto_print_logger(result, main_task_id=main_task_id)
    return result