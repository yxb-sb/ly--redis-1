import json
import numpy as np
from redis import Redis
from sklearn.linear_model import LinearRegression # 导入线性回归
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error

# --- 配置 ---
REDIS_HOST = "172.19.123.13"
REDIS_PORT = 11451
TASK_STREAM = "tasks_stream"
RESULTS_QUEUE = "results"
TOTAL_EXPECTED = 506

# 【关键】独立的组名
GROUP_NAME = "group_lr"
CONSUMER_NAME = "worker_lr"

print(f"🚀 [LinearRegression] 正在启动...")

r = Redis(host=REDIS_HOST, port=REDIS_PORT)

try:
    r.xgroup_create(TASK_STREAM, GROUP_NAME, id="0", mkstream=True)
except Exception as e:
    if "BUSYGROUP" in str(e):
        r.xgroup_setid(TASK_STREAM, GROUP_NAME, id="0")
    else:
        raise e

samples = []

while True:
    msgs = r.xreadgroup(GROUP_NAME, CONSUMER_NAME, {TASK_STREAM: ">"}, count=50, block=1000)

    for _, messages in msgs:
        for msg_id, data in messages:
            msg_type = data[b"type"].decode()
            r.xack(TASK_STREAM, GROUP_NAME, msg_id)

            if msg_type == "sample":
                x = np.array(json.loads(data[b"feature_values"].decode())).reshape(1, -1)
                y = float(data[b"target"])
                samples.append((x, y))

                if len(samples) == TOTAL_EXPECTED:
                    print(f"📦 [LinearRegression] 数据集接收完成 ({len(samples)})，开始训练...")
                    
                    X = np.vstack([s[0] for s in samples])
                    y = np.array([s[1] for s in samples])

                    X_train, X_test, y_train, y_test = train_test_split(
                        X, y, test_size=0.2, random_state=42
                    )

                    # === 算法部分 ===
                    model = LinearRegression()
                    model.fit(X_train, y_train)
                    pred = model.predict(X_test)
                    mse = mean_squared_error(y_test, pred)
                    # ===============

                    result = {
                        "algorithm": "LinearRegression",
                        "mse": mse,
                        "samples": TOTAL_EXPECTED
                    }
                    r.rpush(RESULTS_QUEUE, json.dumps(result))
                    print(f"✅ [LinearRegression] 完成! MSE: {mse:.4f}")
                    exit(0)