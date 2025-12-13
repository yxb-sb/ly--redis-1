import json
import pandas as pd
import subprocess
import time
from redis import Redis
from sklearn.preprocessing import StandardScaler

# ================= Redis 启动 =================

REDIS_PORT = 11451
STREAM_KEY = "tasks_stream"

def start_public_redis(port):
    try:
        Redis(host="127.0.0.1", port=port).ping()
        return
    except:
        subprocess.Popen(
            ["redis-server",
             "--port", str(port),
             "--bind", "0.0.0.0",
             "--protected-mode", "no"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(1)

start_public_redis(REDIS_PORT)

r = Redis(host="127.0.0.1", port=REDIS_PORT)

# ================= 数据读取（保持你原逻辑） =================

df = pd.read_csv("BostonHousing.csv")   # 你原来怎么读就怎么读

feature_names = df.columns.drop("medv").tolist()

scaler = StandardScaler()
X_scaled = scaler.fit_transform(df.drop("medv", axis=1))
y = df["medv"].values

# ================= 写入 Redis Stream =================

# ① 第一个：特征名称
r.xadd(
    STREAM_KEY,
    {
        "type": "header",
        "feature_names": json.dumps(feature_names)
    }
)

# ② 后续：只写特征值 + 目标值
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

print(f"已写入 {len(X_scaled) + 1} 条消息（1 header + {len(X_scaled)} samples）")
