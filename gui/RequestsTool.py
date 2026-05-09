import asyncio
import json
import sys

import aiohttp
from PyQt5.QtCore import Qt, QObject, pyqtSignal
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QGroupBox, QHBoxLayout,
                             QPushButton, QTabWidget, QTextEdit, QDialog, QScrollArea,
                             QLabel, QLineEdit, QSizePolicy, QFormLayout, QComboBox, QCheckBox, QMessageBox)
from qasync import asyncSlot, QEventLoop

from config.common_config import config_manager

# 基础默认配置（仅作为兜底）
BASE_DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Content-Type": "application/json",  # 默认改为JSON更通用
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


class AsyncRequestWorker(QObject):
    """异步请求工作器（修复：根据Content-Type自动适配传参方式）"""
    finished = pyqtSignal(object)  # 响应数据
    error = pyqtSignal(str)  # 错误信息
    stopped = False

    def __init__(self, method, url, params, headers=None, cookies=None):
        super().__init__()
        self.method = method
        self.url = url
        self.params = params
        # 使用传入的配置（已从数据库读取），兜底用基础默认值
        self.headers = headers or BASE_DEFAULT_HEADERS.copy()
        self.cookies = cookies or {}

    async def fetch(self):
        """执行HTTP请求（核心修复：根据Content-Type自动选择传参方式）"""
        try:
            # 处理Cookie
            cookie_jar = aiohttp.CookieJar()
            for name, value in self.cookies.items():
                cookie_jar.update_cookies({name: value})

            async with aiohttp.ClientSession(cookie_jar=cookie_jar) as session:
                # 1. 解析Content-Type，决定传参方式
                content_type = self.headers.get('Content-Type', 'application/json').lower()
                request_kwargs = {"headers": self.headers.copy()}  # 请求通用参数

                # 2. 处理请求参数（简化处理，直接使用字典）
                if self.params:
                    # 参数在__init__中已经确保是字符串格式，直接解析为字典
                    try:
                        # 按JSON解析为字典
                        params_dict = json.loads(self.params)
                    except json.JSONDecodeError:
                        # 解析失败则按form格式解析
                        from urllib.parse import parse_qs
                        params_dict = parse_qs(self.params)
                    
                    # 区分GET/POST/PUT等方法的参数位置
                    if self.method.upper() == "GET":
                        # GET请求：参数放URL查询字符串
                        request_kwargs["params"] = params_dict
                    else:
                        # POST/PUT等请求：直接使用json参数传递字典
                        # aiohttp会自动处理JSON序列化
                        request_kwargs["json"] = params_dict
                else:
                    # 无参数时清空请求体/URL参数
                    request_kwargs["data"] = b""

                # 3. 发送请求（自动适配方法）
                if self.method.upper() == "GET":
                    async with session.get(self.url, **request_kwargs) as response:
                        return await self.process_response(response)
                elif self.method.upper() == "POST":
                    async with session.post(self.url, **request_kwargs) as response:
                        return await self.process_response(response)
                elif self.method.upper() == "PUT":
                    async with session.put(self.url, **request_kwargs) as response:
                        return await self.process_response(response)
                elif self.method.upper() == "DELETE":
                    async with session.delete(self.url, **request_kwargs) as response:
                        return await self.process_response(response)
                else:
                    self.error.emit(f"不支持的请求方法: {self.method}")
                    return None

        except asyncio.CancelledError:
            if not self.stopped:
                self.error.emit("请求被取消")
            return None
        except Exception as e:
            if not self.stopped:
                self.error.emit(str(e))
            return None

    async def process_response(self, response):
        """处理响应数据（简化：移除多余的request_headers参数）"""
        try:
            response_text = await response.text()
            return {
                "headers": {
                    "状态码": response.status,
                    "响应头": dict(response.headers)
                },
                "content": response_text,
                "request_headers": self.headers
            }
        except Exception as e:
            return {
                "headers": {"状态码": 0, "响应头": {}},
                "content": f"处理响应时出错: {str(e)}",
                "request_headers": self.headers
            }

    def stop(self):
        """停止请求"""
        self.stopped = True


