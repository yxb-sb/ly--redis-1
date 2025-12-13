
import subprocess
import sys
import os

# 1. 获取当前脚本 (run_all.py) 所在的绝对路径
base_dir = os.path.dirname(os.path.abspath(__file__))

# 定义要运行的脚本文件名
workers = ["worker_rf.py", "worker_svr.py", "worker_lr.py"]
processes = []

print(f"⚡ 开始并行实验，共启动 {len(workers)} 个 Worker...")
print(f"📂 工作目录锁定为: {base_dir}")

for worker_script in workers:
    # 2. 拼接完整的绝对路径
    script_path = os.path.join(base_dir, worker_script)
    
    # 检查文件是否存在，防止报错
    if not os.path.exists(script_path):
        print(f"❌ [错误] 找不到文件: {script_path}")
        continue

    # 3. 使用绝对路径启动子进程
    # sys.executable 确保使用当前相同的 Python 环境
    p = subprocess.Popen([sys.executable, script_path])
    processes.append(p)
    print(f"   -> 已启动 {worker_script} (PID: {p.pid})")

print("⚡ 所有 Worker 已在后台运行，正在等待数据...")

# 等待所有子进程结束
for p in processes:
    p.wait()

print("\n🎉 所有实验运行结束！")
