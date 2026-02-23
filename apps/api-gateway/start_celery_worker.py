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
        f"--concurrency={os.getenv('CELERY_WORKER_CONCURRENCY', '4')}",  # 并发worker数
        "--queues=high_priority,default,low_priority",  # 监听所有队列
        f"--max-tasks-per-child={os.getenv('CELERY_MAX_TASKS_PER_CHILD', '1000')}",  # 每个子进程最多执行任务数
        f"--time-limit={os.getenv('CELERY_WORKER_TIME_LIMIT', '300')}",  # 任务超时时间
        f"--soft-time-limit={os.getenv('CELERY_WORKER_SOFT_TIME_LIMIT', '240')}",  # 软超时
    ])
