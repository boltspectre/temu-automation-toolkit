import json
import os
import random
import sys
import time

from loguru import logger

from config.common_config import modify_price_excels_path

from temu_modules.temu_modules_tools.price_excel import load_price_data, get_price_info
from temu_modules.temu_function.general_interface import get_up_new_lifecycle_list, get_price_groups
from utils.log_utils import auto_print_logger, write_warning_to_file
from utils.multiThreading_log_manager import check_task_stopped, get_task_log_manager
from utils.send_temu_req import send_req


def group_sku_by_price_order(shop_abbr, json_data):
    """
    从核价JSON中解析SKU，并按priceOrderId分组
    :return: dict {priceOrderId: [sku_item1, sku_item2,...]}
    """
    price_order_groups = {}
    data = get_price_groups(shop_abbr, json_data)

    for sku_item in data["price_group"]:
        price_order_id = sku_item["priceOrderId"]
        # 按priceOrderId分组
        if price_order_id not in price_order_groups:
            price_order_groups[price_order_id] = []
        price_order_groups[price_order_id].append(sku_item)

    return price_order_groups


def submit_price_by_group(
            uid,
            headers,
            cookies,
            price_order_groups,
            minu_price,
            modify_times,
            price_cache,
            shop_abbr,
            main_task_id=None
          ):
    """
    按priceOrderId分组提交核价
    """
    total_success = 0
    total_failed = 0

    for price_order_id, sku_list in price_order_groups.items():
        try:
            # ========== 检查任务是否被停止 ==========
            if main_task_id:
                check_task_stopped(get_task_log_manager(), main_task_id)

            # 情况1：分组内只有1个SKU → 单独提交（复用你现有的modify_price函数）
            if len(sku_list) == 1:
                result = modify_price(uid, headers, cookies, sku_list[0], minu_price, modify_times, price_cache, shop_abbr, main_task_id=main_task_id)
                if result["code"] == 1:
                    total_success += 1
                else:
                    total_failed += 1
            # 情况2：分组内有多个SKU → 批量提交（改造modify_price支持批量SKU）
            else:
                result = modify_price_in_priceOrder(uid, headers, cookies, sku_list, minu_price, modify_times, price_cache, shop_abbr,
                                            price_order_id, main_task_id=main_task_id)
                if result["code"] == 1:
                    total_success += len(sku_list)  # 批量提交成功则所有SKU算成功
                else:
                    total_failed += len(sku_list)

            # 随机休眠，避免请求过快
            sleep_time = random.uniform(0.5, 1.5)
            logger.trace(f"店铺{shop_abbr}：随机休眠{round(sleep_time, 2)}秒")
            time.sleep(sleep_time)

        except RuntimeError as e:
            remarks = f"店铺{shop_abbr}：检测到手动停止信号，正在退出"
            auto_print_logger(remarks=remarks, success_type="e", main_task_id=main_task_id)
            total_failed += len(sku_list)
            return {"success": total_success, "failed": total_failed}

        except Exception as e:
            remarks = f"店铺{shop_abbr}：priceOrderId={price_order_id}提交失败：{e}"
            auto_print_logger(msg="核价提交失败", remarks=remarks, success_type="e", main_task_id=main_task_id)
            total_failed += len(sku_list)

    return {"success": total_success, "failed": total_failed}


