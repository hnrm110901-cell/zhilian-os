/**
 * BOM 管理页面（配方版本化管理）
 *
 * 功能：
 *   - 门店 BOM 列表（按菜品分组，当前激活版本高亮）
 *   - BOM 明细行：食材 / 标准用量 / 单位 / 出成率
 *   - 版本历史浏览
 *   - 版本激活（将选中版本设为当前版本）
 *   - 新建 BOM 及添加食材行
 *   - Excel 批量导入入口
 */
import React, { useState, useCallback, useEffect } from 'react';
import {
  Form, Input, InputNumber, Select, Upload, Drawer, message,
} from 'antd';
import type { UploadProps } from 'antd';
import {
  PlusOutlined, UploadOutlined, CheckCircleOutlined,
  HistoryOutlined, EyeOutlined, ThunderboltOutlined,
  ReloadOutlined, BookOutlined, DollarOutlined,
} from '@ant-design/icons';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZSelect,
  ZTable, ZModal, ZEmpty,
} from '../design-system/components';
import type { ZTableColumn } from '../design-system/components/ZTable';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';
import styles from './BOMManagementPage.module.css';

const { Option } = Select;

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface BOMItem {
  id: string;
  ingredient_id: string;
  standard_qty: number;
  raw_qty: number | null;
  unit: string;
  unit_cost: number | null;
  waste_factor: number;
  is_key_ingredient: boolean;
  is_optional: boolean;
  prep_notes: string | null;
}

interface BOMTemplate {
  id: string;
  store_id: string;
  dish_id: string;
  version: string;
  effective_date: string;
  expiry_date: string | null;
  yield_rate: number;
  standard_portion: number | null;
  prep_time_minutes: number | null;
  is_active: boolean;
  is_approved: boolean;
  approved_by: string | null;
  notes: string | null;
  created_by: string | null;
  items: BOMItem[];
}

interface CostReportItem {
  ingredient_id: string;
  standard_qty: number;
  unit: string;
  unit_cost_fen: number;
  item_cost_fen: number;
  item_cost_yuan: number;
  cost_pct: number;
}

interface CostReport {
  bom_id: string;
  dish_id: string;
  version: string;
  total_cost_fen: number;
  total_cost_yuan: number;
  price_yuan: number;
  food_cost_pct: number;
  items: CostReportItem[];
}

// ── 列定义（放组件外避免每次渲染重新创建） ────────────────────────────────────

const itemColumns: ZTableColumn<BOMItem>[] = [
  {
    key: 'ingredient_id',
    title: '食材 ID',
    render: (v: string) => <code style={{ fontSize: 12 }}>{v}</code>,
  },
  {
    key: 'standard_qty',
    title: '标准用量',
    width: 90,
    render: (v: number, row: BOMItem) => `${v} ${row.unit}`,
  },
  {
    key: 'raw_qty',
    title: '毛料用量',
    width: 90,
    render: (v: number | null, row: BOMItem) => v != null ? `${v} ${row.unit}` : '—',
  },
  {
    key: 'waste_factor',
    title: '损耗系数',
    width: 90,
    render: (v: number) => `${(v * 100).toFixed(1)}%`,
  },
  {
    key: 'unit_cost',
    title: '单价(分)',
    width: 90,
    align: 'right',
    render: (v: number | null) => v != null ? `¥${(v / 100).toFixed(2)}` : '—',
  },
  {
    key: 'is_key_ingredient',
    title: '标签',
    width: 120,
    render: (_: any, row: BOMItem) => (
      <div style={{ display: 'flex', gap: 4 }}>
        {row.is_key_ingredient && <ZBadge type="critical" text="核心" />}
        {row.is_optional && <ZBadge type="default" text="可选" />}
      </div>
    ),
  },
  {
    key: 'prep_notes',
    title: '加工说明',
    render: (v: string | null) => v || '—',
  },
];

