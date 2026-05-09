from loguru import logger

from utils.log_utils import auto_print_logger
from utils.send_temu_req import send_req


# ====== 查询备货单列表 ======
def query_sub_order_list(shop_abbr: str, headers: dict, cookies: dict, uid, page_no: int = 1, page_size: int = 100, urgency_type: int = 1, is_custom_goods: bool = False, status_list: list = None, one_dimension_sort: dict = None, max_retries: int = 5) -> dict:
    """
    查询备货单列表
    :return:
    """
    _result = {}
    for attempt in range(1, max_retries + 1):

        url = "https://agentseller.temu.com/mms/venom/api/supplier/purchase/manager/querySubOrderList"

        if status_list is None:
            status_list = [1]
        if one_dimension_sort is None:
            one_dimension_sort = {
                "firstOrderByParam": "expectLatestDeliverTime",
                "firstOrderByDesc": 0
            }

        payload = {
            "pageNo": page_no,
            "pageSize": page_size,
            "urgencyType": urgency_type,
            "isCustomGoods": is_custom_goods,
            "statusList": status_list,
            "oneDimensionSort": one_dimension_sort
        }

        response = send_req(
            method="POST",
            headers=headers,
            cookies=cookies,
            url=url,
            json=payload,
            uid=uid
        )

        if not response:
            remarks = f"异常，响应结果为空"
        elif response.status_code != 200:
            remarks = f"网络异常或请求被拦截，状态码:{response.status_code}，响应: {response.json()}"
        else:
            remarks = response.json().get("errorMsg", "")
            if remarks is None:
                remarks = ""

        if response.json()["success"]:
            _result = {"code": 1, "msg": f"店铺{shop_abbr}：查询备货单列表成功", "data": response.json(), "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：查询备货单列表失败", "data": response.json(), "remarks": remarks}
            continue

    auto_print_logger(_result)

    return _result


# ====== 解析备货单号（只提取可加入发货台的） ======
def extract_sub_order_sns(query_result: dict) -> list:
    """
    从查询备货单列表的响应结果中，提取可加入发货台的备货单号
    :param query_result: query_sub_order_list 的返回结果（标准 _result 结构）
    :return: 备货单号列表 ["WB2605081074455", ...]
    """
    if query_result.get("code") != 1:
        logger.warning(f"提取备货单号失败：{query_result.get('msg', '未知错误')}")
        return []

    data = query_result.get("data", {})
    if not data:
        logger.warning("提取备货单号失败：响应数据为空")
        return []

    result_data = data.get("result", {})
    sub_order_list = result_data.get("subOrderForSupplierList", [])
    if not sub_order_list:
        logger.info("提取备货单号：当前页无可加入发货台的备货单")
        return []

    sn_list = []
    for order in sub_order_list:
        if order.get("isCanJoinDeliverPlatform") is True:
            sn = order.get("subPurchaseOrderSn")
            if sn:
                sn_list.append(sn)

    logger.info(f"提取备货单号：共提取 {len(sn_list)} 个可加入发货台的备货单")
    return sn_list


