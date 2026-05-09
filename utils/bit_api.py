import json

import requests

# 官方文档地址
# https://doc2.bitbrowser.cn/jiekou/ben-di-fu-wu-zhi-nan.html

# 此demo仅作为参考使用，以下使用的指纹参数仅是部分参数，完整参数请参考文档

BIT_BROWSER_API = "http://127.0.0.1:54345"
headers = {'Content-Type': 'application/json'}


def createBrowser():  # 创建或者更新窗口，指纹参数 browserFingerPrint 如没有特定需求，只需要指定下内核即可，如果需要更详细的参数，请参考文档
    json_data = {
        'name': 'google',  # 窗口名称
        'remark': '',  # 备注
        'proxyMethod': 2,  # 代理方式 2自定义 3 提取IP
        # 代理类型  ['noproxy', 'http', 'https', 'socks5', 'ssh']
        'proxyType': 'noproxy',
        'host': '',  # 代理主机
        'port': '',  # 代理端口
        'proxyUserName': '',  # 代理账号
        "browserFingerPrint": {  # 指纹对象
            'coreVersion': '124'  # 内核版本，注意，win7/win8/winserver 2012 已经不支持112及以上内核了，无法打开
        }
    }

    res = requests.post(f"{BIT_BROWSER_API}/browser/update",
                        data=json.dumps(json_data), headers=headers).json()
    browserId = res['data']['id']
    print(browserId)
    return browserId


def updateBrowser():  # 更新窗口，支持批量更新和按需更新，ids 传入数组，单独更新只传一个id即可，只传入需要修改的字段即可，比如修改备注，具体字段请参考文档，browserFingerPrint指纹对象不修改，则无需传入
    # json_data = {'ids': ['93672cf112a044f08b653cab691216f0'],
    #              'remark': '我是一个备注', 'browserFingerPrint': {}}
    json_data = {
  "ids": ['bbe47cb7f04c429b81830e70aa096430'],
  "browserFingerPrint": {
    "coreProduct": "chrome",
    "coreVersion": "128",
    "ostype": "PC",
    "os": "Win32",
    "osVersion": "10"
  },
  "workbench": "localserver"
}
    res = requests.post(f"{BIT_BROWSER_API}/browser/update/partial",
                        data=json.dumps(json_data), headers=headers).json()
    print(res)


def openBrowser(id):  # 直接指定ID打开窗口，也可以使用 createBrowser 方法返回的ID
    json_data = {"id": f'{id}'}
    res = requests.post(f"{BIT_BROWSER_API}/browser/open",
                        data=json.dumps(json_data), headers=headers, timeout=10).json()
    return res


def closeBrowser(id):  # 关闭窗口
    json_data = {'id': f'{id}'}
    requests.post(f"{BIT_BROWSER_API}/browser/close",
                  data=json.dumps(json_data), headers=headers).json()


def deleteBrowser(id):  # 删除窗口
    json_data = {'id': f'{id}'}
    print(requests.post(f"{BIT_BROWSER_API}/browser/delete",
          data=json.dumps(json_data), headers=headers).json())



def list_browsers():
    """获取当前所有已启动的浏览器窗口"""
    try:
        resp = requests.get(f"{BIT_BROWSER_API}/browser/list")
        if resp.status_code == 200:
            return resp.json().get("data", [])
        return []
    except:
        return []


def is_browser_running(browser_id: str) -> bool:
    """检查指定 ID 的浏览器是否已在运行"""
    browsers = list_browsers()
    for b in browsers:
        if b.get("id") == browser_id and b.get("status") == "running":
            return True
    return False


def get_browser_ws(browser_id: str):
    """安全获取 browser_id 对应的 WebSocket 地址（不启动新窗口）"""
    # 先检查是否已在运行
    if is_browser_running(browser_id):
        # 直接从 list 接口拿 ws（部分版本支持）
        browsers = list_browsers()
        for b in browsers:
            if b.get("id") == browser_id:
                # 有些版本返回 webSocketDebuggerUrl
                ws = b.get("webSocketDebuggerUrl")
                if ws:
                    return ws
                # 否则 fallback 到 openBrowser（但设置 reuse）

    # 如果没在运行，或拿不到 ws，才尝试 open（带 reuse 参数）
    try:
        # 注意：新版 BitBrowser 支持 reuse=true
        resp = requests.post(
            f"{BIT_BROWSER_API}/browser/open",
            json={"id": browser_id, "reuse": True}
        )
        data = resp.json()
        if data.get("success"):
            return data["data"]["ws"]
    except Exception as e:
        print(f"⚠️ 获取 WebSocket 失败: {e}")

    raise RuntimeError(f"无法获取 browser_id={browser_id} 的浏览器id，请检查浏览器id是否正确，确保窗口已手动启动并登录，如果仍然报错请检查比特浏览器窗口启动次数是否达到上限！或本次使用的浏览器id是否为当前比特浏览器程序的账号！")


if __name__ == '__main__':
    # print("创建窗口")
    # browser_id = createBrowser()
    # openBrowser(browser_id)
    #
    # time.sleep(10)  # 等待10秒自动关闭窗口
    #
    # print("关闭窗口")
    # closeBrowser(browser_id)
    #
    # time.sleep(10)  # 等待10秒自动删掉窗口
    #
    # print("删除窗口")
    # deleteBrowser(browser_id)
    #
    # print("结束")
    browser_id = "bbe47cb7f04c429b81830e70aa096430"
    resp = is_browser_running(browser_id)
    print(resp)
