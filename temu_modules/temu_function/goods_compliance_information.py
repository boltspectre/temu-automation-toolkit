from loguru import logger

from config.usual_config import TEMU_PAGE_SIZE
from utils.log_utils import auto_print_logger
from utils.send_temu_req import send_req


# ====== 获取合规信息订单基础参数 ======
def get_query_compliance_order(shop_abbr: str, headers: dict, cookies: dict,  spu_id_list: list, uid, max_retries: int = 5) -> dict:
    """
    获取合规信息订单基础参数
    :return:
    """
    _result = {}
    for attempt in range(1, max_retries + 1):

        url = "https://agentseller.temu.com/ms/bg-flux-ms/compliance_property/page_query"

        payload = {"page_num":1,"page_size":TEMU_PAGE_SIZE,"type":2,"spu_id_list":[str(spu_id) for spu_id in spu_id_list]}

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
            _result = {"code": 1, "msg": f"店铺{shop_abbr}：获取合规信息成功", "data": response.json(), "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：获取合规信息失败", "data": response.json(), "remarks": remarks}
            continue

    auto_print_logger(_result)

    return _result


# ====== 获取合规信息模板和详细信息 ======
def get_compliance_template_detail(shop_abbr, headers: dict, cookies: dict,  payload: dict, uid, type: str = "template", max_retries: int = 5) -> dict:
    """
    获取合规信息模板和详细信息
    :type template detail
    :return:
    """
    _result = {}
    for attempt in range(1, max_retries + 1):
        if type == "template":
            url = "https://agentseller.temu.com/ms/bg-flux-ms/compliance_property/query_template"
        elif type == "detail":
            url = "https://agentseller.temu.com/ms/bg-flux-ms/compliance_property/query_detail"
        else:
            return {"code": -1, "msg": f"获取合规信息模板和详细信息传入类型错误{type}", "data": {}, "remarks": "可选类型：template, detail"}

        # payload其他参数

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

        if type == "template":
            msg_info = "模板"
        elif type == "detail":
            msg_info = "详细信息"
        else:
            return {"code": -1, "msg": f"店铺{shop_abbr}：获取合规信息模板和详细信息传入类型错误{type}", "data": {}, "remarks": "可选类型：template, detail"}

        if response.json()["success"]:
            _result = {"code": 1, "msg": f"店铺{shop_abbr}：获取合规信息{msg_info}成功", "data": response.json(), "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：获取合规信息{msg_info}成功", "data": response.json(), "remarks": remarks}
            continue

    auto_print_logger(_result)

    return _result



