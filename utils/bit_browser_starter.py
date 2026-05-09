# bit_browser_starter.py
import json
import time
import webbrowser
from typing import Dict

import requests
import unicodedata
from playwright.sync_api import sync_playwright

from utils.bit_api import openBrowser


def get_user_Info(headers, cookies, shop_name):
    url = "https://agentseller.temu.com/api/seller/auth/userInfo"
    data = {}
    data = json.dumps(data, separators=(',', ':'))
    response = requests.post(url, headers=headers, cookies=cookies, data=data)
    if response.status_code == 200:
        response_json = response.json()
        result_data = response_json.get('result')
        # 获取 mallId
        mall_id_list = result_data['mallList']
        if not mall_id_list:
            return None, None, None, None
        PHONE = result_data["maskMobile"]
        for mall_id_json in mall_id_list:
            if normalize_str(mall_id_json['mallName']) == normalize_str(shop_name):
                mall_id = mall_id_json['mallId']
                mall_name = mall_id_json['mallName']
                headers['mallid'] = str(mall_id)
                return headers, mall_name, PHONE, mall_id
        return None, None, None, None
    else:
        return None, None, None, None


def normalize_str(s):
    return ''.join(
        c for c in unicodedata.normalize('NFKC', s)
        if not unicodedata.category(c).startswith('C')
    ).strip()


def get_cookies(context) -> Dict:
    """获取并组装当前浏览器上下文中的所有Cookies"""
    cookies = context.cookies()
    cookie_dict = {}
    for cookie in cookies:
        cookie_dict[cookie['name']] = cookie['value']
    return cookie_dict

def auto_get_headers(browser_id):
    with sync_playwright() as p:
        # 1. 连接 BitBrowser
        res = openBrowser(browser_id)
        ws = res['data']['ws']
        browser = p.chromium.connect_over_cdp(ws)
        context = browser.contexts[0]
        page = context.new_page()

        # 2. 自动采集带 anti-content 的 headers
        print("正在采集 headers（含 anti-content）...")
        headers = execute_flow(page)  # ← 关键！会触发页面并捕获真实请求头
        print("headers:", headers)
        # 3. 获取 cookies
        cookies = get_cookies(context)

    return cookies

class HeaderHarvester:
    def __init__(self):
        self.target_headers = [
            "accept", "accept-language", "anti-content", "cache-control",
            "content-type", "mallid", "origin", "priority", "referer",
            "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform",
            "sec-fetch-dest", "sec-fetch-mode", "sec-fetch-site", "user-agent"
        ]
        self.result = {}
        self.page = None

    def _get_mallid_from_headers(self, headers):
        for key in ['mallid', 'Mallid', 'MALLID']:
            if key in headers:
                return headers[key]
        return None

    def _request_handler(self, request):
        raw_headers = request.headers
        if raw_headers.get("anti-content"):  # ← 关键：只要有 anti-content 就捕获
            captured = {k: raw_headers.get(k) for k in self.target_headers}
            captured["mallid"] = self._get_mallid_from_headers(raw_headers)
            self.result.update({k: v for k, v in captured.items() if v})
            # print(f"✅ 捕获 anti-content 来自: {request.url}")

    def harvest(self, page):
        self.page = page
        page.on("request", self._request_handler)

        # ========== 新增：同时打开两个页面（仅查看） ==========
        # 创建新的上下文（如果需要独立会话）或直接在当前上下文创建新页面
        # 方式1：在当前浏览器上下文创建新页面（共享登录状态，推荐）
        # page1 = page.context.new_page()
        page2 = page.context.new_page()

        # 打开第一个额外页面（实拍图合规页面）
        # page1.goto(
        #     "https://agentseller.temu.com/govern/compliant-live-photos",
        #     wait_until="load",
        #     timeout=30000
        # )
        # 打开第二个额外页面（首页）
        page2.goto(
            "https://agentseller.temu.com/",
            wait_until="load",
            timeout=30000
        )

        # 可选：让新页面保持可见（不自动关闭），你可以手动查看
        # 注：Playwright 默认会隐藏无头模式，如需可视化需启动时设置 headless=False
        # page1.bring_to_front()  # 可选：把第一个新页面置顶

        # ========== 原有核心逻辑（商品选择页面） ==========
        # 主页面跳转到目标页（保持原有逻辑）
        page.goto(
            "https://agentseller.temu.com/newon/product-select",
            wait_until="load",
            timeout=30000
        )

        # 检查是否登录
        if "login" in page.url:
            raise RuntimeError("❌ 未登录！")

        # 等待关键元素
        try:
            page.wait_for_selector("text=商品管理", timeout=10000)
        except:
            pass

        # 等待请求发出
        page.wait_for_timeout(3000)

        # 可选：如果需要让所有页面都保持打开，这里不关闭新页面
        # 如需自动关闭，可在方法结束前调用 page1.close()/page2.close()

        return self._finalize_headers()

    def _finalize_headers(self):
        essentials = {
            "content-type": "application/json",
            "origin": "https://agentseller.temu.com",
            "referer": "https://agentseller.temu.com/newon/product-select"
        }
        final = {**essentials, **self.result}
        return {k: v for k, v in final.items() if v}


def execute_flow(page):
    """主执行流程"""
    harvester = HeaderHarvester()
    headers = harvester.harvest(page)
    return headers


def open_temu_mainPage(mall_id):
    url = f"https://www.temu.com/us-zh-Hans/-m-{mall_id}.html"
    # print("正在打开网页...")
    try:
        # 打开默认浏览器并访问
        webbrowser.open(url, new=2)  # new=2 表示尽量在新标签页打开
        return True
    except Exception as e:
        print(e)
        return False


if __name__ == '__main__':
    BROWSER_ID = "e1020513ed5e41aea9ed687573d8da3b"  # 替换为你的已登录窗口ID

    with sync_playwright() as p:
        # 1. 连接 BitBrowser
        res = openBrowser(BROWSER_ID)
        ws = res['data']['ws']
        browser = p.chromium.connect_over_cdp(ws)
        context = browser.contexts[0]
        page = context.new_page()

        # 2. 自动采集带 anti-content 的 headers
        print("正在采集 headers（含 anti-content）...")
        headers = execute_flow(page)  # ← 关键！会触发页面并捕获真实请求头
        print("headers:", headers)
        # 3. 获取 cookies
        cookies = get_cookies(context)

        browser.close()

    # 4. 构造最终请求（使用采集到的 headers + cookies）
    url = "https://agentseller.temu.com/api/kiana/mms/robin/searchForChainSupplier"
    payload = {"pageSize":10,"pageNum":1,"supplierTodoTypeList":[]}

    for i in range(1, 100):
        print("当前第",i,"次")
        response = requests.post(
            url,
            headers=headers,
            cookies=cookies,
            json=payload,  # 自动设置 Content-Type 和序列化
            timeout=10
        )

        print("状态码:", response.status_code)
        # print("响应:", response.json())
        if response.json()['result']:
            print("成功获取数据！")
        if i > 95:
            print("响应:", response.json())

        time.sleep(1)