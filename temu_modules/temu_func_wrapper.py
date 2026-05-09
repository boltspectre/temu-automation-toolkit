import time

from loguru import logger

from config.start_config import MAIN_TASK_MANAGER
from temu_modules.temu_function.caiwu_func.caiwu_excel import make_caiwu_excel
from temu_modules.temu_function.caiwu_func.caiwu_sku_excel import generate_sku_summary
from config.common_config import config_manager
from temu_modules.temu_function.caiwu_func.caiwu_main import merge_all_months_excel, record_all_need_colum_to_excel, record_skc_to_table
from temu_modules.temu_function.caiwu_func.caiwu_download import download_all_caiwu_excel_complete
from temu_modules.temu_function.adjust_price_manage import final_adjust_price_manage
from temu_modules.temu_function.apply_activity import final_apply_activity, filter_activityType_list
from temu_modules.temu_function.expected_goods_place import final_modify_expected_goods_place
from temu_modules.temu_function.jit_govern import do_all_open_jit_modify_govern
from temu_modules.temu_function.modify_price import all_modify_price
from temu_modules.temu_function.upload_real_pic import final_upload_real_pic
from utils.TemuBase import get_shop_info_db, connect_shop


def temu_login_warpper(
        uid,
        login_type: str = "auto",
        reload_cookies: bool = False,
        headless: bool = True,
        auto_close: bool = True,
        window_size: tuple[int, int] = (1920, 1080),
        fetch_all_region_cookies: bool = False,
):
    try:
        task_auto_login = config_manager.get_or_set_config(
            "task_auto_login",
            "是"
        )

        if task_auto_login == "是":
            connect_result = connect_shop(uid, login_type=login_type, reload_cookies=reload_cookies, headless=headless,
                                          auto_close=auto_close, window_size=window_size, fetch_all_region_cookies=fetch_all_region_cookies)
            if connect_result["code"] != 1:
                return {"code": -1, "data": {}, "msg": connect_result.get("msg", "店铺连接失败"), "remarks": connect_result.get("remarks", "店铺连接失败")}

        shop_info = get_shop_info_db(uid)
        required_keys = ["headers", "cookies", "shop_abbr", "mall_id"]
        if not isinstance(shop_info, dict) or any(key not in shop_info for key in required_keys):
            return {"code": -1, "data": {}, "msg": "店铺信息关键字段缺失"}
        return {"code": 1, "data": shop_info, "msg": "登录成功", "remarks": ""}
    except Exception as e:
        logger.error(f"❌ uid:{uid} 登录失败：{str(e)[:200]}")
        return {"code": -1, "data": {}, "msg": f"登录异常", "remarks": str(e)[:200]}


def upload_real_pic_task_wrapper(
        uid,
        input_check_type_list: list = None,
        input_rapid_screen_status_list: list = None,
        input_spu_id_list: list = None,
        black_word_type_list: list = None,
        goods_status_list: list = None,
        sleep_open: bool = False,
        login_type: str = "auto",
        reload_cookies: bool = False,
        headless: bool = True,
        custom_fixed_upload_img: bool = False,
        main_task_id=None,
        auto_close: bool = True,
        window_size: tuple[int, int] = (1920, 1080)
):
    login_result = temu_login_warpper(uid, login_type=login_type, reload_cookies=reload_cookies, headless=headless,
                                 auto_close=auto_close, window_size=window_size)
    if login_result["code"] != 1:
        return {"code": -1, "msg": f"{login_result['msg']}", "remarks":login_result["remarks"], "data": {}}

    shop_info = login_result["data"]
    shop_abbr = shop_info.get("shop_abbr", "未知店铺")
    mall_id = shop_info.get("mall_id", 0)

    try:
        result = final_upload_real_pic(
            uid=uid,
            headers=shop_info["headers"],
            cookies=shop_info["cookies"],
            shop_abbr=shop_abbr,
            input_check_type_list=input_check_type_list,
            input_rapid_screen_status_list=input_rapid_screen_status_list,
            input_spu_id_list=input_spu_id_list,
            black_word_type_list=black_word_type_list,
            goods_status_list=goods_status_list,
            sleep_open=sleep_open,
            custom_fixed_upload_img=custom_fixed_upload_img,
            mall_id=mall_id,
            main_task_id=main_task_id,
        )
        return result
    except Exception as e:
        logger.error(f"❌ 店铺{shop_abbr} 实拍图上传失败：{str(e)[:200]}")
        return {"code": -1, "msg": f"实拍图上传失败：{str(e)[:200]}", "data": {}, "remarks": str(e)[:500]}


