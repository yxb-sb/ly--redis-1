# ly--redis-1
这是一个基于 **Redis Streams** 构建的分布式/并行机器学习实验框架。该项目演示了如何使用 Redis 作为消息中间件，将数据集分发给多个不同的运算子（Worker），并行进行训练和评估，最后统一收集实验结果。

├── Dispatcher.py            # [生产者] 启动 Redis，读取 CSV，读取before_settings，将数据写入 Stream,将预期算法同样写入队列

├── worker.py             # [消费者]拉取队列中的一个任务，并读取数据，将结果发送回队列

├── before_settings      # [任务版] 记载要处理的任务等

├── Result_Collector.py      # [收集器] 读取实验结果，保存 JSON，关闭 Redis

├── task_definitions.py      # [词典] 储存对不同任务的处理代码

└── training_results.json    # [输出] 最终生成的实验报告

### 第一步：分发数据 (Dispatcher)
运行调度器。它会尝试在本地启动一个 Redis 实例（端口 11451），也有可能会使用已有redis，读取 CSV 数据并推送到 Redis Stream 中，同时把任务发送到队列总。

```bash
python Dispatcher.py
```
> **输出示例**: `<img width="743" height="44" alt="image" src="https://github.com/user-attachments/assets/3ad286ad-0543-485d-9ffd-0630886544fe" />


### 第二步：并行训练 (Workers)
运行启动脚本。它会自动拉取队列中的一个任务开始执行。





### 第三步：收集结果 (Collector)
待所有 Worker 运行结束后，运行收集器。它会从 Redis 获取 MSE 结果，保存为 JSON 文件，并关闭 Redis 服务。
<img width="585" height="151" alt="image" src="https://github.com/user-attachments/assets/f281c6d2-2618-4c8c-9d15-1ad04c51de8a" />




## ⚙️ 核心逻辑说明

### 1. 生产者-消费者模型
*   **Dispatcher** 处理数据（本组为演示只进行归一化）将数据写入 `tasks_stream`。
*   **Stream header**: 第一条消息包含特征名称 (`feature_names`)。
*   **Stream samples**: 后续消息包含归一化后的特征值 (`feature_values`) 和目标值 (`target`)。

### 2. 广播机制 (Fan-out)

*   这确保了 Redis 会将流中的每一条消息都完整地分发给每个算法，而不是在算法之间进行负载均衡。

### 3. 游标重置
Worker 脚本中包含 `BUSYGROUP` 异常处理逻辑。如果实验重复运行，它会强制将消费者组的游标重置为 `0`，确保算法每次都能获取到从头开始的完整历史数据。

### 4. 自动化管理
*   `Dispatcher` 负责自动启动 `redis-server` 进程。
*   `Result Collector` 负责在收集完结果后发送 `SHUTDOWN` 命令关闭 Redis，保持环境整洁。

### 5.任务
*   现阶段只模拟了四种任务
1. 基础连通性任务 (`simple_add`)
*   模拟内容**: CPU 纯计算（极轻量）。
*   逻辑**: 接收两个数字 `a` 和 `b`，返回它们的和。
*   测试目的**:
    *   验证“代码通道”**: Worker 能否成功下载并加载 `task_definitions.py`。
    *   验证“指令通道”**: Worker 能否收到 JSON 任务并解析参数。
    *   不依赖数据**: 即使 Redis Stream 里的 CSV 数据上传失败，这个任务也能跑通。

2. 数据通道验证任务 (`get_data_info`) —— *新增*
*   模拟内容**: I/O 密集型操作 + 基础统计。
*   逻辑**:
    1.  连接 Redis Stream (`tasks_stream`)。
    2.  下载所有训练数据。
    3.  统计样本数量（行数）、特征数量（列数）。
    4.  计算目标变量（Target）的平均值。
*   测试目的**:
    *   验证“数据通道”**: 确保 Dispatcher 成功把 CSV 塞进了 Redis，且 Worker 能通过网络把数据拉下来。
    *   排查故障**: 如果这个任务报错（如 `No data`），说明 CSV 上传环节挂了，不用去跑后面的机器学习了。

3. 数据预处理/分析任务
这部分任务模拟了“在训练前对数据进行清洗或分析”的场景。
*   任务 A: 特征重要性测试 (`shuffle_feature_test`)**
    *   逻辑**: 随机打乱某一列特征（破坏其携带的信息），观察与目标变量的相关性下降了多少。
    *   模拟**: 数据增强、敏感性分析。
*   任务 B: 降维分析 (`pca_feature_extract`)**
    *   逻辑**: 使用 PCA（主成分分析）算法将 13 维特征压缩成 2 维或 3 维。
    *   模拟**: 数学运算密集的预处理步骤。
      
4.核心业务任务 (`train_ml_model`)
*   模拟内容**: 综合性负载（I/O + CPU + 内存）。
*   逻辑**:
    1.  从 Redis 拉取完整数据。
    2.  根据参数实例化不同的模型（线性回归 `LinearRegression` 或 随机森林 `RandomForest`）。
    3.  执行 `fit()` 训练。
    4.  执行 `predict()` 预测并计算 MSE（均方误差）。
*   测试目的**:
    *   模拟真实的生产环境负载。
    *   测试 Worker 所在机器是否安装了必要的库 (`sklearn`, `numpy`)。
