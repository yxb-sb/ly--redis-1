import json
import pandas as pd
import socket
import os
import sys
import subprocess
import time
from redis import Redis
from sklearn.preprocessing import StandardScaler

# ================= 配置常量 =================
# 三大通道对应的 Redis Key
KEY_CODE   = "dist_code_source"      # 通道 1: 代码
KEY_DATA   = "tasks_stream"          # 通道 2: 数据
KEY_QUEUE  = "algorithms_queue"      # 通道 3: 任务指令

# 本地文件
FILE_CODE     = "task_definitions.py"
FILE_DATA     = "BostonHousing.csv"
FILE_SETTINGS = "before_settings"

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try: s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]
    finally: s.close()
    return ip

# ================= 初始化 Redis 连接 =================
if not os.path.exists(FILE_SETTINGS):
    sys.exit(f"错误: 缺少 {FILE_SETTINGS} 文件")

with open(FILE_SETTINGS, "r", encoding='utf-8') as f:
    raw_lines = [l.strip() for l in f.readlines() if l.strip()]

if not raw_lines: sys.exit("配置为空")

mode = raw_lines[0]
if mode == '0':
    print(">>> [Init] 启动本地 Redis...")
    ip, port = get_local_ip(), 11451
    subprocess.Popen(["redis-server", "--port", str(port), "--bind", "0.0.0.0", "--protected-mode", "no"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    r = Redis(host="127.0.0.1", port=port)
else:
    ip, port = raw_lines[1], int(raw_lines[2])
    print(f">>> [Init] 连接远程 Redis {ip}:{port}...")
    r = Redis(host=ip, port=port)

try:
    r.ping()
    print(">>> [Init] Redis 连接成功。")
except Exception as e:
    sys.exit(f"Redis 连接失败: {e}")

# ================= 第一步: 发送代码 (Code Channel) =================
print(f"\n>>> [Step 1/3] 发送代码 (逻辑层)...")
if os.path.exists(FILE_CODE):
    with open(FILE_CODE, "r", encoding="utf-8") as f:
        code_content = f.read()
    r.set(KEY_CODE, code_content)
    print(f" -> 成功上传 '{FILE_CODE}' 到 Redis Key: {KEY_CODE}")
else:
    print(f" -> !!! 警告: 找不到代码文件 {FILE_CODE}，Worker 将无法加载逻辑！")

# ================= 第二步: 发送数据 (Data Channel) =================
print(f"\n>>> [Step 2/3] 发送数据 (数据层)...")
if os.path.exists(FILE_DATA):
    try:
        df = pd.read_csv(FILE_DATA)
        # 预处理：统一列名小写，去空格
        df.columns = df.columns.str.strip().str.lower()
        
        # 兼容性重命名
        if "medv" not in df.columns:
            last_col = df.columns[-1]
            df.rename(columns={last_col: "medv"}, inplace=True)
            print(f" -> 将 '{last_col}' 重命名为 'medv'")

        # 标准化特征
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(df.drop("medv", axis=1))
        y = df["medv"].values
        
        # 清空旧数据并上传
        r.delete(KEY_DATA)
        pipe = r.pipeline()
        # 写入元数据 Header (可选，方便 Worker 知道列名)
        pipe.xadd(KEY_DATA, {"type": "header", "cols": json.dumps(df.columns.tolist())})
        
        # 写入样本
        for i, row in enumerate(X_scaled):
            pipe.xadd(KEY_DATA, {
                "type": "sample",
                "feature_values": json.dumps(row.tolist()),
                "target": float(y[i])
            })
        pipe.execute()
        print(f" -> 成功上传 {len(X_scaled)} 条样本到 Redis Stream: {KEY_DATA}")
    except Exception as e:
        print(f" -> !!! 数据上传失败: {e}")
else:
    print(f" -> 提示: 未找到 {FILE_DATA}，跳过数据上传。")

# ================= 第三步: 发送任务 (Task Channel) =================
print(f"\n>>> [Step 3/3] 发送任务 (指令层)...")
r.delete(KEY_QUEUE) # 清空旧任务
task_count = 0

for line in raw_lines:
    # 智能过滤: 只处理 JSON 格式的行 ({ 开头)
    if line.startswith("{"):
        try:
            t = json.loads(line)
            
            # 自动补全 task_name
            if "task_name" not in t and "model_name" in t:
                t = {
                    "task_name": "train_ml_model",
                    "params": {"model_name": t["model_name"], "model_params": t.get("params", {})}
                }
            
            # 关键：推送到 Redis List
            r.rpush(KEY_QUEUE, json.dumps(t))
            print(f" -> [任务入队] {t.get('task_name')} | Params: {t.get('params')}")
            task_count += 1
        except Exception as e:
            print(f" -> [忽略无效行] {line} | 错误: {e}")

if task_count == 0:
    print(" -> !!! 警告: 未发送任何任务。请检查 before_settings 文件。")
else:
    print(f" -> 共发送 {task_count} 个任务到 Redis List: {KEY_QUEUE}")

# ================= 完成 =================
with open("after_settings", "w") as f:
    f.write(f"{ip}\n{port}\n")
print(f"\n>>> Dispatcher 全部完成。Worker 可连接 IP: {ip}")