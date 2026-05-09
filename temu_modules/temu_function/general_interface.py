from loguru import logger
from utils.log_utils import auto_print_logger
from utils.send_temu_req import send_req
import json


def get_goods_list(
    uid: str,
    headers: dict,
    cookies: dict,
    max_retries: int = 5,
    page: int = 1,
    pageSize: int = 50,
    skc_id_list:list[int]=None,
    spu_id_list:list[int]=None,
    sku_id_list:list[int]=None,
    cat_id_list:list[int]=None,
    skcTopStatus:int=None,
    skcExtCodes:list[str]=None,
) -> dict[str, int | str]:
    """
    获取商品列表（SKU/SKC/SPU 关联信息）
    https://agentseller.temu.com/goods/list
    :param uid: 店铺唯一标识
    :param headers: 请求头
    :param cookies: 请求Cookie
    :param max_retries: 最大重试次数
    :param skc_id_list: SKC ID列表（可选）
    :param spu_id_list: SPU ID列表（可选）
    :param sku_id_list: SKU ID列表（可选）
    :return {"code": 1, "msg": "获取商品列表成功", "data": 完整的json, "remarks": remarks}
    """

    _result = {}
    for attempt in range(1, max_retries + 1):
        url = "https://agentseller.temu.com/visage-agent-seller/product/skc/pageQuery"

        # 搜索指定 spuid 的 skcid
        payload = {
            "pageSize": pageSize, # 50 100 500
            "page": page,
        }

        if skc_id_list is not None:
            payload["productSkcIds"] = skc_id_list
        if spu_id_list is not None:
            payload["productIds"] = spu_id_list
        if sku_id_list is not None:
            payload["productSkuIds"] = sku_id_list
        if cat_id_list is not None:
            payload["catIds"] = cat_id_list
        if skcTopStatus is not None:
            payload["skcTopStatus"] = skcTopStatus # 在售中 100
        if skcExtCodes is not None:
            payload["skcExtCodes"] = skcExtCodes


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
            _result = {"code": 1, "msg": "获取商品列表成功", "data": response.json(), "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": "获取商品列表失败", "data": response.json(), "remarks": remarks}
            continue

    # auto_print_logger(_result)

    return _result

def extract_category_from_goods_item(item: dict) -> dict:
    """
    从商品数据中提取完整的类目路径列表
    :param item: 商品数据项，包含 categories 字段
    :return: {"类目id": [9711, 9712, ...], "类目名": ["家居、厨房用品", "厨房和餐厅", ...]}
    """
    cat_ids = []
    cat_names = []
    
    categories = item.get("categories", {})
    if categories:
        # 按层级顺序遍历 cat1 ~ cat10
        for i in range(1, 11):
            cat_node = categories.get(f"cat{i}", {})
            if isinstance(cat_node, dict):
                cat_id = cat_node.get("catId")
                cat_name = cat_node.get("catName", "")
                # 过滤无效类目（catId为0或空名称）
                if cat_id and cat_id != 0 and cat_name:
                    cat_ids.append(cat_id)
                    cat_names.append(cat_name)
    
    # 如果 categories 为空或解析失败，回退到 leafCat
    if not cat_ids:
        leaf_cat = item.get("leafCat", {})
        if leaf_cat:
            cat_id = leaf_cat.get("catId")
            cat_name = leaf_cat.get("catName", "")
            if cat_id and cat_name:
                cat_ids.append(cat_id)
                cat_names.append(cat_name)
    
    return {"类目id": cat_ids, "类目名": cat_names}