const costItemColumns: ZTableColumn<CostReportItem>[] = [
  {
    key: 'ingredient_id',
    title: '食材',
    render: (v: string) => <code style={{ fontSize: 11 }}>{v}</code>,
  },
  {
    key: 'standard_qty',
    title: '标准用量',
    width: 100,
    render: (v: number, row: CostReportItem) => `${v} ${row.unit}`,
  },
  {
    key: 'unit_cost_fen',
    title: '单价',
    width: 80,
    align: 'right',
    render: (v: number) => v ? `¥${(v / 100).toFixed(2)}` : '—',
  },
  {
    key: 'item_cost_yuan',
    title: '成本',
    width: 80,
    align: 'right',
    render: (v: number) => `¥${Number(v).toFixed(2)}`,
  },
  {
    key: 'cost_pct',
    title: '占比',
    width: 140,
    render: (v: number) => {
      const barColor = v >= 40 ? 'var(--red)' : v >= 25 ? 'var(--yellow)' : 'var(--green)';
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 80, height: 5, background: '#f0f0f0', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{ width: `${Math.min(v, 100)}%`, height: '100%', background: barColor, borderRadius: 3 }} />
          </div>
          <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{v}%</span>
        </div>
      );
    },
  },
];

// ── 主组件 ────────────────────────────────────────────────────────────────────

