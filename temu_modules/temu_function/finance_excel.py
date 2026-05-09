import calendar
import json
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from utils.TemuBase import get_shop_info_db, test_connect_shop
from utils.log_utils import auto_print_logger
from utils.send_temu_req import send_req


def get_export_history_page(
    uid: str,
    headers: dict,
    cookies: dict,
    task_type: int,
    page_num: int = 1,
    max_retries: int = 5,
) -> dict[str, int | str]:
    """
    发货单列表
    :param task_type: task_type
    :param max_retries:
    :return {"code": 1, "msg": "获取核价列表成功", "data": 完整的json, "remarks": remarks}
    """

    _result = {}
    for attempt in range(1, max_retries + 1):
        url = "https://seller.kuajingmaihuo.com/api/merchant/file/export/history/page"
        payload = {"taskType": task_type, "pageSize": 100, "pageNum": page_num}

        if not task_type:
            logger.error("请传入 task_type")

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
            _result = {"code": 1, "msg": "获取账单下载列表成功", "data": response.json(), "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": "获取账单下载列表失败", "data": response.json(), "remarks": remarks}
            continue

    auto_print_logger(_result)

    return _result

def extract_export_history_page(download_page_json: dict):
    """提取导出历史页面数据，增加错误处理"""
    try:
        if not download_page_json or "data" not in download_page_json:
            logger.warning(f"extract_export_history_page: 无效的输入数据，缺少'data'键")
            return []
        
        data = download_page_json["data"]
        if not data or "result" not in data:
            logger.warning(f"extract_export_history_page: data中缺少'result'键")
            return []
        
        items = []
        for item in data["result"].get("merchantMerchantFileExportHistoryList", []):
            if item.get("status") == 2:
                item = {
                    "begin_time": item.get("searchExportTimeBegin"),
                    "end_time": item.get("searchExportTimeEnd"),
                    "download_id": item.get("id"),
                    "query_params": {
                        "params": item.get("agentSellerExportParams"),
                        "sign": item.get("agentSellerExportSign"),
                    }
                }
                items.append(item)

        return items
    except Exception as e:
        logger.error(f"extract_export_history_page: 解析数据时出错: {e}", exc_info=True)
        return []


