#!/usr/bin/env python
"""
Celery Worker启动脚本（v2.0 多Worker模式）

通过 WORKER_TYPE 环境变量选择 Worker 角色：
  WORKER_TYPE=realtime   → 仅监听 high_priority 队列（低并发、快响应）
  WORKER_TYPE=default    → 仅监听 default 队列（标准业务逻辑）
  WORKER_TYPE=batch      → 仅监听 low_priority 队列（高并发、长时限）
  WORKER_TYPE=all        → 监听所有队列（单机开发/小规模部署兼容）

不设置 WORKER_TYPE 时默认 all，保持向后兼容。

示例（Docker Compose）：
  celery-realtime:
    command: python start_celery_worker.py
    environment:
      WORKER_TYPE: realtime

  celery-default:
    command: python start_celery_worker.py
    environment:
      WORKER_TYPE: default
      CELERY_WORKER_CONCURRENCY: 6

  celery-batch:
    command: python start_celery_worker.py
    environment:
      WORKER_TYPE: batch
      CELERY_WORKER_TIME_LIMIT: 14400
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.celery_app import celery_app

# ── Worker 角色配置 ──
WORKER_PROFILES = {
    "realtime": {
        "queues": "high_priority",
        "concurrency": os.getenv("CELERY_WORKER_CONCURRENCY", "2"),
        "time_limit": os.getenv("CELERY_WORKER_TIME_LIMIT", "60"),
        "soft_time_limit": os.getenv("CELERY_WORKER_SOFT_TIME_LIMIT", "45"),
        "max_tasks_per_child": os.getenv("CELERY_MAX_TASKS_PER_CHILD", "500"),
        "hostname": "realtime@%h",
    },
    "default": {
        "queues": "default",
        "concurrency": os.getenv("CELERY_WORKER_CONCURRENCY", "6"),
        "time_limit": os.getenv("CELERY_WORKER_TIME_LIMIT", "300"),
        "soft_time_limit": os.getenv("CELERY_WORKER_SOFT_TIME_LIMIT", "240"),
        "max_tasks_per_child": os.getenv("CELERY_MAX_TASKS_PER_CHILD", "1000"),
        "hostname": "default@%h",
    },
    "batch": {
        "queues": "low_priority",
        "concurrency": os.getenv("CELERY_WORKER_CONCURRENCY", "3"),
        "time_limit": os.getenv("CELERY_WORKER_TIME_LIMIT", "14400"),  # 4小时
        "soft_time_limit": os.getenv("CELERY_WORKER_SOFT_TIME_LIMIT", "14100"),
        "max_tasks_per_child": os.getenv("CELERY_MAX_TASKS_PER_CHILD", "100"),
        "hostname": "batch@%h",
    },
    "all": {
        "queues": "high_priority,default,low_priority",
        "concurrency": os.getenv("CELERY_WORKER_CONCURRENCY", "4"),
        "time_limit": os.getenv("CELERY_WORKER_TIME_LIMIT", "300"),
        "soft_time_limit": os.getenv("CELERY_WORKER_SOFT_TIME_LIMIT", "240"),
        "max_tasks_per_child": os.getenv("CELERY_MAX_TASKS_PER_CHILD", "1000"),
        "hostname": "all@%h",
    },
}

if __name__ == "__main__":
    worker_type = os.getenv("WORKER_TYPE", "all").lower()

    if worker_type not in WORKER_PROFILES:
        print(f"错误: WORKER_TYPE={worker_type!r} 不合法，可选: {list(WORKER_PROFILES.keys())}")
        sys.exit(1)

    profile = WORKER_PROFILES[worker_type]
    print(f"启动 Celery Worker [{worker_type}] → 队列: {profile['queues']}, 并发: {profile['concurrency']}")

    celery_app.worker_main([
        "worker",
        "--loglevel=info",
        f"--concurrency={profile['concurrency']}",
        f"--queues={profile['queues']}",
        f"--max-tasks-per-child={profile['max_tasks_per_child']}",
        f"--time-limit={profile['time_limit']}",
        f"--soft-time-limit={profile['soft_time_limit']}",
        f"--hostname={profile['hostname']}",
    ])
