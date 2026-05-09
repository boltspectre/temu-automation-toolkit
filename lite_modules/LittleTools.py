import datetime
import email.utils
import json
from datetime import datetime as dt
from datetime import timezone, timedelta
from time import sleep
from typing import Optional, Union, Dict, List
import requests
from PyQt5.QtWidgets import QApplication
from loguru import logger
from config.common_config import encryptor
from config.py_config import config_value

def get_baidu_internet_date():
    """
    解析百度响应头的Date字段获取互联网标准时间（中国时区，仅日期）
    使用标准库 email.utils.parsedate_to_datetime，避免 requests 版本兼容问题
    """
    try:
        response = requests.get(
            "https://www.baidu.com",
            timeout=5,
            allow_redirects=False,
            proxies=None,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        date_header = response.headers.get('Date')
        if not date_header:
            raise ValueError("响应头中缺少 Date 字段")

        # ✅ 使用标准库解析 RFC 2822 时间格式（如 'Fri, 09 Jan 2026 03:45:28 GMT'）
        utc_datetime = email.utils.parsedate_to_datetime(date_header)

        # 转换为中国时区（UTC+8）
        china_tz = timezone(timedelta(hours=8))
        china_datetime = utc_datetime.astimezone(china_tz)

        return china_datetime.date()
    except Exception as e:
        # logger.warning(f"解析百度时间失败：{str(e)}，降级使用本地时间")
        return dt.now().date()


# ====================== 2. 日期验证核心函数（替换为百度互联网时间） ======================
def clean_and_parse_json(raw_str):
    """清理并解析JSON字符串（保留原有逻辑）"""
    lines = [line.strip() for line in raw_str.split('\n')]
    cleaned_str = ''.join(lines)
    try:
        result = json.loads(cleaned_str)
        return result
    except json.JSONDecodeError as e:
        print(f"JSON解析失败：{e}")
        return None


def check_date_validation(base_date_str):
    """
    日期验证函数（基于百度互联网时间）
    :param base_date_str: 过期日期字符串（%Y-%m-%d）
    :return: 验证结果字典
    """
    try:
        # 处理永久有效期（9999-09-09）
        if base_date_str == "9999-09-09":
            return {"code": 1, "msg": "有效期验证通过！"}

        # 解析基准日期
        base_date = dt.strptime(base_date_str, "%Y-%m-%d").date()
        target_date = base_date + datetime.timedelta(days=1)

        # 核心修改：使用百度互联网时间
        current_date = get_baidu_internet_date()

        # 日期比对
        if current_date >= target_date:
            return {
                "code": -1,
                "msg": f"验证失败,卡密过期！"
            }
        else:
            return {
                "code": 1,
                "msg": f"有效期验证通过！"
            }

    except Exception as e:
        logger.error(f"验证异常：{str(e)}")
        return {
            "code": -2,
            "msg": f"验证异常!"
        }


def check_date_validation_by_config():
    """从配置文件解密获取有效期，调用百度互联网时间验证"""
    try:
        # 解密数据
        with open(f"{config_value.login_data_path}", "r") as f:
            encrypted_data = f.read()

        decrypted_data = encryptor.decrypt(encrypted_data)
        end_time = decrypted_data['end_time'] if 'end_time' in decrypted_data else '未知时间'

        # 校验end_time有效性
        if end_time in ['未知时间', '']:
            return {"code": -2, "msg": "验证异常!"}

        # 调用验证函数
        result_json = check_date_validation(end_time)
        return result_json
    except Exception as e:
        logger.error(f"配置解析异常：{str(e)}")
        return {"code": -2, "msg": f"验证异常!"}



# ========== 根目录适配函数 ==========
def get_app_root_dir():
    """
    获取应用程序根目录（兼容IDE运行/打包后）
    - IDE运行：返回项目根目录（gui/ 的上一级）
    - 打包后：返回exe所在目录（dist/ 根目录）
    """
    import sys
    import os

    if getattr(sys, 'frozen', False):
        # 打包后（Nuitka/PyInstaller）：exe所在目录 = 根目录
        root_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        # IDE运行：当前文件（MainApp.py）在gui/下，取上一级 = 项目根目录
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(current_file_dir)  # 向上一级到项目根

    return root_dir

# ====================== 4. 原有测试函数（保留） ======================
def validate_in_sleep():
    while True:
        jsont = check_date_validation_by_config()
        sleep(2)
        print(f"正在运行中，监测结果：{jsont['msg']}")
        if jsont['code'] != 1:
            return False


def adapt_component_size(
        w: Optional[Union[int, float, List[Union[int, float]]]] = None,
        h: Optional[Union[int, float, List[Union[int, float]]]] = None
) -> Union[Dict, List[int]]:
    base_screen_w = 2560
    scale_ratio = 1.0

    # ========== PyQt5 原生分辨率获取（仅复用实例，不主动创建，规避 Qt 初始化错误） ==========
    try:
        # 核心：仅复用项目主入口已创建的 QApplication 实例，绝不主动新建
        app = QApplication.instance()
        if app is None:
            # 无实例时抛出明确提示，而非创建（项目运行时必有实例，此分支仅单独运行该文件时触发）
            raise RuntimeError("未检测到QApplication实例！请确保PyQt5项目主入口已提前初始化QApplication")

        # PyQt5 原生方法获取主屏幕分辨率，稳定无冲突
        screen = app.primaryScreen()
        current_w = screen.size().width()  # 获取屏幕实际宽度，与原tkinter逻辑一致
        scale_ratio = current_w / base_screen_w  # 计算缩放比例，完全保留原业务逻辑
    except RuntimeError as e:
        # 捕获无实例的明确错误，打印提示并使用默认缩放比例
        print(f"【警告】{e}，将使用默认缩放比例1.0")
    except Exception as e:
        # 捕获其他意外错误（如屏幕获取失败），兼容兜底
        print(f"【警告】获取屏幕尺寸失败，使用默认缩放比例1.0，错误信息：{e}")
    # ========== PyQt5 分辨率获取结束，后续逻辑完全不变 ==========

    # 原尺寸缩放逻辑，无需任何修改，保持业务一致性
    if isinstance(w, list) and h is None:
        scaled_list = []
        for item in w:
            if isinstance(item, (int, float)):
                scaled_list.append(int(item * scale_ratio))
            else:
                scaled_list.append(0)
        return scaled_list
    elif isinstance(h, list) and w is None:
        scaled_list = []
        for item in h:
            if isinstance(item, (int, float)):
                scaled_list.append(int(item * scale_ratio))
            else:
                scaled_list.append(0)
        return scaled_list

    target_w = int(w * scale_ratio) if (w is not None and isinstance(w, (int, float))) else 0
    target_h = int(h * scale_ratio) if (h is not None and isinstance(h, (int, float))) else 0
    return {
        "w": target_w,
        "h": target_h
    }