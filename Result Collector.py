import json
from redis import Redis
import subprocess

REDIS_HOST = "127.0.0.1"
REDIS_PORT = 11451
RESULTS_QUEUE = "results"

OUTPUT_FILE = "training_results.json"

r = Redis(host=REDIS_HOST, port=REDIS_PORT)

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

# 关闭 Redis
print("正在关闭 Redis Server...")
subprocess.run(
    ["redis-cli", "-p", str(REDIS_PORT), "shutdown"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL
)

print("Redis 已关闭，流程结束")