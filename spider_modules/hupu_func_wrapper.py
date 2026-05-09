from loguru import logger
from spider_modules.hupu_spiders.hupu_post_spider import get_hupu_posts
from spider_modules.hupu_spiders.hupu_detail_spider import get_hupu_detail
from spider_modules.hupu_spiders.hupu_score_spider import get_hupu_score
from config.common_config import hupu_db, hupu_post_list_concurrent, hupu_detail_list_concurrent, hupu_score_list_concurrent
from utils.multiThreading_log_manager import check_task_stopped, get_task_log_manager
from utils.log_utils import auto_print_logger
from datetime import datetime
import json
import traceback
from urllib.parse import urlparse, parse_qs, unquote





def process_hupu_posts_chunk(
    keyword: str,
    page_chunk: list,
    sleep_time: float,
    id: int,
    sortby: str,
    topic_id: str,
    only_one_page: bool,
    main_task_id: str
):
    """处理虎扑帖子数据块的子函数（多线程）"""
    try:
        item_count = 0
        for page_data in page_chunk:
            check_task_stopped(get_task_log_manager(), main_task_id)
            
            logger.info(f"处理页面数据 | 页面数: {len(page_data)}")
            
            # 按照每一行数据为最小单元单独处理
            for item in page_data:
                check_task_stopped(get_task_log_manager(), main_task_id)
                
                item_count += 1
                logger.info(f"正在处理第 {item_count} 条数据 | 标题: {item.get('标题', '')} | 回复数: {item.get('回复数', '')}")
                
                # 插入数据库（使用 INSERT OR IGNORE 避免重复）
                try:
                    hupu_db.execute_sql(
                        "INSERT OR IGNORE INTO hupu_post_list (huputitle, hupu_zone, posturl, replies, tuijian_count, fatietime, liangping_count, task_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        params=(
                            item.get('标题', ''),
                            item.get('分区', ''),
                            item.get('posturl', ''),
                            item.get('回复数', ''),
                            item.get('推荐数', ''),
                            item.get('发帖时间', ''),
                            item.get('亮评数', ''),
                            main_task_id  # 添加主任务标识
                        )
                    )
                    logger.info(f"第 {item_count} 条数据已成功插入数据库")
                except Exception as db_error:
                    logger.warning(f"第 {item_count} 条数据插入失败（可能是重复数据）: {db_error}")
        
        return {"code": 1, "msg": f"成功处理 {item_count} 条数据", "data": {"item_count": item_count}}
    except Exception as e:
        logger.error(f"处理虎扑帖子数据块失败: {e}")
        return {"code": -1, "msg": f"处理失败: {str(e)}", "data": {"item_count": 0}}


def process_hupu_detail_chunk(
    post_id: str,
    page_chunk: list,
    sleep_time: float,
    id: int,
    main_task_id: str
):
    """处理虎扑帖子详情数据块的子函数（多线程）"""
    try:
        item_count = 0
        for page_data in page_chunk:
            check_task_stopped(get_task_log_manager(), main_task_id)
            
            logger.info(f"处理页面数据 | 页面数: {len(page_data)}")
            
            # 按照每一行数据为最小单元单独处理
            for item in page_data:
                check_task_stopped(get_task_log_manager(), main_task_id)
                
                item_count += 1
                logger.info(f"正在处理第 {item_count} 条数据 | 昵称: {item.get('name', '')} | 楼层: {item.get('floor', '')}")
                
                # 插入数据库（使用 INSERT OR IGNORE 避免重复）
                try:
                    hupu_db.execute_sql(
                        "INSERT OR IGNORE INTO hupu_detail_list (fabucontent, nickname, replycontent, floor, ipaddress, posttitle, like_count, posturl, replytime, reply_count, task_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        params=(
                            item.get('comment', ''),
                            item.get('name', ''),
                            item.get('reply_comment', ''),
                            item.get('floor', ''),
                            item.get('location', ''),
                            item.get('posttitle', ''),
                            item.get('like_count', ''),
                            item.get('hupu_url', ''),
                            item.get('time', ''),
                            item.get('reply_count', ''),
                            main_task_id  # 添加主任务标识
                        )
                    )
                    logger.info(f"第 {item_count} 条数据已成功插入数据库")
                    
                    # 每插入一条数据后检查任务是否被停止
                    check_task_stopped(get_task_log_manager(), main_task_id)
                except Exception as db_error:
                    logger.warning(f"第 {item_count} 条数据插入失败（可能是重复数据）: {db_error}")
                    
                    # 每次操作后检查任务是否被停止
                    check_task_stopped(get_task_log_manager(), main_task_id)
        
        return {"code": 1, "msg": f"成功处理 {item_count} 条数据", "data": {"item_count": item_count}}
    except Exception as e:
        logger.error(f"处理虎扑帖子详情数据块失败: {e}")
        return {"code": -1, "msg": f"处理失败: {str(e)}", "data": {"item_count": 0}}


