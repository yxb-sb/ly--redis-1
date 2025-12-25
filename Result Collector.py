import json
from redis import Redis
import subprocess
import socket

# --- 步骤 1：读取 after_settings 文件 ---
SETTINGS_FILE = "after_settings"

try:
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
        # 移除空行并获取前两行
        valid_lines = [line.strip() for line in lines if line.strip()]
        if len(valid_lines) < 2:
            raise ValueError("after_settings 文件格式错误：需要至少两行（IP和端口）")
        
        REDIS_HOST = valid_lines[0]
        REDIS_PORT = int(valid_lines[1])
except FileNotFoundError:
    print(f"错误：未找到配置文件 {SETTINGS_FILE}")
    exit(1)
except Exception as e:
    print(f"读取配置出错: {e}")
    exit(1)

RESULTS_QUEUE = "results"
OUTPUT_FILE = "training_results.json"

# 连接 Redis
try:
    r = Redis(host=REDIS_HOST, port=REDIS_PORT)
    # 测试连接是否通畅
    r.ping()
except Exception as e:
    print(f"无法连接到 Redis ({REDIS_HOST}:{REDIS_PORT}): {e}")
    exit(1)

print(f"成功连接 Redis: {REDIS_HOST}:{REDIS_PORT}")
print("开始读取 results 队列...")

results = []

while True:
    item = r.lpop(RESULTS_QUEUE)
    if item is None:
        break
    results.append(json.loads(item.decode()))

print(f"共收集 {len(results)} 条结果")

# 保存到文件
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"结果已保存到 {OUTPUT_FILE}")

# 确保队列已清空
r.delete(RESULTS_QUEUE)

# --- 步骤 2：获取本机 IP 并判断是否关闭 ---

def get_local_ip():
    """获取本机真实 IP（非 0.0.0.0）"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 不需要实际连接，只是申请路由来确定出口 IP
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        # 如果没有网络连接，回退到本地回环
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

local_ip = get_local_ip()
print(f"检测到本机 IP: {local_ip}")

# 判断逻辑：
# 1. 配置文件里的 IP 等于 get_local_ip() 获取的 IP
# 2. 或者配置文件写的是本地回环地址 (127.0.0.1, localhost, 0.0.0.0)
is_local_target = (REDIS_HOST == local_ip) or (REDIS_HOST in ["127.0.0.1", "localhost", "0.0.0.0"])

if is_local_target:
    print(f"Redis 地址 ({REDIS_HOST}) 判定为本机，正在关闭 Redis Server...")
    # 使用 -h 指定 host，防止 REDIS_HOST 为局域网 IP 时默认 shutdown 127.0.0.1 失败
    subprocess.run(
        ["redis-cli", "-h", REDIS_HOST, "-p", str(REDIS_PORT), "shutdown"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    print("Redis 已关闭，流程结束")
else:
    print(f"Redis 地址 ({REDIS_HOST}) 与本机 IP ({local_ip}) 不一致，跳过关闭操作，流程结束")
