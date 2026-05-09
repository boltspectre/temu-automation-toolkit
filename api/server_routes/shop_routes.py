# api/shop_routes.py
import ast
from datetime import datetime, timedelta

from fastapi import APIRouter, Query, Depends, Request
from loguru import logger
from starlette.responses import JSONResponse

from api.server_routes.auth import verify_token
from config.common_config import config_manager
from config.middleware_config import db, generator
from config.start_config import MAIN_TASK_MANAGER
from lite_modules.del_img import delete_old_pictures
from utils.TemuBase import connect_shop, test_connect_shop

# 创建路由实例
router = APIRouter()

# -------------------------- 店铺分页接口 --------------------------
@router.get("/api/page", dependencies=[Depends(verify_token)])
def paginate_shop_data(
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(10, ge=1, le=100, description="每页条数"),
        keyword: str = Query("", description="搜索关键词（店铺名称/缩写/Browser ID）"),
        sort_field: str = Query("id", description="排序字段"),
        sort_order: str = Query("asc", description="排序方式：asc/desc")
):
    """店铺数据分页接口（从数据库读取）"""
    try:
        # 1. 构建基础查询SQL
        base_sql = "SELECT * FROM shops"
        params = []

        # 2. 关键词过滤
        filter_conditions = []
        if keyword.strip():
            keyword_lower = f"%{keyword.strip().lower()}%"
            filter_conditions.append("(LOWER(shop_name) LIKE ? OR LOWER(shop_abbr) LIKE ? OR LOWER(browser_id) LIKE ?)")
            params.extend([keyword_lower, keyword_lower, keyword_lower])

        if filter_conditions:
            base_sql += " WHERE " + " AND ".join(filter_conditions)

        # 3. 排序处理
        valid_sort_fields = ["id", "shop_name", "shop_abbr", "browser_id", "phone", "password", "create_time", "update_time"]
        sort_field = sort_field if sort_field in valid_sort_fields else "id"
        sort_order = "ASC" if sort_order.lower() == "asc" else "DESC"
        base_sql += f" ORDER BY {sort_field} {sort_order}"

        # 4. 获取总条数
        count_sql = f"SELECT COUNT(*) as total FROM ({base_sql}) as temp"
        count_result = db.execute_sql(count_sql, params=params, fetch="fetch_one")
        total = count_result["total"] if count_result else 0

        # 5. 分页计算
        total_pages = (total + page_size - 1) // page_size
        offset = (page - 1) * page_size
        paginated_sql = base_sql + " LIMIT ? OFFSET ?"
        params.extend([page_size, offset])

        # 6. 执行分页查询
        shop_list = db.execute_sql(paginated_sql, params=params, fetch="fetch")

        # 7. 格式化数据
        formatted_data = []
        for shop in shop_list:
            formatted_data.append({
                "id": shop.get("id"),
                "店铺名称": shop.get("shop_name") or "",
                "店铺缩写": shop.get("shop_abbr") or "",
                "browser_id": shop.get("browser_id") or "",
                "phone": shop.get("phone") or "",
                "password": shop.get("password") or "",
                "uid": shop.get("uid"),
                "is_multi_shops": shop.get("multi_shops") or "0",
                "connect_status": shop.get("connect_status") or "未连接",
                "create_time": shop.get("create_time").strftime("%Y-%m-%d %H:%M:%S") if shop.get("create_time") else "",
                "update_time": shop.get("update_time").strftime("%Y-%m-%d %H:%M:%S") if shop.get("update_time") else "",
                "headers": shop.get("headers"),
                "cookies": shop.get("cookies")
            })

        phone_count = {}
        for item in formatted_data:
            phone = item["phone"].strip()
            if phone:  # 只统计非空手机号
                phone_count[phone] = phone_count.get(phone, 0) + 1

        # 步骤2：找出重复的手机号（出现次数>1）
        duplicate_phones = [phone for phone, count in phone_count.items() if count > 1]

        # 步骤3：给重复手机号的行标记 is_phone_duplicate = True
        for item in formatted_data:
            phone = item["phone"].strip()
            if phone in duplicate_phones:
                item["is_phone_duplicate"] = True

        # 步骤4（可选）：返回重复手机号列表，方便前端批量展示
        duplicate_phone_list = list(duplicate_phones)

        return {
            "success": True,
            "data": formatted_data,
            "duplicate_phone_list": duplicate_phone_list,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "has_prev": page > 1,
                "has_next": page < total_pages
            }
        }
    except Exception as e:
        logger.error(f"分页查询失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"分页查询失败：{str(e)}"}
        )