def modify_price_in_priceOrder(
        uid,
        headers: dict,
        cookies: dict,
        sku_list: list,
        minu_price: float,
        modify_times: int,
        price_cache: dict,
        shop_abbr: str,
        price_order_id: int,
        main_task_id=None
) -> dict:
    """
    提交同一个priceOrderId下的多个SKU
    """
    try:
        # 1. 统一计算supplierResult（确保同批次规则一致）
        supplier_result = None
        batch_items = []
        # 新增：记录批量核价的日志备注（包含modify_times）
        batch_remarks_list = []

        for sku_item in sku_list:
            # ========== 检查任务是否被停止 ==========
            if main_task_id:
                check_task_stopped(get_task_log_manager(), main_task_id)

            # 复用你现有的价格计算逻辑
            if type(sku_item['suggest_supply_price']) == str or type(sku_item['suggest_supply_price']) == int:
                supply_price = int(sku_item['suggest_supply_price'])
            else:
                remarks = f"店铺{shop_abbr}：核价接口未返回推荐价 | skuId={sku_item['skuId']}"
                auto_print_logger(msg="核价接口未返回推荐价", remarks=remarks, success_type="e", main_task_id=main_task_id)
                return {"code": -1, "msg": f"店铺{shop_abbr}：核价接口未返回推荐价"}

            base_price, ideal_price = get_price_info(price_cache, sku_item['leimu'], sku_item['size'])
            current_supplier_result = calculate_supplier_result(shop_abbr, supply_price, base_price, ideal_price, sku_item, modify_times)

            # 确保同批次supplierResult一致（平台要求）
            if supplier_result is None:
                supplier_result = current_supplier_result
            elif supplier_result != current_supplier_result:
                logger.warning(
                    f"店铺{shop_abbr}：priceOrderId={price_order_id}内SKU的supplierResult不一致，统一使用{supplier_result}")

            # 构造批量提交的item
            if supplier_result == 1 or supplier_result == 2:
                # 重新申报/提交：需要价格
                submit_price = int(sku_item['current_price'] - minu_price * 100) if supplier_result == 2 else supply_price
                batch_items.append({
                    "productSkuId": sku_item['skuId'],
                    "price": submit_price
                })
                # ========== 补充批量场景的日志备注（含modify_times） ==========
                if supplier_result == 2:
                    sku_remarks = f"skuId：{sku_item['skuId']}，返回价{sku_item['suggest_supply_price'] / 100.00}，申报价{submit_price / 100.00}，底价{base_price}，理想价{ideal_price if ideal_price else '空'}，次数{sku_item['times']}，核价次数上限 {modify_times}"
                else:
                    sku_remarks = f"skuId：{sku_item['skuId']}，返回价{sku_item['suggest_supply_price'] / 100.00}，确认申报价{submit_price / 100.00}，底价{base_price}，理想价{ideal_price if ideal_price else '空'}，次数{sku_item['times']}，核价次数上限 {modify_times}"
                batch_remarks_list.append(sku_remarks)

            else:
                # 放弃：price为null
                batch_items.append({
                    "productSkuId": sku_item['skuId'],
                    "price": None
                })
                # ========== 放弃场景的日志备注（含modify_times） ==========
                sku_remarks = f"skuId：{sku_item['skuId']}，返回价{sku_item['suggest_supply_price'] / 100.00}，申报价{supply_price / 100.00}，底价{base_price}，理想价{ideal_price if ideal_price else '空'}，次数{sku_item['times']}，核价次数上限 {modify_times}"
                batch_remarks_list.append(sku_remarks)

        # ========== 构造批量核价的整体日志 ==========
        if supplier_result == 1 or supplier_result == 2:
            msg = f"批量{'重新提交报价' if supplier_result == 2 else '确认调整报价'}：priceOrderId={price_order_id}，共{len(sku_list)}个SKU"
            remarks = f"店铺{shop_abbr}：准备{'重新提交' if supplier_result == 2 else '确认调整'}批量报价 | priceOrderId={price_order_id} | 明细：{' | '.join(batch_remarks_list)}"
        elif supplier_result == 3:
            msg = f"批量放弃报价：priceOrderId={price_order_id}，共{len(sku_list)}个SKU"
            remarks = f"店铺{shop_abbr}：准备放弃批量调整报价 | priceOrderId={price_order_id} | 明细：{' | '.join(batch_remarks_list)}"
        else:
            return {"code": -1, "msg": f"店铺{shop_abbr}：supplierResult异常：{supplier_result}"}

        # 打印批量核价的日志（和单SKU格式统一）
        auto_print_logger(msg=msg, remarks=remarks, success_type="i", main_task_id=main_task_id)

        # 2. 构造批量提交的payload
        if supplier_result == 1 or supplier_result == 2:
            url = "https://agentseller.temu.com/api/kiana/mms/magneto/price/bargain-no-bom"
            payload = {
                "supplierResult": supplier_result,
                "priceOrderId": price_order_id,
                "items": batch_items,
                "bargainReasonList": []
            }
        elif supplier_result == 3:
            url = "https://agentseller.temu.com/api/kiana/mms/magneto/api/price-review-order/no-bom/review"
            payload = {"priceOrderId": price_order_id}
        else:
            return {"code": -1, "msg": f"店铺{shop_abbr}：supplierResult异常：{supplier_result}"}

        # 3. 调用接口（复用你现有的send_req）
        response = send_req(
            method="POST",
            headers=headers,
            cookies=cookies,
            url=url,
            json=payload,
            uid=uid,
        )

        # 4. 解析结果（保持原有逻辑，仅补充modify_times到最终日志）
        if not response:
            remarks = f"店铺{shop_abbr}：priceOrderId={price_order_id} 异常，响应结果为空 | 核价次数上限 {modify_times}"
            auto_print_logger(remarks=remarks, success_type="e", main_task_id=main_task_id)
        elif response.status_code != 200:
            remarks = f"店铺{shop_abbr}：priceOrderId={price_order_id} 网络异常或请求被拦截，状态码:{response.status_code}，响应: {response.json()} | 核价次数上限 {modify_times}"
            auto_print_logger(remarks=remarks, success_type="e", main_task_id=main_task_id)
        else:
            remarks = response.json().get("errorMsg", "") or ""

        official_return_msg = "The current state is Pending Pricing, and the command cannot be executed: Non-Disassembled Price Negotiation"
        if response.json()["success"]:
            result = {"code": 1, "msg": f"店铺{shop_abbr}：核价提交成功，priceOrderId：{price_order_id}，SKU数：{len(sku_list)} | 核价次数上限 {modify_times}",
                      "data": response.json(), "remarks": remarks}
        elif response.json()["errorMsg"] == official_return_msg:
            result = {"code": 1, "msg": f"店铺{shop_abbr}：核价重复修改，未执行，priceOrderId：{price_order_id} | 核价次数上限 {modify_times}",
                      "data": response.json(),
                      "remarks": remarks}
        else:
            result = {"code": -1, "msg": f"店铺{shop_abbr}：核价失败，priceOrderId：{price_order_id} | 核价次数上限 {modify_times}", "data": response.json(),
                      "remarks": remarks}

        if result["code"] == 1:
            auto_print_logger(result, success_type="i", main_task_id=main_task_id)
        else:
            auto_print_logger(result, success_type="e", main_task_id=main_task_id)

        return result

    # 异常处理部分也补充modify_times日志
    except RuntimeError as e:
        result = {"code": -1, "msg": f"店铺{shop_abbr}：检测到手动停止信号，正在退出 | 核价次数上限 {modify_times}", "data": None, "remarks": f"{e}"}
        auto_print_logger(result, success_type="e", main_task_id=main_task_id)
        return result

    except Exception as e:
        result = {"code": -1, "msg": f"店铺{shop_abbr}：批量提交失败 | 核价次数上限 {modify_times}", "data": None, "remarks": f"{e}"}
        auto_print_logger(result, success_type="e", main_task_id=main_task_id)
        return result



