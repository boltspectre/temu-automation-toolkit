import base64
import hashlib
import hmac
import json
import os
import secrets
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from loguru import logger


class KamiEncryptionError(Exception):
    """Custom exception for kami encryption errors"""
    pass


class KamiEncryptor:
    """
    卡密加密工具类
    基于卡密的加密实现，确保：
    1. 不同卡密产生不同的加密输出
    2. 加密过程不可逆（不知道卡密无法解密）
    3. 每个唯一卡密生成唯一的加密密钥
    """

    _GLOBAL_SALT = b"ikun_alliance_2024_salt_v1"

    def __init__(self, kami: str = None):
        """
        初始化加密器

        Args:
            kami: 卡密字符串，用于派生密钥。如果为None，则使用全局密钥。
        """
        self.kami = kami
        self._derived_key = self._derive_key(kami) if kami else self._get_global_key()

    def _get_global_key(self) -> bytes:
        """获取全局默认密钥（用于兼容旧数据）"""
        return hashlib.sha256(self._GLOBAL_SALT).digest()

    def _derive_key(self, kami: str) -> bytes:
        """
        从卡密派生唯一的加密密钥

        使用 PBKDF2 风格的密钥派生：
        key = SHA256(kami + salt)
        每个不同的 kami 都会产生完全不同的密钥

        Args:
            kami: 卡密字符串

        Returns:
            派生的32字节密钥
        """
        if not kami:
            raise KamiEncryptionError("卡密不能为空")

        combined = kami.encode('utf-8') + self._GLOBAL_SALT
        return hashlib.sha256(combined).digest()

    def _get_iv(self) -> bytes:
        """
        生成随机IV向量

        Returns:
            16字节随机IV
        """
        return secrets.token_bytes(16)

    def encrypt(self, data: dict) -> str:
        """
        加密数据

        使用格式：base64(IV + encrypted_data)
        IV被包含在加密数据中，以便解密时使用

        Args:
            data: 要加密的字典数据

        Returns:
            加密后的Base64字符串

        Raises:
            KamiEncryptionError: 加密失败时抛出
        """
        try:
            if not isinstance(data, dict):
                raise KamiEncryptionError("数据必须是字典类型")

            json_str = json.dumps(data, ensure_ascii=False)
            iv = self._get_iv()
            cipher = AES.new(self._derived_key, AES.MODE_CBC, iv)

            encrypted = cipher.encrypt(pad(json_str.encode('utf-8'), AES.block_size))

            result = base64.b64encode(iv + encrypted).decode('utf-8')
            return result

        except Exception as e:
            logger.error(f"加密失败: {str(e)}")
            raise KamiEncryptionError(f"加密失败: {str(e)}")

    def decrypt(self, encrypted_str: str) -> dict:
        """
        解密数据

        Args:
            encrypted_str: 加密后的Base64字符串

        Returns:
            解密后的字典数据

        Raises:
            KamiEncryptionError: 解密失败时抛出
        """
        try:
            if not encrypted_str:
                raise KamiEncryptionError("加密字符串不能为空")

            encrypted_data = base64.b64decode(encrypted_str.encode('utf-8'))

            iv = encrypted_data[:16]
            ciphertext = encrypted_data[16:]

            cipher = AES.new(self._derived_key, AES.MODE_CBC, iv)
            decrypted = unpad(cipher.decrypt(ciphertext), AES.block_size)

            return json.loads(decrypted.decode('utf-8'))

        except Exception as e:
            logger.error(f"解密失败: {str(e)}")
            raise KamiEncryptionError(f"解密失败，可能是卡密错误: {str(e)}")

    @staticmethod
    def verify_kami(kami: str, encrypted_str: str) -> bool:
        """
        验证卡密是否正确

        Args:
            kami: 要验证的卡密
            encrypted_str: 加密数据

        Returns:
            卡密是否正确
        """
        try:
            test_encryptor = KamiEncryptor(kami)
            test_encryptor.decrypt(encrypted_str)
            return True
        except:
            return False

    @staticmethod
    def generate_unbind_token(kami: str, timestamp: int = None) -> str:
        """
        生成解绑验证令牌

        Args:
            kami: 卡密
            timestamp: 时间戳，默认当前时间

        Returns:
            HMAC-SHA256 签名字符串
        """
        if timestamp is None:
            import time
            timestamp = int(time.time())

        message = f"{kami}:{timestamp}"
        signature = hmac.new(
            KamiEncryptor._GLOBAL_SALT,
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        return f"{timestamp}:{signature}"

    @staticmethod
    def verify_unbind_token(kami: str, token: str, max_age: int = 300) -> bool:
        """
        验证解绑令牌

        Args:
            kami: 卡密
            token: 令牌字符串
            max_age: 令牌最大有效期（秒），默认5分钟

        Returns:
            令牌是否有效
        """
        try:
            import time

            parts = token.split(':')
            if len(parts) != 2:
                return False

            timestamp = int(parts[0])
            signature = parts[1]

            if abs(time.time() - timestamp) > max_age:
                return False

            expected_message = f"{kami}:{timestamp}"
            expected_signature = hmac.new(
                KamiEncryptor._GLOBAL_SALT,
                expected_message.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(signature, expected_signature)

        except:
            return False


class KamiConfigManager:
    """
    卡密配置管理器
    提供基于卡密的配置加密存储功能
    """

    def __init__(self, kami: str = None):
        """
        初始化管理器

        Args:
            kami: 当前卡密，用于加密配置
        """
        self.kami = kami
        self.encryptor = KamiEncryptor(kami) if kami else None

    def save_kami_config(self, data: dict) -> bool:
        """
        保存卡密配置到文件

        Args:
            data: 要保存的配置字典

        Returns:
            是否保存成功
        """
        try:
            from config.kami_config import kami_config

            if not self.encryptor:
                logger.error("未设置卡密，无法加密配置")
                return False

            encrypted = self.encryptor.encrypt(data)
            kami_config.set("encrypted_config", encrypted)

            logger.info("卡密配置保存成功")
            return True

        except Exception as e:
            logger.error(f"保存卡密配置失败: {str(e)}")
            return False

    def load_kami_config(self) -> dict:
        """
        加载卡密配置

        Returns:
            解密后的配置字典，如果失败返回空字典
        """
        try:
            from config.kami_config import kami_config

            encrypted = kami_config.get("encrypted_config", "")
            if not encrypted:
                return {}

            if not self.encryptor:
                logger.error("未设置卡密，无法解密配置")
                return {}

            return self.encryptor.decrypt(encrypted)

        except Exception as e:
            logger.error(f"加载卡密配置失败: {str(e)}")
            return {}


def create_kami_encryptor(kami: str = None) -> KamiEncryptor:
    """
    工厂函数：创建卡密加密器

    Args:
        kami: 卡密字符串

    Returns:
        KamiEncryptor 实例
    """
    return KamiEncryptor(kami)


def verify_current_kami(kami: str) -> bool:
    """
    验证当前卡密是否有效

    Args:
        kami: 要验证的卡密

    Returns:
        卡密是否有效
    """
    try:
        from config.kami_config import kami_config

        encrypted_data = kami_config.get("encrypted_config", "")
        if not encrypted_data:
            return True

        return KamiEncryptor.verify_kami(kami, encrypted_data)

    except Exception as e:
        logger.error(f"验证卡密失败: {str(e)}")
        return False
