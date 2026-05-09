# api/task_routes.py
import os
import platform
import shutil
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs, unquote

from fastapi import APIRouter

from config.common_config import config_manager, encryptor
from config.task_permission_config import get_required_permission, check_task_permission
from config.start_config import MAIN_TASK_MANAGER
from temu_modules.temu_func_wrapper import upload_real_pic_task_wrapper, modify_price_task_wrapper, \
    adjust_price_manage_task_wrapper, download_export_excel_wrapper, merge_all_months_excel_wrapper, \
    record_all_need_colum_to_excel_wrapper, make_caiwu_excel_wrapper, all_make_caiwu_excel_wrapper, jit_govern_wrapper, \
    apply_activity_wrapper, expected_goods_place_task_wrapper, temu_login_warpper, sku_summary_wrapper, \
    batch_join_delivery_wrapper
from spider_modules.hupu_func_wrapper import hupu_post_list_wrapper, hupu_detail_list_wrapper, hupu_score_list_wrapper
from spider_modules.hupu_spiders.hupu_spider_tool import get_post_title, get_score_title
from utils.TemuBase import get_shop_info_db
from utils.multiThreading_log_manager import generate_unique_task_id, TaskStatus, TOTAL_LOG_FILE, get_task_log_manager

# 创建路由实例
router = APIRouter()

# -------------------------- 任务相关接口 --------------------------
from fastapi import Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
# 请确保导入你的验证依赖和数据库实例
from api.server_routes.auth import verify_token
from config.middleware_config import db

STATUS_MAPPING = {
    "pending": "待处理",
    "running": "进行中",
    "success": "已完成",
    "failed": "异常",
    "timeout": "已超时",
    "stopped": "已退出",
    "captcha": "验证码",
    "验证码": "验证码"  # 兼容前端直接传递中文
}

# 任务类型映射：前端传入的task_type -> 数据库中的task_name
TASK_TYPE_MAPPING = {
    "upload_real_pic": "上传实拍图",
    "modify_price": "核价",
    "jit_govern": "JIT维护库存",
    "adjust_price": "调价管理",
    "apply_activity": "报活动任务",
    "expected_goods_place": "批量修改期望到货地点",
    "financial_full": "自动生成财务报表",
    "financial_export": "导出所选月份账单",
    "financial_merge": "融合所选月份账单",
    "financial_record": "记录所需列到总表",
    "financial_calculate": "计算并生成财务报表",
    "sku_summary": "生成SKU汇总表",
    "hupu_post_list": "虎扑帖子列表",
    "hupu_detail_list": "虎扑帖子详情",
    "hupu_score_list": "虎扑评分",
    "purchase_delivery": "批量加入发货台"
}


@router.post("/api/submit_temu_task", dependencies=[Depends(verify_token)])
async def submit_temu_task_api(request: Request):
    """接收前端提交的任务参数"""
    try:
        task_data = await request.json()

        selected_shop_uids = task_data.get("selected_shop_uids", []) # 选择店铺，下拉方式选择
        task_type = task_data.get("task_type") # 任务类型 1,2,3,4 || 1:上传实拍图任务 2:核价
        input_task_kwargs = task_data.get("task_kwargs") or {} # 任务参数 每个请求发送不同的任务类型配合不同参数，详细参数见下方详情task_kwargs
        is_maintain_task = task_data.get("is_maintain_task", 0)

        if not selected_shop_uids or selected_shop_uids == []:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "未选择店铺"}
            )

        if not task_type:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "未选择任务类型"}
            )

        # 权限检查
        # 使用统一的权限管理器检查权限
        from config.permission_manager import permission_manager
        if not permission_manager.check_permission(task_type):
            return JSONResponse(
                status_code=403,
                content={"success": False, "error_msg": f"您没有执行此任务的权限"}
            )

        # 通过task_type获取任务名称 及其函数名

        if task_type == "upload_real_pic":
            task_name = "上传实拍图"
            task_function = upload_real_pic_task_wrapper

        elif task_type == "modify_price":
            task_name = "核价"
            task_function = modify_price_task_wrapper

        elif task_type == "jit_govern":
            task_name = "JIT维护库存"
            task_function = jit_govern_wrapper

        elif task_type == "adjust_price":
            task_name = "调价管理"
            task_function = adjust_price_manage_task_wrapper

        elif task_type == "apply_activity":
            task_name = "报活动任务"
            task_function = apply_activity_wrapper

        elif task_type == "expected_goods_place":
            task_name = "批量修改期望到货地点"
            task_function = expected_goods_place_task_wrapper

        elif task_type == "financial_export":
            task_name = "导出所选月份账单"
            task_function = download_export_excel_wrapper

        elif task_type == "financial_merge":
            task_name = "融合所选月份账单"
            task_function = merge_all_months_excel_wrapper

        elif task_type == "financial_record":
            task_name = "记录所需列到总表"
            task_function = record_all_need_colum_to_excel_wrapper

        elif task_type == "financial_calculate":
            task_name = "计算并生成财务报表"
            task_function = make_caiwu_excel_wrapper

        elif task_type == "financial_full":
            task_name = "自动生成财务报表"
            task_function = all_make_caiwu_excel_wrapper

        elif task_type == "sku_summary":
            task_name = "生成SKU汇总表"
            task_function = sku_summary_wrapper

        elif task_type == "purchase_delivery":
            task_name = "批量加入发货台"
            task_function = batch_join_delivery_wrapper

        else:
            return {
                "success": False,
                "error_msg": "任务类型错误"
            }

        success_num = 0

        for uid in selected_shop_uids:
            shop_info = get_shop_info_db(uid)
            
            # 生成包含店铺信息的任务名称
            shop_name = shop_info.get('shop_name', shop_info.get('shop_abbr', ''))
            if task_type == "upload_real_pic":
                task_name_with_shop = f"上传实拍图-{shop_name}"
            elif task_type == "modify_price":
                task_name_with_shop = f"核价-{shop_name}"
            elif task_type == "jit_govern":
                task_name_with_shop = f"JIT维护库存-{shop_name}"
            elif task_type == "adjust_price":
                task_name_with_shop = f"调价管理-{shop_name}"
            elif task_type == "apply_activity":
                task_name_with_shop = f"报活动任务-{shop_name}"
            elif task_type == "expected_goods_place":
                task_name_with_shop = f"批量修改期望到货地点-{shop_name}"
            elif task_type == "financial_export":
                task_name_with_shop = f"导出所选月份账单-{shop_name}"
            elif task_type == "financial_merge":
                task_name_with_shop = f"融合所选月份账单-{shop_name}"
            elif task_type == "financial_record":
                task_name_with_shop = f"记录所需列到总表-{shop_name}"
            elif task_type == "financial_calculate":
                task_name_with_shop = f"计算并生成财务报表-{shop_name}"
            elif task_type == "financial_full":
                task_name_with_shop = f"自动生成财务报表-{shop_name}"
            elif task_type == "sku_summary":
                task_name_with_shop = f"生成SKU汇总表-{shop_name}"
            elif task_type == "purchase_delivery":
                task_name_with_shop = f"批量加入发货台-{shop_name}"
            else:
                task_name_with_shop = task_name

            task_group = f"{shop_info['shop_abbr']}_{task_name}"

            input_task_kwargs.update({"uid": uid})

            task_kwargs = input_task_kwargs

            parent_task_id = None

            main_task_id = generate_unique_task_id(task_function, task_kwargs, shop_info["mall_id"] or 0, task_name or "", parent_task_id or "")
            task_kwargs.update({"main_task_id": main_task_id})

            # print("任务参数：", task_kwargs)
            task_id = get_task_log_manager().add_task(
                target_func=task_function, **task_kwargs,
                task_id=main_task_id,
                task_group=task_group,
                mall_id=shop_info["mall_id"],
                task_name=task_name_with_shop,
                # parent_task_id=main_task_id, # 子线程传入
                is_main_task=1,
            )

            if task_id:
                success_num += 1

            if is_maintain_task:
                db.execute_sql(
                    "UPDATE task SET is_maintain_task = ?, update_time = datetime('now', '+8 hours') WHERE task_id = ?",
                    params=[1, task_id],
                    fetch="none"
                )

        return {
            "success": True,
            "message": f"任务提交成功，本次成功提交{success_num}/{len(selected_shop_uids)}个店铺",
        }

    except Exception as e:
        logger.error(f"任务提交失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"提交失败：{str(e)}"}
        )


