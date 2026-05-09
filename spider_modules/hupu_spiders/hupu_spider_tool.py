import sys
import requests
from bs4 import BeautifulSoup
from loguru import logger
from config.py_config import config_value
from config.common_config import config_manager
from spider_modules.SpiderSession import SpiderSession

def get_post_title(post_id: str):
    hupu_url = f"https://bbs.hupu.com/{post_id}.html"
    
    # 根据配置决定是否使用代理
    use_proxy = config_manager.get_or_set_config("spider_use_proxy", "否") == "是"
    proxies_list = []
    
    if use_proxy:
        get_proxies_url = f"{config_value.api_proxy_url}/get_proxies"
        try:
            resp = requests.get(get_proxies_url)
            proxies_list = resp.json()["proxies"]
        except Exception as e:
            logger.error("ip获取异常，请检查是否启动代理线程", e)

    session = SpiderSession(proxies_list)
    _resp = session.get(hupu_url)
    resp = _resp.get("response")
    req_ip = _resp.get("ip")

    soup = BeautifulSoup(resp.text, "lxml")
    posttitle = soup.find("title").text.strip()
    if posttitle:
        p_list = posttitle.split("-")
        p_list_without_last = p_list[:-2] if len(p_list) >= 2 else p_list
        posttitle = "-".join(p_list_without_last)

    data_list = {
        "posttitle": posttitle,
        "req_ip": req_ip
    }
    return data_list


def get_score_title(score_id: str):
    hupu_url = f"https://m.hupu.com/score-item/common_second/{score_id}"

    # 根据配置决定是否使用代理
    use_proxy = config_manager.get_or_set_config("spider_use_proxy", "否") == "是"
    proxies_list = []
    
    if use_proxy:
        get_proxies_url = f"{config_value.api_proxy_url}/get_proxies"
        try:
            resp = requests.get(get_proxies_url)
            proxies_list = resp.json()["proxies"]
        except Exception as e:
            logger.error("ip获取异常，请检查是否启动代理线程", e)

    session = SpiderSession(proxies_list)
    _resp = session.get(hupu_url)
    resp = _resp.get("response")
    req_ip = _resp.get("ip")

    soup = BeautifulSoup(resp.text, "lxml")
    _score_title = soup.find("div", class_="basic-info_basic-info-right__JVP56")
    score = soup.find("div", class_="score-card_score-card-left-top__LJK5l")

    if score:
        score = score.text.strip()
    else:
        score = None

    if _score_title:
        score_title = _score_title.text.strip()
    else:
        score_title = None

    data_list = {
        "score_title": score_title,
        "score": score,
        "req_ip": req_ip
    }

    return data_list


if __name__ == '__main__':
    logger.remove()
    logger.add(sys.stderr, level="TRACE")

    # 测试获取帖子标题
    print("测试获取帖子标题:")
    post_title_data = get_post_title("634303667")
    print(post_title_data)
    
    # 测试获取评分标题
    print("\n测试获取评分标题:")
    score_title_data = get_score_title("936742")
    print(score_title_data)