import inspect
import random
import threading
import time
from typing import Dict

import psutil
from loguru import logger


def apply_stealth_to_page(page):
    """
    🔥 终极 Playwright Stealth 注入脚本（同步版）
    目标：让页面认为你是一个「普通 Windows Chrome 用户」
    适用于 TEMU / SHEIN / Amazon / TikTok 等高防网站
    """
    page.add_init_script("""
    // =============== 1. 清除自动化标志 ===============
    try { delete navigator.__proto__.webdriver; } catch (e) {}
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

    // =============== 2. 隐藏 chrome.runtime（关键！） ===============
    if (window.chrome && window.chrome.runtime) {
        // 不直接 delete，避免某些网站 JS 崩溃
        const runtime = window.chrome.runtime;
        if (runtime && typeof runtime.connect === 'function') {
            // 如果是真实 runtime，保留但隐藏敏感属性
            try {
                Object.defineProperty(runtime, 'id', { value: '' });
                Object.defineProperty(runtime, 'manifest', { value: {} });
            } catch (e) {}
        } else {
            // 自动化环境常见：无 connect 方法 → 直接隐藏
            Object.defineProperty(window.chrome, 'runtime', {
                value: undefined,
                writable: true,
                configurable: true,
                enumerable: false
            });
        }
    }

    // =============== 3. 模拟插件和 MIME 类型（对抗 plugins.length === 0） ===============
    const fakePlugins = [
        { name: "Chrome PDF Plugin", filename: "internal-pdf-viewer" },
        { name: "Chrome PDF Viewer", filename: "mhjfbmdgcfjbbpaeojofohoefgiehjai" },
        { name: "Native Client", filename: "internal-nacl-plugin" }
    ];
    Object.defineProperty(navigator, 'plugins', {
        get: () => fakePlugins
    });
    Object.defineProperty(navigator, 'mimeTypes', {
        get: () => [
            { type: "application/pdf", suffixes: "pdf" },
            { type: "application/x-google-chrome-pdf", suffixes: "pdf" },
            { type: "application/x-nacl", suffixes: "" }
        ]
    });

        // =============== 4. 修复 permissions API 行为 ===============
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = function(parameters) {
        return new Promise(resolve => {
            let state = 'denied';
            if (parameters.name === 'notifications') {
                state = Notification.permission || 'denied';
            } else if (['geolocation', 'camera', 'microphone'].includes(parameters.name)) {
                state = 'prompt';
            }
            resolve({
                state: state,
                onchange: null,
                name: parameters.name
            });
        });
    };

    // =============== 5. 防止 cdc_ / __SENTRY__ / _Selenium_ID 等变量检测 ===============
    const suspiciousKeys = Object.keys(window).filter(k =>
        k.startsWith('cdc_') ||
        k.startsWith('__SENTRY__') ||
        k.includes('Selenium') ||
        k.includes('selenium')
    );
    suspiciousKeys.forEach(k => delete window[k]);

    // =============== 6. 伪造硬件与语言信息 ===============
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    
        // =============== 伪造网络连接信息 ===============
    if (!navigator.connection) {
        Object.defineProperty(navigator, 'connection', {
            value: {
                effectiveType: '4g',
                rtt: 50,
                downlink: 10,
                saveData: false
            },
            writable: true,
            configurable: true
        });
    }

    // =============== 7. WebGL 厂商伪装（对抗 Canvas/WebGL 指纹） ===============
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(param) {
        if (param === 37445) return 'Google Inc. (Intel)';
        if (param === 37446) return 'ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11-Feature Level)';
        return getParameter.call(this, param);
    };

    // =============== 8. 禁用 navigator.brave（如果存在） ===============
    if (navigator.brave) {
        Object.defineProperty(navigator, 'brave', {
            value: undefined,
            writable: true,
            configurable: true
        });
    }

    // =============== 9. 修复 toString 检测（部分网站会检测函数是否被重写） ===============
    const originalToString = Function.prototype.toString;
    Function.prototype.toString = function() {
        if (this === window.navigator.permissions.query) {
            return 'function query() { [native code] }';
        }
        if (this === WebGLRenderingContext.prototype.getParameter) {
            return 'function getParameter() { [native code] }';
        }
        return originalToString.call(this);
    };

    // =============== 10. 防止 iframe 检测 top !== self（可选） ===============
    try {
        Object.defineProperty(window, 'top', {
            get: () => window,
            configurable: false,
            writable: false
        });
    } catch (e) {}

    """)


