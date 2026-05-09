import json
import os
import subprocess
import sys
import time
from datetime import datetime
from io import BytesIO

import requests
from PyQt5.QtCore import Qt, QMimeData, QTimer, pyqtSignal, QThread, QUrl, QEvent, QPoint, QRect, QSize
from PyQt5.QtGui import QIcon, QTextOption, QPixmap, QFont, QColor
from PyQt5.QtWidgets import (QMainWindow, QVBoxLayout, QGroupBox, QTabWidget,  # 新增QMainWindow
                             QWidget, QLabel, QPushButton, QTextEdit, QFrame, QSizePolicy, QMessageBox,
                             QDialog, QApplication, QHBoxLayout, QGraphicsDropShadowEffect,
                             QLineEdit, QFileDialog, QScrollArea, QLayout)
from loguru import logger
from twisted.internet import reactor

from config.common_config import config_manager, encryptor
from config.py_config import config_value
from gui.utils.encryptData import CryptoUtils
from modules.close_all import kill_other_python_processes
from modules.machine_code import get_unique_machine_code


class MachineCodeLoader(QThread):
    """异步加载机器码的线程"""
    # 定义信号：加载完成（返回机器码）、加载失败（返回错误信息）
    code_loaded = pyqtSignal(str)
    load_failed = pyqtSignal(str)

    def run(self):
        """线程执行体：异步获取机器码"""
        try:
            # 调用原机器码函数（耗时操作放到线程中）
            machine_code = get_unique_machine_code()
            if machine_code:
                self.code_loaded.emit(machine_code)
            else:
                self.load_failed.emit("机器码获取为空")
        except Exception as e:
            # 捕获所有异常，通过信号返回
            self.load_failed.emit(f"机器码获取失败：{str(e)[:50]}")