def extract_goods_list(goods_list_json: dict):
    data = goods_list_json["data"]
    result = []
    for item in data["result"]["pageItems"]:
        # 提取完整的类目路径列表
        category_info = extract_category_from_goods_item(item)
        
        item_result = {
            "spu_id": item.get("productId"),
            "skc_id": item.get("productSkcId"),
            "类目id": category_info["类目id"],
            "类目名": category_info["类目名"],
            "货号": item.get("extCode")
        }

        productSkuSummaries = item.get("productSkuSummaries")
        sku_list = []
        for productSkuSummary in productSkuSummaries:
            sku_dict = {
                "sku_id": productSkuSummary.get("productSkuId"),
                "sku_货号": productSkuSummary.get("extCode"),
                "尺码": productSkuSummary.get("productSkuSpecList")[0].get("specName"),
                "virtualStock": productSkuSummary.get("virtualStock")
            }

            sku_list.append(sku_dict)
            item_result["sku_list"] = sku_list

        # print(item_result)
        result.append(item_result)

    return {"data": result}


def get_up_new_lifecycle_list(
        uid,
        headers: dict,
        cookies: dict,
        page_num: int = 1,
        max_retries: int = 5,
        spu_id_list=None,
        log: bool = True,
        shop_abbr: str = "",
        type: str = "upload",
        time_type: int = None,
        time_begin: int = None,
        time_end: int = None,
) -> dict[str, int | str]:
    """
    封装 searchForChainSupplier 请求改价商品列表
    每页10条
    :param spu_id_list: 列表list None
    :param type: 
        - "search_skc_id": 根据spuid搜索skcid
        - "jit": JIT模式，使用时间筛选
        - "upload" 或其他: 默认模式，搜索异常核价订单
    :param time_type: 时间类型 1-创建时间 2-更新时间（仅在jit模式下有效）
    :param time_begin: 开始时间戳（毫秒）（仅在jit模式下有效）
    :param time_end: 结束时间戳（毫秒）（仅在jit模式下有效）
    :param max_retries:
    :param page_num:
    :return {"code": 1, "msg": "获取核价列表成功", "data": 完整的json, "remarks": remarks}
    """
    if spu_id_list is None:
        spu_id_list = []

    _result = {}
    # 确保max_retries是整数
    max_retries = int(max_retries) if max_retries is not None else 5
    for attempt in range(1, max_retries + 1):
        url = "https://agentseller.temu.com/api/kiana/mms/robin/searchForChainSupplier"

        if type == "search_skc_id":
            if not spu_id_list:
                from loguru import logger
                logger.error("请传入 spu_id_list 搜索再skc")

            # 搜索指定 spuid 的 skcid
            payload = {
                "pageSize": 100,  # 固定，核价执行速度较快，提高效率
                "pageNum": 1,
                "supplierTodoTypeList": [],
                "productSpuIdList": spu_id_list
            }
            
            # 添加时间筛选参数（如果有）
            if time_type is not None and time_begin is not None and time_end is not None:
                payload["timeType"] = time_type
                payload["timeBegin"] = time_begin
                payload["timeEnd"] = time_end

        elif type == "jit":
            # JIT模式
            if not spu_id_list:
                payload = {
                    "pageSize": 100,
                    "pageNum": 1,
                    "timeType": time_type if time_type is not None else 1,
                    "timeBegin": time_begin if time_begin is not None else 1769875200000,
                    "timeEnd": time_end if time_end is not None else 1770566399999,
                    "supplierTodoTypeList": [],
                    "secondarySelectStatusList" : [10]
                }
            else:
                payload = {
                    "pageSize": 100,
                    "pageNum": 1,
                    "supplierTodoTypeList": [],
                    "secondarySelectStatusList": [10],
                    "productSpuIdList": spu_id_list
                }

        else:
            # 搜索异常核价订单
            payload = {"pageSize":100,"pageNum":page_num,"supplierTodoTypeList":[1],"productSpuIdList":spu_id_list}
            
            # 添加时间筛选参数（如果有）
            if time_type is not None and time_begin is not None and time_end is not None:
                payload["timeType"] = time_type
                payload["timeBegin"] = time_begin
                payload["timeEnd"] = time_end

        response = send_req(
            method="POST",
            headers=headers,
            cookies=cookies,
            url=url,
            data=json.dumps(payload, separators=(',', ':')),
            log=log,
            uid=uid,
        )

        if not response:
            remarks = f"店铺{shop_abbr}：异常，响应结果为空"
        elif response.status_code != 200:
            remarks = f"店铺{shop_abbr}：网络异常或请求被拦截，状态码:{response.status_code}，响应: {response.json()}"
        else:
            remarks = response.json().get("errorMsg", "")
            if remarks is None:
                remarks = ""

        if response.json()["success"]:
            _result = {"code": 1, "msg": f"店铺{shop_abbr}：获取订单列表成功", "data": response.json(),
                       "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：获取订单列表失败", "data": response.json(),
                       "remarks": remarks}
            continue

    if log:
        auto_print_logger(_result)

    return _result