def calculate_supplier_result(
        shop_abbr,
        supply_price,
        _base_price,
        _ideal_price,
        sku_item,
        modify_times
    ):
    """
    根据价格和申报次数计算supplierResult
    :param supply_price: 申报价
    :param base_price: 基础价
    :param ideal_price: 理想价
    :param sku_item: 包含次数的字典，需有"times"键
    :return: int - 1=提交，2=重新申报，3=放弃
    """
    if _base_price:
        base_price = _base_price * 100
    else:
        base_price = None
        warning_msg = f"店铺{shop_abbr}：类目{sku_item['leimu']}, 尺寸{sku_item['size']}, 底价未填写"
        logger.error(warning_msg)
        write_warning_to_file(warning_msg)
        return -1

    if _ideal_price:
        ideal_price = _ideal_price * 100
    else:
        ideal_price = None

    # 校验必填参数
    if "times" not in sku_item:
        raise KeyError(f"店铺{shop_abbr}：核价sku_item字典中缺少'times'键")
    declare_times = sku_item["times"]
    if not isinstance(declare_times, int) or declare_times < 0:
        raise ValueError(f"店铺{shop_abbr}：核价sku_item['times']必须是非负整数")


    # print(f"sku_item: {sku_item}的")
    print(f"sku申报价 {supply_price} 底价 {base_price} 理想价 {ideal_price} 申报次数 {declare_times} 核价次数上限 {modify_times}")

    # 核心规则逻辑
    if ideal_price:
        if supply_price < base_price:
            return 2 if declare_times < modify_times else 3
        elif base_price <= supply_price < ideal_price:
            return 2 if declare_times < modify_times else 1
        else:  # 申报价 ≥ 理想价
            return 1
    else:
        if supply_price < base_price:
            return 2 if declare_times < modify_times else 3
        else:  # 申报价 ≥ 基础价
            return 2 if declare_times < modify_times else 1


