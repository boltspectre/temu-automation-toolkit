# change_upload_pic_index.py（修改后）
import os
import sys
import traceback
from datetime import datetime

from PyQt5.QtGui import QIcon, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QLabel, QMessageBox
)
from soupsieve.util import lower

import json
# 导入你的模块
from lite_modules.change_upload_pic_xy import change_upload_pic_main
from lite_modules.photo_looker import show_image

class ConfigWindow(QWidget):  # 保持继承QWidget，作为可嵌入组件
    def __init__(self, parent=None):  # 增加parent参数，支持嵌入父组件
        super().__init__(parent)  # 传递parent，避免独立窗口
        self.json_file = "./配置文件_实拍图配置/sku.json"
        self.current_sku_data = None
        self.init_ui()

    def init_ui(self):
        # 移除独立窗口的setGeometry/setWindowTitle（由父组件控制）
        # 只保留核心布局和控件初始化
        main_layout = QVBoxLayout(self)  # 直接设置当前组件的布局

        # === 原有输入行 ===
        label_name_layout = QHBoxLayout()
        label_name_label = QLabel("店铺缩写:")
        self.label_name_input = QLineEdit()
        self.label_name_input.setPlaceholderText("输入之后自动加载对应参数")
        self.label_name_input.textChanged.connect(self.on_label_name_changed)
        label_name_layout.addWidget(label_name_label)
        label_name_layout.addWidget(self.label_name_input)
        main_layout.addLayout(label_name_layout)

        product_id_layout = QHBoxLayout()
        product_id_label = QLabel("保存的文件名:")
        self.product_id_input = QLineEdit("SPU123456")
        product_id_layout.addWidget(product_id_label)
        product_id_layout.addWidget(self.product_id_input)
        main_layout.addLayout(product_id_layout)

        product_skc_layout = QHBoxLayout()
        product_skc_label = QLabel("SKCID:")
        self.product_skc_input = QLineEdit("9509672190")
        product_skc_layout.addWidget(product_skc_label)
        product_skc_layout.addWidget(self.product_skc_input)
        main_layout.addLayout(product_skc_layout)

        # === 坐标与字体输入 ===
        self.x_input = QLineEdit()
        self.y_input = QLineEdit()
        self.font_size_input = QLineEdit()

        x_layout = QHBoxLayout()
        x_layout.addWidget(QLabel("X 坐标:"))
        x_layout.addWidget(self.x_input)
        main_layout.addLayout(x_layout)

        y_layout = QHBoxLayout()
        y_layout.addWidget(QLabel("Y 坐标:"))
        y_layout.addWidget(self.y_input)
        main_layout.addLayout(y_layout)

        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel("字体大小:"))
        font_layout.addWidget(self.font_size_input)
        main_layout.addLayout(font_layout)

        # 按钮
        button_layout = QHBoxLayout()
        self.save_button = QPushButton("保存")
        # 修正图标路径（适配ToolsPage的目录结构）
        self.save_button.setIcon(QIcon("gui/img/baochun.png"))
        self.start_button = QPushButton("启动")
        self.start_button.setIcon(QIcon("gui/img/tijiao.png"))
        # self.save_button.setFixedWidth(80)
        # self.start_button.setFixedWidth(80)
        self.save_button.clicked.connect(self.save_to_file)
        self.start_button.clicked.connect(self.start_operation)
        button_layout.addStretch()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.start_button)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        # 添加强制拉伸，适配父组件
        main_layout.addStretch()

        self.on_label_name_changed(self.label_name_input.text())

    # 以下所有方法（load_json_data、save_json_data、on_label_name_changed等）完全保留，无需修改
    def load_json_data(self):
        if not os.path.exists(self.json_file):
            QMessageBox.critical(self, "错误", f"配置文件不存在: {self.json_file}")
            return None
        try:
            with open(self.json_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"读取 JSON 失败: {str(e)}")
            return None

    def save_json_data(self, data):
        try:
            with open(self.json_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存 JSON 失败: {str(e)}")
            return False

    def on_label_name_changed(self, text):
        try:
            text = text.strip()
            if not text:
                self.clear_position_inputs()
                self.current_sku_data = None
                return

            data = self.load_json_data()
            if not data:
                return

            matched = None
            for sku in data["skus"]:
                if lower(sku["name"]) == lower(text):
                    matched = sku
                    break

            if matched:
                self.x_input.setText(str(matched["positionX"]))
                self.y_input.setText(str(matched["positionY"]))
                self.font_size_input.setText(str(matched["font_size"]))
                self.current_sku_data = matched
        except Exception as e:
            QMessageBox.critical(self, "内部错误", f"加载配置失败: {str(e)}")
            traceback.print_exc()

    def clear_position_inputs(self):
        self.x_input.clear()
        self.y_input.clear()
        self.font_size_input.clear()

    def save_to_file(self):
        try:
            label_name = self.label_name_input.text().strip()
            if not label_name:
                QMessageBox.warning(self, "警告", "请先输入有效的店铺缩写！")
                return

            x = int(self.x_input.text())
            y = int(self.y_input.text())
            font_size = int(self.font_size_input.text())

            data = self.load_json_data()
            if not data or "skus" not in data:
                return

            found = False
            for sku in data["skus"]:
                if lower(sku["name"]) == lower(label_name):
                    sku["positionX"] = x
                    sku["positionY"] = y
                    sku["font_size"] = font_size
                    found = True
                    break

            if not found:
                QMessageBox.warning(self, "警告", f"未找到店铺缩写 '{label_name}'，无法保存！")
                return

            if self.save_json_data(data):
                QMessageBox.information(self, "成功", f"坐标已更新并保存到 {self.json_file}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"错误: {str(e)}")
            traceback.print_exc()

    def start_operation(self):
        try:
            label_name = self.label_name_input.text().strip()
            product_id = self.product_id_input.text().strip()
            product_skc_id = self.product_skc_input.text().strip()

            if not label_name:
                QMessageBox.warning(self, "警告", "请先输入店铺缩写！")
                return

            x = int(self.x_input.text())
            y = int(self.y_input.text())
            font_size = int(self.font_size_input.text())

            json_data = {
                "skus": [{
                    "id": 1,
                    "name": label_name,
                    "descId": 1,
                    "positionX": x,
                    "positionY": y,
                    "font_size": font_size
                }],
                "skuDescList": [{
                    "id": 1,
                    "oumentRepList": [{"rep_name": "123 123 SL"}],
                    "makerRepList": [{"rep_name": "123123 123 Cross-Border E-Commerce Co.,Ltd"}]
                }]
            }

            success, output_path = change_upload_pic_main(label_name, product_id, product_skc_id, json_data)
            if not success:
                QMessageBox.critical(self, "操作失败", str(output_path))
                return
            if output_path:
                show_image(output_path)
        except Exception as e:
            error_msg = f"启动操作失败: {str(e)}"
            QMessageBox.critical(self, "错误", error_msg)
            traceback.print_exc()

# ====== 保留独立运行的入口（不影响原有功能）======
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # 创建error文件夹
    error_dir = "../error"
    if not os.path.exists(error_dir):
        os.makedirs(error_dir)

    log_file = os.path.join(error_dir, "error.log")
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] Unhandled exception:\n{error_msg}\n{'-' * 60}\n")

    QMessageBox.critical(None, "程序发生错误", f"发生未处理异常，请查看 error.log 文件。\n\n{str(exc_value)}")

sys.excepthook = handle_exception

if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    font = QFont("Microsoft YaHei", 12)
    app.setFont(font)

    window = ConfigWindow()
    window.setWindowTitle("Ikun标记坐标测试-免费FREE")
    window.setGeometry(700, 400, 500, 300)
    window.setWindowIcon(QIcon("img/favicon.ico"))
    window.show()
    sys.exit(app.exec_())