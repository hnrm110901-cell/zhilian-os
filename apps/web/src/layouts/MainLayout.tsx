import React, { useState, useEffect } from 'react';
import { Layout, Menu, theme, Dropdown, Avatar, Space, Tag, Breadcrumb, Badge, Tooltip, Button } from 'antd';
import type { MenuProps } from 'antd';
import {
  DashboardOutlined,
  ScheduleOutlined,
  ShoppingCartOutlined,
  InboxOutlined,
  CustomerServiceOutlined,
  ReadOutlined,
  BarChartOutlined,
  CalendarOutlined,
  UserOutlined,
  LogoutOutlined,
  SettingOutlined,
  TeamOutlined,
  ApiOutlined,
  LineChartOutlined,
  MobileOutlined,
  ShopOutlined,
  ShoppingOutlined,
  MonitorOutlined,
  DatabaseOutlined,
  BellOutlined,
  DollarOutlined,
  FileTextOutlined,
  FileExcelOutlined,
  HomeOutlined,
  BulbOutlined,
  BulbFilled,
  SearchOutlined,
  RiseOutlined,
  GlobalOutlined,
  SafetyOutlined,
  CheckCircleOutlined,
  RobotOutlined,
  CloudOutlined,
  ExperimentOutlined,
  ApartmentOutlined,
  AppstoreOutlined,
  TranslationOutlined,
  ExportOutlined,
  SyncOutlined,
  SoundOutlined,
  ToolOutlined,
  UploadOutlined,
  TrophyOutlined,
  HistoryOutlined,
  WarningOutlined,
  FireOutlined,
  PieChartOutlined,
  UnorderedListOutlined,
  FundOutlined,
  ControlOutlined,
  UsergroupAddOutlined,
  NodeIndexOutlined,
  RocketOutlined,
  HeartOutlined,
} from '@ant-design/icons';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { GlobalSearch } from '../components/GlobalSearch';
import { useKeyboardShortcuts } from '../hooks/useKeyboardShortcuts';

const { Header, Content, Sider } = Layout;

