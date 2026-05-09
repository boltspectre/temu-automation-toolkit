import os

import psutil


def kill_other_python_processes():
    # 获取当前进程ID
    current_pid = os.getpid()

    # 遍历所有正在运行的进程
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # 检查进程是否是Python进程
            if 'python' in proc.info['name'].lower() or \
                    (proc.info['cmdline'] and 'python' in proc.info['cmdline'][0].lower()):

                pid = proc.info['pid']
                # 跳过当前进程
                if pid == current_pid:
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


if __name__ == "__main__":
    kill_other_python_processes()
