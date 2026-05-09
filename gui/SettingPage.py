import html
import sys
import os
import traceback
import webbrowser
import platform
import subprocess
import ast

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtWidgets import (QMainWindow, QVBoxLayout, QGroupBox, QTabWidget,
                             QWidget, QFormLayout, QLabel, QPushButton, QTextEdit,
                             QLineEdit, QComboBox, QApplication, QHBoxLayout,
                             QMessageBox, QCheckBox, QSizePolicy)
from loguru import logger

from api.server_routes.task_routes import maintain_task_thread
from config.common_config import config_manager, db
from config.start_config import MAIN_TASK_MANAGER
from config.kami_config import kami_config
from gui.utils.jiami import LoginDataEncryptor

from utils.db_updater_ikun import update_shops_table_structure, update_task_table_structure
from utils.multiThreading_log_manager import get_task_log_manager


class SettingWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setWindowIcon(QIcon('gui/img/favicon.ico'))
        self.resize(1000, 800)
        
        # 获取用户权限
        self.code_project_mode = self.get_user_permissions()

        self.initUI()
        self.load_settings()  # 初始化后加载配置
    
    def get_user_permissions(self):
        """获取用户权限列表"""
        from config.permission_manager import permission_manager
        return permission_manager.load_permissions()

    def initUI(self):
        """初始化UI，只保留指定页面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        # 设置分组框
        group_box = QGroupBox("设置")
        group_layout = QVBoxLayout()
        group_box.setLayout(group_layout)

        # 选项卡控件
        tab_widget = QTabWidget()

        # 只保留指定的页面
        # AI工具页 - 只对有spider权限的用户可见

        self.createProgramSettingTab(tab_widget)  # 程序配置页

        self.createThreadConfigTab(tab_widget)  # 线程数配置页

        if "spider" in self.code_project_mode:
            self.createAIToolTab(tab_widget)  # AI工具页

        # Temu任务配置页 - 只对有temu权限的用户可见
        if "temu" in self.code_project_mode:
            self.createTaskRunningConfigTab(tab_widget)  # Temu任务配置页
            
        # 爬虫设置页 - 只对有spider权限的用户可见
        if "spider" in self.code_project_mode:
            self.createSpiderConfigTab(tab_widget)  # 爬虫设置页
        
        # 财务报表设置页 - 只对有财务报表权限的用户可见
        if "caiwu" in self.code_project_mode:
            self.createFinancialReportConfigTab(tab_widget)  # 财务报表设置页

        group_layout.addWidget(tab_widget)
        layout.addWidget(group_box)

        # 保存按钮
        btn_save = QPushButton("保存")
        btn_save.setIcon(QIcon("gui/img/baochun.png"))  # 注释掉避免找不到图标崩溃
        btn_save.clicked.connect(self.save_all_settings)
        layout.addWidget(btn_save, alignment=Qt.AlignCenter)

    def load_settings(self):
        """加载配置到界面"""
        try:
            # 只有spider权限才加载AI工具配置
            if "spider" in self.code_project_mode and hasattr(self, 'ai_model_name'):
                self.ai_reqeust_url.setText(config_manager.get_or_set_config(
                    "SettingPage_ai_reqeust_url",
                    "https://ark.cn-beijing.volces.com/api/v3"
                ))
                self.ai_token.setText(config_manager.get_or_set_config(
                    "SettingPage_ai_token",
                    "请输入AI模型Token"
                ))
                self.ai_request_mode.setCurrentText(config_manager.get_or_set_config(
                    "SettingPage_ai_request_mode",
                    "智能模式"
                ))
                self.ai_model_name.setText(config_manager.get_or_set_config(
                    "SettingPage_ai_model_name",
                    "doubao-1-5-lite-32k-250115"
                ))
                self.result_rule.setText(config_manager.get_or_set_config(
                    "SettingPage_ai_result_rule",
                    "choices###0###message###content"
                ))
                self.body_content.setPlainText(html.unescape(config_manager.get_or_set_config(
                    "SettingPage_ai_body_content",
                    '{\n"model": "doubao-1-5-lite-32k-250115",\n"messages": [\n{\n"role": "system",\n"content": "你是一位专业的虎扑社区数据分析专家，擅长基于虎扑平台的用户行为数据（回复数、亮评数、推荐数、点赞数、地域/IP信息等）进行多维度分析，输出结构化、有洞察的分析结论。\\n\\n核心分析规则\\n1. 数据类型适配：\\n   - 分析「帖子列表」时：结合回复数、亮评数、推荐数综合判断帖子热度，重点总结关键词下的标题特点（如句式、关键词、吸引点）和整体情感偏向（正向/负向/中性，需说明判断依据）；\\n   - 分析「虎扑评分」时：① 结合点赞数和用户所在地区分析评分分布（如高分/低分占比、地区评分差异）、用户评论核心情感；② 若地区发言特点显著，总结不同地区的典型发言内容及对应情感；\\n   - 分析「帖子详情」时：① 结合点赞数和用户IP属地分析回复内容的核心情感；② 若地区发言有差异，总结地域化典型发言及情感；③ 识别用户讨论热烈的争议点/焦点，单独罗列并分析热议原因（如观点对立、话题敏感、利益相关等）。\\n\\n2. 情感分析标准：\\n   - 正向情感：包含表扬、认可、支持、喜爱、赞美、期待等积极倾向；\\n   - 负向情感：包含批评、吐槽、不满、质疑、愤怒、失望等消极倾向；\\n   - 中性情感：客观描述、信息询问、无明显情绪倾向的内容；\\n   - 需明确标注情感占比（如「正向60%、中性30%、负向10%」），并举例支撑结论。\\n\\n3. 输出格式要求：\\n   - 结论分模块呈现（如「一、热度分析」「二、标题特点」「三、情感偏向」「四、地域发言特征」），逻辑清晰；\\n   - 避免笼统表述，所有结论需结合数据细节（如「XX地区用户占比30%，其中80%的发言吐槽XX点」）；\\n   - 热议点分析需说明「讨论内容+参与规模+核心分歧/共鸣点」。\\n\\n4. 其他要求：\\n   - 语言简洁专业，符合虎扑社区语境（如「亮评」「推荐数」「JRs」等术语使用准确）；\\n   - 优先基于提供的数据得出结论，不主观臆断；若数据不足，明确标注「该维度数据不足，无法分析」。输出格式使用纯文本加换行符的格式进行输出，不要使用markdown，不要带*号加粗等特殊符号或格式"\n}\n]\n}'
                )))
                self.speech_content.setPlainText(html.unescape(config_manager.get_or_set_config(
                    "SettingPage_ai_speech_content",
                    '{"帖子列表": "帮我分析以下帖子列表数据，\\n结合回复数，亮评数，推荐数综合判断热度，总结该关键词下的标题特点和情感偏向：\\n数据内容:#数据内容#", "虎扑评分": "帮我分析以下虎扑评分数据，\\n1.结合点赞数和用户所在地区综合判断，总结该评分对象的评分分布和用户评论的主要情感\\n2.如果地区发言特点明显的话总结出地区更可能出现的相关发言及情感：\\n数据内容:#数据内容#", "帖子详情": "帮我分析以下帖子详情回复数据，\\n1.结合点赞数和用户所在IP地址综合判断，总结该帖子的用户发布内容的主要情感\\n2.如果地区发言特点明显的话总结出地区更可能出现的相关发言及情感\\n3.如果用户之间有因为某些内容讨论热烈的特别罗列并分析原因：\\n数据内容:#数据内容#"}'
                )))

            # 加载程序配置
            # 按照复选框值映射规则：勾选时保存值为"是"，不勾选时保存值为"否"
            auto_login_value = kami_config.get("auto_login", "否")
            self.auto_login.setChecked(auto_login_value == "是")
            
            # 只有temu权限才加载task_auto_login配置
            if "temu" in self.code_project_mode and hasattr(self, 'task_auto_login'):
                task_auto_login_value = config_manager.get_or_set_config(
                    "task_auto_login",
                    "是"  # 默认改为"是"
                )
                self.task_auto_login.setChecked(task_auto_login_value == "是")
            
            auto_run_server_value = config_manager.get_or_set_config(
                "SettingPage_auto_run_server",
                "否"
            )
            self.auto_run_server.setChecked(auto_run_server_value == "是")

            handle_yzm_by_hand_value = config_manager.get_or_set_config(
                "handle_yzm_by_hand",
                "否"
            )
            # 只有temu权限才设置handle_yzm_by_hand
            if "temu" in self.code_project_mode and hasattr(self, 'handle_yzm_by_hand'):
                self.handle_yzm_by_hand.setChecked(handle_yzm_by_hand_value == "是")
            
            # 加载错误日志记录次数设置
            self.max_error_logs.setText(config_manager.get_or_set_config(
                "max_error_logs",
                "100"  # 默认100次
            ))
            
            # 加载背景音乐设置
            background_music_enabled_value = config_manager.get_or_set_config(
                "background_music_enabled",
                "是"  # 默认启用
            )
            self.background_music_enabled.setChecked(background_music_enabled_value == "是")
            
            background_music_autoplay_value = config_manager.get_or_set_config(
                "background_music_autoplay",
                "否"  # 默认不自动播放
            )
            self.background_music_autoplay.setChecked(background_music_autoplay_value == "是")
            
            self.background_music_url.setText(config_manager.get_or_set_config(
                "background_music_url",
                "https://link.hhtjim.com/163/3355136306.mp3"  # 默认音乐链接
            ))

            background_music_local_value = config_manager.get_or_set_config(
                "background_music_local",
                "否"  # 默认不播放本地音乐
            )
            self.background_music_local.setChecked(background_music_local_value == "是")

            Settings_use_cookies_value = config_manager.get_or_set_config(
                "Settings_use_cookies",
                "是"  # 默认改为"是"
            )
            # 只有temu权限才设置Settings_use_cookies
            if "temu" in self.code_project_mode and hasattr(self, 'Settings_use_cookies'):
                self.Settings_use_cookies.setChecked(Settings_use_cookies_value == "是")


            self.user_sign_name.setText(config_manager.get_or_set_config(
                "user_sign_name",
                "我是真爱粉"
            ))

            # 加载线程数配置
            self.max_concurrent_tasks.setText(config_manager.get_or_set_config(
                "max_concurrent_tasks",
                "200"
            ))
            
            # 只有temu权限才加载temu相关的线程配置
            if "temu" in self.code_project_mode:
                self.modify_price_concurrent.setText(config_manager.get_or_set_config(
                    "modify_price_concurrent",
                    "2"
                ))
                self.expected_goods_place_concurrent.setText(config_manager.get_or_set_config(
                    "expected_goods_place_concurrent",
                    "2"
                ))
                self.apply_activity_concurrent.setText(config_manager.get_or_set_config(
                    "apply_activity_concurrent",
                    "2"
                ))
                self.upload_real_pic_concurrent.setText(config_manager.get_or_set_config(
                    "upload_real_pic_concurrent",
                    "2"
                ))
                self.jit_govern_concurrent.setText(config_manager.get_or_set_config(
                    "jit_govern_concurrent",
                    "2"
                ))
            
            # 只有spider权限才加载spider相关的线程配置
            if "spider" in self.code_project_mode:
                self.hupu_post_list_concurrent.setText(config_manager.get_or_set_config(
                    "hupu_post_list_concurrent",
                    "2"
                ))
                self.hupu_detail_list_concurrent.setText(config_manager.get_or_set_config(
                    "hupu_detail_list_concurrent",
                    "2"
                ))
                self.hupu_score_list_concurrent.setText(config_manager.get_or_set_config(
                    "hupu_score_list_concurrent",
                    "2"
                ))

            # 加载任务配置（核价次数+降低金额）- 只有temu权限才加载
            if "temu" in self.code_project_mode:
                self.maintain_task_thread_space_time.setText(config_manager.get_or_set_config(
                    "maintain_task_thread_space_time",
                    "30"  # 默认值
                ))
                self.global_modify_times.setText(config_manager.get_or_set_config(
                    "global_modify_times",
                    "10"  # 默认值
                ))
                self.global_minu_price.setText(config_manager.get_or_set_config(
                    "global_minu_price",
                    "0.01"  # 默认值
                ))
                self.global_jit_final_num.setText(config_manager.get_or_set_config(
                    "jit_default_final_num",
                    "500"  # 默认值，与JIT任务中的默认值保持一致
                ))

            # 只有temu权限才加载上传实拍图记录SPU设置
            if "temu" in self.code_project_mode and hasattr(self, 'record_upload_pic_spu_list'):
                record_upload_pic_spu_list_value = config_manager.get_or_set_config(
                    "record_upload_pic_spu_list",
                    "是"  # 默认改为"是"
                )
                self.record_upload_pic_spu_list.setChecked(record_upload_pic_spu_list_value == "是")

            # ========== 新增：加载爬虫设置 ==========
            if "spider" in self.code_project_mode:
                spider_use_proxy_value = config_manager.get_or_set_config(
                    "spider_use_proxy",
                    "否"  # 默认不使用代理
                )
                self.spider_use_proxy.setChecked(spider_use_proxy_value == "是")
                
                spider_force_proxy_value = config_manager.get_or_set_config(
                    "spider_force_proxy",
                    "否"  # 默认不强制使用代理
                )
                self.spider_force_proxy.setChecked(spider_force_proxy_value == "是")

            # ========== 新增：加载财务报表设置 ==========
            if "caiwu" in self.code_project_mode and hasattr(self, 'sku_threshold'):
                self.sku_threshold.setText(config_manager.get_or_set_config(
                    "Settings_caiwu_sku_threshold",
                    "95"
                ))
                self.factory_threshold.setText(config_manager.get_or_set_config(
                    "Settings_caiwu_factory_threshold",
                    "95"
                ))
                self.total_threshold.setText(config_manager.get_or_set_config(
                    "Settings_caiwu_total_threshold",
                    "95"
                ))

        except Exception as e:
            logger.error(f"加载配置时出错: {str(e)}\n{traceback.format_exc()}")
            QMessageBox.warning(self, "加载失败", f"配置加载出错：{str(e)}")

    def save_all_settings(self):
        """保存所有配置"""
        try:
            # 只有spider权限才保存AI工具配置
            if "spider" in self.code_project_mode and hasattr(self, 'ai_model_name'):
                config_manager.upsert_config("SettingPage_ai_reqeust_url", self.ai_reqeust_url.text())
                config_manager.upsert_config("SettingPage_ai_token", self.ai_token.text())
                config_manager.upsert_config("SettingPage_ai_request_mode", self.ai_request_mode.currentText())
                config_manager.upsert_config("SettingPage_ai_model_name", self.ai_model_name.text())
                config_manager.upsert_config("SettingPage_ai_body_content", self.body_content.toPlainText())
                config_manager.upsert_config("SettingPage_ai_result_rule", self.result_rule.text())
                config_manager.upsert_config("SettingPage_ai_speech_content", self.speech_content.toPlainText())

            # 保存程序配置 - 添加权限检查
            # 按照复选框值映射规则：勾选时保存值为"是"，不勾选时保存值为"否"
            if hasattr(self, 'auto_login'):
                auto_login_value = "是" if self.auto_login.isChecked() else "否"
                config_manager.upsert_config("SettingPage_auto_login", auto_login_value)
                kami_config.set("auto_login", auto_login_value)
            
            # 只有temu权限才保存task_auto_login配置
            if "temu" in self.code_project_mode and hasattr(self, 'task_auto_login'):
                config_manager.upsert_config("task_auto_login",
                                            "是" if self.task_auto_login.isChecked() else "否")
            
            if hasattr(self, 'auto_run_server'):
                config_manager.upsert_config("SettingPage_auto_run_server",
                                            "是" if self.auto_run_server.isChecked() else "否")
            
            if hasattr(self, 'handle_yzm_by_hand'):
                config_manager.upsert_config("handle_yzm_by_hand",
                                            "是" if self.handle_yzm_by_hand.isChecked() else "否")
            
            # 保存错误日志记录次数设置
            if hasattr(self, 'max_error_logs'):
                max_error_logs_value = self.max_error_logs.text().strip()
                if not max_error_logs_value or not max_error_logs_value.isdigit() or int(max_error_logs_value) < 1:
                    max_error_logs_value = "100"  # 默认值
                config_manager.upsert_config("max_error_logs", max_error_logs_value)
            
            # 保存背景音乐设置
            if hasattr(self, 'background_music_enabled'):
                config_manager.upsert_config("background_music_enabled",
                                            "是" if self.background_music_enabled.isChecked() else "否")
            
            if hasattr(self, 'background_music_autoplay'):
                config_manager.upsert_config("background_music_autoplay",
                                            "是" if self.background_music_autoplay.isChecked() else "否")
            
            if hasattr(self, 'background_music_url'):
                config_manager.upsert_config("background_music_url", self.background_music_url.text())
            
            if hasattr(self, 'background_music_local'):
                config_manager.upsert_config("background_music_local",
                                            "是" if self.background_music_local.isChecked() else "否")
            
            # 保存其他设置
            if hasattr(self, 'Settings_use_cookies'):
                config_manager.upsert_config("Settings_use_cookies",
                                            "是" if self.Settings_use_cookies.isChecked() else "否")
            
            if hasattr(self, 'Settings_yinghua_html'):
                config_manager.upsert_config("Settings_yinghua_html",
                                            "是" if self.Settings_yinghua_html.isChecked() else "否")
            
            if hasattr(self, 'Settings_qipao_html'):
                config_manager.upsert_config("Settings_qipao_html",
                                            "是" if self.Settings_qipao_html.isChecked() else "否")
            
            if hasattr(self, 'Settings_close_confirm'):
                config_manager.upsert_config("close_confirm",
                                            "1" if self.Settings_close_confirm.isChecked() else "0")
            
            if hasattr(self, 'Settings_rose_html'):
                config_manager.upsert_config("Settings_rose_html",
                                            "是" if self.Settings_rose_html.isChecked() else "否")
            
            if hasattr(self, 'cdn_mode_combo'):
                config_manager.upsert_config("Settings_cdn_mode", self.cdn_mode_combo.currentText())
            
            if hasattr(self, 'Settings_theme'):
                config_manager.upsert_config("Settings_theme", self.Settings_theme.currentText())
            
            if hasattr(self, 'user_sign_name'):
                config_manager.upsert_config("user_sign_name", self.user_sign_name.text())

            # 保存线程数配置
            try:
                # 1. 定义线程配置映射（功能名: (输入控件, 配置key)）
                thread_configs = []
                
                # 只有temu权限才添加temu相关的线程配置
                if "temu" in self.code_project_mode:
                    thread_configs.extend([
                        ("核价", self.modify_price_concurrent, "modify_price_concurrent"),
                        ("期望到货地点", self.expected_goods_place_concurrent, "expected_goods_place_concurrent"),
                        ("报活动", self.apply_activity_concurrent, "apply_activity_concurrent"),
                        ("上传实拍图", self.upload_real_pic_concurrent, "upload_real_pic_concurrent"),
                        ("JIT库存", self.jit_govern_concurrent, "jit_govern_concurrent"),
                    ])
                
                # 只有spider权限才添加spider相关的线程配置
                if "spider" in self.code_project_mode:
                    thread_configs.append(("虎扑帖子列表采集", self.hupu_post_list_concurrent, "hupu_post_list_concurrent"))
                    thread_configs.append(("虎扑帖子详情采集", self.hupu_detail_list_concurrent, "hupu_detail_list_concurrent"))
                    thread_configs.append(("虎扑评分采集", self.hupu_score_list_concurrent, "hupu_score_list_concurrent"))

                # 2. 批量验证+保存+更新
                new_vals = {}
                # 先验证所有输入
                for func_name, widget, config_key in thread_configs:
                    val = int(widget.text())
                    if val < 1:
                        raise ValueError(f"{func_name}任务线程数必须≥1")
                    new_vals[config_key] = val

                # 全局最大并发单独验证
                max_concurrent_tasks = int(self.max_concurrent_tasks.text())
                if max_concurrent_tasks < 1:
                    raise ValueError("最大任务线程数必须≥1")
                new_vals["max_concurrent_tasks"] = max_concurrent_tasks

                # 3. 批量保存到配置文件
                for config_key, val in new_vals.items():
                    config_manager.upsert_config(config_key, str(val))

                # 4. 批量调用update_func_config更新线程数（核心：用for循环）
                for func_name, widget, config_key in thread_configs:
                    get_task_log_manager().update_func_config(func_name, new_vals[config_key])
                    logger.info(f"{func_name}任务并发数已更新为: {new_vals[config_key]}")

            except ValueError as e:
                QMessageBox.warning(self, "输入错误", f"线程数输入无效：{str(e)}")
                return

            # 验证并保存核价任务配置 - 只有temu权限才保存
            if "temu" in self.code_project_mode:
                try:
                    # 1. 核价次数（必须是≥1的整数）
                    modify_times = int(self.global_modify_times.text())
                    if modify_times < 1:
                        raise ValueError("最大核价次数必须≥1")

                    # 2. 每次降低金额（必须是≥0的浮点数）
                    minu_price = float(self.global_minu_price.text())
                    if minu_price < 0:
                        raise ValueError("核价每次降低金额必须≥0")

                    # 3. JIT库存目标数量（必须是≥1的整数）
                    jit_final_num = int(self.global_jit_final_num.text())
                    if jit_final_num < 1:
                        raise ValueError("JIT库存目标数量必须≥1")

                    # 4. 保存到配置 - 添加权限检查
                    if hasattr(self, 'maintain_task_thread_space_time'):
                        config_manager.upsert_config("maintain_task_thread_space_time",
                                                     self.maintain_task_thread_space_time.text())
                    
                    config_manager.upsert_config("global_modify_times", str(modify_times))
                    config_manager.upsert_config("global_minu_price", str(minu_price))
                    config_manager.upsert_config("jit_default_final_num", str(jit_final_num))

                    logger.info(f"工具配置表已更新：最大核价次数={modify_times}，核价重新申报降价金额={minu_price}元，JIT库存目标数量={jit_final_num}")

                except ValueError as e:
                    QMessageBox.warning(self, "输入错误", f"工具配置表输入无效：{str(e)}")
                    return

            # ========== 新增：保存上传实拍图记录SPU的复选框状态 ==========
            if "temu" in self.code_project_mode and hasattr(self, 'record_upload_pic_spu_list'):
                config_manager.upsert_config("record_upload_pic_spu_list", 
                                            "是" if self.record_upload_pic_spu_list.isChecked() else "否")

            # ========== 新增：保存爬虫设置 ==========
            if "spider" in self.code_project_mode:
                config_manager.upsert_config("spider_use_proxy",
                                            "是" if self.spider_use_proxy.isChecked() else "否")
                config_manager.upsert_config("spider_force_proxy",
                                            "是" if self.spider_force_proxy.isChecked() else "否")

            # ========== 新增：保存财务报表设置 ==========
            if "caiwu" in self.code_project_mode and hasattr(self, 'sku_threshold'):
                config_manager.upsert_config("Settings_caiwu_sku_threshold", self.sku_threshold.text())
                config_manager.upsert_config("Settings_caiwu_factory_threshold", self.factory_threshold.text())
                config_manager.upsert_config("Settings_caiwu_total_threshold", self.total_threshold.text())

            logger.trace("设置已保存")
            QMessageBox.information(self, "保存成功", "所有设置已成功保存！")

        except Exception as e:
            logger.error(f"保存设置时出错: {str(e)}\n{traceback.format_exc()}")
            QMessageBox.warning(self, "保存失败", f"设置保存出错：{str(e)}")

    def createAIToolTab(self, tab_widget):
        """创建AI工具选项卡"""
        ai_tool = QWidget()
        layout = QVBoxLayout(ai_tool)

        # 推荐信息
        recommend_text = QTextEdit()
        recommend_text.setPlainText("推荐豆包，官网申请key填入请求头中 https://www.volcengine.com/product/ark")
        recommend_text.setReadOnly(True)
        recommend_text.setFrameStyle(QTextEdit.NoFrame)
        recommend_text.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        recommend_text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        recommend_text.setStyleSheet("background: transparent;")
        recommend_text.setFixedHeight(50)
        layout.addWidget(recommend_text)

        # URL和请求模式
        url_mode_container = QWidget()
        url_mode_layout = QHBoxLayout(url_mode_container)
        url_mode_layout.setContentsMargins(0, 0, 0, 0)

        url_label = QLabel("URL:")
        self.ai_reqeust_url = QLineEdit()
        self.ai_reqeust_url.setMinimumWidth(700)

        mode_label = QLabel("模式:")
        self.ai_request_mode = QComboBox()
        self.ai_request_mode.addItems(["POST", "GET"])
        self.ai_request_mode.setMaximumWidth(150)

        url_mode_layout.addWidget(url_label)
        url_mode_layout.addWidget(self.ai_reqeust_url, 8)
        url_mode_layout.addSpacing(20)
        url_mode_layout.addWidget(mode_label)
        url_mode_layout.addWidget(self.ai_request_mode, 2)
        url_mode_layout.addStretch()

        # 表单布局
        form_layout = QFormLayout()
        form_layout.addRow(url_mode_container)

        # Token
        self.ai_token = QLineEdit()
        self.ai_token.setMinimumWidth(700)
        form_layout.addRow("Token:", self.ai_token)

        # 模型名称
        self.ai_model_name = QLineEdit()
        self.ai_model_name.setMinimumWidth(700)
        form_layout.addRow("模型名称:", self.ai_model_name)

        # 请求体
        self.body_content = QTextEdit()
        self.body_content.setFixedHeight(120)
        form_layout.addRow("请求体:", self.body_content)

        # 结果规则
        self.result_rule = QLineEdit()
        form_layout.addRow("规则:", self.result_rule)

        # 提示词
        self.speech_content = QTextEdit()
        form_layout.addRow("提示词:", self.speech_content)

        # 添加到布局
        form_widget = QWidget()
        form_widget.setLayout(form_layout)
        layout.addWidget(form_widget)

        tab_widget.addTab(ai_tool, "AI工具")

    def createProgramSettingTab(self, tab_widget):
        """创建程序配置选项卡（改造后：新增更新表结构按钮+弹窗提示）"""
        program_setting = QWidget()
        layout = QFormLayout(program_setting)
        layout.setVerticalSpacing(3)  # 减小垂直间距，避免输入框空隙过大
        layout.setHorizontalSpacing(5)  # 减小水平间距，减小标签与输入框之间的距离
        layout.setContentsMargins(10, 10, 10, 10)  # 设置外边距
        layout.setLabelAlignment(Qt.AlignLeft)  # 标签左对齐，布局更美观

        # 1. 用户签名 + 右侧更新表结构按钮（横向布局）
        self.user_sign_name = QLineEdit()
        self.user_sign_name.setMinimumWidth(150)
        self.user_sign_name.setPlaceholderText("显示在标题后面的个性签名")

        # 创建横向布局：输入框 + 按钮
        h_layout = QHBoxLayout()
        h_layout.addWidget(self.user_sign_name)
        # 新增更新表结构按钮
        self.update_table_btn = QPushButton("更新数据库表结构")
        self.update_table_btn.setIcon(QIcon("gui/img/tijiao.png"))
        # 绑定按钮点击事件：触发表更新并弹窗提示
        self.update_table_btn.clicked.connect(self.update_db_table_structure)
        h_layout.addWidget(self.update_table_btn)
        h_layout.setSpacing(20)  # 输入框与按钮间距

        # 将横向布局添加到表单布局，替代原有单独的输入框
        layout.addRow("用户签名:", h_layout)

        # 主题设置，默认主题（放在用户签名下面）
        theme_value = config_manager.get_or_set_config(
            "Settings_theme",
            "默认主题"
        )
        self.Settings_theme = QComboBox()
        self.Settings_theme.addItems(["默认主题", "新年主题"])
        theme_index = self.Settings_theme.findText(theme_value)
        if theme_index >= 0:
            self.Settings_theme.setCurrentIndex(theme_index)
        layout.addRow("主题设置:", self.Settings_theme)

        # 按照复选框布局顺序规范，新增的复选框配置项应放置在复选框组的最上方
        
        # 程序配置设置
        program_config_group = QGroupBox("程序配置")
        program_config_layout = QVBoxLayout(program_config_group)
        
        # 程序启动时自动登录复选框（优先级最高）
        self.auto_login = QCheckBox("程序启动时自动登录")
        program_config_layout.addWidget(self.auto_login)

        # 程序启动时自动运行服务器
        self.auto_run_server = QCheckBox("程序启动时自动运行服务器")
        program_config_layout.addWidget(self.auto_run_server)
        
        # 关闭确认弹窗，默认开启
        close_confirm_value = config_manager.get_or_set_config(
            "close_confirm",
            "1"
        )
        self.Settings_close_confirm = QCheckBox("程序关闭确认弹窗")
        self.Settings_close_confirm.setChecked(close_confirm_value == "1")
        program_config_layout.addWidget(self.Settings_close_confirm)
        
        layout.addRow(program_config_group)

        # 特效效果设置
        effect_group = QGroupBox("特效效果")
        effect_layout = QVBoxLayout(effect_group)

        # 樱花效果，默认开启
        yinghua_html_value = config_manager.get_or_set_config(
            "Settings_yinghua_html",
            "是"
        )
        self.Settings_yinghua_html = QCheckBox("樱花效果")
        self.Settings_yinghua_html.setChecked(yinghua_html_value == "是")
        effect_layout.addWidget(self.Settings_yinghua_html)

        # 气泡效果，默认开启
        qipao_html_value = config_manager.get_or_set_config(
            "Settings_qipao_html",
            "是"
        )
        self.Settings_qipao_html = QCheckBox("气泡效果")
        self.Settings_qipao_html.setChecked(qipao_html_value == "是")
        effect_layout.addWidget(self.Settings_qipao_html)

        # Rose效果，默认关闭
        rose_html_value = config_manager.get_or_set_config(
            "Settings_rose_html",
            "否"
        )
        self.Settings_rose_html = QCheckBox("玫瑰花瓣效果")
        self.Settings_rose_html.setChecked(rose_html_value == "是")
        effect_layout.addWidget(self.Settings_rose_html)

        layout.addRow(effect_group)
        
        # 其他设置
        web_group = QGroupBox("其他设置")
        web_layout = QVBoxLayout(web_group)
        
        # CDN加载模式
        cdn_mode_value = config_manager.get_or_set_config(
            "Settings_cdn_mode",
            "混合"
        )
        self.cdn_mode_combo = QComboBox()
        self.cdn_mode_combo.addItems(["本地", "云端", "混合"])
        self.cdn_mode_combo.setCurrentText(cdn_mode_value)
        web_layout.addWidget(QLabel("CDN加载模式:"))
        web_layout.addWidget(self.cdn_mode_combo)
        
        # 背景音乐设置
        background_music_container = QWidget()
        background_music_layout = QHBoxLayout(background_music_container)
        background_music_layout.setContentsMargins(0, 0, 0, 0)
        
        self.background_music_enabled = QCheckBox("启用")
        background_music_layout.addWidget(self.background_music_enabled)
        
        self.background_music_autoplay = QCheckBox("自动播放")
        background_music_layout.addWidget(self.background_music_autoplay)
        
        self.background_music_local = QCheckBox("播放本地音乐")
        background_music_layout.addWidget(self.background_music_local)
        
        self.background_music_url = QLineEdit()
        self.background_music_url.setPlaceholderText("输入MP3音乐链接，如：https://example.com/music.mp3")
        self.background_music_url.setMinimumWidth(300)
        background_music_layout.addWidget(self.background_music_url)
        
        self.music_format_button = QPushButton("格式转化工具")
        self.music_format_button.setIcon(QIcon("gui/img/tijiao.png"))
        self.music_format_button.setToolTip("打开音乐格式转化工具")
        self.music_format_button.clicked.connect(self.openMusicFormatTool)
        background_music_layout.addWidget(self.music_format_button)
        
        web_layout.addWidget(QLabel("背景音乐:"))
        web_layout.addWidget(background_music_container)
        
        # 同步"播放本地音乐"与"特效效果"中的复选框状态（已移除特效栏的同步）
        # self.background_music_local 仅在"背景音乐"栏中存在
        
        layout.addRow(web_group)
        
        # 错误日志记录次数设置
        error_log_container = QWidget()
        error_log_layout = QHBoxLayout(error_log_container)
        error_log_layout.setContentsMargins(0, 0, 0, 0)
        
        self.max_error_logs = QLineEdit()
        self.max_error_logs.setPlaceholderText("默认100次")
        self.max_error_logs.setMinimumWidth(100)
        error_log_layout.addWidget(self.max_error_logs)
        
        # 添加打开error.log文件的按钮
        self.open_error_log_button = QPushButton("打开错误日志")
        self.open_error_log_button.setIcon(QIcon("gui/img/tijiao.png"))  # 使用指定的图标
        self.open_error_log_button.clicked.connect(self.open_error_log_file)
        self.open_error_log_button.setToolTip("打开error/error.log文件")
        error_log_layout.addWidget(self.open_error_log_button)
        
        layout.addRow("错误日志记录次数设置（超过后将自动清理旧记录）:", error_log_container)

        tab_widget.addTab(program_setting, "系统配置")

    def update_db_table_structure(self):
        """根据权限更新对应的数据库表结构"""
        # 初始化结果统计
        result_msg = []
        success_count = 0
        total_count = 0
        
        # 根据权限更新对应的数据库表结构
        if any(p in self.code_project_mode for p in ["temu", "caiwu"]):
            # 更新 ikun 数据库
            try:
                from config.common_config import initialize_ikun_database
                ikun_success = initialize_ikun_database()
                if ikun_success:
                    result_msg.append("✅ ikun 数据库结构更新成功")
                    success_count += 1
                else:
                    result_msg.append("❌ ikun 数据库结构更新失败")
                total_count += 1
            except Exception as e:
                result_msg.append(f"❌ ikun 数据库更新异常：{str(e)[:50]}...")
                total_count += 1
        
        if "spider" in self.code_project_mode:
            # 更新 hupu 数据库
            try:
                from config.common_config import initialize_hupu_database
                hupu_success = initialize_hupu_database()
                if hupu_success:
                    result_msg.append("✅ hupu 数据库结构更新成功")
                    success_count += 1
                else:
                    result_msg.append("❌ hupu 数据库结构更新失败")
                total_count += 1
            except Exception as e:
                result_msg.append(f"❌ hupu 数据库更新异常：{str(e)[:50]}...")
                total_count += 1
        
        # 修复定时任务表（移除外键约束）
        try:
            from utils.scheduled_tasks_db_updater import update_scheduled_tasks_table_structure
            from config.common_config import db
            repair_success = update_scheduled_tasks_table_structure(db, confirm_drop=False)
            if repair_success:
                result_msg.append("✅ 定时任务表修复成功")
                success_count += 1
            else:
                result_msg.append("❌ 定时任务表修复失败")
            total_count += 1
        except Exception as e:
            result_msg.append(f"❌ 定时任务表修复异常：{str(e)[:50]}...")
            total_count += 1
        
        # 拼接最终提示信息
        if total_count == 0:
            final_msg = "⚠️ 当前权限无需更新任何数据库表结构"
        else:
            final_msg = "\n".join(
                result_msg) + f"\n\n📊 总计更新 {total_count} 个数据库，成功 {success_count} 个，失败 {total_count - success_count} 个"

        # 根据执行结果弹出对应类型弹窗（成功/失败）
        if total_count == 0:
            QMessageBox.information(
                self,  # 父窗口，确保弹窗在主窗口上方
                "无需更新",  # 弹窗标题
                final_msg,  # 弹窗内容
                QMessageBox.Ok  # 确认按钮
            )
        elif success_count == total_count:
            QMessageBox.information(
                self,  # 父窗口，确保弹窗在主窗口上方
                "更新成功",  # 弹窗标题
                final_msg,  # 弹窗内容
                QMessageBox.Ok  # 确认按钮
            )
        else:
            QMessageBox.critical(
                self,
                "更新失败",
                final_msg,
                QMessageBox.Ok
            )

    def createThreadConfigTab(self, tab_widget):
        """创建线程数配置选项卡"""
        thread_config = QWidget()
        layout = QFormLayout(thread_config)
        layout.setSpacing(15)

        # 最大任务线程数
        self.max_concurrent_tasks = QLineEdit()
        self.max_concurrent_tasks.setMinimumWidth(100)
        self.max_concurrent_tasks.setPlaceholderText("请输入数字，如200")
        layout.addRow("任务线程数:", self.max_concurrent_tasks)

        if "temu" in self.code_project_mode:
            # 核价任务线程数
            self.modify_price_concurrent = QLineEdit()
            self.modify_price_concurrent.setMinimumWidth(100)
            self.modify_price_concurrent.setPlaceholderText("请输入数字，如2")
            layout.addRow("核价任务:", self.modify_price_concurrent)

            # 期望到货地点任务线程数
            self.expected_goods_place_concurrent = QLineEdit()
            self.expected_goods_place_concurrent.setMinimumWidth(100)
            self.expected_goods_place_concurrent.setPlaceholderText("请输入数字，如2")
            layout.addRow("期望到货地点任务:", self.expected_goods_place_concurrent)

            # 报活动任务线程数
            self.apply_activity_concurrent = QLineEdit()
            self.apply_activity_concurrent.setMinimumWidth(100)
            self.apply_activity_concurrent.setPlaceholderText("请输入数字，如2")
            layout.addRow("报活动任务:", self.apply_activity_concurrent)

            # 上传实拍图任务线程数
            self.upload_real_pic_concurrent = QLineEdit()
            self.upload_real_pic_concurrent.setMinimumWidth(100)
            self.upload_real_pic_concurrent.setPlaceholderText("请输入数字，如2")
            layout.addRow("上传实拍图任务:", self.upload_real_pic_concurrent)

            # JIT库存任务线程数
            self.jit_govern_concurrent = QLineEdit()
            self.jit_govern_concurrent.setMinimumWidth(100)
            self.jit_govern_concurrent.setPlaceholderText("请输入数字，如2")
            layout.addRow("JIT库存任务:", self.jit_govern_concurrent)
        
        if "spider" in self.code_project_mode:
            # 虎扑帖子列表任务线程数
            self.hupu_post_list_concurrent = QLineEdit()
            self.hupu_post_list_concurrent.setMinimumWidth(100)
            self.hupu_post_list_concurrent.setPlaceholderText("请输入数字，如2")
            layout.addRow("虎扑帖子列表任务:", self.hupu_post_list_concurrent)
            
            # 虎扑帖子详情任务线程数
            self.hupu_detail_list_concurrent = QLineEdit()
            self.hupu_detail_list_concurrent.setMinimumWidth(100)
            self.hupu_detail_list_concurrent.setPlaceholderText("请输入数字，如2")
            layout.addRow("虎扑帖子详情任务:", self.hupu_detail_list_concurrent)
            
            # 虎扑评分任务线程数
            self.hupu_score_list_concurrent = QLineEdit()
            self.hupu_score_list_concurrent.setMinimumWidth(100)
            self.hupu_score_list_concurrent.setPlaceholderText("请输入数字，如2")
            layout.addRow("虎扑评分任务:", self.hupu_score_list_concurrent)

        tab_widget.addTab(thread_config, "任务线程数")

    def start_maintain_task_thread(self):
        """启动守护线程 - 添加线程安全检查"""
        try:
            # 检查是否已经启动了守护线程
            existing_tasks = MAIN_TASK_MANAGER.get_all_tasks()
            for task_id, task_info in existing_tasks.items():
                if "maintain_task_thread" in task_id:
                    QMessageBox.warning(self, "启动失败", "守护线程已经在运行中，请勿重复启动", QMessageBox.Ok)
                    logger.warning(f"尝试重复启动守护线程，但线程已在运行: {task_id}")
                    return
            
            # 使用线程锁防止重复启动
            if not hasattr(self, '_maintain_thread_lock'):
                self._maintain_thread_lock = False
            
            if self._maintain_thread_lock:
                QMessageBox.warning(self, "启动失败", "正在启动守护线程，请稍候...", QMessageBox.Ok)
                return
            
            # 设置锁
            self._maintain_thread_lock = True
            
            # 启动守护线程
            maintain_task_thread_start_success = MAIN_TASK_MANAGER.add_task(
                task_id=f"maintain_task_thread",
                target_func=maintain_task_thread, **{},
                task_group="ikun",
                allow_duplicate=False
            )
            
            # 释放锁
            self._maintain_thread_lock = False
            
            if maintain_task_thread_start_success:
                # 启动成功：弹窗提示+日志记录
                QMessageBox.information(self, "启动成功", "守护重跑任务线程已成功启动！", QMessageBox.Ok)
                logger.info(f"启动守护重跑任务线程成功")
            else:
                # 启动失败：弹窗提示+日志记录
                QMessageBox.warning(self, "启动失败", "守护线程启动失败，请检查日志", QMessageBox.Ok)
                logger.error(f"启动守护重跑任务线程添加失败")
                
        except Exception as e:
            # 释放锁
            if hasattr(self, '_maintain_thread_lock'):
                self._maintain_thread_lock = False
            
            # 记录错误
            logger.error(f"启动守护线程时发生异常: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 显示错误信息
            QMessageBox.critical(self, "启动失败", f"启动守护线程时发生错误：{str(e)}", QMessageBox.Ok)

    def createSpiderConfigTab(self, tab_widget):
        """创建爬虫设置选项卡"""
        spider_config = QWidget()
        layout = QFormLayout(spider_config)
        layout.setSpacing(15)

        # 使用代理IP复选框
        self.spider_use_proxy = QCheckBox("使用代理IP")
        self.spider_use_proxy.setToolTip("勾选后，爬虫将使用代理IP进行请求")
        layout.addRow(self.spider_use_proxy)

        # 强制使用代理IP复选框
        self.spider_force_proxy = QCheckBox("强制使用代理IP（不使用本地IP）")
        self.spider_force_proxy.setToolTip("勾选后，只使用代理IP进行请求，即使代理失败也不会尝试本地IP")
        layout.addRow(self.spider_force_proxy)

        tab_widget.addTab(spider_config, "爬虫设置")

    def createTaskRunningConfigTab(self, tab_widget):
        """创建Temu任务配置选项卡"""
        thread_config = QWidget()
        layout = QFormLayout(thread_config)
        layout.setSpacing(15)
        # 关键：设置表单布局标签和内容均靠左对齐（全局统一，也可单独给h_layout2所在行设置）
        layout.setLabelAlignment(Qt.AlignLeft)
        layout.setFormAlignment(Qt.AlignLeft)

        # ========== 第一行：任务自动登录 + 优先复用Cookie登录 + 手动处理验证码 ==========
        first_row_layout = QHBoxLayout()
        first_row_layout.setAlignment(Qt.AlignLeft)
        first_row_layout.setSpacing(30)
        first_row_layout.setContentsMargins(0, 0, 0, 0)
        
        # 任务自动登录复选框
        self.task_auto_login = QCheckBox("任务自动登录")
        # 设置任务自动登录默认勾选
        self.task_auto_login.setChecked(True)
        first_row_layout.addWidget(self.task_auto_login)
        
        # 优先复用Cookie登录
        self.Settings_use_cookies = QCheckBox("优先复用Cookie登录")
        # 设置优先复用Cookie登录默认勾选
        self.Settings_use_cookies.setChecked(True)
        first_row_layout.addWidget(self.Settings_use_cookies)
        
        # 手动处理登录验证码
        self.handle_yzm_by_hand = QCheckBox("手动处理验证码")
        first_row_layout.addWidget(self.handle_yzm_by_hand)
        
        layout.addRow(first_row_layout)

        self.maintain_task_thread_space_time_lable = QLabel("守护任务线程提交任务间隔时间:")
        # 守护任务间隔时间
        self.maintain_task_thread_space_time = QLineEdit()
        self.maintain_task_thread_space_time.setMinimumWidth(100)
        self.maintain_task_thread_space_time.setPlaceholderText("单位秒，请输入数字，建议10以上，如30")

        # 创建横向布局：输入框 + 按钮
        h_layout = QHBoxLayout()
        h_layout.addWidget(self.maintain_task_thread_space_time_lable)
        h_layout.addWidget(self.maintain_task_thread_space_time)

        # 新增更新表结构按钮
        self.start_maintain_task_thread_btn = QPushButton("启动守护线程")
        self.start_maintain_task_thread_btn.setIcon(QIcon("gui/img/tijiao.png"))
        # self.start_maintain_task_thread_btn.setMinimumWidth(160)  # 设置按钮最小宽度
        # 绑定按钮点击事件：触发表更新并弹窗提示
        self.start_maintain_task_thread_btn.clicked.connect(self.start_maintain_task_thread)
        h_layout.addWidget(self.start_maintain_task_thread_btn)
        h_layout.setSpacing(20)  # 输入框与按钮间距

        # 将横向布局添加到表单布局，替代原有单独的输入框
        layout.addRow(h_layout)

        # 最大核价次数
        self.global_modify_times = QLineEdit()
        self.global_modify_times.setMinimumWidth(100)
        self.global_modify_times.setPlaceholderText("请输入整数，如10")
        layout.addRow("最大核价次数:", self.global_modify_times)

        # 核价重新申报降价金额
        self.global_minu_price = QLineEdit()
        self.global_minu_price.setMinimumWidth(100)
        self.global_minu_price.setPlaceholderText("请输入数字，如0.01")
        layout.addRow("核价重新申报降价金额:", self.global_minu_price)

        # JIT库存目标数量
        self.global_jit_final_num = QLineEdit()
        self.global_jit_final_num.setMinimumWidth(100)
        self.global_jit_final_num.setPlaceholderText("请输入整数，如500")
        layout.addRow("开通JIT库存设置:", self.global_jit_final_num)

        # =====================================
        # 优化后的h_layout2：全靠左、间距合理、结构整洁
        # =====================================
        h_layout2 = QHBoxLayout()
        # 1. 核心设置：布局内所有元素靠左对齐，无拉伸空白
        h_layout2.setAlignment(Qt.AlignLeft)
        # 2. 合理设置间距：元素间小间距，无多余空白（可根据需求调整）
        h_layout2.setSpacing(8)
        # 3. 移除布局默认边距（避免整体偏右）
        h_layout2.setContentsMargins(0, 0, 0, 0)

        # 标签：上传实拍图记录已跑过SPU
        label = QLabel("上传实拍图记录已跑过SPU:")
        # 关键：设置标签固定最小宽度（防止文字被挤压，与复选框对齐更规整）
        label.setMinimumWidth(180)
        h_layout2.addWidget(label)

        # 复选框：是否启动
        self.record_upload_pic_spu_list = QCheckBox()
        # 设置复选框默认勾选
        self.record_upload_pic_spu_list.setChecked(True)
        h_layout2.addWidget(self.record_upload_pic_spu_list)

        # 提示文字：已记录的SPU可在数据库右键店铺清空
        self.record_upload_pic_spu_tips = QLabel("已记录的SPU列表可在数据库右键店铺指定清空")
        # 优化：提示文字设为灰色（次要信息，视觉分层），可根据需求删除
        self.record_upload_pic_spu_tips.setStyleSheet("color: #666666; font-size: 12px;")
        # 提示文字自动收缩，不挤压前方元素
        self.record_upload_pic_spu_tips.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        h_layout2.addWidget(self.record_upload_pic_spu_tips)

        self.clear_spu_btn = QPushButton("清空记录SPU列表")
        self.clear_spu_btn.setIcon(QIcon("gui/img/qingli.png"))
        self.clear_spu_btn.clicked.connect(self.clear_upload_pic_spu_record)
        h_layout2.addWidget(self.clear_spu_btn)

        # 将优化后的h_layout2添加到表单布局
        layout.addRow(h_layout2)

        tab_widget.addTab(thread_config, "Temu任务配置")

    def clear_upload_pic_spu_record(self):
        """清空SPU记录（带确认弹窗）"""
        # 弹出确认对话框，提示用户确认删除
        reply = QMessageBox.question(
            self,  # 父窗口，弹窗相对主窗口居中
            "确认清空",  # 弹窗标题
            "确定要清空所有已记录的SPU数据吗？此操作不可恢复！",  # 提示内容
            QMessageBox.Yes | QMessageBox.No,  # 弹窗按钮：确定/取消
            QMessageBox.No  # 默认选中取消按钮，防止误操作
        )
        # 仅当用户点击「确定」时，才执行删除SQL
        if reply == QMessageBox.Yes:
            try:
                db.execute_sql("DELETE FROM record where 1")
                # 清空成功后，弹出提示框告知用户
                QMessageBox.information(self, "操作成功", "所有SPU记录已清空！")
            except Exception as e:
                QMessageBox.warning(self, "操作失败", f"清空SPU记录失败：{str(e)}")

    def createFinancialReportConfigTab(self, tab_widget):
        """创建财务报表设置选项卡"""
        financial_report_config = QWidget()
        layout = QFormLayout(financial_report_config)
        layout.setSpacing(15)
        layout.setLabelAlignment(Qt.AlignLeft)
        layout.setFormAlignment(Qt.AlignLeft)

        # 第一行：只显示标题label
        title_label = QLabel("财务报表成本列模糊匹配阈值设置（填写100则不执行模糊匹配）：")
        layout.addRow(title_label)

        # 第二行：横向排列三个label+输入框
        h_layout = QHBoxLayout()
        h_layout.setSpacing(20)

        # SKU阈值
        sku_label = QLabel("SKU匹配阈值:")
        self.sku_threshold = QLineEdit()
        self.sku_threshold.setMinimumWidth(100)
        self.sku_threshold.setPlaceholderText("请输入数字，如95")
        sku_layout = QHBoxLayout()
        sku_layout.setSpacing(8)
        sku_layout.addWidget(sku_label)
        sku_layout.addWidget(self.sku_threshold)
        h_layout.addLayout(sku_layout, 1)

        # 工厂阈值
        factory_label = QLabel("厂家匹配阈值:")
        self.factory_threshold = QLineEdit()
        self.factory_threshold.setMinimumWidth(100)
        self.factory_threshold.setPlaceholderText("请输入数字，如95")
        factory_layout = QHBoxLayout()
        factory_layout.setSpacing(8)
        factory_layout.addWidget(factory_label)
        factory_layout.addWidget(self.factory_threshold)
        h_layout.addLayout(factory_layout, 1)

        # 总阈值
        total_label = QLabel("综合阈值:")
        self.total_threshold = QLineEdit()
        self.total_threshold.setMinimumWidth(100)
        self.total_threshold.setPlaceholderText("请输入数字，如95")
        total_layout = QHBoxLayout()
        total_layout.setSpacing(8)
        total_layout.addWidget(total_label)
        total_layout.addWidget(self.total_threshold)
        h_layout.addLayout(total_layout, 1)

        layout.addRow(h_layout)

        tab_widget.addTab(financial_report_config, "财务报表设置")

    def openMusicFormatTool(self):
        """打开音乐格式转化工具网页 - 添加线程安全检查"""
        # 使用线程锁防止重复点击
        if not hasattr(self, '_music_tool_lock'):
            self._music_tool_lock = False
        
        if self._music_tool_lock:
            return  # 如果正在处理，直接返回
        
        try:
            # 设置锁
            self._music_tool_lock = True
            
            url = "https://link.hhtjim.com/"
            
            # 优先使用系统默认浏览器在新标签页打开
            success = webbrowser.open_new_tab(url)
            
            if not success:
                # 兼容处理（针对部分系统 webbrowser 可能返回 False 的情况）
                os_type = platform.system()
                if os_type == "Windows":
                    import os
                    os.startfile(url)  # Windows 专属方式
                elif os_type == "Darwin":  # macOS
                    import subprocess
                    subprocess.run(["open", url], check=True, capture_output=True)
                elif os_type == "Linux":  # Linux
                    import subprocess
                    subprocess.run(["xdg-open", url], check=True, capture_output=True)
            
            # 显示成功消息
            QMessageBox.information(self, "打开成功", "音乐格式转化工具已在新标签页中打开", QMessageBox.Ok)
            
        except Exception as e:
            # 记录错误
            logger.error(f"打开音乐格式转化工具时发生异常: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # 显示错误信息
            QMessageBox.warning(self, "打开网页失败", f"无法打开音乐格式转化工具：{str(e)}")
        finally:
            # 释放锁
            self._music_tool_lock = False
    
    def open_error_log_file(self):
        """打开error/error.log文件"""
        try:
            # 构建error.log文件路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            error_log_path = os.path.join(project_root, "error", "error.log")
            
            # 检查文件是否存在
            if not os.path.exists(error_log_path):
                QMessageBox.warning(self, "文件不存在", f"错误日志文件不存在：\n{error_log_path}")
                return
            
            # 打开文件
            os_type = platform.system()
            if os_type == "Windows":
                os.startfile(error_log_path)  # Windows专属方式
            elif os_type == "Darwin":  # macOS
                subprocess.run(["open", error_log_path], check=True)
            elif os_type == "Linux":  # Linux
                subprocess.run(["xdg-open", error_log_path], check=True)
            
            logger.info(f"已打开错误日志文件：{error_log_path}")
            
        except Exception as e:
            logger.error(f"打开错误日志文件失败：{str(e)}")
            QMessageBox.warning(self, "打开失败", f"无法打开错误日志文件：{str(e)}")


def main():
    """主函数"""
    app = QApplication(sys.argv)

    # 设置全局字体
    font = QFont("Microsoft YaHei", 12)
    app.setFont(font)

    # 异常捕获，避免崩溃
    sys.excepthook = lambda exctype, value, tb: QMessageBox.critical(
        None, "程序崩溃",
        f"发生未处理的异常：\n{exctype.__name__}: {value}\n{''.join(traceback.format_tb(tb))}"
    )

    # 创建并显示窗口
    setting_window = SettingWindow()
    setting_window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()