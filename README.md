# 智链OS (Zhilian OS)

> 中餐连锁品牌门店运营智能体智链操作系统

## 项目简介

智链OS 是一款基于企业微信/飞书，集成门店预定、排位、等位、点单、结账、会员、评价、服务、绩效多业务管理系统的智能体操作系统。采用"路线B - AI智能中间层"架构，通过6大核心Agent实现餐饮门店的智能化运营。

## 核心特性

### 🤖 7大核心Agent

1. **智能排班Agent** - 基于客流预测和员工技能的自动排班
2. **订单协同Agent** - 预定、排位、等位、点单、结账全流程管理
3. **库存预警Agent** - 实时监控、智能预测、自动补货建议
4. **服务质量Agent** - 评价分析、服务监控、质量改进
5. **培训辅导Agent** - 智能问答、培训推荐、知识管理
6. **决策支持Agent** - 数据分析、经营洞察、预测优化
7. **预定宴会Agent** - 预定管理、宴会管理、座位分配、提醒通知

### 🧠 神经系统

智链OS神经系统是餐饮门店的智能中枢，提供：

- **五大核心维度**: 订单、菜品、人员、时间、金额的标准化Schema
- **语义搜索**: 基于向量数据库的自然语言搜索能力
- **联邦学习**: 跨门店知识共享，数据隔离架构保护隐私
- **事件驱动**: 实时事件处理和智能协调

详细文档：
- [神经系统实现报告](./NEURAL_SYSTEM_IMPLEMENTATION.md)
- [神经系统快速开始](./NEURAL_SYSTEM_QUICKSTART.md)

### 🎤 语音交互

支持Shokz骨传导耳机深度集成：

- **OpenComm 2**: 前厅/收银语音交互
- **OpenRun Pro 2**: 后厨语音交互
- **智能路由**: 基于角色的语音命令路由
- **多语言支持**: 中文、英文语音识别和合成

详细文档：[Shokz集成报告](./SHOKZ_INTEGRATION_REPORT.md)

### 🔐 企业账号OAuth登录

支持企业微信、飞书、钉钉OAuth登录：

- **企业微信**: 企业员工一键登录
- **飞书**: 飞书企业账号登录
- **钉钉**: 钉钉企业账号登录
- **自动创建账户**: 首次登录自动创建用户
- **角色自动映射**: 根据职位/部门自动分配角色

详细文档：[OAuth配置指南](./docs/OAUTH_SETUP.md)

### 🏗️ 三层架构

```
企业微信/飞书层
    ↓
AI智能中间层 (智链OS)
    ↓
业务系统层 (奥琦韦、品智等)
```

### 🎯 目标品牌

达登饭店、海底捞、西贝、巴奴、鼎泰丰、费大厨、徐记海鲜等连锁餐饮品牌

## 技术栈

### 后端
- **框架**: FastAPI (Python 3.11+)
- **AI框架**: LangChain + LangGraph
- **RAG**: LlamaIndex
- **数据库**: PostgreSQL + Redis
- **向量数据库**: Qdrant
- **任务队列**: Celery
- **消息队列**: Redis

### 前端
- **框架**: React 18 + TypeScript
- **UI库**: Ant Design Pro
- **图表**: ECharts
- **状态管理**: Zustand
- **构建工具**: Vite

### DevOps
- **容器化**: Docker + Docker Compose
- **编排**: Kubernetes
- **CI/CD**: GitHub Actions
- **监控**: Prometheus + Grafana
- **日志**: ELK Stack

## 项目结构

```
zhilian-os/
├── apps/                      # 应用层
│   ├── web/                   # 管理后台 (React)
│   ├── api-gateway/           # API网关 (FastAPI)
│   └── wechat-service/        # 企业微信服务
├── packages/                  # 共享包
│   ├── agents/                # 7大核心Agent
│   │   ├── schedule/          # 智能排班Agent
│   │   ├── order/             # 订单协同Agent
│   │   ├── inventory/         # 库存预警Agent
│   │   ├── service/           # 服务质量Agent
│   │   ├── training/          # 培训辅导Agent
│   │   ├── decision/          # 决策支持Agent
│   │   └── reservation/       # 预定宴会Agent
│   ├── api-adapters/          # API适配器
│   │   ├── base/              # 基础适配器
│   │   ├── aoqiwei/           # 奥琦韦适配器
│   │   ├── pinzhi/            # 品智适配器
│   │   └── yiding/            # 易订适配器
│   ├── llm-core/              # LLM核心封装
│   ├── shared/                # 共享工具
│   └── types/                 # TypeScript类型定义
├── docs/                      # 文档
├── scripts/                   # 脚本
└── README.md
```