def modify_price(
        uid,
        headers: dict,
        cookies: dict,
        sku_item: dict,
        minu_price: float,
        modify_times: int,
        price_cache: dict,
        shop_abbr: str,
        main_task_id=None
    ) -> dict[str, int | str]:
    """
    封装 modifyPrice 批量改价请求，使用统一认证请求工具
    :return 改价结果
    """
    _result = {
        "code": 0,
        "msg": f"店铺{shop_abbr}：SKU={sku_item['skuId']} 修改价格未执行，请检查或重试",
    }

    if type(sku_item['suggest_supply_price']) == str or type(sku_item['suggest_supply_price']) == int:
        supply_price = int(sku_item['suggest_supply_price'])
    else:
        return {"code": -1, "msg": f"店铺{shop_abbr}：核价接口未返回推荐价"}

    base_price, ideal_price = get_price_info(price_cache, sku_item['leimu'], sku_item['size'])

    supplier_result = calculate_supplier_result(shop_abbr=shop_abbr, supply_price=supply_price, _base_price=base_price, _ideal_price=ideal_price, sku_item=sku_item, modify_times=modify_times)

    if supplier_result == -1:
        return {"code": -1, "msg": f"店铺{shop_abbr}：核价失败", "data": None, "remarks": "底价未设置"}

    if supplier_result not in (1, 2, 3):
        return {"code": -1, "msg": f"店铺{shop_abbr}：核价supplier_result返回值错误", "data": None, "remarks": "supplier_result返回值错误"}

    if supplier_result == 1 or supplier_result == 2:
        # 提交或重新申报
        if supplier_result == 2:
            supply_price = int(sku_item['current_price'] - minu_price * 100)

            msg = f"重新提交报价：skuId：{sku_item['skuId']}"
            remarks = f"店铺{shop_abbr}：准备重新提交报价：skuId：{sku_item['skuId']}，返回价{sku_item['suggest_supply_price'] / 100.00}，申报价{supply_price / 100.00}，底价{base_price}，理想价{ideal_price if ideal_price else '空'}，次数{sku_item['times']}，核价次数上限 {modify_times}"
        else:
            msg = f"确认调整报价：skuId：{sku_item['skuId']}"
            remarks = f"店铺{shop_abbr}：准备确认调整为申报价格：skuId：{sku_item['skuId']}，返回价{sku_item['suggest_supply_price'] / 100.00}，确认申报价{supply_price / 100.00}，底价{base_price}，理想价{ideal_price if ideal_price else '空'}，次数{sku_item['times']}，核价次数上限 {modify_times}"


        url = "https://agentseller.temu.com/api/kiana/mms/magneto/price/bargain-no-bom"
        payload = {"supplierResult": supplier_result, "priceOrderId": sku_item['priceOrderId'],
                   "items": [{"productSkuId": sku_item['skuId'], "price": supply_price}], "bargainReasonList": []}

    elif supplier_result == 3:
        # 放弃
        msg = f"放弃报价：skuId：{sku_item['skuId']}"
        remarks = f"店铺{shop_abbr}：准备放弃调整报价：skuId：{sku_item['skuId']}，返回价{sku_item['suggest_supply_price'] / 100.00}，申报价{supply_price / 100.00}，底价{base_price}，理想价{ideal_price if ideal_price else '空'}，次数{sku_item['times']}，核价次数上限 {modify_times}"
        url = "https://agentseller.temu.com/api/kiana/mms/magneto/api/price-review-order/no-bom/review"
        payload = {"priceOrderId": sku_item['priceOrderId']}

    else:
        return _result

    print(remarks)

    auto_print_logger(msg=msg, remarks=remarks, success_type="i", main_task_id=main_task_id)

    response = send_req(
        method="POST",
        headers=headers,
        cookies=cookies,
        url=url,
        json=payload,
        uid=uid,
    )

    if not response:
        remarks = f"店铺{shop_abbr}：异常，响应结果为空"
        logger.error(remarks)
    elif response.status_code != 200:
        remarks = f"店铺{shop_abbr}：网络异常或请求被拦截，状态码:{response.status_code}，响应: {response.json()}"
        logger.error(remarks)
    else:
        remarks = response.json().get("errorMsg", "")
        if remarks is None:
            remarks = ""

    official_return_msg = "The current state is Pending Pricing, and the command cannot be executed: Non-Disassembled Price Negotiation"

    if response.json()["success"]:
        _result = {"code": 1, "msg": f"店铺{shop_abbr}：核价操作执行成功，skuId：{sku_item['skuId']}",
                   "data": response.json(), "remarks": remarks}
    elif response.json()["errorMsg"] == official_return_msg:
        _result = {"code": 1, "msg": f"店铺{shop_abbr}：核价重复修改，未执行，skuId：{sku_item['skuId']}",
                   "data": response.json(), "remarks": remarks}
    else:
        _result = {"code": -1, "msg": f"店铺{shop_abbr}：核价操作执行失败，skuId：{sku_item['skuId']}",
                   "data": response.json(), "remarks": remarks}

    auto_print_logger(_result)

    return _result


