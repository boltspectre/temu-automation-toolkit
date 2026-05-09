from loguru import logger

from temu_modules.temu_function.finance_excel import auto_create_export_task, \
    get_export_history_page, extract_export_history_page, get_date_range_timestamps, get_download_export_params, \
    do_download_export
from utils.TemuBase import get_shop_info_db
from utils.url_downloader import create_thread_safe_downloader, download_worker


def get_global_excel_urls_only(uid, months_list):
    """
    只获取全球区财务明细下载链接，不执行下载

    return {
        "eu": [(url, month), ...],
        "us": [(url, month), ...],
        "global": [(url, month), ...],
        "seller": [(url, month), ...]
    }
    """
    tries = 0
    max_tries = 3
    while tries < max_tries:
        try:
            shop_info = get_shop_info_db(uid)

            if not shop_info or 'headers' not in shop_info or 'cookies' not in shop_info:
                logger.error(f"店铺{uid}的登录信息不完整")
                return None

            export_history_page = get_export_history_page(uid, shop_info["headers"], shop_info["cookies"], task_type=19)

            if not export_history_page or export_history_page.get("code") != 1:
                logger.error(f"获取导出历史页面失败: {export_history_page}")
                raise Exception("获取导出历史页面失败")

            extract_export_history_page_list = extract_export_history_page(export_history_page)

            select_time_dict = {}
            for month in months_list:
                begin_ms, end_ms = get_date_range_timestamps(month)
                time_tuple = (begin_ms, end_ms)
                select_time_dict[time_tuple] = month

            official_history_dict = {}
            for item in extract_export_history_page_list:
                time_tuple = (item["begin_time"], item["end_time"])
                official_history_dict[time_tuple] = item

            result = _get_download_excel_urls(uid, select_time_dict, official_history_dict, shop_info)
            return result

        except Exception as e:
            tries += 1
            shop_abbr = uid
            if 'shop_info' in locals() and shop_info and 'shop_abbr' in shop_info:
                shop_abbr = shop_info['shop_abbr']
            logger.error(f"⚠️ 店铺{shop_abbr}，选择月份：{months_list}，第{tries}次重试（异常：{e}）")

            if tries >= max_tries:
                logger.error(f"❌ 店铺{shop_abbr}重试{max_tries}次后仍失败")
                return None

            import time
            time.sleep(2)

    return None


def _get_download_excel_urls(uid, select_time_dict: dict, official_history_dict: dict, shop_info: dict):
    """获取各区域下载链接（内部函数）"""
    regions = ["eu", "us", "global", "卖家中心"]

    cookies = None
    eu_urls = []
    us_urls = []
    global_urls = []
    seller_urls = []
    should_break = False

    for region in regions:
        if should_break:
            break

        for select_time_range in select_time_dict:
            month = select_time_dict[select_time_range]
            matched_item = official_history_dict.get(select_time_range)

            if matched_item:
                if region == "卖家中心":
                    download_export_resp = do_download_export(
                        uid,
                        shop_info["headers"],
                        shop_info["cookies"],
                        matched_item["download_id"],
                        "卖家中心"
                    )

                    try:
                        file_url = download_export_resp["data"]["result"]["fileUrl"]
                        seller_urls.append((file_url, month))
                    except KeyError:
                        logger.error(f"卖家中心下载链接获取失败: {download_export_resp}")

                else:
                    if region == "eu":
                        cookies = shop_info["cookies_eu"]
                    elif region == "us":
                        cookies = shop_info["cookies_us"]
                    elif region == "global":
                        cookies = shop_info["cookies"]

                    if not cookies:
                        logger.error(f"店铺{uid}的{region}cookies为空，无法获取下载参数")
                        continue

                    export_result = get_download_export_params(uid, shop_info["headers"], cookies,
                                                               matched_item["query_params"], region)

                    if export_result and export_result.get("data", {}).get("result"):
                        download_id = int(export_result["data"]["result"])
                        download_url = do_download_export(uid, headers=shop_info["headers"], cookies=cookies,
                                                          download_id=download_id, region=region)

                        # 检查返回值是否成功，再提取 fileUrl
                        if download_url and download_url.get("code") == 1:
                            try:
                                file_url = download_url['data']['result']['fileUrl']
                                if region == "eu":
                                    eu_urls.append((file_url, month))
                                elif region == "us":
                                    us_urls.append((file_url, month))
                                elif region == "global":
                                    global_urls.append((file_url, month))
                            except (KeyError, TypeError) as e:
                                logger.error(f"地区 {region} 提取下载链接失败: {e}, 返回数据: {download_url}")
                        else:
                            logger.error(f"地区 {region} 获取直链失败: {download_url}")

                    else:
                        logger.warning(f"地区 {region} 获取参数失败")

            else:
                logger.info(f"检测到有未导出的时间范围财务明细 ({select_time_range})，正在尝试导出..")

                export_output = auto_create_export_task(uid, shop_info["headers"], shop_info["cookies"],
                                                        select_time_dict, official_history_dict)

                if not export_output:
                    logger.info("导出数量超官方限制")
                    should_break = True
                    break
                else:
                    should_break = True
                    break

    return {
        "eu": eu_urls,
        "us": us_urls,
        "global": global_urls,
        "seller": seller_urls
    }



