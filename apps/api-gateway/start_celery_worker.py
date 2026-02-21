#!/usr/bin/env python
"""
Celery Worker启动脚本
用于启动Celery worker处理Neural System的异步任务
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.celery_app import celery_app

if __name__ == "__main__":
    # 启动Celery worker
    celery_app.worker_main([
        "worker",
        "--loglevel=info",
        "--concurrency=4",  # 4个并发worker
        "--queues=high_priority,default,low_priority",  # 监听所有队列
        "--max-tasks-per-child=1000",  # 每个子进程最多执行1000个任务
        "--time-limit=300",  # 任务超时时间5分钟
        "--soft-time-limit=240",  # 软超时4分钟
    ])
