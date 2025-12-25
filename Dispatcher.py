import json
import pandas as pd
import subprocess
import time
import socket
from redis import Redis
from sklearn.preprocessing import StandardScaler
import os
import sys

# ================= 工具函数 =================

def get_local_ip():
    """获取本机真实 IP（非 0.0.0.0）"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip

def parse_before_settings():
    """
    解析 before_settings 文件
    格式：
    Line 1: 0 (自建) 或 1 (连接)
    Line 2: IP (若0则忽略/留白)
    Line 3: Port (若0则忽略/留白)
    Line 4+: 算法名称列表
    
    返回: (mode, ip, port, algorithms_list)
    """
    if not os.path.exists("before_settings"):
        print("错误：找不到 before_settings 文件")
        sys.exit(1)
        
    with open("before_settings", "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines()]
    
    if len(lines) < 3:
        raise ValueError("before_settings 行数不足，至少需要标志位及预留的IP/Port行")

    mode_flag = lines[0] # '0' or '1'
    target_ip = None
    target_port = None
    
    # 提取 IP 和 Port
    if mode_flag == '1':
        if len(lines) < 3 or not lines[1] or not lines[2]:
            raise ValueError("模式为 1 时，必须提供 IP 和端口")
        target_ip = lines[1]
        target_port = int(lines[2])
    else:
        # 模式 0，忽略中间两行（即使有内容也不读）
        pass
        
    # 提取算法 (从第4行开始，即索引3)
    algorithms = []
    if len(lines) > 3:
        algorithms = [l for l in lines[3:] if l] # 过滤空行

    return mode_flag, target_ip, target_port, algorithms

def write_after_settings(ip, port):
    """写 after_settings"""
    with open("after_settings", "w", encoding="utf-8") as f:
        f.write(f"{ip}\n{port}\n")

def start_public_redis(port):
    """启动 0.0.0.0 绑定的 Redis"""
    try:
        # 尝试连接，看是否已经启动
        Redis(host="127.0.0.1", port=port).ping()
        return
    except:
        print(f"正在本地端口 {port} 启动 Redis...")
        subprocess.Popen(
            [
                "redis-server",
                "--port", str(port),
                "--bind", "0.0.0.0",
                "--protected-mode", "no"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(1) # 等待启动

# ================= 主流程 =================

STREAM_KEY = "tasks_stream"
ALGO_QUEUE_KEY = "algorithms_queue"

# 1. 解析配置
mode, ext_ip, ext_port, algo_list = parse_before_settings()

if mode == '0':
    # === 模式 0: 自建 Redis ===
    print("模式 0: 检测到自建 Redis 请求")
    REDIS_PORT = 11451
    start_public_redis(REDIS_PORT)
    
    # 连接本地
    r = Redis(host="127.0.0.1", port=REDIS_PORT)
    
    # 获取对外 IP 用于写入 after_settings
    local_ip = get_local_ip()
    final_ip = local_ip
    final_port = REDIS_PORT

elif mode == '1':
    # === 模式 1: 连接指定 Redis ===
    print(f"模式 1: 连接外部 Redis {ext_ip}:{ext_port}")
    try:
        r = Redis(host=ext_ip, port=ext_port)
        r.ping()
    except Exception as e:
        print(f"无法连接到目标 Redis: {e}")
        sys.exit(1)
        
    final_ip = ext_ip
    final_port = ext_port

else:
    print(f"错误：未知的模式标志 '{mode}'，请检查 before_settings 第一行")
    sys.exit(1)

# ================= 2. 分发算法任务 (List) =================

if algo_list:
    print(f"正在分发 {len(algo_list)} 个算法任务到队列 '{ALGO_QUEUE_KEY}'...")
    # 为了保证纯净，先清空旧的算法队列（可选，视需求而定，这里假设每次分发是新的开始）
    r.delete(ALGO_QUEUE_KEY) 
    for algo in algo_list:
        r.rpush(ALGO_QUEUE_KEY, algo)
else:
    print("警告：before_settings 中未检测到算法列表")

# ================= 3. 数据读取与处理 =================

print("正在读取并处理数据 (BostonHousing.csv)...")
try:
    df = pd.read_csv("BostonHousing.csv")
except FileNotFoundError:
    print("错误：找不到 BostonHousing.csv")
    sys.exit(1)

feature_names = df.columns.drop("medv").tolist()

scaler = StandardScaler()
X_scaled = scaler.fit_transform(df.drop("medv", axis=1))
y = df["medv"].values

# ================= 4. 写入 Redis Stream =================

# 写入 Header
r.xadd(
    STREAM_KEY,
    {
        "type": "header",
        "feature_names": json.dumps(feature_names)
    }
)

# 写入 Samples
for i in range(len(X_scaled)):
    r.xadd(
        STREAM_KEY,
        {
            "type": "sample",
            "task_id": i,
            "feature_values": json.dumps(X_scaled[i].tolist()),
            "target": float(y[i])
        }
    )

print(f"数据流已推送到 '{STREAM_KEY}'")
print(f"共写入 {len(X_scaled) + 1} 条消息（1 header + {len(X_scaled)} samples）")

# ================= 5. 输出 after_settings =================

write_after_settings(final_ip, final_port)
print(f"Redis 配置已写入 after_settings: {final_ip}:{final_port}")