@router.post("/api/submit_spider_task", dependencies=[Depends(verify_token)])
async def submit_spider_task_api(request: Request):
    """接收前端提交的爬虫任务参数"""
    try:
        task_data = await request.json()

        task_type = task_data.get("task_type") # 爬虫任务类型
        task_kwargs = task_data.get("task_kwargs", {}) # 爬虫任务参数
        is_maintain_task = task_data.get("is_maintain_task", 0)
        task_name = task_data.get("task_name", "") # 任务名称
        
        # 定时任务相关参数
        schedule_type = task_data.get("schedule_type", "")  # 定时类型：'once' 或 'interval'
        schedule_time = task_data.get("schedule_time", "")  # 定时执行时间，格式 'HH:MM'
        schedule_interval = task_data.get("schedule_interval", 0)  # 执行间隔时间（分钟）
        schedule_enabled = task_data.get("schedule_enabled", False)  # 是否启用定时

        if not task_type:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "未选择任务类型"}
            )

        # 权限检查
        from config.permission_manager import permission_manager
        if not permission_manager.check_permission(task_type):
            return JSONResponse(
                status_code=403,
                content={"success": False, "error_msg": f"您没有执行此任务的权限"}
            )

        # 通过task_type获取任务名称及其函数名
        if task_type == "hupu_post_list":
            task_group = "虎扑帖子列表采集"
            task_function = hupu_post_list_wrapper

        elif task_type == "hupu_detail_list":
            task_group = "虎扑帖子详情采集"
            task_function = hupu_detail_list_wrapper

        elif task_type == "hupu_score_list":
            task_group = "虎扑评分采集"
            task_function = hupu_score_list_wrapper

        else:
            return {
                "success": False,
                "error_msg": "爬虫任务类型错误"
            }

        # 如果前端没有传task_name，使用task_group作为默认值
        if not task_name:
            task_name = task_group

        # 爬虫任务不需要店铺UID，直接创建任务
        task_group = task_group
        
        # 确保task_kwargs是字典类型
        if not isinstance(task_kwargs, dict):
            task_kwargs = {}

        parent_task_id = None
        main_task_id = generate_unique_task_id(task_function, task_kwargs, 0, task_name or "", parent_task_id or "")
        task_kwargs.update({"main_task_id": main_task_id})

        task_id = get_task_log_manager().add_task(
            target_func=task_function, 
            **task_kwargs,
            task_id=main_task_id,
            task_group=task_group,
            mall_id=0,  # 爬虫任务没有mall_id
            task_name=task_name,
            is_main_task=1,
        )

        if task_id:
            success_num = 1
        else:
            success_num = 0

        if is_maintain_task and task_id:
            db.execute_sql(
                "UPDATE task SET is_maintain_task = ?, update_time = datetime('now', '+8 hours') WHERE task_id = ?",
                params=[1, task_id],
                fetch="none"
            )

        # 添加定时任务
        if task_id and schedule_enabled and schedule_type:
            try:
                from utils.scheduled_task_manager import ScheduledTaskManager
                schedule_manager = ScheduledTaskManager(db)
                
                success = schedule_manager.add_scheduled_task(
                    task_id=task_id,
                    schedule_type=schedule_type,
                    schedule_time=schedule_time if schedule_type == 'once' else None,
                    schedule_interval=schedule_interval if schedule_type == 'interval' else None,
                    schedule_enabled=True,
                    execute_immediately=False  # 不立即执行，等待定时触发
                )
                
                if success:
                    logger.info(f"✅ 定时任务添加成功 | task_id: {task_id} | schedule_type: {schedule_type}")
                else:
                    logger.error(f"❌ 定时任务添加失败 | task_id: {task_id}")
            except Exception as e:
                logger.error(f"❌ 定时任务创建异常 | task_id: {task_id} | 错误: {e}", exc_info=True)

        return {
            "success": True,
            "message": f"{task_name}提交成功，本次成功提交{success_num}个任务",
            "task_id": task_id
        }

    except Exception as e:
        logger.error(f"爬虫任务提交失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"提交失败：{str(e)}"}
        )

# -------------------------- 类目搜索接口 --------------------------
@router.post("/api/search_category", dependencies=[Depends(verify_token)])
async def search_category_api(request: Request):
    """搜索商品类目 - 启动登录任务（兼容旧接口）"""
    return await _start_category_search_login(request, "keyword")


@router.post("/api/search_category_by_goods_sn", dependencies=[Depends(verify_token)])
async def search_category_by_goods_sn_api(request: Request):
    """通过货号搜索类目 - 启动登录任务（兼容旧接口）"""
    return await _start_category_search_login(request, "goods_sn")


async def _start_category_search_login(request: Request, search_type: str):
    """
    统一的类目搜索登录启动函数
    search_type: "keyword" 或 "goods_sn"
    """
    try:
        data = await request.json()
        uid = data.get("uid")
        
        if not uid:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "uid不能为空"}
            )

        task_kwargs = {"uid": uid, "login_type": "ikun", "reload_cookies": False, "headless": True, "auto_close": True}
        login_task_success = MAIN_TASK_MANAGER.add_task(
            task_id=f"category_search_login_{uid}",
            target_func=temu_login_warpper, **task_kwargs,
            task_group="ikun",
            allow_duplicate=False
        )

        return JSONResponse(
            status_code=200,
            content={"success": True, "task_id": f"category_search_login_{uid}", "msg": "登录中...（如果长时间卡住，请在店铺管理手动连接店铺）"}
        )
            
    except Exception as e:
        logger.error(f"类目搜索登录启动失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"启动失败：{str(e)}"}
        )

# -------------------------- 工具函数 --------------------------
def serialize_task_data(task_dict: dict) -> dict:
    """
    序列化任务数据（处理不可JSON序列化的类型，如datetime）
    """
    serialized = {}
    for key, value in task_dict.items():
        if isinstance(value, datetime):
            # 统一转为ISO格式字符串（兼容前端）
            serialized[key] = value.strftime("%Y-%m-%d %H:%M:%S")
        elif value is None:
            serialized[key] = ""  # 前端空值友好处理
        elif key == "task_kwargs" and isinstance(value, str):
            # task_kwargs字段是JSON字符串，需要解析
            try:
                serialized[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                serialized[key] = value  # 解析失败则保留原字符串
        else:
            serialized[key] = value
    return serialized


def safe_get_count(result: Any) -> int:
    """
    安全获取COUNT查询结果，兼容整数/元组/None/字典类型
    ✅ 核心修复：处理字典类型的返回值（如 {'COUNT(*)': 16}）
    """
    # logger.debug(f"COUNT查询原始结果：{result}，类型：{type(result)}")
    if result is None:
        return 0
    # 处理整数/浮点数
    elif isinstance(result, (int, float)):
        return int(result)
    # 处理元组/列表（如 (16,) 或 [16]）
    elif isinstance(result, (tuple, list)) and len(result) > 0:
        return int(result[0]) if result[0] else 0
    # 处理字典（核心修复：适配 {'COUNT(*)': 16} 格式）
    elif isinstance(result, dict):
        # 兼容 COUNT(*) / count(*) / Count(*) 等大小写变体
        count_key = next(iter(result.keys()), None)
        if count_key and result[count_key] is not None:
            return int(result[count_key])
        return 0
    # 兼容sqlite3.Row对象
    elif hasattr(result, 'keys'):
        return int(result[0]) if len(result) > 0 else 0
    else:
        return 0


# -------------------------- 获取搜索类目任务结果接口 --------------------------
@router.post("/api/get_search_category_result", dependencies=[Depends(verify_token)])
async def get_search_category_result_api(request: Request):
    """
    获取关键词搜索类目结果（轮询接口 - 兼容旧接口，实际调用通用接口）
    """
    body = await request.json()
    return await _get_category_search_result(body, "keyword")


@router.post("/api/get_goods_sn_category_result", dependencies=[Depends(verify_token)])
async def get_goods_sn_category_result_api(request: Request):
    """
    获取货号搜索类目结果（轮询接口 - 兼容旧接口，实际调用通用接口）
    """
    body = await request.json()
    return await _get_category_search_result(body, "goods_sn")


async def _get_category_search_result(body: dict, search_type: str):
    """
    统一的类目搜索结果获取函数
    search_type: "keyword" 或 "goods_sn"
    """
    try:
        task_id = body.get("task_id", "").strip()
        
        if not task_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "task_id不能为空"}
            )
        
        result = MAIN_TASK_MANAGER.get_task_result(task_id, timeout=120)
        
        if result["code"] == -2:
            return JSONResponse(
                status_code=200,
                content={"success": False, "error_msg": "任务等待超时", "status": "timeout"}
            )
        
        if result["code"] != 1:
            return JSONResponse(
                status_code=200,
                content={"success": False, "error_msg": result.get("msg", "登录失败"), "status": "failed"}
            )
        
        shop_info = result.get("data")
        if not shop_info:
            return JSONResponse(
                status_code=200,
                content={"success": False, "error_msg": "无法获取店铺信息", "status": "failed"}
            )
        
        uid = body.get("uid")
        
        if search_type == "keyword":
            keyword = body.get("keyword")
            from temu_modules.temu_function.expected_goods_place import search_goods_category
            search_result = search_goods_category(
                uid=uid,
                headers=shop_info["headers"],
                cookies=shop_info["cookies"],
                searchText=keyword
            )
            
            if search_result.get("code") == 1 and search_result.get("data"):
                logger.info(f"搜索类目成功 | uid: {uid} | keyword: {keyword} | 类目数量: {len(search_result['data'])}")
                return JSONResponse(
                    status_code=200,
                    content={"success": True, "data": search_result["data"], "status": "success", "msg": "查询成功！请点击下拉框选择结果！"}
                )
            else:
                logger.warning(f"搜索类目失败 | uid: {uid} | keyword: {keyword} | 错误: {search_result.get('msg', '未知错误')}")
                return JSONResponse(
                    status_code=200,
                    content={"success": False, "error_msg": search_result.get("msg", "搜索失败"), "status": "failed"}
                )
        else:  # goods_sn
            # 货号转为大写，实现不区分大小写搜索
            goods_sn = body.get("goods_sn", "").strip().upper()
            
            if not goods_sn:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error_msg": "goods_sn不能为空"}
                )
            
            from temu_modules.temu_function.general_interface import get_goods_list, extract_goods_list
            goods = get_goods_list(uid, shop_info["headers"], shop_info["cookies"], skcExtCodes=[goods_sn])
            search_result = extract_goods_list(goods)
            
            if not search_result or not search_result.get("data"):
                return JSONResponse(
                    status_code=200,
                    content={"success": False, "error_msg": f"未找到货号为 {goods_sn} 的商品", "status": "failed"}
                )
            
            first_item = search_result["data"][0]
            cat_ids = first_item.get("类目id", [])
            cat_names = first_item.get("类目名", [])
            
            if not cat_ids:
                return JSONResponse(
                    status_code=200,
                    content={"success": False, "error_msg": "未找到类目信息", "status": "failed"}
                )
            
            logger.info(f"货号搜索类目成功 | uid: {uid} | goods_sn: {goods_sn} | 类目: {cat_names}")
            return JSONResponse(
                status_code=200,
                content={"success": True, "data": {"cat_ids": cat_ids, "cat_names": cat_names},
                "message": f"匹配成功：{cat_names}", "status": "success"}
            )
            
    except Exception as e:
        logger.error(f"获取类目搜索结果失败：{str(e)}", exc_info=True)
        error_msg = str(e)
        uid = body.get("uid") if 'body' in locals() else None
        if uid and "403 Client Error" in error_msg:
            try:
                db.execute_sql(
                    "update shops set connect_status = ? where uid = ?",
                    params=("未连接", uid),
                    fetch="none"
                )
            except Exception as db_e:
                logger.error(f"更新店铺连接状态失败：{str(db_e)}")
            return JSONResponse(
                status_code=200,
                content={"success": False, "error_msg": "店铺登录已失效，请重新连接店铺", "status": "failed"}
            )
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"获取结果失败：{error_msg}", "status": "failed"}
        )


