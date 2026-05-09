from loguru import logger
import os

from utils.multiThreading_log_manager import get_task_log_manager, TaskStatus

WARNING_FILE = "error/warning.txt"


def write_warning_to_file(message):
    """
    将警告信息写入warning.txt，避免重复记录

    Args:
        message: 警告信息
    """
    try:
        if not os.path.exists("error"):
            os.makedirs("error")

        if os.path.exists(WARNING_FILE):
            with open(WARNING_FILE, "r", encoding="utf-8") as f:
                existing_lines = f.read().strip().split("\n")
        else:
            existing_lines = []

        if message not in existing_lines:
            with open(WARNING_FILE, "a", encoding="utf-8") as f:
                f.write(message + "\n")
    except Exception as e:
        logger.error(f"写入warning.txt失败: {e}")


def auto_print_logger(
            self_json_data: dict = None,
            success_type: str = "i",
            main_task_id: str = "",
            msg: str = None,
            remarks: str = None,
        ):
    """
    trace warning error info success
    自动输出日志输出msg+remarks ，
    logger.error(f"{self_json_data["msg"]}，{self_json_data["remarks"]}")
    """
    try:
        # 初始化默认值，避免None导致的拼接错误
        remarks = remarks or ""
        msg = msg or ""

        # 关键修复1：先校验self_json_data的类型和完整性
        if self_json_data is not None and isinstance(self_json_data, dict):
            # 检查必要的key是否存在
            has_msg = "msg" in self_json_data
            has_remarks = "remarks" in self_json_data
            has_code = "code" in self_json_data

            if has_msg and has_remarks:
                # 关键修复2：内层用单引号，避免和外层双引号冲突
                log_msg = self_json_data["msg"]
                log_remarks = self_json_data["remarks"]

                if main_task_id:
                    # get_task_log_manager().update_task_msg_and_remarks(
                    #     main_task_id, msg=log_msg, remarks=log_remarks
                    # )
                    get_task_log_manager().update_task_field(
                        main_task_id,
                        status=TaskStatus.RUNNING,
                        msg = log_msg,
                        remarks = log_remarks
                    )

                # 根据code输出不同级别日志
                if has_code:
                    if self_json_data["code"] != 1:
                        logger.error(f"{log_msg} {log_remarks}")
                    else:
                        # 按success_type输出对应级别
                        log_level_map = {
                            "t": logger.trace,
                            "trace": logger.trace,
                            "w": logger.warning,
                            "warning": logger.warning,
                            "e": logger.error,
                            "error": logger.error,
                            "i": logger.info,
                            "info": logger.info,
                            "s": logger.success,
                            "success": logger.success
                        }
                        log_func = log_level_map.get(success_type, logger.info)
                        log_func(f"{log_msg} {log_remarks}")
                else:
                    logger.error("自动输出日志发生错误：self_json_data缺少code字段")
                    logger.error(f"{log_msg} {log_remarks}")
            else:
                logger.error("自动输出日志发生错误：self_json_data缺少msg或remarks字段")
        else:
            # 无self_json_data时，使用传入的msg和remarks
            if main_task_id:
                # get_task_log_manager().update_task_msg_and_remarks(
                #     main_task_id, msg=msg, remarks=remarks
                # )
                get_task_log_manager().update_task_field(
                    main_task_id,
                    status=TaskStatus.RUNNING,
                    msg=msg,
                    remarks=remarks
                )

            # 按success_type输出对应级别日志
            log_level_map = {
                "t": logger.trace,
                "w": logger.warning,
                "e": logger.error,
                "i": logger.info,
                "s": logger.success,
                "trace": logger.trace,
                "warning": logger.warning,
                "error": logger.error,
                "info": logger.info,
                "success": logger.success
            }
            log_func = log_level_map.get(success_type, logger.info)
            log_func(f"{msg} {remarks}")

    except Exception as e:
        logger.error(f"自动输出日志失败：{e}", exc_info=True)

def response_result_handler(shop_abbr, response):
    """
    处理响应结果
    :param response:
    :return:
    """
    try:
        if not response:
            remarks = f"店铺{shop_abbr}：异常，响应结果为空"
        elif response.status_code != 200:
            # 关键修复3：处理response.json()可能的异常
            try:
                resp_json = response.json()
            except Exception:
                resp_json = f"响应内容：{response.text[:500]}"  # 截取部分内容避免过长
            remarks = f"店铺{shop_abbr}：网络异常或请求被拦截，状态码:{response.status_code}，响应: {resp_json}"
        else:
            # 关键修复3：处理response.json()可能的异常
            try:
                resp_json = response.json()
                remarks = resp_json.get("errorMsg", "") or ""
            except Exception:
                remarks = f"店铺{shop_abbr}：响应不是JSON格式，内容：{response.text[:500]}"
        return remarks
    except Exception as e:
        logger.error(f"处理响应结果失败：{e}", exc_info=True)
        return f"店铺{shop_abbr}：处理响应结果异常：{str(e)}"


# 定义专门的异常类，用于传递错误结果
class AutoReturnError(Exception):
    """自动返回错误的异常类，携带错误结果字典"""
    def __init__(self, result: dict):
        self.result = result  # 保存auto_return生成的错误结果
        super().__init__(result["msg"])  # 异常描述用错误信息

def auto_return(data_name=None, msg="自动返回信息异常"):
    """
    判断参数是否为空，抛异常触发外层return（无异常则无操作）
    :param msg: 错误提示
    :param data_name: 参数 为空则抛异常
    """
    if not data_name:
        _result = {
            "code": -1,
            "msg": msg,
            "data": None,
            "remarks": f"返回数据异常空值：{data_name}"
        }
        auto_print_logger(_result)
        # 抛异常，替代return，让异常自动向上穿透
        raise AutoReturnError(_result)
    # 无异常时：不抛异常、不return，函数正常结束