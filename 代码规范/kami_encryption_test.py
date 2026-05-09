"""
卡密加密传输测试工具
用于测试客户端与服务器之间的加密通信

使用方法:
    python kami_encryption_test.py
"""

import base64
import hashlib
import hmac
import json
import time
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


# ============ 配置 ============
# 共享密钥 - 必须与服务器保持一致
SECRET_KEY = 'uno_yyds_wzry_sgs_ljyx'
# 固定IV
ENCRYPTION_IV = b'1234567890123456'
# 服务器地址（示例）
SERVER_URL = "https://your-server.com/index.php"
# 静态Token（示例）
STATIC_TOKEN = "your_static_token"


class KamiCryptoTester:
    """卡密加密传输测试类"""
    
    def __init__(self, kami: str, machine_code: str, version: str = "1.0.0"):
        """
        初始化测试器
        
        Args:
            kami: 测试用卡密
            machine_code: 测试用机器码
            version: 软件版本号
        """
        self.kami = kami
        self.machine_code = machine_code
        self.version = version
        self.key = hashlib.sha256(SECRET_KEY.encode()).digest()
    
    def encrypt_data(self, data: str) -> str:
        """加密数据"""
        cipher = AES.new(self.key, AES.MODE_CBC, ENCRYPTION_IV)
        encrypted = cipher.encrypt(pad(data.encode('utf-8'), AES.block_size))
        return base64.b64encode(encrypted).decode('utf-8')
    
    def decrypt_data(self, encrypted_data: str) -> str:
        """解密数据"""
        cipher = AES.new(self.key, AES.MODE_CBC, ENCRYPTION_IV)
        decrypted = unpad(
            cipher.decrypt(base64.b64decode(encrypted_data)),
            AES.block_size
        )
        return decrypted.decode('utf-8')
    
    def generate_signature(self, timestamp: int) -> str:
        """生成签名"""
        data = f"{self.kami}{timestamp}".encode('utf-8')
        return hmac.new(SECRET_KEY.encode(), data, hashlib.sha256).hexdigest()
    
    def build_request_payload(self) -> dict:
        """
        构建加密请求体
        
        Returns:
            包含加密数据的请求体字典
        """
        timestamp = int(time.time())
        
        # 加密各项数据
        encrypted_kami = self.encrypt_data(self.kami)
        encrypted_machine = self.encrypt_data(self.machine_code)
        encrypted_version = self.encrypt_data(self.version)
        signature = self.generate_signature(timestamp)
        
        payload = {
            'encrypted_kami': encrypted_kami,
            'timestamp': timestamp,
            'signature': signature,
            'encrypted_machine_code': encrypted_machine,
            'encrypted_version': encrypted_version
        }
        
        return payload
    
    def print_request_details(self):
        """打印请求详情"""
        payload = self.build_request_payload()
        
        print("=" * 60)
        print("加密请求详情")
        print("=" * 60)
        
        print(f"\n【原始数据】")
        print(f"  卡密: {self.kami}")
        print(f"  机器码: {self.machine_code}")
        print(f"  版本: {self.version}")
        
        print(f"\n【加密后的请求体】")
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        
        print(f"\n【加密字段详情】")
        print(f"  encrypted_kami: {payload['encrypted_kami'][:50]}...")
        print(f"  encrypted_machine_code: {payload['encrypted_machine_code'][:50]}...")
        print(f"  encrypted_version: {payload['encrypted_version'][:50]}...")
        print(f"  timestamp: {payload['timestamp']}")
        print(f"  signature: {payload['signature'][:32]}...")
        
        return payload
    
    def verify_and_decrypt(self, payload: dict):
        """验证并解密请求数据"""
        print("\n" + "=" * 60)
        print("解密验证")
        print("=" * 60)
        
        # 验证签名
        is_valid = hmac.compare_digest(
            self.generate_signature(payload['timestamp']),
            payload['signature']
        )
        print(f"\n【签名验证】")
        print(f"  结果: {'通过' if is_valid else '失败'}")
        
        # 解密数据
        print(f"\n【解密数据】")
        decrypted_kami = self.decrypt_data(payload['encrypted_kami'])
        decrypted_machine = self.decrypt_data(payload['encrypted_machine_code'])
        decrypted_version = self.decrypt_data(payload['encrypted_version'])
        
        print(f"  卡密: {decrypted_kami}")
        print(f"  机器码: {decrypted_machine}")
        print(f"  版本: {decrypted_version}")
        
        # 验证解密结果
        print(f"\n【验证结果】")
        print(f"  卡密匹配: {'是' if decrypted_kami == self.kami else '否'}")
        print(f"  机器码匹配: {'是' if decrypted_machine == self.machine_code else '否'}")
        print(f"  版本匹配: {'是' if decrypted_version == self.version else '否'}")