class RequestsTool(QMainWindow):
    """核心HTTP请求工具（基础设置放首页）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("HTTP请求工具")
        self.setWindowIcon(QIcon('gui/img/favicon.ico') if 'gui/img/favicon.ico' else QIcon())
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self.current_worker = None  # 当前请求工作器
        self.config = config_manager

        # 初始化UI（基础设置置顶）
        self.init_ui()
        # 加载基础配置（启动时加载一次，后续每次请求重新读取）
        self.load_basic_config()

    def init_ui(self):
        """初始化主界面（基础设置置顶）"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # 基础请求设置
        basic_group = QGroupBox("基础请求设置")
        basic_layout = QFormLayout(basic_group)
        basic_layout.setLabelAlignment(Qt.AlignRight)

        # 请求方法
        self.method_combo = QComboBox()
        self.method_combo.addItems(["GET", "POST", "PUT", "DELETE"])
        basic_layout.addRow("请求方法:", self.method_combo)

        # URL输入
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("请输入请求URL (建议填写如\"https://\"的完整协议)")
        basic_layout.addRow("请求URL:", self.url_input)

        # 请求参数
        self.params_input = QTextEdit()
        self.params_input.setPlaceholderText("请求参数将显示在这里(JSON格式)\n例如：{\"page\":2, \"page_size\":2}")
        self.params_input.setMaximumHeight(100)
        basic_layout.addRow("请求参数:", self.params_input)

        # 操作按钮
        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)

        self.param_btn = QPushButton("添加参数")
        self.param_btn.clicked.connect(self.create_param_dialog)
        self.param_btn.setIcon(QIcon('gui/img/fuzhi.png') if 'gui/img/fuzhi.png' else QIcon())
        button_layout.addWidget(self.param_btn)

        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self.send_http_request)
        self.send_btn.setIcon(QIcon('gui/img/tijiao.png') if 'gui/img/tijiao.png' else QIcon())
        button_layout.addWidget(self.send_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self.stop_request)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setIcon(QIcon('gui/img/stop.png') if 'gui/img/stop.png' else QIcon())
        button_layout.addWidget(self.stop_btn)

        self.clear_log_btn = QPushButton("清空日志")
        self.clear_log_btn.clicked.connect(self.clear_log)
        self.clear_log_btn.setIcon(QIcon('gui/img/qingli.png') if 'gui/img/qingli.png' else QIcon())
        button_layout.addWidget(self.clear_log_btn)

        self.save_btn = QPushButton("保存配置")
        self.save_btn.clicked.connect(self.save_config)
        self.save_btn.setIcon(QIcon('gui/img/baochun.png') if 'gui/img/baochun.png' else QIcon())
        button_layout.addWidget(self.save_btn)

        # JSON自动解码开关（放按钮行右侧）
        self.json_decode_check = QCheckBox("自动解码JSON")
        self.json_decode_check.stateChanged.connect(self.on_json_decode_check)
        button_layout.addStretch()
        button_layout.addWidget(self.json_decode_check)

        # 响应日志区域
        response_group = QGroupBox("响应日志")
        response_layout = QVBoxLayout(response_group)

        self.response_tabs = QTabWidget()
        self.response_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 响应内容
        self.response_content = QTextEdit()
        self.response_content.setReadOnly(True)
        self.response_tabs.addTab(self.response_content, "响应内容")

        # 响应头
        self.response_headers = QTextEdit()
        self.response_headers.setReadOnly(True)
        self.response_tabs.addTab(self.response_headers, "响应头")

        # 日志输出
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setAcceptRichText(True)
        self.response_tabs.addTab(self.log_output, "日志")

        response_layout.addWidget(self.response_tabs)

        # 组装布局
        layout.addWidget(basic_group)
        layout.addWidget(button_row)
        layout.addWidget(response_group)

        # 窗口尺寸
        self.resize(1100, 900)
        
        # 加载保存的配置

    def load_basic_config(self):
        """启动时加载基础配置（兜底用）"""
        # 基础请求配置
        self.method_combo.setCurrentText(self.config.get_or_set_config("RequestSettings_method", "GET"))
        self.url_input.setText(self.config.get_or_set_config("RequestSettings_url", ""))
        self.params_input.setPlainText(self.config.get_or_set_config("RequestSettings_params", ""))

        # JSON解码配置
        json_decode_enabled = self.config.get_or_set_config("RequestSettings_json_decode_enabled", "True")
        self.json_decode_check.setChecked(json_decode_enabled.lower() == "true")

    def get_config_from_db(self):
        """从配置管理器加载最新配置"""
        try:
            # 读取Headers相关配置
            headers_mode = self.config.get_or_set_config("RequestSettings_headers_mode", "default")
            content_type = self.config.get_or_set_config("RequestSettings_content_type", "application/json")
            ua_default_str = self.config.get_or_set_config("RequestSettings_ua_default", "True")
            ua_default = ua_default_str.lower() == "true"
            user_agent = self.config.get_or_set_config("RequestSettings_user_agent", BASE_DEFAULT_HEADERS["User-Agent"])
            custom_headers_text = self.config.get_or_set_config("RequestSettings_custom_headers", "")

            # 读取Cookie相关配置
            cookie_mode = self.config.get_or_set_config("RequestSettings_cookie_mode", "none")

            # 自定义Cookie内容
            cookie_text = self.config.get_or_set_config("RequestSettings_cookies", "")

            # 解析Headers配置
            if headers_mode == "custom" and custom_headers_text:
                try:
                    headers = json.loads(custom_headers_text)
                except json.JSONDecodeError:
                    # 解析失败时，使用默认组合值
                    headers = {
                        "Accept": "*/*",
                        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                        "Connection": "keep-alive",
                        "Content-Type": content_type,
                        "User-Agent": BASE_DEFAULT_HEADERS["User-Agent"] if ua_default else user_agent
                    }
                    self.log(f"自定义Headers解析失败，使用默认组合值: {custom_headers_text}", "red")
            else:
                # 默认模式：拼接基础Headers + Content-Type + User-Agent
                headers = {
                    "Accept": "*/*",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Connection": "keep-alive",
                    "Content-Type": content_type,
                    "User-Agent": BASE_DEFAULT_HEADERS["User-Agent"] if ua_default else user_agent
                }

            # 解析Cookie配置
            if cookie_mode == "custom" and cookie_text:
                try:
                    cookies = json.loads(cookie_text)
                except json.JSONDecodeError:
                    cookies = {}
                    self.log(f"Cookie解析失败，使用空值: {cookie_text}", "red")
            else:
                cookies = {}

            self.log("成功从配置管理器加载最新Headers/Cookie配置", "blue")
            return headers, cookies

        except Exception as e:
            self.log(f"从配置管理器读取配置失败，使用兜底默认值: {str(e)}", "red")
            # 兜底默认配置
            default_headers = {
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Connection": "keep-alive",
                "Content-Type": "application/json",
                "User-Agent": BASE_DEFAULT_HEADERS["User-Agent"]
            }
            return default_headers, {}

    @asyncSlot()
    async def send_http_request(self):
        """发送HTTP请求（每次请求前从数据库读取最新配置）"""
        try:
            # 从数据库读取最新配置
            headers, cookies = self.get_config_from_db()

            # 获取基础配置并验证
            method = self.method_combo.currentText()
            url = self.url_input.text().strip()
            params_text = self.params_input.toPlainText()

            params = params_text

            if not url:
                self.log("错误: URL不能为空", "red")
                return

            # 补全URL协议
            if '://' not in url:
                url = f"http://{url}"

            # 禁用按钮，显示加载状态
            self.send_btn.setEnabled(False)
            self.send_btn.setText("发送中...")
            self.stop_btn.setEnabled(True)

            # 打印请求信息到日志
            self.log(f"发送 {method} 请求到: {url}", "blue")
            self.log(f"使用Headers: {json.dumps(headers, indent=2, ensure_ascii=False)}", "blue")
            if cookies:
                self.log(f"使用Cookies: {json.dumps(cookies, indent=2, ensure_ascii=False)}", "blue")
            if params:
                self.log(f"请求参数: {params}", "blue")

            # 创建异步请求工作器
            self.current_worker = AsyncRequestWorker(method, url, params, headers, cookies)

            # 绑定响应处理（弱引用避免内存泄漏）
            import weakref
            self_ref = weakref.ref(self)

            def safe_handle_response(data):
                try:
                    self_instance = self_ref()
                    if self_instance:
                        self_instance.handle_response(data)
                except Exception as e:
                    self_instance.log(f"处理响应时出错: {str(e)}", "red")

            def safe_handle_error(error):
                try:
                    self_instance = self_ref()
                    if self_instance:
                        self_instance.handle_error(error)
                except Exception as e:
                    self_instance.log(f"处理错误时出错: {str(e)}", "red")

            self.current_worker.finished.connect(safe_handle_response)
            self.current_worker.error.connect(safe_handle_error)

            # 执行请求
            response_data = await self.current_worker.fetch()
            if response_data:
                self.display_response(response_data)

        except asyncio.CancelledError:
            self.log("请求被取消", "red")
        except Exception as e:
            self.handle_error(str(e))
        finally:
            # 恢复按钮状态
            try:
                self.send_btn.setEnabled(True)
                self.send_btn.setText("发送")
                self.stop_btn.setEnabled(False)
            except Exception:
                pass
            self.current_worker = None

    def handle_response(self, response_data):
        """处理成功响应"""
        try:
            if response_data:
                self.display_response(response_data)
                self.log("请求成功完成", "blue")
        except Exception as e:
            self.log(f"处理响应时发生错误: {str(e)}", "red")

    def handle_error(self, error_msg):
        """处理请求错误"""
        try:
            self.log(f"请求失败: {error_msg}", "red")
            self.response_content.clear()
            self.response_content.append(f"请求错误: {error_msg}")
        except Exception:
            pass

    def display_response(self, response_data):
        """显示响应数据"""
        self.response_content.clear()
        response_text = response_data["content"]

        if self.json_decode_check.isChecked() and 'application/json' in response_data["headers"]["响应头"].get(
                'Content-Type', ''):
            try:
                json_data = json.loads(response_text)
                response_text = json.dumps(json_data, indent=4, ensure_ascii=False)
            except json.JSONDecodeError:
                pass

        self.response_content.append(response_text)

        self.response_headers.clear()
        headers = response_data["headers"]["响应头"]
        headers_text = "\n".join(f"{k}: {v}" for k, v in headers.items())
        self.response_headers.append(headers_text)

    def stop_request(self):
        """停止请求"""
        try:
            if self.current_worker:
                self.current_worker.stop()
                self.log("请求已停止", "blue")
                self.send_btn.setEnabled(True)
                self.send_btn.setText("发送")
                self.stop_btn.setEnabled(False)
                self.current_worker = None
        except Exception as e:
            self.log(f"停止请求时发生错误: {str(e)}", "red")

    def clear_log(self):
        """清空日志"""
        self.log_output.clear()

    def on_json_decode_check(self, state):
        """切换JSON自动解码状态"""
        self.config.upsert_config("RequestSettings_json_decode_enabled", "True" if state else "False")
        self.log(f"已{'启用' if state else '禁用'}JSON自动解码", "blue")

    def log(self, message, color="black"):
        """打印带时间戳的彩色日志"""
        from datetime import datetime
        current_time = datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")

        if color == "red":
            log_entry = f'<span style="color:#666">{current_time}</span><span style="color:#FF0000">{message}</span>'
        elif color == "blue":
            log_entry = f'<span style="color:#666">{current_time}</span><span style="color:#00BFFF">{message}</span>'
        else:
            log_entry = f'<span style="color:#666">{current_time}</span><span style="color:#000000">{message}</span>'

        self.log_output.append(log_entry)
        self.log_output.ensureCursorVisible()

    def create_param_dialog(self):
        """创建参数编辑对话框"""
        if not hasattr(self, 'param_dialog'):
            self.param_dialog = QDialog(self)
            self.param_dialog.setWindowTitle("设置请求参数")
            self.param_dialog.resize(800, 500)

            layout = QVBoxLayout()

            self.param_scroll = QScrollArea()
            self.param_scroll.setWidgetResizable(True)
            self.param_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)

            self.param_widget = QWidget()
            self.param_layout = QVBoxLayout(self.param_widget)
            self.param_layout.setSpacing(5)
            self.param_layout.setContentsMargins(5, 5, 5, 5)

            btn_layout = QHBoxLayout()
            add_btn = QPushButton("新增")
            add_btn.setIcon(QIcon("gui/img/fuzhi.png"))
            add_btn.clicked.connect(self.add_param_row)
            save_btn = QPushButton("确认")
            save_btn.setIcon(QIcon("gui/img/baochun.png"))
            save_btn.clicked.connect(self.save_params)
            btn_layout.addWidget(add_btn)
            btn_layout.addWidget(save_btn)

            self.param_scroll.setWidget(self.param_widget)
            layout.addWidget(self.param_scroll)
            layout.addLayout(btn_layout)
            self.param_dialog.setLayout(layout)

        self.load_existing_params()
        self.param_dialog.show()
        self.param_dialog.raise_()
        self.param_dialog.activateWindow()

    def load_existing_params(self):
        """加载现有参数到对话框"""
        while self.param_layout.count():
            item = self.param_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            params = json.loads(self.params_input.toPlainText())
            if isinstance(params, dict):
                for key, value in params.items():
                    self.add_param_row(key, str(value))
        except (json.JSONDecodeError, AttributeError):
            pass

        if self.param_layout.count() == 0:
            self.add_param_row()

    def add_param_row(self, key="", value=""):
        """添加参数行"""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(5)

        row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row.setFixedHeight(40)

        key_edit = QLineEdit()
        key_edit.setPlaceholderText("参数名")
        key_edit.setText(str(key) if key is not None else "")
        row_layout.addWidget(QLabel("name:"))
        row_layout.addWidget(key_edit)

        value_edit = QLineEdit()
        value_edit.setPlaceholderText("参数值")
        value_edit.setText(str(value) if value is not None else "")
        row_layout.addWidget(QLabel("value:"))
        row_layout.addWidget(value_edit)

        del_btn = QPushButton("删除")
        del_btn.setIcon(QIcon("gui/img/close.png"))
        del_btn.clicked.connect(lambda: self.remove_param_row(row))
        row_layout.addWidget(del_btn)

        self.param_layout.addWidget(row)

        if self.param_layout.count() > 5:
            self.param_scroll.ensureWidgetVisible(row)

    def remove_param_row(self, row):
        """删除参数行"""
        self.param_layout.removeWidget(row)
        row.deleteLater()

    def save_params(self):
        """保存参数到基础设置"""
        params = {}
        for i in range(self.param_layout.count()):
            row = self.param_layout.itemAt(i).widget()
            if row:
                children = row.findChildren(QLineEdit)
                if len(children) >= 2:
                    key, value = children[0].text(), children[1].text()
                    if key:
                        params[key] = value

        self.params_input.setPlainText(json.dumps(params, indent=4, ensure_ascii=False))
        self.param_dialog.close()
        self.log("参数保存成功", "blue")

    
    def save_config(self):
        """保存HTTP请求配置到数据库"""
        try:
            url = self.url_input.text().strip()
            params = self.params_input.toPlainText().strip()
            method = self.method_combo.currentText()
            
            from config.common_config import config_manager
            
            url_result = config_manager.upsert_config("http_request_url", url)
            params_result = config_manager.upsert_config("http_request_params", params)
            method_result = config_manager.upsert_config("http_request_method", method)
            
            try:
                parent = self.parent()
                if not parent:
                    parent = self.centralWidget().parent()
                
                while parent and not hasattr(parent, 'settings_widget'):
                    parent = parent.parent()
                
                if parent and hasattr(parent, 'settings_widget'):
                    settings = parent.settings_widget
                    
                    # 保存Headers配置
                    headers_mode = "default" if settings.default_headers_radio.isChecked() else "custom"
                    config_manager.upsert_config("RequestSettings_headers_mode", headers_mode)
                    config_manager.upsert_config("RequestSettings_content_type", settings.ct_combo.currentText())
                    config_manager.upsert_config("RequestSettings_ua_default", str(settings.ua_default_check.isChecked()))
                    config_manager.upsert_config("RequestSettings_user_agent", settings.ua_input.text())
                    config_manager.upsert_config("RequestSettings_custom_headers", settings.custom_headers_text.toPlainText())
                    
                    # 保存Cookie配置
                    cookie_mode = "custom" if settings.custom_cookie_radio.isChecked() else "none"
                    config_manager.upsert_config("RequestSettings_cookie_mode", cookie_mode)
                    config_manager.upsert_config("RequestSettings_cookies", settings.cookie_text.toPlainText())
                    
                    self.log("请求设置配置已同步保存", "blue")
                else:
                    self.log("未找到请求设置组件，仅保存基础配置", "orange")
            except Exception as e:
                self.log(f"保存请求设置配置时出错: {str(e)}", "orange")
            
            # 检查保存结果
            all_success = all([
                url_result.get("code") == 1,
                params_result.get("code") == 1,
                method_result.get("code") == 1
            ])
            
            if all_success:
                self.log("配置保存成功", "green")
                msg_box = QMessageBox()
                msg_box.setIcon(QMessageBox.Information)
                msg_box.setWindowIcon(QIcon('gui/img/favicon.ico') if 'gui/img/favicon.ico' else QIcon())
                msg_box.setText("配置保存成功")
                msg_box.setWindowTitle("提示")
                msg_box.exec_()
            else:
                self.log("部分配置保存失败", "red")
                msg_box = QMessageBox()
                msg_box.setIcon(QMessageBox.Warning)
                msg_box.setWindowIcon(QIcon('gui/img/favicon.ico') if 'gui/img/favicon.ico' else QIcon())
                msg_box.setText("部分配置保存失败，请检查日志")
                msg_box.setWindowTitle("警告")
                msg_box.exec_()
                
        except Exception as e:
            self.log(f"配置保存失败: {str(e)}", "red")
            msg_box = QMessageBox()
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowIcon(QIcon('gui/img/favicon.ico') if 'gui/img/favicon.ico' else QIcon())
            msg_box.setText(f"配置保存失败: {str(e)}")
            msg_box.setWindowTitle("错误")
            msg_box.exec_()