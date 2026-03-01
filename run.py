import os
import sys
import subprocess
from pathlib import Path

# === 配置项 ===
IMAGE_NAME = "worker-final-v2"  # 改个名字强制重新构建

# 1. 宿主机上的缓存目录
CACHE_DIR_APT = Path.cwd() / "cache_sys_apt"   # 存 Python 安装包
CACHE_DIR_LISTS = Path.cwd() / "cache_sys_lists" 
CACHE_DIR_PIP = Path.cwd() / "cache_pip_libs"  # 存 Numpy/Pandas 等库

CONFIG_FILE = Path.cwd() / "after_settings"

def ensure_prerequisites():
    if not CONFIG_FILE.exists():
        print(f"错误: 找不到 {CONFIG_FILE}")
        sys.exit(1)
    
    # 创建目录
    CACHE_DIR_APT.mkdir(exist_ok=True)
    CACHE_DIR_LISTS.mkdir(exist_ok=True)
    CACHE_DIR_PIP.mkdir(exist_ok=True)
    
    print(f"[*] 缓存目录检查完毕")

def build_image():
    # 检查镜像是否存在
    try:
        subprocess.run(["docker", "inspect", IMAGE_NAME], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print(f"[*] 正在构建镜像 {IMAGE_NAME}...")
        if not Path("Dockerfile").exists():
            sys.exit("错误: 找不到 Dockerfile")
        try:
            # --no-cache 确保 Dockerfile 的环境变量修改生效
            subprocess.run(["docker", "build", "-t", IMAGE_NAME, "."], check=True)
            print("[*] 构建成功！")
        except subprocess.CalledProcessError:
            sys.exit(1)

def run_container():
    print(f"[*] 启动 Worker...")
    
    cmd = [
        "docker", "run", "--rm",
        # 挂载配置
        "-v", f"{CONFIG_FILE}:/app/after_settings",
        
        # 挂载 APT 缓存 (Python 版本)
        "-v", f"{CACHE_DIR_APT}:/var/cache/apt/archives",
        "-v", f"{CACHE_DIR_LISTS}:/var/lib/apt/lists",
        
        # ========================================================
        # 【核心修复】挂载 UV 缓存 (通用库)
        # 宿主机: CACHE_DIR_PIP  ->  容器: /uv_cache (必须与 Dockerfile 中的 ENV 一致)
        "-v", f"{CACHE_DIR_PIP}:/uv_cache",
        # ========================================================
        
        IMAGE_NAME
    ]
    
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n[!] 用户停止")
    except subprocess.CalledProcessError:
        print("\n[!] 容器异常退出")

if __name__ == "__main__":
    ensure_prerequisites()
    build_image()
    run_container()
