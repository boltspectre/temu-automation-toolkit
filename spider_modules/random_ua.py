import random
from faker import Faker  # 需要安装faker库: pip install faker

# 初始化Faker用于生成更真实的URL等信息
fake = Faker()


def generate_random_headers():
    # 浏览器User-Agent列表 - 扩充了更多版本和类型
    user_agents = {
        # Chrome - 增加更多版本和平台
        "chrome": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_16_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:109.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        ],

        # Firefox - 增加更多版本
        "firefox": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:102.0) Gecko/20100101 Firefox/102.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:103.0) Gecko/20100101 Firefox/103.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:104.0) Gecko/20100101 Firefox/104.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:101.0) Gecko/20100101 Firefox/101.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:102.0) Gecko/20100101 Firefox/102.0",
            "Mozilla/5.0 (X11; Linux x86_64; rv:102.0) Gecko/20100101 Firefox/102.0"
        ],

        # Safari - 增加移动和桌面版本
        "safari": [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Safari/605.1.15",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (iPad; CPU OS 16_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Mobile/15E148 Safari/604.1"
        ],

        # Edge - 增加更多版本
        "edge": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Edge/114.0.1823.51",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Edge/113.0.1774.57",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Edge/115.0.1901.203"
        ],

        # 移动设备浏览器
        "mobile": [
            "Mozilla/5.0 (Linux; Android 13; SM-G998B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
            "Mozilla/5.0 (Linux; Android 12; SM-S906N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
            "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/112.0.5615.101 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (iPad; CPU OS 16_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/112.0.5615.101 Mobile/15E148 Safari/604.1"
        ]
    }

    # 随机选择浏览器类型
    browser_type = random.choices(
        ["chrome", "firefox", "safari", "edge", "mobile"],
        weights=[0.4, 0.2, 0.1, 0.1, 0.2],  # 权重分配，Chrome和移动设备更常见
        k=1
    )[0]

    # 选择对应的User-Agent
    user_agent = random.choice(user_agents[browser_type])

    # 可接受的内容类型 - 更丰富的选项
    accept_types = [
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "application/json, text/plain, */*",
        "text/plain;q=0.9,text/html;q=0.8,*/*;q=0.7",
        "application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5",
        "image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
    ]

    # 语言 - 增加更多地区和组合
    languages = [
        "zh-CN,zh;q=0.9,en;q=0.8",
        "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "en-US,en;q=0.9,zh-CN;q=0.8",
        "en-GB,en;q=0.9,zh-CN;q=0.8,en-US;q=0.7",
        "ja-JP,ja;q=0.9,en;q=0.8,zh;q=0.7",
        "ko-KR,ko;q=0.9,en;q=0.8,zh;q=0.7",
        "fr-FR,fr;q=0.9,en;q=0.8",
        "de-DE,de;q=0.9,en;q=0.8"
    ]

    # 编码
    encodings = [
        "gzip, deflate, br",
        "gzip, deflate",
        "deflate, gzip",
        "br, gzip, deflate"
    ]

    # 常见的Referer网站
    referrers = [
        fake.uri(),  # 随机生成一个合理的URL
        "https://www.google.com/",
        "https://www.baidu.com/",
        "https://www.bing.com/",
        "https://www.yahoo.com/",
        "https://www.qq.com/",
        "https://www.sina.com.cn/",
        "https://www.taobao.com/",
        "https://www.jd.com/"
    ]

    # 生成基础请求头
    headers = {
        "User-Agent": user_agent,
        "Accept": random.choice(accept_types),
        "Accept-Language": random.choice(languages),
        "Accept-Encoding": random.choice(encodings),
        "Connection": random.choice(["keep-alive", "close"]),
        "Cache-Control": random.choice(["no-cache", "max-age=0", "private, max-age=0", "max-age=3600"]),
    }

    # 根据浏览器类型添加特定头信息，使请求头更真实
    if browser_type in ["chrome", "edge", "mobile"]:
        # Chrome/Edge特有的头信息
        headers["Upgrade-Insecure-Requests"] = "1" if random.random() > 0.2 else "0"
        headers["DNT"] = "1" if random.random() > 0.3 else "0"  # Do Not Track，1更常见

        # 随机添加Sec-Fetch-*头信息（Chrome等现代浏览器）
        if random.random() > 0.2:
            headers["Sec-Fetch-Dest"] = random.choice(["document", "empty", "image", "script"])
            headers["Sec-Fetch-Mode"] = random.choice(["navigate", "no-cors", "cors"])
            headers["Sec-Fetch-Site"] = random.choice(["same-origin", "cross-site", "none", "same-site"])
            headers["Sec-Fetch-User"] = "?1" if headers["Sec-Fetch-Mode"] == "navigate" else "?0"

    elif browser_type == "firefox":
        # Firefox特有的头信息
        headers["Upgrade-Insecure-Requests"] = "1" if random.random() > 0.3 else "0"
        headers["DNT"] = "1" if random.random() > 0.4 else "0"
        headers["TE"] = "trailers" if random.random() > 0.3 else "identity"

    elif browser_type == "safari":
        # Safari特有的头信息
        headers["Upgrade-Insecure-Requests"] = "1" if random.random() > 0.4 else "0"
        headers["DNT"] = "1" if random.random() > 0.5 else "0"

    # 随机添加Referer（大多数请求会有）
    # if random.random() > 0.2:  # 80%的概率添加Referer
    #     headers["Referer"] = random.choice(referrers)

    # 随机添加Origin头（通常在POST请求中出现）
    # if random.random() > 0.7:  # 30%的概率添加Origin
    #     origin = fake.uri()
    #     # 确保origin是域名形式，没有路径
    #     if '/' in origin:
    #         origin = origin.split('/', 3)[0] + '//' + origin.split('/', 3)[2]
    #     headers["Origin"] = origin

    # 随机添加内容类型（POST请求更常见）
    if random.random() > 0.5:  # 50%的概率添加Content-Type
        content_types = [
            "application/json",
            "application/x-www-form-urlencoded",
            "multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW",
            "text/plain; charset=UTF-8",
            "application/xml; charset=UTF-8"
        ]
        headers["Content-Type"] = random.choice(content_types)

    # 随机添加其他常见头信息
    # other_headers = {
    #     "Pragma": random.choice(["no-cache", ""]),
    #     "X-Requested-With": "XMLHttpRequest" if random.random() > 0.7 else "",
    #     "If-Modified-Since": fake.date_time_this_year().strftime(
    #         "%a, %d %b %Y %H:%M:%S GMT") if random.random() > 0.8 else "",
    #     "Cookie": f"sessionid={fake.uuid4()}; user_id={fake.random_int(1000, 99999)}; preferences={fake.md5()}" if random.random() > 0.6 else ""
    # }

    # 添加非空的额外头信息
    # for key, value in other_headers.items():
    #     if value:
    #         headers[key] = value

    return headers


# 生成并打印随机请求头
if __name__ == "__main__":
    for i in range(3):
        print(f"第{i + 1}个随机请求头:")
        headers = generate_random_headers()
        for key, value in headers.items():
            print(f"  {key}: {value}")
        print()  # 空行分隔
