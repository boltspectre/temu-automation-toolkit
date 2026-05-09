import datetime
import json
import os
import re
import threading
import time

import requests
from PyQt5.QtCore import QSize, pyqtSignal, QObject, Qt, QTimer, QThread
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTabWidget, QTextEdit, QLabel, QCheckBox, QLineEdit,
                             QGroupBox, QPlainTextEdit, QComboBox, QMessageBox)
from loguru import logger

from config.common_config import config_manager
from config.py_config import config_value
from api.proxy_api import start_proxy_api, close_proxy_api


# 自定义信号类，用于线程间通信
class ThreadSignals(QObject):
    log_signal = pyqtSignal(str)  # 日志信号
    update_button_signal = pyqtSignal(bool)  # 更新按钮状态信号
    show_message_signal = pyqtSignal(str, str)  # 显示消息框信号


class StopProxyThread(QThread):
    """异步停止代理服务器线程，避免阻塞主线程"""
    stop_finished = pyqtSignal(bool, str)  # 停止完成信号：(是否成功, 提示信息)
    log_update = pyqtSignal(str)  # 日志更新信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

    def run(self):
        """异步执行停止逻辑"""
        try:
            self.log_update.emit("开始停止代理服务器...")

            # 1. 设置停止事件
            self.parent.stop_event.set()
            self.log_update.emit("停止信号已发送")

            # 2. 清空代理列表
            clean_proxies_url = f"{self.parent.api_proxy_url}/clean_proxies"
            try:
                clean_proxies_resp = requests.get(clean_proxies_url, timeout=5)
                clean_proxies_resp.raise_for_status()
                self.log_update.emit(f"{clean_proxies_resp.json().get('message')}")
            except requests.exceptions.RequestException as e:
                # 如果API服务器已经关闭，忽略错误
                self.log_update.emit(f"清空代理列表失败: {str(e)}")

            # 3. 关闭API服务器
            try:
                self.log_update.emit("正在关闭代理API服务器...")
                close_proxy_api()
                self.log_update.emit("代理API服务器已关闭")
            except Exception as e:
                self.log_update.emit(f"关闭代理API服务器失败: {str(e)}")

            # 4. 最终状态通知
            self.stop_finished.emit(True, "代理服务器停止成功")
            self.log_update.emit("所有代理服务器资源已清理完成")

        except Exception as e:
            self.log_update.emit(f"<font color='red'>停止逻辑异常</font>: {str(e)}")
            self.stop_finished.emit(False, f"停止失败: {str(e)}")