# ====== 批量加入发货台 ======
def batch_join_delivery_platform(shop_abbr: str, headers: dict, cookies: dict, uid, sub_order_sn_list: list, max_retries: int = 5) -> dict:
    """
    批量将备货单加入发货台
    :param sub_order_sn_list: 备货单号列表 ["WB2605081074455", ...]
    :return:
    """
    _result = {}
    for attempt in range(1, max_retries + 1):

        url = "https://agentseller.temu.com/mms/venom/api/supplier/purchase/manager/batchJoinDeliveryGoodsOrderPlatformV2ForUrgency"

        payload = {
            "joinDeliveryPlatformRequestList": [
                {"subPurchaseOrderSn": sn} for sn in sub_order_sn_list
            ]
        }

        response = send_req(
            method="POST",
            headers=headers,
            cookies=cookies,
            url=url,
            json=payload,
            uid=uid
        )

        if not response:
            remarks = f"异常，响应结果为空"
        elif response.status_code != 200:
            remarks = f"网络异常或请求被拦截，状态码:{response.status_code}，响应: {response.json()}"
        else:
            remarks = response.json().get("errorMsg", "")
            if remarks is None:
                remarks = ""

        response_json = response.json()
        if response_json["success"]:
            result_data = response_json.get("result", {})
            error_info_list = result_data.get("errorInfoList", []) or []
            failed_sns = [item["id"] for item in error_info_list if item.get("id")]
            success_sns = [sn for sn in sub_order_sn_list if sn not in failed_sns]
            response_json["_parsed"] = {"success_sns": success_sns, "failed_sns": failed_sns}
            _result = {"code": 1, "msg": f"店铺{shop_abbr}：批量加入发货台成功，数量: {len(sub_order_sn_list)}", "data": response_json, "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：批量加入发货台失败", "data": response_json, "remarks": remarks}
            continue

    auto_print_logger(_result)

    return _result


# ====== 批量加入发货台总流程 ======
def batch_join_delivery_platform_main(shop_abbr: str, headers: dict, cookies: dict, uid, batch_size: int = 100, max_pages: int = None, urgency_type: int = 1, status_list: list = None) -> dict:
    """
    批量加入发货台总流程：翻页查询 → 解析单号 → 凑满提交，循环直到结束
    :param batch_size: 每批提交数量，默认100
    :param max_pages: 最大翻页数，None 表示查询到最后一页
    :param urgency_type: 紧急类型，默认1（紧急备货单）
    :param status_list: 备货单状态列表，默认 [1]
    :return: 汇总结果
    """
    if status_list is None:
        status_list = [1]

    pool = []
    page_no = 1
    all_batch_results = []
    total_processed = 0

    all_success_sns = []
    all_failed_sns = []

    while True:
        logger.info(f"批量加入发货台：查询第 {page_no} 页")

        query_result = query_sub_order_list(
            shop_abbr=shop_abbr,
            headers=headers,
            cookies=cookies,
            uid=uid,
            page_no=page_no,
            page_size=batch_size,
            urgency_type=urgency_type,
            status_list=status_list
        )

        if query_result.get("code") != 1:
            logger.error(f"批量加入发货台：第 {page_no} 页查询失败，{query_result.get('msg', '')}")
            break

        sn_list = extract_sub_order_sns(query_result)
        pool.extend(sn_list)
        logger.info(f"批量加入发货台：第 {page_no} 页提取 {len(sn_list)} 个单号，当前池子共 {len(pool)} 个")

        while len(pool) >= batch_size:
            batch = pool[:batch_size]
            pool = pool[batch_size:]
            total_processed += len(batch)
            logger.info(f"批量加入发货台：提交一批 {len(batch)} 个单号，累计已处理 {total_processed} 个")
            batch_result = batch_join_delivery_platform(
                shop_abbr=shop_abbr,
                headers=headers,
                cookies=cookies,
                uid=uid,
                sub_order_sn_list=batch
            )
            all_batch_results.append(batch_result)
            parsed = batch_result.get("data", {}).get("_parsed", {})
            all_success_sns.extend(parsed.get("success_sns", []))
            all_failed_sns.extend(parsed.get("failed_sns", []))

        data = query_result.get("data", {})
        result_data = data.get("result", {}) if data else {}
        sub_order_list = result_data.get("subOrderForSupplierList", [])
        total = result_data.get("total", 0)

        if len(sub_order_list) < batch_size:
            logger.info(f"批量加入发货台：第 {page_no} 页数据不足 {batch_size} 条（实际 {len(sub_order_list)} 条），已到最后一页")
            break

        if max_pages is not None and page_no >= max_pages:
            logger.info(f"批量加入发货台：达到最大翻页数 {max_pages}，停止翻页")
            break

        page_no += 1

    if pool:
        total_processed += len(pool)
        logger.info(f"批量加入发货台：提交最后一批 {len(pool)} 个单号，累计已处理 {total_processed} 个")
        batch_result = batch_join_delivery_platform(
            shop_abbr=shop_abbr,
            headers=headers,
            cookies=cookies,
            uid=uid,
            sub_order_sn_list=pool
        )
        all_batch_results.append(batch_result)
        parsed = batch_result.get("data", {}).get("_parsed", {})
        all_success_sns.extend(parsed.get("success_sns", []))
        all_failed_sns.extend(parsed.get("failed_sns", []))
        pool = []

    success_count = sum(1 for r in all_batch_results if r.get("code") == 1)
    fail_count = len(all_batch_results) - success_count

    summary = {
        "code": 1 if fail_count == 0 else -1,
        "msg": f"店铺{shop_abbr}：批量加入发货台完成，共提交 {total_processed} 个备货单，{len(all_batch_results)} 个批次（成功 {success_count} 批次，失败 {fail_count} 批次）",
        "data": {
            "total_processed": total_processed,
            "batch_count": len(all_batch_results),
            "success_batch_count": success_count,
            "fail_batch_count": fail_count,
            "batch_results": all_batch_results,
            "success_order_sns": all_success_sns,
            "failed_order_sns": all_failed_sns
        },
        "remarks": ""
    }

    auto_print_logger(summary)

    return summary


