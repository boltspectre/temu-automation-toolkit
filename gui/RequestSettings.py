import json

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QFormLayout, QLabel, QComboBox,
                             QLineEdit, QCheckBox, QHBoxLayout, QRadioButton, QTextEdit,
                             QPushButton, QMessageBox)  # 新增导入QPushButton、QMessageBox

from config.common_config import config_manager


class RequestsSettings(QWidget):
    """仅负责Headers和Cookie配置的独立组件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        # 默认配置常量
        self.DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        self.DEFAULT_HEADERS = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive"
        }
        self.config = config_manager

        # 初始化UI
        self.init_ui()
        # 加载保存的配置
        self.load_config()
        # 绑定信号
        self.bind_signals()

    def init_ui(self):
        """初始化Headers/Cookie配置UI"""
        layout = QVBoxLayout(self)

        # ========== 1. Headers配置 ==========
        headers_group = QGroupBox("请求头配置")
        headers_layout = QVBoxLayout()

        # Headers模式选择
        mode_row = QWidget()
        mode_layout = QHBoxLayout(mode_row)
        mode_layout.setContentsMargins(0, 0, 0, 10)
        self.default_headers_radio = QRadioButton("使用默认Headers（可自定义Content-Type/User-Agent）")
        self.custom_headers_radio = QRadioButton("完全自定义Headers")
        self.default_headers_radio.setChecked(True)
        mode_layout.addWidget(self.default_headers_radio)
        mode_layout.addWidget(self.custom_headers_radio)
        headers_layout.addWidget(mode_row)

        # 默认Headers配置项
        default_headers_widget = QWidget()
        default_headers_layout = QFormLayout(default_headers_widget)
        default_headers_layout.setLabelAlignment(Qt.AlignRight)

        # Content-Type
        ct_row = QWidget()
        ct_layout = QHBoxLayout(ct_row)
        self.ct_combo = QComboBox()
        self.ct_combo.addItems([
            "application/x-www-form-urlencoded",
            "application/json",
            "multipart/form-data",
            "text/plain",
            "text/html",
            "application/xml"
        ])
        self.ct_combo.setCurrentText("application/x-www-form-urlencoded")
        ct_layout.addWidget(QLabel("Content-Type:"))
        ct_layout.addWidget(self.ct_combo)
        default_headers_layout.addRow(ct_row)

        # User-Agent
        ua_row = QWidget()
        ua_layout = QHBoxLayout(ua_row)
        self.ua_default_check = QCheckBox("使用默认")
        self.ua_default_check.setChecked(True)
        self.ua_input = QLineEdit()
        self.ua_input.setPlaceholderText("自定义User-Agent（勾选默认则忽略此值）")
        self.ua_input.setText(self.DEFAULT_USER_AGENT)
        self.ua_input.setEnabled(False)
        ua_layout.addWidget(QLabel("User-Agent:"))
        ua_layout.addWidget(self.ua_default_check)
        ua_layout.addWidget(self.ua_input)
        default_headers_layout.addRow(ua_row)

        headers_layout.addWidget(default_headers_widget)

        # 自定义Headers输入
        self.custom_headers_text = QTextEdit()
        self.custom_headers_text.setPlaceholderText("请输入JSON格式的Headers")
        self.custom_headers_text.setMaximumHeight(120)
        self.custom_headers_text.setEnabled(False)
        headers_layout.addWidget(QLabel("自定义Headers内容："))
        headers_layout.addWidget(self.custom_headers_text)

        headers_group.setLayout(headers_layout)

        # ========== 2. Cookie配置（简化版） ==========
        cookie_group = QGroupBox("Cookie配置")
        cookie_layout = QVBoxLayout()

        # Cookie模式选择（仅保留不使用/自定义）
        cookie_mode_row = QWidget()
        cookie_mode_layout = QHBoxLayout(cookie_mode_row)
        cookie_mode_layout.setContentsMargins(0, 0, 0, 10)
        self.no_cookie_radio = QRadioButton("不使用Cookie")
        self.custom_cookie_radio = QRadioButton("自定义Cookie")
        self.no_cookie_radio.setChecked(True)
        cookie_mode_layout.addWidget(self.no_cookie_radio)
        cookie_mode_layout.addWidget(self.custom_cookie_radio)
        cookie_layout.addWidget(cookie_mode_row)

        # Cookie内容输入
        self.cookie_text = QTextEdit()
        self.cookie_text.setPlaceholderText(
            "请输入JSON格式的Cookie，例如：{\"session_id\": \"123456\",\"token\": \"abcdef\"}")
        self.cookie_text.setMaximumHeight(100)
        self.cookie_text.setEnabled(False)
        cookie_layout.addWidget(QLabel("Cookie内容："))
        cookie_layout.addWidget(self.cookie_text)

        cookie_group.setLayout(cookie_layout)

        # ========== 新增：保存按钮（下方中间位置） ==========
        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 10, 0, 10)  # 上下间距10px
        button_layout.addStretch()  # 左侧伸缩项（居中关键）

        self.save_btn = QPushButton("保存配置")
        self.save_btn.setIcon(QIcon('gui/img/baochun.png') if 'gui/img/baochun.png' else QIcon())  # 可选图标
        # self.save_btn.setFixedSize(120, 35)  # 固定按钮大小
        self.save_btn.clicked.connect(self.on_save_click)  # 绑定点击事件

        button_layout.addWidget(self.save_btn)
        button_layout.addStretch()  # 右侧伸缩项（居中关键）

        # ========== 组装布局 ==========
        layout.addWidget(headers_group)
        layout.addWidget(cookie_group)
        layout.addWidget(button_row)  # 按钮行添加到布局
        layout.addStretch()

    def bind_signals(self):
        """绑定UI交互信号"""
        # Headers相关
        self.default_headers_radio.toggled.connect(self.toggle_headers_mode)
        self.custom_headers_radio.toggled.connect(self.toggle_headers_mode)
        self.ua_default_check.stateChanged.connect(self.toggle_ua_input)

        # Cookie相关
        self.no_cookie_radio.toggled.connect(self.toggle_cookie_input)
        self.custom_cookie_radio.toggled.connect(self.toggle_cookie_input)

    def toggle_ua_input(self, state):
        """切换User-Agent输入框状态"""
        self.ua_input.setEnabled(not state)
        if state:
            self.ua_input.setText(self.DEFAULT_USER_AGENT)
        else:
            self.ua_input.clear()

    def toggle_headers_mode(self):
        """切换Headers配置模式"""
        is_default = self.default_headers_radio.isChecked()
        self.ct_combo.setEnabled(is_default)
        self.ua_default_check.setEnabled(is_default)
        self.ua_input.setEnabled(is_default and not self.ua_default_check.isChecked())
        self.custom_headers_text.setEnabled(not is_default)

    def toggle_cookie_input(self):
        """切换Cookie输入框状态"""
        self.cookie_text.setEnabled(self.custom_cookie_radio.isChecked())

    def load_config(self):
        """从配置管理器加载保存的配置"""
        # Headers配置
        headers_mode = self.config.get_or_set_config("RequestSettings_headers_mode", "default")
        if headers_mode == 'custom':
            self.custom_headers_radio.setChecked(True)
        self.ct_combo.setCurrentText(
            self.config.get_or_set_config("RequestSettings_content_type", "application/x-www-form-urlencoded"))
        ua_default = self.config.get_or_set_config("RequestSettings_ua_default", "True")
        self.ua_default_check.setChecked(ua_default.lower() == "true")
        self.ua_input.setText(self.config.get_or_set_config("RequestSettings_user_agent", self.DEFAULT_USER_AGENT))
        self.custom_headers_text.setPlainText(self.config.get_or_set_config("RequestSettings_custom_headers", ""))

        # Cookie配置
        cookie_mode = self.config.get_or_set_config("RequestSettings_cookie_mode", "none")
        if cookie_mode == 'custom':
            self.custom_cookie_radio.setChecked(True)
        self.cookie_text.setPlainText(self.config.get_or_set_config("RequestSettings_cookies", ""))

    def save_config(self):
        """保存当前配置到配置管理器"""
        # Headers配置
        self.config.upsert_config("RequestSettings_headers_mode",
                                  "default" if self.default_headers_radio.isChecked() else "custom")
        self.config.upsert_config("RequestSettings_content_type", self.ct_combo.currentText())
        self.config.upsert_config("RequestSettings_ua_default", str(self.ua_default_check.isChecked()))
        self.config.upsert_config("RequestSettings_user_agent", self.ua_input.text())
        self.config.upsert_config("RequestSettings_custom_headers", self.custom_headers_text.toPlainText())

        # Cookie配置
        self.config.upsert_config("RequestSettings_cookie_mode",
                                  "custom" if self.custom_cookie_radio.isChecked() else "none")
        self.config.upsert_config("RequestSettings_cookies", self.cookie_text.toPlainText())

    def on_save_click(self):
        """保存按钮点击事件（新增）"""
        try:
            self.save_config()
            QMessageBox.information(self, "保存成功", "配置已成功保存！", QMessageBox.Ok)
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"配置保存出错：{str(e)}", QMessageBox.Ok)

    def get_headers(self):
        """获取最终的Headers字典"""
        if self.default_headers_radio.isChecked():
            headers = self.DEFAULT_HEADERS.copy()
            headers['Content-Type'] = self.ct_combo.currentText()
            if self.ua_default_check.isChecked():
                headers['User-Agent'] = self.DEFAULT_USER_AGENT
            else:
                ua_value = self.ua_input.text().strip()
                if ua_value:
                    headers['User-Agent'] = ua_value
            return headers
        else:
            try:
                headers_text = self.custom_headers_text.toPlainText().strip()
                if headers_text:
                    return json.loads(headers_text)
                return {}
            except json.JSONDecodeError:
                return self.DEFAULT_HEADERS.copy()

    def get_cookies(self):
        """获取最终的Cookie字典"""
        if self.no_cookie_radio.isChecked():
            return {}
        try:
            cookie_text = self.cookie_text.toPlainText().strip()
            if cookie_text:
                return json.loads(cookie_text)
            return {}
        except json.JSONDecodeError:
            return {}