// ── 路由 → 新 6 分组 key 的映射 ───────────────────────────────────────────────
const ROUTE_TO_GROUP: Record<string, string> = {
  // 01 经营总览
  '/': 'nav-overview',
  '/daily-hub': 'nav-overview',
  '/kpi-dashboard': 'nav-overview',
  '/profit-dashboard': 'nav-overview',
  '/monthly-report': 'nav-overview',
  '/forecast': 'nav-overview',
  '/cross-store-insights': 'nav-overview',
  '/hq-dashboard': 'nav-overview',
  '/data-visualization': 'nav-overview',
  '/analytics': 'nav-overview',
  '/decision-stats': 'nav-overview',
  '/competitive-analysis': 'nav-overview',
  '/report-templates': 'nav-overview',
  '/finance': 'nav-overview',

  // 02 门店运营
  '/ops-hub': 'nav-operations',
  '/schedule': 'nav-operations',
  '/employees': 'nav-operations',
  '/my-schedule': 'nav-operations',
  '/queue': 'nav-operations',
  '/meituan-queue': 'nav-operations',
  '/reservation': 'nav-operations',
  '/pos': 'nav-operations',
  '/service': 'nav-operations',
  '/quality': 'nav-operations',
  '/compliance': 'nav-operations',
  '/human-in-the-loop': 'nav-operations',
  '/tasks': 'nav-operations',
  '/ops-agent': 'nav-operations',
  '/voice-devices': 'nav-operations',
  '/employee-performance': 'nav-operations',

  // 03 商品与供应链
  '/products-hub': 'nav-products',
  '/dishes': 'nav-products',
  '/bom-management': 'nav-products',
  '/inventory': 'nav-products',
  '/order': 'nav-products',
  '/waste-reasoning': 'nav-products',
  '/waste-events': 'nav-products',
  '/supply-chain': 'nav-products',
  '/dish-cost': 'nav-products',
  '/alert-thresholds': 'nav-products',
  '/reconciliation': 'nav-products',
  '/dynamic-pricing': 'nav-products',

  // 04 会员与增长
  '/marketing':       'nav-crm',
  '/crm-hub': 'nav-crm',
  '/members': 'nav-crm',
  '/customer360': 'nav-crm',
  '/private-domain': 'nav-crm',
  '/channel-profit': 'nav-crm',
  '/recommendations': 'nav-crm',
  '/wechat-triggers': 'nav-crm',

  // 05 智能体中心
  '/agent-hub': 'nav-agents',
  '/decision': 'nav-agents',
  '/training': 'nav-agents',
  '/ai-evolution': 'nav-agents',
  '/ai-accuracy': 'nav-agents',
  '/governance': 'nav-agents',
  '/agent-collaboration': 'nav-agents',
  '/agent-memory': 'nav-agents',
  '/knowledge-rules': 'nav-agents',
  '/decision-validator': 'nav-agents',
  '/edge-node': 'nav-agents',
  '/federated-learning': 'nav-agents',
  '/neural': 'nav-agents',
  '/embedding': 'nav-agents',
  '/vector-index': 'nav-agents',
  '/event-sourcing': 'nav-agents',
  '/voice-ws': 'nav-agents',

  // 06 平台与治理 (admin only)
  '/platform-hub': 'nav-platform',
  '/users': 'nav-platform',
  '/stores': 'nav-platform',
  '/multi-store': 'nav-platform',
  '/approval': 'nav-platform',
  '/approval-list': 'nav-platform',
  '/audit': 'nav-platform',
  '/data-security': 'nav-platform',
  '/integrations': 'nav-platform',
  '/adapters': 'nav-platform',
  '/enterprise': 'nav-platform',
  '/llm-config': 'nav-platform',
  '/model-marketplace': 'nav-platform',
  '/hardware': 'nav-platform',
  '/monitoring': 'nav-platform',
  '/system-health': 'nav-platform',
  '/scheduler': 'nav-platform',
  '/backup': 'nav-platform',
  '/export-jobs': 'nav-platform',
  '/data-import-export': 'nav-platform',
  '/bulk-import': 'nav-platform',
  '/open-platform': 'nav-platform',
  '/developer-docs': 'nav-platform',
  '/isv-ecosystem': 'nav-platform',
  '/isv-management': 'nav-platform',
  '/plugin-marketplace': 'nav-platform',
  '/revenue-share': 'nav-platform',
  '/isv-dashboard': 'nav-platform',
  '/platform-analytics': 'nav-platform',
  '/webhook-management': 'nav-platform',
  '/api-billing':        'nav-platform',
  '/developer-console':  'nav-platform',
  '/business-events':    'nav-overview',
  '/cfo-dashboard':      'nav-overview',
  '/settlement-risk':    'nav-overview',
  '/ceo-dashboard':      'nav-overview',
  '/budget-management':  'nav-overview',
  '/financial-alerts':   'nav-overview',
  '/finance-health':     'nav-overview',
  '/financial-forecast': 'nav-overview',
  '/financial-anomaly':  'nav-overview',
  '/performance-ranking':      'nav-overview',
  '/financial-recommendation': 'nav-overview',
  '/dish-profitability': 'nav-overview',
  '/menu-optimization': 'nav-overview',
  '/dish-cost-alert': 'nav-overview',
  '/dish-benchmark': 'nav-overview',
  '/dish-pricing': 'nav-overview',
  '/dish-lifecycle': 'nav-overview',
  '/dish-forecast': 'nav-overview',
  '/dish-health': 'nav-overview',
  '/industry-solutions': 'nav-platform',
  '/i18n': 'nav-platform',
  '/raas': 'nav-platform',
  '/benchmark': 'nav-platform',

  // 角色视图（顶栏入口，不在侧边栏）
  '/hq': '',
  '/sm': '',
  '/chef': '',
  '/floor': '',
  '/profile': '',
};

