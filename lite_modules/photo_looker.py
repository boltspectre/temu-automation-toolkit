import sys

from PIL import Image
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget, QMessageBox


class ImageViewer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon("gui/img/favicon.ico"))
        self.initUI()

    def initUI(self):
        self.setWindowTitle('测试成功！图片已打开！')
        self.setGeometry(150, 60, 1400, 900)  # 增加窗口初始大小

        # 创建布局和组件
        layout = QVBoxLayout()

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label)

        self.setLayout(layout)

    def open_image(self, image_path):
        """根据给定路径打开并显示图片"""
        try:
            # 使用PIL检查图片有效性
            with Image.open(image_path) as img:
                img.verify()  # 验证图片完整性

            # 使用QPixmap加载图片
            pixmap = QPixmap(image_path)

            # 设定目标宽度为800像素，保持原始比例
            target_width = 1500
            scaled_pixmap = pixmap.scaled(target_width,
                                          int(target_width * pixmap.height() / pixmap.width()),
                                          aspectRatioMode=Qt.KeepAspectRatio,
                                          transformMode=Qt.SmoothTransformation)

            self.image_label.setPixmap(scaled_pixmap)
            self.image_label.adjustSize()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开图片: {str(e)}")


def show_image(image_path):
    """用于打开或更新图片的函数"""
    if hasattr(show_image, 'viewer') and show_image.viewer.isVisible():
        show_image.viewer.open_image(image_path)
    else:
        show_image.viewer = ImageViewer()
        show_image.viewer.open_image(image_path)
        show_image.viewer.show()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # 示例：直接调用show_image函数来测试
    test_image_path = r"/PS后/PS后_M/SPU123456.png"
    show_image(test_image_path)

    sys.exit(app.exec_())