const BOMManagementPage: React.FC = () => {
  const [storeId, setStoreId]       = useState(localStorage.getItem('store_id') || '');
  const [stores, setStores]         = useState<any[]>([]);
  const [boms, setBoms]             = useState<BOMTemplate[]>([]);
  const [loading, setLoading]       = useState(false);
  const [selectedBom, setSelectedBom] = useState<BOMTemplate | null>(null);
  const [historyBoms, setHistoryBoms] = useState<BOMTemplate[]>([]);
  const [historyDishId, setHistoryDishId] = useState<string | null>(null);

  // 成本分析
  const [costReport, setCostReport]             = useState<CostReport | null>(null);
  const [costReportVisible, setCostReportVisible] = useState(false);
  const [costReportLoading, setCostReportLoading] = useState(false);

  // 新建 BOM modal
  const [createVisible, setCreateVisible] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [createForm] = Form.useForm();

  // 添加食材行 modal
  const [itemVisible, setItemVisible]   = useState(false);
  const [itemLoading, setItemLoading]   = useState(false);
  const [itemForm] = Form.useForm();
  const [targetBomId, setTargetBomId]   = useState<string | null>(null);

  // 抽屉
  const [detailVisible, setDetailVisible]   = useState(false);
  const [historyVisible, setHistoryVisible] = useState(false);

  // ── 数据加载 ────────────────────────────────────────────────────────────────

  const loadBoms = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get(`/api/v1/bom/store/${storeId}`);
      setBoms(res || []);
    } catch (err: any) {
      handleApiError(err, '加载 BOM 列表失败');
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/api/v1/stores');
      const list: any[] = res.stores || res || [];
      setStores(list);
      if (list.length > 0 && !list.find((s: any) => (s.store_id || s.id) === storeId)) {
        setStoreId(list[0].store_id || list[0].id || '');
      }
    } catch { /* ignore */ }
  }, [storeId]);

  useEffect(() => { loadStores(); loadBoms(); }, [loadStores, loadBoms]);

  // ── 查看 BOM 详情 ───────────────────────────────────────────────────────────

  const viewDetail = useCallback(async (bom: BOMTemplate) => {
    try {
      const res = await apiClient.get(`/api/v1/bom/${bom.id}`);
      setSelectedBom(res);
      setDetailVisible(true);
    } catch (err: any) {
      handleApiError(err, '加载 BOM 详情失败');
    }
  }, []);

  // ── 查看版本历史 ────────────────────────────────────────────────────────────

  const viewHistory = useCallback(async (dishId: string) => {
    setHistoryDishId(dishId);
    try {
      const res = await apiClient.get(`/api/v1/bom/dish/${dishId}/history`);
      setHistoryBoms(res || []);
      setHistoryVisible(true);
    } catch (err: any) {
      handleApiError(err, '加载版本历史失败');
    }
  }, []);

  // ── 激活版本 ────────────────────────────────────────────────────────────────

  const activateBom = useCallback(async (bomId: string) => {
    try {
      await apiClient.post(`/api/v1/bom/${bomId}/activate`);
      showSuccess('版本已激活');
      loadBoms();
      if (historyDishId) {
        const res = await apiClient.get(`/api/v1/bom/dish/${historyDishId}/history`);
        setHistoryBoms(res || []);
      }
    } catch (err: any) {
      handleApiError(err, '激活失败');
    }
  }, [loadBoms, historyDishId]);

  // ── 审核 BOM ────────────────────────────────────────────────────────────────

  const approveBom = useCallback(async (bomId: string) => {
    try {
      await apiClient.post(`/api/v1/bom/${bomId}/approve`);
      showSuccess('BOM 审核通过');
      loadBoms();
    } catch (err: any) {
      handleApiError(err, '审核失败');
    }
  }, [loadBoms]);

  // ── 成本分析 ────────────────────────────────────────────────────────────────

  const loadCostReport = useCallback(async (bomId: string) => {
    setCostReportLoading(true);
    setCostReportVisible(true);
    try {
      const res = await apiClient.get(`/api/v1/bom/${bomId}/cost-report`);
      setCostReport(res.data);
    } catch (err: any) {
      handleApiError(err, '加载成本分析失败');
      setCostReportVisible(false);
    } finally {
      setCostReportLoading(false);
    }
  }, []);

  // ── 新建 BOM ────────────────────────────────────────────────────────────────

  const handleCreateBom = async (values: any) => {
    setCreateLoading(true);
    try {
      await apiClient.post('/api/v1/bom/', {
        ...values,
        store_id: storeId,
        activate: values.activate !== false,
      });
      showSuccess('BOM 创建成功');
      setCreateVisible(false);
      createForm.resetFields();
      loadBoms();
    } catch (err: any) {
      handleApiError(err, '创建 BOM 失败');
    } finally {
      setCreateLoading(false);
    }
  };

  // ── 添加食材行 ──────────────────────────────────────────────────────────────

  const openAddItem = (bomId: string) => {
    setTargetBomId(bomId);
    itemForm.resetFields();
    setItemVisible(true);
  };

  const handleAddItem = async (values: any) => {
    if (!targetBomId) return;
    setItemLoading(true);
    try {
      await apiClient.post(`/api/v1/bom/${targetBomId}/items`, values);
      showSuccess('食材行已添加');
      setItemVisible(false);
      const res = await apiClient.get(`/api/v1/bom/${targetBomId}`);
      setSelectedBom(res);
      loadBoms();
    } catch (err: any) {
      handleApiError(err, '添加食材行失败');
    } finally {
      setItemLoading(false);
    }
  };

  // ── Excel 导入 ──────────────────────────────────────────────────────────────

  const uploadProps: UploadProps = {
    name: 'file',
    accept: '.xlsx,.xls',
    action: `/api/v1/bom/import/excel?store_id=${storeId}`,
    headers: {
      Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
    },
    showUploadList: false,
    onChange(info) {
      if (info.file.status === 'done') {
        const result = info.file.response;
        showSuccess(`导入完成：新建 ${result?.created ?? 0} 条，跳过 ${result?.skipped ?? 0} 条`);
        loadBoms();
      } else if (info.file.status === 'error') {
        message.error('Excel 导入失败，请检查文件格式');
      }
    },
  };

  // ── 统计 ────────────────────────────────────────────────────────────────────

  const totalBoms    = boms.length;
  const activeBoms   = boms.filter(b => b.is_active).length;
  const approvedBoms = boms.filter(b => b.is_approved).length;
  const avgYieldRate = boms.length > 0
    ? (boms.reduce((s, b) => s + b.yield_rate, 0) / boms.length * 100).toFixed(1)
    : '0.0';

  const storeOptions = stores.length > 0
    ? stores.map((s: any) => ({ value: s.store_id || s.id, label: s.name || s.store_id || s.id }))
    : [];

  // ── BOM 列表列定义 ──────────────────────────────────────────────────────────

  const bomColumns: ZTableColumn<BOMTemplate>[] = [
    {
      key: 'dish_id',
      title: '菜品 ID',
      width: 200,
      render: (v: string) => <code style={{ fontSize: 12 }}>{v}</code>,
    },
    {
      key: 'version',
      title: '版本',
      width: 90,
      render: (v: string, rec: BOMTemplate) => (
        <ZBadge type={rec.is_active ? 'success' : 'default'} text={v} />
      ),
    },
    {
      key: 'yield_rate',
      title: '出成率',
      width: 90,
      align: 'center',
      render: (v: number) => <ZBadge type="info" text={`${(v * 100).toFixed(1)}%`} />,
    },
    {
      key: 'items',
      title: '食材数',
      width: 80,
      align: 'center',
      render: (items: BOMItem[]) => items?.length ?? 0,
    },
    {
      key: 'effective_date',
      title: '生效日期',
      width: 120,
      render: (v: string) => v?.slice(0, 10),
    },
    {
      key: 'is_active',
      title: '状态',
      width: 140,
      render: (_: any, rec: BOMTemplate) => (
        <div style={{ display: 'flex', gap: 4 }}>
          {rec.is_active && (
            <ZBadge type="success" text="当前" />
          )}
          <ZBadge
            type={rec.is_approved ? 'info' : 'warning'}
            text={rec.is_approved ? '已审核' : '待审核'}
          />
        </div>
      ),
    },
    {
      key: 'id',
      title: '操作',
      width: 220,
      render: (_: any, rec: BOMTemplate) => (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          <ZButton size="sm" icon={<EyeOutlined />} onClick={() => viewDetail(rec)} title="查看详情" />
          <ZButton
            size="sm"
            icon={<DollarOutlined />}
            onClick={() => loadCostReport(rec.id)}
            title="成本分析"
            style={{ color: '#1A7A52', borderColor: '#1A7A52' }}
          />
          <ZButton size="sm" icon={<HistoryOutlined />} onClick={() => viewHistory(rec.dish_id)} title="版本历史" />
          {!rec.is_active && (
            <ZButton
              size="sm"
              variant="primary"
              icon={<ThunderboltOutlined />}
              title="激活版本"
              onClick={() => {
                if (window.confirm('激活此版本将停用同菜品的当前版本，确认？')) {
                  activateBom(rec.id);
                }
              }}
            />
          )}
          {!rec.is_approved && (
            <ZButton
              size="sm"
              onClick={() => {
                if (window.confirm('审核通过此 BOM？')) approveBom(rec.id);
              }}
            >
              审核
            </ZButton>
          )}
          <ZButton size="sm" icon={<PlusOutlined />} onClick={() => openAddItem(rec.id)} title="添加食材行" />
        </div>
      ),
    },
  ];

  // ── 版本历史列定义 ──────────────────────────────────────────────────────────

  const historyColumns: ZTableColumn<BOMTemplate>[] = [
    { key: 'version', title: '版本', width: 80 },
    {
      key: 'effective_date',
      title: '生效日期',
      width: 110,
      render: (v: string) => v?.slice(0, 10),
    },
    {
      key: 'expiry_date',
      title: '失效日期',
      width: 110,
      render: (v: string | null) => v ? v.slice(0, 10) : <ZBadge type="success" text="当前" />,
    },
    {
      key: 'yield_rate',
      title: '出成率',
      width: 80,
      align: 'center',
      render: (v: number) => `${(v * 100).toFixed(1)}%`,
    },
    {
      key: 'items',
      title: '食材数',
      width: 70,
      align: 'center',
      render: (items: BOMItem[]) => items?.length ?? 0,
    },
    {
      key: 'is_approved',
      title: '状态',
      width: 120,
      render: (_: any, rec: BOMTemplate) => (
        <div style={{ display: 'flex', gap: 4 }}>
          <ZBadge
            type={rec.is_active ? 'success' : 'default'}
            text={rec.is_active ? '激活' : '历史'}
          />
          {rec.is_approved && <ZBadge type="info" text="已审核" />}
        </div>
      ),
    },
    {
      key: 'id',
      title: '操作',
      width: 100,
      render: (_: any, rec: BOMTemplate) => !rec.is_active ? (
        <ZButton
          size="sm"
          variant="primary"
          icon={<ThunderboltOutlined />}
          onClick={() => {
            if (window.confirm('激活此版本将停用当前版本，确认？')) activateBom(rec.id);
          }}
        >
          激活
        </ZButton>
      ) : null,
    },
  ];

  // ── 渲染 ────────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <h2 className={styles.pageTitle}>
            <BookOutlined style={{ marginRight: 8 }} />
            BOM 配方管理
          </h2>
          <p className={styles.pageSub}>管理门店菜品的标准配方版本、食材用量及出成率</p>
        </div>
        <div className={styles.headerActions}>
          <ZSelect
            value={storeId}
            options={storeOptions}
            onChange={(v) => setStoreId(v as string)}
            style={{ width: 160 }}
          />
          <Upload {...uploadProps}>
            <ZButton icon={<UploadOutlined />}>Excel 导入</ZButton>
          </Upload>
          <ZButton variant="primary" icon={<PlusOutlined />} onClick={() => setCreateVisible(true)}>
            新建 BOM
          </ZButton>
          <ZButton icon={<ReloadOutlined />} onClick={loadBoms} disabled={loading} />
        </div>
      </div>

      {/* 统计卡片 */}
      <div className={styles.kpiGrid}>
        <ZCard><ZKpi value={totalBoms}    unit="个" label="BOM 总数" /></ZCard>
        <ZCard><ZKpi value={activeBoms}   unit="个" label="激活版本" /></ZCard>
        <ZCard><ZKpi value={`${approvedBoms} / ${totalBoms}`} label="已审核" /></ZCard>
        <ZCard><ZKpi value={avgYieldRate} unit="%"  label="平均出成率" /></ZCard>
      </div>

      {/* BOM 列表 */}
      <ZCard
        title="配方版本列表"
        extra={
          <span className={styles.hintText}>
            <CheckCircleOutlined style={{ color: '#1A7A52', marginRight: 4 }} />
            绿色徽标 = 当前激活版本
          </span>
        }
      >
        {loading ? (
          <ZSkeleton rows={6} block />
        ) : boms.length === 0 ? (
          <ZEmpty description="暂无 BOM 数据" />
        ) : (
          <ZTable<BOMTemplate>
            columns={bomColumns}
            data={boms}
            rowKey="id"
            emptyText="暂无 BOM 数据"
          />
        )}
      </ZCard>

      {/* ── BOM 详情 Drawer ──────────────────────────────────────────────────── */}
      <Drawer
        title={
          selectedBom ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <BookOutlined />
              BOM 详情
              <span style={{
                fontSize: 12, padding: '1px 8px', borderRadius: 12,
                background: selectedBom.is_active ? 'rgba(26,122,82,0.08)' : '#f5f5f5',
                color: selectedBom.is_active ? '#1A7A52' : '#595959',
                border: `1px solid ${selectedBom.is_active ? 'rgba(26,122,82,0.3)' : '#d9d9d9'}`,
              }}>
                {selectedBom.version}
              </span>
            </div>
          ) : 'BOM 详情'
        }
        open={detailVisible}
        onClose={() => setDetailVisible(false)}
        width={720}
        extra={
          selectedBom && (
            <ZButton variant="primary" icon={<PlusOutlined />} onClick={() => openAddItem(selectedBom.id)}>
              添加食材行
            </ZButton>
          )
        }
      >
        {selectedBom && (
          <>
            <dl className={styles.descList}>
              <div className={styles.descRow2}><dt>菜品 ID</dt><dd><code>{selectedBom.dish_id}</code></dd></div>
              <div className={styles.descRowGrid}>
                <div className={styles.descRow}><dt>版本</dt><dd>{selectedBom.version}</dd></div>
                <div className={styles.descRow}><dt>出成率</dt><dd>{(selectedBom.yield_rate * 100).toFixed(2)}%</dd></div>
              </div>
              <div className={styles.descRowGrid}>
                <div className={styles.descRow}><dt>生效日期</dt><dd>{selectedBom.effective_date?.slice(0, 10)}</dd></div>
                <div className={styles.descRow}><dt>失效日期</dt><dd>{selectedBom.expiry_date?.slice(0, 10) ?? '—'}</dd></div>
              </div>
              {selectedBom.standard_portion != null && (
                <div className={styles.descRow}><dt>标准份重</dt><dd>{selectedBom.standard_portion} g</dd></div>
              )}
              {selectedBom.prep_time_minutes != null && (
                <div className={styles.descRow}><dt>制作工时</dt><dd>{selectedBom.prep_time_minutes} min</dd></div>
              )}
              <div className={styles.descRow2}>
                <dt>审核状态</dt>
                <dd>
                  {selectedBom.is_approved ? (
                    <ZBadge type="info" text={`已审核${selectedBom.approved_by ? `（${selectedBom.approved_by}）` : ''}`} />
                  ) : (
                    <ZBadge type="warning" text="待审核" />
                  )}
                </dd>
              </div>
              {selectedBom.notes && (
                <div className={styles.descRow2}><dt>备注</dt><dd>{selectedBom.notes}</dd></div>
              )}
            </dl>

            <div className={styles.sectionTitle}>
              食材明细（{selectedBom.items?.length ?? 0} 行）
            </div>

            <ZTable<BOMItem>
              columns={itemColumns}
              data={selectedBom.items || []}
              rowKey="id"
              emptyText="暂无食材行"
            />
          </>
        )}
      </Drawer>

      {/* ── 版本历史 Drawer ──────────────────────────────────────────────────── */}
      <Drawer
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <HistoryOutlined />
            版本历史
          </div>
        }
        open={historyVisible}
        onClose={() => setHistoryVisible(false)}
        width={760}
      >
        <ZTable<BOMTemplate>
          columns={historyColumns}
          data={historyBoms}
          rowKey="id"
          emptyText="暂无历史版本"
        />
      </Drawer>

      {/* ── 成本分析 Modal ────────────────────────────────────────────────────── */}
      <ZModal
        open={costReportVisible}
        title={
          costReport
            ? `BOM 成本分析  v${costReport.version}`
            : 'BOM 成本分析'
        }
        onClose={() => { setCostReportVisible(false); setCostReport(null); }}
        width={640}
      >
        {costReportLoading ? (
          <ZSkeleton rows={5} block />
        ) : costReport ? (
          <>
            <div className={styles.kpiGrid3}>
              <ZCard>
                <ZKpi value={`¥${costReport.total_cost_yuan.toFixed(2)}`} label="标准总成本" />
              </ZCard>
              <ZCard>
                <ZKpi value={`¥${costReport.price_yuan.toFixed(2)}`} label="菜品售价" />
              </ZCard>
              <ZCard>
                <ZKpi value={costReport.food_cost_pct.toFixed(1)} unit="%" label="食材成本率" />
              </ZCard>
            </div>

            <div className={styles.sectionTitle} style={{ marginTop: 16 }}>
              食材成本明细（按贡献降序）
            </div>

            <ZTable<CostReportItem>
              columns={costItemColumns}
              data={costReport.items}
              rowKey="ingredient_id"
              emptyText="暂无明细数据"
            />
          </>
        ) : null}
      </ZModal>

      {/* ── 新建 BOM Modal ───────────────────────────────────────────────────── */}
      <ZModal
        open={createVisible}
        title="新建 BOM 版本"
        onClose={() => setCreateVisible(false)}
        width={560}
        footer={
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <ZButton onClick={() => setCreateVisible(false)}>取消</ZButton>
            <ZButton variant="primary" disabled={createLoading} onClick={() => createForm.submit()}>
              {createLoading ? '创建中…' : '确定'}
            </ZButton>
          </div>
        }
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={handleCreateBom}
          initialValues={{ activate: true, yield_rate: 1.0 }}
        >
          <Form.Item name="dish_id" label="菜品 ID" rules={[{ required: true, message: '请输入菜品 ID' }]}>
            <Input placeholder="例：DISH-001" />
          </Form.Item>
          <Form.Item name="version" label="版本号" rules={[{ required: true, message: '请输入版本号' }]}>
            <Input placeholder="例：v1 / v2 / 2026-03" />
          </Form.Item>
          <div className={styles.formRow2}>
            <Form.Item name="yield_rate" label="出成率">
              <InputNumber
                min={0.01} max={1.0} step={0.01} style={{ width: '100%' }}
                formatter={(v) => `${((v as number) * 100).toFixed(0)}%`}
                parser={(v) => parseFloat((v || '100').replace('%', '')) / 100 as unknown as 1}
              />
            </Form.Item>
            <Form.Item name="standard_portion" label="标准份重（g）">
              <InputNumber min={1} style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <Form.Item name="prep_time_minutes" label="制作工时（分钟）">
            <InputNumber min={1} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="activate" label="创建后立即激活">
            <Select style={{ width: 160 }}>
              <Option value={true}>是</Option>
              <Option value={false}>否（保存为草稿）</Option>
            </Select>
          </Form.Item>
        </Form>
      </ZModal>

      {/* ── 添加食材行 Modal ─────────────────────────────────────────────────── */}
      <ZModal
        open={itemVisible}
        title="添加食材行"
        onClose={() => setItemVisible(false)}
        width={560}
        footer={
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <ZButton onClick={() => setItemVisible(false)}>取消</ZButton>
            <ZButton variant="primary" disabled={itemLoading} onClick={() => itemForm.submit()}>
              {itemLoading ? '添加中…' : '确定'}
            </ZButton>
          </div>
        }
      >
        <Form
          form={itemForm}
          layout="vertical"
          onFinish={handleAddItem}
          initialValues={{ waste_factor: 0, is_key_ingredient: false, is_optional: false }}
        >
          <Form.Item name="ingredient_id" label="食材 ID" rules={[{ required: true, message: '请输入食材 ID' }]}>
            <Input placeholder="对应 InventoryItem.id，例：ING-PORK-001" />
          </Form.Item>
          <div className={styles.formRow2}>
            <Form.Item name="standard_qty" label="标准用量" rules={[{ required: true, message: '请输入用量' }]}>
              <InputNumber min={0.001} step={0.5} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="unit" label="单位" rules={[{ required: true, message: '请选择单位' }]}>
              <Select>
                {['g', 'kg', 'ml', 'L', '个', '份', '片', '条'].map((u) => (
                  <Option key={u} value={u}>{u}</Option>
                )) : null}
              </Select>
            </Form.Item>
          </div>
          <div className={styles.formRow2}>
            <Form.Item name="raw_qty" label="毛料用量（可选）">
              <InputNumber min={0} step={0.5} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="unit_cost" label="单价（分，可选）">
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <div className={styles.formRow2}>
            <Form.Item name="waste_factor" label="损耗系数（0~1）">
              <InputNumber min={0} max={1} step={0.01} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="is_key_ingredient" label="核心食材">
              <Select>
                <Option value={false}>否</Option>
                <Option value={true}>是（重点监控）</Option>
              </Select>
            </Form.Item>
          </div>
          <Form.Item name="prep_notes" label="加工说明">
            <Input placeholder="例：去骨、切丁、腌制20分钟" />
          </Form.Item>
        </Form>
      </ZModal>
    </div>
  );
};

export default BOMManagementPage;