def process_hupu_score_chunk(
    score_id: str,
    page_chunk: list,
    sleep_time: float,
    id: int,
    main_task_id: str
):
    """处理虎扑评分数据块的子函数（多线程）"""
    try:
        item_count = 0
        for page_data in page_chunk:
            check_task_stopped(get_task_log_manager(), main_task_id)
            
            logger.info(f"处理页面数据 | 页面数: {len(page_data)}")
            
            # 按照每一行数据为最小单元单独处理
            for item in page_data:
                check_task_stopped(get_task_log_manager(), main_task_id)
                
                item_count += 1
                logger.info(f"正在处理第 {item_count} 条数据 | 昵称: {item.get('name', '')} | 评分: {item.get('score', '')}")
                
                # 插入数据库（使用 INSERT OR IGNORE 避免重复）
                try:
                    hupu_db.execute_sql(
                        "INSERT OR IGNORE INTO hupu_score_list (name, time, location, comment, reply_comment, like_count, score, score_title, scoreurl, task_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        params=(
                            item.get('name', ''),
                            item.get('time', ''),
                            item.get('location', ''),
                            item.get('comment', ''),
                            item.get('reply_comment', ''),
                            item.get('like_count', ''),
                            item.get('score', ''),
                            item.get('score_title', ''),
                            item.get('scoreurl', ''),
                            main_task_id  # 添加主任务标识
                        )
                    )
                    logger.info(f"第 {item_count} 条数据已成功插入数据库")
                    
                    # 每插入一条数据后检查任务是否被停止
                    check_task_stopped(get_task_log_manager(), main_task_id)
                except Exception as db_error:
                    logger.warning(f"第 {item_count} 条数据插入失败（可能是重复数据）: {db_error}")
                    
                    # 每次操作后检查任务是否被停止
                    check_task_stopped(get_task_log_manager(), main_task_id)
        
        return {"code": 1, "msg": f"成功处理 {item_count} 条数据", "data": {"item_count": item_count}}
    except Exception as e:
        logger.error(f"处理虎扑评分数据块失败: {e}")
        return {"code": -1, "msg": f"处理失败: {str(e)}", "data": {"item_count": 0}}


def split_task_list(task_list, chunk_size):
    """将任务列表分割成指定大小的块"""
    chunks = []
    for i in range(0, len(task_list), chunk_size):
        chunks.append(task_list[i:i + chunk_size])
    return chunks


