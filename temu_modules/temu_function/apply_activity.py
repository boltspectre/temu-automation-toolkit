import json
import time

from loguru import logger

from utils.log_utils import auto_print_logger
from utils.multiThreading_log_manager import get_task_log_manager
from utils.send_temu_req import send_req


def get_activity_list(uid, headers: dict, cookies: dict, max_retries: int = 5, main_task_id: str = None,
                     shop_abbr: str = None) -> dict:
    """
    获取活动列表
    :param uid: 用户ID
    :param headers: 请求头
    :param cookies: Cookie信息
    :param max_retries: 最大重试次数
    :param main_task_id: 主任务ID
    :param shop_abbr: 店铺简称
    :return: 包含活动列表的字典
    """
    shop_abbr = shop_abbr or ""
    _result = {}

    for attempt in range(1, max_retries + 1):
        # 获取活动列表
        url = "https://agentseller.temu.com/api/kiana/gamblers/marketing/enroll/activity/list"
        data = {
            "needSessionItem": True,
            "needCanEnrollCnt": True
        }

        response = send_req(
            uid=uid,
            method="POST",
            headers=headers,
            cookies=cookies,
            url=url,
            json=data,
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
            _result = {"code": 1, "msg": f"店铺{shop_abbr}：获取活动列表成功", "data": response.json(), "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：获取活动列表失败", "data": response.json(), "remarks": remarks}
            continue

    auto_print_logger(_result, main_task_id=main_task_id)

    return _result




def extract_activities_from_json(data):
    """
    从JSON文件中提取活动相关信息
    根据活动特征分为大活动（含sessionList）和小活动（含activityThematicId）
    并将父级的activityName传递给子级活动

    Args:
        file_path (str): JSON文件路径

    Returns:
        dict: 包含大活动、小活动和其他活动的字典
    """

    big_activities = []  # 包含 sessionList 的大活动
    small_activities = []  # 包含 activityThematicId 的小活动

    def classify_activities_recursive(data, parent_activity_name=None):
        if isinstance(data, dict):
            current_activity_name = None

            # 检查当前对象是否包含 activityName
            if 'activityName' in data:
                current_activity_name = data['activityName']
            elif 'name' in data:
                current_activity_name = data['name']

            # 检查是否是大活动（包含 sessionList 相关字段）
            if any(key in data for key in ['sessionList', 'session_list', 'sessions']):
                # 提取大活动相关信息
                big_activity = {}
                for key, value in data.items():
                    if key in ['activityName', 'name', 'activityType', 'type', 'stockThreshold', 'threshold',
                               # 'sessionList', 'session_list', 'sessions',
                               'activityId', 'id']:
                        big_activity[key] = value
                # 如果有父级活动名称且当前没有活动名称，则使用父级名称
                if parent_activity_name and 'activityName' not in big_activity and 'name' not in big_activity:
                    big_activity['activityName'] = parent_activity_name
                if big_activity:
                    big_activities.append(big_activity)

            # 检查是否是小活动（包含 activityThematicId 相关字段）
            elif any(key in data for key in ['activityThematicId', 'thematicId', 'theme_id']):
                # 提取小活动相关信息
                small_activity = {}
                for key, value in data.items():
                    if key in ['activityName', 'name', 'activityThematicId', 'thematicId', 'theme_id',
                               'activityThematicName', 'thematicName', 'theme_name',
                               'stockThreshold', 'threshold', 'activityType', 'type', 'activityId', 'id']:
                        small_activity[key] = value
                # 如果有父级活动名称且当前没有活动名称，则使用父级名称
                if parent_activity_name and 'activityName' not in small_activity and 'name' not in small_activity:
                    small_activity['activityName'] = parent_activity_name
                if current_activity_name:
                    small_activity['activityName'] = current_activity_name
                if small_activity:
                    small_activities.append(small_activity)

            # 如果既不是大活动也不是小活动，但包含活动相关字段，则归类为其他活动
            else:
                has_activity_fields = any(field in data for field in
                                          ['activityName', 'name', 'activityType', 'type',
                                           'stockThreshold', 'threshold', 'activityThematicId',
                                           'thematicId', 'activityThematicName', 'thematicName',
                                           # 'sessionList', 'session_list', 'sessions'
                                           ])
                if has_activity_fields:
                    other_activity = {}
                    for key, value in data.items():
                        if key in ['activityName', 'name', 'activityThematicId', 'thematicId', 'theme_id',
                                   'activityThematicName', 'thematicName', 'theme_name',
                                   'stockThreshold', 'threshold', 'activityType', 'type',
                                   # 'sessionList', 'session_list', 'sessions',
                                   'activityId', 'id']:
                            other_activity[key] = value
                    # 如果有父级活动名称且当前没有活动名称，则使用父级名称
                    if parent_activity_name and 'activityName' not in other_activity and 'name' not in other_activity:
                        other_activity['activityName'] = parent_activity_name
                    if current_activity_name:
                        other_activity['activityName'] = current_activity_name

            # 递归处理子元素，传递当前或父级的活动名称
            activity_name_to_pass = current_activity_name or parent_activity_name
            for value in data.values():
                if isinstance(value, (dict, list)):
                    classify_activities_recursive(value, activity_name_to_pass)

        elif isinstance(data, list):
            for item in data:
                classify_activities_recursive(item, parent_activity_name)

    classify_activities_recursive(data)

    return {
        'big_activities': big_activities,
        'small_activities': small_activities,
    }


def final_get_activity_list(uid, headers, cookies):
    """
    result['small_activities']
    small_activities
    big_activities
    """
    result = {
        "big_activities": [],
        "small_activities": [],
    }

    activity_list = get_activity_list(uid, headers, cookies)

    activities = extract_activities_from_json(activity_list["data"])

    for activity in activities['big_activities']:
        if activity["stockThreshold"] and activity["activityType"]:
            result["big_activities"].append(activity)


    for activity in activities['small_activities']:
        if activity["activityThematicId"] and activity["stockThreshold"] and activity["activityType"]:
            result["small_activities"].append(activity)

    return result


def filter_activityType_list(uid, headers, cookies, act_list):
    activityType_list = []

    final_get_activities = final_get_activity_list(uid, headers, cookies)

    activityType_list.extend(i for i in final_get_activities["big_activities"])
    activityType_list.extend(i for i in final_get_activities["small_activities"])

    print("activityType_list", activityType_list)
    for item in activityType_list:
        print(item)

    result = []
    for item in activityType_list:
        if 'activityThematicId' not in item:
            if item["activityType"] in act_list:
                result.append(item)

    if 10000001 in act_list:
        result.extend([i for i in activityType_list if 'activityThematicId' in i])

    return result



def get_match_activity_list(uid, headers: dict, cookies: dict, searchScrollContext: str = None, activityType: int = 5,
                            spu_id_list: list[int] = None, max_retries: int = 3, main_task_id: str = None,
                            shop_abbr: str = None
                            , activityThematicId: int = None) -> dict:

    shop_abbr = shop_abbr or ""
    _result = {}
    
    for attempt in range(1, max_retries + 1):
        try:
            url = "https://agentseller.temu.com/api/kiana/gamblers/marketing/enroll/scroll/match"
            data = {
                "activityType": activityType,
                "activityThematicId": activityThematicId,
                "rowCount": 50,
                "filterUnsalableWarning": False,
                "productSkcExtCodes": [],
                "searchScrollContext": searchScrollContext,
            }

            if spu_id_list:
                data["productIds"] = spu_id_list

            response = send_req(
                uid=uid,
                method="POST",
                headers=headers,
                cookies=cookies,
                url=url,
                json=data,
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
                _result = {"code": 1, "msg": f"店铺{shop_abbr}：获取报活动列表成功", "data": response.json(), "remarks": remarks}
                break  # 成功则退出重试循环
            else:
                _result = {"code": -1, "msg": f"店铺{shop_abbr}：获取报活动列表失败", "data": response.json(), "remarks": remarks}
                
                # 如果不是最后一次重试，等待一段时间再重试
                if attempt < max_retries:
                    import time
                    logger.warning(f"店铺{shop_abbr}：获取报活动列表失败，第{attempt}次重试，等待2秒后重试...")
                    time.sleep(2)
                continue

        except Exception as e:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：获取报活动列表时发生异常", "data": {}, "remarks": str(e)}
            
            # 如果不是最后一次重试，等待一段时间再重试
            if attempt < max_retries:
                import time
                logger.warning(f"店铺{shop_abbr}：获取报活动列表异常，第{attempt}次重试，等待2秒后重试... 异常: {e}")
                time.sleep(2)
            continue

    auto_print_logger(_result, main_task_id=main_task_id)

    return _result

def merge_payloads_dict(match_payloads_list, activityType, activityThematicId) -> dict:
    """
    将多个独立的官方格式JSON列表合并为一个标准的官方报活动JSON结构
    Args:
        match_payloads_list (list): 包含多个独立官方格式JSON字典的列表
    Returns:
        str: 合并后的官方标准JSON字符串（带缩进，可直接提交）
    """
    # 初始化最终的官方结构
    official_result = {
        "activityType": activityType,  # 固定为5，也可从第一个payload取
        "productList": []
    }
    if activityThematicId:
        official_result["activityThematicId"] = activityThematicId

    # 遍历每个payload，合并productList
    for payload in match_payloads_list:
        # 提取当前payload的productList并合并到最终列表
        official_result["productList"].extend(payload.get("productList", []))

    # print(json.dumps(official_result, indent=2, ensure_ascii=False))

    # 生成格式化的JSON字符串（与官方格式一致）
    return official_result


def submit_apply_activity(uid, headers: dict, cookies: dict, payload: dict = None,
                          max_retries: int = 5, main_task_id: str = None,
                          shop_abbr: str = None
                          ) -> dict:
    """
    :param cookies:
    :param headers:
    :param max_retries:

    :return:
    """
    shop_abbr = shop_abbr or ""
    spu_id_list = []
    _result = {}
    if not payload:
        return {"code": -1, "msg": f"店铺{shop_abbr}：提交报活动异常", "data": {}, "remarks": "payload为空，上传个毛"}

    for spu_list in payload["productList"]:
        spu_id = spu_list["productId"]
        spu_id_list.append(spu_id)

    for _ in range(1, max_retries + 1):

        # 报活动提交url
        url = "https://agentseller.temu.com/api/kiana/gamblers/marketing/enroll/submit"

        response = send_req(
            uid=uid,
            method="POST",
            headers=headers,
            cookies=cookies,
            url=url,
            json=payload,
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
            msg = f"店铺{shop_abbr}：SPU列表={spu_id_list}，提交报活动成功"
            fail_list = response.json().get("result", {}).get("failList", [])
            if fail_list:
                fail_msg_groups = {}
                for fail_item in fail_list:
                    fail_msg = fail_item.get("failMsg", "未知错误")
                    product_id = fail_item.get("productId")
                    if fail_msg not in fail_msg_groups:
                        fail_msg_groups[fail_msg] = []
                    fail_msg_groups[fail_msg].append(product_id)
                
                fail_details = []
                for fail_msg, product_ids in fail_msg_groups.items():
                    fail_details.append(f"{product_ids} {fail_msg}")
                
                msg += f"但包含错误信息，详情：{'; '.join(fail_details)}"
            
            _result = {"code": 1, "msg": msg, "data": response.json(), "remarks": remarks, "spu_id_list": spu_id_list}
            break
        else:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：SPU列表={spu_id_list}，提交报活动失败", "data": response.json(), "remarks": remarks, "spu_id_list": []}
            continue

    auto_print_logger(_result, main_task_id=main_task_id)

    return _result


# 解析JSON数据并提取所需字段
def parse_product_data(data):
    # 存储最终解析结果
    result = []
    
    # 检查数据结构是否有效，防止NoneType错误
    if not data or 'result' not in data or data['result'] is None:
        raise ValueError("数据格式无效：'result'字段不存在或为None")
    
    result_data = data['result']
    
    if 'searchScrollContext' not in result_data or result_data['searchScrollContext'] is None:
        raise ValueError("数据格式无效：'searchScrollContext'字段不存在或为None")
    
    if 'matchList' not in result_data or result_data['matchList'] is None:
        raise ValueError("数据格式无效：'matchList'字段不存在或为None")
    
    searchScrollContext = result_data['searchScrollContext']
    
    # 遍历每个商品（SPU）
    for product in result_data['matchList']:
        if not product or 'productId' not in product or 'suggestEnrollSessionIdList' not in product:
            continue  # 跳过无效的产品数据
        
        product_info = {
            'productId': product['productId'],
            'suggestEnrollSessionIdList': product['suggestEnrollSessionIdList'],
            'skus': []
        }

        # 遍历SKC列表（每个SPU下的SKC）
        skc_list = product.get('skcList', [])
        for skc in skc_list:
            if not skc:
                continue
                
            skc_id = skc.get('skcId', '')
            skc_ext_code = skc.get('extCode', '')

            # 遍历SKU列表（每个SKC下的SKU）
            sku_list = skc.get('skuList', [])
            for sku in sku_list:
                if not sku or 'skuId' not in sku:
                    continue
                    
                sku_info = {
                    'skcId': skc_id,
                    'skcextCode': skc_ext_code,
                    'skuId': sku['skuId'],
                    'skuextCode': sku.get('extCode', ''),
                    'suggestActivityPrice': sku.get('suggestActivityPrice', ''),
                    'suggestActivityDiscount': sku.get('suggestActivityDiscount', ''),
                    'dailyPrice': sku.get('dailyPrice', ''),
                    '尺码': sku.get('properties', {}).get('尺码', '')
                }
                product_info['skus'].append(sku_info)

        result.append(product_info)

    return {
        "result": result,
        "searchScrollContext": searchScrollContext
    }


def generate_payload(product_info, activityType: int, activityThematicId: int = None, stockThreshold: int = None):
    """
    根据解析的商品信息生成报活动payload
    """
    # 按skcId分组SKU
    skc_groups = {}
    for sku in product_info['skus']:
        skc_id = sku['skcId']
        if skc_id not in skc_groups:
            skc_groups[skc_id] = []
        
        # 只有当相应的字段存在时才添加这些参数
        sku_info = {'skuId': sku['skuId']}
        
        # 添加 activityPrice，仅当 suggestActivityPrice 存在时
        if 'suggestActivityPrice' in sku and sku['suggestActivityPrice'] is not None:
            sku_info['activityPrice'] = sku['suggestActivityPrice']
        
        # 添加 activityDiscount，仅当 suggestActivityDiscount 存在时
        if 'suggestActivityDiscount' in sku and sku['suggestActivityDiscount'] is not None:
            sku_info['activityDiscount'] = sku['suggestActivityDiscount']
        
        skc_groups[skc_id].append(sku_info)

    # 构建skcList
    skc_list = []
    for skc_id, sku_list in skc_groups.items():
        skc_list.append({
            'skcId': skc_id,
            'skuList': sku_list
        })

    # 构建完整的payload
    payload = {
        'activityType': activityType,
        'activityThematicId': activityThematicId if activityThematicId else None,
        'productList': [
            {
                'productId': product_info['productId'],
                'activityStock': stockThreshold,
                'skcList': skc_list,
                'sessionIds': product_info["suggestEnrollSessionIdList"]
            }
        ]
    }

    return payload

# 折扣结构
# {"activityType":53,"activityThematicId":2603050000024022,"productList":[{"productId":6252296824,"activityStock":15,"skcList":[{"skcId":29223803588,"skuList":[{"skuId":13125150595,"activityDiscount":80},{"skuId":64660894333,"activityDiscount":80}]}]},{"productId":5353687489,"activityStock":15,"skcList":[{"skcId":98740053541,"skuList":[{"skuId":69716487008,"activityDiscount":80},{"skuId":17134336276,"activityDiscount":80}]}]},{"productId":4764715980,"activityStock":15,"skcList":[{"skcId":83937259233,"skuList":[{"skuId":43975568380,"activityDiscount":80},{"skuId":49269191122,"activityDiscount":80},{"skuId":95003956058,"activityDiscount":80}]}]},{"productId":4617954825,"activityStock":15,"skcList":[{"skcId":13318869881,"skuList":[{"skuId":38155492371,"activityDiscount":80}]}]},{"productId":3186930233,"activityStock":15,"skcList":[{"skcId":28128698054,"skuList":[{"skuId":92559651530,"activityDiscount":80},{"skuId":31733735946,"activityDiscount":80},{"skuId":78149047021,"activityDiscount":80}]}]},{"productId":3059540999,"activityStock":15,"skcList":[{"skcId":89640842435,"skuList":[{"skuId":76104749081,"activityDiscount":80}]}]},{"productId":9207268773,"activityStock":15,"skcList":[{"skcId":25159721930,"skuList":[{"skuId":90932692720,"activityDiscount":80},{"skuId":28335800466,"activityDiscount":80},{"skuId":17096573319,"activityDiscount":80},{"skuId":75529575673,"activityDiscount":80}]}]},{"productId":8931872998,"activityStock":15,"skcList":[{"skcId":50692065010,"skuList":[{"skuId":83887124694,"activityDiscount":80},{"skuId":34193774507,"activityDiscount":80},{"skuId":50878399450,"activityDiscount":80},{"skuId":63792075903,"activityDiscount":80}]}]},{"productId":7687862248,"activityStock":15,"skcList":[{"skcId":55207487255,"skuList":[{"skuId":66590481263,"activityDiscount":80}]}]},{"productId":7661116794,"activityStock":15,"skcList":[{"skcId":56918332742,"skuList":[{"skuId":85845228643,"activityDiscount":80},{"skuId":48190213627,"activityDiscount":80},{"skuId":87527126954,"activityDiscount":80},{"skuId":82271831728,"activityDiscount":80}]}]},{"productId":7312593426,"activityStock":15,"skcList":[{"skcId":37182441356,"skuList":[{"skuId":92560811135,"activityDiscount":80},{"skuId":99594554305,"activityDiscount":80},{"skuId":81212871173,"activityDiscount":80}]}]},{"productId":6826194657,"activityStock":15,"skcList":[{"skcId":96547327528,"skuList":[{"skuId":33302882042,"activityDiscount":80},{"skuId":72480619235,"activityDiscount":80},{"skuId":60770651923,"activityDiscount":80},{"skuId":47604488276,"activityDiscount":80}]}]}]}


def validate_activity_price(product_info, activity_price_cache):
    """
    校验商品的所有SKU是否都满足底价要求

    Args:
        product_info: 商品信息
        activity_price_cache: 报活动底价缓存

    Returns:
        tuple[bool, str]: (是否通过, 未通过原因)
    """
    from temu_modules.temu_modules_tools.price_excel import get_activity_price_info

    for index, sku in enumerate(product_info['skus'], 1):
        skc_code = sku['skcextCode']
        size = sku['尺码']
        suggest_price = sku['suggestActivityPrice']
        suggestActivityDiscount = sku['suggestActivityDiscount']
        dailyPrice = sku['dailyPrice']

        if suggestActivityDiscount and dailyPrice:
            suggest_price = float(dailyPrice) * (float(suggestActivityDiscount) / 100)

        if not suggest_price:
            return False, f"第{index}个SKU {sku['skuId']} 推荐价为空"

        # 查询最低价
        min_price = get_activity_price_info(activity_price_cache, skc_code, size)

        if min_price is None:
            return False, f"第{index}个SKU {sku['skuId']} (类目: {skc_code}, 规格: {size}) 未找到底价配置"

        # 表格里的价格乘以100就是后端传递的价格
        min_price_backend = min_price * 100

        # 对比推荐价和最低价
        if suggest_price < min_price_backend:
            return False, f"第{index}个SKU {sku['skuId']} (类目: {skc_code}, 规格: {size}) 推荐价: {suggest_price} < 最低价: {min_price_backend:.0f}"

    return True, "所有SKU都满足底价要求"


def get_match_payloads(parsed_data, activity_price_cache, activityType: int, activityThematicId: int = None, stockThreshold: int = None, shop_abbr: str = None, open_log_false=False, not_skc_set: set = None):
    """
    为每个商品生成并打印payload，先进行底价校验，并排除指定的SKC
    """
    shop_abbr = shop_abbr or ""
    not_skc_set = not_skc_set or set()
    result = []
    for i, product in enumerate(parsed_data, 1):
        # 检查是否包含需要排除的SKC
        skc_id_list = product.get('skcIdList', [])
        if skc_id_list:
            # 检查是否有任何SKC在排除列表中
            excluded_skcs = [skc_id for skc_id in skc_id_list if skc_id in not_skc_set]
            if excluded_skcs:
                logger.info(f"店铺{shop_abbr}，活动类型={activityType}：🚫 跳过SPU={product['productId']}，包含排除的SKC: {excluded_skcs}")
                continue

        # 先进行底价校验
        is_valid, reason = validate_activity_price(product, activity_price_cache)

        if is_valid:
            logger.info(f"店铺{shop_abbr}，活动类型={activityType}：✅ 通过 SPU={product['productId']}")
            payload = generate_payload(product, activityType, activityThematicId, stockThreshold)
            # print(json.dumps(payload, indent=2, ensure_ascii=False))
            result.append(payload)

        else:
            if open_log_false:
                logger.info(f"店铺{shop_abbr}，活动类型={activityType}：官方推荐价低于最低价: {reason} SPU={product['productId']}")

    return result


def apply_activity_thread(
        uid,
        headers,
        cookies,
        shop_abbr,
        spu_id_list: list[int] = None,
        searchScrollContext: str = None,
        activityType: int = 5,
        stockThreshold: int = 30,
        activityThematicId: int = None,
        main_task_id=None,
        open_log_false=False,
        not_skc_list: list = None,
    ):
    from temu_modules.temu_modules_tools.price_excel import load_activity_price_data

    file_path = rf"配置文件_工具配置表\{shop_abbr}_工具配置表.xlsx"
    activity_price_cache = load_activity_price_data(file_path)
    logger.info(f"店铺{shop_abbr}：已加载报活动底价缓存，共 {len(activity_price_cache)} 条记录")

    # 将排除SKC列表转换为集合，便于快速查找
    not_skc_set = set(not_skc_list) if not_skc_list else set()
    if not_skc_set:
        logger.info(f"店铺{shop_abbr}：排除SKC列表：{not_skc_set}")

    result_list = []
    sum_submit_list = []
    sum_submit = 0
    i = 0
    empty_result_count = 0

    while True:
        # 1. 构造请求数据（使用最新的searchScrollContext）
        json_data = get_match_activity_list(uid, headers, cookies, searchScrollContext, spu_id_list=spu_id_list, activityType=activityType, activityThematicId=activityThematicId, shop_abbr=shop_abbr)["data"]

        # 3. 解析数据，更新searchScrollContext（核心：先更新，再处理后续逻辑）
        try:
            parse_result = parse_product_data(json_data)
            parsed_result = parse_result["result"]

            if empty_result_count > 10:
                logger.warning(f"店铺{shop_abbr}：连续10页无数据，可能是暂未查询到可报名商品或无商品，退出")
                break

            if not parsed_result:
                logger.warning(f"店铺{shop_abbr}：可报名商品为空结果")
                empty_result_count += 1
                continue

            searchScrollContext = parse_result["searchScrollContext"]
            # print(f"滚动条searchScrollContext：{searchScrollContext}")
        except ValueError as ve:
            # 处理数据格式错误
            logger.error(f"店铺{shop_abbr}：滚动条searchScrollContext {searchScrollContext} 页数据格式错误：{ve}")
            break  # 数据格式错误则终止循环
        except Exception as e:
            # 检查是否是频率限制错误
            error_msg = str(e)
            if "Operation too frequent" in error_msg or "try again later" in error_msg:
                logger.warning(f"店铺{shop_abbr}：操作过于频繁，暂停处理，等待API限制解除：{e}")
                import time
                time.sleep(10)  # 等待10秒后继续
                continue  # 继续下一次循环而不是退出
            else:
                logger.error(f"店铺{shop_abbr}：滚动条searchScrollContext {searchScrollContext} 页数据解析失败：{e}")
                break  # 其他错误则终止循环

        match_payloads_list = get_match_payloads(parsed_result, activity_price_cache, activityType, activityThematicId, stockThreshold, shop_abbr, open_log_false=open_log_false, not_skc_set=not_skc_set)

        # if len(match_payloads_list) == 0:
        #     print(json_data)
        #     print(parsed_result)

        if match_payloads_list:
            for match_payloads in match_payloads_list:
                result_list.append(match_payloads)

        logger.info(f"activityType={activityType}, "+ (f"activityThematicId={activityThematicId} " if activityThematicId else "") + f"累计待提交SPU数 {len(result_list)} ")

        if result_list and (len(result_list) >= 10 or i >= 50):
            submit_payloads = merge_payloads_dict(result_list, activityType, activityThematicId)

            spu_id_list = submit_apply_activity(uid, headers, cookies, submit_payloads, shop_abbr=shop_abbr)["spu_id_list"]
            sum_submit += len(result_list)
            sum_submit_list.extend(spu_id_list)
            result_list = []

        if not json_data['result']['hasMore']:
            logger.warning(f"店铺{shop_abbr}：hasMore={json_data['result']['hasMore']}，未获取到更多数据")
            break


        i += 1

    logger.info(f"店铺{shop_abbr}：循环结束，最终searchScrollContext：{searchScrollContext}")

    if result_list:
        logger.info(f"店铺{shop_abbr}：最后一页数据，还有 {len(result_list)} 条未提交，正在提交...")
        submit_payloads = merge_payloads_dict(result_list, activityType, activityThematicId)
        spu_id_list = submit_apply_activity(uid, headers, cookies, submit_payloads, shop_abbr=shop_abbr)["spu_id_list"]
        sum_submit += len(result_list)
        sum_submit_list.extend(spu_id_list)

    result = {"code": 1, "msg": f"店铺{shop_abbr}：报活动任务完成 活动类型={activityType}", "data": None, "remarks": f"本次提交{sum_submit}个SPU，SPU列表={sum_submit_list}"}

    logger.info("====================== 报活动任务完成 ======================")
    auto_print_logger(result, main_task_id=main_task_id, success_type="s")
    logger.info("============================================================")

    return result



def final_apply_activity(
        uid,
        headers,
        cookies,
        shop_abbr,
        activityType_list: list[int] = None,
        spu_id_list: list = None,
        searchScrollContext: str = None,
        mall_id: int = None,
        open_log_false=False,
        not_skc_list: list = None,
        main_task_id: str = None,
        wait_all_complete: bool = True,
        timeout: int = 3600
):
    """
    多线程报活动主函数
    Args:
        uid: 用户ID
        headers: 请求头
        cookies: Cookies
        shop_abbr: 店铺缩写
        activityType_list: 活动类型列表，如 [1, 2, 3, 4, 5]
        spu_id_list: SPU ID列表
        searchScrollContext: 滚动上下文
        mall_id: 商城ID
        not_skc_list: 排除的SKC ID列表
        main_task_id: 主任务ID
        wait_all_complete: 是否等待所有任务完成
        timeout: 任务等待超时时间（秒）
    Returns:
        dict: 任务结果
    """
    task_ids = []
    activityType_list = activityType_list or []
    not_skc_list = not_skc_list or []
    logger.info(f"店铺{shop_abbr}：开始多线程报活动任务 | 活动类型列表：{activityType_list} | 排除SKC列表：{not_skc_list}")
    
    try:
        for activityItem in activityType_list:
            task_kwargs = {
                "uid": uid,
                "headers": headers,
                "cookies": cookies,
                "shop_abbr": shop_abbr,
                "stockThreshold": activityItem['stockThreshold'],
                "activityType": activityItem['activityType'],
                "activityThematicId": activityItem['activityThematicId'] if 'activityThematicId' in activityItem else None,
                "spu_id_list": spu_id_list,
                "searchScrollContext": searchScrollContext,
                "main_task_id": main_task_id,
                "open_log_false": open_log_false,
                "not_skc_list": not_skc_list,
            }

            task_id = get_task_log_manager().add_task(
                target_func=apply_activity_thread, **task_kwargs,
                task_group=f"{shop_abbr}_报活动",
                mall_id=mall_id,
                parent_task_id=main_task_id,
                is_main_task=0,
            )

            if task_id:
                task_ids.append(task_id)
                logger.info(f"店铺{shop_abbr}：成功提交活动{activityItem}的报活动任务 | 任务ID：{task_id}")
            else:
                logger.error(f"店铺{shop_abbr}：提交活动{activityItem}的报活动任务失败")
                continue

        if not wait_all_complete:
            return {
                "code": 1,
                "msg": f"店铺{shop_abbr}：已提交{len(task_ids)}个报活动任务，不等待完成",
                "data": {"task_ids": task_ids},
                "remarks": ""
            }

        logger.info(f"店铺{shop_abbr}：等待{len(task_ids)}个报活动任务完成，超时时间：{timeout}秒")

        for task_id in task_ids:
            try:
                task_result = get_task_log_manager().get_task_result(task_id, timeout=timeout)
            except Exception as e:
                logger.error(f"店铺{shop_abbr}：获取任务{task_id}结果失败：{e}")

        result = {
            "code": 1,
            "msg": f"店铺{shop_abbr}：报活动任务完成",
            "data": {},
            "remarks": f"完成共{len(activityType_list)}个活动"
        }

        auto_print_logger(result, success_type="s", main_task_id=main_task_id)
        return result

    except Exception as e:
        logger.error(f"店铺{shop_abbr}：多线程报活动任务异常：{e}")
        return {
            "code": -1,
            "msg": f"店铺{shop_abbr}：多线程报活动任务异常",
            "data": {},
            "remarks": str(e)[:500]
        }