def get_download_export_params(
    uid: str,
    headers: dict,
    cookies: dict,
    query_params: dict,
    region: str,
    max_retries: int = 5,
) -> dict[str, int | str]:
    """
    获得其他区的下载id
    :param query_params: {"params": , "sign":}
    :param max_retries:
    """

    _result = {}
    for attempt in range(1, max_retries + 1):
        if region == "us":
            host = "agentseller-us.temu.com"
            task_type = 31
        elif region == "eu":
            host = "agentseller-eu.temu.com"
            task_type = 31
        elif region == "global":
            task_type = 31
            host = "agentseller.temu.com"
        elif region == "卖家中心":
            task_type = 19
            host = "seller.kuajingmaihuo.com"

        url = f"https://{host}/api/merchant/file/export"
        payload = {
            "taskType": task_type,
            "params": query_params.get("params"),
            "sign": query_params.get("sign"),
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
            _result = {"code": 1, "msg": "获取下载账单表参数成功", "data": response.json(), "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": "获取下载账单表参数失败", "data": response.json(), "remarks": remarks}
            continue

    auto_print_logger(_result)

    return _result


def do_download_export(
    uid: str,
    headers: dict,
    cookies: dict,
    download_id: int,
    region: str,
    max_retries: int = 5,
    retry_interval: int = 3,
) -> dict[str, int | str]:
    """
    获取表格直链下载地址，cookie需要根据地区使用对应的cookies
    https://{host}/api/merchant/file/export/download
    :param max_retries: 最大重试次数
    :param retry_interval: 重试间隔秒数（当导出任务未完成时等待）
    :return {"code": 1, "msg": "下载账单表成功", "data": 完整的json, "remarks": remarks}
    """
    import time

    _result = {}
    for attempt in range(1, max_retries + 1):
        if region == "us":
            host = "agentseller-us.temu.com"
            task_type = 31
        elif region == "eu":
            host = "agentseller-eu.temu.com"
            task_type = 31
        elif region == "global":
            task_type = 31
            host = "agentseller.temu.com"
        else:
            task_type = 19
            host = "seller.kuajingmaihuo.com"

        url = f"https://{host}/api/merchant/file/export/download"
        # url = "https://seller.kuajingmaihuo.com/api/merchant/file/export/download"

        payload = {"id":download_id,"taskType":task_type}

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
            _result = {"code": 1, "msg": "获取下载账单表直链下载地址成功", "data": response.json(), "remarks": remarks}
            break
        else:
            error_msg = response.json().get("errorMsg", "")
            _result = {"code": -1, "msg": "获取下载账单表直链下载地址失败", "data": response.json(), "remarks": remarks}

            # 如果是导出任务未完成，等待后重试
            if error_msg and "未完成" in error_msg:
                if attempt < max_retries:
                    logger.info(f"⏳ 导出任务未完成，等待 {retry_interval} 秒后重试（第{attempt}/{max_retries}次）")
                    time.sleep(retry_interval)
            continue

    auto_print_logger(_result)

    return _result

def get_global_download_export_url(
    query_params: dict,
    region: str,
) -> str:
    """
    获取下载url 下载账务明细(卖家中心) cookie相同所以可以直接用。其他的因为cookie不同最好使用自动化登录下载
    :param query_params: {"params": , "sign":}
    """
    if region == "us":
        host = "agentseller-us.temu.com"
    elif region == "eu":
        host = "agentseller-eu.temu.com"
    else:
        host = "agentseller.temu.com"

    url = f"https://{host}/labor/bill-download-with-detail?params={query_params['params']}&sign={query_params['sign']}"

    return url



def get_date_range_timestamps(start_date_str: str, end_date_str: str = None) -> tuple:
    """
    根据输入的日期字符串，计算指定时间范围的起始和结束毫秒级时间戳。
    支持两种模式：

    模式一（默认）：仅传入一个月份字符串 "YYYY.MM"。
    - 计算该月的第一天 00:00:00 和最后一天 23:59:59 的时间戳。
    - 示例: get_date_range_timestamps("2025.4")

    模式二：传入两个具体的日期字符串 "YYYY.MM.DD"。
    - 计算这两个日期当天 00:00:00 的时间戳。
    - 结束日期的时间戳会自动调整为该天的 23:59:59。
    - **强制约束**：两个日期之间的总天数（包含头尾）不能超过31天。
    - 示例: get_date_range_timestamps("2025.4.10", "2025.4.25")

    :param start_date_str: 开始日期字符串。格式为 "YYYY.MM" 或 "YYYY.MM.DD"。
    :param end_date_str: 结束日期字符串（可选）。格式必须为 "YYYY.MM.DD"。
    :return: 一个包含两个整数的元组 (start_timestamp_ms, end_timestamp_ms)。
             如果输入无效或超出范围，则返回 (None, None)。
    """
    try:
        # --- 模式一：仅传入一个参数，按整月计算 ---
        if end_date_str is None:
            # 解析输入的年份和月份
            year, month = map(int, start_date_str.split('.'))

            # 计算该月的第一天 00:00:00
            start_date = datetime(year, month, 1)

            # 计算该月的最后一天 23:59:59
            _, last_day = calendar.monthrange(year, month)
            end_date = datetime(year, month, last_day, 23, 59, 59)

            # print(f"📅 模式一（整月）：计算 '{start_date_str}' 的时间范围...")

        # --- 模式二：传入两个参数，按自定义日期范围计算 ---
        else:
            # 解析开始和结束日期（精确到天）
            start_date = datetime.strptime(start_date_str, "%Y.%m.%d")
            end_date = datetime.strptime(end_date_str, "%Y.%m.%d")

            # 验证开始日期不能晚于结束日期
            if start_date > end_date:
                raise ValueError(f"开始日期 '{start_date_str}' 不能晚于结束日期 '{end_date_str}'。")

            # 计算总天数（包含头尾两天）
            delta = end_date - start_date
            total_days = delta.days + 1  # +1 是因为要包含结束日期当天

            # 强制约束：总天数不能超过31天
            if total_days > 31:
                raise ValueError(f"日期范围过大。总天数（包含头尾）为 {total_days} 天，不能超过 31 天。")

            # 将结束日期的时间调整为 23:59:59
            end_date = end_date.replace(hour=23, minute=59, second=59)

            # print(f"📅 模式二（自定义范围）：计算 '{start_date_str}' 到 '{end_date_str}' 的时间范围...")

        # --- 公共逻辑：转换为毫秒级时间戳 ---
        start_timestamp_ms = int(start_date.timestamp() * 1000)
        end_timestamp_ms = int(end_date.timestamp() * 1000)

        return start_timestamp_ms, end_timestamp_ms

    except ValueError as e:
        logger.error(f"❌ 输入日期月份错误: {e}")
        return None, None
    except AttributeError:
        logger.error(f"❌ 输入格式错误。请使用 'YYYY.MM' 或 'YYYY.MM.DD' 格式。")
        return None, None


def get_month_range_list(start_month_str: str, end_month_str: str) -> list:
    """
    根据输入的开始月份和结束月份，生成一个包含所有中间月份的列表。

    :param start_month_str: 开始月份字符串，格式为 "YYYY.MM"，例如 "2025.1"。
    :param end_month_str: 结束月份字符串，格式为 "YYYY.MM"，例如 "2025.3"。
    :return: 包含所有月份的列表，例如 ["2025.1", "2025.2", "2025.3"]。
    :raises ValueError: 输入格式错误或开始月份在结束月份之后时抛出。
    """
    try:
        # 1. 解析输入的字符串为 datetime 对象
        #    我们使用每个月的第一天来进行日期计算
        start_date = datetime.strptime(start_month_str, "%Y.%m")
        end_date = datetime.strptime(end_month_str, "%Y.%m")

        # 2. 验证开始月份不能晚于结束月份
        if start_date > end_date:
            raise ValueError(f"开始月份 '{start_month_str}' 不能晚于结束月份 '{end_month_str}'。")

        # 3. 生成月份列表
        month_list = []
        current_date = start_date

        # 循环，直到当前月份超过结束月份
        while current_date <= end_date:
            # 将当前日期格式化为 "YYYY.MM" 字符串并添加到列表
            month_list.append(current_date.strftime("%Y.%m"))

            # 移动到下一个月的第一天
            # 先加32天确保跨到下个月，然后用 replace(day=1) 定位到第一天
            next_month = current_date + timedelta(days=32)
            current_date = next_month.replace(day=1)

        return month_list

    except ValueError as e:
        # 捕获格式错误或日期逻辑错误
        if "does not match format" in str(e):
            raise ValueError(
                f"输入格式错误，请使用 'YYYY.MM' 格式。例如 '2025.1' 而不是 '{start_month_str}' 或 '{end_month_str}'。") from e
        else:
            raise e  # 重新抛出其他ValueError，如开始日期晚于结束日期

def do_caiwu_create(
        uid: int,
        headers: dict,
        cookies: dict,
        task_type: int,
        begin_time: int,
        end_time: int,
        max_retries: int = 5,
) -> dict[str, int | str]:
    """
    在商城执行财务明细生成导出操作，导出到历史列表中
    :param task_type: task_type
    :param max_retries:
    :return {"code": 1, "msg": "获取核价列表成功", "data": 完整的json, "remarks": remarks}
    """

    _result = {}
    for attempt in range(1, max_retries + 1):
        url = "https://seller.kuajingmaihuo.com/api/merchant/file/export"
        payload = {"fundDetailExport":True,"taskType":task_type,"beginTime":begin_time,"endTime":end_time}

        if not task_type:
            logger.error("请传入 task_type")

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
            _result = {"code": 1, "msg": "财务明细生成成功", "data": response.json(), "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": "财务明细生成失败", "data": response.json(), "remarks": remarks}
            continue

    auto_print_logger(_result)

    return _result


def auto_create_export_task(uid, headers, cookies, select_time_dict, official_time_dict):
    try:
        for select_time in select_time_dict:
            # 【核心优化1】先检查任务是否已存在
            if select_time in official_time_dict:
                logger.info(f"时间范围{select_time}的导出任务已存在，无需重复创建")
                continue

            # 【核心优化2】创建任务时捕获「重复创建」错误
            create_resp = do_caiwu_create(
                uid=uid,
                headers=headers,
                cookies=cookies,
                begin_time=select_time[0],
                end_time=select_time[1],
                task_type=19
            )

            # 识别「重复创建」错误，直接标记为已存在，不返回失败
            if "当前筛选条件的导出任务已创建" in create_resp["remarks"]:
                logger.warning(f"时间范围{select_time}的导出任务已存在（重复创建），跳过")
                # 将该时间范围加入已存在字典，避免后续重复尝试
                official_time_dict[select_time] = True
                continue

            # 识别「导出任务过多」错误，返回失败
            if create_resp["remarks"] == "当前创建的导出任务过多, 请明日再来":
                logger.error(f"时间范围{select_time}创建导出任务失败：今日导出任务上限")
                return False

        return True
    except Exception as e:
        logger.error(f"自动创建财务明细任务出错了: {e}", exc_info=True)
        return False


# 暂时无用
def get_send_goods_list(
    uid: str,
    headers: dict,
    cookies: dict,
    max_retries: int = 5,
) -> list[Any]:
    """
    获取解析后的发货地址
    :return {"code": 1, "msg": "获取核价列表成功", "data": 完整的json, "remarks": remarks}
    """

    _result = {}
    for attempt in range(1, max_retries + 1):
        url = "https://seller.kuajingmaihuo.com/bgSongbird-api/supplier/address/queryDeliveryAddressInfo"

        response = send_req(
            method="POST",
            headers=headers,
            cookies=cookies,
            url=url,
            json={},
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
            _result = {"code": 1, "msg": "获取发货地址成功", "data": response.json(), "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": "获取发货地址失败", "data": response.json(), "remarks": remarks}
            continue

    auto_print_logger(_result)

    def extract_send_goods_list(resp):
        result = []
        for item in resp["data"]["result"]["deliveryAddressInfoList"]:
            result.append({
                "factory_id": item["id"],
                "factory_name": item["addressLabel"],
                "factory_person": item["contactPersonName"],
            })
        return result

    result = extract_send_goods_list(_result)
    return result


def get_search_purchase_order_list(
    uid: str,
    headers: dict,
    cookies: dict,
    max_retries: int = 5,
    subPurchaseOrderSnList: list[str]=None,
) -> dict[str, int | str]:
    """
    备货单列表 获取订单所有信息
    对应页面
    https://seller.kuajingmaihuo.com/main/order-manager/shipping-list
    :param spu_id_list: 列表list None
    :param type: search_skc_id 根据spuid搜索skcid
    :param max_retries:
    :param page_num:
    :return {"code": 1, "msg": "获取核价列表成功", "data": 完整的json, "remarks": remarks}
    """

    _result = {}
    for attempt in range(1, max_retries + 1):
        url = "https://seller.kuajingmaihuo.com/bgSongbird-api/supplier/deliverGoods/management/pageQueryDeliveryOrders"

        if subPurchaseOrderSnList is None:
            return {"code": -1, "msg": "请传入备货单号 subPurchaseOrderSnList", "data": {}, "remarks": "备货单号都不传还搜个蛋的备货单？"}

        payload = {"pageNo":1,
                   "pageSize":100,
                   "subPurchaseOrderSnList":subPurchaseOrderSnList,
                   "productLabelCodeStyle":0}

        response = send_req(
            method="POST",
            headers=headers,
            cookies=cookies,
            url=url,
            json=payload,
            max_retries=max_retries,
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
            _result = {"code": 1, "msg": "获取备货单列表成功", "data": response.json(), "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": "获取备货单列表失败", "data": response.json(), "remarks": remarks}
            continue

    # auto_print_logger(_result)

    return _result


def extract_search_purchase_order_list(resp):
    result = []
    for item in resp["data"]["result"]["list"]:
        result.append({
            "order_id": item["subPurchaseOrderSn"],
            "delivery_order_id": item["deliveryOrderSn"],
            "factory_id": item["deliveryAddressInfo"]["id"],
            "factory_name": item["deliveryAddressInfo"]["addressLabel"],
            "skcExtCode": item["skcExtCode"],
            "skc_id": item["productSkcId"],
            "status": item["status"],
        })
    return result



