import json

from loguru import logger

from config.middleware_config import db, generator
from temu_modules.temu_modules_tools.usual_tools import get_shop_userinfo
from utils.bitClient import _ensure_session
from utils.directClient import create_temu_session
from utils.log_utils import auto_print_logger


def update_headers_cookies_shop_info(uid, shop_name, shop_abbr: str, mall_id: int, auto_headers: dict, auto_cookies: dict):
    """
    更新数据库中cookies，headers
    :param shop_abbr:
    :param auto_headers:
    :param auto_cookies:
    :return:
    """
    # 有缩写：执行更新
    if not uid:
        return {
            "code": -1,
            "msg": "更新失败",
            "remarks": f"未提供店铺uid，请检查后重试",
            "data": {}
        }

    data = db.execute_sql("update shops set shop_name = ?, shop_abbr = ?, headers = ?, cookies = ?, connect_status = ?, mall_id = ?, update_time = datetime('now', '+8 hours') where uid = ?",
                          params=(shop_name, shop_abbr, json.dumps(auto_headers), json.dumps(auto_cookies), "已连接", mall_id, uid),
                          fetch="none")
    if data:
        result = {
            "code": 1, "msg": "更新成功", "data": {"auto_cookies": auto_cookies, "auto_headers": auto_headers}, "remarks": "店铺更新成功"
        }
        auto_print_logger(result, "success")
        return result
    else:
        result = {
            "code": -1,
            "msg": "更新失败",
            "remarks": f"{shop_abbr}：无法更新cookies和headers，请检查",
            "data": {}
        }
        auto_print_logger(result, "error")
        return result

# 数据库查询cookies 传入uid
def get_shop_info_db(uid: str):
    """
    从数据库中查询店铺信息。
    保证在数据库记录存在的情况下，至少返回基础信息。
    headers 和 cookies 的加载是可选的，失败不会导致整个函数失败。

    :param uid: 店铺的唯一ID
    :return: 包含店铺信息的字典，如果数据库中无此记录则返回 None。
    """
    try:
        # 1. 【核心步骤】先获取所有基础信息
        headers_cookies_query = db.execute_sql(
            "select * from shops where uid = ?",
            params=(uid,),
            fetch="fetch_one"
        )

        # 检查数据库中是否存在该记录
        if headers_cookies_query is None:
            # logger.warning(f"在数据库中未找到 uid 为 '{uid}' 的店铺记录。")
            return None

        # 2. 【核心步骤】先将基础信息存入最终结果
        # headers_cookies_query 已经是一个包含所有字段的字典
        final_shop_info = headers_cookies_query.copy() # 使用 copy() 避免修改原始查询结果

        # 3. 【核心步骤】尝试加载 headers 和 cookies
        try:
            _auto_cookies = final_shop_info.get("cookies")
            _auto_headers = final_shop_info.get("headers")
            _auto_cookies_us = final_shop_info.get("cookies_us")
            _auto_cookies_eu = final_shop_info.get("cookies_eu")

            # 检查数据库中的值是否为 NULL (在Python中是 None)
            if _auto_cookies and _auto_headers:
                auto_cookies = json.loads(_auto_cookies)
                auto_headers = json.loads(_auto_headers)

                # 将加载成功的字典更新到最终结果中
                final_shop_info["cookies"] = auto_cookies
                final_shop_info["headers"] = auto_headers
                # logger.info(f"成功为 uid '{uid}' 加载 headers 和 cookies。")
            else:
                # 如果数据库中的值就是 NULL，也记录一下
                # logger.warning(f"uid '{uid}' 的 headers 或 cookies 在数据库中为 NULL，跳过加载。")
                # 从结果中移除原始的JSON字符串，避免混淆
                if "cookies" in final_shop_info:
                    del final_shop_info["cookies"]
                if "headers" in final_shop_info:
                    del final_shop_info["headers"]

            # 加载 cookies_us
            if _auto_cookies_us:
                try:
                    auto_cookies_us = json.loads(_auto_cookies_us)
                    final_shop_info["cookies_us"] = auto_cookies_us
                except (json.JSONDecodeError, TypeError):
                    # 加载失败则删除该字段
                    if "cookies_us" in final_shop_info:
                        del final_shop_info["cookies_us"]
            
            # 加载 cookies_eu
            if _auto_cookies_eu:
                try:
                    auto_cookies_eu = json.loads(_auto_cookies_eu)
                    final_shop_info["cookies_eu"] = auto_cookies_eu
                except (json.JSONDecodeError, TypeError):
                    # 加载失败则删除该字段
                    if "cookies_eu" in final_shop_info:
                        del final_shop_info["cookies_eu"]

        except (json.JSONDecodeError, TypeError) as e:
            # 捕获JSON解码错误或类型错误（比如值是None）
            logger.error(f"为 uid '{uid}' 解析 headers 或 cookies 时发生错误: {e}")
            # 加载失败，不做任何事，final_shop_info 中不会有解析后的 headers 和 cookies

        # 4. 【核心步骤】无论如何，都返回包含基础信息的字典
        return final_shop_info

    except Exception as e:
        # 捕获最外层的、意想不到的严重错误（如数据库连接失败）
        logger.error(f"查询 uid '{uid}' 的店铺信息时发生错误: {e}")
        return None


