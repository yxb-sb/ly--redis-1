import json
import numpy as np
from redis import Redis
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
import os
# --- 配置 ---
if not os.path.exists("after_settings"):
    raise FileNotFoundError("未找到 after_settings 文件")

with open("after_settings", "r") as f:
    lines = [line.strip() for line in f.readlines()]

if len(lines) != 2:
    raise ValueError("after_settings 格式错误，必须两行：IP 和端口")

REDIS_HOST = lines[0]
REDIS_PORT = int(lines[1])
TASK_STREAM = "tasks_stream"
RESULTS_QUEUE = "results"
TOTAL_EXPECTED = 506

# 【关键】独立的组名，确保能收到完整数据的副本
GROUP_NAME = "group_rf"
CONSUMER_NAME = "worker_rf"

print(f"🚀 [RandomForest] 正在启动...")

r = Redis(host=REDIS_HOST, port=REDIS_PORT)

# 【关键】创建组，如果存在则重置游标到 0 (从头开始)
try:
    r.xgroup_create(TASK_STREAM, GROUP_NAME, id="0", mkstream=True)
except Exception as e:
    if "BUSYGROUP" in str(e):
        # 强制重置游标，保证实验可重复运行
        r.xgroup_setid(TASK_STREAM, GROUP_NAME, id="0")
    else:
        raise e

samples = []

while True:
    # 阻塞读取
    msgs = r.xreadgroup(GROUP_NAME, CONSUMER_NAME, {TASK_STREAM: ">"}, count=50, block=1000)

    for _, messages in msgs:
        for msg_id, data in messages:
            msg_type = data[b"type"].decode()
            
            # 立即ACK
            r.xack(TASK_STREAM, GROUP_NAME, msg_id)

            if msg_type == "header":
                continue

            if msg_type == "sample":
                x = np.array(json.loads(data[b"feature_values"].decode())).reshape(1, -1)
                y = float(data[b"target"])
                samples.append((x, y))

                if len(samples) == TOTAL_EXPECTED:
                    print(f"📦 [RandomForest] 数据集接收完成 ({len(samples)})，开始训练...")
                    
                    X = np.vstack([s[0] for s in samples])
                    y = np.array([s[1] for s in samples])

                    X_train, X_test, y_train, y_test = train_test_split(
                        X, y, test_size=0.2, random_state=42
                    )

                    # === 算法部分 ===
                    model = RandomForestRegressor(random_state=42)
                    model.fit(X_train, y_train)
                    pred = model.predict(X_test)
                    mse = mean_squared_error(y_test, pred)
                    # ===============

                    result = {
                        "algorithm": "RandomForest",
                        "mse": mse,
                        "samples": TOTAL_EXPECTED
                    }
                    r.rpush(RESULTS_QUEUE, json.dumps(result))
                    print(f"✅ [RandomForest] 完成! MSE: {mse:.4f}")
                    exit(0)