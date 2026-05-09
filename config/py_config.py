import datetime
import os


def ensure_config_file_exists():
    """
    确保配置文件存在，如果不存在则生成默认配置。
    在 ConfigValue 初始化前调用。
    """
    config_dir = "./配置文件_系统配置"
    config_file_path = f"{config_dir}/py_config_value.txt"

    # 确保配置目录存在
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
        print(f"✅ 创建配置目录: {config_dir}")

    # 默认配置内容
    default_config = """# 系统配置文件
    # py_config_value.txt 文件路径（自身路径，用于参考）
    py_config_value_path = 配置文件_系统配置/py_config_value.txt
    
    # 代理配置文件路径
    proxy_file_path = 配置文件_系统配置/proxy.txt
    
    # API代理配置文件路径
    api_proxy_file_path = 配置文件_系统配置/api_proxy.txt
    
    # API代理端口
    api_proxy_port = 7899
    """

    # 如果配置文件不存在，创建默认配置
    if not os.path.exists(config_file_path):
        try:
            with open(config_file_path, 'w', encoding='utf-8') as f:
                f.write(default_config)
            print(f"✅ 创建默认配置文件: {config_file_path}")
        except Exception as e:
            print(f"❌ 创建配置文件失败: {e}")


# 在模块加载时确保配置文件存在
ensure_config_file_exists()


class ConfigValue:
    """配置文件处理类"""

    def __init__(self):
        """
        初始化配置值。
        所有需要从文件读取的配置项都在这里处理。
        """
        # --- 从配置文件动态读取的属性 ---
        # 1. API代理配置
        self.api_proxy_port = extract_data('api_proxy_port')
        self.api_proxy_url = f"http://127.0.0.1:{self.api_proxy_port}" if self.api_proxy_port else None

        # 2. 其他文件路径配置 (新增)
        self.login_data_path = "config/login_data.dat"

        self.proxy_file_path = extract_data('proxy_file_path')
        self.api_proxy_file_path = extract_data('api_proxy_file_path')

        # --- 硬编码的静态属性 ---
        self.server_api_domain = "https://这里填写你的卡密系统接口地址" # 如果没有就在启动入口取消打包模式，选择免密模式进行打包
        self.static_token = "unoass"
        self.prefix_token = "unoass"
        self.current_version = "v20260508"
        self.app_info = "内测版本，有问题及时反馈。"
        self.contribution_usdt_address = "TX4Jiw8zvHU6AA3YyczHTKUTUtr76sbjbx"
        # py_config_value_path 值在 extract_data 函数

def extract_data(key):
    """
    从配置文件中提取指定键的值，返回原始字符串。
    不进行任何类型转换，不引用外部变量。
    """
    # 确保文件路径正确
    py_config_value_path = "./配置文件_系统配置/py_config_value.txt"
    try:
        with open(py_config_value_path, 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()
                # 跳过空行和注释行
                if not line or line.startswith('#'):
                    continue
                # 查找以目标键开头的行
                if line.startswith(key):
                    # 分割键和值，只分割一次
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        # 返回值部分，并去除前后空白
                        return parts[1].strip()
        # 如果遍历完文件都未找到键，返回 None
        return None
    except FileNotFoundError:
        print(f"错误：配置文件 '{py_config_value_path}' 不存在，请检查路径。")
        return None
    except Exception as e:
        # 捕获其他所有异常，并打印详细信息
        print(f"处理配置文件时出错：{str(e)}")
        return None


def generate_version_number(prefix: str = "v") -> str:
    """
    自动获取当前日期并生成版本号（格式：前缀 + YYYYMMDD）
    例如：2026年1月19日 → v20260119

    参数：
    prefix (str): 版本号前缀，默认是"v"，可自定义（如空字符串、"V"、"version-"等）

    返回：
    str: 生成的版本号字符串
    """
    # 获取当前本地日期（也可改用 UTC 日期：datetime.datetime.utcnow()）
    today = datetime.datetime.now()
    # 格式化日期为 YYYYMMDD（补零，如1月→01，9日→09）
    date_str = today.strftime("%Y%m%d")
    # 拼接前缀和日期
    version = f"{prefix}{date_str}"
    return version


# 创建一个全局的配置对象，方便其他模块直接导入使用
config_value = ConfigValue()

# 使用示例
if __name__ == "__main__":
    # 直接使用全局实例 config_value
    print(f"API 端口: {config_value.api_proxy_port}")
    print(f"API 地址: {config_value.api_proxy_url}")
    print(f"登录数据路径: {config_value.login_data_path}")
