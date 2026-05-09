import base64
import hashlib
import json
import os
import sys

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from config.py_config import config_value


class LoginDataEncryptor:
    """登录数据加密解密工具类"""

    # 加密配置 - 应与服务器端保持一致
    _SECRET_KEY = hashlib.sha256("uno_yyds_wzry_sgs_ljyx".encode()).digest()
    _IV = b"1234567890123456"  # 16字节IV向量

    def __init__(self):
        self.login_data_path = f"{config_value.login_data_path}"

        # 确保配置目录存在
        if not os.path.exists("config"):
            os.makedirs("config")

    def encrypt(self, data: dict) -> str:
        """加密字典数据"""
        try:
            # 将字典转换为JSON字符串
            json_str = json.dumps(data)
            # 初始化AES加密器
            cipher = AES.new(self._SECRET_KEY, AES.MODE_CBC, self._IV)
            # 加密并进行Base64编码
            encrypted_data = cipher.encrypt(pad(json_str.encode('utf-8'), AES.block_size))
            return base64.b64encode(encrypted_data).decode('utf-8')
        except Exception as e:
            print(f"加密失败: {str(e)}")
            return ""

    def decrypt(self, encrypted_str: str) -> dict:
        """解密为字典数据"""
        try:
            if not encrypted_str:
                return {}

            # 解码Base64并解密
            encrypted_data = base64.b64decode(encrypted_str.encode('utf-8'))
            cipher = AES.new(self._SECRET_KEY, AES.MODE_CBC, self._IV)
            decrypted_data = unpad(cipher.decrypt(encrypted_data), AES.block_size)

            # 将JSON字符串转换为字典
            return json.loads(decrypted_data.decode('utf-8'))
        except Exception as e:
            print(f"解密失败: {str(e)}")
            return {}

    def save_login_data(self, data: dict) -> bool:
        """保存登录数据到文件"""
        try:
            encrypted_data = self.encrypt(data)
            with open(self.login_data_path, 'w', encoding='utf-8') as f:
                f.write(encrypted_data)
            return True
        except Exception as e:
            print(f"保存登录数据失败: {str(e)}")
            return False

    def load_login_data(self) -> dict:
        """加载并解密登录数据，确保返回字典类型"""
        try:
            if not os.path.exists(self.login_data_path):
                return {}

            with open(self.login_data_path, 'r', encoding='utf-8') as f:
                encrypted_data = f.read().strip()

            # 解密数据，如果解密失败返回空字典
            decrypted_data = self.decrypt(encrypted_data)

            # 确保返回的是字典类型
            if not isinstance(decrypted_data, dict):
                return {}

            return decrypted_data
        except Exception as e:
            print(f"加载登录数据失败: {str(e)}")
            return {}  # 始终返回字典，即使出错

