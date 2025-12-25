import json
import pandas as pd
import subprocess
import time
import socket
from redis import Redis
from sklearn.preprocessing import StandardScaler
import os

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

def read_before_settings():
    """读取 before_settings，返回 (ip, port) 或 None"""
    if not os.path.exists("before_settings"):
        return None
    with open("before_settings", "r") as f:
        lines = [line.strip() for line in f.readlines()]
    if len(lines) != 2:
        raise ValueError("before_settings 格式错误，必须两行：IP 和端口")
    return lines[0], int(lines[1])

def write_after_settings(ip, port):
    """写 after_settings"""
    with open("after_settings", "w") as f:
        f.write(f"{ip}\n{port}\n")

def start_public_redis(port):
    """启动 0.0.0.0 绑定的 Redis"""
    try:
        Redis(host="127.0.0.1", port=port).ping()
        return
    except:
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
        time.sleep(1)

# ================= Redis 初始化逻辑（核心修改） =================

STREAM_KEY = "tasks_stream"

settings = read_before_settings()

if settings:
    # 情况 1：使用已有 Redis
    REDIS_HOST, REDIS_PORT = settings
    r = Redis(host=REDIS_HOST, port=REDIS_PORT)
    r.ping()
    final_ip = REDIS_HOST

else:
    # 情况 2：本地启动 Redis
    REDIS_PORT = 11451
    start_public_redis(REDIS_PORT)
    r = Redis(host="127.0.0.1", port=REDIS_PORT)

    local_ip = get_local_ip()
    final_ip = local_ip  # after_settings 中不能是 0.0.0.0

# ================= 数据读取（保持你原逻辑） =================

df = pd.read_csv("BostonHousing.csv")

feature_names = df.columns.drop("medv").tolist()

scaler = StandardScaler()
X_scaled = scaler.fit_transform(df.drop("medv", axis=1))
y = df["medv"].values

# ================= 写入 Redis Stream =================

# ① header：特征名称
r.xadd(
    STREAM_KEY,
    {
        "type": "header",
        "feature_names": json.dumps(feature_names)
    }
)

# ② sample：仅特征值 + 目标值
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

# ================= 输出 after_settings =================

write_after_settings(final_ip, REDIS_PORT)

print(f"已写入 {len(X_scaled) + 1} 条消息（1 header + {len(X_scaled)} samples）")
print(f"Redis 配置已写入 after_settings: {final_ip}:{REDIS_PORT}")
