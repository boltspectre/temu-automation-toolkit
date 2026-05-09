import re

from utils.log_utils import auto_print_logger
from utils.send_temu_req import send_req


def get_shop_userinfo(uid, headers: dict, cookies: dict , max_retries: int = 5, log: bool = True) -> dict:
    """
    获取店铺信息
    原始信息：
    {
    "success": true,
    "errorCode": 1000000,
    "errorMsg": null,
    "result": {
        "accountId": 27903675768554,
        "maskMobile": null,
        "mallList": [
            {
                "mallId": 6221667799378,
                "mallName": "Hephzibah",
                "managedType": 0,
                "uniqueId": "eyJ1IjoiZGJLRWtaZFFuVXNBYlgwUStOaE1pQT09IiwidiI6MX0="
            },
            {
                "mallId": 6222230100783,
                "mallName": "Margarida",
                "managedType": 0,
                "uniqueId": "eyJ1IjoiakVDdWtESldWNktiVk1lc0pINDBaZz09IiwidiI6MX0="
            },
            {
                "mallId": 6215832731945,
                "mallName": "Balendin",
                "managedType": 0,
                "uniqueId": "eyJ1IjoiZE5IZHpEeTBrQWUxSStpRHFzMmw3Zz09IiwidiI6MX0="
            },
            {
                "mallId": 634418223681329,
                "mallName": "Balendin local",
                "managedType": 1,
                "uniqueId": "eyJ1IjoiODY5dGszbDc3WjN0Vy9ldWFMOTZDZz09IiwidiI6MX0="
            }
        ],
        "accountType": 2
    }
}
    :return: {"code":1, "data": shop_info_list}
    """
    _result = {}
    for attempt in range(1, max_retries + 1):

        url = "https://agentseller.temu.com/api/seller/auth/userInfo"

        response = send_req(
            headers=headers,
            cookies=cookies,
            method="POST",
            max_retries=max_retries,
            url=url,
            json={},
            log=log,
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
            shop_info_list = extract_shop_info(response.json())

            _result = {"code": 1, "msg": "获取店铺信息成功", "data": shop_info_list, "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": "获取店铺信息失败", "data": response.json(), "remarks": remarks}
            continue

    if log:
        auto_print_logger(_result)

    return _result


def extract_shop_info(data: dict) -> list[dict]:
    """
    提取所有店铺信息（优化点：用for in直接遍历元素，返回完整列表）
    :param data: 原始接口返回数据
    :return: 所有店铺信息的列表，每个元素是单个店铺的信息字典
    """
    # 初始化结果列表（存储所有店铺信息）
    shop_info_list = []

    # 1. 提取公共的accountId（整个账号的唯一标识）
    account_id = data.get("result", {}).get("accountId", "")

    # 2. 用for in直接遍历mallList中的每个店铺元素（替代索引遍历）
    for mall_item in data.get("result", {}).get("mallList", []):
        # 从单个店铺元素中提取字段（加空值保护，避免KeyError）
        mall_id = mall_item.get("mallId", "")
        mall_name = mall_item.get("mallName", "")
        unique_id = mall_item.get("uniqueId", "")
        managed_type = mall_item.get("managedType", "")
        shop_abbr = english_name_initials(mall_name)

        # 组装单个店铺的信息字典
        shop_info = {
            "店铺名称": mall_name,
            "店铺缩写": shop_abbr,
            "account_id": account_id,
            "mall_id": mall_id,
            "unique_id": unique_id,
            "managed_type": managed_type
        }

        # 添加到结果列表
        shop_info_list.append(shop_info)

    # 返回所有店铺信息的列表（而非单个店铺）
    return shop_info_list

def english_name_initials(name: str) -> str:
    """
    英文名字 → 大写缩写
    支持：
    1. 空格/连字符/撇号 分词
    2. 驼峰命名自动分词（如 ThreadTerrace → TT）
    3. 处理HTML实体（如 nbsp）
    4. 忽略非字母字符
    """
    # 1. 处理HTML实体（先解码）
    import html
    name = html.unescape(name.strip())

    # 2. 替换各种空白字符为普通空格
    name = re.sub(r'[\xa0\u2002\u2003\u2009\u202F\u205F\u3000]', ' ', name)

    # 3. 先把驼峰拆成空格分隔
    name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)

    # 4. 再按空白字符/连字符/撇号拆分
    words = re.split(r"[ \-'’]+", name)

    # 5. 取首字母（增强过滤逻辑）
    initials = []
    for w in words:
        if w:  # 非空字符串
            # 只取字母开头的部分
            match = re.search(r'^[A-Za-z]', w)
            if match:
                initials.append(w[0].upper())

    return ''.join(initials)



# 快速测试
if __name__ == "__main__":
    tests = ["Devineresse Delights", "Habcjs", "Mary-Jane Watson", "O'Neill", "  john  doe  "]
    for t in tests:
        print(t, "->", english_name_initials(t))