# ====== 从批量加入发货台结果中提取失败SPU ID ======
def extract_failed_spu_ids_from_batch_results(batch_results: list) -> list:
    """
    从批量加入发货台的批次结果中，提取所有失败的 SPU ID
    :param batch_results: batch_join_delivery_platform_main 返回的 data.batch_results 列表
    :return: 去重后的 SPU ID 列表 [4938487910, ...]
    """
    import re

    spu_ids = set()
    for batch_result in batch_results:
        if batch_result.get("code") != 1:
            continue

        response_data = batch_result.get("data", {})
        result_data = response_data.get("result", {})
        if result_data.get("isSuccess") is True:
            continue

        error_info_list = result_data.get("errorInfoList", [])
        for error_info in error_info_list:
            extra_info = error_info.get("extraInfoMap")
            if not extra_info:
                continue
            url = extra_info.get("url", "")
            match = re.search(r"spuId=(\d+)", url)
            if match:
                spu_ids.add(int(match.group(1)))

    return list(spu_ids)


# ====== 批量加入发货台（带重试：失败自动上传实拍图后重试） ======
def batch_join_delivery_with_retry(shop_abbr: str, headers: dict, cookies: dict, uid, max_cycles: int = 5, batch_size: int = 100, max_pages: int = None, urgency_type: int = 1, status_list: list = None, skip_upload_pic: bool = False, custom_fixed_upload_img: bool = False, mall_id=None, main_task_id=None) -> dict:
    """
    批量加入发货台总入口（带失败重试）：执行加入发货台 → 解析失败SPU → 上传实拍图 → 重新尝试，最多重试 max_cycles 轮
    :param max_cycles: 最大重试轮次，默认5
    :param batch_size: 每批提交数量，透传给 batch_join_delivery_platform_main
    :param max_pages: 最大翻页数，透传
    :param urgency_type: 紧急类型，透传
    :param status_list: 备货单状态列表，透传
    :param skip_upload_pic: 是否跳过上传实拍图，True 则失败后直接结束输出失败列表
    :param custom_fixed_upload_img: 上传实拍图时是否使用固定标签
    :param mall_id: 店铺 mall_id
    :param main_task_id: 主任务ID
    :return: 汇总结果
    """
    from temu_modules.temu_function.upload_real_pic import final_upload_real_pic

    if status_list is None:
        status_list = [1]

    cycle = 1
    all_cycle_results = []
    remaining_failed_spu_ids = []
    all_success_order_sns = []
    all_failed_order_sns = []

    while cycle <= max_cycles:
        logger.info(f"批量加入发货台（带重试）：第 {cycle}/{max_cycles} 轮开始")

        main_result = batch_join_delivery_platform_main(
            shop_abbr=shop_abbr,
            headers=headers,
            cookies=cookies,
            uid=uid,
            batch_size=batch_size,
            max_pages=max_pages,
            urgency_type=urgency_type,
            status_list=status_list
        )

        batch_results = main_result.get("data", {}).get("batch_results", [])
        failed_spu_ids = extract_failed_spu_ids_from_batch_results(batch_results)

        cycle_success_sns = main_result.get("data", {}).get("success_order_sns", [])
        cycle_failed_sns = main_result.get("data", {}).get("failed_order_sns", [])
        all_success_order_sns.extend(cycle_success_sns)
        all_failed_order_sns.extend(cycle_failed_sns)

        cycle_record = {
            "cycle": cycle,
            "main_result": main_result,
            "failed_spu_ids": failed_spu_ids
        }
        all_cycle_results.append(cycle_record)

        if not failed_spu_ids:
            logger.info(f"批量加入发货台（带重试）：第 {cycle} 轮全部成功，无需重试")
            remaining_failed_spu_ids = []
            break

        logger.warning(f"批量加入发货台（带重试）：第 {cycle} 轮有 {len(failed_spu_ids)} 个SPU失败: {failed_spu_ids}")

        if cycle >= max_cycles or skip_upload_pic:
            if skip_upload_pic:
                logger.info(f"批量加入发货台（带重试）：已勾选不上传实拍图，直接结束")
            else:
                logger.warning(f"批量加入发货台（带重试）：已达最大重试次数 {max_cycles}")
            remaining_failed_spu_ids = failed_spu_ids
            break

        logger.info(f"批量加入发货台（带重试）：第 {cycle} 轮上传失败SPU的实拍图，共 {len(failed_spu_ids)} 个")
        upload_result = final_upload_real_pic(
            headers=headers,
            cookies=cookies,
            uid=uid,
            shop_abbr=shop_abbr,
            input_check_type_list=[],
            input_rapid_screen_status_list=[],
            input_spu_id_list=failed_spu_ids,
            custom_fixed_upload_img=custom_fixed_upload_img,
            mall_id=mall_id,
            main_task_id=main_task_id
        )
        logger.info(f"批量加入发货台（带重试）：第 {cycle} 轮实拍图上传结果: {upload_result.get('msg', '')}")

        cycle += 1

    total_all_cycles = sum(len(ar["main_result"].get("data", {}).get("batch_results", [])) for ar in all_cycle_results)
    success_cycles = sum(1 for ar in all_cycle_results if not ar["failed_spu_ids"])

    msg_parts = [f"店铺{shop_abbr}：批量加入发货台（带重试）完成，共执行 {cycle} 轮"]
    msg_parts.append(f"成功 {len(all_success_order_sns)} 个发货单")
    if all_failed_order_sns:
        msg_parts.append(f"失败 {len(all_failed_order_sns)} 个发货单")
    if remaining_failed_spu_ids:
        msg_parts.append(f"失败SPU列表: {remaining_failed_spu_ids}")
    else:
        msg_parts.append("全部成功")
    summary_msg = " | ".join(msg_parts)

    summary = {
        "code": 1 if not remaining_failed_spu_ids else -1,
        "msg": summary_msg,
        "data": {
            "total_cycles": cycle,
            "success_cycles": success_cycles,
            "success_order_sns": all_success_order_sns,
            "failed_order_sns": all_failed_order_sns,
            "remaining_failed_spu_ids": remaining_failed_spu_ids,
            "cycle_results": all_cycle_results
        },
        "remarks": ""
    }

    auto_print_logger(summary)

    return summary
