import os
from PyQt5.QtCore import QFile, QTextStream


class QSSLoader:
    """QSS样式加载器"""
    
    @staticmethod
    def load_qss(qss_file_path):
        """加载QSS文件"""
        if not os.path.exists(qss_file_path):
            return ""
        
        qss_file = QFile(qss_file_path)
        qss_file.open(QFile.ReadOnly | QFile.Text)
        qss_content = QTextStream(qss_file).readAll()
        qss_file.close()
        
        # PyQt5的QTextStream.readAll()返回的是字符串，不需要解码
        if isinstance(qss_content, bytes):
            return qss_content.decode('utf-8')
        else:
            return qss_content
    
    @staticmethod
    def load_table_style():
        """加载表格样式"""
        qss_path = os.path.join(os.path.dirname(__file__), 'table.qss')
        return QSSLoader.load_qss(qss_path)
    
    @staticmethod
    def load_button_style():
        """加载按钮样式"""
        qss_path = os.path.join(os.path.dirname(__file__), 'button.qss')
        return QSSLoader.load_qss(qss_path)
    
    @staticmethod
    def load_input_style():
        """加载输入框样式"""
        qss_path = os.path.join(os.path.dirname(__file__), 'input.qss')
        return QSSLoader.load_qss(qss_path)
    
    @staticmethod
    def load_common_style():
        """加载通用样式"""
        qss_path = os.path.join(os.path.dirname(__file__), 'common.qss')
        return QSSLoader.load_qss(qss_path)
    
    @staticmethod
    def load_all_styles():
        """加载所有样式"""
        styles = []
        styles.append(QSSLoader.load_table_style())
        styles.append(QSSLoader.load_button_style())
        styles.append(QSSLoader.load_input_style())
        styles.append(QSSLoader.load_common_style())
        return '\n'.join(styles)