@router.post("/api/save_saved_category_list", dependencies=[Depends(verify_token)])
async def save_saved_category_list_api(request: Request):
    """
    保存已保存的类目列表（到config_manager，增量添加）
    """
    try:
        body = await request.json()
        category_list = body.get("category_list", [])

        if not isinstance(category_list, list):
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "类目列表必须是数组类型"}
            )

        # 获取已保存的类目列表
        existing_category_list = config_manager.get_or_set_config(
            "saved_category_list",
            [],
            value_type="list"
        )

        # 增量添加：合并新旧列表，避免重复
        merged_list = []
        seen_cat_ids = set()

        # 先添加已存在的类目
        for cat in existing_category_list:
            cat_ids = cat.get("cat_ids", [])
            if cat_ids:
                last_cat_id = cat_ids[-1] if cat_ids else None
                if last_cat_id and last_cat_id not in seen_cat_ids:
                    merged_list.append(cat)
                    seen_cat_ids.add(last_cat_id)

        # 再添加新的类目（避免重复）
        for cat in category_list:
            cat_ids = cat.get("cat_ids", [])
            if cat_ids:
                last_cat_id = cat_ids[-1] if cat_ids else None
                if last_cat_id and last_cat_id not in seen_cat_ids:
                    merged_list.append(cat)
                    seen_cat_ids.add(last_cat_id)

        # 保存合并后的列表
        config_manager.upsert_config("saved_category_list", merged_list)

        return JSONResponse(
            status_code=200,
            content={"success": True, "msg": "保存成功"}
        )
    except Exception as e:
        logger.error(f"保存已保存类目列表失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"保存失败：{str(e)}"}
        )


@router.post("/api/delete_saved_category", dependencies=[Depends(verify_token)])
async def delete_saved_category_api(request: Request):
    """
    删除已保存的类目（从config_manager）
    """
    try:
        body = await request.json()
        cat_id = body.get("cat_id")

        if not cat_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "类目ID不能为空"}
            )

        # 获取已保存的类目列表
        existing_category_list = config_manager.get_or_set_config(
            "saved_category_list",
            [],
            value_type="list"
        )

        # 删除指定的类目
        filtered_list = []
        for cat in existing_category_list:
            cat_ids = cat.get("cat_ids", [])
            if cat_ids:
                last_cat_id = cat_ids[-1] if cat_ids else None
                # 类型转换：确保比较时类型一致
                if str(last_cat_id) != str(cat_id):
                    filtered_list.append(cat)

        # 保存过滤后的列表
        config_manager.upsert_config("saved_category_list", filtered_list)

        return JSONResponse(
            status_code=200,
            content={"success": True, "msg": "删除成功"}
        )
    except Exception as e:
        logger.error(f"删除已保存类目失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"删除失败：{str(e)}"}
        )


@router.post("/api/save_search_category_results", dependencies=[Depends(verify_token)])
async def save_search_category_results_api(request: Request):
    """
    保存搜索类目结果（到config_manager）
    """
    try:
        body = await request.json()
        category_results = body.get("category_results", [])

        if not isinstance(category_results, list):
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "类目结果必须是数组类型"}
            )

        config_manager.upsert_config("saved_category_results", category_results)

        return JSONResponse(
            status_code=200,
            content={"success": True, "msg": "保存成功"}
        )
    except Exception as e:
        logger.error(f"保存搜索类目结果失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"保存失败：{str(e)}"}
        )


@router.post("/api/get_saved_category_list", dependencies=[Depends(verify_token)])
async def get_saved_category_list_api(request: Request):
    """
    获取已保存的类目列表（从config_manager获取）
    """
    try:
        category_list = config_manager.get_or_set_config(
            "saved_category_list",
            [],
            value_type="list"
        )

        return JSONResponse(
            status_code=200,
            content={"success": True, "data": category_list, "msg": "获取成功"}
        )
    except Exception as e:
        logger.error(f"获取已保存类目列表失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"获取失败：{str(e)}"}
        )


@router.post("/api/get_search_category_results", dependencies=[Depends(verify_token)])
async def get_search_category_results_api(request: Request):
    """
    获取搜索类目结果（从config_manager获取）
    """
    try:
        category_results = config_manager.get_or_set_config(
            "saved_category_results",
            [],
            value_type="list"
        )

        return JSONResponse(
            status_code=200,
            content={"success": True, "data": category_results, "msg": "获取成功"}
        )
    except Exception as e:
        logger.error(f"获取搜索类目结果失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"获取失败：{str(e)}"}
        )


