import inspect
import json
import re
import sys
import time
import threading
from pathlib import Path
from typing import Dict, Optional

import psutil
import requests
from loguru import logger
from playwright.sync_api import sync_playwright, Request as PWRequest

from config.common_config import db, config_manager
from config.start_config import MAIN_TASK_MANAGER
from utils.multiThreading_log_manager import get_task_log_manager
from utils.playwright_login_tools import kill_occupied_chrome_processes, click_close_icon_if_exist

THREAD_LOCAL = threading.local()

# ---------------- 配置 ----------------
LOGIN_URL = "https://seller.kuajingmaihuo.com/login"

SELLER_URL = "https://seller.kuajingmaihuo.com/"

TEMU_HOME = "https://agentseller.temu.com/"
AUTH_URL = "https://agentseller.temu.com/main/authentication"

GOODS_URL = "https://seller.kuajingmaihuo.com/goods/list"

# TEMU Cookies 域名（必须精准匹配）
TEMU_COOKIE_DOMAIN = ".agentseller.temu.com"


# ============================================================
# 工具函数（适配多线程 + 新增Cookies格式转换）
# ============================================================

def cookies_from_context(context, domain: str = None) -> Dict[str, str]:
    """
    将 Playwright 上下文的 Cookies 转换为简单字典（便于存储）
    :param context: Playwright BrowserContext
    :param domain: 可选，指定域名过滤（如 ".agentseller-eu.temu.com"），不传则获取所有 cookies
    :return: {"cookie_name": "cookie_value", ...}
    """
    try:
        all_cookies = context.cookies()
        if domain is None:
            # 不过滤，返回所有 cookies
            return {c["name"]: c["value"] for c in all_cookies}
        else:
            # 按域名过滤，只返回指定域名的 cookies
            return {c["name"]: c["value"] for c in all_cookies if c.get("domain") and domain in c["domain"]}
    except Exception:
        return {}


def convert_dict_to_playwright_cookies(cookies_dict: Dict[str, str]) -> list:
    """
    将简单字典格式的Cookies转换为Playwright要求的列表格式
    :param cookies_dict: {"name1": "value1", "name2": "value2"}
    :return: [{"name": "name1", "value": "value1", "domain": ".agentseller.temu.com", ...}, ...]
    """
    playwright_cookies = []
    for name, value in cookies_dict.items():
        playwright_cookies.append({
            "name": name,
            "value": value,
            "domain": TEMU_COOKIE_DOMAIN,  # 必须匹配TEMU的Cookies域名
            "path": "/",  # 路径覆盖所有页面
            "httpOnly": True,  # 适配TEMU的Cookies属性
            "secure": True,
            "sameSite": "Lax"
        })
    return playwright_cookies


def get_mallid_from_userinfo(headers: Dict[str, str], cookies: Dict[str, str]) -> Optional[Dict]:
    """调用 TEMU userInfo 接口获取 mallid"""
    url = "https://agentseller.temu.com/api/seller/auth/userInfo"
    try:
        resp = requests.post(url, headers=headers, cookies=cookies, json={}, timeout=10)
        if resp.status_code == 200:
            result = resp.json().get("result", {})
            mall_list = result.get("mallList", [])
            if mall_list:
                mallid = str(mall_list[0]["mallId"])
                mallName = str(mall_list[0]["mallName"])
                data = {"mallId": mallid, "mallName": mallName}
                logger.info(f"✅ 线程[{threading.current_thread().name}] 主店铺mallid: {mallid} | 主店铺: {mallName}")
                return data
    except Exception as e:
        logger.error(f"❌ 线程[{threading.current_thread().name}] userInfo 接口失败: {e}")
    return {"mallId": "", "mallName": ""}


