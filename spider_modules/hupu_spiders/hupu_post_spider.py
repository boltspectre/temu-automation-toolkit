import sys
import time

import requests
from bs4 import BeautifulSoup
from loguru import logger
from config.common_config import hupu_db, config_manager
from config.py_config import config_value
from spider_modules.SpiderSession import SpiderSession, get_proxies_from_file, get_proxies_with_backup
from spider_modules.spider_config import get_spider_proxy_config

global_sort_by_chinese_to_english = {"综合排序": "general", "按发布时间最新排序": "createtime", "按发布时间最早排序": "createtimeasc",
           "按回复时间排序": "replytime", "按亮回复数排序(近1月)": "light", "按回复数排序(近1月)": "reply"}

global_sort_by_english_to_chinese = {"general": "综合排序", "createtime": "按发布时间最新排序",
                   "createtimeasc": "按发布时间最早排序", "replytime": "按回复时间排序",
                   "light": "按亮回复数排序(近1月)", "reply": "按回复数排序(近1月)"}

def parse_post(post_lists):
    result = []
    for post in post_lists:
        posturl = post.find('a', class_="content-wrap-span")
        title = post.find_all('a', class_="content-wrap-span")[0]
        zone = post.find_all('a', class_="content-wrap-span")[1]
        post_time = post.find("span")
        huifushu = post.find_all("span", class_="content-wrap-span1")[0]
        tuijianshu = post.find_all("span", class_="content-wrap-span1")[1]
        liangpingshu = post.find_all("span", class_="content-wrap-span1")[2] if len(post.find_all("span", class_="content-wrap-span1")) > 2 else None

        _result = {
            "标题": title.text.strip() if title else "",
            "分区": zone.text.strip() if zone else "",
            "发帖时间": post_time.text.strip() if post_time else "",
            "回复数": huifushu.text.strip() if huifushu else "",
            "推荐数": tuijianshu.text.strip() if tuijianshu else "",
            "亮评数": liangpingshu.text.strip() if liangpingshu else "",
            "posturl" : posturl.get("href") if posturl else "",
        }

        result.append(_result)

    return result