# ========== 图片加载线程类 ==========
class ImageLoaderThread(QThread):
    """异步加载图片的线程"""
    image_loaded = pyqtSignal(QPixmap)
    load_failed = pyqtSignal(str)

    def run(self):
        """线程执行体：异步下载图片"""
        try:
            url = "https://你的服务器地址/usdt.jpg"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            img_data = BytesIO(response.content)
            pixmap = QPixmap()
            if pixmap.loadFromData(img_data.read()):
                scaled_pixmap = pixmap.scaled(700, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.image_loaded.emit(scaled_pixmap)
            else:
                self.load_failed.emit("图片格式不支持")
        except Exception as e:
            self.load_failed.emit(f"图片加载失败\n{str(e)}")


# ========== 2. 原有HelpWindow类修改 ==========
class HelpWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("说明")
        self.setWindowIcon(QIcon('gui/img/favicon.ico'))
        self.resize(1000, 800)
        self.end_time_strp = ""
        self.kami = ""
        self.machine_code_loader = None  # 保存线程实例，避免被回收
        self.myinfo_text_edit = None  # 保存我的信息文本框实例
        self.initUI()

    def initUI(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        # 创建分组框
        group_box = QGroupBox("说明")
        group_layout = QVBoxLayout()
        group_box.setLayout(group_layout)

        # 创建选项卡控件
        tab_widget = QTabWidget()

        # 添加各选项卡（先创建，机器码后续异步填充）
        self.createMyInfoTab(tab_widget)
        self.createPlatformInfoTab(tab_widget)
        self.createContributionTab(tab_widget)
        self.createOfflineKeyTab(tab_widget)
        self.createNetworkOptimizationTab(tab_widget)

        group_layout.addWidget(tab_widget)
        layout.addWidget(group_box)

        # 添加关闭按钮
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

        # ========== 3. 启动机器码异步加载（仅当数据库中没有机器码时） ==========
        try:
            machine_code = self.get_machine_code_from_db()
            if not machine_code:
                self.load_machine_code_async()
        except Exception as e:
            logger.warning(f"数据库未初始化，延迟加载机器码: {str(e)}")
            self.load_machine_code_async()

    def createMyInfoTab(self, tab_widget):
        myinfo = QWidget()
        myinfo_layout = QVBoxLayout()

        # 解密数据（同步操作，数据量小不卡顿）
        with open(f"{config_value.login_data_path}", "r") as f:
            encrypted_data = f.read()

        decrypted_data = encryptor.decrypt(encrypted_data)
        self.kami = decrypted_data.get('kami', '获取失败')
        start_time = decrypted_data.get('start_time', '未知时间')
        end_time = decrypted_data.get('end_time', '未知时间')
        # 从数据库获取权限信息
        try:
            from config.permission_manager import permission_manager
            permissions = permission_manager.load_permissions()
        except Exception as e:
            logger.warning(f"数据库未初始化，无法加载权限: {str(e)}")
            permissions = []
        
        # 判断权限状态
        cloudproxy = "已开通" if "cloudproxy" in permissions else "未开通"
        ddos = "已开通" if "ddos" in permissions else "未开通"
        spider = "已开通" if "spider" in permissions else "未开通"
        temu = "已开通" if "temu" in permissions else "未开通"
        caiwu = "已开通" if "caiwu" in permissions else "未开通"

        start_time_strp = datetime.strptime(start_time, '%Y-%m-%d')
        self.end_time_strp = datetime.strptime(end_time, '%Y-%m-%d')
        date_diff = self.end_time_strp - start_time_strp
        duration = date_diff.days

        self.user_sign_name = config_manager.get_or_set_config("user_sign_name", "我是真爱粉")
        
        # 从数据库中获取机器码，如果没有则异步获取
        try:
            machine_code = self.get_machine_code_from_db()
        except Exception as e:
            logger.warning(f"数据库未初始化，延迟加载机器码: {str(e)}")
            machine_code = None
        
        # 创建文本框（先填充其他信息，机器码占位）
        self.myinfo_text_edit = QTextEdit()
        self.myinfo_text_edit.setReadOnly(True)  # 改为只读更合理
        # 初始文本：如果有机器码则显示，否则显示"加载中..."
        machine_code_display = machine_code if machine_code else "努力加载中..."
        initial_text = "\n".join([
            f"用户签名: {self.user_sign_name}",
            f"卡密: {self.kami}",
            f"时长: {duration}天",
            f"到期时间: {self.end_time_strp.year}年{self.end_time_strp.month}月{self.end_time_strp.day}日",
            f"云代理权限: {cloudproxy}",
            f"DDoS权限: {ddos}",
            f"爬虫权限： {spider}",
            f"Temu任务权限: {temu}",
            f"Temu财务报表权限: {caiwu}",
            f"机器码: {machine_code_display}",  # 显示机器码或加载中
            f"当前版本: {config_value.current_version}"
        ])
        self.myinfo_text_edit.setPlainText(initial_text)

        # 文本框样式设置（保留原有）
        self.myinfo_text_edit.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        self.myinfo_text_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.myinfo_text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.myinfo_text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.myinfo_text_edit.setFrameShape(QFrame.NoFrame)
        self.myinfo_text_edit.setStyleSheet("background: transparent;")
        self.myinfo_text_edit.setWordWrapMode(QTextOption.WordWrap)

        # 创建按钮布局
        button_layout = QHBoxLayout()
        
        # 解绑按钮
        jiebang_button = QPushButton("解绑卡密")
        jiebang_button.setStyleSheet("""
            QPushButton {
                background-color: #0B78F4;
                color: white;
                font-size: 16px;
                border-radius: 4px;
                font-weight: bold;
                border: none;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #0966D4;
            }
            QPushButton:pressed {
                background-color: #0858BC;
            }
        """)
        jiebang_button.clicked.connect(self.jiebang)
        
        # 清理进程按钮
        clean_btn = QPushButton("清理ikun进程")
        clean_btn.setStyleSheet("""
            QPushButton {
                background-color: #DC2626;
                color: white;
                font-size: 16px;
                border-radius: 4px;
                font-weight: bold;
                border: none;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #B91C1C;
            }
            QPushButton:pressed {
                background-color: #991B1B;
            }
        """)
        clean_btn.clicked.connect(self.clean_python_processes)
        
        # 添加按钮到布局，左边解绑卡密和右侧清理进程各占一半
        button_layout.addWidget(jiebang_button, 1)
        button_layout.addWidget(clean_btn, 1)

        # 添加到布局
        myinfo_layout.addWidget(self.myinfo_text_edit, stretch=1)
        myinfo_layout.addLayout(button_layout)
        myinfo_layout.addStretch()
        myinfo.setLayout(myinfo_layout)
        tab_widget.addTab(myinfo, "我的信息")

    def load_machine_code_async(self):
        """启动异步加载机器码"""
        # 创建线程实例
        self.machine_code_loader = MachineCodeLoader()

        # 绑定信号槽：线程完成后更新UI
        self.machine_code_loader.code_loaded.connect(self.on_machine_code_loaded)
        self.machine_code_loader.load_failed.connect(self.on_machine_code_failed)

        # 启动线程（异步执行）
        self.machine_code_loader.start()

    def on_machine_code_loaded(self, machine_code):
        """机器码加载成功：更新文本框并保存到数据库"""
        if not self.myinfo_text_edit:
            return

        # 保存机器码到数据库
        self.save_machine_code_to_db(machine_code)

        # 获取原有文本，替换机器码行
        original_text = self.myinfo_text_edit.toPlainText()
        lines = original_text.split('\n')
        new_lines = []
        for line in lines:
            if line.startswith("机器码:"):
                new_lines.append(f"机器码: {machine_code}")
            else:
                new_lines.append(line)

        # 更新文本
        self.myinfo_text_edit.setPlainText("\n".join(new_lines))

        # 线程完成后销毁，释放资源
        self.machine_code_loader.deleteLater()
        self.machine_code_loader = None

    def on_machine_code_failed(self, error_msg):
        """机器码加载失败：更新提示"""
        if not self.myinfo_text_edit:
            return

        # 替换机器码行为错误提示
        original_text = self.myinfo_text_edit.toPlainText()
        lines = original_text.split('\n')
        new_lines = []
        for line in lines:
            if line.startswith("机器码:"):
                new_lines.append(f"机器码: {error_msg}")
            else:
                new_lines.append(line)

        self.myinfo_text_edit.setPlainText("\n".join(new_lines))

        # 销毁线程
        self.machine_code_loader.deleteLater()
        self.machine_code_loader = None

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

    def createPlatformInfoTab(self, tab_widget):
        platform = QWidget()
        platform_layout = QVBoxLayout()

        # 创建可选中文本的QTextEdit控件
        platform_text = QTextEdit()
        platform_text.setReadOnly(True)  # 修改前为False
        platform_text.setAcceptRichText(True)

        platform_text.setFixedHeight(650)
        html_text = "\n".join([
            # '平台:<font color="#0B78F4">添加账号</font><br>',
            # 补充 style="color:#0000EE; text-decoration:underline;" 让链接有下划线
            # "说明:添加TEMU账号；"
            # "查询格式:店铺手机号 密码"
            # "<br>示例参数：15012346666 abc123456",
            #
            # '<br><br>平台:<font color="#0B78F4">自动导出并计算财务汇总全流程任务</font><br>',
            # "说明:自动执行导出月份的所有地区交易表并自动融合生成对应总表，在总表中添加货号、厂家、成本列，最后自动执行生成财务总表任务；"
            # "查询格式:店铺缩写 指定月份(或月份范围) 指定月份用逗号分割，例如: 2025.1, 2025.12 月份范围用 '-' 分割：2025.2-2025.10"
            # "<br>示例参数1：cxk 2025.10,2025.11",
            # "<br>示例参数2：cxk 2025.2-2025.10",
            #
            # '<br><br>平台:<font color="#0B78F4">生成财务总表</font><br>',
            # "说明:自动搜索店铺目录下的 年份.月份 文件夹，自动计算财务汇总结果，生成或更新最新汇总表（存在汇总表时执行任务过程中不要打开表格文件，否则无法更新表格）；"
            # "查询格式:店铺缩写"
            # "<br>示例参数：cxk",
            #
            # '<br><br>平台:<font color="#0B78F4">连接店铺</font><br>',
            # "说明:执行连接店铺流程，自动填写店铺名称和缩写，一般用于添加账号之后没有自动执行连接店铺或未连接成功时使用；"
            # "查询格式:手机号 或 id"
            # "<br>示例参数1：15012346666",
            # "<br>示例参数2：6 (若此店铺在数据库中查看对应行id为6。请注意！这个括号内的内容无需复制！！！)",

            '<font color="#0B78F4">使用教程</font><br>',

            "<br>1.启动：点击下方服务器选项卡，点击启动按钮",
            "<br>2.添加店铺：点击右侧任务管理，在打开的网页中左侧侧边栏选择店铺管理，填写店铺信息，只填写手机号密码即可",
            "<br>3.提交任务：点击提交任务，选择想要执行的任务，勾选店铺，配置任务参数（可选），提交即可",
            "<br>4.查看任务状态：点击任务管理，查看刚才提交的任务，可查看任务状态。详细日志：点击右侧日志按钮，点击查看任务执行过程的日志",

            '<br><br><font color="#0B78F4">注意</font>：店铺缩写会由系统算法自动生成，涉及配置店铺缩写的文件时不要异想天开，要按照标准的单词填写，例如店铺名字是Cai XuKun，那么店铺缩写是CXK，而不是CX！或者打开数据库查看系统自动生成的店铺缩写是什么，然后填进去即可。'

            "<br><br>任务卡住或者执行失败可尝试点击重跑任务；或在服务器页点击停止按钮，重新启动服务器，然后重新提交任务；或重启程序，然后重新提交任务",
            "<br><br>店铺首次执行正常但后续执行有问题的时候可以尝试在数据库里选中店铺右键清空认证，这样下次执行就和新店铺完全一致了，不会再复用登录认证了",
            "<br>这种情况一般出现于程序未执行完成而被强制退出，或异常导致的非正常退出"
            "<br><br><br>"
        ])

        platform_text.setHtml(html_text)

        # 隐藏边框和背景
        platform_text.setFrameShape(QFrame.NoFrame)  # 无边框
        platform_text.setStyleSheet("background: transparent;")  # 透明背景

        # 设置自动换行
        platform_text.setWordWrapMode(QTextOption.WordWrap)

        # 添加到布局
        platform_layout.addWidget(platform_text)  # 修改前为platform_layout.addWidget(platform_layout)
        platform_layout.addStretch()
        platform.setLayout(platform_layout)
        tab_widget.addTab(platform, "平台信息")

    def createAboutTab(self, tab_widget):
        about = QWidget()
        about_layout = QVBoxLayout()

        # 创建可选中文本的QTextEdit控件
        about_text = QTextEdit()
        about_text.setReadOnly(False)  # 设置为只读
        about_text.setPlainText("\n".join([
            "注意:",
            "其他文件也可能会误报,只需关闭杀毒软件或者添加信任就行了。",
            "本程序无任何后门,放心使用。",
            "请勿修改任何机器码相关的特征(cpu,硬盘,网卡,主板,蓝牙,内存),",
            "或者使用会自己修改的机器码的服务器和挂机宝。否则会机器码无法匹配。",
            f"当前版本: {config_value.current_version}"
        ]))

        # 设置文本交互标志，允许鼠标和键盘选择
        about_text.setTextInteractionFlags(
            Qt.TextSelectableByMouse |
            Qt.TextSelectableByKeyboard
        )

        # 隐藏边框和背景
        about_text.setFrameShape(QFrame.NoFrame)  # 无边框
        about_text.setStyleSheet("background: transparent;")  # 透明背景

        # 设置自动换行
        about_text.setWordWrapMode(QTextOption.WordWrap)

        # 添加到布局
        about_layout.addWidget(about_text)
        about_layout.addStretch()
        about.setLayout(about_layout)
        tab_widget.addTab(about, "关于")

    def show_sponsor_window(self):
        # 固定地址（从配置获取）
        fixed_address = config_value.contribution_usdt_address

        # 创建弹窗，指定父对象为当前窗口，确保生命周期绑定
        dialog = QDialog(self)
        dialog.setWindowTitle("赞助")
        dialog.setFixedSize(800, 900)
        dialog.setWindowModality(Qt.ApplicationModal)

        # 主布局
        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # 支付标题
        title_label = QLabel("USDT-TRON")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)

        # 支付图片（初始显示加载中）
        img_label = QLabel()
        img_label.setAlignment(Qt.AlignCenter)
        img_label.setText("加载中...")
        main_layout.addWidget(img_label)

        # 地址文本
        address_label = QLabel(f"地址：{fixed_address}")
        address_label.setAlignment(Qt.AlignCenter)
        address_label.setStyleSheet("font-size: 24px; margin: 10px 0;")
        main_layout.addWidget(address_label)

        # 复制按钮布局
        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignCenter)

        copy_btn = QPushButton("复制地址")
        copy_btn.setIcon(QIcon("gui/img/fuzhi.png"))
        copy_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        copy_btn.setMinimumHeight(70)
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #f0f0f0;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 24px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
        """)

        # 定义定时器变量，避免匿名函数引用问题
        self.copy_timer = None

        # 复制地址函数（命名函数，避免闭包问题）
        def copy_to_clipboard():
            try:
                # 停止之前的定时器（如果存在）
                if self.copy_timer and self.copy_timer.isActive():
                    self.copy_timer.stop()

                # 复制到剪贴板
                clipboard = QApplication.clipboard()
                mime_data = QMimeData()
                mime_data.setText(fixed_address)
                clipboard.setMimeData(mime_data)

                # 显示成功提示
                copy_btn.setText("已复制！")

                # 创建新定时器，绑定到dialog，随窗口销毁
                self.copy_timer = QTimer(dialog)
                self.copy_timer.setSingleShot(True)
                self.copy_timer.timeout.connect(lambda: copy_btn.setText("复制地址"))
                self.copy_timer.start(2000)  # 2秒后恢复文本

            except Exception as e:
                copy_btn.setText("复制失败")
                # 错误提示也会自动恢复
                if self.copy_timer and self.copy_timer.isActive():
                    self.copy_timer.stop()
                self.copy_timer = QTimer(dialog)
                self.copy_timer.setSingleShot(True)
                self.copy_timer.timeout.connect(lambda: copy_btn.setText("复制地址"))
                self.copy_timer.start(2000)

        copy_btn.clicked.connect(copy_to_clipboard)
        btn_layout.addWidget(copy_btn)
        main_layout.addLayout(btn_layout)

        main_layout.addStretch()

        # 异步加载图片
        image_loader = ImageLoaderThread()
        image_loader.image_loaded.connect(lambda pixmap: img_label.setPixmap(pixmap))
        image_loader.load_failed.connect(lambda error: img_label.setText(error))
        image_loader.start()

        # 显示窗口并等待关闭，关闭后强制销毁
        dialog.exec_()
        dialog.destroy()  # 关键：确保窗口及子对象完全销毁

    # def show_wechat_pay_window(self):
    #     """显示微信支付窗口"""
    #     # 创建弹窗，指定父对象为当前窗口
    #     dialog = QDialog(self)
    #     dialog.setWindowTitle("微信支付")
    #     dialog.setFixedSize(800, 900)
    #     dialog.setWindowModality(Qt.ApplicationModal)
    #
    #     # 主布局
    #     main_layout = QVBoxLayout(dialog)
    #     main_layout.setContentsMargins(20, 20, 20, 20)
    #     main_layout.setSpacing(20)
    #
    #     # 标题
    #     title_label = QLabel("微信扫码支付")
    #     title_font = QFont()
    #     title_font.setPointSize(16)
    #     title_font.setBold(True)
    #     title_label.setFont(title_font)
    #     title_label.setAlignment(Qt.AlignCenter)
    #     main_layout.addWidget(title_label)
    #
    #     # 创建QWebEngineView来显示网页
    #     web_view = QWebEngineView(dialog)
    #     web_view.setUrl(QUrl("http://www.baidu.com"))
    #     main_layout.addWidget(web_view)
    #
    #     # 显示窗口
    #     dialog.exec_()
    #     dialog.destroy()

    def createOfflineKeyTab(self, tab_widget):
        """创建'离线卡密'选项卡"""
        offline = QWidget()
        offline_layout = QVBoxLayout()

        # 创建可选中文本的QTextEdit控件
        offline_text = QTextEdit()
        offline_text.setFixedHeight(450)
        offline_text.setReadOnly(False)  # 设置为只读
        offline_text.setPlainText("\n".join([
            "Telegram：@unoass",
            "Email：mlq5x47hf@mozmail.com",
        ]))

        # 设置文本交互标志，允许鼠标和键盘选择
        offline_text.setTextInteractionFlags(
            Qt.TextSelectableByMouse |
            Qt.TextSelectableByKeyboard
        )

        # 隐藏边框和背景
        offline_text.setFrameShape(QFrame.NoFrame)  # 无边框
        offline_text.setStyleSheet("background: transparent;")  # 透明背景

        # 设置自动换行
        offline_text.setWordWrapMode(QTextOption.WordWrap)

        # 添加到布局
        offline_layout.addWidget(offline_text)
        offline_layout.addStretch()
        offline.setLayout(offline_layout)
        tab_widget.addTab(offline, "贡献")


    def createContributionTab(self, tab_widget):
        contribution = QWidget()
        contribution_layout = QVBoxLayout()

        # 文本区域
        contribution_text = QTextEdit()
        contribution_text.setFixedHeight(650)
        contribution_text.setReadOnly(True)
        contribution_text.setPlainText("\n".join([
            "Telegram：@unoass",
            "Email：mlq5x47hf@mozmail.com",
        ]))

        contribution_text.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        contribution_text.setFrameShape(QFrame.NoFrame)
        contribution_text.setStyleSheet("background: transparent;")
        contribution_text.setWordWrapMode(QTextOption.WordWrap)

        contribution_layout.addWidget(contribution_text)

        # 微信支付按钮
        # wechat_pay_btn = QPushButton("微信支付")
        # wechat_pay_btn.setFixedSize(200, 60)
        # wechat_pay_btn.setStyleSheet("""
        #     QPushButton {
        #         background-color: #07C160;
        #         color: white;
        #         font-size: 28px;
        #         border-radius: 4px;
        #         font-weight: bold;
        #         border: none;
        #     }
        #     QPushButton:hover {
        #         background-color: #06AD56;
        #     }
        #     QPushButton:pressed {
        #         background-color: #059A4C;
        #     }
        # """)
        # wechat_pay_btn.clicked.connect(self.show_wechat_pay_window)
        #
        # # 按钮布局
        # btn_layout = QHBoxLayout()
        # btn_layout.addStretch()
        # btn_layout.addWidget(wechat_pay_btn)
        # btn_layout.addStretch()
        # contribution_layout.addLayout(btn_layout)

        # 赞助按钮
        sponsor_btn = QPushButton("赞助")
        sponsor_btn.setFixedSize(200, 60)

        # 动画定时器 - 四色渐变流光效果
        self.gradient_timer = QTimer(self)
        self.gradient_pos = 0.0
        self.sponsor_btn = sponsor_btn

        # 定义炫彩七色渐变颜色
        self.gradient_colors = [
            "#00d4ff",  # 青蓝色
            "#7c3aed",  # 紫色
            "#f43f5e",  # 玫红色
            "#fbbf24",  # 金黄色
            "#10b981",  # 翠绿色
            "#8b5cf6",  # 淡紫色
            "#ec4899",  # 粉红色
            "#00d4ff"  # 回到青蓝色
        ]

        def update_gradient():
            # 更新渐变位置 (0% -> 400%)
            self.gradient_pos += 0.005  # 8秒一个完整循环 (50ms * 160 = 8000ms)
            if self.gradient_pos > 1.0:
                self.gradient_pos = 0.0

            # 计算当前渐变位置 (0% - 400%)
            pos_percent = self.gradient_pos * 4  # 0 -> 4

            # 创建渐变色停止点
            colors = self.gradient_colors
            stops = []
            num_stops = 32  # 增加渐变层数，更平滑
            for i in range(num_stops):
                stop_pos = i / (num_stops - 1)  # 0 - 1 (修复：原先是0% - 100%)
                # 计算该停止点在渐变中的实际位置
                actual_pos = (pos_percent * 100 + stop_pos * 100) % 400

                # 根据实际位置计算颜色（七色渐变）
                if actual_pos < 100:
                    factor = actual_pos / 100
                    color = interpolate_color(colors[0], colors[1], factor)
                elif actual_pos < 200:
                    factor = (actual_pos - 100) / 100
                    color = interpolate_color(colors[1], colors[2], factor)
                elif actual_pos < 300:
                    factor = (actual_pos - 200) / 100
                    color = interpolate_color(colors[2], colors[3], factor)
                elif actual_pos < 400:
                    factor = (actual_pos - 300) / 100
                    color = interpolate_color(colors[3], colors[4], factor)
                elif actual_pos < 500:
                    factor = (actual_pos - 400) / 100
                    color = interpolate_color(colors[4], colors[5], factor)
                elif actual_pos < 600:
                    factor = (actual_pos - 500) / 100
                    color = interpolate_color(colors[5], colors[6], factor)
                else:
                    factor = (actual_pos - 600) / 100
                    color = interpolate_color(colors[6], colors[7], factor)

                stops.append(f"stop:{stop_pos:.3f} {color}")  # 使用3位小数精度

            # 外发光效果的渐变（偏移一个位置）
            glow_stops = []
            glow_pos = (pos_percent + 0.14) % 7  # 外发光有相位偏移（七色）
            for i in range(num_stops):
                stop_pos = i / (num_stops - 1)  # 0 - 1 (修复：原先是0% - 100%)
                actual_pos = (glow_pos * 100 + stop_pos * 100) % 400

                if actual_pos < 100:
                    factor = actual_pos / 100
                    color = interpolate_color(colors[0], colors[1], factor)
                elif actual_pos < 200:
                    factor = (actual_pos - 100) / 100
                    color = interpolate_color(colors[1], colors[2], factor)
                elif actual_pos < 300:
                    factor = (actual_pos - 200) / 100
                    color = interpolate_color(colors[2], colors[3], factor)
                elif actual_pos < 400:
                    factor = (actual_pos - 300) / 100
                    color = interpolate_color(colors[3], colors[4], factor)
                elif actual_pos < 500:
                    factor = (actual_pos - 400) / 100
                    color = interpolate_color(colors[4], colors[5], factor)
                elif actual_pos < 600:
                    factor = (actual_pos - 500) / 100
                    color = interpolate_color(colors[5], colors[6], factor)
                else:
                    factor = (actual_pos - 600) / 100
                    color = interpolate_color(colors[6], colors[7], factor)

                glow_stops.append(f"stop:{stop_pos:.3f} {color}")  # 使用3位小数精度

            # 转换为CSS渐变字符串
            gradient_css = ', '.join(stops)
            glow_css = ', '.join(glow_stops)

            # 应用样式
            gradient_style = f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {gradient_css});
                    color: white;
                    font-size: 28px;
                    font-weight: bold;
                    border-radius: 60px;
                    border: none;
                    padding: 5px;
                    text-align: center;
                }}
                QPushButton:hover {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {gradient_css});
                }}
                QPushButton:pressed {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {gradient_css});
                }}
            """
            self.sponsor_btn.setStyleSheet(gradient_style)

            # 使用 QGraphicsEffect 实现外发光效果
            if hasattr(self, 'sponsor_btn_effect'):
                self.sponsor_btn.setGraphicsEffect(None)

            from PyQt5.QtWidgets import QGraphicsDropShadowEffect
            from PyQt5.QtGui import QColor

            # 获取当前渐变的中心颜色用于发光（七色）
            center_idx = int((pos_percent % 1.0) * 7)
            center_idx = min(center_idx, 6)
            glow_color = QColor(colors[center_idx])

            # 增强发光效果
            shadow_effect = QGraphicsDropShadowEffect()
            shadow_effect.setBlurRadius(20)  # 更强的发光
            shadow_effect.setColor(glow_color)
            shadow_effect.setOffset(0, 0)
            self.sponsor_btn.setGraphicsEffect(shadow_effect)
            self.sponsor_btn_effect = shadow_effect

        def interpolate_color(color1, color2, factor):
            """在两种颜色之间插值"""
            r1, g1, b1 = int(color1[1:3], 16), int(color1[3:5], 16), int(color1[5:7], 16)
            r2, g2, b2 = int(color2[1:3], 16), int(color2[3:5], 16), int(color2[5:7], 16)
            r = int(r1 + (r2 - r1) * factor)
            g = int(g1 + (g2 - g1) * factor)
            b = int(b1 + (b2 - b1) * factor)
            return f"#{r:02x}{g:02x}{b:02x}"

        # 启动动画（直接播放，不需要hover）
        self.is_hovering = True
        # 连接定时器到更新函数
        self.gradient_timer.timeout.connect(update_gradient)
        self.gradient_timer.start(50)  # 每50ms更新一次

        sponsor_btn.clicked.connect(self.show_sponsor_window)  # 直接绑定，不使用lambda

        # 按钮布局
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(sponsor_btn)
        btn_layout.addStretch()
        contribution_layout.addLayout(btn_layout)

        contribution.setLayout(contribution_layout)
        tab_widget.addTab(contribution, "贡献")

    def createOfflineKeyTab(self, tab_widget):
        """创建'离线卡密'选项卡"""
        offline = QWidget()
        offline_layout = QVBoxLayout()

        # 创建可选中文本的QTextEdit控件
        offline_text = QTextEdit()
        offline_text.setFixedHeight(650)
        offline_text.setReadOnly(False)  # 设置为只读
        offline_text.setPlainText("\n".join([
            "离线卡密: ikun",
            "",
            "离线卡密无需联网验证加密算法即可登陆,注意以下事项",
            "1.未联网无法登录，离线卡密用于云端失联时可使用离线卡密免验证登录",
            "2.机器码改变无法登陆,在线检测到会强制下线",
            "3.卡密过期无法登陆",
            "4.安装包文件缺失可能无法登陆",
            "5.乱发安装包会泄漏卡密,发生盗卡后果自负",
            "",
            "注意: 请勿修改任何机器码相关的特征(cpu,硬盘,网卡,主板,蓝牙,内存)。",
            "离线卡密必须登陆过一次生成了机器码等信息才能用,相当于读取本地缓存。版本到期后软件不可用！",
            f"版本到期时间: {self.end_time_strp}",
        ]))

        # 设置文本交互标志，允许鼠标和键盘选择
        offline_text.setTextInteractionFlags(
            Qt.TextSelectableByMouse |
            Qt.TextSelectableByKeyboard
        )

        # 隐藏边框和背景
        offline_text.setFrameShape(QFrame.NoFrame)  # 无边框
        offline_text.setStyleSheet("background: transparent;")  # 透明背景

        # 设置自动换行
        offline_text.setWordWrapMode(QTextOption.WordWrap)

        # 添加到布局
        offline_layout.addWidget(offline_text)
        offline_layout.addStretch()
        offline.setLayout(offline_layout)
        tab_widget.addTab(offline, "离线卡密")



    def createNetworkOptimizationTab(self, tab_widget):
        """创建'网络调优'选项卡"""
        network = QWidget()
        network_layout = QVBoxLayout()

        # 创建可选中文本的QTextEdit控件
        network_text = QTextEdit()
        network_text.setReadOnly(True)
        network_text.setFixedHeight(650)
        network_text.setPlainText("\n".join([
            "1.管理员权限打开CMD窗口,输入",
            "netsh int ipv4 set dynamicport tcp start=1024 num=64511",
            "netsh int ipv4 set dynamicport udp start=1024 num=64511",
            "",
            "2.CMD窗口输入,查看",
            "netsh int ipv4 show dynamicport tcp",
            "netsh int ipv4 show dynamicport udp",
            "",
            "3.降低Time Wait(端口回收)时间, 最低为30秒(不会可以不设置这个)",
            "CMD输入regedit, 打开注册表, 定位到 ",
            "HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Services\\Tcpip\\Parameters",
            "新增键值 TcpTimedWaitDelay, 类型REG_DWORD, 设置为十进制30",
            "",
            "原理(端口范围0到65535):",
            "netsh int ipv4 set dynamicport tcp start=<起始端口号> num=<端口数量>",
            "",
            "默认设置:",
            "netsh int ipv4 set dynamicport tcp start=49152 num=16384",
            "通过修改tcp/udp 端口范围 来实现大规模并发, 默认只有16384个, 设置后有64511个",
            "",
            "参考url: https://blog.csdn.net/xinfeixiang2019/article/details/103474065",
            "修改后重启服务器生效, 设置后任务进行最少翻3倍, 服务器不堵塞",
        ]))

        # 设置文本交互标志，允许鼠标和键盘选择
        network_text.setTextInteractionFlags(
            Qt.TextSelectableByMouse |
            Qt.TextSelectableByKeyboard
        )

        # 隐藏边框和背景
        network_text.setFrameShape(QFrame.NoFrame)  # 无边框
        network_text.setStyleSheet("background: transparent;")  # 透明背景

        # 设置自动换行
        network_text.setWordWrapMode(QTextOption.WordWrap)

        # 添加到布局
        network_layout.addWidget(network_text)
        network_layout.addStretch()
        network.setLayout(network_layout)
        tab_widget.addTab(network, "网络调优")

    def jiebang(self):
        dialog = QDialog(self)
        reply = QMessageBox.question(
            dialog, '确认解绑',
            f'确定要解绑设备吗？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        timestamp = int(time.time())
        raw_machine_code = get_unique_machine_code()
        
        # 检查机器码是否为None，如果是则返回错误
        if not raw_machine_code:
            QMessageBox.warning(self, "错误", "无法获取机器码，请检查系统权限或重启软件")
            return
            
        machine_code = f"{config_value.prefix_token}-{raw_machine_code}"
        encrypted_machine_code = CryptoUtils.encrypt_data(machine_code)
        encrypted_kami = CryptoUtils.encrypt_data(self.kami)
        signature = CryptoUtils.generate_signature(self.kami, timestamp)
        payload = {
            'encrypted_kami': encrypted_kami,
            'timestamp': timestamp,
            'signature': signature,
            'encrypted_machine_code': encrypted_machine_code
        }
        api_url = f"{config_value.server_api_domain}/api/jiebang.php?static_token={config_value.static_token}"
        proxies = {"http": None, "https": None}
        try:
            response = requests.post(api_url, data=payload, proxies=proxies)
            resp_data = response.json()
            if resp_data.get('code') == 1:
                QMessageBox.information(self, '解绑成功', '解绑成功，程序将退出')
                self.quit_without_confirm()  # 调用无确认退出方法
            else:
                error_msg = resp_data.get('msg', '解绑失败')
                QMessageBox.warning(self, '解绑失败', error_msg)
        except requests.exceptions.RequestException as e:
            QMessageBox.warning(self, '网络错误', f"解绑请求失败：{str(e)}")
            return
        except json.JSONDecodeError:
            QMessageBox.warning(self, '解析错误', '服务器返回数据格式异常，解绑失败')
            return

    def quit_without_confirm(self):
        """无确认退出程序：专门用于解绑成功后，跳过关闭确认弹窗"""
        try:
            logger.info("解绑成功，开始执行无确认退出流程...")

            # 1. 停止日期监测线程
            if hasattr(self,
                       'date_check_thread') and self.date_check_thread is not None and self.date_check_thread.isRunning():
                self.date_check_thread.stop_flag = True
                logger.info("已发送日期监测线程停止信号")

            # 6. 直接退出程序（不触发closeEvent）
            QApplication.instance().quit()  # 替换 self.app.quit()

        except Exception as e:
            logger.error(f"无确认退出流程异常：{str(e)}")
            QApplication.instance().quit()  # 异常时也使用全局实例

    def clean_python_processes(self):
        """清理所有名称包含ikun的应用程序"""
        reply = QMessageBox.question(
            self, '确认清理',
            '确定要关闭所有名称包含ikun的应用程序吗？\n\n这将关闭所有正在运行的ikun相关程序，包括当前程序。',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        try:
            from modules.close_all import kill_ikun_processes_with_delay
            # 使用新的延迟清理函数，它会先显示弹窗，然后分步骤清理进程
            # 注意：这个函数会终止当前进程，所以后续代码可能不会执行
            kill_ikun_processes_with_delay()
            # 如果进程没有被终止，显示成功信息
            QMessageBox.information(self, "击落ikun", "ikun进程清理完成")
        except Exception as e:
            QMessageBox.critical(self, "清理失败", f"清理ikun进程时出错：{str(e)}")

    # 保留原有的closeEvent（用户正常关闭窗口时仍会触发确认弹窗）
    # def closeEvent(self, event):
    #     reply = QMessageBox.question(
    #         self,
    #         '确认退出',
    #         '确定要退出程序吗？进行中的订单状态会修改为已退出。',
    #         QMessageBox.Yes | QMessageBox.No,
    #         QMessageBox.No
    #     )
    #     if reply == QMessageBox.Yes:
    #         # 这里可以复用quit_without_confirm的清理逻辑
    #         self.quit_without_confirm()  # 直接调用清理流程，避免代码重复
    #         event.accept()
    #     else:
    #         event.ignore()
    #         logger.info("用户取消退出操作")

    def kill_custom_processes(self):
        # 保持原有逻辑不变
        current_pid = os.getpid()
        logger.info(f"开始清理进程，PID：{current_pid}")

        try:
            from api.proxy_api import close_proxy_api
            close_proxy_api()
            logger.info("Proxy API 服务已执行关闭流程")
        except Exception as e:
            logger.error(f"关闭 Proxy API 服务失败：{str(e)}")

        try:
            from api.server_api import stop_server_api
            stop_server_api()
            logger.info("服务器进程已执行关闭流程")
        except Exception as e:
            logger.error(f"关闭 Server API 服务失败：{str(e)}")

        logger.info("自定义进程清理完成")
        kill_other_python_processes()

    def eventFilter(self, source, event):
        """事件过滤器：处理赞助按钮的hover事件"""
        # 不再需要hover检测，动画始终运行
        return super().eventFilter(source, event)


# ========== 流式布局类 ==========
class FlowLayout(QLayout):
    """流式布局：从左到右依次排列，一行满了自动换行"""

    def __init__(self, parent=None, spacing=-1):
        super().__init__(parent)
        self.setSpacing(spacing)
        self.item_list = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.item_list.append(item)

    def count(self):
        return len(self.item_list)

    def itemAt(self, index):
        if 0 <= index < len(self.item_list):
            return self.item_list[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.item_list):
            return self.item_list.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self.doLayout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()

        for item in self.item_list:
            size = size.expandedTo(item.minimumSize())

        left, top, right, bottom = self.getContentsMargins()
        size += QSize(left + right, top + bottom)
        return size

    def doLayout(self, rect, testOnly):
        """执行布局计算"""
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(+left, +top, -right, -bottom)

        x = effective_rect.x()
        y = effective_rect.y()
        lineHeight = 0

        for item in self.item_list:
            wid = item.widget()

            spaceX = self.spacing()
            spaceY = self.spacing()

            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > effective_rect.right() and lineHeight > 0:
                x = effective_rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y() + bottom