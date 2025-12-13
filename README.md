# ly--redis-1
这是一个基于 **Redis Streams** 构建的分布式/并行机器学习实验框架。该项目演示了如何使用 Redis 作为消息中间件，将数据集分发给多个不同的算法模型（Worker），并行进行训练和评估，最后统一收集实验结果。

├── Dispatcher.py            # [生产者] 启动 Redis，读取 CSV，将数据写入 Stream

├── run_all.py               # [启动器] 一键并行启动所有算法 Worker

├── worker_rf.py             # [消费者] 随机森林算法 Worker

├── worker_svr.py            # [消费者] 支持向量机算法 Worker

├── worker_lr.py             # [消费者] 线性回归算法 Worker

├── Result Collector.py      # [收集器] 读取实验结果，保存 JSON，关闭 Redis

└── training_results.json    # [输出] 最终生成的实验报告

### 第一步：分发数据 (Dispatcher)
运行调度器。它会尝试在本地启动一个 Redis 实例（端口 11451），读取 CSV 数据并推送到 Redis Stream 中。

```bash
python Dispatcher.py
```
> **输出示例**: `<img width="743" height="44" alt="image" src="https://github.com/user-attachments/assets/3ad286ad-0543-485d-9ffd-0630886544fe" />


### 第二步：并行训练 (Workers)
运行启动脚本。它会自动寻找并并行启动三个算法 Worker (`rf`, `svr`, `lr`)。每个 Worker 会独立消费完整的数据副本进行训练。

python run_all.py

<img width="382" height="210" alt="image" src="https://github.com/user-attachments/assets/85fad240-a436-4b54-aaac-9f5c6030102b" />
<img width="643" height="150" alt="image" src="https://github.com/user-attachments/assets/f3729fcc-bfed-4c3e-8135-2be6fa64ca81" />



### 第三步：收集结果 (Collector)
待所有 Worker 运行结束后，运行收集器。它会从 Redis 获取 MSE 结果，保存为 JSON 文件，并关闭 Redis 服务。
<img width="585" height="151" alt="image" src="https://github.com/user-attachments/assets/f281c6d2-2618-4c8c-9d15-1ad04c51de8a" />




## ⚙️ 核心逻辑说明

### 1. 生产者-消费者模型
*   **Dispatcher** 处理数据（本组为演示只进行归一化）将数据写入 `tasks_stream`。
*   **Stream header**: 第一条消息包含特征名称 (`feature_names`)。
*   **Stream samples**: 后续消息包含归一化后的特征值 (`feature_values`) 和目标值 (`target`)。

### 2. 广播机制 (Fan-out)
为了让三个不同的算法都在**同一份数据**上进行训练，我们利用了 Redis Consumer Groups 的特性：
*   每个 Worker 脚本使用**独立的 Group Name** (例如 `group_rf`, `group_svr`)。
*   这确保了 Redis 会将流中的每一条消息都完整地分发给每个算法，而不是在算法之间进行负载均衡。

### 3. 游标重置
Worker 脚本中包含 `BUSYGROUP` 异常处理逻辑。如果实验重复运行，它会强制将消费者组的游标重置为 `0`，确保算法每次都能获取到从头开始的完整历史数据。

### 4. 自动化管理
*   `Dispatcher` 负责自动启动 `redis-server` 进程。
*   `Result Collector` 负责在收集完结果后发送 `SHUTDOWN` 命令关闭 Redis，保持环境整洁。