def get_compliance_final_payload(shop_abbr, _query_json: dict, detail_json: dict, template_json: dict, skc_id: int):
    if not _query_json:
        return {"code": -1, "msg": f"店铺{shop_abbr}：获取合规信息订单基础参数失败", "data": {}, "remarks": "获取合规信息订单基础参数失败"}

    _detail_json = detail_json["result"]
    _template_json = template_json["result"]["template_list"]
    # print(_query_json)

    payload = {
        "cat_id": _query_json['cat_id'],
        "spu_id": _query_json['spu_id'],
        "goods_id": _query_json['goods_id'],
        "group_sku_by_same_info": _detail_json.get("group_sku_by_same_info", False),
        "template_edit_request_list": []
    }

    property_mapping = {  # 示例属性映射，实际应用中应根据实际情况定义
        "1000000001": [1000100066],
        "1000100091": [1000131288],
        "1000100110": [1000131288],
        "1000100120": [1000131288]
    }

    # ===== 构造完整的参数 ===== #

    # query大类匹配
    default_type = []
    for query_task in _query_json['wait_task_show_dtolist']:
        # print(query_task)
        if query_task["show_name"] == "韩国公示信息":
            for i in query_task["wait_task_dtolist"]:
                # print(i["task_id"])
                # print(i["task_type"])
                default_type.append(i["task_type"])
        # if 添加其他大类

    # 根据详细信息匹配
    for task in _detail_json["template_list"]:
        matched_query_task = None

        # 分别对应三个大类里面的小类，但只有一项，所以一一对应，后续大类新增小类可能需要重写，写在前面默认类里面
        if task["task_type"] in [25, 60, 84]:
            # 详细匹配
            for query_task in _query_json['wait_task_dtolist']:
                if query_task["task_type"] == task["task_type"]:
                    matched_query_task = query_task
                    matched_query_task["rep_detail_list"] = task["rep_detail_list"]
                    break

        if matched_query_task:
            payload["template_edit_request_list"].append(matched_query_task)
            # print(matched_query_task)
        else:
            payload["template_edit_request_list"].append(task)

        # 对于这几个要进行匹配properties特殊处理选择
        if task["task_type"] in [4, 33, 42, 49]:
            for template_task in _template_json:
                if template_task["task_type"] == task["task_type"]:
                    task_property_id = str(template_task["template_property_dtolist"][0]["property_id"])

                    task["properties"] = {f"{task_property_id}": property_mapping.get(task_property_id)}
                    # print(template_task["template_property_dtolist"][0]["property_id"])

        if task["task_type"] in default_type:
            for template_task in _template_json:
                if template_task["task_type"] == task["task_type"]:
                    task_property_id = str(template_task["template_property_dtolist"][0]["property_id"])
                    task["properties"] = {f"{task_property_id}": [1000131288]}

        if task["task_type"] == 61:
            task["input_text"] = {
                "1100100115": {
                    "multi_line_inputs": [
                        {
                            "name": f"{skc_id}"
                        }
                    ]
                }
            }

    task_type_mapping = {query_task["task_type"]: query_task["task_id"] for query_task in
                         _query_json['wait_task_dtolist']}

    for item in payload["template_edit_request_list"]:
        current_task_type = item.get("task_type")
        if current_task_type in task_type_mapping:
            item["task_id"] = task_type_mapping[current_task_type]
        else:
            logger.error(f"无匹配的task_type: {current_task_type}，保留原task_id: {item['task_id']}")

    return payload


def compliance_tijiao(shop_abbr, headers: dict, cookies: dict,  payload: dict, uid, max_retries: int = 5) -> dict:
    """
    提交合规信息表单
    :return:
    """
    _result = {}
    for attempt in range(1, max_retries + 1):

        url = "https://agentseller.temu.com/ms/bg-flux-ms/compliance_property/edit_compliance"

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
            _result = {"code": 1, "msg": f"店铺{shop_abbr}：执行提交合规信息表单操作成功", "data": response.json(), "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：Temu系统识别能力待建设或提交合规信息表单失败", "data": response.json(), "remarks": remarks}
            continue

    auto_print_logger(_result)

    return _result



def all_compliance_tijiao(shop_abbr, headers: dict, cookies: dict,  query_json_list: dict, skc_id: int, spu_id: int, uid):
    _query_json = None
    for _query_json in query_json_list["result"]["data"]:
        if _query_json['spu_id'] == spu_id:
            break

    # 用于获取店铺之间不同的请求头参数 如制造商信息
    payload = {'cat_id': _query_json['cat_id'],
               'spu_id': _query_json['spu_id'],
               'goods_id': _query_json['goods_id'],
               'wait_task_list': [t for t in _query_json['wait_task_dtolist']]}

    # detail_json用于获取制造商信息

    detail_json = get_compliance_template_detail(shop_abbr, headers, cookies, payload, uid, type="detail")['data']

    template_json = get_compliance_template_detail(shop_abbr, headers, cookies, payload, uid, type="template")['data']

    final_payload = get_compliance_final_payload(shop_abbr, _query_json, detail_json, template_json, skc_id)

    # print(final_payload)
    _result = compliance_tijiao(shop_abbr, headers, cookies, final_payload, uid)

    return _result




