FROM ubuntu:22.04

# 1. 系统源换成阿里 (加速基础工具下载)
RUN sed -i s@/archive.ubuntu.com/@/mirrors.aliyun.com/@g /etc/apt/sources.list && \
    sed -i s@/security.ubuntu.com/@/mirrors.aliyun.com/@g /etc/apt/sources.list

ENV DEBIAN_FRONTEND=noninteractive

# 2. 配置 APT 保留缓存 (用于挂载)
RUN rm -f /etc/apt/apt.conf.d/docker-clean && \
    echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

# 3. 安装基础工具
RUN apt-get update && apt-get install -y \
    software-properties-common curl git \
    && rm -rf /var/lib/apt/lists/*

# 4. 【核心】添加官方 Deadsnakes PPA (最全的 Python 源)
#    注意：这需要这台电脑能连通 launchpad.net
RUN add-apt-repository ppa:deadsnakes/ppa -y && \
    apt-get update

# 5. 安装 Worker 自身依赖
RUN apt-get install -y python3-pip \
    && pip3 install redis packaging

# 6. 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 7. 配置 UV 缓存目录
ENV UV_CACHE_DIR="/uv_cache"
RUN mkdir -p /uv_cache

WORKDIR /app
COPY worker.py /app/worker.py

CMD ["python3", "worker.py"]