def human_type(locator, text: str):
    locator.click()  # 先聚焦
    for char in text:
        locator.press(char)
        time.sleep(random.uniform(0.05, 0.2))  # 模拟打字节奏


def kill_occupied_chrome_processes(username: str, uid: str) -> None:
    """
    检测并杀死所有占用指定账号/uid浏览器目录的Chrome进程
    :param username: 账号（手机号）
    :param uid: 店铺UID
    """
    thread_name = threading.current_thread().name
    target_dir = f"user_{username}_uid_{uid}"  # 匹配用户目录关键词

    # 遍历所有进程，精准杀死占用该目录的Chrome
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'chrome.exe' in proc.info['name']:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if target_dir in cmdline and proc.is_running():
                    # 先尝试优雅终止，失败则强制杀死
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)  # 等待进程退出
                    except psutil.TimeoutExpired:
                        proc.kill()
                    logger.info(f"🗑️ 线程[{thread_name}] 杀死占用目录的Chrome进程(pid={proc.info['pid']})")
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception) as e:
            logger.warning(f"⚠️ 线程[{thread_name}] 处理进程失败: {e}")


def launch_persistent_context_compat(browser, **kwargs):
    sig = inspect.signature(browser.launch_persistent_context)
    if "userdata_dir" in sig.parameters:
        kwargs["userdata_dir"] = kwargs.pop("user_data_dir", kwargs.get("user_data_dir", None))
    else:
        kwargs["user_data_dir"] = kwargs.pop("userdata_dir", kwargs.get("userdata_dir", None))
    return browser.launch_persistent_context(**kwargs)


def cookies_from_context(context) -> Dict[str, str]:
    """将Playwright上下文的Cookies转换为简单字典（便于存储）"""
    try:
        return {c["name"]: c["value"] for c in context.cookies()}
    except Exception:
        return {}


def convert_dict_to_playwright_cookies(cookies_dict: Dict[str, str]) -> list:
    """
    将简单字典格式的Cookies转换为Playwright要求的列表格式
    :param cookies_dict: {"name1": "value1", "name2": "value2"}
    :return: [{"name": "name1", "value": "value1", "domain": ".agentseller.temu.com", ...}, ...]
    """
    TEMU_COOKIE_DOMAIN = ".agentseller.temu.com"
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


def click_close_icon_if_exist(page, timeout=3000, check_interval=300):
    """
    检测广告关闭叉叉并点击：存在则点击，不存在则轮询等待，超时则放弃
    :param page: Playwright Page实例
    :param timeout: 最大等待超时时间（毫秒），默认10秒
    :param check_interval: 轮询检测间隔（毫秒），默认1秒
    """
    start_time = time.time()
    # 拼接CSS选择器：匹配包含指定class的span + 内部svg（精准定位目标叉叉）
    close_selector = 'span.use-check-bill_dialogClose__1O_sx svg'

    while True:
        # 计算已等待时间，超时则退出
        elapsed_time = (time.time() - start_time) * 1000
        if elapsed_time > timeout:
            # logger.info(f"⏱️  超过{timeout / 1000}秒未检测到广告关闭叉叉，停止检测")
            break

        try:
            # 检测元素是否存在且可见（state="visible" 确保元素可点击）
            close_icon = page.locator(close_selector)
            if close_icon.count() > 0 and close_icon.is_visible():
                # 强制点击（忽略遮挡/不可交互，适配弹窗元素）
                close_icon.click(force=True)
                logger.info("✅ 检测到广告关闭叉叉，已成功点击")
                break
            # else:
                # logger.debug(f"🔍 未检测到可见的广告关闭叉叉，{check_interval / 1000}秒后重试")
        except Exception as e:
            logger.debug(f"🔍 检测叉叉时临时异常：{str(e)[:50]}，{check_interval / 1000}秒后重试")

        # 未检测到，等待指定间隔后继续轮询
        time.sleep(check_interval / 1000)
