import hashlib
import platform
import subprocess
import os
import uuid
import ctypes
from typing import List

# 缓存机器码，避免重复获取时的问题
_cached_machine_code = None


def get_cpu_info() -> List[str]:
    system = platform.system()
    identifiers = []

    try:
        if system == "Windows":
            # 使用正确的 PowerShell 语法（无空格、正确插值）
            ps_script = (
                "$cpu = Get-CimInstance Win32_Processor; "
                "Write-Output (\"$($cpu.Manufacturer)|$($cpu.Name)|$($cpu.NumberOfCores)\")"
            )
            result = subprocess.check_output(
                ["powershell", "-Command", ps_script],
                stderr=subprocess.STDOUT,
                text=True,
                timeout=10
            ).strip()
            parts = [p.strip() for p in result.split('|') if p.strip()]
            identifiers = parts

        elif system == "Linux":
            with open('/proc/cpuinfo', 'r') as f:
                content = f.read()
            import re
            vendor_match = re.search(r'(?i)vendor_id\s*:\s*(.+)', content)
            model_match = re.search(r'(?i)model name\s*:\s*(.+)', content)
            cores_match = re.search(r'(?i)cpu cores\s*:\s*(\d+)', content)
            if vendor_match:
                identifiers.append(vendor_match.group(1).strip())
            if model_match:
                identifiers.append(model_match.group(1).strip())
            if cores_match:
                identifiers.append(cores_match.group(1).strip())

        elif system == "Darwin":
            vendor = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip()
            cores = subprocess.check_output(["sysctl", "-n", "hw.physicalcpu"], text=True).strip()
            identifiers = [vendor, cores]

    except Exception:
        pass

    return [x for x in identifiers if x and x.lower() not in ('to be filled by o.e.m.', 'none', 'unknown', 'not available')]



def get_unique_machine_code() -> str | None:
    """生成稳定的机器指纹（使用WMI获取硬件信息）"""
    global _cached_machine_code
    
    # 如果已经缓存过，直接返回
    if _cached_machine_code:
        return _cached_machine_code
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            import wmi
            
            # 获取物理MAC地址
            def get_physical_mac_address():
                try:
                    wmi_obj = wmi.WMI() 
                    for adapter in wmi_obj.Win32_NetworkAdapter(PhysicalAdapter=True): 
                        if adapter.MACAddress and adapter.MACAddress.strip():
                            return adapter.MACAddress.strip()
                except Exception as e:
                    pass
                return None
            
            # 获取CPU信息
            cpu_info = '.'.join(cpu.Name.strip() for cpu in wmi.WMI().Win32_Processor() if cpu and cpu.Name and cpu.Name.strip())
            
            # 获取硬盘信息
            disk_info = '.'.join(disk.Model for disk in wmi.WMI().Win32_DiskDrive() if disk and disk.Model and disk.Model.strip())
            
            # 获取显卡信息
            gpu_info = '.'.join(gpu.Name for gpu in wmi.WMI().Win32_VideoController() if gpu and gpu.Name and gpu.Name.strip())
            
            # 获取MAC地址
            mac_info = get_physical_mac_address()
            
            # 组合所有信息
            parts = []
            if cpu_info:
                parts.append(cpu_info)
            if disk_info:
                parts.append(disk_info)
            if gpu_info:
                parts.append(gpu_info)
            if mac_info:
                parts.append(mac_info)
            
            if not parts:
                continue

            # 去重并排序（避免顺序影响哈希）
            unique_parts = sorted(set(parts))
            combined = '|'.join(unique_parts).encode('utf-8')
            machine_code = hashlib.sha256(combined).hexdigest()[:32]  # 32位 hex，类似 MD5 长度
            _cached_machine_code = machine_code  # 缓存机器码
            return machine_code
            
        except ImportError:
            # 如果没有安装wmi模块，使用备选方案
            parts = []
            
            try:
                # 获取MAC地址（无需管理员权限）
                mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) for elements in range(0,2*6,2)][::-1])
                if mac and mac != '00:00:00:00:00:00':
                    parts.append(mac)
            except:
                pass
            
            # 获取系统UUID（无需管理员权限）
            system = platform.system()
            if system == "Windows":
                try:
                    import winreg
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                        machine_guid = winreg.QueryValueEx(key, "MachineGuid")[0]
                        if machine_guid and machine_guid.strip():
                            parts.append(machine_guid.strip())
                except:
                    pass
            elif system == "Linux":
                try:
                    with open('/etc/machine-id', 'r') as f:
                        machine_id = f.read().strip()
                        if machine_id:
                            parts.append(machine_id)
                except:
                    pass
            elif system == "Darwin":  # macOS
                try:
                    result = os.popen('ioreg -rd1 -c IOPlatformExpertDevice').read()
                    import re
                    match = re.search(r'"IOPlatformUUID" = "([^"]+)"', result)
                    if match:
                        parts.append(match.group(1))
                except:
                    pass
            
            # 如果以上方法都失败，使用CPU信息作为备选
            if not parts:
                cpu_info = get_cpu_info()
                if cpu_info:
                    parts.extend(cpu_info)

            if not parts:
                continue

            # 去重并排序（避免顺序影响哈希）
            unique_parts = sorted(set(parts))
            combined = '|'.join(unique_parts).encode('utf-8')
            machine_code = hashlib.sha256(combined).hexdigest()[:32]  # 32位 hex，类似 MD5 长度
            _cached_machine_code = machine_code  # 缓存机器码
            return machine_code
        except Exception as e:
            if attempt < max_retries - 1:
                continue
            else:
                return None
    
    return None


if __name__ == '__main__':
    print("CPU Info:", get_cpu_info())
    print("Stable Machine Fingerprint:", get_unique_machine_code())