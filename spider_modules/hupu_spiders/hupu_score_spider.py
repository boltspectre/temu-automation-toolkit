import sys
import time

import requests
from loguru import logger
from config.common_config import hupu_db, config_manager
from config.py_config import config_value
from spider_modules.SpiderSession import SpiderSession, get_proxies_with_backup
from spider_modules.spider_config import get_spider_proxy_config
from spider_modules.hupu_spiders.hupu_spider_tool import get_score_title
from modules.trun_time import get_current_timestamp_with_zero_ms

def parse_hupu_score(score_data: dict, datalist: dict):
    """解析虎扑评分评论数据"""
    _result = []
    if not score_data or not score_data.get("data") or not score_data["data"].get("comments"):
        return _result

    for user in score_data["data"]["comments"]:
        user = user or {}  # 防止user为None
        _result.append({
            "name": user.get("commentUserName", ""),
            "time": user.get("commentDate", ""),
            "location": user.get("ipLocation", ""),
            "comment": user.get("commentContent", ""),
            "reply_comment": user.get("parentCommentContent", ""),
            "like_count": user.get("lightCount", ""),
            "score": str(int(int(user.get("score", 0)) / 2)) if user.get("score") else "0",
            "score_title": datalist.get("score_title", {}).get("score_title", ""),
            "scoreurl": datalist.get("scoreurl", ""),
        })
    return _result


def get_hupu_score(max_pages: int = 1, sleep_time: float = 0.3, score_id="539270", id: int = 0):
    try:
        logger.info(f"开始爬取虎扑评分ID: {score_id}")

        if max_pages <= 0:
            max_pages = 1

        # 获取代理配置
        proxy_config = get_spider_proxy_config()
        
        publishtime = get_current_timestamp_with_zero_ms()
        total_page = max_pages

        for page in range(1, max_pages + 1):
            logger.info(f"正在爬取第{page}页")

            # 构造请求URL
            list_out_biz_type = "common_second"
            list_url = (
                f"https://games.mobileapi.hupu.com/1/8.0.65/bplcommentapi/bpl/comment/list"
                f"?publishTime={publishtime}&order=desc&outBizNo={score_id}"
                f"&outBizType={list_out_biz_type}&clientCode="
            )
            logger.debug(f"请求URL：{list_url}")

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
            _resp = session.get(list_url)
            resp = _resp.get("response")

            # 解析响应数据
            result = []
            next_publishtime = None
            if resp:
                try:
                    resp_json = resp.json()
                    # 获取评分标题和链接
                    score_title = get_score_title(score_id)
                    scoreurl = f"https://m.hupu.com/score-item/common_second/{score_id}"
                    datalist = {
                        "score_title": score_title,
                        "scoreurl": scoreurl
                    }
                    # 解析评论数据
                    result = parse_hupu_score(resp_json, datalist)
                    # 获取下一页游标
                    next_publishtime = resp_json["data"]["cursor"]["publishTime"] if resp_json["data"].get(
                        "cursor") else None
                except Exception as e:
                    logger.error(f"第{page}页解析失败：{e}")
                    next_publishtime = None
            else:
                logger.error(f"第{page}页请求失败，无响应数据")

            # 如果返回空列表，停止爬取
            if not result:
                logger.info(f"第{page}页无数据，停止爬取")
                break

            # 更新下一页的时间游标
            if next_publishtime:
                publishtime = next_publishtime
            else:
                logger.info("未获取到下一页游标，爬取终止")
                break

            if sleep_time:
                time.sleep(sleep_time)

            yield result

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
        score_id = "26848"  # 虎扑评分ID
        max_pages = 2  # 爬取页数
        id = 1548  # 任务ID
        
        logger.info(f"开始爬取虎扑评分ID: {score_id}")
        
        # 获取生成器对象
        result_generator = get_hupu_score(score_id=score_id, max_pages=max_pages, id=id, sleep_time=0)
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