# 检测店铺连接 传入uid查询cookies测试登录
def test_connect_shop(uid: str, log: bool = True):
    """检测店铺连接 如果重试次数过多会自动重新登录
    :return: True / False
    """
    tries = 0
    while tries < 2:
        try:
            shop_info = get_shop_info_db(uid)

            resp = get_shop_userinfo(uid, shop_info["headers"], shop_info["cookies"], max_retries=1, log=False)

            # 检测是否为卖家中心登录
            # resp = get_up_new_lifecycle_list(uid, shop_info["headers"], shop_info["cookies"], page_num=1, max_retries=1, log=log)

            if resp["code"] == 1:
                logger.success(f"✅ 店铺{shop_info.get('shop_abbr') if shop_info.get('shop_abbr') else uid}检测连接成功")
            else:
                logger.error(f"❌ 店铺{shop_info.get('shop_abbr') if shop_info.get('shop_abbr') else uid}检测连接失败")
                return False

            if log:
                logger.success(f"✅ 店铺{shop_info.get('shop_abbr') if shop_info.get('shop_abbr') else uid}检测连接成功")

            db.execute_sql(
                "update shops set connect_status = ?, update_time = datetime('now', '+8 hours') where uid = ?",
                params=("已连接", uid),
                fetch="none")
            return True

        except Exception as e:
            if log:
                # 现在这里的日志会更准确地反映失败原因
                logger.error(f"❌ 店铺{uid}检测连接失败, 原因: {e}")

            db.execute_sql(
                "update shops set connect_status = ?, update_time = datetime('now', '+8 hours') where uid = ?",
                params=("未连接", uid),
                fetch="none")
            tries += 1

    return False


def bit_browser_login(uid: str):
    try:
        shop_info = get_shop_info_db(uid)

        if not shop_info:  # 先判断是否查到店铺信息
            raise Exception(f"未找到UID为{uid}的店铺记录，无法获取browser_id")

        logger.info(f"🔄 尝试连接比特浏览器...")
        session = _ensure_session(shop_info["browser_id"])
        logger.success("✅ 比特浏览器连接成功！")
    except Exception as e:
        raise e

    auto_headers, auto_cookies = session.get_latest_credentials()

    if not session:
        db.execute_sql(
            "update shops set connect_status = ?, update_time = datetime('now', '+8 hours') where uid = ?",
            params=("未连接", uid),
            fetch="none")
        raise Exception("未找到比特浏览器ID为{}的窗口".format(shop_info["browser_id"]))

    return auto_headers, auto_cookies

