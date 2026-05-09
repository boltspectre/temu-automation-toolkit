# send_temu_req.py
import random
import threading
import time
from typing import Any

import requests
from loguru import logger

from config.common_config import db

# 全局字典记录限流状态：key=店铺/URL组合，value={count: 触发次数, last_time: 最后触发时间}
RATE_LIMIT_STATUS = {}
# 锁：保证多线程下操作RATE_LIMIT_STATUS的线程安全
RATE_LIMIT_LOCK = threading.RLock()
# 基础配置
BASE_WAIT_TIME = 10  # 初始等待时间（秒）
MAX_WAIT_TIME = 120  # 最大等待时间（秒）
RESET_INTERVAL = 300  # 5分钟未触发则重置计数（秒）
WAIT_MULTIPLIER = 1.2  # 每次触发的等待时间倍数（首次5s，第二次10s，第三次20s...）



def generate_fixed_random_ua(seed_num: int) -> str:
    rng = random.Random(seed_num)

    # 更真实的版本生成（确定性）
    def gen_chrome_version(rng_obj):
        major = 120 + (rng_obj.randint(0, 15))  # 120 ～ 135
        minor = rng_obj.randint(0, 9)
        build = 5000 + rng_obj.randint(0, 2000)
        patch = rng_obj.randint(0, 300)
        return f"{major}.{minor}.{build}.{patch}"

    os_options = [
        ("Windows NT 10.0; Win64; x64", 0.6),
        ("Windows NT 11.0; Win64; x64", 0.25),
        ("Windows NT 10.0; WOW64", 0.1),
        ("Macintosh; Intel Mac OS X 10_15_7", 0.04),
        ("X11; Linux x64_86", 0.01)
    ]
    os_weights = [w for _, w in os_options]
    os_strings = [s for s, _ in os_options]
    os_ver = rng.choices(os_strings, weights=os_weights, k=1)[0]

    browser_type = rng.choices(["chrome", "edge", "firefox"], weights=[70, 20, 10], k=1)[0]

    if browser_type == "chrome":
        ver = gen_chrome_version(rng)
        return f"Mozilla/5.0 ({os_ver}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{ver} Safari/537.36"
    elif browser_type == "edge":
        chrome_ver = gen_chrome_version(rng)
        # Edge version ≈ Chrome version - small offset
        edge_major = int(chrome_ver.split('.')[0])
        edge_ver = f"{edge_major}.0.{rng.randint(2000, 3000)}.{rng.randint(50, 150)}"
        return f"Mozilla/5.0 ({os_ver}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_ver} Safari/537.36 Edg/{edge_ver}"
    else:
        ff_major = 120 + rng.randint(0, 10)
        ff_ver = f"{ff_major}.0"
        return f"Mozilla/5.0 ({os_ver}; rv:{ff_ver}) Gecko/20100101 Firefox/{ff_ver}"