def modify_price_task_wrapper(
        uid,
        input_spu_id_list: list = None,
        minu_price: float = None,
        modify_times: int = None,
        login_type: str = "auto",
        reload_cookies: bool = False,
        headless: bool = True,
        main_task_id=None,
        auto_close: bool = True,
        window_size: tuple[int, int] = (1920, 1080)
):
    login_result = temu_login_warpper(uid, login_type=login_type, reload_cookies=reload_cookies, headless=headless,
                                 auto_close=auto_close, window_size=window_size)
    if login_result["code"] != 1:
        return {"code": -1, "msg": f"{login_result['msg']}", "remarks":login_result["remarks"],  "data": {}}

    shop_info = login_result["data"]
    shop_abbr = shop_info.get("shop_abbr", "未知店铺")
    mall_id = shop_info.get("mall_id", 0)

    if not modify_times:
        modify_times = int(config_manager.get_or_set_config(
            "global_modify_times",
            "10"
        ))

    if not minu_price:
        minu_price = float(config_manager.get_or_set_config(
            "global_minu_price",
            "0.01"
        ))

    try:
        result = all_modify_price(
            uid=uid,
            headers=shop_info["headers"],
            cookies=shop_info["cookies"],
            minu_price=minu_price,
            modify_times=modify_times,
            shop_abbr=shop_abbr,
            spu_id_list=input_spu_id_list,
            mall_id=mall_id,
            main_task_id=main_task_id,
        )
        return result
    except Exception as e:
        logger.error(f"❌ 店铺{shop_abbr} 核价任务失败：{str(e)[:200]}")
        return {"code": -1, "msg": f"核价任务失败：{str(e)[:200]}", "data": {}, "remarks": str(e)[:500]}


def adjust_price_manage_task_wrapper(
        uid,
        order_id_list: list = None,
        skc_id_list: list = None,
        reason: str = None,
        login_type: str = "auto",
        reload_cookies: bool = False,
        headless: bool = True,
        main_task_id: str = None,
        auto_close: bool = True,
        window_size: tuple[int, int] = (1920, 1080)
):
    login_result = temu_login_warpper(uid, login_type=login_type, reload_cookies=reload_cookies, headless=headless,
                                 auto_close=auto_close, window_size=window_size)
    if login_result["code"] != 1:
        return {"code": -1, "msg": f"{login_result['msg']}", "remarks":login_result["remarks"], "data": {}}

    shop_info = login_result["data"]
    shop_abbr = shop_info.get("shop_abbr", "未知店铺")

    try:
        result = final_adjust_price_manage(
            uid=uid,
            headers=shop_info["headers"],
            cookies=shop_info["cookies"],
            max_retries=5,
            order_id_list=order_id_list,
            skc_id_list=skc_id_list,
            reason=reason,
            shop_abbr=shop_abbr,
            main_task_id=main_task_id
        )
        return result
    except Exception as e:
        logger.error(f"❌ 店铺{shop_abbr} 调价管理任务失败：{str(e)[:200]}")
        return {"code": -1, "msg": f"调价管理任务失败：{str(e)[:200]}", "data": {}, "remarks": str(e)[:500]}