def access_temu_with_cookies(uid, username: str, headless: bool = True, auto_close=True,
                             window_size: tuple = (1920, 1080), fetch_multi_region: bool = False) -> Optional[Dict]:
    """
    复用已保存的 Cookies 直接访问 TEMU 网站（免登录）
    修复点：1. 新增数据库查询结果非空校验 2. 新增字典赋值前None判断 3. 完善异常兜底
    """
    thread_name = threading.current_thread().name
    logger.info(f"🔍 线程[{thread_name}] 尝试复用 Cookies 访问 TEMU（账号：{username}）")

    # 1. 加载已保存的 Cookies 和 headers（核心修复：新增非空校验+初始化）
    save_data = db.execute_sql(
        "SELECT cookies, headers FROM shops WHERE uid = ?",
        params=(uid,),
        fetch="fetch_one"
    )
    # 关键修复1：save_data为None时，初始化为空字典，避免后续赋值报错
    if save_data is None:
        logger.warning(f"⚠️ 线程[{thread_name}] 账号[{username}] 未查询到店铺数据（uid={uid}），跳过复用")
        return None
    # print(f"📥 线程[{thread_name}] 数据库查询结果：{save_data}")

    try:
        # 2. 解析Cookies（字符串→字典，保留原有逻辑）
        cookies_str = save_data.get("cookies", "{}")  # 用get避免键不存在报错
        if cookies_str == "" or cookies_str is None or cookies_str == "{}":
            logger.error(f"❌ 线程[{thread_name}] 账号[{username}] Cookies为空")
            return None

        cookies_dict = json.loads(cookies_str)
        if not isinstance(cookies_dict, dict) or len(cookies_dict) == 0:
            logger.error(f"❌ 线程[{thread_name}] 账号[{username}] Cookies格式错误（非字典/空）")
            return None

        # 转换为Playwright要求的列表格式
        playwright_cookies = convert_dict_to_playwright_cookies(cookies_dict)
        # print(f"✅ 线程[{thread_name}] 账号[{username}] 转换Cookies格式完成（共{len(playwright_cookies)}个）")

        # 3. 解析headers（避免KeyError，保留原有逻辑）
        headers_str = save_data.get("headers", "{}")
        headers_dict = json.loads(headers_str) if (headers_str and headers_str != '{}') else {}
        # print(f"📋 线程[{thread_name}] 从数据库加载的 headers: {headers_dict}")

        # 4. 创建独立的 Playwright 实例和浏览器上下文（线程隔离，保留原有逻辑）
        playwright = sync_playwright().start()
        browser = playwright.chromium

        # 浏览器路径配置
        if getattr(sys, 'frozen', False):
            base_path = Path(sys.executable).parent
        else:
            base_path = Path(__file__).parent.parent
        browser_executable_path = base_path / "浏览器文件" / "chrome-win" / "chrome.exe"
        executable_path = str(browser_executable_path)

        user_data_dir = base_path / "浏览器文件" / "用户数据" / "浏览器窗口" / f"user_{username}_uid_{uid}"

        kill_occupied_chrome_processes(username, uid)
        user_data_dir.mkdir(parents=True, exist_ok=True)

        # 生成唯一CDP端口
        import hashlib
        unique_key = f"{username}_{uid}"
        md5_hash = hashlib.md5(unique_key.encode()).hexdigest()
        cdp_port = 10000 + int(md5_hash[:4], 16) % 50000

        window_length, window_width = window_size
        # 5. 创建浏览器上下文（保留原有逻辑）
        context = browser.launch_persistent_context(
            user_data_dir=user_data_dir,
            executable_path=executable_path,
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                f"--window-size={window_length},{window_width}",
                "--disable-cache",
                "--disable-application-cache",
                f"--remote-debugging-port={cdp_port}",
                "--no-foreground",
                "--background-mode",
                # 关键：启用 Client Hints
                "--enable-features=WebOTP,ClientHints",
                "--window-position=0,0",  # 原有窗口位置
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--enable-features=PasswordImport",  # 启用密码保存功能
                # "--remote-debugging-port=-1",  # 建议开启，彻底禁用调试模式，避免之前的黄色调试栏
                "--disable-debugging-info",
                "--hide-crash-restore-bubble",
                "--disable-features=ChromeDevToolsServer,DevToolsExtension",
                "--disable-dev-tools",
                "--font-render-hinting=none",
            ],
            no_viewport=True,
        )

        context.add_cookies(playwright_cookies)
        logger.info(f"✅ 线程[{thread_name}] 已为账号[{username}] 注入 Cookies")

        # 6. 访问 TEMU 主页（修复原有嵌套异常的语法错误，保留核心逻辑）
        page = context.new_page()

        try:
            print(f"➡️ 线程[{thread_name}] 正在导航到 {TEMU_HOME}...")
            page.goto(TEMU_HOME, wait_until="networkidle", timeout=30000)
            print(f"✅ 线程[{thread_name}] 导航到 {TEMU_HOME} 成功。当前URL: {page.url}")
        except Exception as e:
            logger.error(f"❌ 线程[{thread_name}] 导航到 {TEMU_HOME} 超时/失败：{e}")
            # 重试逻辑（修复原有语法错误）
            tries = 0
            reload_success = False
            while tries < 3:
                tries += 1
                current_timeout = 15000 + tries * 5000
                try:
                    page.reload(wait_until="networkidle", timeout=current_timeout)
                    logger.info(f"🔄 线程[{thread_name}] 第{tries}次刷新后，当前URL: {page.url}")
                    reload_success = True
                    break
                except Exception as reload_e:
                    logger.error(f"❌ 线程[{thread_name}] 第{tries}次刷新失败：{reload_e}")
            if not reload_success:
                context.close()
                playwright.stop()
                return None

        # 7. 验证是否登录成功（检查SUB_PASS_ID，保留原有逻辑）
        current_cookies = cookies_from_context(context)
        if "SUB_PASS_ID" not in current_cookies:
            logger.error(f"❌ 线程[{thread_name}] 账号[{username}] Cookies 失效（无SUB_PASS_ID）")
            try:
                page.reload(wait_until="networkidle", timeout=30000)
                current_cookies_after_reload = cookies_from_context(context)
                if "SUB_PASS_ID" in current_cookies_after_reload:
                    print(f"🔄 线程[{thread_name}] 刷新后找到 SUB_PASS_ID")
                    current_cookies = current_cookies_after_reload
                else:
                    logger.error(f"❌ 线程[{thread_name}] 刷新后仍无 SUB_PASS_ID，访问失败")
                    context.close()
                    playwright.stop()
                    return None
            except Exception as e:
                logger.error(f"❌ 线程[{thread_name}] 验证登录状态时刷新失败：{e}")
                context.close()
                playwright.stop()
                return None

        # 8. 检查最终URL是否为认证/登录页（保留原有逻辑）
        final_url = page.url
        if any(key in final_url.lower() for key in ["authentication", "auth", "login"]):
            logger.warning(f"❌ 线程[{thread_name}] 账号[{username}] 被重定向到认证页")
            context.close()
            playwright.stop()
            return None
        else:
            logger.info(f"✅ 线程 [{thread_name}] 账号 [{username}] 复用 Cookies 访问成功。当前 URL: {final_url}")

        # ========== 新增：获取并保存多区域 Cookies（根据参数决定） ==========
        if fetch_multi_region:
            try:
                logger.info(f"🔄 线程 [{thread_name}] 开始获取多区域 Cookies...")
                region_result = fetch_all_region_cookies_func(context, shop_abbr="")

                # 提取结果
                global_cookies_new = region_result["global_cookies"]
                us_cookies_new = region_result["us_cookies_temp"]
                eu_cookies_new = region_result["eu_cookies_temp"]

                # 保存到数据库
                save_region_cookies_to_db(uid, global_cookies_new, us_cookies_new, eu_cookies_new, shop_abbr="")

                logger.success(f"✅ 线程 [{thread_name}] 多区域 Cookies 已更新并保存到数据库")
            except Exception as e:
                logger.warning(f"⚠️ 线程 [{thread_name}] 获取多区域 Cookies 失败：{e}，继续使用原有 Cookies")
        # =======================================================

        # 9. 捕获headers（mallid/anti-content，保留原有逻辑）
        captured_headers = {}

        def on_request(req):
            try:
                if hasattr(req, 'url') and hasattr(req, 'resource_type') and hasattr(req, 'headers'):
                    if "agentseller.temu.com" in req.url and req.resource_type in ("xhr", "fetch"):
                        h = dict(req.headers)
                        if "anti-content" in h:
                            captured_headers["anti-content"] = h["anti-content"]
                        if "mallid" in h and h.get("mallid") and h["mallid"] != "undefined":
                            captured_headers["mallid"] = h["mallid"]
            except Exception:
                pass

        page.on("request", on_request)
        page.wait_for_timeout(2000)

        # 10. 合并headers（关键修复2：若需对save_data赋值，先判断非空）
        final_headers = headers_dict.copy()
        final_headers.update({k: v for k, v in captured_headers.items() if v})

        # 若业务需要将新headers写回save_data，必须先判断save_data非空（核心兜底）
        # 示例：if save_data is not None: save_data["new_key"] = new_value

        # 11. 获取mallid和mallName（保留原有逻辑）
        try:
            userinfo = get_mallid_from_userinfo(final_headers, current_cookies)
            copyMallId = userinfo.get("mallId")
            mallName = userinfo.get("mallName")
            mallid = captured_headers.get("mallid") or copyMallId
            if mallid:
                final_headers["mallid"] = mallid
                final_headers["mallName"] = mallName
                logger.info(f"✅ 线程[{thread_name}] 获取到 mallid: {mallid}, mallName: {mallName}")
        except Exception as e:
            logger.error(f"❌ 线程[{thread_name}] 获取 mallid/mallName 失败：{e}")
            return None

        # 返回结果（保留原有逻辑）
        return {
            "headers": final_headers,
            "cookies": current_cookies,
            "context": context,
            "page": page,
            "playwright": playwright,
            "mallid": mallid,
            "mallName": mallName,
        }

    except json.JSONDecodeError as e:
        print(f"❌ 线程[{thread_name}] 账号[{username}] Cookies解析失败：{e}")
        return None
    except Exception as e:
        print(f"❌ 线程[{thread_name}] 复用 Cookies 访问失败：{e}")
        # 关键修复3：异常时兜底释放Playwright资源，避免内存泄漏
        if 'playwright' in locals():
            try:
                playwright.stop()
            except:
                pass
        if 'context' in locals():
            try:
                context.close()
            except:
                pass
        return None


def is_any_page_on_target_login(context, target_login_url: str = LOGIN_URL) -> bool:
    """
    检测Playwright上下文内所有标签页，是否有任意一个停在目标登录页面
    :param context: Playwright的BrowserContext实例
    :param target_login_url: 目标登录页URL，默认使用全局配置的LOGIN_URL
    :return: 存在则返回True，无则返回False
    """
    # 上下文为空/无效，直接返回False
    if not context:
        return False
    # 遍历上下文内所有标签页（pages是所有标签页的列表）
    for page in context.pages:
        # 跳过已关闭的页面，避免操作失效页面报错
        if page and not page.is_closed():
            # 严格匹配URL（若需兼容带参数的情况，可改为 target_login_url in page.url）
            if page.url == target_login_url:
                return True
    # 所有有效页面均未匹配目标登录页
    return False