def get_price_groups(shop_abbr, json_data):
    """
    从核价页获取的默认 10 条 skc 以 sku 为单位输出
    新增：类目 EGDT 和 sku 属性中的尺码（如 19.68*31.49inch(50*80cm)）
    """
    num = len(json_data['result']['dataList'])
    _result = {"total": json_data['result']['total'], "num": num, "price_group": [], "skc_spu": []}
    logger.info(f"店铺{shop_abbr}：获取上新列表成功，共 {json_data['result']['total']} 条")
    for item in json_data['result']['dataList']:
        spu_id = item['productId']
        skc_id = None
        for skc in item['skcList']:
            skc_id = skc['skcId']
            ext_code = skc.get('extCode', '')  # 类目 EGDT 就在 skc 的 extCode 字段里
            for review in skc.get('supplierPriceReviewInfoList', []):
                for sku in review['productSkuList']:
                    # 从 sku 的 productPropertyList 里找尺码
                    valid_size_values = []
                    for prop in sku.get('productPropertyList', []):
                        # 安全获取value，默认空字符串
                        size_value = prop.get('value', '')
                        # 过滤空值/纯空格（避免无效连接）
                        if size_value.strip():
                            valid_size_values.append(size_value)
                    # 用-连接所有有效value
                    size_value_joined = "-".join(valid_size_values)

                    _result["price_group"].append({
                        "skcId": skc_id,
                        "spuId": spu_id,
                        "skuId": sku['skuId'],
                        "priceOrderId": review['priceOrderId'],
                        "current_price": review['supplyPrice'],
                        "suggest_supply_price": review['suggestSupplyPrice'],
                        "leimu": ext_code,
                        "size": size_value_joined,
                        "times": review['times']
                    })

        _result["skc_spu"].append({
            "skcId": skc_id,
            "spuId": spu_id,
        })
    return _result



def build_skc_spu_dict(skc_spu_list: list[dict]):
    """
    skc_spu_item {'skcId': 75315629674, 'spuId': 9919167641}
    """
    skc_to_spu = {}
    spu_to_skc = {}
    for item in skc_spu_list:
        # 1. 先获取原始值，兼容字符串/整数类型
        skc_id_raw = item.get('skcId')
        spu_id_raw = item.get('spuId')

        # 2. 强制转为整数（处理空值/非数字场景）
        try:
            skc_id = int(skc_id_raw) if skc_id_raw is not None else None
            spu_id = int(spu_id_raw) if spu_id_raw is not None else None
        except (ValueError, TypeError):
            # 非数字类型直接跳过，避免报错
            continue

        # 3. 仅当两个值都有效时才存入字典
        if skc_id and spu_id:
            skc_to_spu[skc_id] = spu_id  # 键：int，值：int
            spu_to_skc[spu_id] = skc_id  # 键：int，值：int
    return skc_to_spu, spu_to_skc


# 快速查询函数（基于预构建的字典）
def quick_get_related_id(skc_to_spu, spu_to_skc, query_int):
    try:
        if type(query_int) == str:
            query_id = int(query_int.strip())
        else:
            query_id = query_int
    except:
        return None
    return skc_to_spu.get(query_id) or spu_to_skc.get(query_id)






