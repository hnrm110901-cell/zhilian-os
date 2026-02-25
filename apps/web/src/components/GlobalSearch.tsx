import React, { useState, useEffect, useRef } from 'react';
import { Modal, Input, List, Tag, Space, Empty } from 'antd';
import {
  SearchOutlined,
  DashboardOutlined,
  ScheduleOutlined,
  ShoppingCartOutlined,
  InboxOutlined,
  CustomerServiceOutlined,
  ReadOutlined,
  BarChartOutlined,
  CalendarOutlined,
  TeamOutlined,
  ApiOutlined,
  FileTextOutlined,
  ShopOutlined,
  DollarOutlined,
  MonitorOutlined,
  DatabaseOutlined,
  FileExcelOutlined,
  RiseOutlined,
  LineChartOutlined,
  GlobalOutlined,
  SafetyOutlined,
  BulbOutlined,
  UserOutlined,
  RobotOutlined,
  CloudOutlined,
  ExperimentOutlined,
  ApartmentOutlined,
  AppstoreOutlined,
  TranslationOutlined,
  CheckCircleOutlined,
  BellOutlined,
  SettingOutlined,
  ExportOutlined,
  SyncOutlined,
  SoundOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

interface SearchResult {
  id: string;
  title: string;
  description: string;
  path: string;
  icon: React.ReactNode;
  category: string;
}

const searchData: SearchResult[] = [
  { id: '1', title: '控制台', description: '查看系统概览和关键指标', path: '/', icon: <DashboardOutlined />, category: '导航' },
  // Agent系统
  { id: '2', title: '智能排班', description: 'AI驱动的员工排班管理', path: '/schedule', icon: <ScheduleOutlined />, category: 'Agent系统' },
  { id: '3', title: '订单协同', description: '订单管理和协同处理', path: '/order', icon: <ShoppingCartOutlined />, category: 'Agent系统' },
  { id: '4', title: '库存预警', description: '智能库存监控和预警', path: '/inventory', icon: <InboxOutlined />, category: 'Agent系统' },
  { id: '5', title: '服务质量', description: '服务质量监控和分析', path: '/service', icon: <CustomerServiceOutlined />, category: 'Agent系统' },
  { id: '6', title: '培训辅导', description: '员工培训和技能提升', path: '/training', icon: <ReadOutlined />, category: 'Agent系统' },
  { id: '7', title: '决策支持', description: '数据驱动的决策建议', path: '/decision', icon: <BarChartOutlined />, category: 'Agent系统' },
  { id: '8', title: '预定宴会', description: '宴会预定和管理', path: '/reservation', icon: <CalendarOutlined />, category: 'Agent系统' },
  // 业务管理
  { id: '9', title: '多门店管理', description: '跨门店统一管理', path: '/multi-store', icon: <ShopOutlined />, category: '业务管理' },
  { id: '10', title: '供应链管理', description: '供应商和采购管理', path: '/supply-chain', icon: <ShoppingCartOutlined />, category: '业务管理' },
  { id: '11', title: '财务管理', description: '财务报表和收支管理', path: '/finance', icon: <DollarOutlined />, category: '业务管理' },
  // 数据分析
  { id: '12', title: '数据大屏', description: '实时数据可视化大屏', path: '/data-visualization', icon: <LineChartOutlined />, category: '数据分析' },
  { id: '13', title: '高级分析', description: '深度数据分析和洞察', path: '/analytics', icon: <BarChartOutlined />, category: '数据分析' },
  { id: '14', title: '系统监控', description: '系统性能和健康监控', path: '/monitoring', icon: <MonitorOutlined />, category: '数据分析' },
  // 通知
  { id: '15', title: '通知中心', description: '系统通知和消息管理', path: '/notifications', icon: <BellOutlined />, category: '导航' },
  // 系统管理
  { id: '16', title: '用户管理', description: '系统用户和权限管理', path: '/users', icon: <TeamOutlined />, category: '系统管理' },
  { id: '17', title: '企业集成', description: '第三方系统集成配置', path: '/enterprise', icon: <ApiOutlined />, category: '系统管理' },
  { id: '18', title: '数据备份', description: '数据备份和恢复管理', path: '/backup', icon: <DatabaseOutlined />, category: '系统管理' },
  { id: '19', title: '审计日志', description: '系统操作审计记录', path: '/audit', icon: <FileTextOutlined />, category: '系统管理' },
  { id: '20', title: '数据导入导出', description: '批量数据导入和导出', path: '/data-import-export', icon: <FileExcelOutlined />, category: '系统管理' },
  { id: '21', title: '开放平台', description: '插件市场和开发者管理', path: '/open-platform', icon: <AppstoreOutlined />, category: '系统管理' },
  { id: '22', title: '行业解决方案', description: '行业最佳实践和KPI基准', path: '/industry-solutions', icon: <GlobalOutlined />, category: '系统管理' },
  { id: '23', title: '国际化', description: '多语言和货币换算', path: '/i18n', icon: <TranslationOutlined />, category: '系统管理' },
  // 智能分析
  { id: '24', title: '需求预测', description: 'Prophet模型需求预测', path: '/forecast', icon: <LineChartOutlined />, category: '智能分析' },
  { id: '25', title: '跨门店洞察', description: '跨门店异常检测和最佳实践', path: '/cross-store-insights', icon: <GlobalOutlined />, category: '智能分析' },
  { id: '26', title: '推荐引擎', description: '菜品推荐和动态定价', path: '/recommendations', icon: <BulbOutlined />, category: '智能分析' },
  { id: '27', title: '竞争分析', description: '竞争对手分析和市场洞察', path: '/competitive-analysis', icon: <RiseOutlined />, category: '智能分析' },
  { id: '28', title: '报表模板', description: '自定义报表模板管理', path: '/report-templates', icon: <FileTextOutlined />, category: '智能分析' },
  { id: '29', title: 'KPI看板', description: 'KPI指标跟踪和趋势分析', path: '/kpi-dashboard', icon: <BarChartOutlined />, category: '智能分析' },
  // 客户运营
  { id: '30', title: '私域运营', description: 'RFM分析和用户旅程管理', path: '/private-domain', icon: <TeamOutlined />, category: '客户运营' },
  { id: '31', title: '会员系统', description: '会员管理和积分体系', path: '/members', icon: <UserOutlined />, category: '客户运营' },
  { id: '32', title: '客户360', description: '客户全景画像和行为分析', path: '/customer360', icon: <UserOutlined />, category: '客户运营' },
  // 门店运营
  { id: '33', title: 'POS系统', description: 'POS订单和库存实时管理', path: '/pos', icon: <ShoppingCartOutlined />, category: '门店运营' },
  { id: '34', title: '质量管理', description: '食品安全和质检记录', path: '/quality', icon: <CheckCircleOutlined />, category: '门店运营' },
  { id: '35', title: '合规管理', description: '证照管理和合规检查', path: '/compliance', icon: <SafetyOutlined />, category: '门店运营' },
  { id: '36', title: '人工审批', description: 'AI决策人工审批队列', path: '/human-in-the-loop', icon: <SafetyOutlined />, category: '门店运营' },
  // AI基础设施
  { id: '37', title: 'AI进化看板', description: 'Agent采纳率和信任阶段', path: '/ai-evolution', icon: <RobotOutlined />, category: 'AI基础设施' },
  { id: '38', title: '边缘节点', description: '离线模式和边缘计算管理', path: '/edge-node', icon: <CloudOutlined />, category: 'AI基础设施' },
  { id: '39', title: '决策验证', description: 'AI决策合规性验证', path: '/decision-validator', icon: <CheckCircleOutlined />, category: 'AI基础设施' },
  { id: '40', title: '联邦学习', description: '隐私保护的分布式模型训练', path: '/federated-learning', icon: <ExperimentOutlined />, category: 'AI基础设施' },
  { id: '41', title: 'Agent协作', description: '多Agent协调和冲突解决', path: '/agent-collaboration', icon: <ApartmentOutlined />, category: 'AI基础设施' },
  // 业务管理（批次3）
  { id: '42', title: '任务管理', description: '任务创建、分配和跟踪', path: '/tasks', icon: <FileTextOutlined />, category: '业务管理' },
  { id: '43', title: '对账管理', description: '财务对账执行和差异确认', path: '/reconciliation', icon: <FileExcelOutlined />, category: '业务管理' },
  { id: '44', title: '菜品管理', description: '菜品CRUD、分类和成本明细', path: '/dishes', icon: <ShoppingCartOutlined />, category: '业务管理' },
  { id: '45', title: '员工管理', description: '员工信息和角色管理', path: '/employees', icon: <TeamOutlined />, category: '业务管理' },
  // 系统管理（批次3）
  { id: '46', title: 'RaaS定价', description: '效果付费套餐和账单明细', path: '/raas', icon: <DollarOutlined />, category: '系统管理' },
  { id: '47', title: '模型市场', description: '购买AI模型和贡献训练数据', path: '/model-marketplace', icon: <AppstoreOutlined />, category: '系统管理' },
  { id: '48', title: 'LLM配置', description: 'AI大模型配置和连接测试', path: '/llm-config', icon: <SettingOutlined />, category: '系统管理' },
  { id: '49', title: '外部集成', description: 'POS/供应商/会员系统同步管理', path: '/integrations', icon: <ApiOutlined />, category: '系统管理' },
  { id: '50', title: '调度管理', description: '定时任务计划和手动触发', path: '/scheduler', icon: <CalendarOutlined />, category: '系统管理' },
  // AI基础设施（批次3/4）
  { id: '51', title: '硬件管理', description: '树莓派边缘节点和Shokz设备', path: '/hardware', icon: <CloudOutlined />, category: 'AI基础设施' },
  { id: '52', title: '神经系统', description: '语义搜索和神经网络状态', path: '/neural', icon: <ApartmentOutlined />, category: 'AI基础设施' },
  { id: '53', title: '嵌入模型', description: '向量嵌入训练和相似度计算', path: '/embedding', icon: <ExperimentOutlined />, category: 'AI基础设施' },
  // 智能分析（批次4）
  { id: '54', title: '基准测试', description: '行业基准对比和综合评分', path: '/benchmark', icon: <BarChartOutlined />, category: '智能分析' },
  { id: '55', title: '审批管理', description: 'AI决策人工审批、拒绝和修改', path: '/approval', icon: <CheckCircleOutlined />, category: '系统管理' },
  { id: '56', title: '门店管理', description: '门店CRUD和统计数据查看', path: '/stores', icon: <ShopOutlined />, category: '系统管理' },
  { id: '57', title: '导出任务', description: '数据导出任务管理和文件下载', path: '/export-jobs', icon: <ExportOutlined />, category: '系统管理' },
  { id: '58', title: '排队管理', description: '餐厅叫号排队和入座管理', path: '/queue', icon: <TeamOutlined />, category: '门店运营' },
  { id: '59', title: '智能体记忆', description: 'AI智能体共享记忆流监控', path: '/agent-memory', icon: <DatabaseOutlined />, category: 'AI基础设施' },
  { id: '60', title: '微信触发器', description: '微信推送触发规则管理', path: '/wechat-triggers', icon: <BellOutlined />, category: '系统管理' },
  { id: '61', title: '事件溯源', description: '神经系统事件处理链监控', path: '/event-sourcing', icon: <FileTextOutlined />, category: 'AI基础设施' },
  { id: '62', title: '美团排队', description: '美团/大众点评排队集成配置', path: '/meituan-queue', icon: <SyncOutlined />, category: '门店运营' },
  { id: '63', title: '向量知识库', description: '向量索引管理和语义搜索', path: '/vector-index', icon: <SearchOutlined />, category: 'AI基础设施' },
  { id: '64', title: '适配器管理', description: '天才/美团/傲旗威/品智第三方平台适配器', path: '/adapters', icon: <ApiOutlined />, category: '系统管理' },
  { id: '65', title: '语音设备', description: 'Shokz骨传导耳机设备管理和广播通知', path: '/voice-devices', icon: <SoundOutlined />, category: '门店运营' },
  { id: '66', title: '系统健康', description: '系统健康检查、Agent状态和外部系统监控', path: '/system-health', icon: <MonitorOutlined />, category: '系统管理' },
  { id: '67', title: '个人信息', description: '查看和编辑个人资料、修改密码', path: '/profile', icon: <UserOutlined />, category: '导航' },
  { id: '68', title: '语音WebSocket', description: 'STT/TTS/对话WebSocket实时测试', path: '/voice-ws', icon: <SoundOutlined />, category: 'AI基础设施' },
];

interface GlobalSearchProps {
  visible: boolean;
  onClose: () => void;
}

export const GlobalSearch: React.FC<GlobalSearchProps> = ({ visible, onClose }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [activeIndex, setActiveIndex] = useState(-1);
  const inputRef = useRef<any>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (visible) {
      setTimeout(() => {
        inputRef.current?.focus();
      }, 100);
    } else {
      setSearchQuery('');
      setResults([]);
      setActiveIndex(-1);
    }
  }, [visible]);

  useEffect(() => {
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      const filtered = searchData.filter(
        (item) =>
          item.title.toLowerCase().includes(query) ||
          item.description.toLowerCase().includes(query) ||
          item.category.toLowerCase().includes(query)
      );
      setResults(filtered);
    } else {
      setResults(searchData.slice(0, 8));
    }
    setActiveIndex(-1);
  }, [searchQuery]);

  useEffect(() => {
    if (activeIndex >= 0 && listRef.current) {
      const items = listRef.current.querySelectorAll('.ant-list-item');
      const activeItem = items[activeIndex] as HTMLElement;
      if (activeItem) activeItem.scrollIntoView({ block: 'nearest' });
    }
  }, [activeIndex]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (results.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex(prev => (prev + 1) % results.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex(prev => (prev <= 0 ? results.length - 1 : prev - 1));
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      e.preventDefault();
      handleSelect(results[activeIndex].path);
    }
  };

  const handleSelect = (path: string) => {
    navigate(path);
    onClose();
  };

  return (
    <Modal
      open={visible}
      onCancel={onClose}
      footer={null}
      width={600}
      style={{ top: 100 }}
      bodyStyle={{ padding: 0 }}
      closeIcon={null}
    >
      <div style={{ padding: '16px 16px 0' }}>
        <Input
          ref={inputRef}
          size="large"
          placeholder="搜索页面、功能... (Ctrl+K)"
          prefix={<SearchOutlined style={{ color: 'var(--text-tertiary)' }} />}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          style={{ borderRadius: 'var(--radius-md)' }}
          allowClear
        />
      </div>

      <div ref={listRef} style={{ maxHeight: 400, overflowY: 'auto', padding: '8px 0' }}>
        {results.length > 0 ? (
          <List
            dataSource={results}
            renderItem={(item, index) => (
              <List.Item
                onClick={() => handleSelect(item.path)}
                onMouseEnter={() => setActiveIndex(index)}
                style={{
                  padding: '12px 16px',
                  cursor: 'pointer',
                  background: index === activeIndex ? 'var(--bg-secondary)' : 'transparent',
                  transition: 'background var(--transition-fast)',
                }}
              >
                <List.Item.Meta
                  avatar={
                    <div
                      style={{
                        width: 40,
                        height: 40,
                        borderRadius: 'var(--radius-md)',
                        background: 'var(--bg-secondary)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 18,
                        color: 'var(--primary-color)',
                      }}
                    >
                      {item.icon}
                    </div>
                  }
                  title={
                    <Space>
                      <span style={{ fontWeight: 500 }}>{item.title}</span>
                      <Tag style={{ fontSize: 11 }}>{item.category}</Tag>
                    </Space>
                  }
                  description={
                    <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                      {item.description}
                    </span>
                  }
                />
              </List.Item>
            )}
          />
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="未找到相关结果"
            style={{ padding: '32px 0' }}
          />
        )}
      </div>

      <div
        style={{
          padding: '12px 16px',
          borderTop: '1px solid var(--border-light)',
          background: 'var(--bg-secondary)',
          fontSize: 12,
          color: 'var(--text-tertiary)',
        }}
      >
        <Space size={16}>
          <span>↑↓ 导航</span>
          <span>Enter 选择</span>
          <span>Esc 关闭</span>
        </Space>
      </div>
    </Modal>
  );
};
