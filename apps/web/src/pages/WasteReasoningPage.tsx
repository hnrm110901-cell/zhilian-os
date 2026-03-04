import React, { useState, useCallback, useEffect } from 'react';
import {
  Row, Col, Card, Select, Button, Table, Tag, Statistic,
  Space, Spin, Typography, DatePicker, Alert, Tooltip, Badge,
  Progress,
} from 'antd';
import {
  ReloadOutlined, WarningOutlined, FireOutlined,
  ArrowUpOutlined, ArrowDownOutlined, MinusOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import dayjs from 'dayjs';
import { apiClient } from '../services/api';
import { handleApiError } from '../utils/message';

const { RangePicker } = DatePicker;
const { Text, Title } = Typography;
const { Option } = Select;

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface RootCause {
  root_cause:  string;
  event_type:  string | null;
  event_count: number;
}

interface WasteItem {
  rank:            number;
  item_id:         string;
  item_name:       string;
  category:        string;
  unit:            string;
  waste_cost_fen:  number;
  waste_cost_yuan: number;
  waste_qty:       number;
  cost_share_pct:  number;
  root_causes:     RootCause[];
  action:          string;
}

interface BomDeviationItem {
  rank:               number;
  ingredient_id:      string;
  item_name:          string;
  unit:               string;
  total_variance_qty: number;
  variance_cost_yuan: number;
  avg_variance_pct:   number;
  event_count:        number;
}

interface WasteReport {
  store_id:          string;
  start_date:        string;
  end_date:          string;
  waste_rate_pct:    number;
  waste_rate_status: string;
  total_waste_yuan:  number;
  waste_change_yuan: number;
  top5:              WasteItem[];
  bom_deviation:     BomDeviationItem[];
}

// ── 辅助组件 ──────────────────────────────────────────────────────────────────

const statusBadge = (status: string) => {
  const map: Record<string, { color: string; text: string }> = {
    ok:       { color: 'success', text: '正常' },
    warning:  { color: 'warning', text: '偏高' },
    critical: { color: 'error',   text: '超标' },
  };
  const cfg = map[status] || { color: 'default', text: status };
  return <Badge status={cfg.color as any} text={cfg.text} />;
};

const rootCauseLabel = (cause: string) => {
  const map: Record<string, string> = {
    staff_error:   '操作失误',
    food_quality:  '食材质量',
    over_prep:     '备料过多',
    spoilage:      '自然腐败',
    bom_deviation: 'BOM偏差',
    transfer_loss: '转运损耗',
    drop_damage:   '跌落损坏',
    unknown:       '待追因',
  };
  return map[cause] || cause;
};

const rootCauseColor = (cause: string) => {
  const map: Record<string, string> = {
    staff_error:   'red',
    food_quality:  'orange',
    over_prep:     'gold',
    spoilage:      'volcano',
    bom_deviation: 'purple',
    transfer_loss: 'blue',
    drop_damage:   'geekblue',
    unknown:       'default',
  };
  return map[cause] || 'default';
};

// ── 主组件 ────────────────────────────────────────────────────────────────────

const WasteReasoningPage: React.FC = () => {
  const [loading, setLoading]     = useState(false);
  const [stores, setStores]       = useState<any[]>([]);
  const [storeId, setStoreId]     = useState(localStorage.getItem('store_id') || 'STORE001');
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs().subtract(6, 'day'),
    dayjs(),
  ]);
  const [report, setReport]       = useState<WasteReport | null>(null);
  const [error, setError]         = useState<string | null>(null);

  // 加载门店列表
  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      const list = res.data?.stores || res.data || [];
      setStores(list);
      if (list.length > 0 && !list.find((s: any) => s.id === storeId)) {
        setStoreId(list[0].id || list[0].store_id || 'STORE001');
      }
    } catch {
      // 静默降级，使用默认门店ID
    }
  }, [storeId]);

  // 加载损耗报告
  const loadReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [start, end] = dateRange;
      const res = await apiClient.get('/api/v1/waste/report', {
        params: {
          store_id:   storeId,
          start_date: start.format('YYYY-MM-DD'),
          end_date:   end.format('YYYY-MM-DD'),
        },
      });
      setReport(res.data);
    } catch (err: any) {
      setError('加载损耗数据失败，请检查网络或联系管理员');
      handleApiError(err, '加载损耗数据失败');
    } finally {
      setLoading(false);
    }
  }, [storeId, dateRange]);

  useEffect(() => {
    loadStores();
  }, [loadStores]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  // ── Top5 损耗食材表格列定义 ─────────────────────────────────────────────────

  const top5Columns: ColumnsType<WasteItem> = [
    {
      title: '排名',
      dataIndex: 'rank',
      width: 56,
      render: (rank) => (
        <span style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 28, height: 28, borderRadius: '50%',
          background: rank <= 3 ? '#ff4d4f' : '#d9d9d9',
          color: rank <= 3 ? '#fff' : '#666',
          fontWeight: 'bold', fontSize: 13,
        }}>
          {rank}
        </span>
      ),
    },
    {
      title: '食材名称',
      dataIndex: 'item_name',
      render: (name, row) => (
        <Space direction="vertical" size={2}>
          <Text strong>{name}</Text>
          {row.category && <Text type="secondary" style={{ fontSize: 12 }}>{row.category}</Text>}
        </Space>
      ),
    },
    {
      title: '损耗金额',
      dataIndex: 'waste_cost_yuan',
      sorter: (a, b) => a.waste_cost_yuan - b.waste_cost_yuan,
      render: (yuan) => (
        <Text strong style={{ color: '#cf1322' }}>¥{yuan.toLocaleString('zh-CN', { minimumFractionDigits: 0 })}</Text>
      ),
    },
    {
      title: '损耗数量',
      render: (_, row) => `${row.waste_qty.toFixed(2)} ${row.unit}`,
    },
    {
      title: '占总损耗',
      dataIndex: 'cost_share_pct',
      render: (pct) => (
        <Space>
          <Progress percent={pct} size="small" style={{ width: 80 }} showInfo={false}
            strokeColor={pct >= 30 ? '#ff4d4f' : pct >= 15 ? '#faad14' : '#52c41a'} />
          <Text style={{ fontSize: 12 }}>{pct.toFixed(1)}%</Text>
        </Space>
      ),
    },
    {
      title: '归因',
      dataIndex: 'root_causes',
      render: (causes: RootCause[]) => {
        if (!causes || causes.length === 0) {
          return <Tag color="default">待记录</Tag>;
        }
        return (
          <Space wrap>
            {causes.slice(0, 2).map((c, i) => (
              <Tag key={i} color={rootCauseColor(c.root_cause)}>
                {rootCauseLabel(c.root_cause)}×{c.event_count}
              </Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: '建议行动',
      dataIndex: 'action',
      width: 240,
      render: (action) => (
        <Text style={{ fontSize: 12, color: '#1677ff' }}>{action}</Text>
      ),
    },
  ];

  // ── BOM偏差表格列定义 ────────────────────────────────────────────────────────

  const bomColumns: ColumnsType<BomDeviationItem> = [
    {
      title: '排名',
      dataIndex: 'rank',
      width: 56,
      render: (rank) => (
        <span style={{
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          width: 28, height: 28, borderRadius: '50%',
          background: rank <= 3 ? '#fa8c16' : '#d9d9d9',
          color: rank <= 3 ? '#fff' : '#666',
          fontWeight: 'bold', fontSize: 13,
        }}>
          {rank}
        </span>
      ),
    },
    { title: '食材名称', dataIndex: 'item_name', render: (name) => <Text strong>{name}</Text> },
    {
      title: '偏差成本',
      dataIndex: 'variance_cost_yuan',
      sorter: (a, b) => a.variance_cost_yuan - b.variance_cost_yuan,
      render: (yuan) => (
        <Text strong style={{ color: '#d46b08' }}>
          ¥{yuan.toLocaleString('zh-CN', { minimumFractionDigits: 0 })}
        </Text>
      ),
    },
    {
      title: '超用数量',
      render: (_, row) => `+${row.total_variance_qty.toFixed(2)} ${row.unit}`,
    },
    {
      title: '平均偏差率',
      dataIndex: 'avg_variance_pct',
      render: (pct) => (
        <Tag color={pct >= 20 ? 'red' : pct >= 10 ? 'orange' : 'gold'}>
          +{pct.toFixed(1)}%
        </Tag>
      ),
    },
    { title: '事件次数', dataIndex: 'event_count' },
  ];

  // ── 渲染 KPI 卡片 ──────────────────────────────────────────────────────────

  const renderKpiCards = () => {
    if (!report) return null;
    const change = report.waste_change_yuan;
    const changeColor = change > 0 ? '#cf1322' : change < 0 ? '#3f8600' : undefined;
    const changeIcon = change > 0 ? <ArrowUpOutlined /> : change < 0 ? <ArrowDownOutlined /> : <MinusOutlined />;

    return (
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card>
            <Statistic
              title="总损耗金额"
              value={report.total_waste_yuan}
              prefix="¥"
              precision={0}
              valueStyle={{ color: '#cf1322', fontWeight: 'bold' }}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title={<Space>损耗率 {statusBadge(report.waste_rate_status)}</Space>}
              value={report.waste_rate_pct}
              suffix="%"
              precision={2}
              valueStyle={{
                color: report.waste_rate_status === 'critical' ? '#cf1322'
                     : report.waste_rate_status === 'warning'  ? '#d46b08'
                     : '#3f8600',
              }}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              行业标准：&lt;3%为优秀
            </Text>
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="较上期损耗变化"
              value={Math.abs(change)}
              prefix={<span style={{ color: changeColor }}>{changeIcon} ¥</span>}
              precision={0}
              valueStyle={{ color: changeColor }}
              suffix={change === 0 ? '' : change > 0 ? '（增加）' : '（减少）'}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="Top5食材"
              value={report.top5?.length ?? 0}
              suffix="种"
              valueStyle={{ color: '#1677ff' }}
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              {report.start_date} 至 {report.end_date}
            </Text>
          </Card>
        </Col>
      </Row>
    );
  };

  // ── 渲染主体 ────────────────────────────────────────────────────────────────

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16 }} wrap>
        <Title level={4} style={{ margin: 0 }}>
          <FireOutlined style={{ color: '#ff4d4f', marginRight: 8 }} />
          损耗Top5分析
        </Title>

        {/* 门店选择 */}
        <Select
          value={storeId}
          onChange={setStoreId}
          style={{ width: 160 }}
          placeholder="选择门店"
        >
          {stores.length > 0
            ? stores.map((s: any) => (
                <Option key={s.id || s.store_id} value={s.id || s.store_id}>
                  {s.name || s.store_name || s.id}
                </Option>
              ))
            : <Option value="STORE001">默认门店</Option>
          }
        </Select>

        {/* 日期范围 */}
        <RangePicker
          value={dateRange}
          onChange={(dates) => {
            if (dates && dates[0] && dates[1]) {
              setDateRange([dates[0], dates[1]]);
            }
          }}
          format="YYYY-MM-DD"
          allowClear={false}
        />

        <Button
          icon={<ReloadOutlined />}
          onClick={loadReport}
          loading={loading}
        >
          刷新
        </Button>
      </Space>

      {error && (
        <Alert type="error" message={error} style={{ marginBottom: 16 }} showIcon />
      )}

      <Spin spinning={loading}>
        {/* KPI 卡片 */}
        {renderKpiCards()}

        {/* Top5 损耗食材表 */}
        <Card
          title={
            <Space>
              <WarningOutlined style={{ color: '#ff4d4f' }} />
              Top5 损耗食材（按损耗金额排序）
            </Space>
          }
          style={{ marginBottom: 16 }}
          extra={
            report && report.total_waste_yuan > 0 && (
              <Text type="secondary">
                总损耗 ¥{report.total_waste_yuan.toLocaleString('zh-CN', { minimumFractionDigits: 0 })}
              </Text>
            )
          }
        >
          <Table
            columns={top5Columns}
            dataSource={report?.top5 ?? []}
            rowKey="item_id"
            pagination={false}
            size="middle"
            locale={{ emptyText: '暂无损耗数据' }}
            expandable={{
              expandedRowRender: (row) => (
                <div style={{ padding: '8px 16px', background: '#fafafa', borderRadius: 4 }}>
                  <Text strong style={{ marginRight: 8 }}>建议行动：</Text>
                  <Text style={{ color: '#1677ff' }}>{row.action}</Text>
                </div>
              ),
              rowExpandable: (row) => !!row.action,
            }}
          />
        </Card>

        {/* BOM 偏差排名 */}
        {report?.bom_deviation && report.bom_deviation.length > 0 && (
          <Card
            title={
              <Space>
                <WarningOutlined style={{ color: '#fa8c16' }} />
                BOM配方偏差排名（实际用量超出标准）
              </Space>
            }
          >
            <Table
              columns={bomColumns}
              dataSource={report.bom_deviation}
              rowKey="ingredient_id"
              pagination={false}
              size="middle"
              locale={{ emptyText: '暂无BOM偏差数据（需要开启损耗事件追踪）' }}
            />
          </Card>
        )}

        {!report && !loading && !error && (
          <Card>
            <Alert
              type="info"
              message="请选择门店和日期范围后点击刷新加载损耗数据"
              showIcon
            />
          </Card>
        )}
      </Spin>
    </div>
  );
};

export default WasteReasoningPage;
