import os
import platform

import psutil
from PyQt5.QtGui import QIcon


def kill_other_python_processes():
    # 获取当前进程ID
    # input("请按回车键继续...")
    current_pid = os.getpid()
    print(f"当前进程ID: {current_pid}")

    # 遍历所有正在运行的进程
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # 检查进程是否是Python进程
            if 'python' in proc.info['name'].lower() or \
                    (proc.info['cmdline'] and 'python' in proc.info['cmdline'][0].lower()):

                pid = proc.info['pid']
                # 跳过当前进程
                if pid == current_pid:
                    print(f"跳过当前Python进程: PID {pid}")
                    continue

                # 尝试终止进程（Windows兼容方式）
                print(f"终止Python进程: PID {pid}, 名称: {proc.info['name']}")
                # 使用psutil的terminate()方法（跨平台兼容）
                proc.terminate()

                # 等待1秒后检查是否终止
                try:
                    # 等待进程终止，超时3秒
                    proc.wait(timeout=3)
                    print(f"进程 {pid} 已成功终止")
                except psutil.TimeoutExpired:
                    # 超时未终止，尝试强制终止（Windows用kill()方法）
                    print(f"进程 {pid} 未正常终止，尝试强制终止")
                    proc.kill()  # psutil的kill()方法在Windows上会发送强制终止信号

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            print(f"处理进程时出错: {e}")


def kill_ikun_processes():
    """杀死名称包含ikun的所有应用程序"""
    # 获取当前进程ID
    current_pid = os.getpid()
    print(f"当前进程ID: {current_pid}")

    killed_count = 0
    found_count = 0
    background_processes = []
    current_process = None

    # 遍历所有正在运行的进程
    for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
        try:
            pid = proc.info['pid']
            
            # 检查进程名称、可执行文件路径或命令行是否包含ikun（不区分大小写）
            process_name = (proc.info['name'] or "").lower()
            exe_path = (proc.info['exe'] or "").lower()
            cmdline = " ".join(proc.info['cmdline'] or []).lower()
            
            # 检查是否包含ikun（不区分大小写）
            is_ikun_process = ('ikun' in process_name or 
                              'ikun' in exe_path or 
                              'ikun' in cmdline)
            
            if is_ikun_process:
                found_count += 1
                print(f"发现ikun进程: PID {pid}, 名称: {proc.info['name']}, 路径: {proc.info['exe']}")
                print(f"命令行: {proc.info['cmdline']}")
                
                # 如果是当前进程，记录下来稍后处理
                if pid == current_pid:
                    current_process = proc
                    print(f"当前进程: PID {pid}, 将最后处理")
                else:
                    # 其他进程作为后台进程处理
                    background_processes.append(proc)
                    print(f"后台进程: PID {pid}")

        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            print(f"处理进程时出错: {e}")
    
    print(f"共找到 {found_count} 个ikun相关进程，其中 {len(background_processes)} 个后台进程")
    
    # 返回找到的进程信息，由调用方处理实际的清理逻辑
    return {
        'background_processes': background_processes,
        'current_process': current_process,
        'found_count': found_count
    }


def kill_ikun_processes_with_delay():
    """先弹出弹窗，过1秒，清理后台进程，最后清理自身"""
    import time
    from PyQt5.QtWidgets import QApplication
    
    # 获取当前应用程序实例
    app = QApplication.instance()
    
    # 先显示一个提示弹窗
    from PyQt5.QtWidgets import QMessageBox
    msg_box = QMessageBox()
    msg_box.setWindowIcon(QIcon("gui/img/favicon.ico"))
    msg_box.setWindowTitle("击落ikun")
    msg_box.setText("击落中...")
    msg_box.setStandardButtons(QMessageBox.NoButton)  # 不显示任何按钮
    msg_box.show()
    
    # 处理UI事件，确保弹窗显示
    app.processEvents()
    
    # 等待1秒
    time.sleep(1)
    
    # 获取ikun进程信息
    process_info = kill_ikun_processes()
    background_processes = process_info['background_processes']
    current_process = process_info['current_process']
    found_count = process_info['found_count']
    
    killed_count = 0
    
    # 清理后台进程
    for proc in background_processes:
        try:
            pid = proc.info['pid']
            print(f"正在终止后台ikun进程: PID {pid}")

            # 在Windows上，首先尝试使用taskkill命令
            if platform.system() == "Windows":
                import subprocess
                # 先尝试正常终止
                result = subprocess.run(['taskkill', '/PID', str(pid), '/F'], 
                                     capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"使用taskkill成功终止进程 {pid}")
                    killed_count += 1
                else:
                    print(f"taskkill终止进程 {pid} 失败: {result.stderr}")
                    # 如果taskkill失败，再尝试psutil方法
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                        print(f"使用psutil成功终止进程 {pid}")
                        killed_count += 1
                    except psutil.TimeoutExpired:
                        print(f"进程 {pid} 未正常终止，尝试强制终止")
                        proc.kill()
                        killed_count += 1
            else:
                # 非Windows系统使用psutil方法
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                    print(f"使用psutil成功终止进程 {pid}")
                    killed_count += 1
                except psutil.TimeoutExpired:
                    print(f"进程 {pid} 未正常终止，尝试强制终止")
                    proc.kill()
                    killed_count += 1
        except Exception as e:
            print(f"终止后台进程时出错: {e}")
    
    # 更新弹窗文本
    msg_box.setText(f"已击落 {killed_count} 个后台ikun进程，准备击落自身...")
    app.processEvents()
    
    # 再等待1秒
    time.sleep(1)
    
    # 清理自身进程
    if current_process:
        try:
            pid = current_process.info['pid']
            print(f"正在终止当前ikun进程: PID {pid}")
            
            # 在Windows上，首先尝试使用taskkill命令
            if platform.system() == "Windows":
                import subprocess
                # 先尝试正常终止
                result = subprocess.run(['taskkill', '/PID', str(pid), '/F'], 
                                     capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"使用taskkill成功终止当前进程 {pid}")
                    killed_count += 1
                else:
                    print(f"taskkill终止当前进程 {pid} 失败: {result.stderr}")
                    # 如果taskkill失败，再尝试psutil方法
                    current_process.terminate()
                    try:
                        current_process.wait(timeout=3)
                        print(f"使用psutil成功终止当前进程 {pid}")
                        killed_count += 1
                    except psutil.TimeoutExpired:
                        print(f"当前进程 {pid} 未正常终止，尝试强制终止")
                        current_process.kill()
                        killed_count += 1
            else:
                # 非Windows系统使用psutil方法
                current_process.terminate()
                try:
                    current_process.wait(timeout=3)
                    print(f"使用psutil成功终止当前进程 {pid}")
                    killed_count += 1
                except psutil.TimeoutExpired:
                    print(f"当前进程 {pid} 未正常终止，尝试强制终止")
                    current_process.kill()
                    killed_count += 1
        except Exception as e:
            print(f"终止当前进程时出错: {e}")

    # 关闭提示弹窗
    msg_box.close()
    
    print(f"共找到 {found_count} 个ikun相关进程，成功击落了 {killed_count} 个")

    return killed_count


if __name__ == "__main__":
    # 确认操作
    kill_other_python_processes()