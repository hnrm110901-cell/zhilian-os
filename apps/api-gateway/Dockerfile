# 多阶段构建 - 基础镜像
FROM python:3.9-slim as base

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 生产镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装运行时依赖
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 从基础镜像复制已安装的包
COPY --from=base /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=base /usr/local/bin /usr/local/bin

# 复制应用代码
COPY . .

# 创建日志目录，确保 entrypoint 可执行
RUN mkdir -p logs && chmod +x docker-entrypoint.sh

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -sf http://localhost:8000/api/v1/health || exit 1

# 启动命令：先初始化 DB，再启动 uvicorn
CMD ["bash", "docker-entrypoint.sh", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
