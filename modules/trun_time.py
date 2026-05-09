import datetime
def get_current_timestamp_with_zero_ms():
    """获取当前时间的毫秒级时间戳，确保最后三位为0（精确到秒）"""
    # 获取当前时间的秒级时间戳（整数）
    current_second = int(datetime.datetime.now().timestamp())
    # 转换为毫秒级，末尾补三个0
    timestamp_ms = current_second * 1000
    return timestamp_ms

def timestamp_ms_to_date(timestamp_ms):
    """将毫秒级时间戳转换为日期时间字符串"""
    # 毫秒转秒（除以1000，取整数）
    timestamp_s = timestamp_ms // 1000
    # 转换为UTC时间（带时区信息）
    dt_utc = datetime.datetime.fromtimestamp(timestamp_s, datetime.UTC)
    # 转换为本地时间
    dt_local = dt_utc.astimezone()
    # 格式化输出
    return dt_local.strftime("%Y-%m-%d %H:%M:%S")

def convert_to_ms_timestamp(year, month, day, hour=8, minute=0, second=0):
    """将指定日期时间转换为整数毫秒级时间戳"""
    # 构造指定时间的datetime对象（本地时间）
    from datetime import datetime
    dt = datetime(year, month, day, hour, minute, second)
    # 转换为UTC时间戳（秒），乘以1000得到毫秒，取整数
    timestamp_ms = int(dt.timestamp() * 1000)
    return timestamp_ms

def local_time():
    # 自动获取今天的年、月、日
    from datetime import datetime
    today = datetime.today()
    year = today.year
    month = today.month
    day = today.day
    # 转换为今天0点0分0秒的毫秒级时间戳
    today_timestamp_ms = convert_to_ms_timestamp(year, month, day)

    return today_timestamp_ms

if __name__ == "__main__":
    # print(local_time())

    # # 示例：转换2025年9月4日0点0分0秒
    timestamp = convert_to_ms_timestamp(2025, 9, 4)
    print(timestamp)  # 输出：1756915200000（与目标格式一致）
    date_str = timestamp_ms_to_date(timestamp)
    print(f"时间戳 {timestamp} 对应的日期是：{date_str}")


    # 示例：获取符合要求的当前时间戳
    current_timestamp = get_current_timestamp_with_zero_ms()
    print(current_timestamp)  # 输出类似：1717234567000（最后三位为0）
    date_str = timestamp_ms_to_date(current_timestamp+100000)
    print(f"时间戳 {current_timestamp} 对应的日期是：{date_str}")