def jit_govern_wrapper(
        uid,
        spu_id_list: list = None,
        final_num: int = None,
        start_date: str = None,
        end_date: str = None,
        login_type: str = "auto",
        reload_cookies: bool = False,
        headless: bool = True,
        main_task_id: str = None,
        auto_close: bool = True,
        window_size: tuple[int, int] = (1920, 1080),
        wait_all_complete: bool = True,
        timeout: int = 3600
):
    """
    开通JIT维护库存封装函数
    
    Args:
        uid: 用户ID
        spu_id_list: SPU ID列表，格式: [123456, 789012, ...]
        final_num: 目标库存数量，为空时从数据库获取默认值
        start_date: 开始日期，格式如 20260202
        end_date: 结束日期，格式如 20260208
        login_type: 登录类型，默认"auto"
        reload_cookies: 是否重新加载cookies，默认False
        headless: 是否无头模式，默认True
        main_task_id: 主任务ID
        auto_close: 是否自动关闭浏览器，默认True
        window_size: 浏览器窗口大小，默认(1920, 1080)
        wait_all_complete: 是否等待所有任务完成，默认True
        timeout: 任务等待超时时间（秒），默认3600秒
        
    Returns:
        dict: 包含操作结果的字典
    """
    login_result = temu_login_warpper(uid, login_type=login_type, reload_cookies=reload_cookies, headless=headless,
                                 auto_close=auto_close, window_size=window_size)
    if login_result["code"] != 1:
        return {"code": -1, "msg": f"{login_result['msg']}", "remarks":login_result["remarks"], "data": {}}

    shop_info = login_result["data"]
    shop_abbr = shop_info.get("shop_abbr", "未知店铺")

    # 如果final_num为空，从数据库获取默认值
    if final_num is None:
        try:
            from config.common_config import config_manager
            final_num = int(config_manager.get_or_set_config("jit_default_final_num", "500"))
        except Exception as e:
            logger.error(f"获取JIT默认库存数量失败：{str(e)}")
            final_num = 500  # 如果获取失败，使用默认值500

    try:
        result = do_all_open_jit_modify_govern(
            uid=uid,
            headers=shop_info["headers"],
            cookies=shop_info["cookies"],
            spu_id_list=spu_id_list,
            start_date=start_date,
            end_date=end_date,
            final_num=final_num,
            main_task_id=main_task_id,
            shop_abbr=shop_abbr,
            mall_id=shop_info.get("mall_id"),
            wait_all_complete=wait_all_complete,
            timeout=timeout,
        )
        return result
    except Exception as e:
        logger.error(f"❌ 店铺{shop_abbr} JIT库存管理任务失败：{str(e)[:200]}")
        return {"code": -1, "msg": f"店铺{shop_abbr} JIT库存管理任务失败：{str(e)[:200]}", "data": {}, "remarks": str(e)[:500]}




def apply_activity_wrapper(
        uid,
        spu_id_list: list = None,
        searchScrollContext: str = None,
        activityType_list: list[dict] = None,
        detailed_activity_list: list[dict] = None,
        open_log_false: bool = False,
        not_skc_list: list = None,
        login_type: str = "auto",
        reload_cookies: bool = False,
        headless: bool = True,
        main_task_id: str = None,
        auto_close: bool = True,
        window_size: tuple[int, int] = (1920, 1080)
):
    login_result = temu_login_warpper(uid, login_type=login_type, reload_cookies=reload_cookies, headless=headless,
                                      auto_close=auto_close, window_size=window_size)
    if login_result["code"] != 1:
        return {"code": -1, "msg": f"{login_result['msg']}", "remarks": login_result["remarks"], "data": {}}

    shop_info = login_result["data"]
    shop_abbr = shop_info.get("shop_abbr", "未知店铺")
    mall_id = shop_info.get("mall_id")

    # 如果传入了详细活动信息列表，直接使用；否则使用activityType_list
    converter_activityType_list = []
    if detailed_activity_list:
        # 详细筛选模式（多选）
        converter_activityType_list = detailed_activity_list
    elif activityType_list:
        # 快速选择模式
        converter_activityType_list = filter_activityType_list(uid, shop_info["headers"], shop_info["cookies"], activityType_list)

    try:
        result = final_apply_activity(
            uid=uid,
            headers=shop_info["headers"],
            cookies=shop_info["cookies"],
            shop_abbr=shop_abbr,
            activityType_list=converter_activityType_list,
            spu_id_list=spu_id_list,
            searchScrollContext=searchScrollContext,
            mall_id=mall_id,
            open_log_false=open_log_false,
            not_skc_list=not_skc_list,
            main_task_id=main_task_id
        )

        return result

    except Exception as e:
        logger.error(f"❌ 店铺{shop_abbr} 报活动任务失败：{str(e)[:200]}")
        return {"code": -1, "msg": f"报活动任务失败：{str(e)[:200]}", "data": {}, "remarks": str(e)[:500]}