## ========== 连接店铺 ========== ##
def connect_shop(
         uid: str,
         login_type: str = "ikun",
         reload_cookies: bool = False,
         headless: bool = True,
         auto_close: bool = True,
         window_size: tuple[int, int] = (1920, 1080),
         fetch_all_region_cookies: bool = False
     ):
    """
    连接店铺 直接执行连接或重连，而不是尝试更新
    提供缩写可以免去获取缩写的一步
    :param login_type: bit or 其他字符串
    :param reload_cookies: 强制重新登录获取cookie，而不是检测并复用
    :param headless: 如果选择bit 则headless参数无作用
    """
    # cookies中只有seller_temp影响登录状态

    shop_info = get_shop_info_db(uid)

    # 尽量检测登录状态，而不是强制重新登录
    if not reload_cookies:
        try:
            is_login = test_connect_shop(uid, False)
            if is_login:
                result = {
                    "code": 1,
                    "msg": f"店铺{shop_info.get("shop_abbr", "")}连接成功",
                    "remarks": "店铺已登录"
                }
                return result
        except Exception:
            logger.info(f"✅开始执行连接店铺")

    try:
        if login_type == "bit":
            auto_headers, auto_cookies = bit_browser_login(uid)
        else:
            try:
                task_kwargs = {
                    "uid": uid,
                    "shop_abbr": shop_info.get("shop_abbr", ""),
                    "username": shop_info["phone"],
                    "password": shop_info["password"],
                    "auto_close": auto_close,
                    "headless": headless,
                    "window_size": window_size,
                    "reload_cookies": reload_cookies,
                    "fetch_all_region_cookies": fetch_all_region_cookies
                }

                # 添加任务
                login_result = create_temu_session(**task_kwargs)

                auto_headers, auto_cookies = login_result["headers"], login_result["cookies"]

            except Exception as e:
                result = {
                    "code": -1,
                    "msg": f"店铺{shop_info.get("shop_abbr", "")}连接出错",
                    "remarks": str(e)
                }
                auto_print_logger(result)

                return result

        # ===== 核心改造：适配userinfo返回列表的逻辑 =====
        # 1. 获取店铺列表（原user_info改为列表）
        shop_info_list = get_shop_userinfo(uid, auto_headers, auto_cookies, max_retries=1, log=False)["data"]
        # 校验返回格式（兼容异常情况）
        if not isinstance(shop_info_list, list) or len(shop_info_list) == 0:
            raise Exception("获取店铺列表为空或格式错误")

        # 2. 判断是否为多店铺
        total_shops = len(shop_info_list)
        if total_shops == 1:
            logger.info(f"✅ 店铺{shop_info.get("shop_abbr", "")} 单店铺更新逻辑")
            # 单店铺：沿用原逻辑，取第一个
            user_info = shop_info_list[0]
            main_shop_abbr = user_info["店铺缩写"]

            # 更新主店铺信息
            update_resp = update_headers_cookies_shop_info(
                uid,
                user_info["店铺名称"],
                user_info["店铺缩写"],
                user_info["mall_id"],
                auto_headers,
                auto_cookies
            )
            if update_resp["code"] != 1:
                result = {
                    "code": -1,
                    "msg": f"店铺{main_shop_abbr}连接失败",
                    "remarks": update_resp["remarks"]
                }
                auto_print_logger(result)
                return result

            result = {
                "code": 1,
                "remarks": main_shop_abbr,
                "msg": f"店铺{main_shop_abbr}连接成功"
            }
            auto_print_logger(result)
            return result

        else:
            # 多店铺：先查数据库标记
            multi_shop_data = db.execute_sql(
                "select is_multi_shops from shops where uid = ?",
                params=(uid,),
                fetch="fetch_one"
            )
            is_multi_shops = multi_shop_data["is_multi_shops"] if multi_shop_data else "0"

            # 标记为多店铺账号（仅第一次执行）
            if is_multi_shops != "1":
                logger.info(f"✅ 店铺{shop_info.get("shop_abbr", "")} 多店铺多信息更新逻辑")

                db.execute_sql(
                    "update shops set is_multi_shops = ? WHERE uid = ?",
                    params=("1", uid),
                    fetch="none"
                )
                logger.info(f"账号{shop_info["phone"]}标记为多店铺账号，共{total_shops}个店铺")

                # 未标记过：批量创建子店铺（复用cookie/headers，仅修改mall_id）
                # 第一个店铺作为主账号，沿用原uid
                main_shop = shop_info_list[0]
                main_shop_abbr = main_shop["店铺缩写"]

                main_headers = auto_headers.copy()
                main_cookies = auto_cookies.copy()
                main_headers["mallid"] = str(main_shop["mall_id"])
                main_cookies["mallid"] = str(main_shop["mall_id"])

                # 更新主店铺信息
                update_resp = update_headers_cookies_shop_info(
                    uid,
                    main_shop["店铺名称"],
                    main_shop["店铺缩写"],
                    main_shop["mall_id"],
                    main_headers,
                    main_cookies
                )
                if update_resp["code"] != 1:
                    raise Exception(f"主店铺{main_shop_abbr}更新失败：{update_resp["remarks"]}")

                # 批量创建子店铺（从第二个开始）
                for idx, sub_shop in enumerate(shop_info_list[1:], start=2):
                    sub_shop_data = sub_shop

                    # 复用主账号的cookie/headers，仅修改mall_id
                    sub_headers = auto_headers.copy()
                    sub_cookies = auto_cookies.copy()
                    sub_headers["mallid"] = str(sub_shop_data["mall_id"])  # 关键：修改为子店铺的mall_id
                    sub_cookies["mallid"] = str(sub_shop_data["mall_id"])

                    # 生成子店铺uid（可根据你的规则调整，比如主uid+序号）
                    sub_uid = generator.generate_id()

                    # 创建子店铺记录（复用手机号/密码，仅修改mall_id和uid）
                    db.execute_sql(
                        """
                        INSERT INTO shops (uid, phone, password, shop_abbr, shop_name, headers, cookies,
                                           is_multi_shops, mall_id, connect_status,
                                           create_time, update_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                                datetime('now', '+8 hours'), datetime('now', '+8 hours'))
                        """,
                        params=[
                            sub_uid,
                            shop_info["phone"],
                            shop_info["password"],
                            sub_shop_data['店铺缩写'],  # 店铺缩写
                            sub_shop_data.get("店铺名称", ""),
                            sub_headers,
                            sub_cookies,
                            "1",  # 标记多店铺
                            str(sub_shop_data["mall_id"]),  # 当前mall_id
                            "已连接"
                        ],
                        fetch="none"
                    )
                    logger.info(f"创建子店铺{idx}：{sub_shop_data["店铺名称"]}（uid={sub_uid}）")

                result = {
                    "code": 1,
                    "remarks": f"主店铺{main_shop_abbr}，共{total_shops}个店铺",
                    "msg": f"多店铺账号连接成功，主店铺{main_shop_abbr}，已创建{total_shops - 1}个子店铺"
                }
                auto_print_logger(result)
                return result

            else:
                # ========== 核心调整：多店铺已标记，执行单店铺逻辑 ==========
                logger.info(f"✅ 店铺{shop_info.get("shop_abbr", "")} 多店铺单信息更新逻辑")

                # 从数据库获取当前主账号对应的店铺信息（不再按索引取）
                main_shop_data = db.execute_sql(
                    "select shop_name, shop_abbr, mall_id from shops where uid = ?",
                    params=(uid,),
                    fetch="fetch_one"
                )

                if not main_shop_data:
                    raise Exception(f"主账号{uid}在数据库中无店铺信息")

                main_headers = auto_headers.copy()
                main_cookies = auto_cookies.copy()
                main_headers["mallid"] = str(main_shop_data["mall_id"])
                main_cookies["mallid"] = str(main_shop_data["mall_id"])

                # 复用单店铺的更新逻辑（仅店铺信息来源不同）
                update_resp = update_headers_cookies_shop_info(
                    uid,
                    main_shop_data["shop_name"],
                    main_shop_data["shop_abbr"],
                    main_shop_data["mall_id"],
                    main_headers,
                    main_cookies
                )

                if update_resp["code"] != 1:
                    result = {
                        "code": -1,
                        "msg": f"店铺{main_shop_data["shop_abbr"]}连接失败",
                        "remarks": update_resp["remarks"]
                    }
                    auto_print_logger(result)
                    return result

                result = {
                    "code": 1,
                    "remarks": main_shop_data["shop_abbr"],
                    "msg": f"店铺{main_shop_data["shop_abbr"]}连接成功（多店铺已标记）"
                }
                auto_print_logger(result)
                return result

    except Exception as e:
        # 异常处理：标记为未连接
        db.execute_sql("update shops set connect_status = ?, update_time = datetime('now', '+8 hours') where uid = ?",
                       params=("未连接", uid),
                       fetch="none")
        result = {
            "code": -1,
            "remarks": str(e),
            "msg": f"店铺{shop_info.get("shop_abbr", "") if shop_info else uid}连接失败"
        }
        auto_print_logger(result)
        return result