# -------------------------- 店铺状态检测 --------------------------
# 从数据库获取最新店铺连接状态
@router.get("/api/check_shop_status", dependencies=[Depends(verify_token)])
def check_shop_status(uid: str = Query(..., description="uid")):
    """从数据库获取最新店铺连接状态"""
    try:
        shop = db.execute_sql(
            "SELECT connect_status FROM shops WHERE uid = ?",
            params=[uid],
            fetch="fetch_one"
        )
        if not shop:
            return {"success": False, "connected": False, "error_msg": "店铺不存在"}

        is_connected = shop.get("connect_status") == "已连接"
        return {
            "success": True,
            "connected": is_connected,
            "uid": uid
        }
    except Exception as e:
        logger.error(f"检测店铺状态失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"{str(e)}"}
        )


# -------------------------- 店铺连接 --------------------------
@router.post("/api/toggle_shop_connection/test", dependencies=[Depends(verify_token)])
async def toggle_shop_connection_test(request: Request):
    """检测店铺连接状态"""
    try:
        body = await request.json()
        uid = body.get("uid")
        if not uid:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": f"uid为必传参数"}
            )

        task_kwargs = {"uid": uid}

        task_id = f"test_connect_{uid}_task"
        success = MAIN_TASK_MANAGER.add_task(
            task_id=task_id,
            target_func=test_connect_shop, **task_kwargs,
            task_group="ikun"
        )

        return {
            "success": success,
            "task_id": task_id,
            "message": "检测连接任务已提交"
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"{str(e)}"}
        )

@router.post("/api/toggle_shop_connection", dependencies=[Depends(verify_token)])
async def toggle_shop_connection(request: Request):
    """执行店铺连接任务"""
    try:
        body = await request.json()
        uid = body.get("uid")
        if not uid:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": f"uid为必传参数"}
            )

        task_kwargs = {
            "uid": uid,
            "login_type": body.get("login_type", "ikun"),
            "reload_cookies": body.get("reload_cookies", False),
            "headless": body.get("headless", False),
            "auto_close": body.get("auto_close", True),
            "window_size": body.get("window_size", [1920, 1080])
        }

        task_id = f"connect_shop_{uid}_task"

        success = MAIN_TASK_MANAGER.add_task(
            task_id=task_id,
            target_func=connect_shop, **task_kwargs,
            task_group="ikun",
        )

        return {
            "success": success,
            "task_id": task_id,
            "message": "连接任务已提交"
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": f"{str(e)}"}
        )

# -------------------------- 店铺添加/修改/删除 --------------------------
@router.post("/api/add_shop", dependencies=[Depends(verify_token)])
async def add_shop_api(request: Request):
    """添加店铺"""
    try:
        body = await request.json()
        browser_id = body.get("browser_id")
        shop_name = body.get("shop_name")
        shop_abbr = body.get("shop_abbr")
        phone = body.get("phone")
        password = body.get("password")
        # 生成uid
        uid = generator.generate_id()

        fields = [browser_id, shop_name, shop_abbr, phone, password]
        if not any(field and str(field).strip() for field in fields):
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": f"店铺信息不能全为空"}
            )

        db.execute_sql(
            "INSERT INTO shops (uid, browser_id, shop_name, shop_abbr, phone, password, create_time, update_time) VALUES (?, ?, ?, ?, ?, ?, datetime('now', '+8 hours'), datetime('now', '+8 hours'))",
            params=[uid, browser_id, shop_name, shop_abbr, phone, password],
            fetch="none"
        )

        return {
            "success": True,
            "message": f"店铺添加成功"
        }

    except Exception as e:
        logger.error(f"添加店铺失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": str(e)}
        )


@router.post("/api/modify_shop", dependencies=[Depends(verify_token)])
async def modify_shop_info(request: Request):
    """编辑店铺信息 前端所有参数都要传,不传的会默认更新数据库为null值"""
    try:
        body = await request.json()
        uid = body.get("uid")
        browser_id = body.get("browser_id")
        shop_name = body.get("shop_name")
        shop_abbr = body.get("shop_abbr")
        phone = body.get("phone")
        password = body.get("password")

        success = db.execute_sql(
            "UPDATE shops SET browser_id = ?, update_time = datetime('now', '+8 hours'), shop_name = ?, shop_abbr = ?, phone = ?, password = ? WHERE uid = ?",
            params=[browser_id, shop_name, shop_abbr, phone, password, uid],
            fetch="none"
        )
        if success == 1:
            return {
                "success": True,
                "message": f"店铺信息修改成功"
            }
        else:
            return {
                "success": False,
                "message": f"店铺信息修改失败"
            }

    except Exception as e:
        logger.error(f"修改店铺ID失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": str(e)}
        )

@router.post("/api/delete_shop", dependencies=[Depends(verify_token)])
async def delete_shop(request: Request):
    """编辑店铺信息 前端所有参数都要传,不传的会默认更新数据库为null值"""
    try:
        body = await request.json()
        uid = body.get("uid")

        if not uid:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "店铺UID不能为空"}
            )

        success = db.execute_sql(
            "delete from shops WHERE uid = ?",
            params=[uid],
            fetch="none"
        )
        if success == 1:
            return {
                "success": True,
                "message": f"店铺删除成功"
            }
        else:
            return {
                "success": False,
                "message": f"店铺删除失败"
            }

    except Exception as e:
        logger.error(f"店铺删除异常：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": str(e)}
        )


