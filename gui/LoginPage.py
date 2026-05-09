import json
import os
import sys
import time
from collections import deque
from datetime import datetime

import requests
from PyQt5.QtCore import Qt, QMutex, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QFrame, QMessageBox, QFormLayout, QApplication, QLayout)
from loguru import logger

from config.kami_config import kami_config
from config.py_config import config_value
from gui.MainApp import MainStartApp
from gui.utils.encryptData import CryptoUtils
from gui.utils.jiami import LoginDataEncryptor
from gui.utils.window_adapter import adapt_window_size
from lite_modules.LittleTools import check_date_validation
from modules.internet_status import NetworkChecker
from modules.machine_code import get_unique_machine_code


def detect_system_proxy() -> dict:
    """
    检测系统是否配置了代理
    返回: {"enabled": bool, "http": str, "https": str, "source": str}
    """
    result = {"enabled": False, "http": "", "https": "", "source": ""}
    
    # 1. 检测环境变量中的代理
    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    
    if http_proxy or https_proxy:
        result["enabled"] = True
        result["http"] = http_proxy or ""
        result["https"] = https_proxy or ""
        result["source"] = "环境变量"
        return result
    
    # 2. 检测 Windows 系统代理设置（通过注册表）
    if sys.platform == "win32":
        try:
            import winreg
            # 打开 Internet Settings 注册表项
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                               r"Software\Microsoft\Windows\CurrentVersion\Internet Settings") as key:
                try:
                    proxy_enable = winreg.QueryValueEx(key, "ProxyEnable")[0]
                    if proxy_enable:
                        result["enabled"] = True
                        proxy_server = winreg.QueryValueEx(key, "ProxyServer")[0]
                        result["http"] = proxy_server
                        result["https"] = proxy_server
                        result["source"] = "Windows系统代理"
                        return result
                except FileNotFoundError:
                    pass
        except Exception as e:
            logger.debug(f"检测Windows系统代理失败: {e}")
    
    return result


def check_server_without_proxy(url: str, timeout: int = 10) -> dict:
    """
    绕过所有代理直接检测服务器可达性
    返回: {"reachable": bool, "response": Response or None, "error": str}
    """
    # 创建不信任环境变量的 Session，绕过系统代理
    session = requests.Session()
    session.trust_env = False  # 关键：不使用环境变量和系统代理设置
    
    try:
        response = session.get(url, timeout=timeout)
        return {"reachable": True, "response": response, "error": ""}
    except requests.exceptions.RequestException as e:
        return {"reachable": False, "response": None, "error": str(e)}
    finally:
        session.close()