// ── 面包屑 label 映射 ─────────────────────────────────────────────────────────
const BREADCRUMB_LABELS: Record<string, string> = {
  '/': '经营总览',
  '/daily-hub': '经营作战台',
  '/kpi-dashboard': 'KPI看板',
  '/profit-dashboard': '成本率分析',
  '/monthly-report': '月度经营报告',
  '/forecast': '需求预测',
  '/cross-store-insights': '跨门店洞察',
  '/hq-dashboard': '总部看板',
  '/data-visualization': '数据大屏',
  '/analytics': '高级分析',
  '/decision-stats': '决策统计',
  '/competitive-analysis': '竞争分析',
  '/report-templates': '报表模板',
  '/finance': '财务管理',
  '/products-hub': '商品与供应链中心',
  '/schedule': '智能排班',
  '/employees': '员工管理',
  '/my-schedule': '我的班表',
  '/queue': '排队管理',
  '/meituan-queue': '美团排队',
  '/reservation': '预订宴会',
  '/pos': 'POS系统',
  '/service': '服务质量',
  '/quality': '质量管理',
  '/compliance': '合规管理',
  '/human-in-the-loop': '人工审批',
  '/tasks': '任务管理',
  '/ops-agent': 'IT运维Agent',
  '/voice-devices': '语音设备',
  '/employee-performance': '员工绩效',
  '/dishes': '菜品管理',
  '/bom-management': 'BOM配方',
  '/inventory': '库存管理',
  '/order': '订单协同',
  '/waste-reasoning': '损耗分析',
  '/waste-events': '损耗事件',
  '/supply-chain': '供应链管理',
  '/dish-cost': '菜品成本',
  '/alert-thresholds': '告警阈值',
  '/reconciliation': '对账管理',
  '/dynamic-pricing': '动态定价',
  '/members': '会员中心',
  '/crm-hub': '会员与增长中心',
  '/marketing': '营销智能体',
  '/customer360': '客户360',
  '/private-domain': '私域运营',
  '/channel-profit': '渠道毛利',
  '/recommendations': '推荐引擎',
  '/wechat-triggers': '企微触发器',
  '/agent-hub': '智能体总览',
  '/decision': '决策支持',
  '/training': '培训辅导',
  '/ai-evolution': 'AI进化看板',
  '/ai-accuracy': 'AI准确率',
  '/governance': 'AI治理看板',
  '/agent-collaboration': 'Agent协作',
  '/agent-memory': '智能体记忆',
  '/knowledge-rules': '知识规则库',
  '/decision-validator': '决策验证',
  '/edge-node': '边缘节点',
  '/federated-learning': '联邦学习',
  '/neural': '神经系统',
  '/embedding': '嵌入模型',
  '/vector-index': '向量知识库',
  '/event-sourcing': '事件溯源',
  '/voice-ws': '语音WebSocket',
  '/users': '用户管理',
  '/platform-hub': '平台与治理中心',
  '/stores': '门店管理',
  '/multi-store': '多门店管理',
  '/approval': '审批管理',
  '/approval-list': '审批列表',
  '/audit': '审计日志',
  '/data-security': '数据安全',
  '/integrations': '外部集成',
  '/adapters': '适配器管理',
  '/enterprise': '企业集成',
  '/llm-config': 'LLM配置',
  '/model-marketplace': '模型市场',
  '/hardware': '硬件管理',
  '/monitoring': '系统监控',
  '/system-health': '系统健康',
  '/scheduler': '调度管理',
  '/backup': '数据备份',
  '/export-jobs': '导出任务',
  '/data-import-export': '数据导入导出',
  '/bulk-import': '数据导入',
  '/open-platform': '开放平台',
  '/developer-docs': '开发者文档',
  '/isv-ecosystem': 'ISV 生态招募',
  '/isv-management': 'ISV 管理后台',
  '/plugin-marketplace': '插件市场',
  '/revenue-share': '收入分成管理',
  '/isv-dashboard': 'ISV 开发者看板',
  '/platform-analytics': '平台商业化总览',
  '/webhook-management': 'Webhook 事件订阅',
  '/api-billing':        'API 计量计费',
  '/developer-console':  'ISV 开发者控制台',
  '/business-events':    '经营事件中心',
  '/cfo-dashboard':      'CFO 工作台',
  '/settlement-risk':    '结算风控',
  '/ceo-dashboard':      'CEO 驾驶舱',
  '/budget-management':  '预算管理',
  '/financial-alerts':   '财务预警',
  '/finance-health':     '财务健康评分',
  '/financial-forecast': '财务预测',
  '/financial-anomaly':  '财务异常检测',
  '/performance-ranking':      '财务对标排名',
  '/financial-recommendation': '财务智能建议',
  '/dish-profitability': '菜品盈利分析',
  '/menu-optimization': '菜单优化建议',
  '/dish-cost-alert': '菜品成本预警',
  '/dish-benchmark': '跨店菜品对标',
  '/dish-pricing': '菜品智能定价',
  '/dish-lifecycle': '菜品生命周期',
  '/dish-forecast': '菜品销售预测',
  '/dish-health': '菜品健康评分',
  '/industry-solutions': '行业解决方案',
  '/i18n': '国际化',
  '/raas': 'RaaS定价',
  '/benchmark': '基准测试',
  '/hq': '总部大屏',
  '/sm': '店长移动端',
  '/chef': '厨师长看板',
  '/floor': '楼面经理看板',
  '/profile': '个人信息',
  '/notifications': '通知中心',
};