## 快速开始

### 环境要求

- Node.js >= 18.0.0
- Python >= 3.11
- pnpm >= 8.0.0
- Docker >= 24.0.0
- PostgreSQL >= 15.0
- Redis >= 7.0

### 安装依赖

```bash
# 安装前端依赖
pnpm install

# 安装Python依赖
cd apps/api-gateway
pip install -r requirements.txt
```

### 环境配置

复制环境变量模板并配置：

```bash
cp .env.example .env
```

配置以下环境变量：
- `DATABASE_URL`: PostgreSQL连接字符串
- `REDIS_URL`: Redis连接字符串
- `OPENAI_API_KEY`: OpenAI API密钥
- `WECHAT_CORP_ID`: 企业微信CorpID
- `WECHAT_CORP_SECRET`: 企业微信Secret
- `FEISHU_APP_ID`: 飞书应用ID
- `FEISHU_APP_SECRET`: 飞书应用密钥
- `DINGTALK_APP_KEY`: 钉钉应用Key
- `DINGTALK_APP_SECRET`: 钉钉应用密钥
- `AOQIWEI_APP_KEY`: 奥琦韦应用Key
- `PINZHI_TOKEN`: 品智Token

### 启动开发环境

```bash
# 启动基础设施 (PostgreSQL, Redis, Qdrant)
docker-compose up -d

# 初始化神经系统
cd apps/api-gateway
python scripts/init_neural_system.py

# 启动所有服务
pnpm dev

# 或分别启动
pnpm --filter web dev          # 前端
pnpm --filter api-gateway dev  # 后端
```

### 运行测试

```bash
pnpm test

# API Gateway 迁移链和数据库升级验证
make migrate-verify
```

如果本地历史开发库 `zhilian_os` 已经落后当前模型和迁移链，建议直接：

```bash
make dev-db-backup
make dev-db-rebuild
```

相关文档：
- [API Gateway 迁移验证](./apps/api-gateway/MIGRATION_VALIDATION.md)
- [开发库恢复指南](./apps/api-gateway/DEV_DB_RECOVERY.md)

## 开发指南

### 代码规范

- 使用 ESLint + Prettier 进行代码格式化
- 遵循 TypeScript 严格模式
- 编写单元测试（覆盖率 > 80%）
- 提交前运行 `pnpm lint` 和 `pnpm test`

### Git工作流

1. 从 `main` 分支创建功能分支
2. 开发并提交代码
3. 创建 Pull Request
4. 代码审查通过后合并

### 提交规范

使用 Conventional Commits 规范：

```
feat: 新功能
fix: 修复bug
docs: 文档更新
style: 代码格式调整
refactor: 重构
test: 测试相关
chore: 构建/工具相关
```

## 部署

### Docker部署

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d
```

### Kubernetes部署

```bash
# 应用配置
kubectl apply -f k8s/

# 查看状态
kubectl get pods -n zhilian-os
```

## 文档

- [架构设计](./docs/architecture.md)
- [API文档](./docs/api-spec.md)
- [部署指南](./docs/deployment.md)
- [开发指南](./docs/development.md)

## 路线图

### Phase 1: MVP (Week 1-4)
- [x] 项目初始化
- [x] API适配器开发 (易订适配器)
- [x] 智能排班Agent
- [x] 订单协同Agent
- [x] 预定宴会Agent
- [x] API Gateway集成

### Phase 2: 核心功能 (Week 5-8)
- [x] 库存预警Agent
- [x] 服务质量Agent
- [x] 培训辅导Agent
- [x] 决策支持Agent
- [x] 管理后台开发
- [x] 企业微信/飞书集成
- [x] OAuth登录（企业微信、飞书、钉钉）
- [x] Shokz耳机权限配置
- [x] 多渠道通知服务（短信、企业微信）

### Phase 3: 优化上线 (Week 9-12)
- [x] 性能优化（GZip压缩、Redis缓存TTL、K8s HPA弹性伸缩）
- [x] 安全加固（安全响应头中间件、CORS精确配置、SSL/TLS Nginx）
- [x] 生产部署（K8s全套配置、Prometheus告警规则、Alembic迁移体系）
- [x] 用户培训（docs/user-training-guide.md）

## 贡献

欢迎贡献代码、报告问题或提出建议！

## 许可证

MIT License

## 联系方式

- 项目主页: https://github.com/zhilian-os/zhilian-os
- 问题反馈: https://github.com/zhilian-os/zhilian-os/issues
- 邮箱: dev@zhilian-os.com

---

**智链OS开发团队** © 2026