# -------------------------- 接口定义 --------------------------
@router.post("/api/get_tasks", dependencies=[Depends(verify_token)])
async def get_tasks_api(request: Request):
    """
    获取任务列表（支持多条件复合筛选+分页）
    筛选条件：
    - task_status: 任务状态（pending/running/success/failed/timeout/stopped/captcha）【新增captcha验证码状态】
    - task_id: 任务ID（精确匹配，单值）
    - task_id_list: 任务ID列表（精确匹配，多值）
    - maintain_task: 是否查询固定守护任务列表（1=是，其他/不传=否，新增）
    - task_type: 任务类型（1=上传实拍图，2=核价）
    - shop_abbr: 店铺简称（模糊匹配）
    - is_main_task: 是否主任务（0/1）
    分页参数：
    - page: 页码（默认1）
    - page_size: 每页条数（默认20，最大100）
    """
    try:
        # 1. 解析请求体（添加默认值，避免KeyError，新增maintain_task解析）
        body = await request.json()
        task_status_en = body.get("task_status")
        task_id = body.get("task_id", "").strip()  # 保留原有单值task_id，提前去空
        task_id_list = body.get("task_id_list", [])  # 多值task_id_list，默认空列表
        is_maintain_task = body.get("is_maintain_task")
        task_type = body.get("task_type")
        auto_rerun_time = body.get("auto_rerun_time")
        shop_abbr = body.get("shop_abbr", "").strip()
        is_main_task = body.get("is_main_task")
        has_scheduled_task = body.get("has_scheduled_task")

        # 分页参数（容错处理：避免非数字值）
        try:
            page = max(int(body.get("page", 1)), 1)  # 页码≥1
            page_size = min(int(body.get("page_size", 20)), 100)  # 每页条数≤100
        except (ValueError, TypeError):
            page = 1
            page_size = 20
        offset = (page - 1) * page_size

        # 2. 构建动态SQL和参数列表（严格参数化）
        base_sql = """
                   SELECT id,
                          task_name,
                          task_id,
                          status,
                          msg,
                          remarks,
                          task_group,
                          func_name,
                          mall_id,
                          is_main_task,
                          is_maintain_task,
                          auto_rerun_time,
                          parent_task_id,
                          create_time,
                          update_time,
                          func_path,
                          ip,
                          task_kwargs
                   FROM task
                   WHERE 1 = 1
                   """
        count_sql = "SELECT COUNT(*) FROM task WHERE 1 = 1"
        params = []
        count_params = []

        # 2.1 任务状态筛选（英文转中文，【新增captcha验证码状态映射】）
        if task_status_en and task_status_en in STATUS_MAPPING:
            base_sql += " AND status = ?"
            count_sql += " AND status = ?"
            status_cn = STATUS_MAPPING[task_status_en]
            params.append(status_cn)
            count_params.append(status_cn)

        # 2.2 任务ID筛选优先级：maintain_task=1 → task_id（单值） → task_id_list（多值）
        if task_id:  # 原有单值查询，非空时生效
            base_sql += " AND task_id = ?"
            count_sql += " AND task_id = ?"
            params.append(task_id)
            count_params.append(task_id)
        elif isinstance(task_id_list, list) and len(task_id_list) > 0:  # 多值查询，仅当以上都为空时生效
            # 过滤列表中的无效值（空/非字符串），并去重
            valid_task_ids = [str(tid).strip() for tid in task_id_list if tid and str(tid).strip()]
            if valid_task_ids:
                placeholders = ", ".join(["?"] * len(valid_task_ids))
                base_sql += f" AND task_id IN ({placeholders})"
                count_sql += f" AND task_id IN ({placeholders})"
                params.extend(valid_task_ids)
                count_params.extend(valid_task_ids)

        # 2.3 任务类型筛选（使用 LIKE 包含匹配，支持 task_name 格式：任务名称-店铺名称）
        if task_type in TASK_TYPE_MAPPING:
            base_sql += " AND task_name LIKE ?"
            count_sql += " AND task_name LIKE ?"
            task_name = TASK_TYPE_MAPPING[task_type]
            # 使用包含匹配，如 "记录所需列到总表%" 匹配 "记录所需列到总表-RugVogue"
            like_param = f"{task_name}%"
            params.append(like_param)
            count_params.append(like_param)
        elif task_type is not None:
            logger.warning(f"无效的任务类型：{task_type}，已跳过该筛选条件")

        # 2.4 店铺简称筛选（匹配 task_group 前缀，格式：店铺缩写_任务名称）
        if shop_abbr:
            base_sql += " AND task_group LIKE ?"
            count_sql += " AND task_group LIKE ?"
            # 匹配前缀，如 AE_ 匹配 AE_自动生成财务报表
            like_param = f"{shop_abbr}_%"
            params.append(like_param)
            count_params.append(like_param)

        # 2.5 是否主任务筛选（仅0/1有效，兼容字符串/数字）
        if is_main_task in (0, 1, "0", "1"):
            base_sql += " AND is_main_task = ?"
            count_sql += " AND is_main_task = ?"
            # 统一转为整数
            is_main_task_int = int(is_main_task)
            params.append(is_main_task_int)
            count_params.append(is_main_task_int)

        # 2.6 守护任务筛选
        if is_maintain_task in (1, "1"):
            base_sql += " AND is_maintain_task = ?"
            count_sql += " AND is_maintain_task = ?"
            # 统一转为整数
            is_maintain_task_int = int(is_maintain_task)
            params.append(is_maintain_task_int)
            count_params.append(is_maintain_task_int)

        # 2.7 定时任务筛选
        if has_scheduled_task in (0, 1, "0", "1"):
            has_scheduled_task_int = int(has_scheduled_task)
            if has_scheduled_task_int == 1:
                # 筛选已设置定时任务的任务
                base_sql += " AND task_id IN (SELECT task_id FROM scheduled_tasks WHERE schedule_enabled = 1)"
                count_sql += " AND task_id IN (SELECT task_id FROM scheduled_tasks WHERE schedule_enabled = 1)"
            else:
                # 筛选未设置定时任务的任务
                base_sql += " AND task_id NOT IN (SELECT task_id FROM scheduled_tasks WHERE schedule_enabled = 1)"
                count_sql += " AND task_id NOT IN (SELECT task_id FROM scheduled_tasks WHERE schedule_enabled = 1)"

        # 2.8 添加排序和分页（核心优化：避免返回全量数据）
        base_sql += " ORDER BY update_time DESC LIMIT ? OFFSET ?"
        params.extend([page_size, offset])

        # 3. 执行SQL查询（先查总数，再查分页数据）
        count_result = db.execute_sql(
            count_sql,
            params=count_params,
            fetch="fetch_one"
        )
        total_count = safe_get_count(count_result)

        all_task_id_list = db.execute_sql(
            "SELECT task_id FROM task",
            fetch="fetch"
        ) or []

        # 3.2 查分页数据（兜底空列表）
        result_list = db.execute_sql(
            base_sql,
            params=params,
            fetch="fetch"
        ) or []

        # -------------------------- 关键修改1：定义字符截断函数 --------------------------
        def truncate_long_text(text: str, max_length: int = 200) -> str:
            """
            长文本截断函数：超出最大长度则截断并补省略号，空值/非字符串返回空
            :param text: 原始文本
            :param max_length: 最大显示长度，默认200
            :return: 截断后的文本
            """
            if not isinstance(text, str) or not text:
                return ""
            return text[:max_length] + "..." if len(text) > max_length else text

        # 4. 格式化并序列化结果（-------------------------- 关键修改2：调用截断函数 --------------------------）
        formatted_tasks = []
        for task in result_list:
            # 兼容sqlite3.Row和普通字典
            task_dict = dict(task) if hasattr(task, 'keys') else task
            # 序列化基础数据
            serialized_task = serialize_task_data(task_dict)
            # 对易过长的字段进行200字符截断（可根据实际需求添加/删除字段，如func_path、msg等）
            serialized_task['msg'] = truncate_long_text(serialized_task.get('msg', ''))
            serialized_task['remarks'] = truncate_long_text(serialized_task.get('remarks', ''))
            # 如需对其他字段截断，直接添加即可，示例：
            # serialized_task['func_path'] = truncate_long_text(serialized_task.get('func_path', ''))
            formatted_tasks.append(serialized_task)

        # 5. 返回响应（包含分页信息）
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "total": total_count,
                "page": page,
                "page_size": page_size,
                "count": len(formatted_tasks),
                "tasks": formatted_tasks,
                "all_task_id_list": all_task_id_list
            },
            headers={"Content-Type": "application/json; charset=utf-8"}
        )

    # 异常处理（分类更清晰）
    except json.JSONDecodeError as e:
        logger.error(f"请求体解析失败：{str(e)}")
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error_msg": "请求体格式错误，请传入合法的JSON数据",
                "error_detail": str(e)
            }
        )
    except HTTPException as e:
        # 透传认证相关的异常
        raise e
    except Exception as e:
        logger.error(f"获取任务列表失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error_msg": "获取任务列表失败",
                "error_detail": str(e) if "DEBUG" in __name__ else "服务器内部错误"
            }
        )




@router.post("/api/get_task_log", dependencies=[Depends(verify_token)])
async def get_task_log_api(request: Request):
    """获取任务日志"""
    try:
        body = await request.json()
        task_id = body.get("task_id", "").strip()

        if not task_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务ID不能为空"}
            )

        log_result = db.execute_sql(
            "SELECT log FROM task WHERE task_id = ?",
            params=[task_id],
            fetch="fetch_one"
        )

        # 安全处理日志结果
        log_content = log_result["log"] if (log_result and "log" in log_result) else ""

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "msg": "获取任务日志成功",
                "task_id": task_id,
                "log": log_content
            }
        )

    except Exception as e:
        logger.error(f"获取任务日志失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"获取任务日志失败：{str(e)}"}
        )


# -------------------------- 定时任务相关接口 --------------------------

from utils.scheduled_task_manager import ScheduledTaskManager

@router.post("/api/add_schedule_task", dependencies=[Depends(verify_token)])
async def add_schedule_task_api(request: Request):
    """添加定时任务"""
    try:
        task_data = await request.json()
        
        task_id = task_data.get("task_id")
        schedule_type = task_data.get("schedule_type")
        schedule_time = task_data.get("schedule_time")
        schedule_interval = task_data.get("schedule_interval")
        schedule_enabled = task_data.get("schedule_enabled", True)
        execute_immediately = task_data.get("execute_immediately", True)
        
        if not task_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务ID不能为空"}
            )
        
        if not schedule_type:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "定时类型不能为空"}
            )
        
        if schedule_type == "once" and not schedule_time:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "定时时间不能为空"}
            )
        
        if schedule_type == "interval" and not schedule_interval:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "执行间隔不能为空"}
            )
        
        # 创建定时任务管理器
        schedule_manager = ScheduledTaskManager(db)
        
        # 添加定时任务
        success = schedule_manager.add_scheduled_task(
            task_id=task_id,
            schedule_type=schedule_type,
            schedule_time=schedule_time,
            schedule_interval=schedule_interval,
            schedule_enabled=schedule_enabled,
            execute_immediately=execute_immediately
        )
        
        if success:
            return JSONResponse(
                status_code=200,
                content={"success": True, "msg": "定时任务添加成功"}
            )
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error_msg": "定时任务添加失败"}
            )
            
    except Exception as e:
        logger.error(f"添加定时任务失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"添加定时任务失败：{str(e)}"}
        )


