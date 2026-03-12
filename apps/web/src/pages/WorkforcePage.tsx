import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  DatePicker,
  Form,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd';
import dayjs, { Dayjs } from 'dayjs';
import ReactECharts from 'echarts-for-react';
import { CheckCircleOutlined, EditOutlined, TeamOutlined, RiseOutlined, FallOutlined } from '@ant-design/icons';

import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';
import { ZButton, ZCard, ZKpi, ZSkeleton } from '../design-system/components';
import AgentWorkspaceTemplate from '../components/AgentWorkspaceTemplate';
import styles from './WorkforcePage.module.css';

const { Text } = Typography;

type PeriodKey = 'morning' | 'lunch' | 'dinner';

interface PeriodForecast {
  predicted_customer_count: number;
  confidence_score: number;
  total_headcount_needed: number;
  position_requirements: Record<string, number>;
  reason_1?: string;
  reason_2?: string;
  reason_3?: string;
}

interface ForecastResp {
  forecast_date: string;
  daily_peak_headcount: number;
  periods: Record<PeriodKey, PeriodForecast>;
}

interface LaborCostResp {
  actual_labor_cost_rate: number;
  headcount_actual?: number;
  saving_yuan?: number;
}

interface LaborBudgetResp {
  budget_period: string;
  target_labor_cost_rate: number;
  max_labor_cost_yuan: number;
  daily_budget_yuan?: number;
  alert_threshold_pct?: number;
  exists: boolean;
}

interface SeriesPoint {
  date: string;
  actualRate: number;
  actualHeadcount: number;
  recommendedHeadcount: number;
}

interface EmployeeHealthItem {
  employee_id: string;
  name: string;
  position?: string;
  risk_score_90d: number;
  risk_level: 'critical' | 'high' | 'medium' | 'low';
  replacement_cost_yuan: number;
  major_risk_factors: Array<string | { name: string; score?: number }>;
  unfavorable_ratio: number;
  unfavorable_shifts: number;
  total_shifts: number;
}

interface EmployeeHealthResp {
  store_id: string;
  year: number;
  month: number;
  total: number;
  fairness_index: number;
  fairness_distribution: {
    high_unfairness: number;
    medium_unfairness: number;
    low_unfairness: number;
  };
  items: EmployeeHealthItem[];
}

interface ShiftFairnessDetailResp {
  store_id: string;
  year: number;
  month: number;
  fairness_index: number;
  total_employees: number;
  distribution: {
    high_unfairness_count: number;
    medium_unfairness_count: number;
    low_unfairness_count: number;
  };
  employee_stats: Array<{
    employee_id: string;
    total_shifts: number;
    unfavorable_shifts: number;
    unfavorable_ratio: number;
  }>;
  consecutive_alerts: string[];
}

const defaultStoreId = localStorage.getItem('store_id') || 'STORE001';

