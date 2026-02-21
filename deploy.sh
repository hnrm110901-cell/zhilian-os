#!/bin/bash

# 智链OS生产环境部署脚本
# 使用方法: ./deploy.sh [start|stop|restart|status|logs]

set -e

PROJECT_DIR="/opt/zhilian-os"
DOCKER_COMPOSE_FILE="docker-compose.prod.yml"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查Docker是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker未安装，请先安装Docker"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose未安装，请先安装Docker Compose"
        exit 1
    fi
}

# 检查环境变量文件
check_env_files() {
    if [ ! -f "apps/web/.env.production" ]; then
        log_warn "前端环境变量文件不存在，从示例文件复制"
        cp apps/web/.env.production.example apps/web/.env.production
        log_warn "请编辑 apps/web/.env.production 填入正确的配置"
    fi

    if [ ! -f "apps/api-gateway/.env.production" ]; then
        log_warn "后端环境变量文件不存在，从示例文件复制"
        cp apps/api-gateway/.env.production.example apps/api-gateway/.env.production
        log_warn "请编辑 apps/api-gateway/.env.production 填入正确的配置"
    fi
}

# 启动服务
start_services() {
    log_info "启动智链OS服务..."
    check_docker
    check_env_files

    docker-compose -f $DOCKER_COMPOSE_FILE up -d

    log_info "等待服务启动..."
    sleep 10

    log_info "检查服务状态..."
    docker-compose -f $DOCKER_COMPOSE_FILE ps

    log_info "服务启动完成！"
    log_info "前端访问地址: http://localhost"
    log_info "API访问地址: http://localhost:8000"
}

# 停止服务
stop_services() {
    log_info "停止智链OS服务..."
    docker-compose -f $DOCKER_COMPOSE_FILE down
    log_info "服务已停止"
}

# 重启服务
restart_services() {
    log_info "重启智链OS服务..."
    stop_services
    start_services
}

# 查看服务状态
show_status() {
    log_info "智链OS服务状态:"
    docker-compose -f $DOCKER_COMPOSE_FILE ps
}

# 查看日志
show_logs() {
    log_info "查看智链OS服务日志 (Ctrl+C退出):"
    docker-compose -f $DOCKER_COMPOSE_FILE logs -f
}

# 构建镜像
build_images() {
    log_info "构建Docker镜像..."
    docker-compose -f $DOCKER_COMPOSE_FILE build --no-cache
    log_info "镜像构建完成"
}

# 更新部署
update_deployment() {
    log_info "更新智链OS部署..."

    # 拉取最新代码
    log_info "拉取最新代码..."
    git pull origin main

    # 构建新镜像
    build_images

    # 重启服务
    restart_services

    log_info "更新部署完成！"
}

# 备份数据
backup_data() {
    log_info "备份智链OS数据..."

    BACKUP_DIR="./backups"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/zhilian_os_backup_$TIMESTAMP.tar.gz"

    mkdir -p $BACKUP_DIR

    # 备份配置文件
    tar -czf $BACKUP_FILE \
        apps/web/.env.production \
        apps/api-gateway/.env.production \
        logs/

    log_info "备份完成: $BACKUP_FILE"
}

# 健康检查
health_check() {
    log_info "执行健康检查..."

    # 检查前端
    if curl -f http://localhost > /dev/null 2>&1; then
        log_info "✓ 前端服务正常"
    else
        log_error "✗ 前端服务异常"
    fi

    # 检查API
    if curl -f http://localhost:8000/api/v1/health > /dev/null 2>&1; then
        log_info "✓ API服务正常"
    else
        log_error "✗ API服务异常"
    fi
}

# 主函数
main() {
    case "$1" in
        start)
            start_services
            ;;
        stop)
            stop_services
            ;;
        restart)
            restart_services
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs
            ;;
        build)
            build_images
            ;;
        update)
            update_deployment
            ;;
        backup)
            backup_data
            ;;
        health)
            health_check
            ;;
        *)
            echo "使用方法: $0 {start|stop|restart|status|logs|build|update|backup|health}"
            echo ""
            echo "命令说明:"
            echo "  start   - 启动服务"
            echo "  stop    - 停止服务"
            echo "  restart - 重启服务"
            echo "  status  - 查看服务状态"
            echo "  logs    - 查看服务日志"
            echo "  build   - 构建Docker镜像"
            echo "  update  - 更新部署"
            echo "  backup  - 备份数据"
            echo "  health  - 健康检查"
            exit 1
            ;;
    esac
}

main "$@"