@router.post("/api/update_schedule_task", dependencies=[Depends(verify_token)])
async def update_schedule_task_api(request: Request):
    """更新定时任务配置"""
    try:
        task_data = await request.json()
        
        schedule_id = task_data.get("schedule_id")
        schedule_type = task_data.get("schedule_type")
        schedule_time = task_data.get("schedule_time")
        schedule_interval = task_data.get("schedule_interval")
        schedule_enabled = task_data.get("schedule_enabled")
        execute_immediately = task_data.get("execute_immediately")
        
        if not schedule_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "定时任务ID不能为空"}
            )
        
        # 创建定时任务管理器
        schedule_manager = ScheduledTaskManager(db)
        
        # 更新定时任务
        success = schedule_manager.update_scheduled_task(
            schedule_id=schedule_id,
            schedule_type=schedule_type,
            schedule_time=schedule_time,
            schedule_interval=schedule_interval,
            schedule_enabled=schedule_enabled,
            execute_immediately=execute_immediately
        )
        
        if success:
            return JSONResponse(
                status_code=200,
                content={"success": True, "msg": "定时任务更新成功"}
            )
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error_msg": "定时任务更新失败"}
            )
            
    except Exception as e:
        logger.error(f"更新定时任务失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"更新定时任务失败：{str(e)}"}
        )


@router.post("/api/delete_schedule_task", dependencies=[Depends(verify_token)])
async def delete_schedule_task_api(request: Request):
    """删除定时任务"""
    try:
        task_data = await request.json()
        
        schedule_id = task_data.get("schedule_id")
        task_id = task_data.get("task_id")
        
        # 支持通过 task_id 删除定时任务
        if task_id and not schedule_id:
            # 通过 task_id 查找对应的 id
            schedule_record = db.execute_sql(
                "SELECT id FROM scheduled_tasks WHERE task_id = ? AND schedule_enabled = 1",
                params=[task_id],
                fetch="fetch_one"
            )
            if schedule_record:
                schedule_id = schedule_record.get('id')
        
        if not schedule_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "定时任务ID不能为空"}
            )
        
        # 创建定时任务管理器
        schedule_manager = ScheduledTaskManager(db)
        
        # 删除定时任务
        success = schedule_manager.delete_scheduled_task(schedule_id)
        
        if success:
            return JSONResponse(
                status_code=200,
                content={"success": True, "msg": "定时任务删除成功"}
            )
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error_msg": "定时任务删除失败"}
            )
            
    except Exception as e:
        logger.error(f"删除定时任务失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"删除定时任务失败：{str(e)}"}
        )


@router.post("/api/get_schedule_task", dependencies=[Depends(verify_token)])
async def get_schedule_task_api(request: Request):
    """获取任务的定时配置"""
    try:
        task_data = await request.json()
        
        task_id = task_data.get("task_id")
        
        if not task_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务ID不能为空"}
            )
        
        # 创建定时任务管理器
        schedule_manager = ScheduledTaskManager(db)
        
        # 获取定时任务配置
        schedule_task = schedule_manager.get_scheduled_task_by_task_id(task_id)
        
        if schedule_task:
            return JSONResponse(
                status_code=200,
                content={"success": True, "data": schedule_task}
            )
        else:
            return JSONResponse(
                status_code=200,
                content={"success": True, "data": None}
            )
            
    except Exception as e:
        logger.error(f"获取定时任务配置失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"获取定时任务配置失败：{str(e)}"}
        )


@router.post("/api/get_all_schedule_tasks", dependencies=[Depends(verify_token)])
async def get_all_schedule_tasks_api(request: Request):
    """获取所有定时任务"""
    try:
        task_data = await request.json()
        
        enabled_only = task_data.get("enabled_only", True)
        
        # 创建定时任务管理器
        schedule_manager = ScheduledTaskManager(db)
        
        # 获取所有定时任务
        schedule_tasks = schedule_manager.get_all_scheduled_tasks(enabled_only=enabled_only)
        
        return JSONResponse(
            status_code=200,
            content={"success": True, "data": schedule_tasks}
        )
            
    except Exception as e:
        logger.error(f"获取定时任务列表失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"获取定时任务列表失败：{str(e)}"}
        )


@router.post("/api/clean_task_log", dependencies=[Depends(verify_token)])
async def clean_task_log_api(request: Request):
    """清理任务日志"""
    try:
        body = await request.json()
        task_id_list = body.get("task_id_list", [])

        if not isinstance(task_id_list, list) or len(task_id_list) == 0:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务ID列表不能为空，且必须为数组格式"}
            )

        task_id_list = [str(tid).strip() for tid in task_id_list if tid and str(tid).strip()]
        if not task_id_list:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务ID列表中无有效任务ID"}
            )

        # 1. 生成对应数量的占位符（?），例如3个元素生成 "?, ?, ?"
        placeholders = ", ".join(["?"] * len(task_id_list))

        # 用 + 拼接列表，生成扁平参数
        params = ["任务日志清理成功\n"] + task_id_list

        # 3. 执行批量更新（不更新update_time，避免影响任务排序）
        success = db.execute_sql(
            f"UPDATE task SET log = ? WHERE task_id IN ({placeholders})",
            params=params,
            fetch="none"
        )

        if not success:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务日志清理失败"}
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "msg": f"任务日志清理成功",
                "task_id_list": task_id_list
            }
        )

    except Exception as e:
        logger.error(f"任务日志清理失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"任务日志清理失败：{str(e)}"}
        )


@router.post("/api/clear_task_logs", dependencies=[Depends(verify_token)])
async def clear_task_logs_api(request: Request):
    """清空选中任务的日志"""
    try:
        body = await request.json()
        task_id_list = body.get("task_id_list", [])

        if not isinstance(task_id_list, list) or len(task_id_list) == 0:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务ID列表不能为空，且必须为数组格式"}
            )

        task_id_list = [str(tid).strip() for tid in task_id_list if tid and str(tid).strip()]
        if not task_id_list:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务ID列表中无有效任务ID"}
            )

        # 1. 生成对应数量的占位符（?），例如3个元素生成 "?, ?, ?"
        placeholders = ", ".join(["?"] * len(task_id_list))

        # 2. 执行批量清空（将log字段设置为空字符串）
        success = db.execute_sql(
            f"UPDATE task SET log = '' WHERE task_id IN ({placeholders})",
            params=task_id_list,
            fetch="none"
        )

        if not success:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务日志清空失败"}
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": f"成功清空 {len(task_id_list)} 个任务的日志",
                "task_id_list": task_id_list
            }
        )

    except Exception as e:
        logger.error(f"任务日志清空失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"任务日志清空失败：{str(e)}"}
        )


@router.post("/api/clean_task_log_with_keep", dependencies=[Depends(verify_token)])
async def clean_task_log_with_keep_api(request: Request):
    """清理任务日志并保留指定比例"""
    try:
        body = await request.json()
        task_id_list = body.get("task_id_list", [])
        keep_ratio = body.get("keep_ratio", 0.2)

        if not isinstance(task_id_list, list) or len(task_id_list) == 0:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务ID列表不能为空，且必须为数组格式"}
            )

        if not 0 < keep_ratio <= 1:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "keep_ratio必须在0到1之间"}
            )

        task_id_list = [str(tid).strip() for tid in task_id_list if tid and str(tid).strip()]
        if not task_id_list:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务ID列表中无有效任务ID"}
            )

        success_count = 0
        failed_count = 0
        failed_tasks = []

        for task_id in task_id_list:
            try:
                # 读取当前日志
                task = db.execute_sql(
                    "SELECT log FROM task WHERE task_id = ?",
                    params=[task_id],
                    fetch="fetch_one"
                )

                if not task:
                    failed_count += 1
                    failed_tasks.append(task_id)
                    continue

                log_content = task.get("log", "")
                if not log_content:
                    # 日志为空，跳过
                    success_count += 1
                    continue

                # 按行分割
                lines = log_content.split('\n')
                total_lines = len(lines)

                # 计算保留的行数
                keep_lines = max(1, int(total_lines * keep_ratio))

                # 保留最新的日志
                new_content = '\n'.join(lines[-keep_lines:])

                # 更新数据库
                success = db.execute_sql(
                    "UPDATE task SET log = ? WHERE task_id = ?",
                    params=[new_content, task_id],
                    fetch="none"
                )

                if success:
                    success_count += 1
                else:
                    failed_count += 1
                    failed_tasks.append(task_id)

            except Exception as e:
                logger.error(f"清理任务日志失败 | task_id: {task_id}, error: {str(e)}")
                failed_count += 1
                failed_tasks.append(task_id)

        if failed_count > 0:
            msg = f"任务日志清理完成，成功{success_count}个，失败{failed_count}个（{', '.join(failed_tasks[:5])}{'...' if len(failed_tasks) > 5 else ''}）"
        else:
            msg = f"任务日志清理成功，保留最新{int(keep_ratio * 100)}%（{success_count}个任务）"

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "msg": msg,
                "success_count": success_count,
                "failed_count": failed_count,
                "task_id_list": task_id_list
            }
        )

    except Exception as e:
        logger.error(f"任务日志清理失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"任务日志清理失败：{str(e)}"}
        )