class ProxyPage(QWidget):
    def __init__(self):
        super().__init__()
        self.PROXY_FILE_PATH = config_value.proxy_file_path

        self.PROXYAPI_FILE_PATH = config_value.api_proxy_file_path
        self.proxy_service_running = False  # 代理服务状态
        self.worker_thread = None  # 工作线程
        self.stop_thread = None  # 停止线程
        self.stop_event = threading.Event()  # 用于停止线程的事件

        self.api_proxy_url = config_value.api_proxy_url

        # 使用数据库配置管理器替代配置加载器
        self.config = None

        # 创建信号实例
        self.signals = ThreadSignals()
        # 连接信号与槽
        self.signals.log_signal.connect(self._appendLog)
        self.signals.update_button_signal.connect(self._updateButtonState)
        self.signals.show_message_signal.connect(self._showMessageBox)

        self.initUI()

    def initUI(self):
        main_layout = QVBoxLayout(self)

        # 主分组框
        proxy_group = QGroupBox("代理IP管理")
        group_layout = QVBoxLayout(proxy_group)

        # 选项卡组件
        self.proxy_tabs = QTabWidget()

        # 创建四个选项卡
        self.log_tab = self._createLogTab()
        self.normal_tab = self._createNormalTab()
        self.api_tab = self._createApiTab()
        self.format_tab = self._createFormatTab()
        self.desc_tab = self._createDescTab()

        self.proxy_tabs.addTab(self.log_tab, "日志")
        self.proxy_tabs.addTab(self.normal_tab, "普通模式")
        self.proxy_tabs.addTab(self.api_tab, "接口模式")
        self.proxy_tabs.addTab(self.format_tab, "格式转换")
        self.proxy_tabs.addTab(self.desc_tab, "说明")

        group_layout.addWidget(self.proxy_tabs)
        main_layout.addWidget(proxy_group)

        # 底部控制栏
        control_group = QGroupBox()
        control_layout = QHBoxLayout(control_group)

        self.proxy_btn = QPushButton("启动", self)
        self.proxy_btn.setIcon(QIcon("gui/img/qidong.png"))
        self.proxy_btn.setCheckable(True)
        self.proxy_btn.setIconSize(QSize(32, 32))
        # self.proxy_btn.setStyleSheet("QPushButton { padding: 8px 20px; font-size: 22px; }")
        self.proxy_btn.setStyleSheet("QPushButton { font-size: 25px; }")  # 恢复样式

        self.test_check = QCheckBox("测试")
        self.timeout_edit = QLineEdit()
        self.timeout_edit.setPlaceholderText("单位/秒")
        self.timeout_edit.setFixedWidth(120)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("测试URL (例：http://www.baidu.com)")
        self.thread_count_edit = QLineEdit()
        self.thread_count_edit.setPlaceholderText("测试线程数")
        self.thread_count_edit.setFixedWidth(100)
        # 设置默认测试URL
        # self.url_edit.setText("http://www.baidu.com")

        control_layout.addWidget(self.proxy_btn)
        control_layout.addWidget(self.test_check)
        control_layout.addWidget(QLabel("超时时间:"))
        control_layout.addWidget(self.timeout_edit)
        control_layout.addWidget(QLabel("测试URL:"))
        control_layout.addWidget(self.url_edit)
        control_layout.addWidget(QLabel("线程数:"))
        control_layout.addWidget(self.thread_count_edit)

        main_layout.addWidget(control_group)

        # 信号连接
        self.proxy_btn.clicked.connect(self._toggleProxyService)

        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        # 绑定信号与槽
        self.test_check.stateChanged.connect(self.on_test_check_action)
        self.timeout_edit.textChanged.connect(self.on_timeout_edit_action)
        self.url_edit.textChanged.connect(self.on_url_edit_action)
        self.thread_count_edit.textChanged.connect(self.on_thread_count_edit_action)
        self.update_time.textChanged.connect(self.on_update_time_action)
        self.api_update_time.textChanged.connect(self.on_api_update_time_action)
        self.api_mode_combo.currentIndexChanged.connect(self.on_api_mode_combo_action)

    def load_settings(self):
        """加载配置到界面"""
        try:
            # 使用数据库配置管理器加载配置
            self.url_edit.setText(config_manager.get_or_set_config("ProxyPage_url_edit", "https://www.baidu.com"))
            self.timeout_edit.setText(config_manager.get_or_set_config("ProxyPage_timeout_edit", "10"))
            self.thread_count_edit.setText(config_manager.get_or_set_config("ProxyPage_thread_count_edit", "5"))
            test_check_value = config_manager.get_or_set_config("ProxyPage_test_check", "False")
            self.test_check.setChecked(test_check_value.lower() == "true")
            self.update_time.setText(config_manager.get_or_set_config("ProxyPage_update_time", "1800"))
            self.api_update_time.setText(config_manager.get_or_set_config("ProxyPage_api_update_time", "1800"))

            saved_mode_text = config_manager.get_or_set_config("ProxyPage_api_mode", "轮询模式")  # 默认值与下拉框第一个选项一致
            mode_idx = self.api_mode_combo.findText(saved_mode_text)  # 查找文本对应的索引
            if mode_idx != 1:  # 若未找到匹配文本（如配置值异常），设为默认索引0
                mode_idx = 0
            self.api_mode_combo.setCurrentIndex(mode_idx)

        except Exception as e:
            logger.error(f"加载配置错误：{e}")

    def _createLogTab(self):
        """日志选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.proxy_log = QTextEdit()
        self.proxy_log.setReadOnly(True)
        self.proxy_log.setStyleSheet("""
               QTextEdit {
                   border: 1px solid #ddd;
                   color: #00BFFF;
                   background-color: #F5F5F5;
               }
           """)
        self.proxy_log.setPlaceholderText("代理ip日志将显示在这里")
        layout.addWidget(self.proxy_log)
        return tab

    def _createNormalTab(self):
        """普通模式选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # IP输入区
        ip_group = QGroupBox("代理IP列表")
        ip_layout = QVBoxLayout(ip_group)

        self.normal_edit = QPlainTextEdit()
        self.normal_edit.setPlaceholderText("每行输入一条代理IP")

        # 加载代理IP
        ip_list = self.loadProxyIPs()
        self.normal_edit.setPlainText("\n".join(ip_list))

        # 更新时间和保存按钮布局（放在同一行）
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("更新时间："))
        self.update_time = QLineEdit()
        self.update_time.setPlaceholderText("单位：秒")
        control_layout.addWidget(self.update_time)

        # 保存按钮
        btn_save = QPushButton("保存")
        btn_save.setIcon(QIcon("gui/img/baochun.png"))
        btn_save.clicked.connect(self.saveProxySettings)
        control_layout.addWidget(btn_save)

        ip_layout.addWidget(self.normal_edit)
        ip_layout.addLayout(control_layout)

        layout.addWidget(ip_group)
        return tab

    def saveProxySettings(self):
        """保存代理IP设置（带格式校验和自动转换）"""
        try:
            # 获取输入的每行内容
            raw_text = self.normal_edit.toPlainText()
            ips = [line.strip() for line in raw_text.split('\n') if line.strip()]

            # 校验IP格式并格式化，支持自动转换自定义格式
            valid_ips = []
            # 标准代理格式正则
            ip_regex = re.compile(
                r'^(http|https|socks5)://'  # 协议
                r'(?:([^:]+):([^@]+)@)?'  # 可选的账号密码
                r'((?:\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F:]+)'  # IPv4或IPv6
                r':(\d+)$'  # 端口
            )
            # 自定义格式正则（ip/端口/账号/密码，可能带有额外的地区信息）
            custom_regex = re.compile(
                r'^((?:\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F:]+)'  # IP
                r'/(\d+)'  # 端口
                r'/([^/]+)'  # 账号
                r'/([^/]+)'  # 密码
                r'(?:/.*)?$'  # 可能的额外信息（如//地区信息）
            )

            for ip in ips:
                # 先检查是否为标准格式
                if ip_regex.match(ip):
                    valid_ips.append(ip)
                # 再检查是否为自定义格式（ip/端口/账号/密码）
                elif custom_regex.match(ip):
                    # 提取各部分并转换为socks5标准格式
                    match = custom_regex.match(ip)
                    groups = match.groups()
                    # 只使用前四个分组：IP、端口、账号、密码
                    ip_addr, port, username, password = groups[:4]
                    converted = f"socks5://{username}:{password}@{ip_addr}:{port}"
                    valid_ips.append(converted)
                    self._appendLog(f"自动转换自定义格式: {ip} -> {converted}")
                else:
                    logger.warning(f"格式错误的IP: {ip}")

            # 确保目录存在
            os.makedirs(os.path.dirname(self.PROXY_FILE_PATH), exist_ok=True)

            # 写入文件
            with open(self.PROXY_FILE_PATH, 'w', encoding='utf-8') as f:
                for ip in valid_ips:
                    f.write(f"{ip}\n")

            # 显示成功提示
            QMessageBox.information(
                self,
                "保存成功",
                f"保存 {len(valid_ips)} 个有效代理IP, 失败 {len(ips) - len(valid_ips)} 个代理IP",
                QMessageBox.Ok
            )
            self._appendLog(f"保存 {len(valid_ips)} 个有效代理IP, 失败 {len(ips) - len(valid_ips)} 个代理IP")

        except Exception as e:
            logger.error(f"保存代理IP失败: {e}")
            QMessageBox.critical(
                self,
                "保存失败",
                f"保存代理IP时出错: {str(e)}",
                QMessageBox.Ok
            )
        finally:
            ip_list = self.loadProxyIPs()
            self.normal_edit.setPlainText("\n".join(ip_list))

    def loadProxyIPs(self):
        """从文件加载代理IP列表"""
        ip_list = []
        if not self.PROXY_FILE_PATH or not os.path.exists(self.PROXY_FILE_PATH):
            return ip_list

        try:
            with open(self.PROXY_FILE_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    ip = line.strip()
                    if ip:
                        ip_list.append(ip)
        except Exception as e:
            logger.error(f"读取代理IP文件时出错: {e}")
            QMessageBox.warning(
                self,
                "读取失败",
                f"读取代理IP文件时出错: {str(e)}",
                QMessageBox.Ok
            )

        return ip_list

    def _createApiTab(self):
        """接口模式选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # IP输入区
        api_group = QGroupBox("API配置")
        api_layout = QVBoxLayout(api_group)

        self.api_edit = QPlainTextEdit()
        self.api_edit.setPlaceholderText("输入API接口地址，每行一个\n示例：http://api.provider.com/get?type=http")

        api_list = self.loadProxyAPIs()  # 调用已有的读取API文件方法
        self.api_edit.setPlainText("\n".join(api_list))  # 将读取的API列表设置为文本内容

        # 模式选择
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("获取模式："))
        self.api_mode_combo = QComboBox()
        self.api_mode_combo.addItems(["轮询模式", "随机模式", "智能切换"])

        mode_layout.addWidget(self.api_mode_combo)

        # 更新时间
        update_layout = QHBoxLayout()
        update_layout.addWidget(QLabel("更新时间："))
        self.api_update_time = QLineEdit()
        self.api_update_time.setPlaceholderText("单位：秒")
        update_layout.addWidget(self.api_update_time)

        # 添加保存按钮
        btn_api_save = QPushButton("保存")
        btn_api_save.setIcon(QIcon("gui/img/baochun.png"))
        btn_api_save.clicked.connect(self.saveApiSettings)
        update_layout.addWidget(btn_api_save)

        api_layout.addWidget(self.api_edit)
        api_layout.addLayout(mode_layout)
        api_layout.addLayout(update_layout)

        layout.addWidget(api_group)
        return tab

    def saveApiSettings(self):
        """保存代理IP设置（带格式校验和自动转换）"""
        try:
            # 获取输入的每行内容
            raw_text = self.api_edit.toPlainText()
            urls = [line.strip() for line in raw_text.split('\n') if line.strip()]

            # 确保目录存在
            os.makedirs(os.path.dirname(self.PROXYAPI_FILE_PATH), exist_ok=True)

            # 写入文件
            with open(self.PROXYAPI_FILE_PATH, 'w', encoding='utf-8') as f:
                for url in urls:
                    f.write(f"{url}\n")

            # 显示成功提示
            QMessageBox.information(
                self,
                "保存成功",
                f"保存 {len(urls)} 个代理API",
                QMessageBox.Ok
            )
            self._appendLog(f"保存 {len(urls)} 个代理API")

        except Exception as e:
            logger.error(f"保存代理API失败: {e}")
            QMessageBox.critical(
                self,
                "保存失败",
                f"保存代理API时出错: {str(e)}",
                QMessageBox.Ok
            )
        finally:
            api_list = self.loadProxyAPIs()
            self.api_edit.setPlainText("\n".join(api_list))

    def loadProxyAPIs(self):
        """从文件加载代理IP列表"""
        api_list = []
        if not self.PROXYAPI_FILE_PATH or not os.path.exists(self.PROXYAPI_FILE_PATH):
            return api_list

        try:
            with open(self.PROXYAPI_FILE_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    url = line.strip()
                    if url:
                        api_list.append(url)
        except Exception as e:
            logger.error(f"读取代理IP文件时出错: {e}")
            QMessageBox.warning(
                self,
                "读取失败",
                f"读取代理IP文件时出错: {str(e)}",
                QMessageBox.Ok
            )

        return api_list

    def _createFormatTab(self):
        """格式转换选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # 主布局：左右两部分
        main_split = QHBoxLayout()

        # 左半部分：ip/端口/账号/密码格式
        left_group = QGroupBox("IP/端口/账号/密码格式")
        left_layout = QVBoxLayout(left_group)

        left_label = QLabel("每行一条，格式：IP/端口/账号/密码")
        left_label.setStyleSheet("color: #666; font-size: 12px;")
        left_layout.addWidget(left_label)

        self.format_left_edit = QPlainTextEdit()
        self.format_left_edit.setPlaceholderText("例如：\n121.11.99.213/11835/Qingsip03/476088\n192.168.1.1/8080/user/pass")
        left_layout.addWidget(self.format_left_edit)

        # 左侧按钮布局
        left_btn_layout = QHBoxLayout()
        
        left_copy_btn = QPushButton("复制全部")
        left_copy_btn.setIcon(QIcon("gui/img/fuzhi.png"))
        left_copy_btn.clicked.connect(lambda: self._copyToClipboard(self.format_left_edit))
        left_btn_layout.addWidget(left_copy_btn)

        left_convert_btn = QPushButton("向右转换 →")
        left_convert_btn.setIcon(QIcon("gui/img/zhuanhuan.png"))
        left_convert_btn.clicked.connect(self._convertLeftToRight)
        left_btn_layout.addWidget(left_convert_btn)

        left_layout.addLayout(left_btn_layout)

        # 右半部分：socks5://账号:密码@ip:端口格式
        right_group = QGroupBox("SOCKS5标准格式")
        right_layout = QVBoxLayout(right_group)

        right_label = QLabel("每行一条，格式：socks5://账号:密码@ip:端口")
        right_label.setStyleSheet("color: #666; font-size: 12px;")
        right_layout.addWidget(right_label)

        self.format_right_edit = QPlainTextEdit()
        self.format_right_edit.setPlaceholderText("例如：\nsocks5://Qingsip03:476088@121.11.99.213:11835\nsocks5://user:pass@192.168.1.1:8080")
        right_layout.addWidget(self.format_right_edit)

        # 右侧按钮布局
        right_btn_layout = QHBoxLayout()

        right_convert_btn = QPushButton("← 向左转换")
        right_convert_btn.setIcon(QIcon("gui/img/zhuanhuan.png"))
        right_convert_btn.clicked.connect(self._convertRightToLeft)
        right_btn_layout.addWidget(right_convert_btn)

        right_copy_btn = QPushButton("复制全部")
        right_copy_btn.setIcon(QIcon("gui/img/fuzhi.png"))
        right_copy_btn.clicked.connect(lambda: self._copyToClipboard(self.format_right_edit))
        right_btn_layout.addWidget(right_copy_btn)

        right_layout.addLayout(right_btn_layout)

        # 添加到主布局
        main_split.addWidget(left_group)
        main_split.addWidget(right_group)

        layout.addLayout(main_split)

        # 提示标签（用于显示转换结果）
        self.format_tip_label = QLabel()
        self.format_tip_label.setAlignment(Qt.AlignCenter)
        self.format_tip_label.setStyleSheet("color: #28a745; font-size: 24px; font-weight: bold;")
        layout.addWidget(self.format_tip_label)

        return tab

    def _convertLeftToRight(self):
        """从左向右转换：IP/端口/账号/密码 -> socks5://账号:密码@ip:端口"""
        try:
            raw_text = self.format_left_edit.toPlainText()
            lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
            
            converted_lines = []
            removed_count = 0

            for line in lines:
                parts = line.split('/')
                if len(parts) >= 4:
                    ip_addr = parts[0]
                    port = parts[1]
                    username = parts[2]
                    password = parts[3]
                    
                    # 直接使用完整的密码
                    if password:
                        converted = f"socks5://{username}:{password}@{ip_addr}:{port}"
                        converted_lines.append(converted)
                    else:
                        removed_count += 1
                else:
                    removed_count += 1

            # 设置转换结果
            self.format_right_edit.setPlainText("\n".join(converted_lines))

            # 显示提示
            if removed_count > 0:
                self._showFormatTip(f"转换完成，已清理 {removed_count} 条无效格式")
            else:
                self._showFormatTip("转换完成")

        except Exception as e:
            logger.error(f"格式转换失败: {e}")
            self._showFormatTip(f"转换失败: {str(e)}")

    def _convertRightToLeft(self):
        """从右向左转换：socks5://账号:密码@ip:端口 -> IP/端口/账号/密码"""
        try:
            raw_text = self.format_right_edit.toPlainText()
            lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
            
            # 标准代理格式正则
            ip_regex = re.compile(
                r'^(http|https|socks5)://'  # 协议
                r'(?:([^:]+):([^@]+)@)?'  # 可选的账号密码
                r'((?:\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F:]+)'  # IPv4或IPv6
                r':(\d+)$'  # 端口
            )

            converted_lines = []
            removed_count = 0

            for line in lines:
                match = ip_regex.match(line)
                if match:
                    protocol, username, password, ip_addr, port = match.groups()
                    if username and password:
                        converted = f"{ip_addr}/{port}/{username}/{password}"
                    else:
                        converted = f"{ip_addr}/{port}/"
                    converted_lines.append(converted)
                else:
                    removed_count += 1

            # 设置转换结果
            self.format_left_edit.setPlainText("\n".join(converted_lines))

            # 显示提示
            if removed_count > 0:
                self._showFormatTip(f"转换完成，已清理 {removed_count} 条无效格式")
            else:
                self._showFormatTip("转换完成")

        except Exception as e:
            logger.error(f"格式转换失败: {e}")
            self._showFormatTip(f"转换失败: {str(e)}")

    def _copyToClipboard(self, text_edit):
        """复制文本框内容到剪贴板"""
        try:
            text = text_edit.toPlainText()
            if text:
                from PyQt5.QtWidgets import QApplication
                QApplication.clipboard().setText(text)
                self._showFormatTip("已复制到剪贴板")
            else:
                self._showFormatTip("没有内容可复制")
        except Exception as e:
            logger.error(f"复制失败: {e}")
            self._showFormatTip(f"复制失败: {str(e)}")

    def _showFormatTip(self, message):
        """显示格式转换提示（5秒后自动消失）"""
        self.format_tip_label.setText(message)
        
        # 创建定时器，5秒后清空提示
        QTimer.singleShot(5000, lambda: self.format_tip_label.setText(""))

    def _createDescTab(self):
        """说明选项卡"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        desc_text = QTextEdit()
        desc_text.setReadOnly(True)
        desc_text.setHtml("""
           <p><b>普通模式：</b></p>
           <ul>
               <li><b>账号密码模式：</b> socks5://账号:密码@ip:端口</li>
               <li><b>无验证模式：</b> socks5://ip:端口</li>
               <li>支持所有代理协议：http/https/socks5</li>
               <li>万能通用格式：协议+(账号密码)+ip/域名+端口</li>
               <li>无论什么代理格式，只要符合上述规则都可以使用</li>
           </ul>
           <p><b>接口模式：</b></p>
           <ul>
               <li>支持动态获取代理IP的API接口</li>
               <li>支持HTTP/HTTPS协议</li>
               <li><b>文本格式：</b> 每行一个IP:端口</li>
               <li><b>JSON格式示例：</b>
                   <pre>{"data": [
           {"ip": "socks5://admin:123456@192.168.0.1", "port": 1234},
           {"ip": "http://user:pass@10.0.0.1", "port": 8080} ]
                   }</pre>
               </li>
               <li>接口模式需要自行构造正确格式，几行代码就可以搞定</li>
           </ul>
           <p><b>测试设置：</b></p>
           <ul>
               <li>测试功能会检测代理是否可用</li>
               <li>测试超时时间(秒)：时间越长筛选的代理质量可能越差</li>
               <li>测试URL示例：https://www.baidu.com/</li>
               <li>对代理IP有信心可不开启测试</li>
           </ul>
           """)

        layout.addWidget(desc_text)
        return tab

    def _appendLog(self, message):
        """添加日志记录"""
        timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
        self.proxy_log.append(f'<span style="color:#666">{timestamp}</span>{message}')

    def _toggleProxyService(self):
        """切换代理服务状态"""
        if self.proxy_btn.isChecked():
            # 启动服务
            self.stop_event.clear()
            
            # 立即更新按钮状态，不等待
            self._updateButtonState(True)
            
            # 在后台线程中启动API服务器和代理服务
            self.worker_thread = threading.Thread(target=self._startProxyServiceThread, daemon=True)
            self.worker_thread.start()
        else:
            # 停止服务（异步化修改）
            self._appendLog("开始异步停止代理服务器...")

            # 创建并启动停止线程
            self.stop_thread = StopProxyThread(self)
            self.stop_thread.stop_finished.connect(self.on_stop_finished)
            self.stop_thread.log_update.connect(self._appendLog)
            self.stop_thread.start()

    def on_stop_finished(self, success, msg):
        """停止完成回调（主线程执行）"""
        self._resetButtonState()

        # 提示结果
        if success:
            QMessageBox.information(self, "成功", msg)
        else:
            QMessageBox.warning(self, "警告", msg)

    def _updateButtonState(self, is_running):
        """更新按钮状态"""
        if is_running:
            self.proxy_btn.setText("停止")
            self.proxy_btn.setIcon(QIcon("gui/img/tingzhi.png"))
            self.proxy_service_running = True
            # 立即清除焦点，使焦点转移到其他控件
            self.proxy_btn.clearFocus()
            # 重置按钮样式，移除选中状态
            self.proxy_btn.setStyleSheet("QPushButton { font-size: 25px; }")
        else:
            self._resetButtonState()

    def _resetButtonState(self):
        """重置按钮状态"""
        self.proxy_btn.setText("启动")
        self.proxy_btn.setIcon(QIcon("gui/img/qidong.png"))
        self.proxy_btn.setChecked(False)
        self.proxy_service_running = False
        # 清除焦点，使焦点转移到其他控件
        self.proxy_btn.clearFocus()
        # 重置按钮样式，移除选中状态
        self.proxy_btn.setStyleSheet("QPushButton { font-size: 25px; }")

    def _showMessageBox(self, title, message):
        """显示消息框（通过信号调用，确保在主线程）"""
        QMessageBox.warning(self, title, message, QMessageBox.Ok)

    def _startProxyServiceThread(self):
        """在单独线程中执行的代理服务启动逻辑（优化轮询测试）"""
        try:
            # 先启动API服务器（在后台线程中）
            self.signals.log_signal.emit("正在启动代理API服务器...")
            if not start_proxy_api():
                self.signals.log_signal.emit("启动代理API服务器失败")
                self.signals.update_button_signal.emit(False)
                return
            
            self.signals.log_signal.emit("代理API服务器启动中...")
            
            # 等待并验证API服务器是否可用
            max_wait = 10  # 最多等待10秒
            wait_interval = 0.5  # 每0.5秒检查一次
            api_ready = False
            
            for i in range(int(max_wait / wait_interval)):
                time.sleep(wait_interval)
                try:
                    # 尝试连接API服务器
                    test_resp = requests.get(f"{self.api_proxy_url}/", timeout=2)
                    if test_resp.status_code == 200:
                        api_ready = True
                        break
                except:
                    continue
            
            if api_ready:
                self.signals.log_signal.emit("代理API服务器启动成功")
                self.signals.log_signal.emit(f"API地址: {self.api_proxy_url}")
            else:
                self.signals.log_signal.emit("代理API服务器启动超时，请检查端口是否被占用")
                self.signals.update_button_signal.emit(False)
                return
            
            ip_list = self.loadProxyIPs()
            if not ip_list:
                self.signals.log_signal.emit("代理列表为空，无法启动服务")
                self.signals.update_button_signal.emit(False)
                return

            # 发送代理列表到API
            send_proxies_url = f"{self.api_proxy_url}/send_proxies"
            payload = {"proxies": ip_list}
            try:
                send_proxies_resp = requests.post(
                    send_proxies_url,
                    data=json.dumps(payload),
                    headers={"Content-Type": "application/json"},  # 显式指定JSON格式
                    timeout=10
                )
                send_proxies_resp.raise_for_status()  # 检查HTTP错误状态码
                self.signals.log_signal.emit(f"加载代理列表成功，共 {len(ip_list)} 个代理")
            except requests.exceptions.RequestException as e:
                self.signals.log_signal.emit(f"加载代理列表失败: {str(e)}")
                self.signals.update_button_signal.emit(False)
                return

            # 获取所有代理
            all_proxies_url = f"{self.api_proxy_url}/get_all_proxies"
            try:
                all_proxies_resp = requests.get(all_proxies_url, timeout=10)
                all_proxies_resp.raise_for_status()
                all_proxies_list = all_proxies_resp.json().get("proxies", [])
                self.signals.log_signal.emit(f"获取代理列表成功，共 {len(all_proxies_list)} 个代理")
            except requests.exceptions.RequestException as e:
                self.signals.log_signal.emit(f"获取代理列表失败: {str(e)}")
                self.signals.update_button_signal.emit(False)
                return

            test_enabled = self.test_check.isChecked()
            if not test_enabled:
                # 不启用测试，直接使用所有代理（无轮询）
                self.signals.log_signal.emit("未启用测试，使用所有代理")
                while not self.stop_event.is_set():
                    if self.stop_event.wait(1):
                        break
                return

            # 启用测试：轮询逻辑
            self.signals.log_signal.emit("已启用测试，将按更新时间轮询")
            while not self.stop_event.is_set():
                # 每次轮询前读取最新配置（支持动态修改）
                try:
                    # 读取最新测试URL
                    test_url = self.url_edit.text().strip()
                    if not test_url:
                        self.signals.show_message_signal.emit("警告", "测试URL为空，跳过本轮测试")
                        cycle_time = int(self.update_time.text().strip() or 1800)
                        self.stop_event.wait(cycle_time)
                        continue

                    # 读取最新超时时间（默认10秒）
                    timeout = int(self.timeout_edit.text().strip() or 10)
                    # 读取最新更新周期（默认1800秒，30分钟）
                    cycle_time = int(self.update_time.text().strip() or 1800)
                    if cycle_time <= 0:
                        raise ValueError("更新时间必须为正数")

                except ValueError as e:
                    self.signals.show_message_signal.emit("配置错误", f"{str(e)}，使用默认值")
                    timeout = 10
                    cycle_time = 1800

                # 执行本轮代理测试
                self.signals.log_signal.emit(
                    f"启动代理ip检测，超时: {timeout}秒，下轮间隔: {cycle_time}秒"
                )
                
                # 检查是否需要停止
                if self.stop_event.is_set():
                    break
                
                test_proxy_url = f"{self.api_proxy_url}/test_proxy"
                
                # 获取线程数配置
                try:
                    thread_count = int(self.thread_count_edit.text().strip()) if self.thread_count_edit.text().strip() else 5
                except ValueError:
                    thread_count = 5
                
                payload = {
                    "proxies": all_proxies_list,
                    "test_url": test_url,
                    "thread_count": thread_count
                }
                
                # 设置合理的总超时时间：每个代理超时时间 * 代理数量 + 额外缓冲时间
                total_timeout = timeout * len(all_proxies_list) + 30  # 额外30秒缓冲
                
                self.signals.log_signal.emit(f"正在发送测试请求到API服务器...")
                try:
                    test_resp = requests.post(
                        test_proxy_url,
                        data=json.dumps(payload),
                        headers={"Content-Type": "application/json"},
                        timeout=total_timeout
                    )
                    
                    # 如果因为停止事件而退出，跳过结果处理
                    if self.stop_event.is_set():
                        break
                    
                    test_resp.raise_for_status()
                    result = test_resp.json()
                    
                    self.signals.log_signal.emit(
                        f"本轮测试完成 - 总代理: {result.get('total')}, 有效: {result.get('valid')}, {result.get('valid_proxies')} "
                        f"下次测试时间: {datetime.datetime.now() + datetime.timedelta(seconds=cycle_time):%H:%M:%S}"
                    )
                except requests.exceptions.Timeout:
                    if not self.stop_event.is_set():
                        self.signals.log_signal.emit(f"本轮测试超时（超过 {total_timeout} 秒）")
                except requests.exceptions.RequestException as e:
                    if not self.stop_event.is_set():
                        self.signals.log_signal.emit(f"本轮测试失败: {str(e)}")

                # 等待下一轮测试（可被停止信号中断）
                if self.stop_event.wait(cycle_time):
                    break  # 收到停止信号，退出轮询

        except Exception as e:
            logger.error(f"代理服务线程出错: {e}")
            self.signals.log_signal.emit(f"服务出错: {str(e)}")
        finally:
            self.signals.update_button_signal.emit(False)

    def on_test_check_action(self):
        """测试功能开关"""
        config_manager.upsert_config("ProxyPage_test_check", "True" if self.test_check.isChecked() else "False")

    def on_url_edit_action(self):
        """测试URL输入框内容变化"""
        config_manager.upsert_config("ProxyPage_url_edit", self.url_edit.text())

    def on_timeout_edit_action(self):
        """超时输入框内容变化"""
        config_manager.upsert_config("ProxyPage_timeout_edit", self.timeout_edit.text())

    def on_thread_count_edit_action(self):
        """线程数输入框内容变化"""
        config_manager.upsert_config("ProxyPage_thread_count_edit", self.thread_count_edit.text())

    def on_update_time_action(self):
        """超时输入框内容变化"""
        config_manager.upsert_config("ProxyPage_update_time", self.update_time.text())

    def on_api_update_time_action(self):
        config_manager.upsert_config("ProxyPage_api_update_time", self.api_update_time.text())

    def on_api_mode_combo_action(self):
        config_manager.upsert_config("ProxyPage_api_mode", self.api_mode_combo.currentText())

    def is_proxy_running(self):
        """获取当前代理服务状态（是否启动）"""
        return self.proxy_service_running

    def closeEvent(self, event):
        """窗口关闭时确保线程停止"""
        self.stop_event.set()
        # 不等待线程结束，直接接受关闭事件
        # 线程会在后台自动停止（因为设置了daemon=True）
        event.accept()