const WorkforcePage: React.FC = () => {
  const [storeId] = useState(defaultStoreId);
  const [date, setDate] = useState<Dayjs>(dayjs().add(1, 'day'));
  const [selectedPeriod, setSelectedPeriod] = useState<PeriodKey>('lunch');

  const [loading, setLoading] = useState(false);
  const [seriesLoading, setSeriesLoading] = useState(false);
  const [forecast, setForecast] = useState<ForecastResp | null>(null);
  const [cost, setCost] = useState<LaborCostResp | null>(null);
  const [budget, setBudget] = useState<LaborBudgetResp | null>(null);
  const [series, setSeries] = useState<SeriesPoint[]>([]);
  const [employeeHealthLoading, setEmployeeHealthLoading] = useState(false);
  const [employeeHealth, setEmployeeHealth] = useState<EmployeeHealthResp | null>(null);
  const [fairnessDetail, setFairnessDetail] = useState<ShiftFairnessDetailResp | null>(null);
  const [prevFairnessIndex, setPrevFairnessIndex] = useState<number | null>(null);
  const [confirmModal, setConfirmModal] = useState(false);
  const [confirmForm] = Form.useForm();
  const [confirmSubmitting, setConfirmSubmitting] = useState(false);

  const [budgetModal, setBudgetModal] = useState(false);
  const [budgetForm] = Form.useForm();
  const [budgetSubmitting, setBudgetSubmitting] = useState(false);

  const loadCore = useCallback(async () => {
    setLoading(true);
    const dateStr = date.format('YYYY-MM-DD');
    const month = date.format('YYYY-MM');
    try {
      const [forecastRes, costRes, budgetRes] = await Promise.all([
        apiClient.get<ForecastResp>(`/api/v1/workforce/stores/${storeId}/labor-forecast`, { params: { date: dateStr } }),
        apiClient.get<LaborCostResp>(`/api/v1/workforce/stores/${storeId}/labor-cost`, { params: { date: dateStr } }),
        apiClient.get<LaborBudgetResp>(`/api/v1/workforce/stores/${storeId}/labor-budget`, { params: { month } }),
      ]);
      setForecast(forecastRes);
      setCost(costRes);
      setBudget(budgetRes);
    } catch (err) {
      handleApiError(err, '加载人力管理数据失败');
    } finally {
      setLoading(false);
    }
  }, [date, storeId]);

  const loadSeries = useCallback(async () => {
    setSeriesLoading(true);
    try {
      const days = Array.from({ length: 30 }).map((_, idx) => dayjs().subtract(29 - idx, 'day'));
      const rows = await Promise.all(
        days.map(async d => {
          const ds = d.format('YYYY-MM-DD');
          const [dailyCost, dailyForecast] = await Promise.all([
            apiClient.get<LaborCostResp>(`/api/v1/workforce/stores/${storeId}/labor-cost`, { params: { date: ds } }),
            apiClient.get<ForecastResp>(`/api/v1/workforce/stores/${storeId}/labor-forecast`, { params: { date: ds } }),
          ]);
          return {
            date: ds,
            actualRate: Number(dailyCost.actual_labor_cost_rate || 0),
            actualHeadcount: Number(dailyCost.headcount_actual || 0),
            recommendedHeadcount: Number(dailyForecast.daily_peak_headcount || 0),
          };
        })
      );
      setSeries(rows);
    } catch (err) {
      handleApiError(err, '加载趋势数据失败');
    } finally {
      setSeriesLoading(false);
    }
  }, [storeId]);

  const loadEmployeeHealth = useCallback(async () => {
    setEmployeeHealthLoading(true);
    try {
      const year = date.year();
      const month = date.month() + 1;
      const prev = date.subtract(1, 'month');

      const [healthRes, fairnessRes, fairnessPrevRes] = await Promise.all([
        apiClient.get<EmployeeHealthResp>(`/api/v1/workforce/stores/${storeId}/employee-health`, {
          params: { year, month, top_n: 20 },
        }),
        apiClient.get<ShiftFairnessDetailResp>(`/api/v1/workforce/stores/${storeId}/shift-fairness-detail`, {
          params: { year, month },
        }),
        apiClient.get<ShiftFairnessDetailResp>(`/api/v1/workforce/stores/${storeId}/shift-fairness-detail`, {
          params: { year: prev.year(), month: prev.month() + 1 },
        }),
      ]);
      setEmployeeHealth(healthRes);
      setFairnessDetail(fairnessRes);
      setPrevFairnessIndex(Number(fairnessPrevRes?.fairness_index ?? null));
    } catch (err) {
      handleApiError(err, '加载员工健康数据失败');
    } finally {
      setEmployeeHealthLoading(false);
    }
  }, [date, storeId]);

  useEffect(() => {
    loadCore();
  }, [loadCore]);

  useEffect(() => {
    loadSeries();
  }, [loadSeries]);

  useEffect(() => {
    loadEmployeeHealth();
  }, [loadEmployeeHealth]);

  const activeForecast = useMemo(() => forecast?.periods?.[selectedPeriod], [forecast, selectedPeriod]);

  const positionRows = useMemo(() => {
    if (!activeForecast?.position_requirements) return [];
    return Object.entries(activeForecast.position_requirements).map(([position, count]) => ({
      key: position,
      position,
      recommended: count,
      delta: (count || 0) - Number(cost?.headcount_actual || 0),
    }));
  }, [activeForecast, cost?.headcount_actual]);

  const costChartOption = useMemo(() => {
    const x = series.map(s => dayjs(s.date).format('MM-DD'));
    const actual = series.map(s => s.actualRate);
    const target = series.map(() => Number(budget?.target_labor_cost_rate || 0));
    const weeklyAvg = series.map((_, idx, arr) => {
      if ((idx + 1) % 7 !== 0) return null;
      const start = idx - 6;
      const seg = arr.slice(start, idx + 1).map(v => v.actualRate);
      return Number((seg.reduce((a, b) => a + b, 0) / seg.length).toFixed(2));
    });
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['实际成本率', '目标线', '周均值'] },
      xAxis: { type: 'category', data: x },
      yAxis: { type: 'value', axisLabel: { formatter: '{value}%' } },
      series: [
        { name: '实际成本率', type: 'line', smooth: true, data: actual },
        { name: '目标线', type: 'line', smooth: true, symbol: 'none', lineStyle: { type: 'dashed' }, data: target },
        { name: '周均值', type: 'bar', data: weeklyAvg },
      ],
    };
  }, [budget?.target_labor_cost_rate, series]);

  const headcountChartOption = useMemo(() => {
    const x = series.map(s => dayjs(s.date).format('MM-DD'));
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: ['实际出勤', '建议人数'] },
      xAxis: { type: 'category', data: x },
      yAxis: { type: 'value' },
      series: [
        { name: '实际出勤', type: 'line', smooth: true, data: series.map(s => s.actualHeadcount) },
        { name: '建议人数', type: 'line', smooth: true, data: series.map(s => s.recommendedHeadcount) },
      ],
    };
  }, [series]);

  const fairnessBarOption = useMemo(() => {
    const dist = fairnessDetail?.distribution || {
      high_unfairness_count: 0,
      medium_unfairness_count: 0,
      low_unfairness_count: 0,
    };
    return {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { top: 16, right: 20, bottom: 10, left: 130 },
      xAxis: {
        type: 'value',
        axisLabel: { formatter: '{value}人' },
      },
      yAxis: {
        type: 'category',
        data: ['高不公平 (>=50%)', '中不公平 (25-50%)', '低不公平 (<25%)'],
      },
      series: [
        {
          name: '班次公平性分布',
          type: 'bar',
          barWidth: 20,
          data: [
            { value: dist.high_unfairness_count, itemStyle: { color: '#ef4444' } },
            { value: dist.medium_unfairness_count, itemStyle: { color: '#f59e0b' } },
            { value: dist.low_unfairness_count, itemStyle: { color: '#10b981' } },
          ],
          label: { show: true, position: 'right', formatter: '{c}人' },
        },
      ],
    };
  }, [fairnessDetail]);

  const fairnessIndexDelta = useMemo(() => {
    if (employeeHealth?.fairness_index == null || prevFairnessIndex == null) return null;
    return Number((employeeHealth.fairness_index - prevFairnessIndex).toFixed(1));
  }, [employeeHealth?.fairness_index, prevFairnessIndex]);

  const submitConfirm = useCallback(async () => {
    try {
      const values = await confirmForm.validateFields();
      setConfirmSubmitting(true);
      await apiClient.post(`/api/v1/workforce/stores/${storeId}/staffing-advice/confirm`, {
        advice_date: date.format('YYYY-MM-DD'),
        meal_period: selectedPeriod,
        action: values.action,
        modified_headcount: values.modified_headcount,
      });
      showSuccess('排班建议已确认');
      setConfirmModal(false);
      confirmForm.resetFields();
      loadCore();
    } catch (err) {
      handleApiError(err, '确认排班建议失败');
    } finally {
      setConfirmSubmitting(false);
    }
  }, [confirmForm, date, loadCore, selectedPeriod, storeId]);

  const submitBudget = useCallback(async () => {
    try {
      const values = await budgetForm.validateFields();
      setBudgetSubmitting(true);
      await apiClient.put(`/api/v1/workforce/stores/${storeId}/labor-budget`, {
        month: date.format('YYYY-MM'),
        target_labor_cost_rate: Number(values.target_labor_cost_rate),
        max_labor_cost_yuan: Number(values.max_labor_cost_yuan),
        daily_budget_yuan: Number(values.daily_budget_yuan || 0),
        alert_threshold_pct: Number(values.alert_threshold_pct || 90),
        is_active: true,
      });
      showSuccess('预算已更新');
      setBudgetModal(false);
      loadCore();
    } catch (err) {
      handleApiError(err, '更新预算失败');
    } finally {
      setBudgetSubmitting(false);
    }
  }, [budgetForm, date, loadCore, storeId]);

  const pageKpis = [
    {
      label: '今日建议人数',
      value: forecast?.daily_peak_headcount ?? '—',
      unit: '人',
      icon: <TeamOutlined style={{ color: '#0AAF9A' }} />,
    },
    {
      label: '当前实际出勤',
      value: cost?.headcount_actual ?? '—',
      unit: '人',
      icon: <TeamOutlined style={{ color: '#1A7A52' }} />,
    },
    {
      label: '本月人工成本率',
      value: cost?.actual_labor_cost_rate != null ? cost.actual_labor_cost_rate.toFixed(1) : '—',
      unit: '%',
      icon: <RiseOutlined style={{ color: '#C8923A' }} />,
      valueColor: cost?.actual_labor_cost_rate != null && budget?.target_labor_cost_rate != null
        ? cost.actual_labor_cost_rate > budget.target_labor_cost_rate ? '#C53030' : '#1A7A52'
        : undefined,
    },
    {
      label: '本月节省',
      value: cost?.saving_yuan != null ? `¥${cost.saving_yuan.toFixed(0)}` : '—',
      icon: <FallOutlined style={{ color: '#1A7A52' }} />,
      valueColor: '#1A7A52',
    },
  ];

  const operationsTab = loading ? <ZSkeleton rows={8} /> : (
    <>
      <div className={styles.kpiGrid}>
        <ZCard><ZKpi label="今日建议人数" value={forecast?.daily_peak_headcount ?? 0} unit="人" /></ZCard>
        <ZCard><ZKpi label="当前实际出勤" value={cost?.headcount_actual ?? 0} unit="人" /></ZCard>
        <ZCard><ZKpi label="本月人工成本率" value={cost?.actual_labor_cost_rate ?? 0} unit="%" /></ZCard>
        <ZCard><ZKpi label="本月节省" value={cost?.saving_yuan ?? 0} unit="¥" /></ZCard>
      </div>

      <div className={styles.sectionGrid}>
        <ZCard title="今日人力建议">
          <Space style={{ marginBottom: 10 }}>
            <Text>餐段</Text>
            <Select<PeriodKey> value={selectedPeriod} onChange={setSelectedPeriod} style={{ width: 130 }}>
              <Select.Option value="morning">早餐</Select.Option>
              <Select.Option value="lunch">午餐</Select.Option>
              <Select.Option value="dinner">晚餐</Select.Option>
            </Select>
            <Tag color="blue">置信度 {(Number(activeForecast?.confidence_score || 0) * 100).toFixed(0)}%</Tag>
          </Space>

          <Alert
            type="info"
            showIcon
            message={`预测客流 ${activeForecast?.predicted_customer_count ?? 0} 人，建议排班 ${activeForecast?.total_headcount_needed ?? 0} 人`}
            style={{ marginBottom: 12 }}
          />

          <Table
            size="small"
            pagination={false}
            rowKey="key"
            dataSource={positionRows}
            columns={[
              { title: '岗位', dataIndex: 'position' },
              { title: '建议人数', dataIndex: 'recommended' },
              {
                title: '较当前差值',
                dataIndex: 'delta',
                render: (v: number) => (v > 0 ? <Tag color="mint">+{v}</Tag> : v < 0 ? <Tag color="green">{v}</Tag> : <Tag>0</Tag>),
              },
            ]}
            style={{ marginBottom: 12 }}
          />

          <div style={{ marginBottom: 12 }}>
            <Text strong>推理链</Text>
            <ol className={styles.reasonList}>
              <li>{activeForecast?.reason_1 || '暂无'}</li>
              <li>{activeForecast?.reason_2 || '暂无'}</li>
              <li>{activeForecast?.reason_3 || '暂无'}</li>
            </ol>
          </div>

          <div className={styles.actions}>
            <ZButton variant="primary" icon={<CheckCircleOutlined />} onClick={() => {
              confirmForm.setFieldsValue({ action: 'confirmed' });
              setConfirmModal(true);
            }}>
              确认排班建议
            </ZButton>
            <ZButton icon={<EditOutlined />} onClick={() => {
              confirmForm.setFieldsValue({
                action: 'modified',
                modified_headcount: activeForecast?.total_headcount_needed ?? 0,
              });
              setConfirmModal(true);
            }}>
              修改并确认
            </ZButton>
          </div>
        </ZCard>

        <ZCard title="预算与告警">
          <Space direction="vertical" style={{ width: '100%' }} size={10}>
            <Text>预算月份：{budget?.budget_period || date.format('YYYY-MM')}</Text>
            <Text>目标成本率：<b>{budget?.target_labor_cost_rate ?? 0}%</b></Text>
            <Text>月度上限：<b>¥{Number(budget?.max_labor_cost_yuan || 0).toLocaleString()}</b></Text>
            <Text>日预算：<b>¥{Number(budget?.daily_budget_yuan || 0).toLocaleString()}</b></Text>
            <Text>预警阈值：<b>{budget?.alert_threshold_pct ?? 90}%</b></Text>
            <ZButton onClick={() => {
              budgetForm.setFieldsValue({
                target_labor_cost_rate: budget?.target_labor_cost_rate ?? 28,
                max_labor_cost_yuan: budget?.max_labor_cost_yuan ?? 0,
                daily_budget_yuan: budget?.daily_budget_yuan ?? 0,
                alert_threshold_pct: budget?.alert_threshold_pct ?? 90,
              });
              setBudgetModal(true);
            }}>
              编辑预算
            </ZButton>
          </Space>
        </ZCard>
      </div>

      <ZCard title="人工成本趋势（近30天）" extra={seriesLoading ? '加载中...' : undefined}>
        <div className={styles.chartBox}>
          <ReactECharts option={costChartOption} style={{ height: 300 }} />
        </div>
      </ZCard>

      <ZCard title="本月与建议对比（近30天）">
        <div className={styles.chartBox}>
          <ReactECharts option={headcountChartOption} style={{ height: 280 }} />
        </div>
      </ZCard>
    </>
  );

  const employeeTab = employeeHealthLoading ? <ZSkeleton rows={6} /> : (
    <>
      <div className={styles.kpiGrid}>
        <ZCard><ZKpi label="员工总数" value={employeeHealth?.total ?? 0} unit="人" /></ZCard>
        <ZCard><ZKpi label="高风险流失" value={employeeHealth?.items.filter(x => x.risk_level === 'high' || x.risk_level === 'critical').length ?? 0} unit="人" /></ZCard>
        <ZCard><ZKpi label="门店公平性指数" value={employeeHealth?.fairness_index ?? 100} unit="" /></ZCard>
        <ZCard><ZKpi label="潜在替换成本" value={employeeHealth?.items.reduce((s, x) => s + (x.replacement_cost_yuan || 0), 0) ?? 0} unit="¥" /></ZCard>
      </div>
      <div className={styles.fairnessTrendRow}>
        <span className={styles.fairnessTrendTitle}>公平指数环比上月</span>
        {fairnessIndexDelta == null ? (
          <Tag>暂无数据</Tag>
        ) : fairnessIndexDelta >= 0 ? (
          <Tag color="green" icon={<RiseOutlined />}>+{fairnessIndexDelta}</Tag>
        ) : (
          <Tag color="red" icon={<FallOutlined />}>{fairnessIndexDelta}</Tag>
        )}
        <span className={styles.fairnessTrendSub}>当前 {Number(employeeHealth?.fairness_index ?? 0).toFixed(1)} / 100</span>
      </div>

      <div className={styles.sectionGrid}>
        <ZCard title="流失风险排名（Top 20）">
          <Table
            size="small"
            rowKey="employee_id"
            pagination={false}
            dataSource={employeeHealth?.items || []}
            expandable={{
              expandedRowRender: (record: EmployeeHealthItem) => {
                const factors = (record.major_risk_factors || []).map((x) => (typeof x === 'string' ? x : x?.name || '未知因素'));
                const isAlerted = !!fairnessDetail?.consecutive_alerts?.includes(record.employee_id);
                return (
                  <div className={styles.expandRow}>
                    <div>
                      <Text type="secondary">主要风险因子：</Text>
                      <div className={styles.factorList}>
                        {factors.length > 0 ? factors.map((f, i) => <Tag key={`${record.employee_id}-${i}`} color="mint">{f}</Tag>) : <Tag>暂无</Tag>}
                      </div>
                    </div>
                    <div className={styles.expandFairnessRow}>
                      <Text type="secondary">班次公平性：</Text>
                      <Tag color={record.unfavorable_ratio >= 0.5 ? 'red' : record.unfavorable_ratio >= 0.25 ? 'orange' : 'green'}>
                        差班 {record.unfavorable_shifts}/{record.total_shifts} · {(record.unfavorable_ratio * 100).toFixed(1)}%
                      </Tag>
                      {isAlerted && <Tag color="magenta">连续差班预警</Tag>}
                    </div>
                  </div>
                );
              },
            }}
            columns={[
              { title: '员工', dataIndex: 'name' },
              { title: '岗位', dataIndex: 'position', render: (v?: string) => v || '-' },
              {
                title: '风险分(90天)',
                dataIndex: 'risk_score_90d',
                render: (v: number) => v.toFixed(2),
              },
              {
                title: '风险等级',
                dataIndex: 'risk_level',
                render: (v: 'critical' | 'high' | 'medium' | 'low') =>
                  v === 'critical' ? <Tag color="magenta">极高</Tag> : v === 'high' ? <Tag color="red">高</Tag> : v === 'medium' ? <Tag color="mint">中</Tag> : <Tag color="green">低</Tag>,
              },
              {
                title: '班次不公平占比',
                dataIndex: 'unfavorable_ratio',
                render: (v: number) => `${(v * 100).toFixed(1)}%`,
              },
              {
                title: '主要因子',
                dataIndex: 'major_risk_factors',
                render: (arr: EmployeeHealthItem['major_risk_factors']) => {
                  const first = (arr || [])[0];
                  const txt = typeof first === 'string' ? first : first?.name;
                  return txt ? <span className={styles.firstFactor}>{txt}</span> : '-';
                },
              },
              {
                title: '替换成本',
                dataIndex: 'replacement_cost_yuan',
                render: (v: number) => `¥${Number(v || 0).toLocaleString()}`,
              },
            ]}
          />
        </ZCard>

        <ZCard title="班次公平性分布">
          <div className={styles.chartBox}>
            <ReactECharts option={fairnessBarOption} style={{ height: 340 }} />
          </div>
        </ZCard>
      </div>
    </>
  );

  const highRiskCount = employeeHealth?.items.filter(x => x.risk_level === 'high' || x.risk_level === 'critical').length ?? 0;

  return (
    <>
      <AgentWorkspaceTemplate
        agentName="人力管理工作台"
        agentIcon="👥"
        agentColor="#0AAF9A"
        description="客流预测 · 排班优化 · 人工成本控制 · 员工健康分析"
        status={loading ? 'idle' : 'running'}
        kpis={pageKpis}
        kpiLoading={loading}
        tabs={[
          { key: 'operations', label: '经营人力', children: operationsTab },
          { key: 'employee',   label: '员工健康', count: highRiskCount, children: employeeTab },
        ]}
        defaultTab="operations"
        loading={loading}
        onRefresh={loadCore}
        headerExtra={
          <Space size="small">
            <Text type="secondary" style={{ fontSize: 12 }}>建议日期</Text>
            <DatePicker value={date} onChange={d => d && setDate(d)} size="small" />
          </Space>
        }
      />

      <Modal
        title="确认排班建议"
        open={confirmModal}
        onCancel={() => setConfirmModal(false)}
        onOk={submitConfirm}
        confirmLoading={confirmSubmitting}
      >
        <Form form={confirmForm} layout="vertical" initialValues={{ action: 'confirmed' }}>
          <Form.Item label="确认动作" name="action" rules={[{ required: true }]}>
            <Select>
              <Select.Option value="confirmed">直接确认</Select.Option>
              <Select.Option value="modified">修改后确认</Select.Option>
              <Select.Option value="rejected">拒绝</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item noStyle shouldUpdate>
            {({ getFieldValue }) => getFieldValue('action') === 'modified' ? (
              <Form.Item label="修改后总人数" name="modified_headcount" rules={[{ required: true, message: '请输入人数' }]}>
                <InputNumber min={1} style={{ width: '100%' }} />
              </Form.Item>
            ) : null}
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="编辑月度人力预算"
        open={budgetModal}
        onCancel={() => setBudgetModal(false)}
        onOk={submitBudget}
        confirmLoading={budgetSubmitting}
      >
        <Form form={budgetForm} layout="vertical">
          <Form.Item label="目标人工成本率（%）" name="target_labor_cost_rate" rules={[{ required: true }]}>
            <InputNumber min={0} max={100} precision={2} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="月度预算上限（¥）" name="max_labor_cost_yuan" rules={[{ required: true }]}>
            <InputNumber min={0} precision={2} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="日预算（¥）" name="daily_budget_yuan">
            <InputNumber min={0} precision={2} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="预警阈值（%）" name="alert_threshold_pct">
            <InputNumber min={0} max={100} precision={2} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default WorkforcePage;