def get_hupu_posts(keyword: str =  None, max_pages: int = 1, sleep_time: float = 0.3, id: int = 0,  sortby: str = "general", topic_id : str = "", only_one_page: bool = False, specific_page: int = 1):
    """
    """
    # 默认排序为general
    try:
        if max_pages <= 0:
            max_pages = 1
        # result =  []
        logger.info(f"开始爬取关键词【{keyword}】下的帖子")

        if only_one_page:
            start_page = specific_page
            total_page = 1
        else:
            start_page = 1
            total_page = max_pages

        # 先请求第一页，获取实际的最大页数
        first_page_url = f"https://bbs.hupu.com/search?q={keyword}&topicId={topic_id}&sortby={sortby}&page=1"
        
        # 获取代理配置
        proxy_config = get_spider_proxy_config()
        proxies_list = []
        
        if proxy_config["use_proxy"]:
            get_proxies_url = f"{config_value.api_proxy_url}/get_proxies"
            try:
                resp = requests.get(get_proxies_url, timeout=5)
                proxies_list = resp.json()["proxies"]
                logger.info(f"从代理API获取到 {len(proxies_list)} 个代理")
            except Exception as e:
                logger.error(f"从代理API获取代理失败: {e}")
                
                # 尝试从文件获取备用代理
                try:
                    proxies_list, msg = get_proxies_from_file(file_path=config_value.proxy_file_path)
                    logger.info(f"从文件获取备用代理: {msg}")
                except Exception as file_e:
                    logger.error(f"从文件获取代理也失败: {file_e}")
                    
                    # 如果强制代理模式且没有可用代理，抛出异常
                    if proxy_config["force_proxy"]:
                        logger.error("强制代理模式且无可用代理，无法继续")
                        raise Exception("强制代理模式需要启动代理IP服务")
                    else:
                        logger.warning("非强制代理模式，将使用本地IP继续执行")
                        proxies_list = []

        session = SpiderSession(
            proxies_list,
            use_proxy=proxy_config["use_proxy"],
            force_proxy=proxy_config["force_proxy"],
            task_id=id  # 传递任务ID，用于记录使用的代理IP
        )
        _resp = session.get(first_page_url)
        resp = _resp.get("response")

        soup = BeautifulSoup(resp.text, "lxml")
        
        # 解析分页信息，获取实际最大页数
        pagination = soup.find("ul", class_="hupu-rc-pagination")
        max_page_from_pagination = None
        if pagination:
            page_items = pagination.find_all("li", class_="hupu-rc-pagination-item")
            if page_items:
                for item in page_items:
                    link = item.find("a")
                    if link:
                        link_text = link.get_text(strip=True)
                        if link_text.isdigit():
                            page_num = int(link_text)
                            if max_page_from_pagination is None or page_num > max_page_from_pagination:
                                max_page_from_pagination = page_num

        # 取输入的最大页数和实际页数中的较小值
        if max_page_from_pagination:
            actual_max_pages = min(max_pages, max_page_from_pagination)
            total_page = actual_max_pages
            logger.info(f"从分页信息解析到实际页数: {max_page_from_pagination}，将爬取: {actual_max_pages} 页")
            max_pages = actual_max_pages

        for page in range(start_page, max_pages + 1):

            logger.info(f"正在爬取第{str(page)}页")

            url = f"https://bbs.hupu.com/search?q={keyword}&topicId={topic_id}&sortby={sortby}&page={page}"

            # 根据配置决定是否使用代理
            proxies_list = []
            if proxy_config["use_proxy"]:
                # 使用代理IP列表（优先API，备用文件）
                proxies_list = get_proxies_with_backup()
            else:
                # 不使用代理
                logger.info("不使用代理IP")

            session = SpiderSession(
                proxies_list,
                use_proxy=proxy_config["use_proxy"],
                force_proxy=proxy_config["force_proxy"],
                task_id=id  # 传递任务ID，用于记录使用的代理IP
            )
            _resp = session.get(url)
            resp = _resp.get("response")
            req_ip = _resp.get("ip")

            if req_ip:
                database_ip = req_ip["socks5"]
            else:
                database_ip = None

            soup = BeautifulSoup(resp.text, "lxml")
            post_lists = soup.find_all('div', class_="content-outline")
            logger.trace(f"找到 {len(post_lists)} 个帖子")
            _result = parse_post(post_lists)
            if not _result:
                logger.trace(f"第{page}页无数据")

            # logger.trace(f"解析结果: {_result}")

            if sleep_time:
                time.sleep(sleep_time)

            # result.append(_result)
            yield _result

            if only_one_page:
                page = 1
            process = f"{str(page)}/{total_page}"
            logger.info(f"进度: {process}")

        logger.info("任务完成")
        
        # 返回一个空列表，表示没有更多数据了
        return
    except Exception as e:
        logger.error(f"任务异常: {e}")
        raise
        # NOTE   can only concatenate str (not "int") to str 报错 检查数据库引入的字符串!

if __name__ == '__main__':
    logger.remove()
    logger.add(sys.stderr, level="TRACE")
    # 可选排序方式: 综合排序, 按发布时间最新排序, 按发布时间最早排序, 按回复时间排序, 按亮回复数排序(近1月), 按回复数排序(近1月)

    logger.info("开始测试爬虫")
    try:
        # 获取生成器对象
        result_generator = get_hupu_posts("贷款还不完", 1, only_one_page=False, id=1543, topic_id="1")
        logger.info("获取到生成器对象")
        
        page_count = 0
        # 正确处理生成器，逐页获取数据
        try:
            for page_data in result_generator:
                page_count += 1
                logger.info(f"第 {page_count} 页数据: {page_data}")  # 每次迭代执行到下一个yield
        except GeneratorExit:
            logger.info("生成器被提前关闭")
        except Exception as gen_error:
            logger.error(f"生成器迭代异常: {gen_error}")
            raise

        logger.info(f"总共处理了 {page_count} 页数据")
        logger.info("完成")
    except Exception as e:
        logger.error(f"发生异常: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        logger.info("程序执行结束")