def expected_goods_place_task_wrapper(
        uid,
        skc_id_list: list = None,
        cat_id_list: list = None,
        exceptReceiveAreaConfigType: int | str | None = None,
        login_type: str = "auto",
        reload_cookies: bool = False,
        headless: bool = True,
        main_task_id: str = None,
        auto_close: bool = True,
        window_size: tuple[int, int] = (1920, 1080)
):
    login_result = temu_login_warpper(uid, login_type=login_type, reload_cookies=reload_cookies, headless=headless,
                                      auto_close=auto_close, window_size=window_size)
    if login_result["code"] != 1:
        return {"code": -1, "msg": f"{login_result['msg']}", "remarks": login_result["remarks"], "data": {}}

    shop_info = login_result["data"]
    shop_abbr = shop_info.get("shop_abbr", "未知店铺")

    skc_values = []
    if isinstance(skc_id_list, list):
        skc_values = [int(item) for item in skc_id_list if str(item).isdigit()]

    cat_values = []
    if isinstance(cat_id_list, list):
        if cat_id_list and isinstance(cat_id_list[0], dict):
            cat_values = cat_id_list
        else:
            cat_values = [int(item) for item in cat_id_list if str(item).isdigit()]

    except_receive_value = None
    if exceptReceiveAreaConfigType is not None:
        if isinstance(exceptReceiveAreaConfigType, str) and exceptReceiveAreaConfigType.isdigit():
            except_receive_value = int(exceptReceiveAreaConfigType)
        elif isinstance(exceptReceiveAreaConfigType, int):
            except_receive_value = exceptReceiveAreaConfigType

    if not except_receive_value:
        return {"code": -1, "msg": "期望到货地点为必选项", "data": {}, "remarks": "exceptReceiveAreaConfigType不能为空"}

    try:
        result = final_modify_expected_goods_place(
            uid=uid,
            headers=shop_info["headers"],
            cookies=shop_info["cookies"],
            skc_id_list=skc_values,
            cat_id_list=cat_values,
            exceptReceiveAreaConfigType=except_receive_value,
            shop_abbr=shop_abbr,
            main_task_id=main_task_id
        )
        return result
    except Exception as e:
        logger.error(f"❌ 店铺{shop_abbr} 批量修改期望到货地点失败：{str(e)[:200]}")
        return {"code": -1, "msg": f"批量修改期望到货地点失败：{str(e)[:200]}", "data": {}, "remarks": str(e)[:500]}




def download_export_excel_wrapper(
        uid,
        months_list: list = None,
        login_type: str = "auto",
        reload_cookies: bool = False,
        headless: bool = True,
        main_task_id: str = None,
        auto_close: bool = True,
        window_size: tuple[int, int] = (1920, 1080)
):
    """
    下载导出账单（新版：使用 API 方式，支持自动重试和文件完整性校验）
    
    Args:
        uid: 店铺 ID
        months_list: 需要下载的月份列表，如 ["2025.01", "2025.04"]
        login_type: 登录类型（保留参数，暂不使用）
        reload_cookies: 是否重新获取 cookies（保留参数，暂不使用）
        headless: 是否无头模式（保留参数，暂不使用）
        main_task_id: 主任务 ID（保留参数，暂不使用）
        auto_close: 是否自动关闭（保留参数，暂不使用）
        window_size: 窗口大小（保留参数，暂不使用）
    
    Returns:
        dict: {"code": 状态码，"msg": 消息，"data": 数据，"remarks": 备注}
    """
    # 使用新版下载函数（API 方式，更稳定可靠）
    try:
        login_result = temu_login_warpper(uid, login_type=login_type, reload_cookies=reload_cookies, headless=headless,
                                          auto_close=auto_close, window_size=window_size, fetch_all_region_cookies=True)
        if login_result["code"] != 1:
            return {"code": -1, "msg": f"{login_result['msg']}", "remarks": login_result["remarks"], "data": {}}

        shop_info = login_result["data"]
        shop_abbr = shop_info.get("shop_abbr", "未知店铺")

        logger.info(f"🚀 开始下载财务报表：店铺{shop_abbr}，月份{months_list}")
        
        # 调用新版完整下载函数（默认重试 5 次，确保所有文件下载完成）
        success = download_all_caiwu_excel_complete(uid, months_list, max_retries=5, check_type="all")
        
        if success:
            logger.success(f"✅ 店铺{shop_abbr} 财务报表下载成功")
            return {
                "code": 1,
                "msg": "财务报表下载成功",
                "data": {"downloaded_months": months_list},
                "remarks": "所有文件已下载并校验通过"
            }
        else:
            logger.error(f"❌ 店铺{shop_abbr} 财务报表下载失败")
            return {
                "code": -1,
                "msg": "财务报表下载失败（重试 5 次后仍有文件缺失）",
                "data": {},
                "remarks": "请检查网络连接或 TEMU 账号状态"
            }
            
    except Exception as e:
        logger.error(f"❌ 下载过程异常：{str(e)[:200]}")
        return {
            "code": -1,
            "msg": f"下载异常：{str(e)[:200]}",
            "data": {},
            "remarks": str(e)[:500]
        }