class LoginThread(QThread):
    login_result = pyqtSignal(bool, str, dict, dict)  # 调整信号：传递用户数据字典（含有效期等）和额外信息（如版本更新链接）

    def __init__(self, kami, encryptor: LoginDataEncryptor = None, parent=None):
        super().__init__(parent)
        self.kami = kami
        self.parent = parent
        self.encryptor = encryptor

    def run(self):
        try:
            api_url = f"{config_value.server_api_domain}/index.php?static_token={config_value.static_token}"
            
            # ========== 核心改动：使用绕过代理的直接检测 ==========
            # 检测系统是否配置了代理
            proxy_info = detect_system_proxy()
            
            # 使用 trust_env=False 的 Session 绕过所有代理直接检测服务器
            direct_check = check_server_without_proxy(api_url, timeout=10)
            server_directly_reachable = direct_check["reachable"]
            
            logger.info(f"系统代理状态: {proxy_info}")
            logger.info(f"绕过代理直接检测服务器: {'可达' if server_directly_reachable else '不可达'}")
            
            # 服务器是否真的不可达（只有直接检测不可达才算真的不可达）
            lixian = not server_directly_reachable

            checker = NetworkChecker()
            is_online, _ = checker.is_connected()  # 设备是否联网

            # 处理ikun卡密  离线登录 服务器失效之后购买过卡密的用户仍然可用，可能无限续期
            if self.kami == 'ikun':
                try:
                    # self.login_result.emit(False, f"离线登录失败：你的设备暂不支持离线登录", {})
                    # return

                    with open(f"{config_value.login_data_path}", "r") as f:
                        encrypted_data = f.read()
                    decrypted_data = self.encryptor.decrypt(encrypted_data)

                    local_kami = decrypted_data.get('kami', '获取失败')
                    end_time = decrypted_data.get('end_time', '未知时间')
                    start_time = decrypted_data.get('start_time', '未知时间')
                    machine = decrypted_data.get('machine', '获取失败')

                    # ========== 修正后的离线登录条件判断 ==========
                    # 条件1：设备必须联网（否则拒绝）
                    if not is_online:
                        self.login_result.emit(False, "设备未联网，无法使用离线登录，请先连接网络", {}, {})
                        return

                    # 条件2：检测到系统配置了代理，拒绝离线登录
                    if proxy_info["enabled"]:
                        proxy_msg = f"检测到系统配置了代理({proxy_info['source']})\n禁止使用离线卡密，请关闭代理后重试"
                        self.login_result.emit(False, proxy_msg, {}, {})
                        return

                    # 条件3：仅服务器不可达时，才允许离线登录
                    if not lixian:  # 服务器可达 → 强制走在线验证，拒绝离线登录
                        self.login_result.emit(False, "服务器正常可用，禁止使用离线卡密，请输入真实卡密登录", {}, {})
                        return

                    # 条件4：机器码匹配
                    current_machine_code = get_unique_machine_code()
                    if not current_machine_code:
                        self.login_result.emit(False, "无法获取机器码，请检查系统权限或重启软件", {}, {})
                        return
                        
                    if machine != current_machine_code:
                        self.login_result.emit(False, "机器码不匹配", {}, {})
                        return

                    # 条件5：卡密未过期
                    result_json = check_date_validation(end_time)
                    if result_json["code"] != 1:
                        self.login_result.emit(False, result_json.get('msg', '卡密已过期'), {}, {})
                        return

                    # 所有条件满足 → 允许离线登录
                    user_data = {
                        'start_time': start_time,
                        'end_time': end_time,
                        'kami': local_kami
                    }
                    self.login_result.emit(True, "离线模式登录\n", user_data, {})
                    return

                except Exception as e:
                    self.login_result.emit(False, f"离线登录失败：{str(e)}", {}, {})
                    return

            # 非ikun卡密 → 强制走在线验证
            timestamp = int(time.time())
            raw_machine_code = get_unique_machine_code()
            
            logger.info(f"获取机器码结果: {raw_machine_code}")
            
            # 检查机器码是否为None，如果是则返回错误
            if not raw_machine_code:
                self.login_result.emit(False, "无法获取机器码，请检查系统权限或重启软件", {}, {})
                return
                
            machine_code = f"{config_value.prefix_token}-{raw_machine_code}"
            encrypted_machine_code = CryptoUtils.encrypt_data(machine_code)
            encrypted_kami = CryptoUtils.encrypt_data(self.kami)
            encrypted_version = CryptoUtils.encrypt_data(config_value.current_version)
            signature = CryptoUtils.generate_signature(self.kami, timestamp)
            payload = {
                'encrypted_kami': encrypted_kami,
                'timestamp': timestamp,
                'signature': signature,
                'encrypted_machine_code': encrypted_machine_code,
                'encrypted_version': encrypted_version
            }

            response = requests.post(api_url, data=payload, proxies=None, timeout=10)
            response.raise_for_status()

            try:
                respdata = response.json()
            except json.JSONDecodeError as e:
                self.login_result.emit(False, f"服务器返回非JSON数据：{str(e)}", {}, {})
                return

            if response.status_code != 200:
                msg = f"HTTP错误 {response.status_code}：{respdata.get('msg', '网络异常')}"
                self.login_result.emit(False, msg, {}, {})
                return



            if respdata.get('code') != 1:
                self.login_result.emit(False, respdata.get('msg', '卡密无效'), {}, {})
                return

            bind_text = '卡密成功绑定本设备\n登录后可在后台解绑卡密\n\n' if respdata.get(
                'msg') == '机器码绑定成功，登录验证通过' else ''

            if 'data' in respdata and respdata['data']:
                try:
                    decrypted_str = CryptoUtils.decrypt_data(respdata['data'])
                    user_data = json.loads(decrypted_str)

                    # print(user_data)
                    if not isinstance(user_data, dict):
                        raise ValueError("用户数据格式错误")

                    result_json = check_date_validation(user_data.get('end_time'))
                    if result_json["code"] != 1:
                        self.login_result.emit(False, result_json.get('msg', '卡密已过期'), {}, {})
                        return

                    if user_data.get('kami') == self.kami:
                        encryptor = LoginDataEncryptor()
                        encryptor.save_login_data(user_data)
                        self.login_result.emit(True, bind_text, user_data, {})
                        return
                except Exception as e:
                    self.login_result.emit(False, f"数据处理异常：{str(e)}", {}, {})
                    return

            self.login_result.emit(False, "未知错误（无有效用户数据）", {}, {})

        except requests.exceptions.RequestException as e:
            self.login_result.emit(False,
                                   f"网络异常，请检查是否联网" if not is_online else f"联网验证暂不可用，请使用离线卡密(ikun) 登录",
                                   {}, {})
        except Exception as e:
            self.login_result.emit(False, f"系统异常：{str(e)}", {}, {})


