import threading
import time


class SnowflakeGenerator:
    """
    雪花算法生成器（手动实现，无第三方依赖）
    结构：0(1位) + 时间戳(41位) + 数据中心ID(5位) + 机器ID(5位) + 序列号(12位)
    """
    # 起始时间戳（2025-01-01 00:00:00），可自定义
    START_TIMESTAMP = 1735689600000
    # 各部分的位长
    DATACENTER_ID_BITS = 5
    WORKER_ID_BITS = 5
    SEQUENCE_BITS = 12

    # 最大值计算
    MAX_DATACENTER_ID = (1 << DATACENTER_ID_BITS) - 1  # 31
    MAX_WORKER_ID = (1 << WORKER_ID_BITS) - 1  # 31
    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1  # 4095

    # 位移量
    WORKER_ID_SHIFT = SEQUENCE_BITS
    DATACENTER_ID_SHIFT = SEQUENCE_BITS + WORKER_ID_BITS
    TIMESTAMP_SHIFT = SEQUENCE_BITS + WORKER_ID_BITS + DATACENTER_ID_BITS

    def __init__(self, worker_id: int, datacenter_id: int):
        """
        初始化生成器
        :param worker_id: 机器ID（0-31）
        :param datacenter_id: 数据中心ID（0-31）
        """
        # 校验参数
        if worker_id < 0 or worker_id > self.MAX_WORKER_ID:
            raise ValueError(f"worker_id必须在0-{self.MAX_WORKER_ID}之间")
        if datacenter_id < 0 or datacenter_id > self.MAX_DATACENTER_ID:
            raise ValueError(f"datacenter_id必须在0-{self.MAX_DATACENTER_ID}之间")

        self.worker_id = worker_id
        self.datacenter_id = datacenter_id
        self.sequence = 0  # 序列号，初始为0
        self.last_timestamp = -1  # 上一次生成ID的时间戳
        self._lock = threading.Lock()  # 线程安全锁

    def _get_current_timestamp(self) -> int:
        """获取当前毫秒级时间戳"""
        return int(time.time() * 1000)

    def _wait_next_millisecond(self, last_timestamp: int) -> int:
        """等待直到下一个毫秒"""
        timestamp = self._get_current_timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._get_current_timestamp()
        return timestamp

    def generate_id(self) -> int:
        """生成雪花ID（线程安全）"""
        with self._lock:
            current_timestamp = self._get_current_timestamp()

            # 时钟回拨处理
            if current_timestamp < self.last_timestamp:
                raise RuntimeError(
                    f"时钟回拨拒绝生成ID！当前时间戳：{current_timestamp}，上一次时间戳：{self.last_timestamp}")

            # 同一毫秒内，序列号递增
            if current_timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.MAX_SEQUENCE
                # 序列号溢出，等待下一个毫秒
                if self.sequence == 0:
                    current_timestamp = self._wait_next_millisecond(self.last_timestamp)
            else:
                # 不同毫秒，序列号重置为0
                self.sequence = 0

            self.last_timestamp = current_timestamp

            # 拼接雪花ID
            snowflake_id = (
                    ((current_timestamp - self.START_TIMESTAMP) << self.TIMESTAMP_SHIFT) |
                    (self.datacenter_id << self.DATACENTER_ID_SHIFT) |
                    (self.worker_id << self.WORKER_ID_SHIFT) |
                    self.sequence
            )
            return snowflake_id


# ------------------- 使用示例 -------------------
if __name__ == "__main__":
    # 初始化生成器（程序启动时执行一次）
    generator = SnowflakeGenerator(worker_id=1, datacenter_id=1)

    # 生成多个ID
    for _ in range(5):
        uid = generator.generate_id()
        print("生成的雪花ID：", uid)