def modify_price_thread(
        uid,
        headers,
        cookies,
        page,
        minu_price,
        modify_times,
        shop_abbr,
        main_task_id=None,
        spu_id_list=None
    ):
    """单页核价任务执行函数（适配分组提交）"""
    total_modified = 0
    total_failed = 0
    logger.info(f"店铺{shop_abbr}：开始处理第 {page} 页核价任务...")
    try:
        file_path = rf"{modify_price_excels_path}{shop_abbr}_工具配置表.xlsx"
        price_cache = load_price_data(file_path)
    except Exception as e:
        logger.error(f"店铺{shop_abbr}：加载价格配置表失败：{e}")
        return {
            "code": -1,
            "msg": f"店铺{shop_abbr}：加载价格配置表失败：{e}",
            "data": None,
            "remarks": f"加载价格配置表失败"
        }
    try:
        # 获取当前页核价列表
        resp = get_up_new_lifecycle_list(uid, headers, cookies, page_num=page, shop_abbr=shop_abbr, spu_id_list=spu_id_list)
        if resp["code"] != 1:
            logger.error(f"店铺{shop_abbr}：第{page}页获取核价列表失败：{resp['remarks']}")
            return {"page": page, "success": 0, "failed": 0, "msg": resp['msg']}

        # 核心改造：按priceOrderId分组
        price_order_groups = group_sku_by_price_order(shop_abbr, resp["data"])
        if not price_order_groups:
            logger.info(f"店铺{shop_abbr}：第{page}页无待处理SKU")
            return {"page": page, "success": 0, "failed": 0, "msg": f"店铺{shop_abbr}：无待处理SKU"}

        # ========== 检查任务是否被停止 ==========
        if main_task_id:
            check_task_stopped(get_task_log_manager(), main_task_id)

        # 按分组提交
        submit_result = submit_price_by_group(uid, headers, cookies, price_order_groups, minu_price, modify_times, price_cache, shop_abbr,
                                              main_task_id=main_task_id)
        total_modified = submit_result["success"]
        total_failed = submit_result["failed"]

        remarks = f"成功 {total_modified} 个SKU | 失败 {total_failed} 个"
        auto_print_logger(msg=f"店铺{shop_abbr}：第{page}页处理完成", remarks=remarks, success_type="s", main_task_id=main_task_id)
        return {"page": page, "success": total_modified, "failed": total_failed, "msg": f"店铺{shop_abbr}：核价处理完成"}

    except RuntimeError as e:
        auto_print_logger(msg=f"店铺{shop_abbr}： 子线程检测到任务停止，正在退出", remarks=f"当前页码={page}", success_type="w", main_task_id=main_task_id)

        return {"page": page, "success": total_modified, "failed": total_failed, "msg": f"店铺{shop_abbr}：子线程检测到任务停止"}

    except Exception as e:
        auto_print_logger(msg=f"店铺{shop_abbr}：第{page}页核价任务执行异常：", remarks=f"原因：{e}", success_type="e", main_task_id=main_task_id)
        return {"page": page, "success": total_modified, "failed": total_failed, "msg": f"店铺{shop_abbr}：核价执行异常：{str(e)}"}


