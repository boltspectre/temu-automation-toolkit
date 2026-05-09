# upload_real_pic.py
import ast
import json
import os
import random
import sys
import time
from collections import defaultdict
from queue import Queue
from typing import Any

from loguru import logger
from requests_toolbelt import MultipartEncoder

from config.common_config import upload_pic_check_rules_path, upload_real_pic_concurrent, config_manager
from config.middleware_config import db

from lite_modules.change_upload_pic_xy import change_upload_pic_main
from lite_modules.del_img import get_all_img_paths_advanced
from config.usual_config import TEMU_PAGE_SIZE
from temu_modules.temu_function.goods_compliance_information import all_compliance_tijiao, get_query_compliance_order
from temu_modules.temu_function.general_interface import get_up_new_lifecycle_list, build_skc_spu_dict, \
    quick_get_related_id, get_price_groups
from temu_modules.temu_modules_tools.upload_real_pic_tools import build_real_pic_payload, extract_real_pic_list_json
from utils.log_utils import auto_print_logger, auto_return, AutoReturnError
from utils.multiThreading_log_manager import check_task_stopped, get_task_log_manager
from utils.send_temu_req import send_req

# ====== 全局变量 ======
_UPLOAD_RULES = None


# ====== 获取上传图片的异常列表 ======
def get_real_picture_list(uid, headers: dict, cookies: dict, page_num: int, check_type_list=None,
                          rapid_screen_status_list=None, input_spu_id_list: list[int] = None,
                          max_retries: int = 5, black_word_type_list=None, goods_status_list=None, main_task_id: str = None,
                          ) -> dict:
    """
    获取上传图片的异常列表 筛选条件为[]则不筛选某项
    :param goods_status_list: 商品状态
    :param black_word_type_list: 敏感词识别
    :param cookies:
    :param headers:
    :param input_spu_id_list:
    :param rapid_screen_status_list: 快速筛选 待传图 异常
    :param max_retries:
    :param page_num:
    :param check_type_list: [135]类型 建议只输入一个或使用for依次执行

    :return:
    """
    if rapid_screen_status_list is None:
        rapid_screen_status_list = []
    _result = {}
    for attempt in range(1, max_retries + 1):

        url = "https://agentseller.temu.com/api/flash/real_picture/list"

        payload = {"page": page_num, "page_size": TEMU_PAGE_SIZE}

        if check_type_list is not None:
            payload["check_type_list"] = check_type_list
        if rapid_screen_status_list is not None:
            payload["rapid_screen_status_list"] = rapid_screen_status_list
        if goods_status_list is not None:
            payload["goods_status_list"] = goods_status_list
        if black_word_type_list is not None:
            payload["black_word_type_list"] = black_word_type_list

        if input_spu_id_list is not None:
            # 步骤1：过滤 None/空元素；步骤2：转字符串；步骤3：非空才更新（避免传空列表）
            valid_spu_ids = [str(i) for i in input_spu_id_list if i is not None and i != ""]
            if valid_spu_ids:  # 仅当有有效ID时才添加该字段
                payload["spu_id_list"] = valid_spu_ids
            # 若 valid_spu_ids 为空，不添加 spu_id_list 字段（接口按“全部”处理）

        # payload其他参数
        # rapid_screen_status_list [1] 待传图 [4] 异常
        # goods_status_list [1] 在售中 [2] 未发布到站点 [] 全部
        # "check_type_status_list": []

        response = send_req(
            uid=uid,
            method="POST",
            headers=headers,
            cookies=cookies,
            url=url,
            json=payload,
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
            _result = {"code": 1, "msg": "获取实拍图订单列表成功", "data": response.json(), "remarks": remarks}
            break
        else:
            _result = {"code": -1, "msg": "获取实拍图订单列表失败", "data": response.json(), "remarks": remarks}
            continue

    auto_print_logger(_result, main_task_id=main_task_id)


    return _result


def _load_upload_pic_check_rules(config_path):
    # "配置文件_系统配置/upload_pic_check.json"
    global _UPLOAD_RULES
    if _UPLOAD_RULES is None:
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                _UPLOAD_RULES = data.get("abnormal_rules", [])
        except Exception as e:
            logger.error(f"加载上传图片规则失败: {e}")
            _UPLOAD_RULES = []
    return _UPLOAD_RULES



def get_upload_pic_signature(uid, headers: dict, cookies: dict) -> str | None:
    """
    获取上传图片的签名参数

    :return:
    """
    logger.trace("获取上传图片的签名参数")
    payload = {"tag": "flash-tag"}
    url = "https://agentseller.temu.com/ms/bg-flux-ms/compliance_property/signature"

    resp = send_req(
        uid=uid,
        method="POST",
        headers=headers,
        cookies=cookies,
        url=url,
        json=payload,
    )
    try:
        if not resp.json()["success"]:
            return None
    except Exception as e:
        logger.error(e)
        return None

    return resp.json()["result"]


def upload_image(uid, headers: dict, cookies: dict, file_path: str, upload_sign: str) -> dict:
    """
    使用 MultipartEncoder 精确构造 multipart/form-data 上传图片
     BitBrowser ID
    :param file_path: 图片路径，如 "小地毯.jpg"
    :param upload_sign: 签名
    :return: 响应 JSON
    """
    url = "https://agentseller.temu.com/api/galerie/v3/store_image?sdk_version=js-0.0.33&tag_name=flash-tag"

    # 读取文件内容（必须一次性读完，因为 MultipartEncoder 需要 bytes）
    with open(file_path, 'rb') as f:
        file_content = f.read()

    filename = os.path.basename(file_path)

    # 构造 multipart 表单 headers 必须multipart
    multipart_data = MultipartEncoder(
        fields={
            'upload_sign': upload_sign,
            'url_width_height': 'true',
            'image': (filename, file_content, 'image/jpeg')
        }
    )

    # 调用统一认证请求（不要传 files，只传 data=multipart_data）
    resp = send_req(
        uid=uid,
        method="POST",
        headers={"Content-Type": multipart_data.content_type},
        cookies=cookies,
        url=url,
        data=multipart_data,
    )

    return resp.json()


def do_upload_new(uid, headers: dict, cookies: dict, payload) -> dict:
    """
    将提交的图片绑定到商品，上传图片最后一步 接口 upload_new

    :return:
    """
    url = "https://agentseller.temu.com/api/flash/real_picture/upload_new"
    resp = send_req(
        uid=uid,
        method="POST",
        headers=headers,
        cookies=cookies,
        url=url,
        json=payload,
    )

    return resp.json()


def get_image_name_by_check_type(check_type: int) -> str | None:
    """
    根据 check_type 值，从 upload_pic_check.json 中查找对应的 image_name。
    仅匹配 primary.check_type。

    :param check_type: 异常类型编号，如 135
    :return: 对应的图片文件名（如 "小地毯.jpg"），未找到返回 None
    """
    for rule in _load_upload_pic_check_rules(upload_pic_check_rules_path):
        primary = rule.get("primary")
        if (
                primary
                and primary.get("check_type") == check_type
                and rule.get("image_name")
        ):
            return rule["image_name"]
    return None


def spu_id_list_2_skc_id_list(uid, headers: dict, cookies: dict, shop_abbr: str, spu_id_list: list) -> tuple[Any, Any]:
    """
    :param spu_id_list:
    :return: skc2spu, spu2skc
    """
    # 先传入spu列表，查询对应的待传图订单
    modify_price_list = get_up_new_lifecycle_list(uid, headers, cookies, spu_id_list=spu_id_list, type="search_skc_id")
    # 获取price_groups中间产物，用于获取skc-spu对应表
    price_groups = get_price_groups(shop_abbr, modify_price_list["data"])
    # 得到skc-spu对应表
    skc_spu_list = price_groups["skc_spu"]
    # 建立skc-spu对应字典
    skc2spu, spu2skc = build_skc_spu_dict(skc_spu_list)

    return skc2spu, spu2skc


def extract_img_url_list(spu_data: dict, img_url_list: list[str]):
    # 1. 初始化pos_dict，兼容空列表/字段缺失
    pos_dict = defaultdict(list)

    reload_all_img = True
    if reload_all_img:
        label_images = []
    else:
        # 获取已有图片，从这里开始添加
        label_images = spu_data.get('label_image_list', [])

    # 遍历处理每张图片（增加多层防护）
    for img in label_images:
        # 防护1：确保img是字典类型
        if not isinstance(img, dict):
            continue
        # 防护2：确保position和image字段存在且有值
        position = img.get('position')
        image = img.get('image')
        if not position or not image:
            continue
        # 防护3：将position转为字符串（避免数字/其他类型键名问题）
        pos_dict[str(position)].append(image)

    # 2. 转换为普通字典，并强制确保1/2键存在（核心需求）
    upload_img_urls = dict(pos_dict)
    # 关键：不存在则创建空列表，存在则保留原有值
    upload_img_urls['1'] = upload_img_urls.get('1', [])
    upload_img_urls['2'] = upload_img_urls.get('2', [])

    for img_url in img_url_list:
        # 3. 正常插入新图片URL（此时1/2键一定存在，不会报错）
        upload_img_urls['1'].append(img_url)
        upload_img_urls['2'].append(img_url)

    return upload_img_urls


def determine_upload_params(shop_abbr: str, check_type_list: list,
                            rapid_screen_status_list: list,
                            input_spu_id_list=None,
                            black_word_type_list: list = None,
                            goods_status_list: list = None,
                            ):
    # 解包参数
    all_rerun = False

    # 接续上次记录的page开始跑
    if not rapid_screen_status_list and not check_type_list and not input_spu_id_list and not input_spu_id_list \
            and not black_word_type_list and not goods_status_list:

        logger.info(f"店铺{shop_abbr}： 开始实拍图全部重跑流程")
        all_rerun = True

    elif input_spu_id_list:
        logger.info(f"店铺{shop_abbr}： 执行指定SPU上传流程")
    # 待上传图片流程
    elif rapid_screen_status_list == [1]:
        logger.info(f"店铺{shop_abbr}： 开始执行待上传图片流程")

    # 自定义流程
    else:
        logger.info(f"店铺{shop_abbr}： 自定义规则上传图片流程")


    logger.info(f"覆盖旧图片：✅自动开启")
    return {
        "all_rerun": all_rerun,
    }


def mark_upload(headers: dict, cookies: dict, check_type_list: list, shop_abbr: str, uid):
    """
    上传异常列表中匹配特殊配置文件的标签，返回待绑定图片url列表
    核心修改：局部去重 - 单次函数调用内，相同upload_pic_file_path只上传一次
    :param check_type_list: 异常类型列表
    :param shop_abbr: 店铺缩写
    :return:img_url_list
    """
    try:
        img_url_list = []
        # ====== 核心新增：局部集合，记录已处理的文件路径（仅本次函数调用有效） ======
        processed_file_paths = set()

        for check_type in check_type_list:
            mark_img_name = get_image_name_by_check_type(check_type)
            if mark_img_name is None:
                continue

            # 拼接文件路径
            upload_pic_file_path = f"配置文件_实拍图配置/{mark_img_name}"

            # ====== 核心去重逻辑：路径已处理过 → 直接跳过 ======
            if upload_pic_file_path in processed_file_paths:
                # logger.info(
                #     f"店铺{shop_abbr}：本次调用中已处理过图片{upload_pic_file_path}，跳过重复上传 | check_type={check_type}")
                continue

            # 路径未处理 → 执行上传，并标记为已处理
            img_url = upload_pictrue_wrapper(headers, cookies, upload_pic_file_path, shop_abbr, uid=uid)

            img_url_list.append(img_url)
            # 将路径加入已处理集合，避免后续重复
            processed_file_paths.add(upload_pic_file_path)
            logger.info(f"店铺{shop_abbr}：成功上传图片{upload_pic_file_path} | check_type={check_type} | URL={img_url}")

        return img_url_list

    except AutoReturnError as e:
        logger.error(e.result)
        return []


def other_img_upload(headers: dict, cookies: dict, shop_abbr: str, uid):
    """
    上传其他固定需要上传的图片，返回待绑定图片url列表
    :param shop_abbr:
    :return: img_url_list
    """
    try:
        other_img_url_list = []

        other_img_path_list = get_all_img_paths_advanced(
            img_extensions={'.png', '.jpg'},
            recursive=False,
            base_dir="配置文件_实拍图配置/fixed_upload_img"
        )

        for other_img_path in other_img_path_list:
            other_img_url = upload_pictrue_wrapper(headers, cookies, other_img_path, shop_abbr, uid=uid)

            other_img_url_list.append(other_img_url)

        return other_img_url_list

    except AutoReturnError as e:
        logger.error(e.result)
        return []


def compliance_upload(uid, headers: dict, cookies: dict, spu_id: int, shop_abbr: str, query_json_list: dict, skc2spu: list,
                      spu2skc: list):
    """
    合规信息实拍图上传，返回待绑定图片url
    执行上传合规信息all_compliance_tijiao 执行批图 获取签名 上传图片

    :param spu_id:
    :param shop_abbr:
    :return:
    """
    try:
        # 获取skc_id
        skc_id = quick_get_related_id(skc2spu, spu2skc, spu_id)

        # 执行上传合规信息
        all_compliance_tijiao(shop_abbr, headers, cookies, query_json_list, skc_id, spu_id, uid)
        # print(f"店铺{shop_abbr}： SPU={spu_id} SKC={skc_id}")

        if not skc_id:
            origin_remarks = db.execute_sql(
                "select remarks from shops where uid = ?",
                params=[uid],
                fetch="fetch_one"
            )["remarks"]

            remarks = origin_remarks + f"店铺{shop_abbr}： SPU={spu_id} 获取SKC失败，无法继续执行\n"
            logger.error(remarks)

            success = db.execute_sql(
                "UPDATE shops SET remarks = ?, update_time = datetime('now', '+8 hours') WHERE uid = ?",
                params=[remarks, uid],
                fetch="none"
            )
            if not success:
                logger.error(f"店铺{shop_abbr}：记录异常日志出错！remarks:{remarks}")
            return None

        # 执行批图
        ps_success, upload_pic_file_path = change_upload_pic_main(shop_abbr, spu_id, skc_id, json_data=None)
        if not ps_success:
            error_msg = f"店铺{shop_abbr}：SPU={spu_id} 图片验证失败 → {upload_pic_file_path}"
            logger.error(error_msg)
            
            # 将错误信息记录到数据库备注
            origin_remarks = db.execute_sql(
                "select remarks from shops where uid = ?",
                params=[uid],
                fetch="fetch_one"
            )["remarks"]

            # 处理 remarks 可能为 None 的情况
            if origin_remarks is None:
                origin_remarks = ""
            
            remarks = origin_remarks + f"{error_msg}\n"
            success = db.execute_sql(
                "UPDATE shops SET remarks = ?, update_time = datetime('now', '+8 hours') WHERE uid = ?",
                params=[remarks, uid],
                fetch="none"
            )
            if not success:
                logger.error(f"店铺{shop_abbr}：记录异常日志出错！remarks:{remarks}")
            
            return None

        img_url = upload_pictrue_wrapper(headers, cookies, upload_pic_file_path, shop_abbr, uid=uid)

        return img_url

    except AutoReturnError as e:
        logger.error(f"店铺{shop_abbr}： 上传合规信息出错：{e.result}")
        return None


def upload_pictrue_wrapper(headers, cookies, upload_pic_file_path, shop_abbr, uid):
    # 获取签名
    upload_sign = get_upload_pic_signature(uid, headers, cookies)
    auto_return(upload_sign, f"店铺{shop_abbr}：获取上传签名失败，无法继续执行")

    # 上传图片
    upload_image_json = upload_image(uid, headers, cookies, upload_pic_file_path, upload_sign)
    auto_return(upload_image_json, f"店铺{shop_abbr}：上传图片失败！")

    logger.info(f"店铺{shop_abbr}： 上传图片成功")
    img_url = upload_image_json["url"]

    return img_url


def split_task_list(task_list, chunk_size):
    """
    将任务列表拆分为指定大小的分片
    :param task_list: 原始任务列表（spu_sku_list）
    :param chunk_size: 每个分片的大小（10个/线程）
    :return: 分片后的列表
    """
    return [task_list[i:i + chunk_size] for i in range(0, len(task_list), chunk_size)]


def process_spu_chunk(uid, headers, cookies, spu_chunk, shop_abbr, query_json_list,
                      skc2spu, spu2skc, sleep_open, custom_fixed_upload_img, main_task_id=None):
    """
    单个线程处理的子函数：处理1个分片（最多10个SPU）
    修复：移除Queue入参，用本地列表存储成功/失败SPU，通过返回值传递给主线程
    """
    skc2spu_fixed = {}
    for k, v in skc2spu.items():
        try:
            skc2spu_fixed[int(k)] = v
        except (ValueError, TypeError):
            continue
    spu2skc_fixed = {}
    for k, v in spu2skc.items():
        try:
            spu2skc_fixed[int(k)] = v
        except (ValueError, TypeError):
            continue
    skc2spu = skc2spu_fixed
    spu2skc = spu2skc_fixed

    chunk_success = 0
    chunk_failed = 0
    # 本地列表存储当前分片的成功/失败SPU，替代原Queue操作
    success_spus = []
    failed_spus = []

    for spu_data in spu_chunk:
        spu_id = spu_data.get('spu_id')
        if not spu_id:
            logger.error(f"店铺{shop_abbr}： SPU_ID为空，跳过处理")
            chunk_failed += 1
            failed_spus.append(spu_id)
            continue

        try:
            if main_task_id:
                check_task_stopped(get_task_log_manager(), main_task_id)

            check_type_list = []
            # 合规信息上传流程
            pitu_img_url = compliance_upload(
                uid, headers, cookies, spu_id, shop_abbr,
                query_json_list, skc2spu, spu2skc
            )
            
            # 检查合规信息上传是否失败（图片验证失败等情况）
            if pitu_img_url is None:
                logger.warning(f"店铺{shop_abbr}：SPU={spu_id} 合规信息上传失败（可能是图片验证失败），跳过该SPU")
                chunk_failed += 1
                failed_spus.append(spu_id)
                continue
            
            # 在每个步骤后都检查任务是否被停止
            if main_task_id:
                check_task_stopped(get_task_log_manager(), main_task_id)

            if custom_fixed_upload_img:
                other_img_url_list = other_img_upload(headers, cookies, shop_abbr, uid)
            else:
                other_img_url_list = []
                
            # 在每个步骤后都检查任务是否被停止
            if main_task_id:
                check_task_stopped(get_task_log_manager(), main_task_id)

            # 异常图片上传
            for rule in spu_data['rule_check_result_list']:
                check_type_list.append(rule['check_type'])
            mark_img_url_list = mark_upload(
                headers, cookies, check_type_list, shop_abbr, uid
            )
            
            # 在每个步骤后都检查任务是否被停止
            if main_task_id:
                check_task_stopped(get_task_log_manager(), main_task_id)

            # 构造图片列表
            img_url_list = []
            if pitu_img_url and pitu_img_url.strip():
                img_url_list.append(pitu_img_url)
            if mark_img_url_list:
                valid_mark_urls = [url for url in mark_img_url_list if url and url.strip()]
                img_url_list.extend(valid_mark_urls)
            if other_img_url_list:
                valid_other_urls = [url for url in other_img_url_list if url and url.strip()]
                img_url_list.extend(valid_other_urls)
            if not img_url_list:
                logger.warning(f"店铺{shop_abbr}：SPU {spu_id} 图片列表为空，无法上传！")
                chunk_failed += 1
                failed_spus.append(spu_id)
                continue

            remarks = f"店铺{shop_abbr}：SPU={spu_id} 本次上传的图片列表 {img_url_list}"
            logger.trace(remarks)
            upload_img_urls = extract_img_url_list(spu_data, img_url_list=img_url_list)
            auto_return(upload_img_urls, "构造图片列表失败！")
            
            # 在每个步骤后都检查任务是否被停止
            if main_task_id:
                check_task_stopped(get_task_log_manager(), main_task_id)

            # 构造请求+发送绑定请求
            payload = build_real_pic_payload(spu_data, upload_img_urls)
            result_new = do_upload_new(uid, headers, cookies, payload)
            
            # 在每个步骤后都检查任务是否被停止
            if main_task_id:
                check_task_stopped(get_task_log_manager(), main_task_id)

            # 统计结果 + 本地列表存储SPU ID
            if result_new.get("success"):
                chunk_success += 1
                success_spus.append(spu_id)
                msg = f"店铺{shop_abbr}： SPU={spu_id} 上传实拍图操作执行成功"
                auto_print_logger(msg=msg, remarks=remarks, success_type="s",
                                  main_task_id=main_task_id)
            else:
                chunk_failed += 1
                failed_spus.append(spu_id)
                msg = f"店铺{shop_abbr}： SPU={spu_id} 上传实拍图操作执行失败（或Temu系统识别能力待建设）"
                auto_print_logger(msg=msg, remarks=remarks, success_type="e",
                                  main_task_id=main_task_id)

            # 随机休眠
            if sleep_open:
                sleep_time = random.uniform(0.5, 1.5)
                logger.trace(f"店铺{shop_abbr}： SPU={spu_id} 处理完成，随机休息{round(sleep_time, 2)}秒")
                time.sleep(sleep_time)

        except RuntimeError as e:
            logger.warning(f"店铺{shop_abbr}： 子线程检测到任务停止，正在退出 | SPU={spu_id}")
            chunk_failed += 1
            failed_spus.append(spu_id)
            return {"success": chunk_success, "failed": chunk_failed,
                    "success_spus": success_spus, "failed_spus": failed_spus}

        except Exception as e:
            chunk_failed += 1
            failed_spus.append(spu_id)

            if "403 Client Error" in str(e):
                logger.error(f"店铺{shop_abbr}：登录失效！", exc_info=True)
                db.execute_sql("update shops set connect_status = ? where headers = ? and cookies = ?",
                               params=("未连接", headers, cookies),
                               fetch="none")
                return {"success": chunk_success, "failed": chunk_failed,
                        "success_spus": success_spus, "failed_spus": failed_spus}
            else:
                logger.error(f"店铺{shop_abbr}：SPU={spu_id} 处理异常：{str(e)}", exc_info=True)

    # 返回包含成功/失败SPU列表的字典，供主线程收集
    return {"success": chunk_success, "failed": chunk_failed,
            "success_spus": success_spus, "failed_spus": failed_spus}





def batch_process_spu_page(uid, headers, cookies, spu_sku_list, shop_abbr, query_json_list,
                           skc2spu, spu2skc, sleep_open, page_num,
                           custom_fixed_upload_img, main_task_id, mall_id):
    """
    处理单页SPU：页内并行（3线程）
    修复：1. 移除子线程的Queue入参；2. 主线程从子线程返回值提取SPU列表，统一写入队列；3. 保持线程安全
    :return: 系统标准格式字典 {code, msg, data, remarks}
    """
    page_success = 0
    page_failed = 0
    # 主线程专属队列，仅主线程操作，保证线程安全
    page_success_queue = Queue()
    page_failed_queue = Queue()
    task_kwargs_dict = {}  # 存储每个task_id的参数，避免覆盖

    for tries in range(3):
        page_success = 0
        page_failed = 0
        task_ids = []
        task_kwargs_dict.clear()

        target_threads = upload_real_pic_concurrent-1
        total_spus = len(spu_sku_list)

        # 计算分片大小（原有逻辑不变）
        chunk_size = total_spus // target_threads if total_spus % target_threads == 0 else total_spus // target_threads + 1
        if total_spus % target_threads != 0 and total_spus % target_threads < target_threads // 2:
            chunk_size = total_spus // (target_threads - 1)
        logger.info(f"目标线程数: {target_threads}, 总SPU数: {total_spus}, 计算得到的分片大小: {chunk_size}")

        task_chunks = split_task_list(spu_sku_list, chunk_size=chunk_size)
        logger.info(
            f"店铺{shop_abbr}： 第{page_num}页共{total_spus}个SPU，拆分为{len(task_chunks)}个分片（目标{target_threads}线程），每个分片{chunk_size}个SPU")

        for chunk_idx, spu_chunk in enumerate(task_chunks):
            task_kwargs = {
                "uid": uid,
                "headers": headers,
                "cookies": cookies,
                "spu_chunk": spu_chunk,
                "shop_abbr": shop_abbr,
                "query_json_list": query_json_list,
                "skc2spu": skc2spu,
                "spu2skc": spu2skc,
                "sleep_open": sleep_open,
                # 核心修复：移除Queue相关入参，子线程不再操作队列
                "custom_fixed_upload_img": custom_fixed_upload_img,
                "main_task_id": main_task_id,
            }

            task_id = get_task_log_manager().add_task(
                target_func=process_spu_chunk, **task_kwargs,
                task_group=f"{shop_abbr}_上传实拍图",
                mall_id=mall_id,
                parent_task_id=main_task_id,
                is_main_task=0,
            )
            task_ids.append(task_id)
            task_kwargs_dict[task_id] = task_kwargs

        # 遍历每个任务结果，主线程统一处理队列写入
        for task_id in task_ids:
            chunk_result = get_task_log_manager().get_task_result(task_id, timeout=3000000)
            current_kwargs = task_kwargs_dict.get(task_id, {})
            if chunk_result and chunk_result.get("code") == 1:
                # 从子线程返回值中提取成功/失败SPU列表
                data = chunk_result.get("data", {})
                page_success += data.get("success", 0)
                page_failed += data.get("failed", 0)
                # 主线程统一写入队列，保证线程安全
                for spu_id in data.get("success_spus", []):
                    page_success_queue.put(spu_id)
                for spu_id in data.get("failed_spus", []):
                    page_failed_queue.put(spu_id)
            else:
                # 任务执行异常，所有分片SPU计入失败
                failed_count = len([item for item in current_kwargs.get('spu_chunk', []) if item.get('spu_id')])
                page_failed += failed_count
                failed_spus = [item.get('spu_id') for item in current_kwargs.get('spu_chunk', []) if item.get('spu_id')]
                for spu_id in failed_spus:
                    page_failed_queue.put(spu_id)
                logger.warning(f"店铺{shop_abbr}：任务{task_id}执行异常或无返回，计入{failed_count}个失败")

        break

    # 主线程提取队列数据，转普通列表（原有逻辑不变）
    page_success_spus = []
    page_failed_spus = []
    while not page_success_queue.empty():
        page_success_spus.append(page_success_queue.get())
    while not page_failed_queue.empty():
        page_failed_spus.append(page_failed_queue.get())

    page_success_spus = list(set(page_success_spus))
    page_failed_spus = list(set(page_failed_spus))

    # 系统标准返回格式（原有逻辑不变）
    return {
        "code": 1,
        "msg": f"店铺{shop_abbr}：第{page_num}页SPU处理完成",
        "data": {
            "page_success": page_success,
            "page_failed": page_failed,
            "page_success_spus": page_success_spus,
            "page_failed_spus": page_failed_spus,
        },
        "remarks": f"店铺{shop_abbr}：第{page_num}页处理结果 - 成功{page_success}条，失败{page_failed}条 | 实际成功SPU数：{len(page_success_spus)}"
    }





def init_record_table(uid, shop_abbr):
    """
    初始化record表：若uid无对应记录则插入（空列表初始值），保证后续查询/更新有基础记录
    :param uid: 唯一标识（主键/唯一键）
    :param shop_abbr: 店铺缩写（仅用于日志）
    :return: bool - 初始化成功/失败
    """
    try:
        # 先查询是否存在记录（避免重复插入）
        exist_data = db.execute_sql(
            "select 1 from record WHERE uid = ?",
            params=[uid],
            fetch="fetch_one"
        )
        if exist_data:
            # logger.info(f"店铺{shop_abbr}：uid={uid}已存在record记录，无需初始化")
            return True

        # 无记录则插入：upload_pic_all初始化为空列表，update_time为当前时间
        insert_sql = """
                     INSERT INTO record (uid, upload_pic_all, update_time)
                     VALUES (?, ?, datetime('now', '+8 hours')) 
                     """
        db.execute_sql(
            insert_sql,
            params=[uid, "[]"],  # 空列表以字符串形式存储，与原有格式一致
            fetch="none"
        )
        logger.info(f"店铺{shop_abbr}：uid={uid}初始化record记录成功（空列表）")
        return True
    except Exception as e:
        logger.error(f"店铺{shop_abbr}：uid={uid}初始化record记录失败：{str(e)}", exc_info=True)
        return False


def upsert_record_spu_list(uid, shop_abbr, final_spu_list):
    """
    数据库UPSERT操作：更新record表，若无记录则自动插入（兜底逻辑）
    :param uid: 唯一标识
    :param shop_abbr: 店铺缩写（仅用于日志）
    :param final_spu_list: 待入库的最终SPU列表
    :return: bool - 操作成功/失败
    """
    try:
        # 第一步：尝试更新（基于uid匹配）
        update_sql = """
                     UPDATE record
                     SET upload_pic_all = ?, 
                         update_time    = datetime('now', '+8 hours')
                     WHERE uid = ? 
                     """
        # 执行更新并获取影响行数（需确认db.execute_sql支持返回影响行数，若不支持则注释rowcount相关）
        rowcount = db.execute_sql(
            update_sql,
            params=[str(final_spu_list), uid],
            fetch="none"
        )

        if rowcount > 0:
            logger.info(f"店铺{shop_abbr}：uid={uid}更新record记录成功，影响{rowcount}行")
            return True

        # 第二步：更新无影响（无记录），执行插入
        insert_sql = """
                     INSERT INTO record (uid, upload_pic_all, update_time)
                     VALUES (?, ?, datetime('now', '+8 hours')) \
                     """
        db.execute_sql(
            insert_sql,
            params=[uid, str(final_spu_list)],
            fetch="none"
        )
        logger.info(f"店铺{shop_abbr}：uid={uid}无record记录，自动插入新记录成功")
        return True
    except Exception as e:
        logger.error(f"店铺{shop_abbr}：uid={uid}UPSERT record记录失败：{str(e)}", exc_info=True)
        return False



def get_original_sql_spu_list(uid, shop_abbr):
    """
    纯查询函数：从数据库读取upload_pic_all字段，解析为原始列表（无任何修改）
    新增：查询前自动初始化，无记录则插入空列表记录
    :param uid: 唯一标识
    :param shop_abbr: 店铺缩写（仅用于日志）
    :return: 数据库解析后的原始列表（兜底空列表）
    """
    try:
        # ========== 新增核心代码：查询前初始化，无记录则插入 ==========
        init_record_table(uid, shop_abbr)
        # ==============================================================

        record_data = db.execute_sql(
            "select upload_pic_all from record WHERE uid = ?",
            params=[uid],
            fetch="fetch_one"
        )
        # 校验记录/字段是否存在（经过初始化，此处基本不会触发，仅做终极兜底）
        if not record_data or "upload_pic_all" not in record_data:
            logger.warning(f"店铺{shop_abbr}：初始化后仍未查询到uid={uid}的record记录，返回空列表")
            return []

        sql_spu_id_list_str = record_data["upload_pic_all"]
        # 校验字段值是否为空/空列表
        if not sql_spu_id_list_str or sql_spu_id_list_str.strip() in ["", "[]"]:
            logger.info(f"店铺{shop_abbr}：数据库upload_pic_all字段为空，返回空列表")
            return []

        # 安全解析并校验类型
        original_list = ast.literal_eval(sql_spu_id_list_str)
        if not isinstance(original_list, list):
            logger.warning(f"店铺{shop_abbr}：数据库upload_pic_all非列表格式，返回空列表")
            return []

        logger.info(f"店铺{shop_abbr}：成功查询数据库原始SPU列表，共{len(original_list)}条数据")
        return original_list.copy()  # 浅拷贝，避免外部修改数据库原始值

    except Exception as e:
        logger.error(f"店铺{shop_abbr}：查询数据库原始SPU列表失败：{str(e)}", exc_info=True)
        return []  # 异常兜底空列表


def extend_final_spu_list(original_sql_spu_list, page_success_spus):
    """
    纯处理函数：将当前页成功SPU列表扁平追加到原始列表，做去重+排序（无数据库操作）
    :param original_sql_spu_list: 数据库原始SPU列表（来自get_original_sql_spu_list）
    :param page_success_spus: 当前页成功SPU列表
    :return: 处理后的最终扁平列表（兜底空列表）
    """
    try:
        # 基础校验：确保两个参数都是列表，非列表则转为空列表
        original_list = original_sql_spu_list if isinstance(original_sql_spu_list, list) else []
        current_page_list = page_success_spus if isinstance(page_success_spus, list) else []

        # 过滤空的当前页列表，避免无意义追加
        if len(current_page_list) == 0:
            logger.info("当前页成功SPU列表为空，无需追加，直接返回原始列表")
            final_list = original_list.copy()
        else:
            # 核心逻辑：扁平追加（extend），避免嵌套
            final_list = original_list.copy()
            final_list.extend(current_page_list)
            logger.info(f"成功追加当前页SPU列表，原始{len(original_list)}条+当前{len(current_page_list)}条")

        # 去重+排序（可选，根据业务需求注释/删除）
        final_list = list(set(final_list))  # 去重
        final_list.sort()  # 正序排列

        logger.info(f"SPU列表处理完成，最终去重排序后共{len(final_list)}条数据")
        return final_list

    except Exception as e:
        logger.error(f"处理SPU列表追加失败：{str(e)}", exc_info=True)
        # 异常时返回原始列表（兜底，避免数据丢失）
        return original_sql_spu_list if isinstance(original_sql_spu_list, list) else []


def final_upload_real_pic(
        headers: dict, cookies: dict, uid: str, input_check_type_list: list,
        input_rapid_screen_status_list: list, shop_abbr: str,
        sleep_open: bool = True, input_spu_id_list: list[int] = None,
        black_word_type_list: list[int] = None, goods_status_list: list[int] = None,
        max_global_retry: int = 5, custom_fixed_upload_img: bool = False,
        mall_id=None, main_task_id=None
) -> dict:
    """
    上传实拍图全流程（最终版：基于总页数的分页控制，页数串行，页内并行）
    """
    # 初始化参数
    return_dtm_json = determine_upload_params(shop_abbr, input_check_type_list,
                                              input_rapid_screen_status_list,
                                              input_spu_id_list=input_spu_id_list)
    all_rerun = return_dtm_json.get("all_rerun")
    total_modified = 0
    total_failed = 0
    _result = {}
    global_retry_count = 0
    thrown_error = ""

    if not sleep_open:
        max_global_retry += 30

    while global_retry_count < max_global_retry:
        try:
            # ========== 第一步：初始化 - 获取第1页数据+计算总页数 ==========
            # 指定SPU时强制只查第1页
            init_page_num = 1 if (input_spu_id_list and len(input_spu_id_list) > 0) else 1
            # 首次请求：获取第1页数据+总条数
            first_response = get_real_picture_list(
                uid, headers, cookies,
                page_num=init_page_num,
                check_type_list=input_check_type_list,
                rapid_screen_status_list=input_rapid_screen_status_list,
                input_spu_id_list=input_spu_id_list,
                black_word_type_list=black_word_type_list,
                goods_status_list=goods_status_list,
                main_task_id=main_task_id
            )
            auto_return(first_response, "第1页订单列表获取失败")

            # 解析首次请求数据
            spu_data_list = extract_real_pic_list_json(data_json=first_response['data'])
            total = spu_data_list.get('total', 0)
            max_page = (total + TEMU_PAGE_SIZE - 1) // TEMU_PAGE_SIZE if total > 0 else 0

            # 日志：关键分页信息
            logger.info(f"店铺{shop_abbr}：Temu显示总数（可能与实际数量不符）={total} | 每页大小={TEMU_PAGE_SIZE} | 总页数={max_page}")

            # 无数据直接退出
            if max_page == 0:
                logger.info(f"店铺{shop_abbr}：无待处理数据，直接退出")
                _result = {
                    "code": 1,
                    "msg": f"店铺{shop_abbr}：上传图片执行完成（无数据）",
                    "data": None,
                    "remarks": "成功 0 条，失败 0 条"
                }
                auto_print_logger(_result, success_type="s", main_task_id=main_task_id)
                return _result

            # ========== 第二步：按总页数循环处理（核心优化：用for替代while） ==========
            for page in range(1, max_page + 1):
                # 检查任务是否被停止
                if main_task_id:
                    check_task_stopped(get_task_log_manager(), main_task_id)

                logger.info(f"店铺{shop_abbr}：开始处理第{page}页")

                # 复用首次请求的第1页数据，避免重复调用
                if page == 1:
                    real_picture_list = first_response
                else:
                    # 非第1页，正常请求
                    real_picture_list = get_real_picture_list(
                        uid, headers, cookies,
                        page_num=page,
                        check_type_list=input_check_type_list,
                        rapid_screen_status_list=input_rapid_screen_status_list,
                        input_spu_id_list=input_spu_id_list,
                        black_word_type_list=black_word_type_list,
                        goods_status_list=goods_status_list,
                        main_task_id=main_task_id
                    )
                    auto_return(real_picture_list, f"第{page}页订单列表获取失败")

                # 解析当前页数据
                spu_data_list = extract_real_pic_list_json(data_json=real_picture_list['data'])
                spu_sku_list = spu_data_list.get('data', [])

                # 关键日志：恢复分页数据监控
                logger.info(f"第{page}页 | total={spu_data_list.get('total', 'N/A')} | data_count={len(spu_sku_list)}")

                # 总页数范围内的空页：仅警告，继续下一页
                if not spu_sku_list:
                    logger.warning(f"店铺{shop_abbr}：第{page}页无数据（总页数范围内），跳过")
                    continue

                # ========== 原有业务逻辑（完全保留） ==========
                # 提取所有spu skc id_list
                spu_id_list = [spu_data.get('spu_id') for spu_data in spu_sku_list]
                original_sql_spu_list = get_original_sql_spu_list(uid, shop_abbr)

                original_sql_spu_set = set(original_sql_spu_list)
                filtered_spu_id_list = [
                    spu_id for spu_id in spu_id_list
                    if spu_id is not None and spu_id not in original_sql_spu_set
                ]
                filtered_spu_id_list = list(dict.fromkeys(filtered_spu_id_list))
                logger.info(
                    f"SPU列表过滤完成 | 待处理总数：{len(spu_id_list)} | 已成功排除：{len(spu_id_list) - len(filtered_spu_id_list)} | 最终待处理：{len(filtered_spu_id_list)}")

                # 一次性查询所有spu skc id 减少重复请求时间
                skc2spu, spu2skc = spu_id_list_2_skc_id_list(uid, headers, cookies, shop_abbr, spu_id_list)

                if not spu2skc or not skc2spu:
                    logger.error(f"店铺{shop_abbr}： 获取spu_id列表失败")
                if not filtered_spu_id_list:
                    logger.info(f"店铺{shop_abbr}：第{page}页无未处理SPU，直接跳至下一页")
                    continue

                # 获取合规订单查询结果
                query_json_list = get_query_compliance_order(shop_abbr, headers, cookies, spu_id_list, uid)['data']

                batch_result = batch_process_spu_page(
                    uid=uid,
                    headers=headers,
                    cookies=cookies,
                    spu_sku_list=spu_sku_list,
                    shop_abbr=shop_abbr,
                    query_json_list=query_json_list,
                    skc2spu=skc2spu,
                    spu2skc=spu2skc,
                    sleep_open=sleep_open,
                    page_num=page,
                    custom_fixed_upload_img=custom_fixed_upload_img,
                    mall_id=mall_id,
                    main_task_id=main_task_id,
                )

                if batch_result and batch_result.get("code") == 1:
                    batch_data = batch_result.get("data", {})
                    total_modified += batch_data.get("page_success", 0)
                    total_failed += batch_data.get("page_failed", 0)
                    page_success_spus = batch_data.get("page_success_spus", [])
                    page_failed_spus = batch_data.get("page_failed_spus", [])
                else:
                    # 整页失败处理
                    logger.error(f"店铺{shop_abbr}：第{page}页处理返回异常：{batch_result}")
                    total_failed += len(filtered_spu_id_list)
                    page_success_spus = []
                    page_failed_spus = filtered_spu_id_list

                logger.info(f"店铺{shop_abbr}： 第{page}页处理完成 | 本页统计：")
                logger.info(f"✅ 本页成功SPU数：{len(page_success_spus)} | 成功SPU列表：{page_success_spus}")
                if page_failed_spus:
                    logger.info(f"❌ 本页失败SPU数：{len(page_failed_spus)} | 失败SPU列表：{page_failed_spus}")

                success_spu_show = page_success_spus[:3] + ['...'] if len(
                    page_success_spus) > 3 else page_success_spus
                remarks = f"店铺{shop_abbr}： 成功 {total_modified} 条，失败 {total_failed} 条，成功SPU列表：{success_spu_show}，失败列表 {page_failed_spus}"

                # 指定SPU场景：处理完第1页直接退出
                if input_spu_id_list and len(input_spu_id_list) > 0:
                    _result = {
                        "code": 1,
                        "msg": f"店铺{shop_abbr}： 指定SPU上传图片执行完成",
                        "data": None,
                        "remarks": remarks
                    }
                    auto_print_logger(_result, success_type="s", main_task_id=main_task_id)
                    return _result

                # 记录成功SPU到数据库
                record_upload_pic_spu_list = config_manager.get_or_set_config("record_upload_pic_spu_list", "否")
                if record_upload_pic_spu_list == "是":
                    logger.info("===== 开始记录成功SPU列表到数据库 =====")
                    original_sql_spu_list = get_original_sql_spu_list(uid, shop_abbr)
                    final_spu_list = extend_final_spu_list(original_sql_spu_list, page_success_spus)
                    if final_spu_list != []:
                        upsert_success = upsert_record_spu_list(uid, shop_abbr, final_spu_list)
                        if upsert_success:
                            logger.info(
                                f"原始列表条数：{len(original_sql_spu_list)} | 当前页追加：{len(page_success_spus)} | 最终入库：{len(final_spu_list)}")
                            logger.info("===== 记录SPU列表到数据库成功 =====")
                    else:
                        logger.warning(f"店铺{shop_abbr}：当前页成功SPU列表为空，执行空列表UPSERT兜底")
                        init_record_table(uid, shop_abbr)

            # ========== 所有页数处理完成：正常退出 ==========
            logger.info(f"店铺{shop_abbr}：所有{max_page}页处理完成，总成功{total_modified}条，总失败{total_failed}条")
            _result = {
                "code": 1,
                "msg": f"店铺{shop_abbr}：上传图片执行完成",
                "data": None,
                "remarks": f"成功 {total_modified} 条，失败 {total_failed} 条"
            }
            auto_print_logger(_result, success_type="s", main_task_id=main_task_id)
            return _result

        except AutoReturnError as e:
            logger.error(f"店铺{shop_abbr}： 检测到异常：{e.result['msg']}")
            global_retry_count += 1
            thrown_error = str(e)

        except RuntimeError as e:
            logger.warning(f"店铺{shop_abbr}： 任务被手动停止，退出执行")
            _result = {
                "code": -2,
                "msg": f"店铺{shop_abbr}： 任务被手动停止",
                "data": None,
                "remarks": f"停止原因：{str(e)} | 已处理成功{total_modified}条，失败{total_failed}条"
            }
            auto_print_logger(_result, success_type="w", main_task_id=main_task_id)
            return _result

        except Exception as e:
            _result = {"code": -1, "msg": f"店铺{shop_abbr}： 执行出错，尝试重新执行", "data": None,
                       "remarks": str(e)}
            thrown_error = str(e)
            auto_print_logger(_result, success_type="w", main_task_id=main_task_id)
            global_retry_count += 1

    # 达到最大重试次数
    _result = {"code": -1, "msg": f"店铺{shop_abbr}： 异常次数达到上限，程序退出！", "data": None,
               "remarks": f"异常{thrown_error}"}
    auto_print_logger(_result, success_type="error", main_task_id=main_task_id)
    return _result
