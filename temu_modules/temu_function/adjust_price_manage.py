from utils.log_utils import auto_print_logger, response_result_handler
from utils.send_temu_req import send_req


def get_adjust_price_list(
        uid,
        headers: dict,
        cookies: dict,
        max_retries: int = 5,
        order_id_list: list[str] = None,
        skc_id_list: list[str] = None,
        page_num: int = 1,
        shop_abbr: str = "",
        main_task_id=None
) -> dict[str, int | str]:
    """
    商品价格申报,不调整
    :param order_id_list: 列表list None
    :param max_retries:
    :return {"code": 1, "msg": "获取xx成功", "data": 完整的json, "remarks": remarks}
    """
    if order_id_list is None:
        order_id_list = []
    if skc_id_list is None:
        skc_id_list = []

    _result = {}
    for attempt in range(1, max_retries + 1):

        url = "https://agentseller.temu.com/api/kiana/mms/magneto/price-adjust/page-query"

        # payload = {"pageInfo":{"pageSize":100,"pageNo":page_num},"status":1}

        payload = {"pageInfo":{"pageSize":100,"pageNo":page_num},"status":1,
                   # "skcId":["75340684251"],
                   # "priceOrderSn":["HJD260120575632672"]
                   "skcId": skc_id_list,
                   "priceOrderSn": order_id_list
                   }

        response = send_req(
            method="POST",
            headers=headers,
            cookies=cookies,
            url=url,
            json=payload,
            uid=uid,
        )

        remarks = response_result_handler(shop_abbr, response)

        if response.json()["success"]:
            _result = {"code": 1, "msg": f"店铺{shop_abbr}：获取商品价格申报列表成功", "data": response.json(),
                       "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：获取商品价格申报列表失败", "data": response.json(),
                       "remarks": remarks}
            continue

    auto_print_logger(_result, main_task_id=main_task_id)

    return _result


def extract_adjust_price_list(adjust_price_list_json: dict):
    data = adjust_price_list_json["data"]["result"]
    result_list = []
    total = data["total"]
    list = data["list"]

    if not list:
        print(data)
        return {"data": [], "total": total}

    for item in list:
        result_list.append(
                {
                    "id": item["id"],
                    "skc_id": item["skcId"],
                    "spu_id": item["productId"],
                    "sku_id": item["skuInfoItemList"][0]["productSkuId"],
                    "order_id": item["priceOrderSn"]
                }
           )

    return {"data": result_list, "total": total}


def adjust_price_manage(
        uid,
        headers: dict,
        cookies: dict,
        max_retries: int = 1,
        order_id_list: list[str] = None,
        order_oid_list: list[str] = None,
        reason: str = None,
        shop_abbr: str = "",
        main_task_id=None
) -> dict[str, int | str]:
    """
    商品价格申报,不调整
    :param order_id_list: 列表list None
    :param max_retries:
    :return {"code": 1, "msg": "获取xx成功", "data": 完整的json, "remarks": remarks}
    """
    if order_id_list is None:
        order_id_list = []

    _result = {}
    for attempt in range(1, max_retries + 1):

        # 单个
        # url = "https://agentseller.temu.com/api/kiana/mms/magneto/api/price/purchase-adjust/review"
        # payload = {"adjustId":260120533133336,"result":2,"reason":"2"}

        url = "https://agentseller.temu.com/api/kiana/mms/gmp/bg/magneto/api/price-adjust/batch/adjust"

        adjust_list = []

        for order_id in order_id_list:
            adjust_list.append({"adjustId": order_id, "result": 2, "reason": reason if reason else "我就不调整"})

        payload = {"adjustList": adjust_list}

        response = send_req(
            method="POST",
            headers=headers,
            cookies=cookies,
            url=url,
            json=payload,
            uid=uid,
        )

        remarks = response_result_handler(shop_abbr, response)

        if response.json()["success"]:
            _result = {"code": 1, "msg": f"店铺{shop_abbr}：{order_oid_list}商品价格申报不调整执行成功", "data": response.json(),
                       "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：{order_oid_list} 商品价格申报不调整执行出错，存在失败单", "data": response.json(),
                       "remarks": remarks}
            continue

    auto_print_logger(_result, success_type="s",
                      main_task_id=main_task_id)

    return _result


def final_adjust_price_manage(
        uid,
        headers: dict,
        cookies: dict,
        max_retries: int = 2,
        order_id_list: list[str] = None,
        skc_id_list: list = None,
        reason: str = None,
        shop_abbr: str = "",
        main_task_id=None
    ):

    adjust_price_list_json = get_adjust_price_list(
        uid=uid,
        headers=headers,
        cookies=cookies,
        max_retries=max_retries,
        order_id_list=order_id_list,
        skc_id_list=skc_id_list,
        page_num=1,
        shop_abbr=shop_abbr,
        main_task_id=main_task_id
    )

    result_order_id_list = []
    result_order_oid_list = []

    result = extract_adjust_price_list(adjust_price_list_json)
    for order in result["data"]:
        result_order_id_list.append(order["id"])
        result_order_oid_list.append(order["order_id"])

    # 如果总条数为0，直接跳出
    if result["total"] == 0:
        print("总条数为0，无需分页")
    else:
        # 计算总页数：向上取整（比如total=100 → 1页；total=101 → 2页；total=350 → 4页）
        total_pages = (result["total"] + 99) // 100  # 等价于 ceil(total/100)，避免浮点运算


        # 从第2页开始遍历到最后一页
        for page in range(2, total_pages + 1):
            print(f"开始遍历第{page}页")
            adjust_price_list_json = get_adjust_price_list(
                headers=headers,
                cookies=cookies,
                max_retries=max_retries,
                order_id_list=order_id_list,
                skc_id_list=skc_id_list,
                page_num=page,
                shop_abbr=shop_abbr,
                uid=uid,
                main_task_id = main_task_id
            )

            result = extract_adjust_price_list(adjust_price_list_json)
            print(result)
            for order in result["data"]:
                result_order_id_list.append(order["id"])
                result_order_oid_list.append(order["order_id"])


    # print(result_order_oid_list)
    # print(len(result_order_oid_list))

    result = adjust_price_manage(
        headers=headers,
        cookies=cookies,
        max_retries=max_retries,
        order_id_list=result_order_id_list,
        order_oid_list=result_order_oid_list,
        reason=reason,
        shop_abbr=shop_abbr,
        uid=uid,
        main_task_id=main_task_id
    )

    return result