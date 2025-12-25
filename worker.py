import json
import redis
import numpy as np
import os
import sys
import socket
from sklearn.metrics import mean_squared_error, r2_score

# 导入单独拆分的算法配置
try:
    from algo import ALGO_MAP
except ImportError:
    print("错误：找不到 algo.py 文件，请确保它与 Worker.py 在同一目录下。")
    sys.exit(1)

# ================= 配置常量 =================

SETTINGS_FILE = "after_settings"
STREAM_KEY = "tasks_stream"
ALGO_QUEUE_KEY = "algorithms_queue"
RESULTS_QUEUE = "results"

# ================= 工具函数 =================

def read_redis_config():
    """读取 after_settings 获取 IP 和 端口"""
    if not os.path.exists(SETTINGS_FILE):
        print(f"错误：找不到配置文件 {SETTINGS_FILE}，请先运行 Dispatcher。")
        sys.exit(1)
    
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
        
    if len(lines) < 2:
        print("错误：配置文件格式不对（需包含两行：IP和端口）")
        sys.exit(1)
        
    return lines[0], int(lines[1])

def fetch_training_data(r):
    """从 Redis Stream 读取所有训练数据"""
    print("正在从 Stream 读取数据...")
    stream_data = r.xrange(STREAM_KEY, min='-', max='+')
    
    X = []
    y = []
    
    if not stream_data:
        return np.array([]), np.array([])

    for message_id, data in stream_data:
        msg_type = data.get(b'type').decode()
        
        if msg_type == 'sample':
            features = json.loads(data.get(b'feature_values').decode())
            target = float(data.get(b'target').decode())
            X.append(features)
            y.append(target)
            
    return np.array(X), np.array(y)

# ================= 主流程 =================

def main():
    # 1. 连接 Redis
    host, port = read_redis_config()
    print(f"Worker 启动，连接 Redis: {host}:{port}")
    
    try:
        r = redis.Redis(host=host, port=port)
        r.ping()
    except Exception as e:
        print(f"连接 Redis 失败: {e}")
        return

    # 2. 尝试领取 **单个** 任务
    # 直接取一次，如果有就做，没有就直接退出
    item = r.lpop(ALGO_QUEUE_KEY)
    
    if item is None:
        print("当前队列无待处理任务，Worker 无需工作，直接退出。")
        return

    algo_name = item.decode()
    print(f"\n>>> 成功抢到任务: [{algo_name}]")

    # 3. 检查配置中是否有该算法
    if algo_name not in ALGO_MAP:
        print(f"错误：algo_config.py 中未定义算法 '{algo_name}'，无法处理。")
        # 也可以选择把任务塞回去: r.rpush(ALGO_QUEUE_KEY, algo_name)
        return

    # 4. 加载数据 (确定有任务了再拉数据，节省带宽)
    X, y = fetch_training_data(r)
    if len(X) == 0:
        print("警告：Stream 中没有数据，无法训练。")
        return
    print(f"数据加载完毕，样本量: {len(X)}")

    # 5. 执行训练与评估
    model = ALGO_MAP[algo_name]
    try:
        # 训练
        model.fit(X, y)
        # 预测
        pred = model.predict(X)
        
        # 评估
        mse = mean_squared_error(y, pred)
        r2 = r2_score(y, pred)
        
        print(f"训练完成 | MSE: {mse:.4f} | R2: {r2:.4f}")
        
        # 6. 回传结果 (移除 worker 标识)
        result_data = {
            "algorithm": algo_name,
            "mse": mse,
            "r2_score": r2,
            "status": "success"
        }
        
        r.rpush(RESULTS_QUEUE, json.dumps(result_data))
        print("结果已回传至 Redis，任务结束。")
        
    except Exception as e:
        print(f"训练 '{algo_name}' 时发生异常: {e}")
        # 回传错误信息
        error_data = {
            "algorithm": algo_name,
            "status": "error",
            "error_msg": str(e)
        }
        r.rpush(RESULTS_QUEUE, json.dumps(error_data))

if __name__ == "__main__":
    main()