def download_all_caiwu_excel(uid, months_list):
    result = get_global_excel_urls_only(uid, months_list=months_list)

    if not result:
        logger.error("获取下载链接失败")
        exit(1)

    print(result)

    print("\n" + "=" * 30)
    print("🔗 下载链接汇总")
    print("=" * 30)

    print(f"\n🇪🇺 EU 地区链接 ({len(result.get('eu', []))}个):")
    for url, month in result.get("eu", []):
        print(f"[{month}] {url}")

    print(f"\n🇺🇸 US 地区链接 ({len(result.get('us', []))}个):")
    for url, month in result.get("us", []):
        print(f"[{month}] {url}")

    print(f"\n🌐 Global 地区链接 ({len(result.get('global', []))}个):")
    for url, month in result.get("global", []):
        print(f"[{month}] {url}")

    print(f"\n🏪 卖家中心链接 ({len(result.get('seller', []))}个):")
    for url, month in result.get("seller", []):
        print(f"[{month}] {url}")

    print("=" * 30 + "\n")

    shop_info = get_shop_info_db(uid)
    if not shop_info:
        logger.error(f"店铺{uid}信息获取失败")
        exit(1)

    logger.info("开始下载财务明细文件...")

    region_cookies_map = {
        "eu": shop_info.get("cookies_eu"),
        "us": shop_info.get("cookies_us"),
        "global": shop_info.get("cookies"),
        "seller": shop_info.get("cookies")
    }

    region_name_map = {
        "eu": "eu",
        "us": "us",
        "global": "global",
        "seller": "卖家中心"
    }

    for region, urls_list in result.items():
        cookies = region_cookies_map.get(region)
        region_name = region_name_map.get(region, region)

        if not cookies:
            logger.warning(f"店铺{uid}的{region_name}cookies为空，跳过下载")
            continue

        if not urls_list:
            logger.info(f"{region_name}地区没有需要下载的文件")
            continue

        logger.info(f"开始下载{region_name}地区文件，共{len(urls_list)}个")

        safe_downloader = create_thread_safe_downloader(headers=shop_info['headers'], cookies=cookies)

        for url, month in urls_list:
            save_dir = f"./配置文件_结算导出/{shop_info['shop_abbr']}/{month}"

            task_kwargs = {
                "downloader": safe_downloader,
                "url": url,
                "save_folder": save_dir,
                "custom_filename": f"导出原表_{region_name}_{month}.xlsx"
            }
            download_worker(**task_kwargs)

    logger.info("所有文件下载完成")


def check_download_files(shop_abbr, month, type: str = "all"):
    """
    校验下载文件完整性
    """
    import os
    target_dir = fr"配置文件_结算导出\{shop_abbr}\{month}"

    if type == "seller":
        check_files = [f"导出原表_卖家中心_{month}.xlsx"]
    elif type == "global":
        # global 类型只检查 global 文件
        check_files = [f"导出原表_global_{month}.xlsx"]
    elif type == "all":
        # all 类型只检查 eu、us、global 文件，不检查卖家中心
        check_files = [f"导出原表_eu_{month}.xlsx", f"导出原表_us_{month}.xlsx", f"导出原表_global_{month}.xlsx"]
    else:
        check_files = [f"导出原表_卖家中心_{month}.xlsx", f"导出原表_eu_{month}.xlsx", f"导出原表_us_{month}.xlsx",
                       f"导出原表_global_{month}.xlsx"]

    logger.info(f"校验下载文件完整性...")
    for file_name in check_files:
        file_path = os.path.join(target_dir, file_name)
        if os.path.exists(file_path):
            logger.info(f"✅ 存在文件：{file_name}（{os.path.abspath(file_path)}）")
        else:
            logger.error(f"❌ 缺失文件：{file_name}")
            return {"code": -1, "msg": f"缺失文件：{file_name}"}

    logger.info(f"所选导出文件已全部存在")
    return {"code": 1, "msg": "文件已全部存在"}


