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
    Line 1: 0 (自建) 或 1 (连接)
    Line 2: IP
    Line 3: Port
    Line 4+: 算法配置（可以是纯名字，也可以是 JSON 字符串）
    """
    if not os.path.exists("before_settings"):
        print("错误：找不到 before_settings 文件")
        sys.exit(1)
        
    with open("before_settings", "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines()]
    
    if len(lines) < 3:
        raise ValueError("before_settings 行数不足")

    mode_flag = lines[0]
    target_ip = None
    target_port = None
    
    if mode_flag == '1':
        if len(lines) < 3 or not lines[1] or not lines[2]:
            raise ValueError("模式为 1 时，必须提供 IP 和端口")
        target_ip = lines[1]
        target_port = int(lines[2])
    
    # 提取任务行 (从第4行开始)
    task_lines = []
    if len(lines) > 3:
        task_lines = [l for l in lines[3:] if l]

    return mode_flag, target_ip, target_port, task_lines

def write_after_settings(ip, port):
    with open("after_settings", "w", encoding="utf-8") as f:
        f.write(f"{ip}\n{port}\n")

def start_public_redis(port):
    try:
        Redis(host="127.0.0.1", port=port).ping()
        return
    except:
        print(f"正在本地端口 {port} 启动 Redis...")
        subprocess.Popen(
            ["redis-server", "--port", str(port), "--bind", "0.0.0.0", "--protected-mode", "no"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(1)

# ================= 主流程 =================

STREAM_KEY = "tasks_stream"
ALGO_QUEUE_KEY = "algorithms_queue"

# 1. 解析配置
mode, ext_ip, ext_port, raw_task_lines = parse_before_settings()

if mode == '0':
    print("模式 0: 检测到自建 Redis 请求")
    REDIS_PORT = 11451
    start_public_redis(REDIS_PORT)
    r = Redis(host="127.0.0.1", port=REDIS_PORT)
    final_ip = get_local_ip()
    final_port = REDIS_PORT
elif mode == '1':
    print(f"模式 1: 连接外部 Redis {ext_ip}:{ext_port}")
    try:
        r = Redis(host=ext_ip, port=ext_port)
        r.ping()
    except Exception as e:
        print(f"无法连接 Redis: {e}")
        sys.exit(1)
    final_ip = ext_ip
    final_port = ext_port
else:
    print(f"错误：模式 '{mode}' 无效")
    sys.exit(1)

# ================= 2. 分发任务 (核心修改部分) =================

if raw_task_lines:
    print(f"正在解析并分发 {len(raw_task_lines)} 个任务到队列 '{ALGO_QUEUE_KEY}'...")
    r.delete(ALGO_QUEUE_KEY) 
    
    for line in raw_task_lines:
        line = line.strip()
        task_payload = {}
        
        # 尝试判断用户写的是 JSON 还是普通字符串
        try:
            # 尝试解析 JSON
            parsed_json = json.loads(line)
            if isinstance(parsed_json, dict) and "model_name" in parsed_json:
                # 用户写的是完整的 JSON 配置
                task_payload = parsed_json
            else:
                # 虽然是 JSON 但格式不对，或者用户写的是纯字符串但包含了引号
                # 这种情况下，默认当作模型名处理
                task_payload = {"model_name": line, "params": {}}
        except json.JSONDecodeError:
            # 解析失败，说明是普通字符串（例如：LinearRegression）
            task_payload = {
                "model_name": line,
                "params": {}
            }
        
        # 最终推入 Redis 的必须是 JSON 字符串
        r.rpush(ALGO_QUEUE_KEY, json.dumps(task_payload))
        print(f" -> 已添加任务: {task_payload['model_name']} (Params: {task_payload.get('params')})")
        
else:
    print("警告：before_settings 中未检测到任务列表")

# ================= 3. 数据处理 =================

print("正在读取并处理数据 (BostonHousing.csv)...")
try:
    df = pd.read_csv("BostonHousing.csv")
    feature_names = df.columns.drop("medv").tolist()
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df.drop("medv", axis=1))
    y = df["medv"].values
except Exception as e:
    print(f"读取或处理数据失败: {e}")
    sys.exit(1)

# ================= 4. 写入 Redis Stream =================

# 写入 Header
r.xadd(STREAM_KEY, {"type": "header", "feature_names": json.dumps(feature_names)})

# 写入 Samples
for i in range(len(X_scaled)):
    r.xadd(STREAM_KEY, {
        "type": "sample",
        "task_id": i,
        "feature_values": json.dumps(X_scaled[i].tolist()),
        "target": float(y[i])
    })

print(f"数据流已推送，共 {len(X_scaled)} 条样本")

# ================= 5. 完成 =================

write_after_settings(final_ip, final_port)
print(f"配置已就绪: {final_ip}:{final_port}")