def connect_shop_playwright(uid: str,
                 login_type: str,
                 reload_cookies: bool = False,
                 headless: bool=True,
                 auto_close: bool=True,
                 window_size: tuple[int, int] = (1920, 1080)
                 ):
    """
    连接店铺 直接执行连接或重连，而不是尝试更新
    提供缩写可以免去获取缩写的一步
    :param login_type: bit or 其他字符串
    :param reload_cookies: 强制重新登录获取cookie，而不是检测并复用
    :param headless: 如果选择bit 则headless参数无作用
    """
    # cookies中只有seller_temp影响登录状态

    shop_info = get_shop_info_db(uid)

    if not reload_cookies:
        try:
            is_login = test_connect_shop(uid, False)
            if is_login:
                result = {
                    "code": 1,
                    "msg": f"店铺{shop_info.get("shop_abbr", "")}连接成功",
                    "remarks": "店铺已登录"
                }
                return result
        except Exception:
            logger.info(f"✅开始执行连接店铺")

    try:
        if login_type == "bit":
            auto_headers, auto_cookies = bit_browser_login(uid)
        else:
            try:
                task_kwargs = {
                    "uid": uid,
                    "shop_abbr": shop_info.get("shop_abbr", ""),
                    "username": shop_info["phone"],
                    "password": shop_info["password"],
                    "auto_close": auto_close,
                    "headless": headless,
                    "window_size": window_size
                }

                # 添加任务
                login_result = create_temu_session(**task_kwargs)
                mall_id_list = login_result["mall_id_list"]
                auto_headers, auto_cookies = login_result["headers"], login_result["cookies"]

                result = []
                if len(mall_id_list) > 1:
                    # 先查询多店铺标记（注意：确保数据库字段是is_multi_shops）
                    multi_shop_data = db.execute_sql(
                        "select is_multi_shops from shops where uid = ?",
                        params=(uid,),
                        fetch="fetch_one"
                    )
                    is_multi_shops = multi_shop_data["is_multi_shops"] if multi_shop_data else "0"

                    # 只更新一次多店铺标记（移出循环，避免重复执行）
                    if is_multi_shops != "1":
                        db.execute_sql(
                            "update shops set is_multi_shops = ? WHERE uid = ?",
                            params=("1", uid),
                            fetch="none"
                        )

                    # 遍历mall_id处理每个店铺
                    for i in range(len(mall_id_list)):
                        current_uid = uid  # 初始化当前UID为原始UID
                        # 非第一个店铺：生成新UID并插入
                        if i != 0:
                            new_uid = generator.generate_id()
                            # 插入新店铺记录（核心：用new_uid）
                            db.execute_sql(
                                """
                                INSERT INTO shops (uid, phone, password, shop_abbr, browser_id,
                                                   is_multi_shops, mall_id, connect_status,
                                                   create_time, update_time)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                                        datetime('now', '+8 hours'), datetime('now', '+8 hours'))
                                """,
                                params=[
                                    new_uid,  # 新生成的UID（关键！）
                                    shop_info["phone"],
                                    shop_info["password"],
                                    f"{shop_info['shop_abbr']}_multi_{i}",  # 多店铺缩写
                                    shop_info.get("browser_id", ""),  # 继承browser_id
                                    "1",  # 标记多店铺
                                    mall_id_list[i],  # 当前mall_id
                                    "未连接"
                                ],
                                fetch="none"
                            )
                            current_uid = new_uid  # 切换为新UID

                        # 更新当前mall_id的cookies
                        auto_cookies["mall_id"] = mall_id_list[i]
                        # 获取店铺信息
                        user_info = get_shop_userinfo(uid, auto_headers, auto_cookies, max_retries=1, log=False)
                        # print(user_info)

                        # 用current_uid更新店铺信息（兼容新旧UID）
                        update_resp = update_headers_cookies_shop_info(
                            current_uid,
                            user_info["店铺名称"],
                            user_info["店铺缩写"],
                            mall_id_list[i],
                            auto_headers,
                            auto_cookies
                        )

                        # 收集结果
                        if update_resp["code"] != 1:
                            result.append(f"店铺{user_info["店铺缩写"]}（UID:{current_uid}）连接失败")
                        else:
                            result.append(f"店铺{user_info["店铺缩写"]}（UID:{current_uid}）连接成功")

                    result = {
                        "code": 1,
                        "remarks": result,
                        "msg": f"店铺连接结果{result}"
                    }

                    auto_print_logger(result)

                    return result
                else:
                    # 获取店铺信息
                    user_info = get_shop_userinfo(uid, auto_headers, auto_cookies, max_retries=1, log=False)
                    update_resp = update_headers_cookies_shop_info(uid, user_info["店铺名称"],
                                                                   user_info["店铺缩写"],
                                                                   user_info["mall_id"], auto_headers,
                                                                   auto_cookies)
                    if update_resp["code"] != 1:
                        result = {
                            "code": -1,
                            "msg": f"店铺{user_info["店铺缩写"]}连接失败",
                            "remarks": update_resp["remarks"]
                        }

                        auto_print_logger(result)
                        return result

                    result = {
                        "code": 1,
                        "remarks": user_info["店铺缩写"],
                        "msg": f"店铺{user_info["店铺缩写"]}连接成功"
                    }
                    auto_print_logger(result)
                    return result



            except Exception as e:
                logger.error(f"❌ 登录失败：{e}")
                result = {
                    "code": -1,
                    "msg": f"店铺{shop_info.get("shop_abbr", "")}连接失败",
                    "remarks": "请检查店铺 账号（手机号）、密码 是否填写正确"
                }
                auto_print_logger(result)
                return result

        # ===== 更新店铺信息和headers,cookie =====

        # 获取店铺信息
        user_info = get_shop_userinfo(uid, auto_headers, auto_cookies, max_retries=1, log=False)
        update_resp = update_headers_cookies_shop_info(uid, user_info["店铺名称"], user_info["店铺缩写"], user_info["mall_id"], auto_headers, auto_cookies)
        if update_resp["code"] != 1:
            result = {
                "code": -1,
                "msg": f"店铺{user_info["店铺缩写"]}连接失败",
                "remarks": update_resp["remarks"]
            }

            auto_print_logger(result)
            return result

        result = {
            "code": 1,
            "remarks": user_info["店铺缩写"],
            "msg": f"店铺{user_info["店铺缩写"]}连接成功"
        }
        auto_print_logger(result)
        return result

    except Exception as e:
        db.execute_sql("update shops set connect_status = ?, update_time = datetime('now', '+8 hours') where uid = ?",
                       params=("未连接", uid),
                       fetch="none")
        result = {
            "code": -1,
            "remarks": str(e),
            "msg": f"店铺{shop_info.get("shop_abbr", "")}连接失败"
        }
        auto_print_logger(result)
        return result