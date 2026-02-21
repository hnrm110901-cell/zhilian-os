#!/bin/bash
# Celery Beat启动脚本
# 用于启动定时任务调度器

# 设置工作目录
cd "$(dirname "$0")/.." || exit

# 启动Celery Beat
celery -A src.core.celery_app beat \
    --loglevel=info \
    --logfile=logs/celery_beat.log \
    --pidfile=logs/celery_beat.pid \
    --schedule=logs/celerybeat-schedule.db

# 说明:
# - beat: 启动Celery Beat调度器
# - --loglevel=info: 设置日志级别
# - --logfile: 日志文件路径
# - --pidfile: PID文件路径
# - --schedule: 调度数据库文件路径