def test_encrypt_decrypt():
    """测试基础加密解密功能"""
    print("\n" + "=" * 60)
    print("基础加密解密测试")
    print("=" * 60)
    
    key = hashlib.sha256(SECRET_KEY.encode()).digest()
    test_data = "测试数据: VIP-TEST-1234"
    
    print(f"\n【加密过程】")
    print(f"  原始数据: {test_data}")
    print(f"  密钥(SHA256): {key.hex()[:32]}...")
    print(f"  IV: {ENCRYPTION_IV}")
    
    # 加密
    cipher = AES.new(key, AES.MODE_CBC, ENCRYPTION_IV)
    encrypted = cipher.encrypt(pad(test_data.encode('utf-8'), AES.block_size))
    encrypted_b64 = base64.b64encode(encrypted).decode('utf-8')
    
    print(f"  加密结果(Base64): {encrypted_b64}")
    
    print(f"\n【解密过程】")
    # 解密
    cipher2 = AES.new(key, AES.MODE_CBC, ENCRYPTION_IV)
    decrypted = unpad(cipher2.decrypt(base64.b64decode(encrypted_b64)), AES.block_size)
    decrypted_str = decrypted.decode('utf-8')
    
    print(f"  解密结果: {decrypted_str}")
    print(f"  验证: {'通过' if test_data == decrypted_str else '失败'}")


def test_kami_encryption():
    """测试卡密加密传输"""
    print("\n" + "=" * 60)
    print("卡密加密传输测试")
    print("=" * 60)
    
    # 测试数据
    test_kami = "VIP-TEST-1234-5678"
    test_machine = "TEST-MACHINE-CODE-001"
    test_version = "1.0.0"
    
    # 创建测试器
    tester = KamiCryptoTester(test_kami, test_machine, test_version)
    
    # 打印请求详情
    payload = tester.print_request_details()
    
    # 验证并解密
    tester.verify_and_decrypt(payload)


def test_signature():
    """测试签名生成和验证"""
    print("\n" + "=" * 60)
    print("签名测试")
    print("=" * 60)
    
    kami = "VIP-TEST-1234"
    timestamp = int(time.time())
    
    print(f"\n【签名生成】")
    print(f"  卡密: {kami}")
    print(f"  时间戳: {timestamp}")
    print(f"  密钥: {SECRET_KEY}")
    
    # 生成签名
    data = f"{kami}{timestamp}".encode('utf-8')
    signature = hmac.new(SECRET_KEY.encode(), data, hashlib.sha256).hexdigest()
    
    print(f"  签名结果: {signature}")
    
    print(f"\n【签名验证】")
    # 验证签名
    expected = hmac.new(SECRET_KEY.encode(), data, hashlib.sha256).hexdigest()
    is_valid = hmac.compare_digest(expected, signature)
    print(f"  验证结果: {'通过' if is_valid else '失败'}")
    
    print(f"\n【篡改测试】")
    # 篡改测试
    wrong_signature = signature[:-1] + ('0' if signature[-1] != '0' else '1')
    is_valid_wrong = hmac.compare_digest(expected, wrong_signature)
    print(f"  错误签名: {wrong_signature}")
    print(f"  验证结果: {'通过' if is_valid_wrong else '失败（符合预期）'}")


def simulate_server_response():
    """模拟服务器响应解密"""
    print("\n" + "=" * 60)
    print("模拟服务器响应解密")
    print("=" * 60)
    
    key = hashlib.sha256(SECRET_KEY.encode()).digest()
    
    # 模拟服务器返回的用户数据
    user_data = {
        "kami": "VIP-TEST-1234-5678",
        "start_time": "2024-01-01",
        "end_time": "2025-01-01",
        "level": "VIP",
        "features": ["feature_a", "feature_b", "feature_c"]
    }
    
    print(f"\n【服务器端加密】")
    print(f"  原始数据: {json.dumps(user_data, ensure_ascii=False)}")
    
    # 服务器加密
    json_str = json.dumps(user_data, ensure_ascii=False)
    cipher = AES.new(key, AES.MODE_CBC, ENCRYPTION_IV)
    encrypted = cipher.encrypt(pad(json_str.encode('utf-8'), AES.block_size))
    response_data = base64.b64encode(encrypted).decode('utf-8')
    
    print(f"  加密响应: {response_data[:60]}...")
    
    print(f"\n【客户端解密】")
    # 客户端解密
    cipher2 = AES.new(key, AES.MODE_CBC, ENCRYPTION_IV)
    decrypted = unpad(cipher2.decrypt(base64.b64decode(response_data)), AES.block_size)
    decrypted_data = json.loads(decrypted.decode('utf-8'))
    
    print(f"  解密结果: {json.dumps(decrypted_data, ensure_ascii=False, indent=2)}")
    print(f"  验证: {'通过' if decrypted_data == user_data else '失败'}")


if __name__ == "__main__":
    """运行所有测试"""
    print("\n" + "=" * 70)
    print(" " * 20 + "卡密加密系统测试工具")
    print("=" * 70)
    
    # 运行各项测试
    test_encrypt_decrypt()
    test_signature()
    test_kami_encryption()
    simulate_server_response()
    
    print("\n" + "=" * 70)
    print(" " * 25 + "所有测试完成")
    print("=" * 70)
