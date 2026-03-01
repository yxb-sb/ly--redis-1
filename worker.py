import os
import sys
import subprocess
import time
import json
import shutil
from pathlib import Path
import redis
import tempfile
from packaging import version
from packaging.requirements import Requirement

# === 容器内路径 ===
WORKER_BASE_DIR = Path("/app/workspace")
WORKER_BASE_DIR.mkdir(exist_ok=True)
DEFAULT_VENV_PATH = WORKER_BASE_DIR / "default_venv"


def install_python_via_apt(ver):
    """
    通过 APT 动态安装 Python。
    因为挂载了宿主机的 apt_cache，如果包已存在，
    APT 会直接校验并解压，速度极快 (3-5秒)。
    """
    target_bin = f"/usr/bin/python{ver}"
    if os.path.exists(target_bin):
        return target_bin

    print(f">>> [Docker] 正在安装 Python {ver} (检查本地 .deb 缓存)...")
    
    # 构造命令: 安装解释器 + venv模块 + dev开发头文件
    # update 是必须的，但因为挂载了 lists 缓存，也会很快
    pkg = f"python{ver}"
    cmd = f"apt-get update && apt-get install -y {pkg} {pkg}-venv {pkg}-dev"
    
    try:
        # 这里只发生解压和配置，不发生编译
        subprocess.run(cmd, shell=True, check=True)
        print(f"    ✔ Python {ver} 安装/解压完成")
        return target_bin
    except subprocess.CalledProcessError:
        raise RuntimeError(f"APT 安装失败，请检查网络或源配置")

def resolve_python_interpreter(version_req):
    if version_req in ("default", "", None):
        return sys.executable
    ver = version_req.replace("python", "").replace("py", "").strip()
    return install_python_via_apt(ver)

def check_requirements_satisfied(python_exe, libs):
    if not libs: return True
    try:
        res = subprocess.run(
            ["uv", "pip", "list", "--python", python_exe, "--format=json"], 
            capture_output=True, text=True, check=True
        )
        installed = {p['name'].lower(): p['version'] for p in json.loads(res.stdout)}
    except: return False

    for lib in libs:
        try:
            req = Requirement(lib)
            if req.name.lower() not in installed: return False
            if not req.specifier.contains(version.parse(installed[req.name.lower()]), prereleases=True): return False
        except: return False
    return True

def create_venv_and_install(venv_path, base_python, libs):
    if not venv_path.exists():
        print(f"  → [容器] 创建 venv: {venv_path}")
        subprocess.run(["uv", "venv", str(venv_path), "--python", base_python, "--allow-existing"], check=True)
    if libs:
        print(f"  → [容器] 安装依赖: {len(libs)} 个")
        subprocess.run(["uv", "pip", "install"] + libs + ["--python", str(venv_path)], check=True)

def run_task_code(python_exe, code, timeout=60):
    start_time = time.time()
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(code)
        script_path = f.name
    
    result_data = {}
    try:
        cmd_python = str(python_exe)
        # 修正 venv 路径
        if Path(cmd_python).is_dir():
            cmd_python = str(Path(cmd_python) / "bin" / "python")

        res = subprocess.run([cmd_python, script_path], capture_output=True, text=True, timeout=timeout, env=os.environ.copy())
        
        if "---RESULT_START---" in res.stdout:
            try:
                json_part = res.stdout.split("---RESULT_START---")[1].split("---RESULT_END---")[0]
                result_data = json.loads(json_part)
                result_data["status"] = "success" if "error" not in result_data else "error"
            except Exception as e: result_data = {"status": "parse_error", "error": str(e), "raw": res.stdout}
        else: result_data = {"status": "crash", "stderr": res.stderr, "stdout": res.stdout}
    except subprocess.TimeoutExpired: result_data = {"status": "timeout"}
    except Exception as e: result_data = {"status": "sys_error", "error": str(e)}
    finally:
        if os.path.exists(script_path): os.remove(script_path)
    result_data["execution_time"] = round(time.time() - start_time, 3)
    return result_data

def load_redis_config():
    config_path = Path("/app/after_settings")
    if not config_path.exists(): sys.exit(f"错误: 容器内未找到 {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    return lines[0], int(lines[1])

def main():
    try:
        REDIS_HOST, REDIS_PORT = load_redis_config()
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        r.ping()
    except Exception as e:
        sys.exit(f"Redis 连接失败: {e}")

    print(f"\nWorker (Docker APT 缓存版) 启动 | Redis: {REDIS_HOST}")

    while True:
        try:
            # 阻塞等待任务
            data = r.blpop("task_queue", timeout=5)
            if not data: continue
            
            _, msg = data
            task = json.loads(msg)
            t_id = task.get("id", "unk")
            req_ver = task.get("python_executable", "default")
            
            print(f">>> 领取任务: {task.get('task_name')} (Py: {req_ver})")

            # 1. 准备 Python (APT动态)
            base_python = resolve_python_interpreter(req_ver)
            
            # 2. 准备运行环境
            libs = task.get("libs", [])
            need_venv = not check_requirements_satisfied(base_python, libs)
            target_python = base_python
            venv_path = None

            if need_venv:
                if req_ver not in ("default", "", None):
                    venv_path = WORKER_BASE_DIR / f"tmp_{t_id}"
                else:
                    venv_path = DEFAULT_VENV_PATH
                create_venv_and_install(venv_path, base_python, libs)
                target_python = venv_path / "bin" / "python"
            
            # 3. 执行任务
            result = run_task_code(target_python, task.get("code", ""), task.get("options", {}).get("timeout", 60))
            result["task_id"] = t_id
            result["task_name"] = task.get("task_name")

            if result.get("status") == "success":
                print(f"    ✔ 完成 (MSE: {result.get('mse_score', 'N/A')})")
            else:
                print(f"    ✖ 失败: {result.get('error') or result.get('stderr')}")

            r.rpush("result_queue", json.dumps(result))
            
            # 4. 清理环境
            if need_venv and venv_path and venv_path.exists():
                shutil.rmtree(venv_path, ignore_errors=True)

            print(">>> 任务结束，容器 Worker 退出。")
            sys.exit(0)

        except Exception as e:
            print(f"[Error] {e}"); sys.exit(1)

if __name__ == "__main__":
    main()