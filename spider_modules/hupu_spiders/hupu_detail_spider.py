import sys
import time

import requests
from bs4 import BeautifulSoup
from loguru import logger
from config.common_config import hupu_db, config_manager
from config.py_config import config_value
from spider_modules.SpiderSession import SpiderSession, get_proxies_from_file, get_proxies_with_backup
from spider_modules.spider_config import get_spider_proxy_config
from spider_modules.hupu_spiders.parse_string_tool import soup_bs4_tag_to_newline_text

def parse_detail(comment_boxs: list, hupu_url: str, data_list: dict):
    result = []
    for comment_box in comment_boxs:
        user_name = comment_box.find("a", class_="post-reply-list-user-info-top-name")
        user_time = comment_box.find("span", class_="post-reply-list-user-info-top-time")
        user_location = comment_box.find("span", class_="post-reply-list-user-info-user-location")

        comment = comment_box.find("div", class_="thread-content-detail")

        todo_list_texts = comment_box.find_all("span", class_="todo-list-text")
        
        like_count = ""
        reply_count = "0"
        if todo_list_texts:
            like_count = todo_list_texts[0].get_text(strip=True).replace("亮了(", "").replace(")", "")
            if len(todo_list_texts) > 1:
                reply_count_text = todo_list_texts[-1].get_text(strip=True).replace("查看评论(", "").replace(")",
                                                                                                             "").replace(
                    '回复', '')
                reply_count = reply_count_text if reply_count_text else "0"

        floor_tag = comment_box.find("div", class_="user-operate").find("a", class_="position") if comment_box.find(
            "div", class_="user-operate") else None
        floor = floor_tag.get_text(strip=True) if floor_tag else ""
        reply_comment_tag = comment_box.find("div", class_="index_bbs-thread-comp-container__QkBRG")
        reply_comment = reply_comment_tag.get_text(strip=True).replace("只看此人", "") if reply_comment_tag else ""

        if not floor:
            continue

        _result = {
        "name": user_name.text.strip() if user_name else "",
        "time": user_time.text.strip() if user_time else "",
        "location": user_location.text.strip().replace("发布于", "") if user_location else "",
        "comment": comment.text.strip() if comment else "",
        "reply_comment": reply_comment,
        "like_count": like_count if like_count else "",
        "reply_count": reply_count if reply_count else "0",
        "floor": floor,
        "hupu_url": hupu_url,
        "posttitle": data_list["posttitle"],
        }
        result.append(_result)

    return result

def get_hupu_detail(post_id: str, max_pages: int, sleep_time: float = 0.3, id: int = 0, only_one_page: bool = False, specific_page: int = 1):
    try:
        logger.info(f"开始爬取帖子ID为【{post_id}】的帖子")

        if max_pages <= 0:
            max_pages = 1
            
        if only_one_page:
            start_page = specific_page
            total_page = 1
        else:
            start_page = 1
            total_page = max_pages
            
        data_list = {"posttitle": ""}

        # 先请求第一页，获取实际的最大页数
        first_page_url = f"https://bbs.hupu.com/{post_id}.html"
        
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
            logger.info(f"正在爬取第{page}页")

            hupu_url = f"https://bbs.hupu.com/{post_id}-{page}.html" if page > 1 else f"https://bbs.hupu.com/{post_id}.html"

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
            _resp = session.get(hupu_url)
            resp = _resp.get("response")
            req_ip = _resp.get("ip")

            if req_ip:
                database_ip = req_ip["socks5"]
            else:
                database_ip = None

            soup = BeautifulSoup(resp.text, "lxml")
            
            # 解析标题
            posttitle = soup.find("title").text.strip() if soup.find("title") else ""
            if posttitle:
                p_list = posttitle.split("-")
                p_list_without_last = p_list[:-2] if len(p_list) >= 2 else p_list
                posttitle = "-".join(p_list_without_last)
            data_list["posttitle"] = posttitle

            page_data = []
            
            # 解析楼主信息（仅第1页）
            if page == 1:
                louzhu_name = soup.find_all("a", class_="post-user_post-user-comp-info-top-name__N3D4w")
                louzhu_fatie_time = soup.find_all("span", class_="post-user_post-user-comp-info-top-time__k9K2U")
                louzhu_ip = soup.find_all("span", class_="post-user_post-user-comp-info-user-location___VcVN")
                fabu_content = soup.find("div", class_="thread-content-detail")
                todo_list_text = soup.find_all("span", class_="todo-list-text")

                louzhu_list = {
                    "name": f"楼主-{louzhu_name[0].text.strip() if louzhu_name else '楼主'}",
                    "time": louzhu_fatie_time[0].text.strip() if louzhu_fatie_time else "未知时间",
                    "location": louzhu_ip[0].text.strip().replace("发布于", "") if louzhu_ip else "未知",
                    "comment": f"楼主发表:{soup_bs4_tag_to_newline_text(fabu_content)}" if fabu_content else "未知内容",
                    "reply_comment": "",
                    "like_count": todo_list_text[0].text.strip().replace("推荐 (", "").replace(")", "") if todo_list_text else "",
                    "reply_count": todo_list_text[1].text.strip().replace("评论 (", "").replace(")", "") if todo_list_text else "",
                    "floor": "楼主",
                    "hupu_url": hupu_url,
                    "posttitle": posttitle,
                }
                page_data.append(louzhu_list)

            # 解析评论区
            comment_boxs = soup.find_all("div", class_="post-reply-list_post-reply-list-wrapper__o4_81 post-reply-list-wrapper")
            if not comment_boxs and page != 1:
                logger.trace(f"第{page}页无评论内容")
            else:
                parsed_comments = parse_detail(comment_boxs, hupu_url, data_list)
                page_data.extend(parsed_comments)

            if sleep_time:
                time.sleep(sleep_time)

            yield page_data

            if only_one_page:
                page = 1
            process = f"{str(page)}/{total_page}"
            logger.info(f"进度: {process}")

        logger.info("任务完成")
        
        return
    except Exception as e:
        logger.error(f"任务异常: {e}")
        raise

if __name__ == '__main__':
    logger.remove()
    logger.add(sys.stderr, level="TRACE")
    
    logger.info("开始测试爬虫")
    try:
        name = "罗永浩悬赏10万元征集西贝预制菜线索，并回应西贝起诉：\"嗯，我准备好了\"-634782056"
        max_pages = 2
        id = 1547
        
        if '-' in name:
            post_id = name.split('-')[-1]
        else:
            post_id = name
            
        logger.info(f"开始爬取帖子ID: {post_id}")
        
        # 获取生成器对象
        result_generator = get_hupu_detail(post_id=post_id, max_pages=max_pages, id=id, sleep_time=0)
        logger.info("获取到生成器对象")
        
        page_count = 0
        # 正确处理生成器，逐页获取数据
        try:
            for page_data in result_generator:
                page_count += 1
                logger.info(f"第 {page_count} 页数据: {len(page_data)} 条记录")
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