def main():
    # --------------------------
    # 1. 初始化加密器并打印基础信息
    # --------------------------
    print("=" * 60)
    print("         LoginDataEncryptor 功能测试")
    print("=" * 60)
    try:
        encryptor = LoginDataEncryptor()
        print(f"✅ 加密器初始化成功")
        print(f"📂 登录数据存储路径：{os.path.abspath(encryptor.login_data_path)}")
        print(f"🔑 加密算法：AES-256-CBC（密钥长度：{len(encryptor._SECRET_KEY)}字节，IV长度：{len(encryptor._IV)}字节）")
    except Exception as e:
        print(f"❌ 加密器初始化失败：{str(e)}")
        sys.exit(1)  # 初始化失败直接退出测试

    # --------------------------
    # 2. 模拟真实登录响应数据（与项目实际场景一致）
    # --------------------------
    print("\n" + "-" * 60)
    print("📥 模拟登录成功后的响应数据（respdata）")
    print("-" * 60)
    # 模拟服务器返回的完整登录响应（包含code、msg、data字段，与登录页逻辑一致）
    mock_login_resp = {
        "code": 1,  # 1表示登录成功
        "msg": "验证成功",
        "data": {  # 核心用户数据（需加密存储）
            "kami": "IKUN_2024_VIP_8888",  # 卡密
            "user_id": "ikun_10086",  # 用户ID
            "expire_time": "2025-12-31 23:59:59",  # 有效期
            "ddos": "True",  # 工具箱权限标识
            "vip_level": "SVIP",  # VIP等级（扩展字段）
            "login_time": "2024-08-26 15:30:45"  # 登录时间
        }
    }
    print(f"原始响应数据：{json.dumps(mock_login_resp, ensure_ascii=False, indent=2)}")
    print(f"数据类型：{type(mock_login_resp)}")

    # --------------------------
    # 3. 加密并保存登录数据
    # --------------------------
    print("\n" + "-" * 60)
    print("🔒 加密并保存登录数据")
    print("-" * 60)
    save_result = encryptor.save_login_data(mock_login_resp)
    if save_result:
        print(f"✅ 登录数据保存成功")
        # 读取保存的加密文件内容（验证文件是否正常写入）
        with open(encryptor.login_data_path, "r", encoding="utf-8") as f:
            encrypted_content = f.read()
        print(f"加密后的数据（前50字符）：{encrypted_content[:50]}...")
        print(f"加密数据长度：{len(encrypted_content)} 字符")
    else:
        print(f"❌ 登录数据保存失败")
        sys.exit(1)

    # --------------------------
    # 4. 加载并解密登录数据
    # --------------------------
    print("\n" + "-" * 60)
    print("🔓 加载并解密登录数据")
    print("-" * 60)
    loaded_data = encryptor.load_login_data()
    if loaded_data:
        print(f"✅ 数据加载解密成功")
        print(f"解密后的数据：{json.dumps(loaded_data, ensure_ascii=False, indent=2)}")
        print(f"解密数据类型：{type(loaded_data)}")
    else:
        print(f"❌ 数据加载解密失败（返回空字典）")
        sys.exit(1)

    # --------------------------
    # 5. 验证数据一致性（核心测试）
    # --------------------------
    print("\n" + "-" * 60)
    print("✅ 验证解密数据与原始数据一致性")
    print("-" * 60)
    # 对比解密后的数据与原始模拟数据
    if loaded_data == mock_login_resp:
        print(f"✅ 数据一致性验证通过！解密数据与原始数据完全一致")
        # 额外验证关键字段（如卡密、权限标识）
        key_fields = ["kami", "ddos", "expire_time"]
        for field in key_fields:
            if field in loaded_data["data"]:
                print(f"  ✅ 关键字段[{field}]：{loaded_data['data'][field]}")
            else:
                print(f"  ⚠️  关键字段[{field}]缺失")
    else:
        print(f"❌ 数据一致性验证失败！")
        print(f"  原始数据关键字段：{mock_login_resp['data'].keys()}")
        print(f"  解密数据关键字段：{loaded_data.get('data', {}).keys()}")

    # --------------------------
    # 6. 测试异常场景（增强鲁棒性验证）
    # --------------------------
    print("\n" + "-" * 60)
    print("⚠️  异常场景测试（验证容错能力）")
    print("-" * 60)
    # 场景1：加密空字典
    empty_data = {}
    empty_encrypted = encryptor.encrypt(empty_data)
    print(f"  场景1-加密空字典：{'成功' if empty_encrypted else '失败'}（加密结果：{empty_encrypted[:30]}...）")

    # 场景2：解密无效字符串（模拟损坏的缓存文件）
    invalid_str = "this_is_invalid_encrypted_data_123456"
    invalid_decrypted = encryptor.decrypt(invalid_str)
    print(f"  场景2-解密无效字符串：返回类型{type(invalid_decrypted)}（结果：{invalid_decrypted}）")

    # 场景3：加载不存在的文件（模拟首次登录无缓存）
    temp_path = os.path.join("config", "non_exist.dat")
    original_path = encryptor.login_data_path
    encryptor.login_data_path = temp_path  # 临时修改路径
    non_exist_data = encryptor.load_login_data()
    encryptor.login_data_path = original_path  # 恢复原路径
    print(f"  场景3-加载不存在的文件：返回类型{type(non_exist_data)}（结果：{non_exist_data}）")

    # --------------------------
    # 7. 清理测试文件（可选，避免残留）
    # --------------------------
    print("\n" + "-" * 60)
    print("🧹 测试清理")
    print("-" * 60)
    clean_choice = input("是否删除测试生成的登录数据文件？(y/n)：").strip().lower()
    if clean_choice == "y":
        if os.path.exists(encryptor.login_data_path):
            os.remove(encryptor.login_data_path)
            print(f"✅ 已删除测试文件：{os.path.abspath(encryptor.login_data_path)}")
        else:
            print(f"ℹ️  测试文件不存在，无需删除")
    else:
        print(f"ℹ️  保留测试文件：{os.path.abspath(encryptor.login_data_path)}")

    print("\n" + "=" * 60)
    print("🎉 所有测试流程执行完成")
    print("=" * 60)


if __name__ == "__main__":
    # 初始化加密器
    encryptor = LoginDataEncryptor()
    print("加密器初始化完成\n")

    # 测试数据
    test_data = {
        "kami": "TEST_123456",
        "ddos": "True",
        "expire": "2025-01-01"
    }
    print(f"原始数据: {test_data}")

    # 加密
    encrypted = encryptor.encrypt(test_data)
    print(f"加密后: {encrypted[:100]}...")  # 只显示前50字符

    encrypted = "1oG9PhsQXLxizFbR3QEikDDPtbABhsE8onIe9OREnF24Wkya0gpr8/DvYsiKbMRFyYkYKZP+sjRJlLyMAfENGimgRkSSUaEOX/d40RmlTD+i82vtVypMh0rcio+RRKvQXidkKYPZWQaEqzRuAACoG6QPCazBtL7vVyzETooHHxLft5IcSCfU+Dl/9cabxskbgrt7uHhd2rw27t4c+iqb1eWofbLsXhc+Hl+406EriWg/iKmvSycy9TX56ERV4j17GxXu9VvPgHRBqd14hnVXJw=="
    # 解密
    decrypted = encryptor.decrypt(encrypted)
    print(f"解密后: {decrypted}")

    # 验证结果
    print("\n验证结果:", "成功" if decrypted == test_data else "失败")

    # 文件存储测试
    if encryptor.save_login_data(test_data):
        loaded = encryptor.load_login_data()
        print("文件存储验证:", "成功" if loaded == test_data else "失败")
