# spider_modules/spider_config.py
"""爬虫配置管理模块"""

from loguru import logger
from config.common_config import config_manager


def get_spider_proxy_config():
    """获取爬虫代理配置
    
    Returns:
        dict: 包含代理配置的字典
            - use_proxy: 是否使用代理
            - force_proxy: 是否强制使用代理
    """
    try:
        use_proxy_value = config_manager.get_or_set_config(
            "spider_use_proxy",
            "否"  # 默认不使用代理
        )
        force_proxy_value = config_manager.get_or_set_config(
            "spider_force_proxy",
            "否"  # 默认不强制使用代理
        )
        
        config = {
            "use_proxy": use_proxy_value == "是",
            "force_proxy": force_proxy_value == "是"
        }
        
        logger.info(f"爬虫代理配置: use_proxy={config['use_proxy']}, force_proxy={config['force_proxy']}")
        return config
        
    except Exception as e:
        logger.error(f"获取爬虫代理配置失败: {e}")
        return {
            "use_proxy": False,
            "force_proxy": False
        }