@router.post("/api/delete_record_page", dependencies=[Depends(verify_token)])
async def delete_record_page(request: Request):
    """删除店铺记录"""
    try:
        body = await request.json()
        uid = body.get("uid")

        if not uid:
            return JSONResponse(
                status_code=400,
                content={"success": False, "error_msg": "店铺浏览器id不能为空"}
            )

        if uid == "all123":
            db.execute_sql("update record_page set upload_pic_all = ?, update_time = datetime('now', '+8 hours')",
                           params=None,
                           fetch="none")
            message = "所有店铺记录已删除"
        else:
            db.execute_sql("update record_page set upload_pic_all = ?, update_time = datetime('now', '+8 hours') where uid = ?",
                           params=(None, uid),
                           fetch="none")
            message = f"店铺记录已删除"

        return {
            "success": True,
            "message": message
        }
    except Exception as e:
        logger.error(f"删除店铺记录失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": str(e)}
        )

@router.get("/api/delete_images", dependencies=[Depends(verify_token)])
async def delete_images(request: Request):
    """删除店铺记录"""
    try:

        TARGET_FOLDER = r"PS后"
        cutoff_datetime = datetime.now() - timedelta(hours=0.01)
        delete_result = delete_old_pictures(TARGET_FOLDER, cutoff_datetime)

        return {
            "success": True,
            "message": delete_result
        }
    except Exception as e:
        logger.error(f"删除店铺记录失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": str(e)}
        )



@router.post("/api/get_connect_shop_config", dependencies=[Depends(verify_token)])
async def delete_shop(request: Request):
    try:
        body = await request.json()

        save = body.get("save")

        prefix = "connect_shop_config_"

        if str(save) == "0":
            login_type = config_manager.get_or_set_config(
                f"{prefix}login_type",
                "ikun"  # 默认值
            )
            reload_cookies = config_manager.get_or_set_config(
                f"{prefix}reload_cookies",
                "False"  # 默认值
            )
            headless = config_manager.get_or_set_config(
                f"{prefix}headless",
                "False"  # 默认值
            )
            auto_close = config_manager.get_or_set_config(
                f"{prefix}auto_close",
                "True"  # 默认值
            )
            save = config_manager.get_or_set_config(
                f"{prefix}save",
                "1"  # 默认值
            )
            str_window_size = config_manager.get_or_set_config(
                f"{prefix}window_size",
                "(1920, 1080)"  # 默认值
            )

            window_size = ast.literal_eval(str_window_size)

            return {
                "success": True,
                "message": f"店铺连接配置获取成功",
                "login_type": login_type,
                "reload_cookies": bool(reload_cookies),
                "headless": bool(headless),
                "auto_close": bool(auto_close),
                "window_size": window_size,
                "save": save
            }

        else:
            login_type = body.get("login_type")
            reload_cookies = body.get("reload_cookies")
            headless = body.get("headless")
            auto_close = body.get("auto_close")
            window_size = body.get("window_size")

            config_manager.upsert_config(f"{prefix}login_type", login_type)
            config_manager.upsert_config(f"{prefix}reload_cookies", reload_cookies)
            config_manager.upsert_config(f"{prefix}headless", headless)
            config_manager.upsert_config(f"{prefix}auto_close", auto_close)
            config_manager.upsert_config(f"{prefix}window_size", window_size)

            return {
            "success": True,
            "message": f"店铺连接配置保存成功",
            "login_type": login_type,
            "reload_cookies": bool(reload_cookies),
            "headless": bool(headless),
            "auto_close": bool(auto_close),
            "window_size": window_size,
            "save": save
        }

    except Exception as e:
        logger.error(f"获取或保存店铺连接配置失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": str(e)}
        )


@router.post("/api/jit_default_config", dependencies=[Depends(verify_token)])
async def manage_jit_default_config(request: Request):
    """管理JIT默认配置"""
    try:
        body = await request.json()
        action = body.get("action", "get")  # get 或 set
        
        if action == "get":
            # 获取JIT默认库存数量
            default_final_num = config_manager.get_or_set_config("jit_default_final_num", "500")
            return {
                "success": True,
                "default_final_num": int(default_final_num)
            }
        elif action == "set":
            # 设置JIT默认库存数量
            final_num = body.get("final_num")
            if final_num is None or not isinstance(final_num, int) or final_num < 1:
                return {
                    "success": False,
                    "error_msg": "无效的库存数量，必须为大于0的整数"
                }
            
            config_manager.upsert_config("jit_default_final_num", str(final_num))
            return {
                "success": True,
                "message": f"JIT默认库存数量已设置为 {final_num}",
                "default_final_num": final_num
            }
        else:
            return {
                "success": False,
                "error_msg": "无效的操作类型"
            }
            
    except Exception as e:
        logger.error(f"管理JIT默认配置失败：{str(e)}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error_msg": str(e)}
        )