@router.post("/api/clean_task_log_all", dependencies=[Depends(verify_token)])
async def clean_task_log_all_api(request: Request):
    """清理任务日志"""
    try:

        # 3. 执行批量更新（不更新update_time，避免影响任务排序）
        success = db.execute_sql(
            f"UPDATE task SET log = ? WHERE TRUE",
            params=["任务日志清理成功\n"],
            fetch="none"
        )

        if not success:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "全部任务日志清理失败"}
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "msg": f"全部任务日志清理成功"
            }
        )

    except Exception as e:
        logger.error(f"全部任务日志清理失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"全部任务日志清理成功：{str(e)}"}
        )


@router.post("/api/check_log_length", dependencies=[Depends(verify_token)])
async def check_log_length_api(request: Request):
    """检查日志文件长度"""
    try:
        log_content = get_task_log_manager().read_log_file_content(max_lines=None, keyword=None)
        log_length = len(log_content) if log_content else 0

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "msg": "日志长度检查成功",
                "log_length": log_length
            }
        )

    except Exception as e:
        logger.error(f"日志长度检查失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"日志长度检查失败：{str(e)}"}
        )


@router.post("/api/clean_old_logs", dependencies=[Depends(verify_token)])
async def clean_old_logs_api(request: Request):
    """清除旧日志并保留指定比例"""
    try:
        body = await request.json()
        keep_ratio = body.get("keep_ratio", 0.2)

        if not 0 < keep_ratio <= 1:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "keep_ratio必须在0到1之间"}
            )

        # 读取所有日志
        log_content = get_task_log_manager().read_log_file_content(max_lines=None, keyword=None)
        if not log_content:
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "msg": "日志文件为空，无需清理"
                }
            )

        # 按行分割
        lines = log_content.split('\n')
        total_lines = len(lines)

        # 计算保留的行数
        keep_lines = max(1, int(total_lines * keep_ratio))

        # 保留最新的20%日志
        new_content = '\n'.join(lines[-keep_lines:])

        # 写入日志文件
        success, msg = get_task_log_manager().write_log_file_content(new_content)

        if not success:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": msg}
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "msg": f"旧日志已清除，保留最新{int(keep_ratio * 100)}%（{keep_lines}/{total_lines}行）"
            }
        )

    except Exception as e:
        logger.error(f"清除旧日志失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"清除旧日志失败：{str(e)}"}
        )


@router.post("/api/connect_total_log", dependencies=[Depends(verify_token)])
async def connect_total_log_api(request: Request):
    """连接任务日志"""
    try:
        body = await request.json()
        max_lines = body.get("max_lines", None)
        keyword = body.get("keyword", None)
        if max_lines:
            max_lines = int(max_lines)

        total_log_content = get_task_log_manager().read_log_file_content(max_lines=max_lines, keyword=keyword)

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "msg": f"总任务日志连接成功",
                "total_log_content": total_log_content
            }
        )

    except Exception as e:
        logger.error(f"总任务日志连接失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"总任务日志连接失败：{str(e)}"}
        )


@router.post("/api/clean_total_log", dependencies=[Depends(verify_token)])
async def clean_total_log_api(request: Request):
    """清理任务日志（清空total_log.txt）"""
    try:
        # 调用任务管理器的清空日志函数
        success, msg = get_task_log_manager().clean_total_log_file()

        if not success:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": msg}
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "msg": msg
            }
        )

    except Exception as e:
        error_msg = f"总任务日志清理失败：{str(e)}"
        logger.error(error_msg, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": error_msg}
        )


def get_default_download_path(filename: str) -> Path:
    """
    获取系统默认下载目录，并拼接文件名
    :param filename: 要导出的文件名
    :return: 默认下载路径的Path对象
    """
    # 根据系统类型获取默认下载目录
    if platform.system() == "Windows":
        # Windows：C:/Users/用户名/Downloads
        download_dir = Path(os.path.expanduser("~")) / "Downloads"
    elif platform.system() == "Darwin":  # macOS
        # macOS：/Users/用户名/Downloads
        download_dir = Path(os.path.expanduser("~")) / "Downloads"
    else:  # Linux
        # Linux：/home/用户名/Downloads
        download_dir = Path(os.path.expanduser("~")) / "Downloads"

    # 拼接默认下载路径（文件名保留原名称）
    default_export_path = download_dir / filename
    return default_export_path.resolve()


@router.post("/api/export_total_log", dependencies=[Depends(verify_token)])
async def export_total_log_api(request: Request):
    """
    导出total_log.txt到系统默认下载目录（可选传export_path自定义路径）
    请求体参数：
    {
        "filename": "total_log.txt",  // 可选，默认导出total_log.txt
        "export_path": "D:/导出文件/总日志.txt"  // 可选，不传则用默认下载目录
    }
    """
    try:
        ALLOWED_EXTENSIONS = {".txt", ".log", ".csv", ".xlsx", ".json"}

        # 解析请求体参数（兼容不传参的情况）
        request_data = await request.json() if await request.body() else {}
        filename = request_data.get("filename", "total_log.txt")  # 默认导出total_log.txt
        export_path = request_data.get("export_path")  # 可选，自定义导出路径

        # 1. 拼接源文件完整路径（修复原代码：TOTAL_LOG_FILE是文件路径，不是目录）
        # 若TOTAL_LOG_FILE是文件完整路径，直接使用；若为目录则拼接
        source_file_path = Path(TOTAL_LOG_FILE).resolve() if os.path.isfile(TOTAL_LOG_FILE) else Path(
            TOTAL_LOG_FILE) / filename
        source_file_path = source_file_path.resolve()

        # 2. 确定最终导出路径（优先用自定义路径，否则用默认下载目录）
        if export_path:
            final_export_path = Path(export_path).resolve()
        else:
            final_export_path = get_default_download_path(filename)

        # 3. 源文件存在性校验
        if not source_file_path.exists():
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": f"源文件不存在：{source_file_path}"}
            )

        # 4. 安全校验：仅允许导出指定后缀的文件
        file_ext = source_file_path.suffix.lower()
        if ALLOWED_EXTENSIONS and file_ext not in ALLOWED_EXTENSIONS:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error_msg": f"不允许导出该类型文件，仅支持：{','.join(ALLOWED_EXTENSIONS)}"}
            )

        # 5. 确保导出目录存在（自动创建不存在的目录）
        export_dir = final_export_path.parent
        if not export_dir.exists():
            export_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"自动创建导出目录：{export_dir}")

        # 6. 执行文件导出（复制文件，保留源文件）
        shutil.copy2(source_file_path, final_export_path)

        # 7. 日志记录 + 返回成功结果
        logger.info(f"文件导出成功 | 源文件：{source_file_path} | 导出路径：{final_export_path}")
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "msg": f"文件导出成功！\n自动导出到浏览器默认下载地址\n路径：{str(final_export_path)}",
                "export_path": str(final_export_path)  # 额外返回实际导出路径，方便前端展示
            }
        )

    # 针对性异常捕获
    except PermissionError:
        error_msg = "权限不足：无法读取源文件或写入导出路径"
        logger.error(error_msg, exc_info=True)
        return JSONResponse(
            status_code=403,
            content={"success": False, "error_msg": error_msg}
        )
    except FileNotFoundError as e:
        error_msg = f"文件不存在：{str(e)}"
        logger.error(error_msg)
        return JSONResponse(
            status_code=400,
            content={"success": False, "error_msg": error_msg}
        )
    except Exception as e:
        error_msg = f"文件导出失败：{str(e)}"
        logger.error(error_msg, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": error_msg}
        )


@router.post("/api/delete_task", dependencies=[Depends(verify_token)])
async def delete_task_api(request: Request):
    """删除任务"""
    try:
        body = await request.json()
        task_id_list = body.get("task_id_list", [])

        if not isinstance(task_id_list, list) or len(task_id_list) == 0:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务ID列表不能为空，且必须为数组格式"}
            )

        task_id_list = [str(tid).strip() for tid in task_id_list if tid and str(tid).strip()]
        if not task_id_list:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务ID列表中无有效任务ID"}
            )

        # 1. 生成对应数量的占位符（?），例如3个元素生成 "?, ?, ?"
        placeholders = ", ".join(["?"] * len(task_id_list))

        params = task_id_list + [TaskStatus.RUNNING, TaskStatus.PENDING]

        # 3. 执行批量更新
        success = db.execute_sql(
            f"delete FROM task WHERE task_id IN ({placeholders}) AND status NOT IN (?, ?)",
            params=params,
            fetch="none"
        )

        if not success:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务删除失败，只能删除未在执行的任务"}
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "msg": f"任务删除成功，成功删除{len(task_id_list)}条任务",
                "task_id_list": task_id_list
            }
        )

    except Exception as e:
        logger.error(f"任务删除失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"任务删除失败：{str(e)}"}
        )


