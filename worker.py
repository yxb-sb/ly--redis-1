import json
import redis
import numpy as np
import os
import sys
# 引入常用的 sklearn 模型，建立映射以便动态调用
from sklearn.linear_model import LinearRegression, Ridge, Lasso, ElasticNet
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.svm import SVR
from sklearn.tree import DecisionTreeRegressor
from sklearn.neighbors import KNeighborsRegressor
from sklearn.metrics import mean_squared_error, r2_score

# ================= 配置常量 =================

SETTINGS_FILE = "after_settings"
STREAM_KEY = "tasks_stream"
ALGO_QUEUE_KEY = "algorithms_queue" # 现在这里面存的是 JSON 字符串
RESULTS_QUEUE = "results"

# ================= 模型注册表 =================
# 为了安全起见，建立一个字符串到类的映射，而不是使用 eval
MODEL_REGISTRY = {
    "LinearRegression": LinearRegression,
    "Ridge": Ridge,
    "Lasso": Lasso,
    "ElasticNet": ElasticNet,
    "RandomForest": RandomForestRegressor,
    "GradientBoosting": GradientBoostingRegressor,
    "SVR": SVR,
    "DecisionTree": DecisionTreeRegressor,
    "KNN": KNeighborsRegressor,
    "SVM": SVR
}

# ================= 核心封装类 =================

class ModelTrainer:
    """
    通用模型训练器
    负责解析配置、实例化模型、训练及评估
    """
    def __init__(self, task_config):
        """
        :param task_config: 字典，包含 {"model_name": str, "params": dict}
        """
        self.model_name = task_config.get("model_name")
        self.params = task_config.get("params", {}) # 默认为空字典
        self.model = self._build_model()

    def _build_model(self):
        """根据名称和参数动态实例化模型"""
        if self.model_name not in MODEL_REGISTRY:
            raise ValueError(f"不支持的模型类型: {self.model_name}。支持列表: {list(MODEL_REGISTRY.keys())}")
        
        model_class = MODEL_REGISTRY[self.model_name]
        
        try:
            # 这里的 **self.params 就是将字典解包传参
            # 例如: RandomForestRegressor(n_estimators=100, max_depth=5)
            return model_class(**self.params)
        except TypeError as e:
            raise ValueError(f"参数错误，模型 {self.model_name} 不接受某些参数: {e}")

    def run(self, X, y):
        """执行训练和评估流程"""
        # 1. 训练
        self.model.fit(X, y)
        
        # 2. 预测
        pred = self.model.predict(X)
        
        # 3. 评估
        mse = mean_squared_error(y, pred)
        r2 = r2_score(y, pred)
        
        return {
            "algorithm": self.model_name,
            "params": self.params, # 把参数也回传，方便分析哪个参数效果好
            "mse": mse,
            "r2_score": r2,
            "status": "success"
        }

# ================= 工具函数 =================

def read_redis_config():
    """读取 after_settings 获取 IP 和 端口"""
    if not os.path.exists(SETTINGS_FILE):
        print(f"错误：找不到配置文件 {SETTINGS_FILE}。")
        sys.exit(1)
    
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
        
    if len(lines) < 2:
        print("错误：配置文件格式不对")
        sys.exit(1)
        
    return lines[0], int(lines[1])

def fetch_training_data(r):
    """从 Redis Stream 读取数据"""
    print("正在从 Stream 读取数据...")
    stream_data = r.xrange(STREAM_KEY, min='-', max='+')
    
    X = []
    y = []
    
    if not stream_data:
        return np.array([]), np.array([])

    for _, data in stream_data:
        msg_type = data.get(b'type').decode()
        if msg_type == 'sample':
            features = json.loads(data.get(b'feature_values').decode())
            target = float(data.get(b'target').decode())
            X.append(features)
            y.append(target)
            
    return np.array(X), np.array(y)

# ================= 主流程 =================

def main():
    host, port = read_redis_config()
    print(f"Worker 启动 (通用模式)，连接 Redis: {host}:{port}")
    
    try:
        r = redis.Redis(host=host, port=port)
        r.ping()
    except Exception as e:
        print(f"连接 Redis 失败: {e}")
        return

    # 1. 尝试领取任务
    raw_item = r.lpop(ALGO_QUEUE_KEY)
    
    if raw_item is None:
        print("当前队列无任务，退出。")
        return

    # 2. 解析任务 (现在是一个 JSON 结构，包含模型名和参数)
    try:
        task_config = json.loads(raw_item)
        print(f"\n>>> 收到任务配置: {task_config}")
    except json.JSONDecodeError:
        print("错误：任务格式不是有效的 JSON。")
        return

    # 3. 加载数据
    X, y = fetch_training_data(r)
    if len(X) == 0:
        print("警告：无训练数据。")
        return

    # 4. 执行封装的训练流程
    try:
        # 实例化 Trainer
        trainer = ModelTrainer(task_config)
        
        # 运行训练并获取结果
        result_data = trainer.run(X, y)
        
        print(f"训练完成 | MSE: {result_data['mse']:.4f} | R2: {result_data['r2_score']:.4f}")
        
        # 回传结果
        r.rpush(RESULTS_QUEUE, json.dumps(result_data))
        print("结果已回传。")
        
    except Exception as e:
        print(f"执行任务失败: {e}")
        error_data = {
            "algorithm": task_config.get("model_name", "Unknown"),
            "params": task_config.get("params", {}),
            "status": "error",
            "error_msg": str(e)
        }
        r.rpush(RESULTS_QUEUE, json.dumps(error_data))

if __name__ == "__main__":
    main()

