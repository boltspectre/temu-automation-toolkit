import subprocess
import re

def get_wifi_passwords():
    try:
        # 获取所有WiFi配置文件（解决中文编码报错）
        results = subprocess.run(
            ["netsh", "wlan", "show", "profiles"],
            capture_output=True,
            text=False
        ).stdout

        # 自动解码，不乱码
        try:
            results = results.decode("gbk")
        except:
            results = results.decode("utf-8", errors="ignore")

        # 提取WiFi名称
        wifi_names = re.findall(r"所有用户配置文件\s*:\s*(.*)", results)

        print("===== WiFi 名称 + 密码 =====")
        for name in wifi_names:
            name = name.strip()
            if not name:
                continue

            # 获取密码
            pass_result = subprocess.run(
                ["netsh", "wlan", "show", "profile", f"name={name}", "key=clear"],
                capture_output=True,
                text=False
            ).stdout

            try:
                pass_result = pass_result.decode("gbk")
            except:
                pass_result = pass_result.decode("utf-8", errors="ignore")

            # 提取密码
            pass_find = re.search(r"关键内容\s*:\s*(.*)", pass_result)
            password = pass_find.group(1).strip() if pass_find else "无密码"

            print(f"WiFi：{name} ｜ 密码：{password}")

    except Exception as e:
        print("获取失败：", e)

if __name__ == "__main__":
    get_wifi_passwords()