const MainLayout: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);
  const [searchVisible, setSearchVisible] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { isDark, toggleTheme } = useTheme();
  const { token: { colorBgContainer, borderRadiusLG } } = theme.useToken();

  const isAdmin = user?.role === 'admin';

  // 当前路由对应的分组 key
  const currentGroup = ROUTE_TO_GROUP[location.pathname] ?? '';

  const [openKeys, setOpenKeys] = useState<string[]>(() =>
    currentGroup ? [currentGroup] : []
  );

  useEffect(() => {
    if (currentGroup) {
      setOpenKeys(prev => prev.includes(currentGroup) ? prev : [...prev, currentGroup]);
    }
  }, [currentGroup]);

  // ── 全局快捷键 ──────────────────────────────────────────────────────────────
  useKeyboardShortcuts([
    { key: 'k', ctrl: true, callback: () => setSearchVisible(true),    description: '打开搜索' },
    { key: 't', ctrl: true, shift: true, callback: toggleTheme,        description: '切换主题' },
    { key: 'h', ctrl: true, callback: () => navigate('/'),             description: '返回首页' },
    { key: 'n', ctrl: true, callback: () => navigate('/notifications'), description: '打开通知' },
  ]);

  // ── 角色 badge ──────────────────────────────────────────────────────────────
  const roleMap: Record<string, { text: string; color: string }> = {
    admin:         { text: '管理员', color: 'red' },
    store_manager: { text: '店长',   color: 'blue' },
    manager:       { text: '经理',   color: 'blue' },
    staff:         { text: '员工',   color: 'green' },
    waiter:        { text: '服务员', color: 'green' },
  };

  // ── 角色视图（顶栏 dropdown）──────────────────────────────────────────────
  const roleViewItems: MenuProps['items'] = [
    { key: '/sm',    icon: <MobileOutlined />,   label: '店长首页' },
    { key: '/chef',  icon: <TeamOutlined />,     label: '厨师长看板' },
    { key: '/floor', icon: <HomeOutlined />,     label: '楼面经理看板' },
    ...(isAdmin ? [{ key: '/hq', icon: <ShopOutlined />, label: '总部大屏' }] : []),
  ];

  // ── 用户菜单 ────────────────────────────────────────────────────────────────
  const userMenuItems: MenuProps['items'] = [
    { key: 'profile', icon: <UserOutlined />, label: '个人信息' },
    { key: 'settings', icon: <SettingOutlined />, label: '设置' },
    { type: 'divider' },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
  ];

  const handleUserMenuClick: MenuProps['onClick'] = ({ key }) => {
    if (key === 'logout') { logout(); navigate('/login'); }
    else if (key === 'profile') { navigate('/profile'); }
  };

  // ── 6 大一级导航 ────────────────────────────────────────────────────────────
  const menuItems: MenuProps['items'] = [

    // 01 经营总览
    {
      key: 'nav-overview',
      icon: <FundOutlined />,
      label: '经营总览',
      children: [
        { key: '/',                    icon: <DashboardOutlined />,  label: '经营作战台' },
        { key: '/daily-hub',           icon: <RiseOutlined />,       label: '明日备战板' },
        { key: '/kpi-dashboard',       icon: <BarChartOutlined />,   label: 'KPI看板' },
        { key: '/profit-dashboard',    icon: <LineChartOutlined />,  label: '成本率分析' },
        { key: '/monthly-report',      icon: <FileTextOutlined />,   label: '月度经营报告' },
        { key: '/decision-stats',      icon: <PieChartOutlined />,   label: '决策统计' },
        { key: '/forecast',            icon: <LineChartOutlined />,  label: '需求预测' },
        { key: '/cross-store-insights',icon: <GlobalOutlined />,     label: '跨门店洞察' },
        { key: '/competitive-analysis',icon: <RiseOutlined />,       label: '竞争分析' },
        { key: '/hq-dashboard',        icon: <ShopOutlined />,       label: '总部看板' },
        { key: '/data-visualization',  icon: <MonitorOutlined />,    label: '数据大屏' },
        { key: '/finance',             icon: <DollarOutlined />,     label: '财务管理' },
        { key: '/business-events',     icon: <NodeIndexOutlined />,  label: '经营事件中心' },
        { key: '/cfo-dashboard',        icon: <DollarOutlined />,     label: 'CFO 工作台' },
        { key: '/settlement-risk',      icon: <SafetyOutlined />,     label: '结算风控' },
        { key: '/ceo-dashboard',        icon: <FundOutlined />,       label: 'CEO 驾驶舱' },
        { key: '/budget-management',    icon: <DollarOutlined />,     label: '预算管理' },
        { key: '/financial-alerts',     icon: <BellOutlined />,       label: '财务预警' },
        { key: '/finance-health',        icon: <FundOutlined />,       label: '财务健康评分' },
        { key: '/financial-forecast',    icon: <LineChartOutlined />,  label: '财务预测' },
        { key: '/financial-anomaly',     icon: <WarningOutlined />,    label: '财务异常检测' },
        { key: '/performance-ranking',   icon: <TrophyOutlined />,     label: '财务对标排名' },
        { key: '/financial-recommendation', icon: <BulbOutlined />,    label: '财务智能建议' },
        { key: '/dish-profitability',      icon: <PieChartOutlined />, label: '菜品盈利分析' },
        { key: '/menu-optimization',       icon: <BulbOutlined />,    label: '菜单优化建议' },
        { key: '/dish-cost-alert',         icon: <WarningOutlined />, label: '菜品成本预警' },
        { key: '/dish-benchmark',           icon: <TrophyOutlined />, label: '跨店菜品对标' },
        { key: '/dish-pricing',             icon: <DollarOutlined />, label: '菜品智能定价' },
        { key: '/dish-lifecycle',           icon: <HistoryOutlined />, label: '菜品生命周期' },
        { key: '/dish-forecast',            icon: <LineChartOutlined />, label: '菜品销售预测' },
        { key: '/dish-health',              icon: <HeartOutlined />, label: '菜品健康评分' },
      ],
    },

    // 02 门店运营
    {
      key: 'nav-operations',
      icon: <ShopOutlined />,
      label: '门店运营',
      children: [
        { key: '/ops-hub',           icon: <AppstoreOutlined />,       label: '运营中心' },
        { key: '/schedule',          icon: <ScheduleOutlined />,      label: '智能排班' },
        { key: '/employees',         icon: <TeamOutlined />,          label: '员工管理' },
        { key: '/my-schedule',       icon: <CalendarOutlined />,      label: '我的班表' },
        { key: '/employee-performance', icon: <TrophyOutlined />,     label: '员工绩效' },
        { key: '/queue',             icon: <TeamOutlined />,          label: '排队管理' },
        { key: '/meituan-queue',     icon: <SyncOutlined />,          label: '美团排队' },
        { key: '/reservation',       icon: <CalendarOutlined />,      label: '预订宴会' },
        { key: '/pos',               icon: <ShoppingCartOutlined />,  label: 'POS系统' },
        { key: '/service',           icon: <CustomerServiceOutlined />,label: '服务质量' },
        { key: '/quality',           icon: <CheckCircleOutlined />,   label: '质量管理' },
        { key: '/compliance',        icon: <SafetyOutlined />,        label: '合规管理' },
        { key: '/human-in-the-loop', icon: <CheckCircleOutlined />,   label: '人工审批' },
        { key: '/tasks',             icon: <FileTextOutlined />,      label: '任务管理' },
        { key: '/ops-agent',         icon: <ToolOutlined />,          label: 'IT运维Agent' },
        { key: '/voice-devices',     icon: <SoundOutlined />,         label: '语音设备' },
      ],
    },

    // 03 商品与供应链
    {
      key: 'nav-products',
      icon: <InboxOutlined />,
      label: '商品与供应链',
      children: [
        { key: '/products-hub',    icon: <AppstoreOutlined />,  label: '供应链中心' },
        { key: '/dishes',          icon: <ShoppingOutlined />,  label: '菜品管理' },
        { key: '/bom-management',  icon: <ReadOutlined />,      label: 'BOM配方' },
        { key: '/inventory',       icon: <InboxOutlined />,     label: '库存管理' },
        { key: '/order',           icon: <ShoppingCartOutlined />, label: '订单协同' },
        { key: '/waste-reasoning', icon: <FireOutlined />,      label: '损耗分析' },
        { key: '/waste-events',    icon: <WarningOutlined />,   label: '损耗事件' },
        { key: '/dish-cost',       icon: <DollarOutlined />,    label: '菜品成本' },
        { key: '/alert-thresholds',icon: <BellOutlined />,      label: '告警阈值' },
        { key: '/supply-chain',    icon: <ShoppingOutlined />,  label: '供应链管理' },
        { key: '/reconciliation',  icon: <FileExcelOutlined />, label: '对账管理' },
        { key: '/dynamic-pricing', icon: <DollarOutlined />,    label: '动态定价' },
      ],
    },

    // 04 会员与增长
    {
      key: 'nav-crm',
      icon: <UsergroupAddOutlined />,
      label: '会员与增长',
      children: [
        { key: '/crm-hub',          icon: <AppstoreOutlined />,  label: '会员增长中心' },
        { key: '/members',          icon: <UserOutlined />,      label: '会员中心' },
        { key: '/customer360',      icon: <UserOutlined />,      label: '客户360' },
        { key: '/marketing',        icon: <RocketOutlined />,    label: '营销智能体' },
        { key: '/private-domain',   icon: <TeamOutlined />,      label: '私域运营' },
        { key: '/channel-profit',   icon: <ShopOutlined />,      label: '渠道毛利' },
        { key: '/recommendations',  icon: <BulbOutlined />,      label: '推荐引擎' },
        { key: '/wechat-triggers',  icon: <BellOutlined />,      label: '企微触发器' },
      ],
    },

    // 05 智能体中心
    {
      key: 'nav-agents',
      icon: <RobotOutlined />,
      label: '智能体中心',
      children: [
        // 总览
        { key: '/agent-hub',         icon: <AppstoreOutlined />,    label: 'Agent 总览' },
        // Agent 工作台
        { key: '/decision',          icon: <BarChartOutlined />,    label: '经营决策 Agent' },
        { key: '/training',          icon: <ReadOutlined />,        label: '培训管理 Agent' },
        // 配置与治理
        { key: '/agent-collaboration',icon: <ApartmentOutlined />,  label: '协作编排' },
        { key: '/agent-memory',      icon: <DatabaseOutlined />,    label: 'Agent 记忆' },
        { key: '/knowledge-rules',   icon: <DatabaseOutlined />,    label: '知识规则库' },
        { key: '/governance',        icon: <SafetyOutlined />,      label: 'AI 治理看板' },
        { key: '/decision-validator',icon: <CheckCircleOutlined />, label: '决策验证器' },
        { key: '/ai-accuracy',       icon: <BarChartOutlined />,    label: 'AI 准确率' },
        { key: '/ai-evolution',      icon: <RobotOutlined />,       label: 'AI 进化追踪' },
        // 底层技术
        { key: '/edge-node',         icon: <CloudOutlined />,       label: '边缘节点' },
        { key: '/federated-learning',icon: <ExperimentOutlined />,  label: '联邦学习' },
        { key: '/neural',            icon: <ApartmentOutlined />,   label: '神经系统' },
        { key: '/embedding',         icon: <ExperimentOutlined />,  label: '嵌入模型' },
        { key: '/vector-index',      icon: <SearchOutlined />,      label: '向量知识库' },
        { key: '/event-sourcing',    icon: <FileTextOutlined />,    label: '事件溯源' },
        { key: '/voice-ws',          icon: <SoundOutlined />,       label: '语音 WebSocket' },
      ],
    },

    // 06 平台与治理（admin only）
    ...(isAdmin ? [{
      key: 'nav-platform',
      icon: <ControlOutlined />,
      label: '平台与治理',
      children: [
        { key: '/platform-hub',     icon: <AppstoreOutlined />,   label: '治理中心' },
        // 组织与权限
        { key: '/users',            icon: <TeamOutlined />,       label: '用户管理' },
        { key: '/stores',           icon: <ShopOutlined />,       label: '门店管理' },
        { key: '/multi-store',      icon: <ShopOutlined />,       label: '多门店管理' },
        { key: '/approval',         icon: <CheckCircleOutlined />,label: '审批管理' },
        { key: '/approval-list',    icon: <UnorderedListOutlined />,label: '审批列表' },
        { key: '/audit',            icon: <FileTextOutlined />,   label: '审计日志' },
        { key: '/data-security',    icon: <SafetyOutlined />,     label: '数据安全' },
        // 集成与适配
        { key: '/integrations',     icon: <ApiOutlined />,        label: '外部集成' },
        { key: '/adapters',         icon: <ApiOutlined />,        label: '适配器管理' },
        { key: '/enterprise',       icon: <ApiOutlined />,        label: '企业集成' },
        // 模型与知识
        { key: '/llm-config',       icon: <SettingOutlined />,    label: 'LLM配置' },
        { key: '/model-marketplace',icon: <AppstoreOutlined />,   label: '模型市场' },
        { key: '/hardware',         icon: <CloudOutlined />,      label: '硬件管理' },
        // 系统监控
        { key: '/monitoring',       icon: <MonitorOutlined />,    label: '系统监控' },
        { key: '/system-health',    icon: <MonitorOutlined />,    label: '系统健康' },
        { key: '/scheduler',        icon: <CalendarOutlined />,   label: '调度管理' },
        { key: '/benchmark',        icon: <BarChartOutlined />,   label: '基准测试' },
        // 数据与配置
        { key: '/backup',           icon: <DatabaseOutlined />,   label: '数据备份' },
        { key: '/export-jobs',      icon: <ExportOutlined />,     label: '导出任务' },
        { key: '/data-import-export',icon: <FileExcelOutlined />, label: '数据导入导出' },
        { key: '/bulk-import',      icon: <UploadOutlined />,     label: '批量导入' },
        { key: '/report-templates', icon: <FileTextOutlined />,   label: '报表模板' },
        { key: '/raas',             icon: <DollarOutlined />,     label: 'RaaS定价' },
        { key: '/open-platform',    icon: <AppstoreOutlined />,   label: '开放平台' },
        { key: '/developer-docs',   icon: <FileTextOutlined />,   label: '开发者文档' },
        { key: '/isv-ecosystem',    icon: <RocketOutlined />,     label: 'ISV 生态招募' },
        { key: '/isv-management',   icon: <TeamOutlined />,       label: 'ISV 管理后台' },
        { key: '/plugin-marketplace', icon: <AppstoreOutlined />,  label: '插件市场' },
        { key: '/revenue-share',      icon: <DollarOutlined />,    label: '收入分成管理' },
        { key: '/isv-dashboard',      icon: <FundOutlined />,      label: 'ISV 开发者看板' },
        { key: '/platform-analytics', icon: <RiseOutlined />,      label: '平台商业化总览' },
        { key: '/webhook-management', icon: <ApiOutlined />,        label: 'Webhook 事件订阅' },
        { key: '/api-billing',        icon: <DollarOutlined />,     label: 'API 计量计费' },
        { key: '/developer-console',  icon: <FundOutlined />,       label: 'ISV 开发者控制台' },
        { key: '/industry-solutions',icon: <GlobalOutlined />,    label: '行业解决方案' },
        { key: '/i18n',             icon: <TranslationOutlined />,label: '国际化' },
      ],
    } as MenuProps['items'][number]] : []),
  ];

  const handleMenuClick = ({ key }: { key: string }) => {
    navigate(key);
  };

  // ── 面包屑 ──────────────────────────────────────────────────────────────────
  const breadcrumbItems = () => {
    const snippets = location.pathname.split('/').filter(Boolean);
    const extra = snippets.map((_, i) => {
      const url = `/${snippets.slice(0, i + 1).join('/')}`;
      return {
        key: url,
        title: <a onClick={() => navigate(url)}>{BREADCRUMB_LABELS[url] ?? url}</a>,
      };
    });
    return [
      { key: 'home', title: <a onClick={() => navigate('/')}><HomeOutlined /> 首页</a> },
      ...extra,
    ];
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <GlobalSearch visible={searchVisible} onClose={() => setSearchVisible(false)} />

      {/* ── 侧边导航 ──────────────────────────────────────────────────────── */}
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        width={220}
        style={{ overflow: 'auto', height: '100vh', position: 'fixed', left: 0, top: 0, bottom: 0 }}
      >
        {/* Logo */}
        <div style={{
          height: 56,
          display: 'flex',
          alignItems: 'center',
          justifyContent: collapsed ? 'center' : 'flex-start',
          padding: collapsed ? 0 : '0 20px',
          color: 'white',
          fontSize: collapsed ? 20 : 16,
          fontWeight: 700,
          letterSpacing: collapsed ? 0 : 1,
          background: 'rgba(255,255,255,0.06)',
          borderBottom: '1px solid rgba(255,255,255,0.08)',
          transition: 'all 0.2s',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
        }}>
          {collapsed ? '屯' : '🍜 屯象OS'}
        </div>

        <Menu
          theme="dark"
          selectedKeys={[location.pathname]}
          openKeys={collapsed ? [] : openKeys}
          onOpenChange={setOpenKeys}
          mode="inline"
          items={menuItems}
          onClick={handleMenuClick}
          style={{ borderRight: 0, paddingBottom: 24 }}
        />
      </Sider>

      {/* ── 主区域 ─────────────────────────────────────────────────────────── */}
      <Layout style={{ marginLeft: collapsed ? 80 : 220, transition: 'margin-left 0.2s' }}>

        {/* ── 顶部栏 ──────────────────────────────────────────────────────── */}
        <Header style={{
          padding: '0 20px',
          background: colorBgContainer,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
          position: 'sticky',
          top: 0,
          zIndex: 100,
          height: 56,
        }}>
          {/* 左：系统名 */}
          <div style={{ fontSize: 15, fontWeight: 600, color: '#1677ff', letterSpacing: 0.3 }}>
            智链经营助手
          </div>

          {/* 右：工具栏 */}
          <Space size={4}>
            {/* 全局搜索 */}
            <Tooltip title="搜索 (Ctrl+K)">
              <Button type="text" icon={<SearchOutlined />} onClick={() => setSearchVisible(true)} />
            </Tooltip>

            {/* 主题切换 */}
            <Tooltip title={isDark ? '切换亮色' : '切换暗色'}>
              <Button
                type="text"
                icon={isDark ? <BulbFilled style={{ color: '#faad14' }} /> : <BulbOutlined />}
                onClick={toggleTheme}
              />
            </Tooltip>

            {/* 通知 */}
            <Tooltip title="通知中心">
              <Badge count={5} size="small">
                <Button
                  type="text"
                  icon={<BellOutlined style={{ fontSize: 17 }} />}
                  onClick={() => navigate('/notifications')}
                />
              </Badge>
            </Tooltip>

            {/* 角色视图快速切换 */}
            <Dropdown
              menu={{
                items: roleViewItems,
                onClick: ({ key }) => navigate(key),
              }}
              placement="bottomRight"
            >
              <Button type="text" icon={<MobileOutlined />}>
                {!collapsed && <span style={{ fontSize: 13, marginLeft: 2 }}>角色视图</span>}
              </Button>
            </Dropdown>

            {/* 用户菜单 */}
            <Dropdown
              menu={{ items: userMenuItems, onClick: handleUserMenuClick }}
              placement="bottomRight"
            >
              <Space style={{ cursor: 'pointer', padding: '0 4px' }}>
                <Avatar icon={<UserOutlined />} size={30} style={{ backgroundColor: '#1677ff' }} />
                <span style={{ fontSize: 13, fontWeight: 500 }}>{user?.username}</span>
                <Tag color={roleMap[user?.role || 'staff']?.color || 'green'} style={{ margin: 0 }}>
                  {roleMap[user?.role || 'staff']?.text || '员工'}
                </Tag>
              </Space>
            </Dropdown>
          </Space>
        </Header>

        {/* ── 主内容区 ────────────────────────────────────────────────────── */}
        <Content style={{ margin: '12px 16px 0' }}>
          <Breadcrumb
            items={breadcrumbItems()}
            style={{
              marginBottom: 12,
              padding: '6px 16px',
              background: colorBgContainer,
              borderRadius: 8,
              fontSize: 13,
            }}
          />
          <div style={{
            padding: 24,
            minHeight: 360,
            background: colorBgContainer,
            borderRadius: borderRadiusLG,
            boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
          }}>
            <Outlet />
          </div>
        </Content>

        <Layout.Footer style={{ textAlign: 'center', color: '#bbb', fontSize: 12, padding: '12px 0' }}>
          屯象OS ©{new Date().getFullYear()} — 让餐饮管理更智能
        </Layout.Footer>
      </Layout>
    </Layout>
  );
};

export default MainLayout;
