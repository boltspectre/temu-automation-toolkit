import json
import os

CONFIG_FILE_PATH = "配置文件_系统配置/config.txt"

class KamiConfig:
    def __init__(self):
        self.config_file = CONFIG_FILE_PATH
        self._ensure_config_exists()

    def _ensure_config_exists(self):
        if not os.path.exists(self.config_file):
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    json.dump({"kami": ""}, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"创建卡密配置文件失败: {e}")

    def _read_config(self):
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {"kami": ""}
        except Exception as e:
            print(f"读取卡密配置文件失败: {e}")
            return {"kami": ""}

    def _write_config(self, data):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"写入卡密配置文件失败: {e}")
            return False

    def get_kami(self):
        data = self._read_config()
        return data.get("kami", "")

    def set_kami(self, kami):
        data = self._read_config()
        data["kami"] = kami
        return self._write_config(data)

    def get(self, key, default=None):
        data = self._read_config()
        return data.get(key, default)

    def set(self, key, value):
        data = self._read_config()
        data[key] = value
        return self._write_config(data)

kami_config = KamiConfig()