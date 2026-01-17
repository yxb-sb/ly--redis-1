import redis
import json
import os
import sys
import socket

SETTINGS_FILE = "after_settings"
RESULTS_QUEUE = "results"
OUTPUT_FILE = "final_results.json"

def get_local_ip():
    """获取本机局域网 IP"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 连接一个公共 DNS，不需要真的连通，只是为了获取路由接口 IP
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def main():
    # 1. 读取连接配置
    if not os.path.exists(SETTINGS_FILE):
        print(f"错误: 找不到 {SETTINGS_FILE}")
        sys.exit(1)
        
    with open(SETTINGS_FILE, "r") as f:
        lines = [l.strip() for l in f if l.strip()]
    
    redis_ip = lines[0]
    redis_port = int(lines[1])
    
    print(f"正在连接 Redis ({redis_ip}:{redis_port})...")
    
    try:
        r = redis.Redis(host=redis_ip, port=redis_port, socket_timeout=5)
        r.ping()
    except Exception as e:
        print(f"连接 Redis 失败: {e}")
        sys.exit(1)

    # 2. 拉取所有结果
    print("正在拉取结果队列...")
    results = []
    while True:
        # 使用 lpop 逐个取出，相当于"剪切"出来
        item = r.lpop(RESULTS_QUEUE)
        if not item:
            break
        try:
            results.append(json.loads(item))
        except:
            print(f"跳过无法解析的数据: {item}")

    if not results:
        print("警告: 结果队列为空，没有数据被保存。")
    else:
        # 3. 保存到文件
        with open(OUTPUT_FILE, "w", encoding='utf-8') as f:
            json.dump(results, f, indent=4, ensure_ascii=False)
        print(f"成功保存 {len(results)} 条结果到 '{OUTPUT_FILE}'")

    # 4. 判断并关闭 Redis
    local_ip = get_local_ip()
    
    # 判断逻辑：如果是本机IP，或者是回环地址
    is_local = (redis_ip == local_ip) or (redis_ip in ["127.0.0.1", "localhost", "0.0.0.0"])
    
    print(f"---------------------------")
    print(f"本机 IP: {local_ip}")
    print(f"Redis IP: {redis_ip}")
    
    if is_local:
        print("检测到 Redis 运行在本地，正在执行关闭操作...")
        try:
            r.shutdown()
        except redis.ConnectionError:
            # shutdown 后连接断开是正常的
            print("Redis 服务已成功关闭。")
        except Exception as e:
            print(f"关闭 Redis 失败: {e}")
    else:
        print("Redis 运行在远程机器，保持运行状态，仅断开连接。")

if __name__ == "__main__":
    main()