def hupu_post_list_wrapper(
    keyword: str | None = None,
    max_pages: int = 1,
    sleep_time: float = 0.3,
    id: int = 0,
    sortby: str = "general",
    topic_id: str = "",
    only_one_page: bool = False,
    specific_page: int = 1,
    main_task_id: str = ""
):
    logger.info(f"虎扑帖子列表采集任务开始 | main_task_id: {main_task_id}")
    logger.info(f"采集参数: keyword={keyword}, max_pages={max_pages}, sleep_time={sleep_time}, sortby={sortby}, topic_id={topic_id}, only_one_page={only_one_page}, specific_page={specific_page}")
    
    # 为虎扑任务创建或更新对应的订单记录
    task_params = {
        'keyword': keyword,
        'max_pages': max_pages,
        'sortby': sortby,
        'topic_id': topic_id,
        'only_one_page': only_one_page,
        'specific_page': specific_page
    }
    
    try:
        check_task_stopped(get_task_log_manager(), main_task_id)
        
        # 获取生成器对象
        result_generator = get_hupu_posts(
            keyword=keyword,
            max_pages=max_pages,
            sleep_time=sleep_time,
            id=main_task_id,
            sortby=sortby,
            topic_id=topic_id,
            only_one_page=only_one_page,
            specific_page=specific_page
        )
        logger.info("开始处理数据...")

        # 收集所有页面数据
        all_pages_data = []
        page_count = 0
        total_item_count = 0  # 初始化变量，防止异常时未定义
        
        try:
            for page_data in result_generator:
                check_task_stopped(get_task_log_manager(), main_task_id)
                
                page_count += 1
                logger.info(f"正在处理第 {page_count} 页数据，共 {len(page_data)} 条记录")
                auto_print_logger(msg=f"当前第{page_count}页", remarks=f"共{len(page_data)}条数据", success_type="i", main_task_id=main_task_id)
                
                # 收集页面数据，稍后分片处理
                all_pages_data.append(page_data)
                
        except GeneratorExit:
            logger.info("生成器被提前关闭")
        except Exception as gen_error:
            logger.error(f"生成器迭代异常: {gen_error}")
            raise

        # 多线程处理页面数据
        if all_pages_data:
            # 计算目标线程数
            target_threads = hupu_post_list_concurrent
            total_pages = len(all_pages_data)
            
            # 计算分片大小，确保至少为1
            if total_pages <= target_threads:
                # 如果页数少于等于线程数，每页一个分片
                chunk_size = 1
            else:
                # 正常情况下的分片计算
                chunk_size = total_pages // target_threads if total_pages % target_threads == 0 else total_pages // target_threads + 1
                if total_pages % target_threads != 0 and total_pages % target_threads < target_threads // 2:
                    # 确保调整后的分片大小至少为1
                    adjusted_chunk_size = total_pages // (target_threads - 1)
                    chunk_size = max(1, adjusted_chunk_size)
                
            logger.info(f"目标线程数: {target_threads}, 总页数: {total_pages}, 计算得到的分片大小: {chunk_size}")
            
            # 分割页面数据
            page_chunks = split_task_list(all_pages_data, chunk_size=chunk_size)
            logger.info(f"虎扑帖子列表：共{total_pages}页，拆分为{len(page_chunks)}个分片（目标{target_threads}线程），每个分片{chunk_size}页")
            
            # 创建子任务
            task_ids = []
            task_kwargs_dict = {}
            
            for chunk_idx, page_chunk in enumerate(page_chunks):
                task_kwargs = {
                    "keyword": keyword,
                    "page_chunk": page_chunk,
                    "sleep_time": sleep_time,
                    "id": id,
                    "sortby": sortby,
                    "topic_id": topic_id,
                    "only_one_page": only_one_page,
                    "main_task_id": main_task_id
                }
                
                task_id = get_task_log_manager().add_task(
                    target_func=process_hupu_posts_chunk, **task_kwargs,
                    task_group=f"虎扑帖子列表采集",
                    parent_task_id=main_task_id,
                    is_main_task=0,
                )
                task_ids.append(task_id)
                task_kwargs_dict[task_id] = task_kwargs
            
            # 收集所有子任务结果
            total_item_count = 0
            for task_id in task_ids:
                chunk_result = get_task_log_manager().get_task_result(task_id, timeout=3000000)
                if chunk_result and chunk_result.get("code") == 1:
                    item_count = chunk_result.get("data", {}).get("item_count", 0)
                    total_item_count += item_count
                    logger.info(f"子任务 {task_id} 完成，处理了 {item_count} 条数据")
                elif chunk_result and chunk_result.get("code") == -1:
                    error_msg = chunk_result.get("msg", "未知错误")
                    logger.error(f"子任务 {task_id} 失败: {error_msg}")
                else:
                    logger.warning(f"子任务 {task_id} 无返回结果，可能执行成功但无数据")
        else:
            total_item_count = 0

        logger.info(f"数据采集完成 | 总页数: {page_count} | 总记录数: {total_item_count}")
        msg = "虎扑帖子列表采集完成"
        
        # 排序方式映射
        sortby_map = {
            "general": "综合排序",
            "createtime": "按发布时间最新排序",
            "createtimeasc": "按发布时间最早排序",
            "replytime": "按回复时间排序",
            "light": "按亮回复数排序(近1月)",
            "reply": "按回复数排序(近1月)"
        }
        sortby_text = sortby_map.get(sortby, sortby)  # 如果映射中没有，使用原值
        
        remarks = f"共采集 {page_count} 页，关键词: {keyword}, 排序方式: {sortby_text}"
        auto_print_logger(msg=msg, remarks=remarks, success_type="i", main_task_id=main_task_id)
        
        return {"code": 1, "msg": msg, "remarks": remarks, "data": {"page_count": page_count, "item_count": total_item_count}}
    except RuntimeError as e:
        logger.error(f"任务被停止: {e}")
        msg = "任务已退出"
        remarks = f"停止原因：{str(e)} | 已处理成功{total_item_count}条"
        auto_print_logger(msg=msg, remarks=remarks, success_type="w", main_task_id=main_task_id)
        
        return {"code": -1, "msg": msg, "remarks": remarks}
    except Exception as e:
        logger.error(f"发生异常: {e}")
        logger.error(traceback.format_exc())
        msg = "虎扑帖子列表采集失败"
        remarks = str(e)
        auto_print_logger(msg=msg, remarks=remarks, success_type="e", main_task_id=main_task_id)
        
        return {"code": -1, "msg": msg, "remarks": remarks}
    finally:
        logger.info("虎扑帖子列表采集任务结束")