def merge_all_months_excel_wrapper(
        uid,
        months_list: list = None,
        login_type: str = "auto",
        reload_cookies: bool = False,
        main_task_id: str = None,
        headless: bool = True,
        auto_close: bool = True,
        window_size: tuple[int, int] = (1920, 1080)
):
    login_result = temu_login_warpper(uid, login_type=login_type, reload_cookies=reload_cookies, headless=headless,
                                 auto_close=auto_close, window_size=window_size)
    if login_result["code"] != 1:
        return {"code": -1, "msg": f"{login_result['msg']}", "remarks": login_result["remarks"], "data": {}}

    shop_info = login_result["data"]
    shop_abbr = shop_info.get("shop_abbr", "未知店铺")

    try:
        result = merge_all_months_excel(uid, months_list, shop_info)
        
        # 如果result没有统一格式，确保返回正确的消息
        if not isinstance(result, dict) or "msg" not in result:
            result = {"code": 1, "msg": "融合所选月份账单成功", "data": {}, "remarks": ""}
            
        return result
    except Exception as e:
        logger.error(f"❌ 店铺{shop_abbr} 融合所选月份账单失败：{str(e)[:200]}")
        return {"code": -1, "msg": f"融合所选月份账单失败：{str(e)[:200]}", "data": {}, "remarks": str(e)[:500]}



def record_all_need_colum_to_excel_wrapper(
        uid,
        months_list: list = None,
        login_type: str = "auto",
        reload_cookies: bool = False,
        main_task_id: str = None,
        headless: bool = True,
        auto_close: bool = True,
        window_size: tuple[int, int] = (1920, 1080)
):
    login_result = temu_login_warpper(uid, login_type=login_type, reload_cookies=reload_cookies, headless=headless,
                                 auto_close=auto_close, window_size=window_size)
    if login_result["code"] != 1:
        return {"code": -1, "msg": f"{login_result['msg']}", "remarks": login_result["remarks"], "data": {}}

    shop_info = login_result["data"]
    shop_abbr = shop_info.get("shop_abbr", "未知店铺")

    try:
        # 记录到总表
        record_all_need_colum_to_excel(uid, months_list)

        # 记录到履约售后表
        record_skc_to_table(uid, months_list)

        return {"code": 1, "msg": "记录所需数据导表格成功", "data": {}, "remarks": ""}

    except Exception as e:
        logger.error(f"❌ 店铺{shop_abbr} 记录所需数据导表格失败：{str(e)[:200]}")
        return {"code": -1, "msg": f"记录所需数据导表格失败：{str(e)[:200]}", "data": {}, "remarks": str(e)[:500]}



# 财务报表生成 wrapper
def make_caiwu_excel_wrapper(
        uid,
        months_list: list = None,
        login_type: str = "auto",
        main_task_id: str = None,
        reload_cookies: bool = False,
        headless: bool = True,
        auto_close: bool = True,
        window_size: tuple[int, int] = (1920, 1080)
):
    login_result = temu_login_warpper(uid, login_type=login_type, reload_cookies=reload_cookies, headless=headless,
                                 auto_close=auto_close, window_size=window_size)
    if login_result["code"] != 1:
        return {"code": -1, "msg": f"{login_result['msg']}", "remarks": login_result["remarks"], "data": {}}

    shop_info = login_result["data"]
    shop_abbr = shop_info.get("shop_abbr", "未知店铺")

    try:
        # 生成财务报表
        make_caiwu_excel(shop_info, months_list)

        return {"code": 1, "msg": "财务报表生成成功", "data": {}, "remarks": ""}

    except Exception as e:
        logger.error(f"❌ 店铺{shop_abbr} 财务报表生成失败：{str(e)[:200]}")
        return {"code": -1, "msg": f"财务报表生成失败：{str(e)[:200]}", "data": {}, "remarks": str(e)[:500]}