def check_and_close_invalid_browser(context, playwright=None, base_login_url: str = LOGIN_URL) -> bool:
    """
    静态通用函数：检测浏览器标签页是否仅包含允许的页面，无其他页面则关闭进程
    允许的页面类型：
    1. 基础登录页：https://seller.kuajingmaihuo.com/login
    2. 带参数登录页：https://seller.kuajingmaihuo.com/login?xxx（任意参数）
    3. 空白页：about:blank
    :param context: Playwright的BrowserContext实例（必传）
    :param playwright: Playwright驱动实例（可选，传则一起关闭）
    :param base_login_url: 基础登录页URL，默认使用全局LOGIN_URL
    :return: 关闭进程返回True，未关闭返回False
    """
    thread_name = threading.current_thread().name
    # 边界校验：上下文无效/已关闭，直接返回False
    if not context or not hasattr(context, 'pages') or (hasattr(context, 'is_closed') and context.is_closed()):
        logger.warning(f"⚠️ 线程[{thread_name}] 浏览器上下文无效/已关闭，跳过检测")
        return False

    # 遍历所有标签页，检查是否存在非允许页面
    has_unallowed_page = False
    for page in context.pages:
        if page and not page.is_closed():  # 仅处理有效（未关闭）标签页
            current_url = page.url.strip()
            # 判定是否为非允许页面
            if not (
                    current_url == base_login_url  # 匹配基础登录页
                    or current_url.startswith(f"{base_login_url}?")  # 匹配带参数登录页
                    or current_url == "about:blank"  # 匹配空白页
            ):
                has_unallowed_page = True
                logger.info(f"🔍 线程[{thread_name}] 检测到有效业务页面：{current_url}，保留浏览器进程")
                break  # 发现有效页面，直接终止遍历

    # 仅包含允许的页面 → 关闭进程+释放资源
    if not has_unallowed_page:
        logger.info(f"✅ 线程[{thread_name}] 检测通过：仅含登录页/空白页，开始关闭浏览器进程")
        # 1. 关闭浏览器上下文（核心：关闭所有标签页和浏览器进程）
        try:
            if not context.is_closed():
                context.close()
                logger.info(f"🗑️ 线程[{thread_name}] 浏览器上下文已成功关闭")
        except Exception as e:
            logger.error(f"❌ 线程[{thread_name}] 关闭浏览器上下文失败：{str(e)}")
        # 2. 停止Playwright驱动（避免资源泄漏）
        try:
            if playwright and hasattr(playwright, 'stop'):
                playwright.stop()
                logger.info(f"🗑️ 线程[{thread_name}] Playwright驱动已成功停止")
        except Exception as e:
            logger.error(f"❌ 线程[{thread_name}] 停止Playwright驱动失败：{str(e)}")
        return True
    return False


def auto_detect_and_clean_all_browsers(base_login_url: str = LOGIN_URL):
    """
    自动检测系统中所有业务相关Chrome浏览器，校验标签页并关闭无效进程
    核心逻辑：1. CDP连接精准检测标签页 2. 兜底强制关闭无CDP端口的无效业务进程
    :param base_login_url: 基础登录页URL，默认使用全局LOGIN_URL
    """
    thread_name = threading.current_thread().name
    logger.info(f"🚀 线程[{thread_name}] 开始自动检测系统中所有业务Chrome浏览器...")
    # 匹配业务用户目录的正则（适配：user_13800138000_uid_123456 格式）
    user_dir_pattern = re.compile(r"user_\d+_uid_\w+")
    closed_count = 0  # 统计关闭的进程数

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # 过滤：仅处理Chrome进程（兼容大小写，如chrome.exe/Chrome.exe）
            if not (proc.info.get('name') and 'chrome.exe' in proc.info['name'].lower()):
                continue
            cmdline = proc.info.get('cmdline', [])
            if not cmdline:
                continue
            cmdline_str = ' '.join(cmdline)
            # 过滤：仅处理包含业务用户目录的Chrome进程（非业务进程跳过）
            if not user_dir_pattern.search(cmdline_str):
                continue

            pid = proc.info['pid']
            logger.info(f"🔍 线程[{thread_name}] 发现业务Chrome进程(pid={pid})，开始检测...")
            # 提取Chrome进程的CDP调试地址（--remote-debugging-port/--remote-debugging-address）
            cdp_ws = None
            cdp_port = None
            cdp_address = "127.0.0.1"
            # 遍历命令行参数，提取端口和地址
            for arg in cmdline:
                if arg.startswith('--remote-debugging-port='):
                    cdp_port = arg.split('=')[-1].strip()
                    if cdp_port.isdigit():  # 确保是有效数字端口
                        logger.info(f"✅ 线程[{thread_name}] 进程(pid={pid})提取到CDP端口：{cdp_port}")
                elif arg.startswith('--remote-debugging-address='):
                    cdp_address = arg.split('=')[-1].strip()

            # 生成CDP连接地址
            if cdp_port:
                cdp_ws = f"ws://{cdp_address}:{cdp_port}/devtools/browser"
            else:
                logger.warning(f"⚠️ 线程[{thread_name}] 进程(pid={pid})未找到有效CDP调试端口，执行兜底强制关闭...")
                # 兜底逻辑：无CDP端口的业务Chrome进程，直接强制关闭（避免残留）
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                    logger.info(f"🗑️ 线程[{thread_name}] 兜底强制关闭无CDP端口的业务进程(pid={pid})")
                    closed_count += 1
                except psutil.TimeoutExpired:
                    proc.kill()
                    logger.info(f"🗑️ 线程[{thread_name}] 兜底强制杀死无CDP端口的业务进程(pid={pid})")
                    closed_count += 1
                except Exception as e:
                    logger.warning(f"⚠️ 线程[{thread_name}] 兜底关闭进程(pid={pid})失败：{str(e)}")
                continue  # 跳过后续CDP检测，处理下一个进程

            # 通过CDP连接已运行的Chrome进程（原有精准检测逻辑，保留）
            playwright = None
            browser = None
            try:
                playwright = sync_playwright().start()
                browser = playwright.chromium.connect_over_cdp(cdp_ws, timeout=10000)
                logger.info(f"✅ 线程[{thread_name}] 成功通过CDP连接进程(pid={pid})")
                # 遍历浏览器所有上下文，精准检测标签页
                for context in browser.contexts:
                    if check_and_close_invalid_browser(context, playwright, base_login_url):
                        closed_count += 1
            except Exception as e:
                logger.error(f"❌ 线程[{thread_name}] CDP检测进程(pid={pid})失败，执行兜底关闭：{str(e)}")
                # CDP检测失败，兜底强制关闭该业务进程
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                    logger.info(f"🗑️ 线程[{thread_name}] CDP检测失败，兜底关闭进程(pid={pid})")
                    closed_count += 1
                except Exception as e2:
                    logger.warning(f"⚠️ 线程[{thread_name}] 兜底关闭进程(pid={pid})失败：{str(e2)}")
            finally:
                # 兜底释放CDP连接资源
                if browser and browser.is_connected():
                    try:
                        browser.close()
                    except Exception:
                        pass
                if playwright:
                    playwright.stop()

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            logger.warning(f"⚠️ 线程[{thread_name}] 进程(pid={proc.info.get('pid')})已退出/无权限，跳过")
        except Exception as e:
            logger.warning(f"⚠️ 线程[{thread_name}] 处理Chrome进程失败：{str(e)}", exc_info=True)

    logger.success(f"✅ 线程[{thread_name}] 全量浏览器检测完成，共关闭{closed_count}个无效进程")


