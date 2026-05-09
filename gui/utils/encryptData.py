# 安全配置 - 与服务器保持一致
import base64
import hashlib
import hmac

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

SECRET_KEY = 'uno_yyds_wzry_sgs_ljyx'  # 共享密钥，用于签名和加密
ENCRYPTION_IV = b'1234567890123456'  # 加密向量，16字节
TIMESTAMP_VALID_WINDOW = 300  # 时间戳有效窗口（秒）

class CryptoUtils:
    """加密解密工具类"""

    @staticmethod
    def encrypt_data(data):
        """加密数据"""
        key = hashlib.sha256(SECRET_KEY.encode()).digest()
        cipher = AES.new(key, AES.MODE_CBC, ENCRYPTION_IV)
        encrypted_data = cipher.encrypt(pad(data.encode('utf-8'), AES.block_size))
        return base64.b64encode(encrypted_data).decode('utf-8')

    @staticmethod
    def decrypt_data(encrypted_data):
        """解密数据"""
        key = hashlib.sha256(SECRET_KEY.encode()).digest()
        cipher = AES.new(key, AES.MODE_CBC, ENCRYPTION_IV)
        decrypted_data = unpad(cipher.decrypt(base64.b64decode(encrypted_data)), AES.block_size)
        return decrypted_data.decode('utf-8')

    @staticmethod
    def generate_signature(kami, timestamp):
        """生成签名"""
        data = f"{kami}{timestamp}".encode('utf-8')
        signature = hmac.new(SECRET_KEY.encode(), data, hashlib.sha256).hexdigest()
        return signature