def send_req(
        uid,
        method: str,
        url: str,
        *,
        json=None,
        data=None,
        params=None,
        files=None,
        headers=None,
        cookies=None,
        timeout=35,
        max_retries=3,
        sleep_open=True,
        log: bool = True,
        append_headers=None,
) -> dict[Any, Any] | Any:
    """所有需要登录态的请求都走这里（新增动态429等待逻辑）"""
    # 1. 初始化headers
    headers = headers or {}

    # 2. 生成随机UA（有种子则用固定随机，无则用默认）
    DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    if uid:
        shop_info = db.execute_sql(
            "select * from shops WHERE uid = ?",
            params=(uid,),
            fetch="fetch_one"
        )
    else:
        print("请求中没有找到店铺信息")
        logger.info("请求中没有找到店铺信息")
        return None

    if shop_info["mall_id"] is not None:
        headers["User-Agent"] = generate_fixed_random_ua(shop_info["mall_id"])
    elif "User-Agent" not in headers:
        headers["User-Agent"] = DEFAULT_UA

    headers["mallid"] = str(shop_info["mall_id"])
    cookies["mallid"] = str(shop_info["mall_id"])

    # 3. 补充附加headers
    if append_headers is not None:
        headers.update(append_headers)

    session = requests.Session()
    if cookies:
        session.cookies.update(cookies)

    session.headers.update(headers)

    # 生成限流统计的唯一key（店铺+URL，避免不同店铺/URL互相影响）
    rate_limit_key = f"{shop_info['shop_abbr'] or 'unknown'}_{url}"

    retry_count = 0
    while retry_count <= max_retries:
        try:
            # 使用Session发送请求，而非单次request
            response = session.request(
                method=method,
                url=url,
                json=json,
                data=data,
                params=params,
                files=files,
                timeout=timeout,
                verify=False
            )
            response.raise_for_status()

            # ========== 新增：请求成功，重置限流计数 ==========
            with RATE_LIMIT_LOCK:
                if rate_limit_key in RATE_LIMIT_STATUS:
                    del RATE_LIMIT_STATUS[rate_limit_key]

            return response

        except (RuntimeError, requests.RequestException) as e:
            retry_count += 1
            if retry_count > max_retries:
                raise

            if log:
                error_msg_parts = []
                if params:
                    error_msg_parts.append(f"params：{params}")
                if json:
                    error_msg_parts.append(f"json：{json}")
                if data:
                    error_msg_parts.append(f"data：{data}")
                error_msg = " | ".join(error_msg_parts)

                logger.warning(
                    f"店铺{shop_info['shop_abbr'] or '未知'}: 请求失败，正在重试（{retry_count}/{max_retries}）: "
                    f"错误信息[{str(e)[:200]}], URL[{url}], 参数[{error_msg[:200]}] {'网络请求错误信息详情请查看日志' if len(error_msg) > 200 else ''}"
                )

                # ========== 核心修改：动态429等待逻辑 ==========
                if "429 Client Error: Too Many Requests" in str(e):
                    with RATE_LIMIT_LOCK:
                        # 1. 获取当前限流状态（次数+最后触发时间）
                        status = RATE_LIMIT_STATUS.get(rate_limit_key, {"count": 0, "last_time": 0})
                        current_time = time.time()

                        # 2. 如果超过重置间隔，重置计数
                        if current_time - status["last_time"] > RESET_INTERVAL:
                            status["count"] = 0

                        # 3. 累计触发次数，更新最后触发时间
                        status["count"] += 1
                        status["last_time"] = current_time
                        RATE_LIMIT_STATUS[rate_limit_key] = status

                        # 4. 计算动态等待时间（指数增长，不超过最大值）
                        wait_time = round(min(BASE_WAIT_TIME * (WAIT_MULTIPLIER ** (status["count"] - 1)), MAX_WAIT_TIME), 2)

                    # 打印动态等待日志
                    logger.warning(
                        f"店铺{shop_info['shop_abbr'] or '未知'}: 请求被限流（第{status['count']}次触发），"
                        f"等待{wait_time}秒后重试 【触发频率越高，等待越久:）】"
                    )
                    time.sleep(wait_time)

                elif "403 Client Error" in str(e):
                    logger.error(f"店铺{shop_info['shop_abbr'] or '未知'}: Cookie过期或无权限访问")

            # 普通错误的基础等待（保留原有逻辑）
            if sleep_open and retry_count <= max_retries:
                # 避免重复sleep（429已单独sleep）
                if "429 Client Error: Too Many Requests" not in str(e):
                    time.sleep(3)

    return {}


# ========== 可选：添加定时清理过期限流状态的线程（防止内存泄漏） ==========
def clean_expired_rate_limit_status():
    """定时清理超过重置间隔的限流状态（每10分钟执行一次）"""
    while True:
        time.sleep(600)  # 10分钟
        with RATE_LIMIT_LOCK:
            current_time = time.time()
            expired_keys = [
                key for key, status in RATE_LIMIT_STATUS.items()
                if current_time - status["last_time"] > RESET_INTERVAL
            ]
            for key in expired_keys:
                del RATE_LIMIT_STATUS[key]
            if expired_keys:
                logger.info(f"清理过期限流状态 | 数量: {len(expired_keys)}")


# 启动定时清理线程（守护线程，不影响主程序退出）
clean_thread = threading.Thread(target=clean_expired_rate_limit_status, daemon=True, name="rate_limit_clean_thread")
clean_thread.start()


if __name__ == "__main__":
    # 测试：相同种子生成相同UA
    seed1 = 758287618356
    ua1 = generate_fixed_random_ua(seed1)
    ua2 = generate_fixed_random_ua(seed1)
    print(f"种子{seed1}生成的UA1：{ua1}")
    print(f"种子{seed1}生成的UA2：{ua2}")
    print(f"是否相同：{ua1 == ua2}")  # 输出True

    # 测试：不同种子生成不同UA
    seed2 = 123456789012
    ua3 = generate_fixed_random_ua(seed2)
    print(f"\n种子{seed2}生成的UA3：{ua3}")
    print(f"是否不同：{ua1 != ua3}")  # 输出True

    # 集成到请求函数的调用示例
    response = send_req(
        "GET",
        "https://example.com",
        uid="758287618356"  # 传入种子，生成固定随机UA
    )
    print(f"\n请求使用的UA：{response.request.headers['User-Agent']}")