def download_all_caiwu_excel_complete(uid, months_list, max_retries=5, check_type="all"):
    """
    自动下载财务明细文件并确保所有文件完整下载
    
    Args:
        uid: 店铺 ID
        months_list: 需要下载的月份列表，如 ["2025.01", "2025.04"]
        max_retries: 最大重试次数，默认 5 次
        check_type: 文件校验类型，可选值：
                   - "all": 检查 eu、us、global（默认）
                   - "seller": 只检查卖家中心
                   - "global": 只检查 global
                   - "other": 检查所有类型（eu、us、global、卖家中心）
    
    Returns:
        bool: 是否成功下载所有文件
    """
    import time
    import os
    
    shop_info = get_shop_info_db(uid)
    if not shop_info:
        logger.error(f"店铺{uid}信息获取失败")
        return False
    
    shop_abbr = shop_info.get('shop_abbr', uid)
    
    logger.info(f"🚀 开始执行完整下载任务：店铺{shop_abbr}，月份{months_list}，最大重试次数{max_retries}")
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"{'='*60}")
            logger.info(f"第 {attempt}/{max_retries} 次尝试下载")
            logger.info(f"{'='*60}")
            
            # 执行下载
            download_all_caiwu_excel(uid, months_list)
            
            # 等待下载完成
            logger.info("⏳ 等待 3 秒确保所有下载完成...")
            time.sleep(3)
            
            # 校验所有月份的文件
            all_files_complete = True
            missing_files = []
            
            for month in months_list:
                check_result = check_download_files(shop_abbr, month, type=check_type)
                if check_result["code"] != 1:
                    all_files_complete = False
                    missing_files.append(month)
            
            if all_files_complete:
                logger.info(f"\n{'='*60}")
                logger.info(f"✅ 所有文件已成功下载！店铺：{shop_abbr}，月份：{months_list}")
                logger.info(f"{'='*60}\n")
                return True
            else:
                logger.warning(f"\n⚠️ 以下月份文件缺失：{missing_files}")
                
                if attempt < max_retries:
                    logger.info(f"⏳ 2 秒后进行第 {attempt + 1} 次重试...\n")
                    time.sleep(2)
                else:
                    logger.error(f"\n{'='*60}")
                    logger.error(f"❌ 达到最大重试次数{max_retries}，仍有文件未下载成功")
                    logger.error(f"缺失文件的月份：{missing_files}")
                    logger.error(f"{'='*60}\n")
                    return False
                    
        except Exception as e:
            logger.error(f"⚠️ 第{attempt}次下载过程中出现异常：{e}")
            
            if attempt < max_retries:
                logger.info(f"⏳ 2 秒后进行第 {attempt + 1} 次重试...\n")
                time.sleep(2)
            else:
                logger.error(f"\n{'='*60}")
                logger.error(f"❌ 达到最大重试次数{max_retries}，下载失败")
                logger.error(f"错误信息：{e}")
                logger.error(f"{'='*60}\n")
                return False
    
    return False


if __name__ == '__main__':
    uid = "1"
    shop_info = get_shop_info_db(uid)
    months_list = ["2025.01", "2025.04", "2025.05", "2025.06"]
    
    # 方式一：使用新的完整下载函数（推荐）
    # 自动重试最多 5 次，确保所有文件下载完成
    success = download_all_caiwu_excel_complete(uid, months_list, max_retries=5, check_type="all")
    
    if success:
        logger.info("🎉 下载任务成功完成！")
    else:
        logger.error("💥 下载任务失败，请检查日志")
    
    # 方式二：手动调用原始函数（不推荐，无重试保障）
    # download_all_caiwu_excel(uid, months_list)
    # check_download_files(shop_info["shop_abbr"], "2025.01")