def fetch_all_region_cookies_func(context, shop_abbr: str = "") -> Dict:
    """
    获取 TEMU 多区域 Cookies（全球区、美区、欧区）并保存到数据库
    :param context: Playwright BrowserContext
    :param shop_abbr: 店铺缩写
    :return: {global_cookies, us_cookies_temp, eu_cookies_temp, page2, current_url}
    """
    thread_name = threading.current_thread().name

    # ========== 第一步：获取全球区 Cookies ==========
    logger.info("\n" + "=" * 80)
    logger.info(f"🌍 第一步：获取全球区 Cookies")
    logger.info("=" * 80)

    global_cookies = cookies_from_context(context)
    logger.info(f"📊 全球区 cookies 数量：{len(global_cookies)}个")

    # 打印全球区 seller_temp
    if 'seller_temp' in global_cookies:
        global_seller_temp = global_cookies['seller_temp']
        logger.info(f"\n🔑 全球区 seller_temp:")
        logger.info(f"seller_temp = '{global_seller_temp}'\n")
    else:
        logger.warning("⚠️ 全球区 cookies 中未找到 seller_temp")
        global_seller_temp = None

    # ========== 第二步：依次点击美国、欧区并获取 Cookies ==========
    logger.info("\n" + "=" * 80)
    logger.info(f"🌎 第二步：依次点击美国、欧区并获取 Cookies")
    logger.info("=" * 80)

    # 初始化所有可能用到的变量（防止异常分支未定义）
    us_cookies_temp = {}
    eu_cookies_temp = {}
    page2 = None
    current_url = TEMU_HOME
    eu_page_new = None

    # 创建新页面访问美区
    us_page_new = context.new_page()
    logger.info(f"🆕 创建新页面访问美区...")
    us_page_new.goto(TEMU_HOME, wait_until="networkidle", timeout=15000)
    time.sleep(3)

    try:
        # 等待地区选择器出现（使用多种选择器策略）
        region_items = None
        selectors_to_try = [
            'a.index-module__drItem___kEdZY',  # 原始选择器
            'a[class*="drItem"]',  # 类名包含 drItem
            'a[href*="region"]',  # href 包含 region
            '[class*="region-item"]',  # 类名包含 region-item
            'a[class*="RegionItem"]',  # 类名包含 RegionItem（大写）
        ]

        for selector in selectors_to_try:
            try:
                us_page_new.wait_for_selector(selector, timeout=5000)
                region_items = us_page_new.query_selector_all(selector)
                if region_items and len(region_items) >= 3:
                    logger.info(f"✅ 使用选择器 [{selector}] 找到 {len(region_items)} 个地区选项")
                    break
            except Exception:
                continue

        if not region_items or len(region_items) < 3:
            # 尝试通过文本内容查找地区选项
            logger.info(f"⚠️ 常规选择器未找到地区选项，尝试通过文本查找...")
            try:
                # 查找包含特定文本的链接
                all_links = us_page_new.query_selector_all('a')
                region_items = []
                for link in all_links:
                    text = link.inner_text().strip()
                    # 查找可能包含地区名称的链接
                    if any(region in text for region in ['全球', '美国', '欧', 'US', 'EU', 'Global']):
                        region_items.append(link)
                if region_items:
                    logger.info(f"✅ 通过文本找到 {len(region_items)} 个可能的地區选项")
            except Exception as text_e:
                logger.warning(f"⚠️ 文本查找也失败：{text_e}")

        if region_items and len(region_items) >= 3:
            # 点击第二个：美国
            logger.info(f"\n🇺🇸 点击美国...")
            region_items[1].click()
            time.sleep(3)  # 减少等待时间

            # 打印点击后的 URL
            logger.info(f"📍 点击美国后页面 URL: {us_page_new.url}")

            # ========== 立即获取美区 cookies ==========
            us_seller_temp_only = cookies_from_context(context, domain='agentseller-us.temu.com')
            logger.info(f"📊 美区 cookies 数量：{len(us_seller_temp_only)}个")

            # 只保留美区域名下的 cookies
            all_context_cookies = context.cookies()
            us_domain_cookies = {c['name']: c['value'] for c in all_context_cookies if
                                 'agentseller-us.temu.com' in c.get('domain', '')}
            logger.info(f"🔍 美区域名 cookies 列表：{list(us_domain_cookies.keys())}")

            # 直接使用美区 cookies
            us_cookies_temp = us_domain_cookies.copy()
            logger.info(f"✅ 已保存美区 cookies（{len(us_cookies_temp)}个）")

            # 【关键修改】不关闭美区页面，保留到后续选择
            logger.info(f"🔄 保留美区页面，等待后续选择")

            # ========== 重新创建新页面点击欧洲区 ==========
            eu_page_new = context.new_page()
            logger.info(f"\n🆕 创建新页面访问欧区...")
            eu_page_new.goto(TEMU_HOME, wait_until="networkidle", timeout=15000)
            time.sleep(3)

            # 使用同样的多选择器策略查找欧区选项
            region_items_eu = None
            for selector in selectors_to_try:
                try:
                    eu_page_new.wait_for_selector(selector, timeout=5000)
                    region_items_eu = eu_page_new.query_selector_all(selector)
                    if region_items_eu and len(region_items_eu) >= 3:
                        logger.info(f"✅ 欧区页面使用选择器 [{selector}] 找到 {len(region_items_eu)} 个地区选项")
                        break
                except Exception:
                    continue

            if not region_items_eu or len(region_items_eu) < 3:
                # 尝试通过文本查找
                try:
                    all_links = eu_page_new.query_selector_all('a')
                    region_items_eu = []
                    for link in all_links:
                        text = link.inner_text().strip()
                        if any(region in text for region in ['全球', '美国', '欧', 'US', 'EU', 'Global']):
                            region_items_eu.append(link)
                    if region_items_eu:
                        logger.info(f"✅ 欧区页面通过文本找到 {len(region_items_eu)} 个可能的地区选项")
                except Exception:
                    pass

            # 点击第三个：欧区
            logger.info(f"\n🇪🇺 点击欧区...")
            if region_items_eu and len(region_items_eu) >= 3:
                region_items_eu[2].click()
                time.sleep(3)  # 减少等待时间

                # 打印点击后的 URL
                logger.info(f"📍 点击欧区后页面 URL: {eu_page_new.url}")

                # ========== 立即获取欧区 cookies ==========
                eu_seller_temp_only = cookies_from_context(context, domain='agentseller-eu.temu.com')
                logger.info(f"📊 欧区 cookies 数量：{len(eu_seller_temp_only)}个")

                # 只保留欧区域名下的 cookies
                all_context_cookies_eu = context.cookies()
                eu_domain_cookies = {c['name']: c['value'] for c in all_context_cookies_eu if
                                     'agentseller-eu.temu.com' in c.get('domain', '')}
                logger.info(f"🔍 欧区域名 cookies 列表：{list(eu_domain_cookies.keys())}")

                # 直接使用欧区 cookies
                eu_cookies_temp = eu_domain_cookies.copy()
                logger.info(f"✅ 已保存欧区 cookies（{len(eu_cookies_temp)}个）")

                # 最终使用欧区 cookies
                cookies = eu_cookies_temp
                current_url = eu_page_new.url
                logger.info(f"\n✅ 最终使用欧区 cookies，当前 URL: {current_url}")

                page2 = eu_page_new  # 切换到欧区页面
                logger.info(f"🔄 已切换到欧区页面")
            else:
                logger.warning(f"⚠️ 重新获取后地区选项不足 3 个")
                cookies = us_cookies_temp
                current_url = us_page_new.url  # 使用美区页面 URL
                eu_cookies_temp = us_cookies_temp.copy()  # 兜底

        else:
            logger.warning(f"⚠️ 未找到足够的地区选项（当前有{len(region_items) if region_items else 0}个）")
            cookies = cookies_from_context(context)
            current_url = us_page_new.url  # 使用美区页面 URL
            us_cookies_temp = cookies_from_context(context, domain='agentseller-us.temu.com')
            eu_cookies_temp = cookies_from_context(context, domain='agentseller-eu.temu.com')

    except Exception as e:
        logger.warning(f"⚠️ 点击地区失败：{e}")
        cookies = cookies_from_context(context)
        current_url = us_page_new.url if us_page_new else TEMU_HOME
        us_cookies_temp = cookies_from_context(context, domain='agentseller-us.temu.com')
        eu_cookies_temp = cookies_from_context(context, domain='agentseller-eu.temu.com')

    return {
        "global_cookies": global_cookies,
        "global_seller_temp": global_seller_temp,
        "us_cookies_temp": us_cookies_temp,
        "eu_cookies_temp": eu_cookies_temp,
        "page2": page2,
        "current_url": current_url,
        "us_page": us_page_new,
        "eu_page": eu_page_new
    }