def hupu_detail_list_wrapper(
    name: str = None,
    post_title: str = None,
    max_pages: int = 1,
    sleep_time: float = 0.3,
    id: int = 0,
    only_one_page: bool = False,
    specific_page: int = 1,
    main_task_id: str = ""
):
    logger.info(f"虎扑帖子详情采集任务开始 | main_task_id: {main_task_id}")
    logger.info(f"采集参数: name={name}, post_title={post_title}, max_pages={max_pages}, sleep_time={sleep_time}, only_one_page={only_one_page}, specific_page={specific_page}")
    
    # 为虎扑任务创建或更新对应的订单记录
    task_params = {
        'name': name,
        'post_title': post_title,
        'max_pages': max_pages,
        'only_one_page': only_one_page,
        'specific_page': specific_page
    }
    
    try:
        check_task_stopped(get_task_log_manager(), main_task_id)
        
        # 提取帖子ID
        post_id = name
        
        # 如果输入的是完整URL，提取帖子ID
        if name and "hupu.com" in name:
            # 从URL中提取帖子ID
            # 格式: https://bbs.hupu.com/637618639.html
            parts = name.split("/")
            for part in parts:
                if part.endswith(".html"):
                    post_id = part.replace(".html", "")
                    break
        # 如果输入的是 "标题-ID" 格式，提取ID
        elif name and '-' in name:
            post_id = name.split('-')[-1]

        logger.info(f"开始爬取帖子ID: {post_id}")

        # 获取生成器对象
        result_generator = get_hupu_detail(post_id=post_id, max_pages=max_pages, id=main_task_id, sleep_time=sleep_time, only_one_page=only_one_page, specific_page=specific_page)
        logger.info("开始处理数据...")

        # 收集所有页面数据
        all_pages_data = []
        page_count = 0
        total_item_count = 0  # 初始化变量，防止异常时未定义
        
        try:
            for page_data in result_generator:
                check_task_stopped(get_task_log_manager(), main_task_id)
                
                page_count += 1
                logger.info(f"正在处理第 {page_count} 页数据，共 {len(page_data)} 条记录")
                auto_print_logger(msg=f"当前第{page_count}页", remarks=f"共{len(page_data)}条数据", success_type="i", main_task_id=main_task_id)
                
                # 收集页面数据，稍后分片处理
                all_pages_data.append(page_data)
                
        except GeneratorExit:
            logger.info("生成器被提前关闭")
        except Exception as gen_error:
            logger.error(f"生成器迭代异常: {gen_error}")
            raise

        # 多线程处理页面数据
        if all_pages_data:
            # 计算目标线程数
            target_threads = hupu_detail_list_concurrent
            total_pages = len(all_pages_data)
            
            # 计算分片大小，确保至少为1
            if total_pages <= target_threads:
                # 如果页数少于等于线程数，每页一个分片
                chunk_size = 1
            else:
                # 正常情况下的分片计算
                chunk_size = total_pages // target_threads if total_pages % target_threads == 0 else total_pages // target_threads + 1
                if total_pages % target_threads != 0 and total_pages % target_threads < target_threads // 2:
                    # 确保调整后的分片大小至少为1
                    adjusted_chunk_size = total_pages // (target_threads - 1)
                    chunk_size = max(1, adjusted_chunk_size)
                
            logger.info(f"目标线程数: {target_threads}, 总页数: {total_pages}, 计算得到的分片大小: {chunk_size}")
            
            # 分割页面数据
            page_chunks = split_task_list(all_pages_data, chunk_size=chunk_size)
            logger.info(f"虎扑帖子详情：共{total_pages}页，拆分为{len(page_chunks)}个分片（目标{target_threads}线程），每个分片{chunk_size}页")
            
            # 创建子任务
            task_ids = []
            task_kwargs_dict = {}
            
            for chunk_idx, page_chunk in enumerate(page_chunks):
                task_kwargs = {
                    "post_id": post_id,
                    "page_chunk": page_chunk,
                    "sleep_time": sleep_time,
                    "id": id,
                    "main_task_id": main_task_id
                }
                
                task_id = get_task_log_manager().add_task(
                    target_func=process_hupu_detail_chunk, **task_kwargs,
                    task_group=f"虎扑帖子详情采集",
                    parent_task_id=main_task_id,
                    is_main_task=0,
                )
                task_ids.append(task_id)
                task_kwargs_dict[task_id] = task_kwargs
            
            # 收集所有子任务结果
            for task_id in task_ids:
                chunk_result = get_task_log_manager().get_task_result(task_id, timeout=3000000)
                if chunk_result and chunk_result.get("code") == 1:
                    item_count = chunk_result.get("data", {}).get("item_count", 0)
                    total_item_count += item_count
                    logger.info(f"子任务 {task_id} 完成，处理了 {item_count} 条数据")
                elif chunk_result and chunk_result.get("code") == -1:
                    error_msg = chunk_result.get("msg", "未知错误")
                    logger.error(f"子任务 {task_id} 失败: {error_msg}")
                else:
                    logger.warning(f"子任务 {task_id} 无返回结果，可能执行成功但无数据")
        else:
            total_item_count = 0

        logger.info(f"数据采集完成 | 总页数: {page_count} | 总记录数: {total_item_count}")
        msg = "虎扑帖子详情采集完成"
        remarks = f"共采集 {page_count} 页， 帖子ID/名称: {name}"
        auto_print_logger(msg=msg, remarks=remarks, success_type="i", main_task_id=main_task_id)
        
        return {"code": 1, "msg": msg, "remarks": remarks, "data": {"page_count": page_count, "item_count": total_item_count}}
    except RuntimeError as e:
        logger.error(f"任务被停止: {e}")
        msg = "任务已退出"
        remarks = f"停止原因：{str(e)} | 已处理成功{total_item_count}条"
        auto_print_logger(msg=msg, remarks=remarks, success_type="w", main_task_id=main_task_id)
        
        return {"code": -1, "msg": msg, "remarks": remarks}
    except Exception as e:
        logger.error(f"发生异常: {e}")
        logger.error(traceback.format_exc())
        msg = "虎扑帖子详情采集失败"
        remarks = str(e)
        auto_print_logger(msg=msg, remarks=remarks, success_type="e", main_task_id=main_task_id)
        
        return {"code": -1, "msg": msg, "remarks": remarks}
    finally:
        logger.info("虎扑帖子详情采集任务结束")