def all_modify_price(
        uid: int,
        headers: dict,
        cookies: dict,
        minu_price: float,
        modify_times: int,
        shop_abbr: str,
        spu_id_list: list = None,
        mall_id: int = None,
        main_task_id: str = None,
        wait_all_complete: bool = True,  # 是否等待所有任务完成
        timeout: int = 3600  # 任务等待超时时间（秒），默认1小时
    ) -> dict:
    """
    批量改价主函数（适配任务管理器，按店铺_核价分组限制并发）
    核心修改：移除重试逻辑，直接使用get_task_result设置长超时等待
    """
    # 初始化任务ID列表（用于后续追踪）
    task_ids = []
    total_pages = 0
    logger.info(f"店铺{shop_abbr}：开始批量核价任务 | 当前配置：每次降价金额 {minu_price} | 最大核价次数 {modify_times}")
    try:
        # 获取总页数
        resp = get_up_new_lifecycle_list(uid, headers, cookies, page_num=1, spu_id_list=spu_id_list, shop_abbr=shop_abbr)
        if resp["code"] != 1:
            logger.error(f"店铺{shop_abbr}：获取核价列表失败，无法继续：{resp['remarks']}")

            result = {
                "code": -1,
                "msg": f"店铺{shop_abbr}：获取核价列表失败：{resp['msg']}",
                "data": resp["data"],
                "remarks": resp['remarks']
            }
            auto_print_logger(result, success_type="e", main_task_id=main_task_id)

            return result

        data = get_price_groups(shop_abbr, resp["data"])
        total_sku = data["total"]
        total_pages = int(total_sku / 100) + 1 if total_sku % 100 != 0 else int(total_sku / 100)

        msg = f"店铺{shop_abbr}：核价任务初始化 | 总SKU数：{total_sku} | 总页数：{total_pages}"
        # logger.info(msg)
        auto_print_logger(msg=msg, success_type="i", main_task_id=main_task_id)
        # ========== 检查任务是否被停止 ==========
        if main_task_id:
            check_task_stopped(get_task_log_manager(), main_task_id)

        if total_pages <= 1:
            logger.info(f"店铺{shop_abbr}：核价页数为1页，仅主线程执行")
            task_kwargs = {
                "headers": headers,
                "cookies": cookies,
                "page": 1,
                "minu_price": minu_price,
                "modify_times": modify_times,
                "shop_abbr": shop_abbr,
                "uid": uid,
                "main_task_id": main_task_id,
                "spu_id_list": spu_id_list
            }
            modify_price_thread(**task_kwargs)

        else:
            # 提交所有页的任务（按店铺_核价分组）
            for page in range(1, total_pages + 1):
                task_kwargs = {
                    "headers": headers,
                    "cookies": cookies,
                    "page": page,
                    "minu_price": minu_price,
                    "modify_times": modify_times,
                    "shop_abbr": shop_abbr,
                    "uid": uid,
                    "main_task_id": main_task_id,
                    "spu_id_list": spu_id_list
                }
                task_id = get_task_log_manager().add_task(
                    target_func=modify_price_thread, **task_kwargs,
                    task_group=f"{shop_abbr}_核价",
                    mall_id=mall_id,
                    parent_task_id=main_task_id,
                    is_main_task=0,
                )

                if task_id:
                    task_ids.append(task_id)
                    remarks = f"店铺{shop_abbr}：成功提交第{page}页核价任务 | 任务ID：{task_id}"
                    # logger.info(remarks)
                    auto_print_logger(remarks=remarks, success_type="i", main_task_id=main_task_id)

                else:
                    remarks = f"店铺{shop_abbr}：提交第{page}页核价任务失败"
                    # logger.error(remarks)
                    auto_print_logger(remarks=remarks, success_type="e", main_task_id=main_task_id)

                    continue


        # 如果不等待任务完成，直接返回
        if not wait_all_complete:
            remarks = f"店铺{shop_abbr}：共提交 {len(task_ids)} 个核价任务（总页数：{total_pages}），任务执行中"
            return {
                "code": 1,
                "msg": remarks,
                "data": {"task_ids": task_ids, "total_pages": total_pages},
                "remarks": remarks
            }

        # logger.info(f"店铺{shop_abbr}：等待 {len(task_ids)} 个核价任务执行完成（超时时间：{timeout}秒）...")
        total_modified = 0
        total_failed = 0
        task_results = []

        for task_id in task_ids:
            try:
                # 直接调用get_task_result，设置长超时时间
                # 关键修改：单次等待timeout秒，不再做重试，避免频繁超时
                result = get_task_log_manager().get_task_result(
                    task_id=task_id,
                    timeout=timeout  # 使用传入的超时时间（默认3600秒/1小时）
                )

                task_results.append({"task_id": task_id, "result": result})

                # 汇总结果
                if isinstance(result, dict):
                    total_modified += result.get("success", 0)
                    total_failed += result.get("failed", 0)
                else:
                    # logger.warning(f"店铺{shop_abbr}：任务{task_id}返回结果格式异常：{result}")
                    remarks = f"店铺{shop_abbr}：任务{task_id}返回结果格式异常：{result}"
                    auto_print_logger(remarks=remarks, success_type="e", main_task_id=main_task_id)

                    total_failed += 0  # 任务无有效结果，按失败处理

            except TimeoutError:
                # 仅捕获超时异常，记录并继续处理下一个任务
                # logger.error(f"店铺{shop_abbr}：任务{task_id}等待超时（已等待{timeout}秒）")
                remarks = f"店铺{shop_abbr}：任务{task_id}等待超时（已等待{timeout}秒）"
                auto_print_logger(remarks=remarks, success_type="e", main_task_id=main_task_id)

                task_results.append({"task_id": task_id, "result": None, "error": "timeout"})
                total_failed += 0  # 超时任务按失败处理
            except Exception as e:
                # 捕获其他异常，避免中断整体流程
                # logger.error(f"店铺{shop_abbr}：获取任务{task_id}结果异常：{e}")
                remarks = f"店铺{shop_abbr}：获取任务{task_id}结果异常：{e}"
                auto_print_logger(remarks=remarks, success_type="e", main_task_id=main_task_id)

                task_results.append({"task_id": task_id, "result": None, "error": str(e)})
                total_failed += 0

        # 汇总最终结果
        remarks = f"核价任务完成"
        # logger.info(remarks)
        auto_print_logger(remarks=remarks, success_type="i", main_task_id=main_task_id)

        result =  {
            "code": 1 if total_failed == 0 else -1,
            "msg": f"店铺{shop_abbr}：批量改价完成",
            "data": {
                "total_pages": total_pages,
                "submitted_tasks": len(task_ids),
                "success_sku": total_modified,
                "failed_sku": total_failed,
                "task_results": task_results
            },
            "remarks": remarks
        }
        auto_print_logger(result, main_task_id=main_task_id, success_type="i")
        return result

    except RuntimeError as e:
        # logger.warning(f"店铺{shop_abbr}：主线程检测到任务停止，正在退出")
        # 获取已处理的成功和失败数量
        success_count = 0
        failed_count = 0
        for task_id in task_ids:
            task_result = get_task_log_manager().get_task_result(task_id, timeout=1000)
            if task_result and task_result.get("code") == 1:
                task_data = task_result.get("data", {})
                success_count += task_data.get("success_count", 0)
                failed_count += task_data.get("failed_count", 0)
        
        remarks = f"停止原因：{str(e)} | 已处理成功{success_count}条，失败{failed_count}条"
        result = {
            "code": -1,
            "msg": f"店铺{shop_abbr}： 任务被手动停止",
            "data": {"task_ids": task_ids, "total_pages": total_pages, "success_count": success_count, "failed_count": failed_count},
            "remarks": remarks
        }
        auto_print_logger(result, success_type="w", main_task_id=main_task_id)
        return result

    except Exception as e:
        # logger.error(f"店铺{shop_abbr}：批量改价主流程异常：{e}")
        result = {
            "code": -1,
            "msg": f"店铺{shop_abbr}：批量改价异常：",
            "data": {"task_ids": task_ids, "total_pages": total_pages},
            "remarks": f"{str(e)}"
        }
        auto_print_logger(result, success_type="e", main_task_id=main_task_id)
        return result