def save_region_cookies_to_db(uid: str, global_cookies: Dict, us_cookies: Dict, eu_cookies: Dict, shop_abbr: str = ""):
    """
    保存多区域 Cookies 到数据库
    :param uid: 店铺 UID
    :param global_cookies: 全球区 cookies
    :param us_cookies: 美区 cookies
    :param eu_cookies: 欧区 cookies
    :param shop_abbr: 店铺缩写
    """
    logger.info(f"💾 开始保存店铺{shop_abbr}的多区域 cookies 到数据库...")

    # 确保 cookies_us 和 cookies_eu 列存在（兼容旧数据库）
    try:
        table_info = db.get_table_info("shops")
        existing_columns = [col["name"] for col in table_info]

        if "cookies_us" not in existing_columns:
            db.execute_sql("ALTER TABLE shops ADD COLUMN cookies_us TEXT", commit=True)
            logger.info("✅ 已添加 cookies_us 列到 shops 表")

        if "cookies_eu" not in existing_columns:
            db.execute_sql("ALTER TABLE shops ADD COLUMN cookies_eu TEXT", commit=True)
            logger.info("✅ 已添加 cookies_eu 列到 shops 表")
    except Exception as e:
        logger.warning(f"⚠️ 检查/添加列时出错：{e}")

    # 保存全球区 cookies（字段名：cookies）
    db.execute_sql(
        "update shops set cookies = ? where uid = ?",
        params=(json.dumps(global_cookies), uid),
        fetch="none")

    # 保存美区 cookies（字段名：cookies_us）
    db.execute_sql(
        "update shops set cookies_us = ? where uid = ?",
        params=(json.dumps(us_cookies), uid),
        fetch="none")

    # 保存欧区 cookies（字段名：cookies_eu）
    db.execute_sql(
        "update shops set cookies_eu = ? where uid = ?",
        params=(json.dumps(eu_cookies), uid),
        fetch="none")

    logger.success(f"✅ 店铺{shop_abbr} cookies、cookies_us 和 cookies_eu 已保存到数据库")