@router.post("/api/update_task", dependencies=[Depends(verify_token)])
async def update_task_api(request: Request):
    """更新任务参数"""
    try:
        body = await request.json()
        
        task_id = body.get("task_id", "").strip()
        task_type = body.get("task_type", "").strip()
        task_kwargs = body.get("task_kwargs", {})
        
        if not task_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务ID不能为空"}
            )
        
        if not task_type:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务类型不能为空"}
            )
        
        # 检查任务是否存在
        task_info = db.execute_sql(
            "SELECT task_name, task_kwargs, mall_id, task_group FROM task WHERE task_id = ?",
            params=[task_id],
            fetch="fetch_one"
        )
        
        if not task_info:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error_msg": "任务不存在"}
            )
        
        # 从原有的task_kwargs中提取uid和main_task_id，确保更新时保留这些值
        old_task_kwargs_str = task_info.get("task_kwargs", "{}")
        old_task_kwargs = {}
        if old_task_kwargs_str:
            try:
                old_task_kwargs = json.loads(old_task_kwargs_str) if isinstance(old_task_kwargs_str, str) else old_task_kwargs_str
            except json.JSONDecodeError:
                old_task_kwargs = {}
        
        # 保留原有的uid和main_task_id
        if "uid" in old_task_kwargs:
            task_kwargs["uid"] = old_task_kwargs["uid"]
        if "main_task_id" in old_task_kwargs:
            task_kwargs["main_task_id"] = old_task_kwargs["main_task_id"]
        
        # 权限检查
        from config.permission_manager import permission_manager
        task_name = task_info.get("task_name", "")
        if not permission_manager.check_permission(task_type):
            return JSONResponse(
                status_code=403,
                content={"success": False, "error_msg": f"您没有执行此任务的权限"}
            )
        
        # 将task_kwargs转换为JSON字符串
        task_kwargs_str = json.dumps(task_kwargs, ensure_ascii=False)
        
        # 更新任务参数和守护任务状态
        is_maintain_task = body.get("is_maintain_task", None)
        if is_maintain_task is not None:
            # 同时更新 task_kwargs 和 is_maintain_task
            success = db.execute_sql(
                "UPDATE task SET task_kwargs = ?, is_maintain_task = ?, update_time = datetime('now', '+8 hours') WHERE task_id = ?",
                params=[task_kwargs_str, is_maintain_task, task_id],
                fetch="none"
            )
        else:
            # 只更新 task_kwargs
            success = db.execute_sql(
                "UPDATE task SET task_kwargs = ?, update_time = datetime('now', '+8 hours') WHERE task_id = ?",
                params=[task_kwargs_str, task_id],
                fetch="none"
            )
        
        if not success:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error_msg": "任务参数更新失败"}
            )
        
        # 处理定时任务配置
        schedule_enabled = body.get("schedule_enabled", False)
        if schedule_enabled:
            # 启用定时任务
            schedule_type = body.get("schedule_type", "once")
            schedule_time = body.get("schedule_time", None)
            schedule_interval = body.get("schedule_interval", None)
            execute_immediately = body.get("execute_immediately", False)
            
            # 创建定时任务管理器
            schedule_manager = ScheduledTaskManager(db)
            
            # 添加或更新定时任务
            add_result = schedule_manager.add_scheduled_task(
                task_id=task_id,
                schedule_type=schedule_type,
                schedule_time=schedule_time,
                schedule_interval=schedule_interval,
                schedule_enabled=True,
                execute_immediately=execute_immediately
            )
            
            if not add_result:
                logger.warning(f"定时任务添加/更新失败 | task_id: {task_id}")
        else:
            # 禁用定时任务
            schedule_manager = ScheduledTaskManager(db)
            schedule_manager.disable_scheduled_task(task_id)
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "msg": "任务参数更新成功",
                "task_id": task_id
            }
        )
            
    except Exception as e:
        logger.error(f"更新任务参数失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"更新任务参数失败：{str(e)}"}
        )


def re_run_task_thread(main_task_id):
    # 权限校验
    task_info = db.execute_sql(
        "SELECT task_name FROM task WHERE task_id = ?",
        params=[main_task_id],
        fetch="fetch_one"
    )
    
    if task_info:
        task_name = task_info.get("task_name", "")
        # 使用统一的权限管理器检查权限
        from config.permission_manager import permission_manager
        if not permission_manager.check_permission(task_name):
            logger.warning(f"任务重跑被拒绝，权限不足 | task_id: {main_task_id} | task_name: {task_name}")
            return {"success": False, "error_msg": f"您没有执行此任务的权限: {task_name}"}
    
    # 必须停止 并且子线程也停止
    not_stopped_task = db.execute_sql(
        "select * from task WHERE (status = ? or status = ?) and (parent_task_id = ? or task_id = ?)",
        params=[TaskStatus.PENDING, TaskStatus.RUNNING, main_task_id, main_task_id],
        fetch="fetch"
    )

    # 未停止则先停止，同步停止
    if not_stopped_task:
        resp = stop_task_thread(main_task_id)
        if not resp["success"]:
            return {"success": False, "error_msg": "重跑任务失败，执行重跑过程中任务停止步骤出错"}

    success = db.execute_sql(
        "UPDATE task SET status = ?, update_time = datetime('now', '+8 hours') WHERE task_id = ?",
        params=[TaskStatus.PENDING, main_task_id],
        fetch="none"
    )
    if not success:
        return {"success": False, "error_msg": "重跑任务失败，执行重跑过程中任务状态更新为待处理步骤出错"}

    return {"success": True, "message": f"任务重跑成功"}


def maintain_task_thread():
    """
    线程id固定
    """
    abnormal_info_list = [
        "403 Client Error",
        "登录页存在验证码"
    ]

    while True:
        time.sleep(5)

        maintain_task_id_list = db.execute_sql(
            "SELECT task_id FROM task WHERE is_maintain_task = ?",
            params=[1],
            fetch="fetch"
        )

        for item in maintain_task_id_list:
            main_id = item["task_id"]
            query = db.execute_sql(
                "select * from task WHERE status NOT IN (?, ?) and (parent_task_id = ? or task_id = ?)",
                params=[TaskStatus.PENDING, TaskStatus.RUNNING, main_id, main_id],
                fetch="fetch_one"
            )

            if not query:
                logger.info(f"task_id:{main_id} 查询任务id无任何结果，请检查任务id后重试")
                continue


            if not query["remarks"]:
                continue

            has_abnormal = any(abn in query["remarks"] for abn in abnormal_info_list)

            if has_abnormal:

                maintain_task_thread_space_time = config_manager.get_or_set_config(
                    "maintain_task_thread_space_time",
                    "30"  # 默认值
                )

                time.sleep(int(maintain_task_thread_space_time))
                task_kwargs = {
                    "main_task_id": main_id
                }
                success = MAIN_TASK_MANAGER.add_task(
                    task_id=f"{main_id}_重跑线程_先停止再重跑",
                    target_func=re_run_task_thread, **task_kwargs,
                    task_group="ikun",
                )
                if not success:
                    logger.warning(f"task_id:{main_id} 守护重跑任务执行重跑失败")



@router.post("/api/add_maintain_task", dependencies=[Depends(verify_token)])
async def add_maintain_task_api(request: Request):
    """
    守护任务清理（支持指定ID清理/全部清理）
    """
    try:
        # 1. 解析请求体，获取待清理任务ID列表
        body = await request.json()
        main_task_id_list = body.get("main_task_id_list", [])

        if not main_task_id_list:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务ID列表不能为空"}
            )

        for task_id in main_task_id_list:
            # 执行你指定的UPDATE原生SQL（与原有语法完全一致）
            db.execute_sql(
                sql="UPDATE task SET is_maintain_task = ?, update_time = datetime('now', '+8 hours') where task_id = ?",
                params=[1, task_id],
                fetch="none"
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "msg": "守护任务添加成功",
            }
        )

    except Exception as e:
        logger.error(f"守护任务添加失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"守护任务添加失败：{str(e)}"}
        )


@router.post("/api/del_maintain_task", dependencies=[Depends(verify_token)])
async def del_maintain_task_api(request: Request):
    """
    守护任务清理（支持指定ID清理/全部清理）
    """
    try:
        # 1. 解析请求体，获取待清理任务ID列表
        body = await request.json()
        main_task_id_list = body.get("main_task_id_list", [])

        # 无有效ID直接返回，避免无效遍历
        if not main_task_id_list:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务ID列表不能为空"}
            )

        # 2. 执行数据库删除操作，统计修改条数
        if len(main_task_id_list) == 1 and main_task_id_list[0] == "全部清理":
            db.execute_sql(
                "UPDATE task SET is_maintain_task = ?, update_time = datetime('now', '+8 hours') where 1",
                params=[None,],
                fetch="none"
            )
        else:
            for task_id in main_task_id_list:
                # 执行你指定的UPDATE原生SQL（与原有语法完全一致）
                db.execute_sql(
                    sql="UPDATE task SET is_maintain_task = ?, update_time = datetime('now', '+8 hours') where task_id = ?",
                    params=[None, task_id],
                    fetch="none"
                )

        # 5. 返回成功响应，包含统计信息
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "msg": "守护任务删除成功",
                "cleaned_ids": main_task_id_list  # 返回收起的ID列表，便于核对
            }
        )

    except Exception as e:
        # 异常时回滚事务，避免脏数据
        await db.rollback()
        logger.error(f"守护任务删除失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error_msg": "守护任务删除失败",
                "detail": str(e)[:200],  # 限制详细信息长度，避免返回过大数据
                "cleaned_count": 0
            }
        )