def batch_join_delivery_wrapper(
        uid,
        max_cycles: int = 5,
        batch_size: int = 100,
        urgency_type: int = 1,
        skip_upload_pic: bool = False,
        custom_fixed_upload_img: bool = False,
        login_type: str = "auto",
        reload_cookies: bool = False,
        headless: bool = True,
        main_task_id=None,
        auto_close: bool = True,
        window_size: tuple[int, int] = (1920, 1080)
):
    login_result = temu_login_warpper(uid, login_type=login_type, reload_cookies=reload_cookies, headless=headless,
                                 auto_close=auto_close, window_size=window_size)
    if login_result["code"] != 1:
        return {"code": -1, "msg": f"{login_result['msg']}", "remarks": login_result["remarks"], "data": {}}

    shop_info = login_result["data"]
    shop_abbr = shop_info.get("shop_abbr", "未知店铺")
    mall_id = shop_info.get("mall_id", 0)

    try:
        from temu_modules.temu_function.purchase_delivery import batch_join_delivery_with_retry
        result = batch_join_delivery_with_retry(
            shop_abbr=shop_abbr,
            headers=shop_info["headers"],
            cookies=shop_info["cookies"],
            uid=uid,
            max_cycles=max_cycles,
            batch_size=batch_size,
            urgency_type=urgency_type,
            skip_upload_pic=skip_upload_pic,
            custom_fixed_upload_img=custom_fixed_upload_img,
            mall_id=mall_id,
            main_task_id=main_task_id,
        )
        return result
    except Exception as e:
        logger.error(f"❌ 店铺{shop_abbr} 批量加入发货台失败：{str(e)[:200]}")
        return {"code": -1, "msg": f"批量加入发货台失败：{str(e)[:200]}", "data": {}, "remarks": str(e)[:500]}


# SKU汇总表生成 wrapper
def sku_summary_wrapper(
        uid,
        shop_abbr: str = None,
        months_list: list = None,
        login_type: str = "auto",
        main_task_id: str = None,
        reload_cookies: bool = False,
        headless: bool = True,
        auto_close: bool = True,
        window_size: tuple[int, int] = (1920, 1080)
):
    login_result = temu_login_warpper(uid, login_type=login_type, reload_cookies=reload_cookies, headless=headless,
                                 auto_close=auto_close, window_size=window_size)
    if login_result["code"] != 1:
        return {"code": -1, "msg": f"{login_result['msg']}", "remarks": login_result["remarks"], "data": {}}

    shop_info = login_result["data"]
    if shop_abbr is None:
        shop_abbr = shop_info.get("shop_abbr", "未知店铺")

    try:
        result_path = generate_sku_summary(shop_abbr, months_list)

        if result_path:
            return {"code": 1, "msg": "SKU汇总表生成成功", "data": {"file_path": result_path}, "remarks": ""}
        else:
            return {"code": -1, "msg": "SKU汇总表生成失败", "data": {}, "remarks": "未找到月份SKU表"}

    except Exception as e:
        logger.error(f"❌ 店铺{shop_abbr} SKU汇总表生成失败：{str(e)[:200]}")
        return {"code": -1, "msg": f"SKU汇总表生成失败：{str(e)[:200]}", "data": {}, "remarks": str(e)[:500]}