def create_temu_session(username: str, password: str, uid: str = None, headless=True, shop_abbr: str = None,
                        auto_close: bool = True, window_size: tuple = (1920, 1080), reload_cookies: bool = True,
                        fetch_all_region_cookies: bool = False) -> Dict:
    """
    登录temu（多线程安全版），返回{ headers, cookies, mallid, mallName, global_cookies, us_cookies_temp, eu_cookies_temp }
    优先复用Cookies，失败则重新登录并保存Cookies到数据库
    """
    thread_name = threading.current_thread().name

    shop_abbr = shop_abbr or ""
    logger.info(f"🔐 店铺{shop_abbr}：正在执行自动登录 TEMU 账号[{username}]")

    try:
        use_cookies = config_manager.get_or_set_config("Settings_use_cookies", "是")

        if uid and use_cookies == "是":
            # 第一步：优先尝试复用 Cookies
            reuse_result = access_temu_with_cookies(uid, username, headless, auto_close, window_size,
                                                    fetch_multi_region=fetch_all_region_cookies)
            if reuse_result:
                return reuse_result
            else:
                # 复用失败 → 执行正常登录流程
                logger.warning(f"⚠️ 店铺{shop_abbr} 账号 [{username}] 复用 Cookies 失败，执行重新登录")

    except Exception as e:
        logger.error(f"❌ 店铺{shop_abbr}：自动登录 TEMU 账号[{username}] 失败：{str(e)}")

    playwright = sync_playwright().start()
    browser = playwright.chromium

    if getattr(sys, 'frozen', False):
        base_path = Path(sys.executable).parent
    else:
        base_path = Path(__file__).parent.parent

    browser_executable_path = base_path / "浏览器文件" / "chrome-win" / "chrome.exe"
    executable_path = str(browser_executable_path)

    user_data_dir = base_path / "浏览器文件" / "用户数据" / "浏览器窗口" / f"user_{username}_uid_{uid}"

    kill_occupied_chrome_processes(username, uid)

    user_data_dir.mkdir(parents=True, exist_ok=True)

    context = None
    try:
        # 新增：基于username+uid生成唯一CDP端口（10000-65535范围，避免冲突）
        import hashlib
        # 生成唯一标识，再转成端口号
        unique_key = f"{username}_{uid}"
        md5_hash = hashlib.md5(unique_key.encode()).hexdigest()
        cdp_port = 10000 + int(md5_hash[:4], 16) % 50000  # 端口范围10000-60000

        window_length, window_width = window_size

        context = browser.launch_persistent_context(
            user_data_dir=user_data_dir,
            executable_path=executable_path,
            headless=headless,
            args=[
                "--background-mode",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                f"--window-size={window_length},{window_width}",
                "--disable-cache",
                "--disable-application-cache",
                f"--remote-debugging-port={cdp_port}",
                "--no-foreground",
                # 关键：启用 Client Hints
                "--enable-features=WebOTP,ClientHints",
                "--window-position=0,0",  # 原有窗口位置
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--enable-features=PasswordImport",  # 启用密码保存功能
                # "--remote-debugging-port=-1",  # 建议开启，彻底禁用调试模式，避免之前的黄色调试栏
                "--disable-debugging-info",
                "--hide-crash-restore-bubble",
                "--disable-features=ChromeDevToolsServer,DevToolsExtension",
                "--disable-dev-tools",
                "--font-render-hinting=none",
            ],
            no_viewport=True,
        )

        # 登录流程
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)

        ck_inner_origin = cookies_from_context(context)

        page.get_by_text("手机号登录").click()
        page.locator('input[placeholder*=\"手机号\"]').fill(username)
        page.locator('input[type=\"password\"]').fill(password)
        page.get_by_test_id("beast-core-checkbox-checkIcon").locator("div").click(force=True)
        page.locator('button:has-text(\"登录\")').click()

        # logger.info(f"➡️ 店铺{shop_abbr} 登录表单已提交")

        logger.info(f"➡️ 店铺{shop_abbr} 检测登录参数中...")

        # time.sleep(3)
        for _ in range(17):
            if "settle/site-main" in page.url:
                break
            time.sleep(0.5)
            if _ == 19:
                logger.error(f"❌ 店铺{shop_abbr} 未检测到settle/site-main，建议重新登录")

        login_success = False
        for _ in range(45):
            # 检测短信验证码输入框（缩短超时，避免阻塞，3秒足够）
            verify_code_input = page.locator('input[placeholder*="请输入短信验证码"]')
            try:
                is_verify_code_show = verify_code_input.is_visible(timeout=3000)
            except Exception:
                is_verify_code_show = False

            handle_yzm_by_hand = config_manager.get_or_set_config("handle_yzm_by_hand", "否")
            if handle_yzm_by_hand == "是":
                if is_verify_code_show:
                    logger.info(f"店铺{shop_abbr} 触发验证码,可在一小时内完成短信验证")
                    # 这里需要修改状态为验证码

                    # 人工验证循环：单独校验，仅在成功时标记并直接退出所有循环
                    for _ in range(1800):
                        ck_inner = cookies_from_context(context)
                        if "SUB_PASS_ID" in ck_inner and ck_inner_origin != ck_inner:
                            login_success = True
                            # 仅打印一次日志（核心：移除重复日志）
                            logger.success(f"✅ 店铺{shop_abbr} 人工验证后登录成功")
                            break  # 退出内层人工验证循环
                        time.sleep(2)
                    break  # 核心：退出外层45次循环，避免回到外层重复判定
            else:
                if is_verify_code_show:
                    raise RuntimeError(f"❌ 检测到短信验证码输入框，需要进行验证")

            ck = cookies_from_context(context)
            if "SUB_PASS_ID" in ck:
                login_success = True
                logger.success(f"店铺{shop_abbr} 登录参数验证成功")
                break  # 检测到Cookie，直接退出外层循环，仅打印一次日志
            time.sleep(1)

        if not login_success:
            raise RuntimeError(f"❌ 登录失败，未检测到 SUB_PASS_ID")

        if "login" in page.url:
            raise RuntimeError(f"❌ 检测到 SUB_PASS_ID，但实际未登录成功")

        # 处理 TEMU 授权：仅单次执行，广告关闭后继续走核心点击逻辑，覆盖弹/不弹广告场景
        if "settle/site-main" in page.url:
            try:
                # 【核心前置】进入授权页先检测广告并关闭（广告触发在授权页开始，此处是首次检测）
                # 关闭后继续执行后续核心逻辑，不中断、不兜底
                click_close_icon_if_exist(page)

                # 1. 勾选授权协议：保留原健壮逻辑，增加超时和JS兜底
                icon = page.get_by_test_id("beast-core-checkbox-checkIcon")
                if icon.is_visible(timeout=5000):
                    icon.click(force=True)
                    time.sleep(1)  # 短等待确保勾选状态生效
                else:
                    page.evaluate(
                        "() => { const c=document.querySelector('[data-testid=\"beast-core-checkbox-checkIcon\"]'); if(c) c.click(); }")
                    time.sleep(1)

                # 【二次检测】勾选协议后可能触发广告，关闭后继续走点击逻辑
                # click_close_icon_if_exist(page)

                # 2. 核心点击逻辑：遍历匹配按钮，关闭广告后仍优先执行此逻辑，不提前兜底
                target_btns = ["进入", "进入 TEMU", "进入 常用"]
                click_success = False
                new_page = None
                for text in target_btns:
                    # 【逐次检测】每次尝试点击按钮前，检测是否有广告遮挡，关闭后再点击
                    # click_close_icon_if_exist(page)

                    try:
                        # 优先用get_by_text精准匹配，强制点击忽略遮挡
                        btn = page.get_by_text(text, exact=False).first
                        if btn.is_visible(timeout=5000):
                            with context.expect_page(timeout=10000) as new_page_info:
                                btn.click(force=True)
                            new_page = new_page_info.value
                            click_success = True
                            logger.info(f"✅ 店铺{shop_abbr} 点击「{text}」按钮成功，捕获新页面")
                            break  # 点击成功，退出按钮遍历循环
                    except Exception:
                        # CSS选择器兜底匹配，关闭广告后继续尝试
                        try:
                            css_btn = page.locator(f'button:has-text("{text}")').first
                            if css_btn.is_visible(timeout=3000):
                                with context.expect_page(timeout=10000) as new_page_info:
                                    css_btn.click(force=True)
                                new_page = new_page_info.value
                                click_success = True
                                logger.info(f"✅ 店铺{shop_abbr} CSS兜底点击「{text}」按钮成功")
                                break
                        except Exception as e2:
                            continue  # 该按钮匹配失败，继续尝试下一个

                # 3. 新页面处理：点击成功则替换page，继续后续URL校验（核心：不走兜底）
                if new_page and not new_page.is_closed():
                    page = new_page
                    # 新页面加载后最后检测一次广告，避免干扰后续URL校验
                    # click_close_icon_if_exist(page)
                    page.wait_for_load_state("domcontentloaded", timeout=15000)
                elif not click_success:
                    # 【终极兜底】仅当所有按钮点击失败时，才直接访问TEMU主页
                    logger.warning(f"⚠️ 店铺{shop_abbr} 所有「进入」按钮点击失败，无可用操作按钮，尝试直接访问TEMU主页")
                    click_close_icon_if_exist(page)  # 兜底前最后一次关广告
                    page.goto(TEMU_HOME, wait_until="domcontentloaded", timeout=20000)

            except Exception as e:
                logger.warning(f"⚠️ 店铺{shop_abbr} 授权页操作异常：{e}")
                # 异常兜底：先关广告，再尝试直接访问
                click_close_icon_if_exist(page)
                page.goto(TEMU_HOME, wait_until="domcontentloaded", timeout=20000)

        # 重构URL校验逻辑：保留原健壮特性，仅在关键节点加广告检测
        try:
            page.wait_for_url(re.compile(r"^https://agentseller\.temu\.com/?$"),
                              timeout=40000, wait_until="networkidle")

        except Exception as e:
            logger.warning(f"⚠️ 店铺{shop_abbr} TEMU 页面跳转超时，准备刷新重试 | 原始错误: {e}")
            click_close_icon_if_exist(page)  # 刷新前检测广告，避免遮挡导致刷新无效
            try:
                page.reload(wait_until="domcontentloaded", timeout=30000)
                click_close_icon_if_exist(page)  # 刷新后检测广告
                page.wait_for_url(re.compile(r"^https://agentseller\.temu\.com/?$"),
                                  timeout=40000, wait_until="networkidle")
                logger.info(f"✅ 店铺{shop_abbr} 刷新后成功跳转到 TEMU 后台")
            except Exception as retry_e:
                logger.error(f"❌ 店铺{shop_abbr} 刷新后仍未能跳转到 TEMU 后台 | 错误: {retry_e}")
                click_close_icon_if_exist(page)
                page.goto(TEMU_HOME, wait_until="networkidle", timeout=20000)
                raise

        page2 = context.new_page()

        captured_headers = {}

        def on_request(req: PWRequest):
            if "agentseller.temu.com" in req.url and req.resource_type in ("xhr", "fetch"):
                h = dict(req.headers)
                if "anti-content" in h:
                    captured_headers["anti-content"] = h["anti-content"]
                if "mallid" in h and h.get("mallid") and h["mallid"] != "undefined":
                    captured_headers["mallid"] = h["mallid"]

        page2.on("request", on_request)
        page2.goto(TEMU_HOME, wait_until="domcontentloaded")

        # ========== 第一步：获取全球区 Cookies ==========
        logger.info("\n" + "=" * 80)
        logger.info(f"🌍 第一步：获取全球区 Cookies")
        logger.info("=" * 80)

        global_cookies = cookies_from_context(context)
        logger.info(f"📊 全球区 cookies 数量：{len(global_cookies)}个")

        # 打印全球区 seller_temp
        if 'seller_temp' in global_cookies:
            global_seller_temp = global_cookies['seller_temp']
            logger.info(f"\n🔑 全球区 seller_temp:")
            logger.info(f"seller_temp = '{global_seller_temp}'\n")
        else:
            logger.warning("⚠️ 全球区 cookies 中未找到 seller_temp")
            global_seller_temp = None

        # ========== 获取多区域 Cookies ==========
        if fetch_all_region_cookies:
            # 调用独立函数获取所有区域 cookies（使用全限定名避免与参数名冲突）
            region_result = fetch_all_region_cookies_func(context, shop_abbr)
            global_cookies = region_result["global_cookies"]
            global_seller_temp = region_result["global_seller_temp"]
            us_cookies_temp = region_result["us_cookies_temp"]
            eu_cookies_temp = region_result["eu_cookies_temp"]
            page2 = region_result["page2"]
            current_url = region_result["current_url"]
            us_page = region_result["us_page"]
            eu_page = region_result["eu_page"]

            # 保存到数据库（包括全球区、美区、欧区）
            save_region_cookies_to_db(uid, global_cookies, us_cookies_temp, eu_cookies_temp, shop_abbr)
            # 使用全球区 cookies 作为默认 cookies
            cookies = global_cookies
        else:
            # 默认只获取全球区 cookies
            cookies = global_cookies
            current_url = page2.url
            us_page = None
            eu_page = None

        time.sleep(2)  # 短暂等待

        # 获取当前页面的 URL（直接使用 fetch_all_region_cookies 返回的 page2）
        current_url = page2.url
        logger.info(f"📍 店铺{shop_abbr} 当前 page2 URL: {current_url}")

        # 关键：根据 fetch_all_region_cookies 参数决定使用哪个区域的 cookies
        if fetch_all_region_cookies:
            logger.info(f"\n🔍 准备获取最终 cookies...")
            if fetch_all_region_cookies and eu_page:
                # 已获取所有区域 cookies，使用欧区
                logger.info(f"✅ 找到欧区页面：{eu_page.url}")
                target_region = "欧区"
            elif us_page:
                # 默认使用美区
                logger.info(f"✅ 找到美区页面：{us_page.url}")
                target_region = "美区"
            else:
                logger.error(f"❌ 未找到目标区域页面！")
                target_region = "未知"

            logger.info(f"   当前 page2 URL: {page2.url}")
            logger.info(f"   目标区域：{target_region}")

            # 等待 cookies 完全设置
            logger.info(f"⏳ 等待 cookies 更新...")
            time.sleep(2)  # 增加等待时间

            # 直接从 context 获取最新的 cookies，按域名过滤
            logger.info(f"🔍 正在从 context.cookies() 获取最新的美区 cookies...")
            try:
                # 获取所有域名的 cookies
                all_cookies_list = context.cookies()
                logger.info(f"📋 Context 中所有 cookies ({len(all_cookies_list)}个):")
                for c in all_cookies_list:
                    logger.info(f"   {c['name']}: domain={c.get('domain', 'N/A')}")

                # 关键：先收集所有 temu 相关的 cookies
                temu_cookies = {}
                us_seller_temp = None
                eu_seller_temp = None
                global_seller_temp_new = None

                for c in all_cookies_list:
                    domain = c.get('domain', '')
                    name = c['name']
                    value = c['value']

                    # 保存 temu 相关 cookies
                    if 'temu.com' in domain:
                        temu_cookies[name] = value

                        # 特别处理 seller_temp，根据域名区分
                        if name == 'seller_temp':
                            if 'agentseller-us.temu.com' in domain:
                                us_seller_temp = value
                                logger.info(f"\n✅ 找到美区 seller_temp (domain={domain})")
                            elif 'agentseller-eu.temu.com' in domain:
                                eu_seller_temp = value
                                logger.info(f"✅ 找到欧区 seller_temp (domain={domain})")
                            elif 'agentseller.temu.com' in domain and 'us' not in domain and 'eu' not in domain:
                                global_seller_temp_new = value
                                logger.info(f"✅ 找到全球区 seller_temp (domain={domain})")

                # 根据目标区域选择对应的 seller_temp
                if target_region == "欧区" and eu_seller_temp:
                    temu_cookies['seller_temp'] = eu_seller_temp
                    logger.info(f"💡 已选择欧区 seller_temp")
                elif target_region == "美区" and us_seller_temp:
                    temu_cookies['seller_temp'] = us_seller_temp
                    logger.info(f"💡 已选择美区 seller_temp")
                elif global_seller_temp_new:
                    temu_cookies['seller_temp'] = global_seller_temp_new
                    logger.info(f"💡 已选择全球区 seller_temp")

                # 创建当前 region 的 cookies 副本
                us_cookies = temu_cookies.copy()
                logger.info(f"\n✅ 从 context.cookies() 过滤出 {len(us_cookies)} 个 temu cookies")

                # 同时保存美区和欧区的独立副本（用于后续打印）
                us_cookies_final = temu_cookies.copy()
                eu_cookies_final = eu_cookies_temp.copy() if eu_cookies_temp else temu_cookies.copy()
                logger.info(f"✅ 已保存美区 cookies 副本（{len(us_cookies_final)}个）")
                logger.info(f"✅ 已保存欧区 cookies 副本（{len(eu_cookies_final)}个）")

            except Exception as e:
                logger.error(f"❌ 获取 cookies 失败：{e}")
                us_cookies = {}
                us_cookies_final = {}
                eu_cookies_final = eu_cookies_temp.copy() if eu_cookies_temp else {}

            # 关键：尝试从页面 JavaScript 中读取最新的 seller_temp
            try:
                logger.info(f"🔍 店铺{shop_abbr} 正在从页面 JavaScript 中读取最新的 seller_temp...")

                # 获取页面上的所有 cookies
                all_page_cookies = page2.evaluate("() => document.cookie")
                logger.info(f"📋 页面 JavaScript 中的所有 cookies:")
                logger.info(f"{all_page_cookies}")

                # 解析 seller_temp
                js_seller_temp = page2.evaluate(
                    "() => document.cookie.split('; ').find(row => row.startsWith('seller_temp='))?.split('=')[1]")
                if js_seller_temp:
                    logger.info(f"✅ 从页面读取到 seller_temp: {js_seller_temp[:80]}...")
                    # 对比并输出详细信息
                    if 'seller_temp' in us_cookies:
                        context_val = us_cookies['seller_temp']
                        logger.info(f"\n🔍 详细对比：")
                        logger.info(f"   Context seller_temp: {context_val}")
                        logger.info(f"   Page seller_temp:    {js_seller_temp}")
                        logger.info(f"   是否相同：{context_val == js_seller_temp}")

                        # 如果不一致，使用页面的最新值
                        if js_seller_temp != context_val:
                            logger.warning(f"⚠️ 检测到 seller_temp 不一致！")
                            logger.info(f"💡 将使用页面中的最新值")
                            us_cookies['seller_temp'] = js_seller_temp
                            logger.success(f"✅ 已更新 us_cookies 中的 seller_temp")
                            # 同步更新 us_cookies_final
                            if 'us_cookies_final' in dir() and us_cookies_final:
                                us_cookies_final['seller_temp'] = js_seller_temp
                                logger.success(f"✅ 已同步更新 us_cookies_final 中的 seller_temp")
                        else:
                            logger.info(f"ℹ️  Page 和 Context 的 seller_temp 完全一致")
                else:
                    logger.warning(f"⚠️ 页面中未找到 seller_temp")
            except Exception as js_e:
                logger.warning(f"⚠️ 从页面读取 seller_temp 失败：{js_e}")

        # 打印美区 seller_temp
        if fetch_all_region_cookies:
            if 'seller_temp' in us_cookies:
                us_seller_temp = us_cookies['seller_temp']
                logger.info(f"\n🔑 美区 seller_temp:")
                logger.info(f"seller_temp = '{us_seller_temp}'\n")
            else:
                logger.warning("⚠️ 美区 cookies 中未找到 seller_temp")
                us_seller_temp = None

        # ========== 第三步：对比两个区域的 Cookies ==========
        if fetch_all_region_cookies:
            logger.info("\n" + "=" * 80)
            logger.info(f"🔍 第三步：对比全球区和美区 Cookies 差异")
            logger.info("=" * 80)

            # 对比 seller_temp
            if global_seller_temp and us_seller_temp:
                if global_seller_temp == us_seller_temp:
                    logger.warning("⚠️ 全球区和美区的 seller_temp 完全相同")
                    logger.info("💡 说明：TEMU 区域切换通过 URL 和 Headers 实现，而非 Cookies")
                    logger.info("📊 最终会使用美区的 origin/referer headers 进行 API 调用")
                else:
                    logger.success("✅ 全球区和美区的 seller_temp 不同，可以无缝切换")
                    logger.info(f"\n📊 差异对比：")
                    logger.info(f"   全球区 seller_temp 长度：{len(global_seller_temp)}")
                    logger.info(f"   美区 seller_temp 长度：{len(us_seller_temp)}")

                    # 简单分析差异
                    if '"US"' in us_seller_temp or '"region":"US"' in us_seller_temp:
                        logger.info(f"   ✅ 美区 seller_temp 包含 'US' 标识")
                    if '"CN"' in global_seller_temp or '"region":"CN"' in global_seller_temp:
                        logger.info(f"   ✅ 全球区 seller_temp 包含 'CN' 标识")
            else:
                logger.warning("⚠️ 无法对比：至少一个区域的 seller_temp 为空")

            # 显示前 5 个变化的 cookies
            changed_cookies = []
            for key in global_cookies.keys():
                if key in us_cookies and global_cookies[key] != us_cookies[key]:
                    changed_cookies.append(key)

            if changed_cookies:
                logger.info(f"\n📝 发现 {len(changed_cookies)} 个 cookies 发生变化（前 5 个）：")
                for cookie_name in changed_cookies[:5]:
                    logger.info(f"   {cookie_name}:")
                    logger.info(f"      全球区：{global_cookies[cookie_name][:60]}...")
                    logger.info(f"      美区：  {us_cookies[cookie_name][:60]}...")
            else:
                logger.info("💡 所有 cookies 均未变化，这是正常的")
                logger.info("   TEMU 通过 Headers 中的 origin/referer 区分区域，而非 cookies")

        # ========== 第四步：格式化打印三个区域的 Cookies ==========
        if fetch_all_region_cookies:
            logger.info("\n" + "=" * 80)
            logger.info(f"📋 第四步：格式化打印 Cookies（Python 可用格式）")
            logger.info("=" * 80)

            # 打印全球区 cookies
            print("\n" + "#" * 80)
            print("# ========== 全球区 Cookies（原始状态） ==========")
            print(f"global_cookies = {global_cookies}")
            print("# " + "=" * 80)

            print("\n" + "#" * 80)
            print("# ========== 美区 Cookies（点击美国后） ==========")
            print("us_cookies = ", us_cookies_temp)
            print("# " + "=" * 80)

            print("\n" + "#" + "=" * 80)
            print("# ========== 欧区 Cookies（点击欧区后） ==========")
            print("eu_cookies = ", eu_cookies_temp)
            print("# " + "=" * 80 + "\n")

            db.execute_sql(
                "update shops set cookies_us = ? where uid = ?",
                params=(json.dumps(us_cookies_temp), uid),
                fetch="none")

            db.execute_sql(
                "update shops set cookies_eu = ? where uid = ?",
                params=(json.dumps(eu_cookies_temp), uid),
                fetch="none")

        # 组装结果
        # 根据当前页面设置正确的 origin 和 referer
        if "agentseller-us.temu.com" in current_url:
            headers = {
                "accept": "*/*",
                "content-type": "application/json",
                "origin": "https://agentseller-us.temu.com",
                "referer": "https://agentseller-us.temu.com/",
                "user-agent": "Mozilla/5.0",
            }
        elif "agentseller-eu.temu.com" in current_url:
            headers = {
                "accept": "*/*",
                "content-type": "application/json",
                "origin": "https://agentseller-eu.temu.com",
                "referer": "https://agentseller-eu.temu.com/",
                "user-agent": "Mozilla/5.0",
            }
        else:
            headers = {
                "accept": "*/*",
                "content-type": "application/json",
                "origin": "https://agentseller.temu.com",
                "referer": "https://agentseller.temu.com/",
                "user-agent": "Mozilla/5.0",
            }

        if "anti-content" in captured_headers:
            headers["anti-content"] = captured_headers["anti-content"]

        userinfo = get_mallid_from_userinfo(headers, cookies)
        copyMallId = userinfo.get("mallId")
        mallName = userinfo.get("mallName")
        mallid = captured_headers.get("mallid") or copyMallId
        if mallid:
            headers["mallid"] = mallid
            headers["mallName"] = mallName
            logger.success(f"✅ 店铺{shop_abbr} 登录成功（账号：{username}）")

        # 构建 requests Session
        sess = requests.Session()
        sess.headers.update(headers)
        sess.headers["mallName"] = mallName
        for k, v in cookies.items():
            sess.cookies.set(k, v)

        if cookies is None:
            logger.warning(f"⚠️ 店铺{shop_abbr} 登录结束，未获取到 Cookies")

        # 返回结果
        return {
            "headers": headers,
            "cookies": global_cookies,
            "mallid": mallid,
            "mallName": mallName,
            "thread_name": thread_name,
            "username": username
        }

    except Exception as e:
        logger.error(f"❌ 店铺{shop_abbr or ''} 登录失败（账号：{username}）：{e}", exc_info=True)
        raise
    finally:
        if context and auto_close:
            try:
                if context.pages:
                    for page in context.pages:
                        try:
                            page.close()
                        except:
                            pass
                context.close()
                logger.info(f"✅ 店铺{shop_abbr} 浏览器上下文已关闭（账号：{username}）")
            except Exception as e:
                logger.warning(f"⚠️ 店铺{shop_abbr} 关闭上下文失败：{e}")

        if 'playwright' in locals() and auto_close:
            try:
                if playwright._impl_obj and hasattr(playwright._impl_obj, '_stop'):
                    playwright.stop()
                logger.info(f"✅ 店铺{shop_abbr} Playwright 实例已停止（账号：{username}）")
            except Exception as e:
                logger.warning(f"⚠️ 店铺{shop_abbr} 停止Playwright失败：{e}")