@router.post("/api/re_run_task", dependencies=[Depends(verify_token)])
async def re_run_task_api(request: Request):
    """任务重跑"""
    try:
        body = await request.json()
        main_task_id = body.get("task_id", "").strip()

        if not main_task_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务ID不能为空"}
            )

        # 获取任务信息
        task_info = db.execute_sql(
            "SELECT task_name FROM task WHERE task_id = ?",
            params=[main_task_id],
            fetch="fetch_one"
        )
        
        if not task_info:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error_msg": "任务不存在"}
            )
        
        task_name = task_info.get("task_name", "")
        
        # 使用统一的权限管理器检查权限
        from config.permission_manager import permission_manager
        if not permission_manager.check_permission(task_name):
            return JSONResponse(
                status_code=403,
                content={"success": False, "error_msg": f"您没有执行此任务的权限"}
            )

        task_kwargs = {
            "main_task_id": main_task_id
        }
        success = MAIN_TASK_MANAGER.add_task(
            task_id=f"{main_task_id}_重跑线程_先停止再重跑",
            target_func=re_run_task_thread, **task_kwargs,
            task_group="ikun",
        )
        if not success:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error_msg": "任务重跑失败，执行重跑提交任务线程失败"}
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "msg": "任务重跑提交成功",
                "task_id": main_task_id
            }
        )

    except Exception as e:
        logger.error(f"任务重跑提交失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"任务重跑提交失败：{str(e)}"}
        )


def stop_task_thread(main_task_id):
    for i in range(60):
        success = db.execute_sql(
            "UPDATE task SET status = ?, update_time = datetime('now', '+8 hours') WHERE task_id = ?",
            params=[TaskStatus.STOPPED, main_task_id],
            fetch="none"
        )
        if not success:
            return {"success": False, "error_msg": "任务停止失败"}

        sub_task_status = db.execute_sql(
            "select * from task WHERE  (status = ? or status = ?) and parent_task_id = ?",
            params=[TaskStatus.PENDING, TaskStatus.RUNNING, main_task_id],
            fetch="fetch"
        )

        if len(sub_task_status) == 0:
            success = db.execute_sql(
                "UPDATE task SET status = ?, update_time = datetime('now', '+8 hours') WHERE task_id = ?",
                params=[TaskStatus.STOPPED, main_task_id],
                fetch="none"
            )
            if not success:
                break
            return {"success": True, "error_msg": "任务停止成功"}

        time.sleep(3)
    return {"success": False, "error_msg": "任务停止超时/子任务更新失败"}


@router.post("/api/stop_task", dependencies=[Depends(verify_token)])
async def stop_task_api(request: Request):
    """任务停止"""
    try:
        body = await request.json()
        main_task_id = body.get("task_id", "").strip()

        if not main_task_id:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "任务ID不能为空"}
            )

        # 获取权限配置
        from config.permission_manager import permission_manager

        # 检查任务权限
        task_info = db.execute_sql(
            "SELECT task_name FROM task WHERE task_id = ?",
            params=[main_task_id],
            fetch="fetch_one"
        )
        
        if task_info:
            task_name = task_info.get("task_name", "")
            if not permission_manager.check_permission(task_name):
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error_msg": f"您没有停止任务 {main_task_id} 的权限"}
                )

        task_kwargs = {
            "main_task_id": main_task_id
        }
        success = MAIN_TASK_MANAGER.add_task(
            task_id=f"{main_task_id}_杀手线程",
            target_func=stop_task_thread, **task_kwargs,
            task_group="ikun",
        )

        if success:
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "msg": "任务停止信号已发送",
                    "task_id": main_task_id
                }
            )

    except Exception as e:
        logger.error(f"停止任务失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"停止任务失败：{str(e)}"}
        )


@router.post("/api/get_post_title", dependencies=[Depends(verify_token)])
async def get_post_title_api(request: Request):
    """获取帖子标题"""
    try:
        body = await request.json()
        post_input = body.get("post_input", "").strip()
        
        if not post_input:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "帖子ID或URL不能为空"}
            )
        
        # 提取帖子ID
        post_id = post_input
        
        # 如果输入的是完整URL，提取帖子ID
        if "hupu.com" in post_input:
            # 从URL中提取帖子ID
            # 格式: https://bbs.hupu.com/634838239.html
            parts = post_input.split("/")
            for part in parts:
                if part.endswith(".html"):
                    post_id = part.replace(".html", "")
                    break
        
        # 调用获取帖子标题的函数
        result = get_post_title(post_id)
        
        if result and result.get("posttitle"):
            return JSONResponse(
                status_code=200,
                content={"success": True, "data": {"post_title": result.get("posttitle")}}
            )
        else:
            return JSONResponse(
                status_code=200,
                content={"success": True, "data": {"post_title": ""}}
            )
            
    except Exception as e:
        logger.error(f"获取帖子标题失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"获取帖子标题失败：{str(e)}"}
        )


@router.post("/api/get_score_title", dependencies=[Depends(verify_token)])
async def get_score_title_api(request: Request):
    """获取评分标题"""
    try:
        body = await request.json()
        score_input = body.get("score_input", "").strip()
        
        if not score_input:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "评分ID或URL不能为空"}
            )
        
        # 提取评分ID
        score_id = score_input
        
        # 如果输入的是完整URL，提取评分ID
        if "hupu.com" in score_input:
            # 处理第一种格式：https://bbsactivity.hupu.com/pc-viewer/index.html?t=https%3A%2F%2Fm.hupu.com%2Fscore-item%2Fcommon_second%2F26848
            if "bbsactivity.hupu.com" in score_input and "?" in score_input:
                # 从URL参数中提取实际URL
                from urllib.parse import urlparse, parse_qs
                parsed = urlparse(score_input)
                query_params = parse_qs(parsed.query)
                if 't' in query_params:
                    # URL解码
                    from urllib.parse import unquote
                    actual_url = unquote(query_params['t'][0])
                    # 从实际URL中提取评分ID
                    # 格式: https://m.hupu.com/score-item/common_second/26848
                    parts = actual_url.split("/")
                    for part in parts:
                        if part.isdigit():
                            score_id = part
                            break
            # 处理第二种格式：https://m.hupu.com/score-item/common_second/26848
            else:
                # 从URL中提取评分ID
                # 格式: https://m.hupu.com/score-item/common_second/26848
                parts = score_input.split("/")
                for part in parts:
                    if part.isdigit():
                        score_id = part
                        break
        
        # 调用获取评分标题的函数
        result = get_score_title(score_id)
        
        if result and result.get("score_title"):
            return JSONResponse(
                status_code=200,
                content={"success": True, "data": {"score_title": result.get("score_title")}}
            )
        else:
            return JSONResponse(
                status_code=200,
                content={"success": True, "data": {"score_title": ""}}
            )
            
    except Exception as e:
        logger.error(f"获取评分标题失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"获取评分标题失败：{str(e)}"}
        )


@router.post("/api/fetch_activity_list", dependencies=[Depends(verify_token)])
async def fetch_activity_list_api(request: Request):
    """获取店铺活动列表
    {
        "uid": "店铺UID"
    }
    """
    try:
        params = await request.json()
        uid = params.get("uid", "")
        
        if not uid:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "店铺UID不能为空"}
            )
        
        # 获取店铺信息
        from utils.TemuBase import get_shop_info_db
        shop_info = get_shop_info_db(uid)
        
        if not shop_info or not isinstance(shop_info, dict):
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "店铺不存在"}
            )
        
        required_keys = ["headers", "cookies"]
        if not all(key in shop_info for key in required_keys):
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "请先连接店铺"}
            )
        
        # 获取活动列表
        from temu_modules.temu_function.apply_activity import final_get_activity_list
        result = final_get_activity_list(uid, shop_info["headers"], shop_info["cookies"])
        
        # 合并大活动和小活动
        activity_list = []
        
        # 处理大活动
        for activity in result.get("big_activities", []):
            activity_list.append({
                "activityName": activity.get("activityName", ""),
                "activityType": activity.get("activityType", 0),
                "stockThreshold": activity.get("stockThreshold", 30),
            })
        
        # 处理小活动
        for activity in result.get("small_activities", []):
            activity_list.append({
                "activityName": activity.get("activityName", ""),
                "activityType": activity.get("activityType", 0),
                "activityThematicId": activity.get("activityThematicId", 0),
                "activityThematicName": activity.get("activityThematicName", ""),
                "stockThreshold": activity.get("stockThreshold", 5),
            })
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "data": activity_list,
                "message": f"获取活动列表成功，共{len(activity_list)}个活动"
            }
        )
        
    except Exception as e:
        logger.error(f"获取活动列表失败：{str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"获取活动列表失败：{str(e)}"}
        )
