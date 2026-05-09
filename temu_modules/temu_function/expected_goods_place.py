from loguru import logger
from utils.log_utils import auto_print_logger
from utils.send_temu_req import send_req
from utils.multiThreading_log_manager import get_task_log_manager, check_task_stopped


def extract_skc_pick_out_config_list(data: dict) -> list:
    """
    提取商品期望到货地点配置列表中的 skc_id
    :param data: 接口返回的完整字典数据
    :return: skc_id 列表
    """
    try:
        result = data.get("result", {})
        items = result.get("items", [])
        if not items:
            return []
        
        skc_id_list = []
        for item in items:
            if isinstance(item, dict) and "productSkcId" in item:
                skc_id_list.append(item["productSkcId"])
        
        return skc_id_list
        
    except Exception as e:
        logger.info(f"解析商品期望到货地点配置失败：{str(e)}")
        return []


def search_goods_category(uid, headers: dict, cookies: dict, searchText: str = None,
                          max_retries: int = 5, main_task_id: str = None,
                          shop_abbr: str = None
                          ) -> dict:
    """
    搜索商品类目列表
    如果输入搜索值之后,第一条结果不是需要的类目id,那需要单独配置该类目id
    """
    shop_abbr = shop_abbr or ""
    _result = {}
    
    if not searchText:
        logger.info(f"店铺{shop_abbr}：未输入关键词，不查询商品")
        _result = {"code": 1, "msg": f"店铺{shop_abbr}：未输入关键词，无商品数据", "data": [], "remarks": "未选择类目"}
        auto_print_logger(_result, main_task_id=main_task_id)
        return _result
    
    for attempt in range(1, max_retries + 1):

        url = "https://agentseller.temu.com/anniston-agent-seller/category/search"
        data = {
            "searchText": searchText
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
            # 返回完整的类目路径列表
            category_paths = extract_category_paths_list(response.json())
            # for item in category_paths:
            #     logger.info(item)

            _result = {"code": 1, "msg": f"店铺{shop_abbr}：获取搜索商品类目列表成功，共{len(category_paths)}个类目", "data": category_paths, "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：获取搜索商品类目列表失败", "data": response.json(), "remarks": remarks}
            continue

    auto_print_logger(_result, main_task_id=main_task_id)

    return _result


def extract_category_paths_list(data: dict) -> list:
    """
    提取类目数据中 categoryPaths 的完整路径列表
    :param data: 接口返回的完整字典数据
    :return: 类目路径列表，每个元素是 {"cat_ids": [1,20,27], "cat_names": ["宠物用品","狗狗用品类","狗用进食垫"]}
    """
    try:
        # 1. 定位到 categoryPaths
        result = data.get("result", {})
        category_paths = result.get("categoryPaths", [])
        if not category_paths:
            logger.info("categoryPaths 为空，无类目数据")
            return []
        
        # 2. 定义所有类目节点的key（按层级顺序 cat1~cat10）
        cat_node_keys = [
            "cat1NodeVO", "cat2NodeVO", "cat3NodeVO", "cat4NodeVO",
            "cat5NodeVO", "cat6NodeVO", "cat7NodeVO", "cat8NodeVO",
            "cat9NodeVO", "cat10NodeVO"
        ]
        
        # 3. 遍历每个类目路径
        paths_list = []
        for path in category_paths:
            cat_ids = []
            cat_names = []
            
            for key in cat_node_keys:
                cat_node = path.get(key)
                # 节点非空且包含catId字段时，提取ID和名称
                if isinstance(cat_node, dict) and "catId" in cat_node:
                    cat_ids.append(cat_node["catId"])
                    cat_names.append(cat_node["catName"])
                # 节点为空时，终止遍历（后续层级必然为空）
                elif cat_node is None:
                    break
            
            # 只有当找到类目时才添加
            if cat_ids:
                paths_list.append({
                    "cat_ids": cat_ids,
                    "cat_names": cat_names
                })

        return paths_list
        
    except Exception as e:
        logger.info(f"解析类目路径失败：{str(e)}")
        return []


def format_category_display(cat_id_list: list[dict]) -> str:
    """
    格式化类目列表为简化的显示格式，只显示最子级别的类目ID和名称
    :param cat_id_list: 类目列表
    :return: 格式化后的字符串，如 "1745 狗用进食垫 1746 狗用盆"
    """
    if not cat_id_list:
        return ""
    
    display_parts = []
    for cat in cat_id_list:
        if isinstance(cat, dict):
            cat_ids = cat.get("cat_ids", [])
            cat_names = cat.get("cat_names", [])
            if cat_ids and cat_names:
                last_id = cat_ids[-1]
                last_name = cat_names[-1]
                display_parts.append(f"{last_id} {last_name}")
    
    return " ".join(display_parts)


def get_area_type_name(area_type: int) -> str:
    """
    获取期望到货地点类型的名称
    :param area_type: 类型代码
    :return: 类型名称
    """
    type_mapping = {
        1: "广东",
        2: "义乌",
        3: "按照历史发货地就近推荐"
    }
    return type_mapping.get(area_type, str(area_type))

# 查询所有分类子项  data为空 查询所有
# url = "https://agentseller.temu.com/anniston-agent-seller/category/children/list"
# data = {}

# 查询子分类项 如果 "result":{"categoryNodeVOS":[]}} 则是最终子分类
# url = "https://agentseller.temu.com/anniston-agent-seller/category/children/list"
# data = {
#     "parentCatId": 869
# }
# data = json.dumps(data, separators=(',', ':'))
# response = requests.post(url, headers=headers, cookies=cookies, data=data)
#
# logger.info(response.text)
# logger.info(response)





def get_expected_goods_place_list(uid, headers: dict, cookies: dict, category_paths: list = None, expectReceiveAreaConfigType: int = None,
                                  max_retries: int = 5, main_task_id: str = None,
                                  shop_abbr: str = None, page_number: int = 1
                                  ) -> dict:
    """
    获取商品期望到货地点列表
    根据category_paths提取的类目路径构建请求参数
    """
    shop_abbr = shop_abbr or ""
    _result = {}
    for attempt in range(1, max_retries + 1):

        url = "https://agentseller.temu.com/mms/turbo/supplier/pick/out/config/pageQuerySkcPickOutConfig"
        
        data = {
            "categoryList": [],
            "pageSize": 1000,
            "pageNumber": page_number
        }
        
        if expectReceiveAreaConfigType:
            all_types = [1, 2, 3]
            opposite_types = [t for t in all_types if t != expectReceiveAreaConfigType]
            data["expectReceiveAreaConfigTypeList"] = opposite_types

        if category_paths:
            for path in category_paths:
                cat_ids = path.get("cat_ids", [])
                if cat_ids:
                    category_entry = {}
                    for i, cat_id in enumerate(cat_ids, 1):
                        category_entry[f"cat{i}"] = cat_id
                    data["categoryList"].append(category_entry)


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
            result_data = response.json().get("result", {})
            total = result_data.get("total", 0)
            data_list = result_data.get("items", [])
            _result = {"code": 1, "msg": f"店铺{shop_abbr}：获取商品期望到货地点列表成功，共{total}个商品", "data": data_list, "total": total, "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：获取商品期望到货地点列表失败", "data": response.json(), "total": 0, "remarks": remarks}
            continue

    auto_print_logger(_result, main_task_id=main_task_id)

    return _result


def get_skc_pick_out_config_list(uid, headers: dict, cookies: dict, category_paths: list = None,
                                 max_retries: int = 5, main_task_id: str = None,
                                 shop_abbr: str = None
                                 ) -> list:
    """
    获取商品期望到货地点配置的 skc_id 列表
    """
    shop_abbr = shop_abbr or ""
    skc_id_list = []
    for attempt in range(1, max_retries + 1):

        url = "https://agentseller.temu.com/mms/turbo/supplier/pick/out/config/pageQuerySkcPickOutConfig"
        
        data = {
            "categoryList": [],
            "pageSize": 50,
            "pageNumber": 1
        }
        
        if category_paths:
            for path in category_paths:
                cat_ids = path.get("cat_ids", [])
                if cat_ids:
                    category_entry = {}
                    for i, cat_id in enumerate(cat_ids, 1):
                        category_entry[f"cat{i}"] = cat_id
                    data["categoryList"].append(category_entry)

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
            result_data = response.json().get("result", {})
            total = result_data.get("total", 0)
            items = result_data.get("items", [])
            skc_id_list = extract_skc_pick_out_config_list({"result": {"items": items}})
            auto_print_logger({"code": 1, "msg": f"店铺{shop_abbr}：获取商品期望到货地点配置成功，共{len(skc_id_list)}个SKC", "data": {}, "remarks": f"总记录数：{total}"}, main_task_id=main_task_id)
            break
        else:
            auto_print_logger({"code": -1, "msg": f"店铺{shop_abbr}：获取商品期望到货地点配置失败", "data": response.json(), "remarks": remarks}, main_task_id=main_task_id)
            continue

    return skc_id_list




def modify_expected_goods_place(uid, headers: dict, cookies: dict, skc_id_list: list[int] = None,
                                exceptReceiveAreaConfigType: int = None,
                              max_retries: int = 5, main_task_id: str = None,
                              shop_abbr: str = None
                              ) -> dict:
    """
    修改商品期望到货地点
    """
    shop_abbr = shop_abbr or ""
    _result = {}
    for attempt in range(1, max_retries + 1):

        url = "https://agentseller.temu.com/mms/turbo/supplier/pick/out/config/editExpectReceiveArea"
        data = {
            "exceptReceiveAreaConfigType": exceptReceiveAreaConfigType,
            "productSkcIdList": [str(skc_id) for skc_id in skc_id_list]
        }
        # exceptReceiveAreaConfigType
        # 1 广东
        # 2 义乌
        # 3 按照历史发货地就近推荐

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
            remarks = f"商品ID列表：{skc_id_list}"
            _result = {"code": 1, "msg": f"店铺{shop_abbr}：修改商品期望到货地点成功", "data": response.json(), "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}：修改商品期望到货地点失败，商品ID列表：{skc_id_list}", "data": response.json(), "remarks": remarks}
            continue

    auto_print_logger(_result, main_task_id=main_task_id)

    return _result


def get_expected_goods_place_thread(
        uid,
        headers,
        cookies,
        page_number,
        category_paths,
        expectReceiveAreaConfigType,
        shop_abbr,
        main_task_id=None
    ):
    """单页获取商品期望到货地点任务执行函数"""
    shop_abbr = shop_abbr or ""
    logger.info(f"店铺{shop_abbr}：开始处理第 {page_number} 页期望到货地点任务...")
    
    try:
        result = get_expected_goods_place_list(
            uid=uid,
            headers=headers,
            cookies=cookies,
            category_paths=category_paths,
            expectReceiveAreaConfigType=expectReceiveAreaConfigType,
            max_retries=5,
            main_task_id=main_task_id,
            shop_abbr=shop_abbr,
            page_number=page_number
        )
        
        if result.get("code") == 1:
            data_list = result.get("data", [])
            total_found = len(data_list)
            remarks = f"店铺{shop_abbr}：第{page_number}页查询到{total_found}个商品"
            auto_print_logger(msg=remarks, success_type="i", main_task_id=main_task_id)
            return {"page": page_number, "success": 1, "found": total_found, "data": data_list, "msg": f"店铺{shop_abbr}：第{page_number}页处理完成"}
        else:
            remarks = result.get("remarks", "")
            auto_print_logger(msg=f"店铺{shop_abbr}：第{page_number}页获取失败", remarks=remarks, success_type="e", main_task_id=main_task_id)
            return {"page": page_number, "success": 0, "found": 0, "data": [], "msg": f"店铺{shop_abbr}：第{page_number}页获取失败"}
    
    except RuntimeError as e:
        auto_print_logger(msg=f"店铺{shop_abbr}：子线程检测到任务停止，正在退出", remarks=f"当前页码={page_number}", success_type="w", main_task_id=main_task_id)
        return {"page": page_number, "success": 0, "found": 0, "data": [], "msg": f"店铺{shop_abbr}：子线程检测到任务停止"}
    
    except Exception as e:
        auto_print_logger(msg=f"店铺{shop_abbr}：第{page_number}页任务执行异常", remarks=f"原因：{e}", success_type="e", main_task_id=main_task_id)
        return {"page": page_number, "success": 0, "found": 0, "data": [], "msg": f"店铺{shop_abbr}：第{page_number}页执行异常：{str(e)}"}


def process_expected_goods_place_page(uid, headers, cookies, data_list, exceptReceiveAreaConfigType, shop_abbr, page_number, main_task_id=None):
    """处理单页商品期望到货地点任务执行函数"""
    shop_abbr = shop_abbr or ""
    logger.info(f"店铺{shop_abbr}：开始处理第{page_number}页期望到货地点任务，商品数：{len(data_list)}")

    try:
        skc_id_list = [item["productSkcId"] for item in data_list if item.get("productSkcId") is not None]

        if not skc_id_list:
            logger.info(f"店铺{shop_abbr}：该页无SKC数据，跳过修改")
            return {"page": page_number, "success": 1, "skc_id_list": []}

        result = do_modify_expected_goods_place(
            uid,
            headers,
            cookies,
            skc_id_list=skc_id_list,
            exceptReceiveAreaConfigType=exceptReceiveAreaConfigType,
            main_task_id=main_task_id,
            shop_abbr=shop_abbr,
        )

        if isinstance(result, dict) and result.get("code") == 1:
            return {"page": page_number, "success": 1, "skc_id_list": skc_id_list}
        else:
            return {"page": page_number, "success": 0, "skc_id_list": []}

    except RuntimeError as e:
        auto_print_logger(msg=f"店铺{shop_abbr}：子线程检测到任务停止，正在退出", success_type="w", main_task_id=main_task_id)
        return {"page": page_number, "success": 0, "skc_id_list": []}

    except Exception as e:
        auto_print_logger(msg=f"店铺{shop_abbr}：任务执行异常", remarks=f"原因：{e}", success_type="e", main_task_id=main_task_id)
        return {"page": page_number, "success": 0, "skc_id_list": []}


def do_modify_expected_goods_place(uid, headers: dict, cookies: dict, skc_id_list: list[int] = None, exceptReceiveAreaConfigType: int = None, main_task_id: str = None, shop_abbr: str = None):
    error_msg = ""
    result = {}

    for attempt in range(1, 4):
        try:
            modify_result = modify_expected_goods_place(
                uid,
                headers,
                cookies,
                skc_id_list=skc_id_list,
                exceptReceiveAreaConfigType=exceptReceiveAreaConfigType,
                main_task_id=main_task_id,
                shop_abbr=shop_abbr,
            )

            if isinstance(modify_result, dict) and modify_result.get("code") == 1:
                result = {"code": 1, "msg": f"店铺{shop_abbr}：修改商品期望到货地点执行完成", "data": {}, "remarks": f"执行完成"}
                break
            else:
                error_msg = str(modify_result.get("remarks", "")) if isinstance(modify_result, dict) else "未知错误"

        except Exception as e:
            auto_print_logger({"code": -1, "msg": f"店铺{shop_abbr}：修改商品期望到货地点执行异常", "remarks": f"店铺{shop_abbr}：异常信息：{str(e)}"}, main_task_id=main_task_id)

            error_msg = f"店铺{shop_abbr}：异常信息：{str(e)}"

        if attempt == 3:
            result = {"code": -1, "msg": f"店铺{shop_abbr}：修改商品期望到货地点执行出错", "data": {}, "remarks": error_msg}
            break

    return result



def final_modify_expected_goods_place(uid,
                                      headers: dict,
                                      cookies: dict,
                                      skc_id_list: list[int] = None,
                                      cat_id_list: list[dict] = None,
                                      exceptReceiveAreaConfigType: int = None,
                                      main_task_id: str = None, shop_abbr: str = None
                                      ):
    shop_abbr = shop_abbr or uid or ""
    if skc_id_list:
        result = do_modify_expected_goods_place(uid, headers, cookies, skc_id_list=skc_id_list,
                                                exceptReceiveAreaConfigType=exceptReceiveAreaConfigType,
                                                main_task_id=main_task_id,
                                                shop_abbr=shop_abbr)
        return result

    try:
        category_paths = extract_category_paths_list({"result": {"categoryPaths": []}})
        if cat_id_list:
            if isinstance(cat_id_list, list) and len(cat_id_list) > 0:
                if isinstance(cat_id_list[0], dict) and "cat_ids" in cat_id_list[0]:
                    category_paths = cat_id_list
                else:
                    category_paths = [{
                        "cat_ids": cat_id_list,
                        "cat_names": []
                    }]
        
        if not category_paths:
            auto_print_logger({"code": 1, "msg": f"店铺{shop_abbr}：未选择类目，无商品数据", "data": {"total_found": 0, "total_modified": 0}, "remarks": f"店铺{shop_abbr}：未选择类目"}, main_task_id=main_task_id)
            return {"code": 1, "msg": f"店铺{shop_abbr}：任务完成", "data": {"total_found": 0, "total_modified": 0}, "remarks": f"店铺{shop_abbr}：未选择类目"}

        category_display = format_category_display(cat_id_list)
        area_type_name = get_area_type_name(exceptReceiveAreaConfigType)

        logger.info(f"店铺{shop_abbr}：开始遍历期望到货地点数据，类目：【{category_display}】，目标类型：【{area_type_name}】")

        page = 1
        all_pages_data = []

        while True:
            logger.info(f"店铺{shop_abbr}：正在获取第{page}页数据...")
            page_resp = get_expected_goods_place_list(
                uid=uid,
                headers=headers,
                cookies=cookies,
                category_paths=category_paths,
                expectReceiveAreaConfigType=exceptReceiveAreaConfigType,
                max_retries=5,
                main_task_id=main_task_id,
                shop_abbr=shop_abbr,
                page_number=page
            )

            if page_resp.get("code") != 1:
                logger.error(f"店铺{shop_abbr}：获取第{page}页数据失败")
                break

            data_list = page_resp.get("data", [])
            page_found = len(data_list)

            logger.info(f"店铺{shop_abbr}：第{page}页查询到{page_found}个商品")

            if page_found == 0:
                logger.info(f"店铺{shop_abbr}：第{page}页无数据，停止遍历")
                break

            all_pages_data.append({
                "page": page,
                "data": data_list
            })

            page += 1

        total_pages = len(all_pages_data)
        total_found_all = sum(len(page["data"]) for page in all_pages_data)

        logger.info(f"店铺{shop_abbr}：遍历完成，共{total_pages}页，{total_found_all}个商品")

        if total_pages == 0:
            auto_print_logger({"code": 1, "msg": f"店铺{shop_abbr}：无商品数据", "data": {"total_found": 0, "total_modified": 0}, "remarks": f"店铺{shop_abbr}：无商品数据"}, main_task_id=main_task_id)
            return {"code": 1, "msg": f"店铺{shop_abbr}：任务完成", "data": {"total_found": 0, "total_modified": 0}, "remarks": f"店铺{shop_abbr}：无商品数据"}

        logger.info(f"店铺{shop_abbr}：开始分配{total_pages}页任务给子线程...")

        task_ids = []
        total_modified_all = 0

        for page_data in all_pages_data:
            page_number = page_data["page"]
            data_list = page_data["data"]

            task_kwargs = {
                "uid": uid,
                "headers": headers,
                "cookies": cookies,
                "page_number": page_number,
                "data_list": data_list,
                "exceptReceiveAreaConfigType": exceptReceiveAreaConfigType,
                "shop_abbr": shop_abbr,
                "main_task_id": main_task_id
            }

            task_id = get_task_log_manager().add_task(
                target_func=process_expected_goods_place_page, **task_kwargs,
                task_group=f"{shop_abbr}_期望到货地点",
                parent_task_id=main_task_id,
                is_main_task=0,
            )

            if task_id:
                task_ids.append(task_id)
                logger.info(f"店铺{shop_abbr}：成功分配第{page_number}页任务 | 任务ID：{task_id}")
            else:
                logger.error(f"店铺{shop_abbr}：分配第{page_number}页任务失败")

        if not task_ids:
            logger.error(f"店铺{shop_abbr}：未分配任何任务")
            return None

        logger.info(f"店铺{shop_abbr}：等待{len(task_ids)}个期望到货地点任务完成...")

        for task_id in task_ids:
            try:
                result = get_task_log_manager().get_task_result(task_id, timeout=3600)

                if isinstance(result, dict) and result.get("success") == 1:
                    page_skc_id_list = result.get("skc_id_list", [])
                    if page_skc_id_list:
                        total_modified_all += len(page_skc_id_list)
            except TimeoutError:
                logger.error(f"店铺{shop_abbr}：任务{task_id}等待超时")
            except Exception as e:
                logger.error(f"店铺{shop_abbr}：获取任务{task_id}结果异常：{e}")

        if total_modified_all > 0:
            auto_print_logger({"code": 1, "msg": f"店铺{shop_abbr}：所有页处理完成", "data": {"total_found": total_found_all, "total_modified": total_modified_all}, "remarks": f"店铺{shop_abbr}：共处理{total_pages}页，查询到{total_found_all}个商品，成功修改{total_modified_all}个商品ID，类目：【{category_display}】，目标类型：【{area_type_name}】"}, main_task_id=main_task_id)

        return {"code": 1, "msg": f"店铺{shop_abbr}：任务完成", "data": {"total_found": total_found_all, "total_modified": total_modified_all}, "remarks": f"店铺{shop_abbr}：修改商品期望到货地点执行完成，类目：【{category_display}】，目标类型：【{area_type_name}】"}
            
    except Exception as e:
        auto_print_logger({"code": -1, "msg": f"店铺{shop_abbr}：修改商品期望到货地点执行异常", "remarks": f"店铺{shop_abbr}：异常信息：{str(e)}"}, main_task_id=main_task_id)

    return None