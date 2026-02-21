# 企业账号OAuth登录配置指南

智链OS支持通过企业微信、飞书、钉钉进行OAuth登录，用户可以使用企业账号直接登录系统，无需单独注册。

## 功能特性

- ✅ 企业微信OAuth登录
- ✅ 飞书OAuth登录
- ✅ 钉钉OAuth登录
- ✅ 自动创建用户账户
- ✅ 基于职位/部门的角色自动映射
- ✅ 用户信息自动同步

## 配置步骤

### 1. 企业微信配置

#### 1.1 创建企业微信应用

1. 登录[企业微信管理后台](https://work.weixin.qq.com/)
2. 进入"应用管理" -> "自建" -> "创建应用"
3. 填写应用信息并创建
4. 记录以下信息：
   - Corp ID (企业ID)
   - Agent ID (应用ID)
   - Secret (应用密钥)

#### 1.2 配置OAuth回调地址

在应用设置中，配置"网页授权及JS-SDK"：
- 可信域名：`your-domain.com`
- OAuth2.0网页授权回调域：`your-domain.com`

#### 1.3 配置环境变量

**后端配置** (`apps/api-gateway/.env`):
```bash
WECHAT_CORP_ID=your_corp_id
WECHAT_CORP_SECRET=your_corp_secret
WECHAT_AGENT_ID=your_agent_id
```

**前端配置** (`apps/web/.env`):
```bash
VITE_WECHAT_WORK_CORP_ID=your_corp_id
```

### 2. 飞书配置

#### 2.1 创建飞书应用

1. 登录[飞书开放平台](https://open.feishu.cn/)
2. 进入"开发者后台" -> "创建企业自建应用"
3. 填写应用信息并创建
4. 记录以下信息：
   - App ID (应用ID)
   - App Secret (应用密钥)

#### 2.2 配置权限和回调地址

1. 在"权限管理"中添加以下权限：
   - 获取用户基本信息
   - 获取用户邮箱
   - 获取用户手机号
2. 在"安全设置"中配置重定向URL：
   - `http://localhost:5173/login` (开发环境)
   - `https://your-domain.com/login` (生产环境)

#### 2.3 配置环境变量

**后端配置** (`apps/api-gateway/.env`):
```bash
FEISHU_APP_ID=your_app_id
FEISHU_APP_SECRET=your_app_secret
```

**前端配置** (`apps/web/.env`):
```bash
VITE_FEISHU_APP_ID=your_app_id
```

### 3. 钉钉配置

#### 3.1 创建钉钉应用

1. 登录[钉钉开放平台](https://open-dev.dingtalk.com/)
2. 进入"应用开发" -> "企业内部开发" -> "创建应用"
3. 填写应用信息并创建
4. 记录以下信息：
   - AppKey (应用Key)
   - AppSecret (应用密钥)

#### 3.2 配置权限和回调地址

1. 在"权限管理"中添加以下权限：
   - 成员信息读权限
   - 通讯录只读权限
2. 在"登录与分享"中配置回调域名：
   - `your-domain.com`

#### 3.3 配置环境变量

**后端配置** (`apps/api-gateway/.env`):
```bash
DINGTALK_APP_KEY=your_app_key
DINGTALK_APP_SECRET=your_app_secret
```

**前端配置** (`apps/web/.env`):
```bash
VITE_DINGTALK_APP_KEY=your_app_key
```

### 4. OAuth回调地址配置

**后端配置** (`apps/api-gateway/.env`):
```bash
OAUTH_REDIRECT_URI=http://localhost:5173/login  # 开发环境
# OAUTH_REDIRECT_URI=https://your-domain.com/login  # 生产环境
```

## 角色映射规则

系统会根据用户在企业平台中的职位和部门自动分配角色：

### 管理员 (admin)
- 职位包含：总经理、CEO、CTO、COO、CFO、总监、VP
- 部门包含：管理层、高管

### 店长 (store_manager)
- 职位包含：店长、经理、主管
- 部门包含：门店、店铺

### 员工 (staff)
- 其他所有用户默认为员工角色

## API端点

### 企业微信OAuth回调
```
POST /api/v1/auth/oauth/wechat-work/callback
Content-Type: application/json

{
  "code": "oauth_code_from_wechat",
  "state": "redirect_path"
}
```

### 飞书OAuth回调
```
POST /api/v1/auth/oauth/feishu/callback
Content-Type: application/json

{
  "code": "oauth_code_from_feishu",
  "state": "redirect_path"
}
```

### 钉钉OAuth回调
```
POST /api/v1/auth/oauth/dingtalk/callback
Content-Type: application/json

{
  "auth_code": "oauth_code_from_dingtalk",
  "state": "redirect_path"
}
```

## 登录流程

1. 用户点击"企业微信登录"/"飞书登录"/"钉钉登录"按钮
2. 跳转到对应平台的授权页面
3. 用户在企业平台授权
4. 平台回调到前端，携带授权码
5. 前端将授权码发送到后端
6. 后端获取用户信息并创建/更新账户
7. 返回JWT令牌
8. 前端保存令牌并跳转到主页

## 用户信息同步

首次登录时，系统会自动创建用户账户并同步以下信息：
- 用户名 (username)
- 邮箱 (email)
- 姓名 (full_name)
- 手机号 (mobile)
- 角色 (role) - 根据职位/部门自动映射
- 头像 (avatar)

后续登录时，系统会自动更新用户信息。

## 安全说明

1. **密钥保护**: 所有API密钥和Secret应妥善保管，不要提交到代码仓库
2. **HTTPS**: 生产环境必须使用HTTPS协议
3. **回调验证**: 后端会验证OAuth回调的state参数，防止CSRF攻击
4. **令牌管理**: JWT令牌有效期为30分钟，刷新令牌有效期为7天

## 故障排查

### 问题1: OAuth授权失败
- 检查Corp ID/App ID/App Key是否正确
- 检查Secret/App Secret是否正确
- 检查回调地址是否配置正确
- 检查应用权限是否已授权

### 问题2: 用户信息获取失败
- 检查应用是否有获取用户信息的权限
- 检查access_token是否有效
- 查看后端日志获取详细错误信息

### 问题3: 角色映射不正确
- 检查用户在企业平台的职位和部门信息
- 修改`enterprise_oauth_service.py`中的`_determine_role`方法调整映射规则

## 开发测试

开发环境下，可以使用以下方式测试OAuth登录：

1. 使用企业平台提供的测试账号
2. 配置本地回调地址（需要内网穿透工具如ngrok）
3. 查看浏览器开发者工具的Network面板，检查OAuth流程

## 参考文档

- [企业微信OAuth文档](https://developer.work.weixin.qq.com/document/path/91335)
- [飞书OAuth文档](https://open.feishu.cn/document/common-capabilities/sso/api/get-user-info)
- [钉钉OAuth文档](https://open.dingtalk.com/document/orgapp/tutorial-obtaining-user-personal-information)