# ============================================================
# 测试入口（适配多线程任务调度）
# ============================================================
if __name__ == "__main__":
    logger.remove()
    logger.add(
        sys.stderr,
        level="TRACE",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | 线程[{thread}] | {message}",
        extra={"thread": threading.current_thread().name}
    )

    # 测试任务配置
    task_kwargs1 = {
        "username": "17373633554",
        "password": "JishuDE3554",
        "headless": False,
        "shop_abbr": "test_shop1",
        "auto_close": True
    }
    task_kwargs2 = {
        "username": "13079867019",
        "password": "Jishu111",
        "headless": False,
        "shop_abbr": "test_shop2",
        "auto_close": True
    }

    # 添加任务到任务管理器（多线程执行）
    success1 = MAIN_TASK_MANAGER.add_task(
        task_id=f"login_{task_kwargs1['username']}",
        target_func=create_temu_session,
        **task_kwargs1
    )
    success2 = MAIN_TASK_MANAGER.add_task(
        task_id=f"login_{task_kwargs2['username']}",
        target_func=create_temu_session, **task_kwargs2
    )

    logger.info(f"✅ 任务添加状态：账号17373633554={success1}，账号13079867019={success2}")

    # 循环打印任务状态
    while True:
        time.sleep(5)
        all_tasks = MAIN_TASK_MANAGER.get_all_tasks()
        logger.info(f"📋 当前任务列表（共{len(all_tasks)}个）：{all_tasks}")
        for task_id in all_tasks:
            print(f"任务ID：{task_id} | 状态：执行中/已完成")