class RateLimiter:
    def __init__(self, max_calls, interval):
        self.max_calls = max_calls
        self.interval = interval
        self.calls = deque()
        self.mutex = QMutex()

    def check_limit(self):
        self.mutex.lock()
        try:
            current_time = time.time()
            while self.calls and current_time - self.calls[0] > self.interval:
                self.calls.popleft()
            if len(self.calls) >= self.max_calls:
                return False
            self.calls.append(current_time)
            return True
        finally:
            self.mutex.unlock()


class LoginWindow(QWidget):
    def __init__(self, any_kami_mode=False, code_project_mode_debug=None):
        super().__init__()
        self.any_kami_mode = any_kami_mode  # 任意卡密模式标志
        self.code_project_mode_debug = code_project_mode_debug or []  # 调试模式下的权限列表
        self.setWindowTitle("ikun联盟 - 登录")
        # 使用统一的窗口尺寸适配函数，基准尺寸：500×300（2560分辨率下）
        adapt_window_size(self, 620, 380)
        self.setWindowIcon(QIcon("gui/img/favicon.ico"))
        self.rate_limiter = RateLimiter(max_calls=3, interval=2)  # 修正参数与提示一致
        self.kami_success = False
        self.config = None
        self.duration = "未知"
        self.start_time_strp = ""
        self.end_time_strp = ""
        self.encryptor = LoginDataEncryptor()
        self.setup_ui()

        if kami_config.get("auto_login", "否") == "是" and not any_kami_mode:
            QTimer.singleShot(1, self._auto_login)

    def _auto_login(self):
        try:
            saved_kami = kami_config.get_kami()
            if saved_kami:
                self.kami_input.setText(saved_kami)
                self.handle_login()
            else:
                print("未找到保存的卡密，跳过自动登录")
        except Exception as e:
            print(f"自动登录出错: {e}")


    def setup_ui(self):
        # 创建背景标签
        self.background_label = QLabel(self)
        self.background_label.setPixmap(QPixmap("gui/img/beijingtu.png"))
        self.background_label.setScaledContents(True)
        # 初始设置背景覆盖整个窗口
        self.background_label.setGeometry(0, 0, self.width(), self.height())
        # 将背景标签置于底层
        self.background_label.lower()

        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignCenter)
        main_layout.setSpacing(20)

        # 根据模式设置标题
        if self.any_kami_mode:
            title_text = "IKUN 登录-免密"
            placeholder_text = "请输入任意字符登录"
        else:
            title_text = "IKUN 登录"
            placeholder_text = "请输入卡密"
        
        title_label = QLabel(title_text)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 40px; font-weight: bold; color: #007BFF;")

        form_frame = QFrame()
        form_layout = QFormLayout()
        form_layout.setSpacing(40)
        form_layout.setLabelAlignment(Qt.AlignRight)

        self.kami_input = QLineEdit()
        self.kami_input.setPlaceholderText(placeholder_text)
        # 任意卡密模式下，预填充一个默认值
        if self.any_kami_mode:
            self.kami_input.setText("any")
        else:
            self.kami_input.setText(kami_config.get_kami())
        self.kami_input.setStyleSheet("""
                QLineEdit {
                    font-size: 24px;
                    font-weight: bold;
                    border: 1px solid #007BFF;
                    padding: 8px;
                    border-radius: 4px;
                    background-color: white;
                }
            """)
        form_layout.addRow("卡密:", self.kami_input)

        kami_label = form_layout.labelForField(self.kami_input)
        kami_label.setStyleSheet("font-size: 24px; font-weight: bold;")

        # 创建按钮布局容器
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setSpacing(0)
        button_layout.setContentsMargins(0, 0, 0, 0)

        # 版本迁移按钮（放在中间）
        self.migration_button = QPushButton("版本迁移")
        self.migration_button.clicked.connect(self.open_version_migration)
        self.migration_button.setStyleSheet("""
            QPushButton {
                background-color: #FFC107;
                color: white;
                font-size: 20px;
                font-weight: bold;
                padding: 15px 25px;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #FFA000;
            }
        """)
        self.migration_button.setIcon(QIcon("gui/img/tijiao.png"))
        
        # 登录按钮（放在右侧）
        self.login_button = QPushButton("登录")
        self.login_button.clicked.connect(self.handle_login)
        self.login_button.setStyleSheet("""
            QPushButton {
                background-color: #007BFF;
                color: white;
                font-size: 20px;
                font-weight: bold;
                padding: 15px 25px;
                border-radius: 4px;
                min-width: 100px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
        """)
        
        # 使用比例布局：左空白:按钮:中间空白:按钮:右空白 = 1:1:1:1:1
        button_layout.addStretch(1)
        button_layout.addWidget(self.migration_button)
        button_layout.addStretch(1)
        button_layout.addWidget(self.login_button)
        button_layout.addStretch(1)

        button_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.addRow(button_container)

        form_frame.setLayout(form_layout)
        main_layout.addWidget(title_label)
        main_layout.addWidget(form_frame)
        self.setLayout(main_layout)
    
    def resizeEvent(self, event):
        """窗口大小改变时，调整背景图片大小"""
        super().resizeEvent(event)
        # 更新背景标签的大小以覆盖整个窗口
        self.background_label.setGeometry(0, 0, self.width(), self.height())

    def handle_login(self):
        kami = self.kami_input.text().strip()
        
        # 任意卡密模式：只要有输入即可（允许任意字符）
        if self.any_kami_mode:
            if not kami:
                QMessageBox.warning(self, "错误", "请输入任意字符！")
                return
            # 直接调用登录成功处理，使用配置的权限
            self._handle_any_kami_login(kami)
            return
        
        # 正常卡密模式：不能为空
        if not kami:
            QMessageBox.warning(self, "错误", "卡密不能为空!")
            return

        if not self.rate_limiter.check_limit():
            QMessageBox.warning(self, "请求过于频繁", "每2秒最多只能请求3次，请稍后再试!")
            return
        self.kami_input.setEnabled(False)
        self.login_button.setEnabled(False)
        self.login_button.setText("验证中...")

        self.login_thread = LoginThread(kami, self.encryptor, self)
        self.login_thread.login_result.connect(self.on_login_result)
        self.login_thread.start()
    
    def _handle_any_kami_login(self, kami):
        """处理任意卡密登录"""
        try:
            # 禁用按钮
            self.kami_input.setEnabled(False)
            self.login_button.setEnabled(False)
            self.login_button.setText("登录中...")
            
            # 使用配置的权限列表
            code_project_mode = self.code_project_mode_debug
            
            # 设置一个默认的有效期（9999天）
            from datetime import datetime, timedelta
            start_time = datetime.now().strftime("%Y-%m-%d")
            end_time = (datetime.now() + timedelta(days=9999)).strftime("%Y-%m-%d")
            
            user_data = {
                'start_time': start_time,
                'end_time': end_time,
                'kami': kami,
                'temu': 'True' if 'temu' in code_project_mode else 'False',
                'caiwu': 'True' if 'caiwu' in code_project_mode else 'False',
                'spider': 'True' if 'spider' in code_project_mode else 'False',
                'ddos': 'True' if 'ddos' in code_project_mode else 'False'
            }
            
            # 保存加密登录数据（使 DateCheckThread 能正确读取有效期）
            self.encryptor.save_login_data(user_data)
            
            # 模拟登录成功
            self.on_login_result(True, "任意卡密模式登录成功\n", user_data, {})
            
        except Exception as e:
            logger.error(f"任意卡密登录失败: {e}")
            QMessageBox.critical(self, "错误", f"登录失败: {str(e)}")
            self.kami_input.setEnabled(True)
            self.login_button.setEnabled(True)
            self.login_button.setText("登录")

    def calculate_remaining_days(self, start_time_str, end_time_str):
        """
        计算卡密剩余天数
        :param start_time_str: 开始时间字符串（格式：YYYY-MM-DD HH:MM:SS）
        :param end_time_str: 结束时间字符串（格式：YYYY-MM-DD HH:MM:SS）
        :return: 剩余天数（字符串）
        """
        try:
            # 定义时间格式（根据你的实际时间格式调整，这是最常用的格式）
            time_format = "%Y-%m-%d"
            # 解析开始和结束时间
            end_time = datetime.strptime(end_time_str, time_format)
            now = datetime.now()

            # 计算剩余时间
            if end_time > now:
                remaining_days = (end_time - now).days
                return str(remaining_days)
            else:
                return "0"  # 已过期
        except Exception as e:
            # 解析失败时返回"未知"，避免程序崩溃
            return "未知"

    def on_login_result(self, success, msg, user_data, extra_info):
        self.login_button.setEnabled(True)
        self.kami_input.setEnabled(True)
        self.login_button.setText("登录")

        if success:
            # 核心修改：调用新算法计算剩余天数
            start_time = user_data.get('start_time', '未知时间')
            end_time = user_data.get('end_time', '未知时间')
            self.duration = self.calculate_remaining_days(start_time, end_time)
            self.kami_success = True

            spider = user_data.get('spider', "False")
            ddos = user_data.get('ddos', "False")
            temu = user_data.get('temu', "False")
            caiwu = user_data.get('caiwu', "False")

            code_project_mode = []

            if spider == "True":
                code_project_mode.append("spider")
            if ddos == "True":
                code_project_mode.append("ddos")
            if temu == "True":
                code_project_mode.append("temu")
            if caiwu == "True":
                code_project_mode.append("caiwu")

            # 保存权限到配置文件（快速操作）
            from config.permission_manager import permission_manager
            permission_manager.save_permissions(code_project_mode)
            logger.info(f"✅ 权限已保存到配置文件: {code_project_mode}")

            # 从配置文件读取 machine_code（快速操作）
            machine_code = kami_config.get("machine_code", "")
            if not machine_code:
                machine_code = get_unique_machine_code()
                kami_config.set("machine_code", machine_code)
                logger.info(f"✅ machine_code 已保存到配置文件: {machine_code}")

            if user_data.get('kami') != kami_config.get_kami():
                kami_config.set_kami(self.kami_input.text().strip())
            
            # 立即显示主窗口（不等待数据库初始化）
            self.open_main_window(msg, code_project_mode)
            
            # 异步初始化数据库（在后台进行，不阻塞UI）
            QTimer.singleShot(100, lambda: self._init_database_async(code_project_mode))
            
            # 启动定时任务执行器
            try:
                from utils.scheduled_task_executor import start_scheduled_task_executor
                start_scheduled_task_executor()
            except Exception as e:
                logger.error(f"定时任务执行器启动失败: {e}")
        else:
            # 检查是否是版本过低的错误
            if extra_info and 'update_url' in extra_info:
                self.show_version_update_dialog(msg, extra_info['update_url'])
            else:
                QMessageBox.warning(self, "登录失败", msg)
    
    def _init_database_async(self, code_project_mode):
        """异步初始化数据库（不阻塞UI）"""
        try:
            from config.common_config import initialize_all_databases
            
            logger.info(f"✅ 开始异步初始化数据库，权限: {code_project_mode}")
            
            # 统一初始化所有数据库
            success = initialize_all_databases(code_project_mode)
            
            if success:
                logger.info("✅ 所有数据库初始化完成")
            else:
                logger.warning("⚠️ 部分数据库初始化失败")
        
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")

    def open_main_window(self, msg=None, code_project_mode=None):
        legal_dialog = QMessageBox(self)
        legal_dialog.setWindowTitle("法律声明")
        legal_dialog.setIcon(QMessageBox.Information)
        legal_dialog.setText("法律风险提醒")
        legal_dialog.setInformativeText(
            f"{msg or ''}"
            "1. 本软件仅供学习交流使用\n"
            "2. 禁止用于任何非法用途\n"
            "3. 使用者需遵守当地法律法规\n"
            "4. 违规使用造成后果自行承担\n"
            "5. 只有真ikun才可使用！\n"
            f"卡密剩余天数：{self.duration}天\n"
        )

        yes_btn = legal_dialog.addButton("同意", QMessageBox.YesRole)
        no_btn = legal_dialog.addButton("拒绝", QMessageBox.NoRole)
        legal_dialog.setDefaultButton(no_btn)
        legal_dialog.layout().setSizeConstraint(QLayout.SetFixedSize)
        legal_dialog.setWindowModality(Qt.ApplicationModal)

        legal_dialog.exec_()
        if legal_dialog.clickedButton() == yes_btn:
            self.main_window = MainStartApp(code_project_mode_debug=code_project_mode)
            self.main_window.show()
            self.close()
        else:
            QMessageBox.warning(self, "拒绝条款", "拒绝条款，禁止使用本程序！")

    def open_version_migration(self):
        """打开版本迁移窗口"""
        try:
            from gui.MigrationPage import MigrationWindow
            
            # 弹出确认弹窗
            reply = QMessageBox.question(
                self,
                "确认打开版本迁移",
                "是否打开版本迁移窗口？打开后将关闭登录窗口。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                # 不传递父窗口，让版本迁移窗口独立运行
                self.migration_window = MigrationWindow()
                self.migration_window.show()
                
                # 立即关闭登录窗口
                self.close()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开版本迁移窗口失败：{str(e)}")

    def show_version_update_dialog(self, msg, update_url):
        """显示版本更新弹窗"""
        import webbrowser
        dialog = QMessageBox(self)
        dialog.setWindowTitle("版本更新")
        dialog.setIcon(QMessageBox.Warning)
        dialog.setText("版本过低")
        dialog.setInformativeText(msg)
        
        # 添加打开官网按钮
        open_url_btn = dialog.addButton("打开官网", QMessageBox.ActionRole)
        cancel_btn = dialog.addButton("取消", QMessageBox.RejectRole)
        
        dialog.exec_()
        
        if dialog.clickedButton() == open_url_btn:
            webbrowser.open(update_url)

    def get_machine_code_from_db(self):
        """从数据库读取 machine_code"""
        try:
            from config.common_config import db

            result = db.execute_sql(
                "SELECT value FROM config WHERE key = 'machine_code' AND is_deleted = 0",
                fetch="fetch_one"
            )

            if result and result.get("value"):
                return result["value"]

            return None
        except Exception as e:
            logger.error(f"从数据库读取 machine_code 失败: {str(e)}")
            return None

    def save_machine_code_to_db(self, machine_code):
        """保存 machine_code 到数据库"""
        try:
            from config.common_config import db

            # 检查是否已存在 machine_code 记录
            result = db.execute_sql(
                "SELECT id FROM config WHERE key = 'machine_code' AND is_deleted = 0",
                fetch="fetch_one"
            )

            if result:
                # 更新现有记录
                db.execute_sql(
                    "UPDATE config SET value = ?, update_time = datetime('now') WHERE key = 'machine_code'",
                    (machine_code,),
                    commit=True
                )
                logger.info(f"machine_code 已更新到数据库")
            else:
                # 插入新记录
                db.execute_sql(
                    "INSERT INTO config (key, value, create_time, update_time, is_deleted) VALUES (?, ?, datetime('now'), datetime('now'), 0)",
                    ("machine_code", machine_code),
                    commit=True
                )
                logger.info(f"machine_code 已保存到数据库")
        except Exception as e:
            logger.error(f"保存 machine_code 到数据库失败: {str(e)}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    login_window = LoginWindow()
    login_window.show()
    sys.exit(app.exec_())