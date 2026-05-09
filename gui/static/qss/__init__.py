"""
QSS样式模块初始化
"""

from .qss_loader import QSSLoader

# 导出所有样式加载函数
__all__ = [
    'QSSLoader',
    'load_table_style',
    'load_button_style',
    'load_input_style',
    'load_common_style',
    'load_all_styles'
]

# 提供快捷函数
load_table_style = QSSLoader.load_table_style
load_button_style = QSSLoader.load_button_style
load_input_style = QSSLoader.load_input_style
load_common_style = QSSLoader.load_common_style
load_all_styles = QSSLoader.load_all_styles