def hupu_score_list_wrapper(
    score_id: str = None,
    score_title: str = None,
    max_pages: int = 1,
    sleep_time: float = 0.3,
    id: int = 0,
    main_task_id: str = ""
):
    logger.info(f"虎扑评分采集任务开始 | main_task_id: {main_task_id}")
    logger.info(f"采集参数: score_id={score_id}, score_title={score_title}, max_pages={max_pages}, sleep_time={sleep_time}")
    
    # 为虎扑任务创建或更新对应的订单记录
    task_params = {
        'score_id': score_id,
        'score_title': score_title,
        'max_pages': max_pages
    }
    
    try:
        check_task_stopped(get_task_log_manager(), main_task_id)
        
        # 提取评分ID
        actual_score_id = score_id
        
        # 如果输入的是完整URL，提取评分ID
        if score_id and "hupu.com" in score_id:
            # 处理第一种格式：https://bbsactivity.hupu.com/pc-viewer/index.html?t=https%3A%2F%2Fm.hupu.com%2Fscore-item%2Fcommon_second%2F26848
            if "bbsactivity.hupu.com" in score_id and "?" in score_id:
                # 从URL参数中提取实际URL
                parsed = urlparse(score_id)
                query_params = parse_qs(parsed.query)
                if 't' in query_params:
                    # URL解码
                    actual_url = unquote(query_params['t'][0])
                    # 从实际URL中提取评分ID
                    # 格式: https://m.hupu.com/score-item/common_second/26848
                    parts = actual_url.split("/")
                    for part in parts:
                        if part.isdigit():
                            actual_score_id = part
                            break
            # 处理第二种格式：https://m.hupu.com/score-item/common_second/26848
            else:
                # 从URL中提取评分ID
                # 格式: https://m.hupu.com/score-item/common_second/26848
                parts = score_id.split("/")
                for part in parts:
                    if part.isdigit():
                        actual_score_id = part
                        break

        logger.info(f"开始爬取虎扑评分ID: {actual_score_id}")
        
        # 获取生成器对象
        result_generator = get_hupu_score(score_id=actual_score_id, max_pages=max_pages, id=main_task_id, sleep_time=sleep_time)
        logger.info("开始处理数据...")

        # 收集所有页面数据
        all_pages_data = []
        page_count = 0
        total_item_count = 0  # 初始化变量，防止异常时未定义

        try:
            for page_data in result_generator:
                check_task_stopped(get_task_log_manager(), main_task_id)
                
                page_count += 1
                logger.info(f"正在处理第 {page_count} 页数据，共 {len(page_data)} 条记录")
                auto_print_logger(msg=f"当前第{page_count}页", remarks=f"共{len(page_data)}条数据", success_type="i", main_task_id=main_task_id)
                
                # 收集页面数据，稍后分片处理
                all_pages_data.append(page_data)
                
        except GeneratorExit:
            logger.info("生成器被提前关闭")
        except Exception as gen_error:
            logger.error(f"生成器迭代异常: {gen_error}")
            raise

        # 多线程处理页面数据
        if all_pages_data:
            # 计算目标线程数
            target_threads = hupu_score_list_concurrent
            total_pages = len(all_pages_data)
            
            # 计算分片大小，确保至少为1
            if total_pages <= target_threads:
                # 如果页数少于等于线程数，每页一个分片
                chunk_size = 1
            else:
                # 正常情况下的分片计算
                chunk_size = total_pages // target_threads if total_pages % target_threads == 0 else total_pages // target_threads + 1
                if total_pages % target_threads != 0 and total_pages % target_threads < target_threads // 2:
                    # 确保调整后的分片大小至少为1
                    adjusted_chunk_size = total_pages // (target_threads - 1)
                    chunk_size = max(1, adjusted_chunk_size)
                
            logger.info(f"目标线程数: {target_threads}, 总页数: {total_pages}, 计算得到的分片大小: {chunk_size}")
            
            # 分割页面数据
            page_chunks = split_task_list(all_pages_data, chunk_size=chunk_size)
            logger.info(f"虎扑评分：共{total_pages}页，拆分为{len(page_chunks)}个分片（目标{target_threads}线程），每个分片{chunk_size}页")
            
            # 创建子任务
            task_ids = []
            task_kwargs_dict = {}
            
            for chunk_idx, page_chunk in enumerate(page_chunks):
                task_kwargs = {
                    "score_id": actual_score_id,
                    "page_chunk": page_chunk,
                    "sleep_time": sleep_time,
                    "id": id,
                    "main_task_id": main_task_id
                }
                
                task_id = get_task_log_manager().add_task(
                    target_func=process_hupu_score_chunk, **task_kwargs,
                    task_group=f"虎扑评分采集",
                    parent_task_id=main_task_id,
                    is_main_task=0,
                )
                task_ids.append(task_id)
                task_kwargs_dict[task_id] = task_kwargs
            
            # 收集所有子任务结果
            total_item_count = 0
            for task_id in task_ids:
                chunk_result = get_task_log_manager().get_task_result(task_id, timeout=3000000)
                if chunk_result and chunk_result.get("code") == 1:
                    item_count = chunk_result.get("data", {}).get("item_count", 0)
                    total_item_count += item_count
                    logger.info(f"子任务 {task_id} 完成，处理了 {item_count} 条数据")
                elif chunk_result and chunk_result.get("code") == -1:
                    error_msg = chunk_result.get("msg", "未知错误")
                    logger.error(f"子任务 {task_id} 失败: {error_msg}")
                else:
                    logger.warning(f"子任务 {task_id} 无返回结果，可能执行成功但无数据")
        else:
            total_item_count = 0

        logger.info(f"数据采集完成 | 总页数: {page_count} | 总记录数: {total_item_count}")
        msg = "虎扑评分采集完成"
        remarks = f"共采集 {page_count} 页， 评分ID: {score_id}"
        auto_print_logger(msg=msg, remarks=remarks, success_type="i", main_task_id=main_task_id)
        
        return {"code": 1, "msg": msg, "remarks": remarks, "data": {"page_count": page_count, "item_count": total_item_count}}
    except RuntimeError as e:
        logger.error(f"任务被停止: {e}")
        msg = "任务已退出"
        remarks = f"停止原因：{str(e)} | 已处理成功{total_item_count}条"
        auto_print_logger(msg=msg, remarks=remarks, success_type="w", main_task_id=main_task_id)
        
        return {"code": -1, "msg": msg, "remarks": remarks}
    except Exception as e:
        logger.error(f"发生异常: {e}")
        logger.error(traceback.format_exc())
        msg = "虎扑评分采集失败"
        remarks = str(e)
        auto_print_logger(msg=msg, remarks=remarks, success_type="e", main_task_id=main_task_id)
        
        return {"code": -1, "msg": msg, "remarks": remarks}
    finally:
        logger.info("虎扑评分采集任务结束")


