import os
import threading
from threading import Lock
from urllib.parse import unquote

import requests
from loguru import logger

from config.start_config import MAIN_TASK_MANAGER
from temu_modules.temu_function.finance_excel import do_download_export, auto_create_export_task
from utils.TemuBase import get_shop_info_db


# --- 函数1: 创建一个线程安全的下载器 (已修改) ---
def create_thread_safe_downloader(headers: dict, cookies: dict):
    """
    创建并返回一个包含下载逻辑和锁的闭包。
    """
    file_lock = Lock()

    # 2. 定义一个内部函数，增加 custom_filename 参数
    def download(url: str, save_folder: str, custom_filename: str = None) -> bool:
        """
        线程安全的文件下载函数。

        :param url: 下载链接。
        :param save_folder: 保存文件夹。
        :param custom_filename: (可选) 自定义的文件名。如果提供，将优先使用。
        :param cookies: (可选) 请求时携带的cookies。
        :param headers: (可选) 请求时携带的headers。
        :return: 如果下载成功返回True，否则返回False。
        """
        try:
            os.makedirs(save_folder, exist_ok=True)

            response = requests.get(url, stream=True, cookies=cookies, headers=headers)
            response.raise_for_status()

            # 3. 【核心逻辑】判断是否使用自定义文件名
            if custom_filename:
                filename = custom_filename
                print(f"ℹ️ 线程 {threading.current_thread().name} 将使用自定义文件名: {filename}")
            else:
                # 如果没有提供自定义文件名，则从响应头解析
                filename = "unknown_file"
                if "Content-Disposition" in response.headers:
                    cd = response.headers["Content-Disposition"]
                    if 'filename=' in cd:
                        filename = cd.split("filename=")[-1].strip('"')
                        filename = unquote(filename)

            save_path = os.path.join(save_folder, filename)

            with file_lock:
                print(f"🔒 线程 {threading.current_thread().name} 获得锁，准备写入: {filename}")

                if os.path.exists(save_path):
                    print(f"ℹ️ 文件 {filename} 已存在，线程 {threading.current_thread().name} 已跳过。")
                    return True

                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                print(f"✅ 线程 {threading.current_thread().name} 下载完成: {filename}")
                print(f"🔓 线程 {threading.current_thread().name} 释放锁。")

            return True

        except Exception as e:
            print(f"❌ 线程 {threading.current_thread().name} 下载失败: {e}")
            return False

    return download


# --- 函数2: 线程要执行的工作任务 (已修改) ---
def download_worker(downloader, url, save_folder, custom_filename=None):
    """
    每个线程执行的任务。
    它接收一个已经创建好的下载器实例和可选的文件名。
    """
    # 将 custom_filename 传递给 downloader
    downloader(url=url, save_folder=save_folder, custom_filename=custom_filename)



def download_seller_excel(uid, select_time_dict, official_history_dict, shop_info):
    seller_download_list = []
    for select_time_range in select_time_dict:
        if select_time_range in official_history_dict:
            # 执行下载 卖家中心财务明细
            month = select_time_dict[select_time_range]
            matched_item = official_history_dict[select_time_range]
            download_export_resp = do_download_export(uid, shop_info["headers"], shop_info["cookies"],
                                                      matched_item["download_id"], "卖家中心")

            seller_download_list.append((download_export_resp["data"]["result"]["fileUrl"], month))

        else:
            logger.info("检测到有未导出的时间范围财务明细，正在导出..")
            export_output = auto_create_export_task(uid, shop_info["headers"], shop_info["cookies"], select_time_dict,
                                                    official_history_dict)

            if not export_output:
                logger.info("导出数量超官方限制")
            break

    logger.info("开始下载卖家中心财务明细...")
    for download_item in seller_download_list:
        print(download_item)
    safe_downloader = create_thread_safe_downloader(headers=shop_info['headers'], cookies=shop_info['cookies'])
    for url, month in seller_download_list:
        save_dir = f"./配置文件_结算导出/{shop_info['shop_abbr']}/{month}"

        task_kwargs = {
            "downloader": safe_downloader,
            "url": url,
            "save_folder": save_dir,
            "custom_filename": f"导出原表_卖家中心_{month}.xlsx"
        }
        download_worker(**task_kwargs)


# --- 主程序：如何使用这两个函数 (已修改) ---
if __name__ == "__main__":
    uid = "130197459937923072"
    shop_info = get_shop_info_db(uid)
    safe_downloader = create_thread_safe_downloader(shop_info['headers'], shop_info['cookies'])

    # 2. 准备下载任务 (使用元组列表，包含URL和可选的文件名)
    #    (url, custom_filename)
    download_tasks = [
        ('https://seller.kuajingmaihuo.com/labor-tag/FundDetail-1766992214256-ccd0.xlsx?signB=q-sign-algorithm%3Dsha1%26q-ak%3D3e28gqPmHQPY1BrIsZZfbu66YfzYfmyj%26q-sign-time%3D1767056445%3B1767057045%26q-key-time%3D1767056445%3B1767057045%26q-header-list%3D%26q-url-param-list%3D%26q-signature%3D5e172f44064a395185a9cbd46206ddbde99a6ddf',
         '2025.10'),
        ('https://seller.kuajingmaihuo.com/labor-tag/FundDetail-1766992302632-7a6f.xlsx?signB=q-sign-algorithm%3Dsha1%26q-ak%3D3e28gqPmHQPY1BrIsZZfbu66YfzYfmyj%26q-sign-time%3D1767056445%3B1767057045%26q-key-time%3D1767056445%3B1767057045%26q-header-list%3D%26q-url-param-list%3D%26q-signature%3Dd86b297ee9c540a07835809ab7bd2ac1b0c6c16b',
         '2025.2'),
        ('https://seller.kuajingmaihuo.com/labor-tag/FundDetail-1766992303076-8dad.xlsx?signB=q-sign-algorithm%3Dsha1%26q-ak%3D3e28gqPmHQPY1BrIsZZfbu66YfzYfmyj%26q-sign-time%3D1767056446%3B1767057046%26q-key-time%3D1767056446%3B1767057046%26q-header-list%3D%26q-url-param-list%3D%26q-signature%3D3a69600e571e31a3e0862a74e04f9ac7963d8248',
         '2025.11')
    ]


    for url, month in download_tasks:
        save_dir = f"./download/AE/{month}"

        task_kwargs = {
            "downloader": safe_downloader,
            "url": url,
            "save_folder": save_dir,
            "custom_filename": f"导出原表_卖家中心_{month}.xlsx"
        }
        task_group = f"{shop_info['shop_abbr']}_下载任务"

        success = MAIN_TASK_MANAGER.add_task(
            task_id=f"卖家中心_{month}_xlsx_下载任务",
            target_func=download_worker, **task_kwargs,
            task_group=task_group,
            
        )