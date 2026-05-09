# bitClient.py
import threading
import time

import requests
from loguru import logger
from playwright.sync_api import sync_playwright

from utils.bit_browser_starter import execute_flow

thread_local = threading.local()

def get_cookies(context):
    """获取当前上下文的所有 cookies"""
    cookies = context.cookies()
    return {c['name']: c['value'] for c in cookies}


# ====== 全局客户端管理（只初始化一次） ======
class _TemuSession:
    def __init__(self, browser_id: str):
        logger.info("🔍 尝试连接已运行的 BitBrowser 实例（不启动新窗口）...")
        self.session = requests.Session()
        self.browser_id = browser_id
        self._p = sync_playwright().start()

        # 只获取已有窗口的 WebSocket
        from utils.bit_api import get_browser_ws
        ws = get_browser_ws(browser_id)
        # print(f"🔗 已连接到 WebSocket: {ws}")

        # 通过 CDP 连接已有浏览器
        self._browser = self._p.chromium.connect_over_cdp(ws)
        self._context = self._browser.contexts[0]
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()

        # 确保在卖家中心页面（避免在登录页）
        # if "agentseller.temu.com" not in self._page.url:
        #     print("🌐 当前不在卖家中心，正在跳转...")
        #     self._page.goto("https://agentseller.temu.com", timeout=30000)

        self._session_lock = threading.Lock()  # 实例级锁，非全局
        self._last_headers = {}
        self._last_cookies = {}
        self._last_refresh = 0
        self._max_age = 600

    def _harvest(self):
        # 核心修改2：加实例锁，确保同一浏览器ID的_harvest串行执行
        with self._session_lock:
            try:
                # 检查页面是否有效，无效则重建（避免操作已关闭的页面）
                if self._page is None or self._page.is_closed() or not self._browser.is_connected():
                    logger.warning(f"⚠️ 浏览器 {self.browser_id} 连接失效，重建Page...")
                    # 重新连接浏览器
                    from utils.bit_api import get_browser_ws
                    ws = get_browser_ws(self.browser_id)
                    self._browser = self._p.chromium.connect_over_cdp(ws)
                    self._context = self._browser.contexts[0]
                    self._page = self._context.pages[0] if self._context.pages else self._context.new_page()

                # 执行原有逻辑，提取最新headers/cookies
                self._last_headers = execute_flow(self._page)
                if self._last_headers['mallid'] == "" or self._last_headers['mallid'] == 'undefined':
                    # logger.error("❌请先登录")
                    raise Exception("❌请先登录")

                self._last_cookies = get_cookies(self._context)
                self._last_refresh = time.time()
                # 返回副本，避免外部修改原数据
                return self._last_headers.copy(), self._last_cookies.copy()

            except Exception as e:
                # logger.error(f"🚨 _harvest 失败: {str(e)}")
                # 如果是连接错误，标记页面失效
                if "EPIPE" in str(e) or "Target closed" in str(e) or "not connected" in str(e):
                    logger.warning("⚠️ 浏览器连接已断，下次将重建")
                    self._page = None
                    self._context = None
                    self._browser = None
                raise

    def get_latest_credentials(self):
        """返回有效凭证，过期则自动刷新（加锁保护读写）"""
        # 核心修改3：加实例锁，避免读取到半更新的凭证
        with self._session_lock:
            if time.time() - self._last_refresh > self._max_age:
                return self._harvest()
            # 返回副本，避免外部修改原数据
            return self._last_headers.copy(), self._last_cookies.copy()


    def close(self):
        # 核心修改4：关闭时加锁，避免并发关闭冲突
        with self._session_lock:
            try:
                if hasattr(self, '_browser') and self._browser and self._browser.is_connected():
                    # 安全关闭页面和上下文
                    if hasattr(self, '_page') and self._page and not self._page.is_closed():
                        self._page.close()
                    if hasattr(self, '_context') and self._context:
                        self._context.close()
                    self._browser.close()
            except Exception:
                pass  # 静默失败

            try:
                if hasattr(self, '_p') and self._p:
                    self._p.stop()  # 停止 Playwright 驱动
            except Exception:
                pass


# ===================== 新增：全局映射 + 锁（核心修改）=====================
# 全局字典：key=browser_id，value=_TemuSession实例（实现一个浏览器ID只初始化一次）
_BROWSER_SESSION_MAP = {}
# 全局锁：保护 _BROWSER_SESSION_MAP 的读写，避免多线程并发创建 Session
_BROWSER_SESSION_LOCK = threading.Lock()  # 仅保护Session的创建/销毁
THREAD_LOCAL = threading.local()
def _ensure_session(browser_id: str):
    """同一个浏览器ID只初始化一次 Session，所有线程共用该实例（线程安全）"""
    try:
        if not hasattr(THREAD_LOCAL, "session"):
            THREAD_LOCAL.session = {}
        # 加全局锁：仅保护Session的创建/销毁，不影响后续凭证操作
        with _BROWSER_SESSION_LOCK:
            # 1. 首次初始化Session
            if browser_id not in _BROWSER_SESSION_MAP:
                logger.info(f"📌 浏览器 {browser_id} 首次初始化 Session...")
                session = _TemuSession(browser_id)
                session._harvest()  # 初始化凭证（已加实例锁）
                _BROWSER_SESSION_MAP[browser_id] = session
            # 2. 复用已有Session
            else:
                session = _BROWSER_SESSION_MAP[browser_id]

                # 检查Session是否失效，失效则重建
                if session._page is None or not session._browser.is_connected():
                    logger.error(f"⚠️ 浏览器 {browser_id} 连接失效，重建 Session...")
                    session.close()
                    session = _TemuSession(browser_id)
                    session._harvest()
                    _BROWSER_SESSION_MAP[browser_id] = session

    except Exception as e:
        # logger.error(f"❌ 浏览器 {browser_id} 获取凭证失败: {str(e)}")
        raise e

    return _BROWSER_SESSION_MAP[browser_id]


# ========== 调整清理函数：按浏览器ID清理（可选）==========
def clean_temu_session(browser_id: str = None):
    """清理 Session 资源（加全局锁保护）"""
    with _BROWSER_SESSION_LOCK:
        if browser_id:
            if browser_id in _BROWSER_SESSION_MAP:
                _BROWSER_SESSION_MAP[browser_id].close()
                del _BROWSER_SESSION_MAP[browser_id]
                logger.info(f"🧹 浏览器 {browser_id} Session 已清理")
        else:
            for bid, session in _BROWSER_SESSION_MAP.items():
                session.close()
            _BROWSER_SESSION_MAP.clear()
            logger.info(f"🧹 所有浏览器 Session 已清理")