def all_make_caiwu_excel_wrapper(
        uid,
        months_list: list = None,
        login_type: str = "auto",
        main_task_id: str = None,
        reload_cookies: bool = False,
        headless: bool = True,
        auto_close: bool = True,
        window_size: tuple[int, int] = (1920, 1080)
):
    login_result = temu_login_warpper(uid, login_type=login_type, reload_cookies=reload_cookies, headless=headless,
                                 auto_close=auto_close, window_size=window_size, fetch_all_region_cookies=True)
    if login_result["code"] != 1:
        return {"code": -1, "msg": f"{login_result['msg']}", "remarks": login_result["remarks"], "data": {}}

    shop_info = login_result["data"]
    shop_abbr = shop_info.get("shop_abbr", "未知店铺")

    try:
        # ========== 任务 1：导出所选报表（使用新版 API 方式，内置 5 次重试）==========
        logger.info(f"🚀 开始下载财务报表")
        shop_info = get_shop_info_db(uid)
        if not shop_info:
            return {"code": -1, "msg": f"店铺{uid}信息获取失败", "data": {}, "remarks": "数据库查询失败"}
            
        success = download_all_caiwu_excel_complete(uid, months_list, max_retries=5, check_type="all")
        if not success:
            return {"code": -1, "msg": "财务报表下载失败（重试 5 次后仍有文件缺失）", "data": {}, "remarks": "请检查网络连接或 TEMU 账号状态"}
        logger.success(f"✅ 财务报表下载成功")

        # ========== 任务2：融合所选报表==========
        tries = 0
        while tries < 3:
            try:
                merge_all_months_excel(uid, months_list, shop_info)
                break
            except Exception as e:
                tries += 1
                if tries >= 3:
                    logger.error(f"❌ 店铺{shop_abbr} 融合报表失败（3次重试均异常）：{str(e)[:200]}")
                    return {"code": -1, "msg": f"融合报表失败（3次重试均异常）", "data": {}, "remarks": str(e)[:500]}
                logger.warning(f"⚠️ 店铺{shop_abbr} 融合报表异常，第{tries}次重试，错误：{str(e)[:200]}")
                time.sleep(2)

        # ========== 任务3：记录到总表 ==========
        tries = 0
        while tries < 3:
            try:
                record_all_need_colum_to_excel(uid, months_list)
                break
            except Exception as e:
                tries += 1
                if tries >= 3:
                    logger.error(f"❌ 店铺{shop_abbr} 记录到总表失败（3次重试均异常）：{str(e)[:200]}")
                    return {"code": -1, "msg": f"记录到总表失败（3次重试均异常）", "data": {}, "remarks": str(e)[:500]}
                logger.warning(f"⚠️ 店铺{shop_abbr} 记录到总表异常，第{tries}次重试，错误：{str(e)[:200]}")
                time.sleep(2)

        # ========== 任务4：记录到履约售后表 ==========
        tries = 0
        while tries < 3:
            try:
                record_skc_to_table(uid, months_list)
                break
            except Exception as e:
                tries += 1
                if tries >= 3:
                    logger.error(f"❌ 店铺{shop_abbr} 记录到履约售后表失败（3次重试均异常）：{str(e)[:200]}")
                    return {"code": -1, "msg": f"记录到履约售后表失败（3次重试均异常）", "data": {}, "remarks": str(e)[:500]}
                logger.warning(f"⚠️ 店铺{shop_abbr} 记录到履约售后表异常，第{tries}次重试，错误：{str(e)[:200]}")
                time.sleep(2)

        # ========== 任务5：生成财务报表 ==========
        tries = 0
        while tries < 3:
            try:
                make_caiwu_excel(shop_info, months_list)
                break
            except Exception as e:
                tries += 1
                if tries >= 3:
                    logger.error(f"❌ 店铺{shop_abbr} 生成财务报表失败（3次重试均异常）：{str(e)[:200]}")
                    return {"code": -1, "msg": f"生成财务报表失败（3次重试均异常）", "data": {}, "remarks": str(e)[:500]}
                logger.warning(f"⚠️ 店铺{shop_abbr} 生成财务报表异常，第{tries}次重试，错误：{str(e)[:200]}")
                time.sleep(2)

        generate_sku_summary(shop_abbr, months_list)


        return {"code": 1, "msg": "财务报表生成成功", "data": {}, "remarks": ""}

    except Exception as e:
        logger.error(f"❌ 店铺{shop_abbr} 财务报表生成失败：{str(e)[:200]}")
        return {"code": -1, "msg": f"财务报表生成失败：{str(e)[:200]}", "data": {}, "remarks": str(e)[:500]}

