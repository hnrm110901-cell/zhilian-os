import React, { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import {
  Button, Tag, Space, Tabs, message, Popconfirm, Spin, Badge,
} from 'antd';
import {
  ArrowLeftOutlined, EditOutlined, StopOutlined,
  CheckCircleOutlined, ShopOutlined, TeamOutlined,
  ApiOutlined, RobotOutlined, DollarOutlined,
  AppstoreOutlined, ProfileOutlined, WechatWorkOutlined,
} from '@ant-design/icons';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { apiClient } from '../../services/api';
import type { MerchantDetail, ConfigSummary } from './merchant-constants';
import { CUISINE_LABELS } from './merchant-constants';
import OverviewTab from './merchant-tabs/OverviewTab';
import StoresTab from './merchant-tabs/StoresTab';
import UsersTab from './merchant-tabs/UsersTab';
import CostTargetsTab from './merchant-tabs/CostTargetsTab';
import IMConfigTab from './merchant-tabs/IMConfigTab';
import AgentConfigTab from './merchant-tabs/AgentConfigTab';
import ChannelsTab from './merchant-tabs/ChannelsTab';
import styles from './MerchantDetailPage.module.css';

// ── 种子客户 mock（后端未启动时降级展示）─────────────────────────────────────
const SEED_DETAILS: Record<string, MerchantDetail> = {
  BRD_CZYZ0001: {
    brand_id: 'BRD_CZYZ0001', brand_name: '尝在一起', cuisine_type: 'hunan',
    avg_ticket_yuan: 80, target_food_cost_pct: 35, target_labor_cost_pct: 22,
    target_rent_cost_pct: 10, target_waste_pct: 3, logo_url: null,
    status: 'active', created_at: '2026-01-15T00:00:00Z',
    group: {
      group_id: 'GRP_CZYZ0001', group_name: '尝在一起餐饮管理有限公司',
      legal_entity: '尝在一起法人代表', unified_social_credit_code: '91430100CZYZ000001',
      industry_type: 'chinese_formal', contact_person: '尝在一起联系人',
      contact_phone: '0731-00000001', address: '湖南省长沙市',
    },
    stores: [
      { id: 'CZYZ-2461', name: '文化城店', code: 'CZYZ-WH001', city: '长沙', district: '', status: 'active', address: '', seats: 80, created_at: '2026-01-15T00:00:00Z' },
      { id: 'CZYZ-7269', name: '浏小鲜', code: 'CZYZ-LXX001', city: '长沙', district: '', status: 'active', address: '', seats: 60, created_at: '2026-01-15T00:00:00Z' },
      { id: 'CZYZ-19189', name: '永安店', code: 'CZYZ-YA001', city: '长沙', district: '', status: 'active', address: '', seats: 70, created_at: '2026-01-15T00:00:00Z' },
    ],
    users: [
      { id: 'u1', username: 'czyz_admin', email: 'admin@czyz.com', full_name: '尝在一起管理员', role: 'store_manager', is_active: true, store_id: null, created_at: '2026-01-15T00:00:00Z' },
    ],
  },
  BRD_ZQX0001: {
    brand_id: 'BRD_ZQX0001', brand_name: '最黔线', cuisine_type: 'guizhou',
    avg_ticket_yuan: 75, target_food_cost_pct: 36, target_labor_cost_pct: 23,
    target_rent_cost_pct: 10, target_waste_pct: 3, logo_url: null,
    status: 'active', created_at: '2026-01-20T00:00:00Z',
    group: {
      group_id: 'GRP_ZQX0001', group_name: '老江菜馆餐饮管理有限公司',
      legal_entity: '最黔线法人代表', unified_social_credit_code: '91430100ZQX0000001',
      industry_type: 'chinese_formal', contact_person: '最黔线联系人',
      contact_phone: '0731-00000002', address: '湖南省长沙市',
    },
    stores: [
      { id: 'ZQX-20529', name: '马家湾店', code: 'ZQX-MJW001', city: '长沙', district: '', status: 'active', address: '', seats: 80, created_at: '2026-01-20T00:00:00Z' },
      { id: 'ZQX-32109', name: '东欣万象店', code: 'ZQX-DXWX001', city: '长沙', district: '', status: 'active', address: '', seats: 90, created_at: '2026-01-20T00:00:00Z' },
      { id: 'ZQX-32304', name: '合众路店', code: 'ZQX-HZL001', city: '长沙', district: '', status: 'active', address: '', seats: 80, created_at: '2026-01-20T00:00:00Z' },
      { id: 'ZQX-32305', name: '广州路店', code: 'ZQX-GZL001', city: '长沙', district: '', status: 'active', address: '', seats: 70, created_at: '2026-01-20T00:00:00Z' },
      { id: 'ZQX-32306', name: '昆明路店', code: 'ZQX-KML001', city: '长沙', district: '', status: 'active', address: '', seats: 80, created_at: '2026-01-20T00:00:00Z' },
      { id: 'ZQX-32309', name: '仁怀店', code: 'ZQX-RH001', city: '仁怀', district: '', status: 'active', address: '', seats: 60, created_at: '2026-01-20T00:00:00Z' },
    ],
    users: [
      { id: 'u2', username: 'zqx_admin', email: 'admin@zuiqianxian.com', full_name: '最黔线管理员', role: 'store_manager', is_active: true, store_id: null, created_at: '2026-01-20T00:00:00Z' },
    ],
  },
  BRD_SGC0001: {
    brand_id: 'BRD_SGC0001', brand_name: '尚宫厨', cuisine_type: 'hunan',
    avg_ticket_yuan: 180, target_food_cost_pct: 33, target_labor_cost_pct: 25,
    target_rent_cost_pct: 12, target_waste_pct: 2.5, logo_url: null,
    status: 'active', created_at: '2026-02-01T00:00:00Z',
    group: {
      group_id: 'GRP_SGC0001', group_name: '尚宫厨餐饮管理有限公司',
      legal_entity: '尚宫厨法人代表', unified_social_credit_code: '91430100SGC0000001',
      industry_type: 'chinese_formal', contact_person: '尚宫厨联系人',
      contact_phone: '0731-00000003', address: '湖南省长沙市',
    },
    stores: [
      { id: 'SGC-2463', name: '采霞街店', code: 'SGC-CXJ001', city: '长沙', district: '', status: 'active', address: '', seats: 100, created_at: '2026-02-01T00:00:00Z' },
      { id: 'SGC-7896', name: '湘江水岸店', code: 'SGC-XJSA001', city: '长沙', district: '', status: 'active', address: '', seats: 120, created_at: '2026-02-01T00:00:00Z' },
      { id: 'SGC-24777', name: '乐城店', code: 'SGC-LC001', city: '长沙', district: '', status: 'active', address: '', seats: 90, created_at: '2026-02-01T00:00:00Z' },
      { id: 'SGC-36199', name: '啫匠亲城店', code: 'SGC-ZJQC001', city: '长沙', district: '', status: 'active', address: '', seats: 80, created_at: '2026-02-01T00:00:00Z' },
      { id: 'SGC-41405', name: '酃湖雅院店', code: 'SGC-LHYY001', city: '株洲', district: '', status: 'active', address: '', seats: 110, created_at: '2026-02-01T00:00:00Z' },
    ],
    users: [
      { id: 'u3', username: 'sgc_admin', email: 'admin@shanggongchu.com', full_name: '尚宫厨管理员', role: 'store_manager', is_active: true, store_id: null, created_at: '2026-02-01T00:00:00Z' },
    ],
  },
};

const SEED_CONFIG: ConfigSummary = {
  im: { configured: false, platform: null, last_sync_status: null, last_sync_at: null },
  agents: { total: 6, enabled: 0 },
  channels: { count: 0 },
  store_count: 0, user_count: 0,
};

const MerchantDetailPage: React.FC = () => {
  const { brandId } = useParams<{ brandId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const activeTab = searchParams.get('tab') || 'overview';

  const [detail, setDetail] = useState<MerchantDetail | null>(null);
  const [configSummary, setConfigSummary] = useState<ConfigSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchDetail = useCallback(async () => {
    if (!brandId) return;
    setLoading(true);
    try {
      const data = await apiClient.get<MerchantDetail>(`/api/v1/merchants/${brandId}`);
      setDetail(data);
    } catch {
      // 后端未启动时降级显示种子客户
      const seed = SEED_DETAILS[brandId];
      if (seed) {
        setDetail(seed);
      } else {
        message.error('加载商户详情失败');
      }
    } finally {
      setLoading(false);
    }
  }, [brandId]);

  const fetchConfigSummary = useCallback(async () => {
    if (!brandId) return;
    try {
      const data = await apiClient.get<ConfigSummary>(`/api/v1/merchants/${brandId}/config-summary`);
      setConfigSummary(data);
    } catch {
      setConfigSummary(SEED_CONFIG);
    }
  }, [brandId]);

  useEffect(() => { fetchDetail(); fetchConfigSummary(); }, [fetchDetail, fetchConfigSummary]);

  const handleToggleMerchant = async () => {
    if (!brandId) return;
    try {
      await apiClient.post(`/api/v1/merchants/${brandId}/toggle-status`, {});
      message.success('状态已切换');
      fetchDetail();
      fetchConfigSummary();
    } catch {
      message.error('操作失败');
    }
  };

  const onTabChange = (key: string) => {
    setSearchParams({ tab: key });
  };

  if (loading && !detail) {
    return (
      <div className={styles.loadingContainer}>
        <Spin size="large" />
      </div>
    );
  }

  if (!detail) {
    return (
      <div className={styles.loadingContainer}>
        <div>商户不存在</div>
        <Button onClick={() => navigate('/platform/merchants')}>返回列表</Button>
      </div>
    );
  }

  const tabItems = [
    {
      key: 'overview',
      label: <span><ProfileOutlined /> 概览</span>,
      children: (
        <OverviewTab
          detail={detail}
          configSummary={configSummary}
          onRefresh={() => { fetchDetail(); fetchConfigSummary(); }}
        />
      ),
    },
    {
      key: 'stores',
      label: <span><ShopOutlined /> 门店 ({detail.stores.length})</span>,
      children: (
        <StoresTab
          brandId={detail.brand_id}
          stores={detail.stores}
          onRefresh={fetchDetail}
        />
      ),
    },
    {
      key: 'users',
      label: <span><TeamOutlined /> 用户 ({detail.users.length})</span>,
      children: (
        <UsersTab
          brandId={detail.brand_id}
          users={detail.users}
          stores={detail.stores}
          onRefresh={fetchDetail}
        />
      ),
    },
    {
      key: 'costs',
      label: <span><DollarOutlined /> 成本目标</span>,
      children: (
        <CostTargetsTab
          detail={detail}
          onRefresh={fetchDetail}
        />
      ),
    },
    {
      key: 'im',
      label: (
        <span>
          <ApiOutlined /> IM 集成
          {configSummary?.im.configured && (
            <Badge status="success" style={{ marginLeft: 6 }} />
          )}
        </span>
      ),
      children: (
        <IMConfigTab brandId={detail.brand_id} />
      ),
    },
    {
      key: 'agents',
      label: (
        <span>
          <RobotOutlined /> Agent 配置
          {configSummary && (
            <Tag color="blue" style={{ marginLeft: 6, fontSize: 11 }}>
              {configSummary.agents.enabled}/{configSummary.agents.total}
            </Tag>
          )}
        </span>
      ),
      children: (
        <AgentConfigTab brandId={detail.brand_id} brandName={detail.brand_name} />
      ),
    },
    {
      key: 'channels',
      label: (
        <span>
          <AppstoreOutlined /> 销售渠道
          {configSummary && configSummary.channels.count > 0 && (
            <Tag style={{ marginLeft: 6, fontSize: 11 }}>
              {configSummary.channels.count}
            </Tag>
          )}
        </span>
      ),
      children: (
        <ChannelsTab brandId={detail.brand_id} />
      ),
    },
  ];

  return (
    <div className={styles.container}>
      {/* ── Header ────────────────────────────────────────────────────────────── */}
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/platform/merchants')}
            className={styles.backBtn}
          />
          <div className={styles.brandInfo}>
            <div className={styles.brandName}>
              {detail.brand_name}
              <Tag
                color={detail.status === 'active' ? 'green' : 'red'}
                style={{ marginLeft: 8, verticalAlign: 'middle' }}
              >
                {detail.status === 'active' ? '运营中' : '已停用'}
              </Tag>
            </div>
            <div className={styles.brandMeta}>
              <span>{CUISINE_LABELS[detail.cuisine_type] || detail.cuisine_type}</span>
              {detail.avg_ticket_yuan && <span>人均 ¥{detail.avg_ticket_yuan}</span>}
              <span className={styles.brandIdText}>{detail.brand_id}</span>
              {detail.created_at && <span>开通于 {new Date(detail.created_at).toLocaleDateString('zh-CN')}</span>}
            </div>
          </div>
        </div>
        <Space>
          <Popconfirm
            title={`确认${detail.status === 'active' ? '停用' : '启用'}该商户？`}
            onConfirm={handleToggleMerchant}
          >
            <Button
              danger={detail.status === 'active'}
              icon={detail.status === 'active' ? <StopOutlined /> : <CheckCircleOutlined />}
            >
              {detail.status === 'active' ? '停用' : '启用'}
            </Button>
          </Popconfirm>
        </Space>
      </div>

      {/* ── Config Summary Badges ─────────────────────────────────────────────── */}
      {configSummary && (
        <div className={styles.configBadges}>
          <div className={styles.configBadge}>
            <ApiOutlined />
            <span>IM: {configSummary.im.configured ? (configSummary.im.platform === 'wechat_work' ? '企微已配置' : '钉钉已配置') : '未配置'}</span>
          </div>
          <div className={styles.configBadge}>
            <RobotOutlined />
            <span>Agent: {configSummary.agents.enabled}/{configSummary.agents.total} 启用</span>
          </div>
          <div className={styles.configBadge}>
            <AppstoreOutlined />
            <span>渠道: {configSummary.channels.count} 个</span>
          </div>
          <div className={styles.configBadge}>
            <ShopOutlined />
            <span>门店: {configSummary.store_count}</span>
          </div>
          <div className={styles.configBadge}>
            <TeamOutlined />
            <span>用户: {configSummary.user_count}</span>
          </div>
        </div>
      )}

      {/* ── Tabs ──────────────────────────────────────────────────────────────── */}
      <Tabs
        activeKey={activeTab}
        onChange={onTabChange}
        items={tabItems}
        className={styles.tabs}
      />
    </div>
  );
};

export default MerchantDetailPage;
