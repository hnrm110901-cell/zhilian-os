/**
 * 数据融合向导页面 — 引导商家完成历史数据接入
 * 路由：/hq/data-fusion
 * 数据：POST/GET /api/v1/data-fusion/*
 *
 * 四步向导：
 * 1. 选择来源系统（品智POS/天财商龙/美团/会员系统等）
 * 2. 配置数据范围（时间范围/实体类型/门店范围）
 * 3. 执行数据融合（实时进度/任务列表/错误处理）
 * 4. 查看经营体检报告（6维分析 + AI建议）
 */
import React, { useState, useCallback } from 'react';
import { ZCard, ZButton, ZKpi, ZEmpty, ZBadge } from '../../design-system/components';
import { message } from 'antd';
import apiClient from '../../services/api';
import styles from './DataFusionWizard.module.css';

// ── 来源系统定义 ─────────────────────────────────────────────────────────────

const SOURCE_SYSTEMS = [
  { type: 'pinzhi', name: '品智POS', category: 'pos', icon: '💳' },
  { type: 'tiancai', name: '天财商龙', category: 'pos', icon: '💰' },
  { type: 'aoqiwei', name: '奥琦玮', category: 'pos', icon: '🏪' },
  { type: 'meituan', name: '美团SaaS', category: 'delivery', icon: '🛵' },
  { type: 'keruyun', name: '客如云', category: 'pos', icon: '☁️' },
  { type: 'yiding', name: '一订预订', category: 'reservation', icon: '📅' },
  { type: 'weishenghuo', name: '微生活会员', category: 'member', icon: '👥' },
  { type: 'nuonuo', name: '诺诺财务', category: 'finance', icon: '📊' },
  { type: 'eleme', name: '饿了么', category: 'delivery', icon: '🥡' },
  { type: 'douyin', name: '抖音本地生活', category: 'delivery', icon: '🎵' },
];

const ENTITY_TYPES = [
  { value: 'order', label: '订单数据', desc: '历史交易记录' },
  { value: 'dish', label: '菜品数据', desc: '菜单/价格/分类' },
  { value: 'customer', label: '会员数据', desc: '客户档案/消费记录' },
  { value: 'ingredient', label: '食材数据', desc: '采购/库存/BOM' },
  { value: 'employee', label: '员工数据', desc: '花名册/排班/考勤' },
  { value: 'supplier', label: '供应商数据', desc: '供应商/采购订单' },
];

const STEPS = [
  { title: '选择系统', desc: '选择要接入的SaaS系统' },
  { title: '配置范围', desc: '设置数据范围和类型' },
  { title: '数据融合', desc: '执行历史数据导入' },
  { title: '体检报告', desc: '查看经营分析报告' },
];

// ── 类型定义 ──────────────────────────────────────────────────────────────────

interface TaskInfo {
  id: string;
  source_system: string;
  entity_type: string;
  status: string;
  progress_pct: number;
  processed_count: number;
  success_count: number;
  error_count: number;
  last_error: string | null;
}

interface ProjectInfo {
  project_id: string;
  status: string;
  progress_pct: number;
  total_tasks: number;
  completed_tasks: number;
  total_records_imported: number;
  tasks: TaskInfo[];
}

// ── 主组件 ────────────────────────────────────────────────────────────────────

export default function DataFusionWizardPage() {
  const [currentStep, setCurrentStep] = useState(0);
  const [selectedSystems, setSelectedSystems] = useState<string[]>([]);
  const [selectedEntities, setSelectedEntities] = useState<string[]>(
    ['order', 'dish', 'customer', 'ingredient']
  );
  const [dateRange, setDateRange] = useState({ months: 6 });
  const [projectInfo, setProjectInfo] = useState<ProjectInfo | null>(null);
  const [loading, setLoading] = useState(false);

  // 步骤1：选择系统
  const toggleSystem = useCallback((type: string) => {
    setSelectedSystems(prev =>
      prev.includes(type) ? prev.filter(s => s !== type) : [...prev, type]
    );
  }, []);

  // 步骤2：选择实体类型
  const toggleEntity = useCallback((type: string) => {
    setSelectedEntities(prev =>
      prev.includes(type) ? prev.filter(e => e !== type) : [...prev, type]
    );
  }, []);

  // 步骤3：创建融合项目
  const startFusion = useCallback(async () => {
    if (selectedSystems.length === 0) {
      message.warning('请至少选择一个来源系统');
      return;
    }
    setLoading(true);
    try {
      const sourceSystems = selectedSystems.map(type => {
        const sys = SOURCE_SYSTEMS.find(s => s.type === type);
        return {
          system_type: type,
          category: sys?.category || 'pos',
          channel: 'api',
        };
      });

      const resp = await apiClient.post('/api/v1/data-fusion/projects', {
        brand_id: 'current_brand',  // 从全局状态获取
        name: `数据融合-${new Date().toISOString().slice(0, 10)}`,
        source_systems: sourceSystems,
        entity_types: selectedEntities,
      });

      setProjectInfo({
        project_id: resp.data.project_id,
        status: 'importing',
        progress_pct: 0,
        total_tasks: resp.data.total_tasks,
        completed_tasks: 0,
        total_records_imported: 0,
        tasks: resp.data.tasks?.map((t: any) => ({
          ...t,
          status: 'pending',
          progress_pct: 0,
          processed_count: 0,
          success_count: 0,
          error_count: 0,
          last_error: null,
        })) || [],
      });
      setCurrentStep(2);
      message.success(`融合项目已创建，共 ${resp.data.total_tasks} 个任务`);
    } catch {
      message.error('创建融合项目失败');
    } finally {
      setLoading(false);
    }
  }, [selectedSystems, selectedEntities]);

  // 刷新进度
  const refreshProgress = useCallback(async () => {
    if (!projectInfo?.project_id) return;
    try {
      const resp = await apiClient.get(
        `/api/v1/data-fusion/projects/${projectInfo.project_id}`
      );
      setProjectInfo({
        project_id: resp.data.project_id,
        status: resp.data.status,
        progress_pct: resp.data.progress_pct,
        total_tasks: resp.data.total_tasks,
        completed_tasks: resp.data.completed_tasks,
        total_records_imported: resp.data.total_records_imported,
        tasks: resp.data.tasks || [],
      });
    } catch {
      // 静默失败
    }
  }, [projectInfo?.project_id]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return styles.taskCompleted;
      case 'running': return styles.taskRunning;
      case 'failed': return styles.taskFailed;
      default: return styles.taskPending;
    }
  };

  const getSystemName = (type: string) =>
    SOURCE_SYSTEMS.find(s => s.type === type)?.name || type;

  const getEntityLabel = (type: string) =>
    ENTITY_TYPES.find(e => e.value === type)?.label || type;

  // ── 渲染 ────────────────────────────────────────────────────────────────

  return (
    <div className={styles.container}>
      {/* 页头 */}
      <div className={styles.header}>
        <div className={styles.title}>数据融合向导</div>
        <div className={styles.subtitle}>
          接入您现有的SaaS系统，屯象OS将自动融合历史数据并生成经营体检报告
        </div>
      </div>

      {/* 步骤指示器 */}
      <div className={styles.steps}>
        {STEPS.map((step, idx) => (
          <div
            key={idx}
            className={`${styles.step} ${
              idx === currentStep ? styles.stepActive :
              idx < currentStep ? styles.stepDone : ''
            }`}
            onClick={() => idx <= currentStep && setCurrentStep(idx)}
          >
            <div className={styles.stepNumber}>
              {idx < currentStep ? '✓' : idx + 1}
            </div>
            <div className={styles.stepTitle}>{step.title}</div>
            <div className={styles.stepDesc}>{step.desc}</div>
          </div>
        ))}
      </div>

      {/* 步骤1：选择来源系统 */}
      {currentStep === 0 && (
        <ZCard title="选择要接入的SaaS系统（可多选）">
          <div className={styles.systemGrid}>
            {SOURCE_SYSTEMS.map(sys => (
              <div
                key={sys.type}
                className={`${styles.systemCard} ${
                  selectedSystems.includes(sys.type) ? styles.systemCardSelected : ''
                }`}
                onClick={() => toggleSystem(sys.type)}
              >
                <div className={styles.systemIcon}>{sys.icon}</div>
                <div className={styles.systemName}>{sys.name}</div>
                <div className={styles.systemCategory}>{sys.category}</div>
              </div>
            ))}
          </div>
          <div className={styles.actions}>
            <div />
            <ZButton
              variant="primary"
              disabled={selectedSystems.length === 0}
              onClick={() => setCurrentStep(1)}
            >
              下一步：配置数据范围
            </ZButton>
          </div>
        </ZCard>
      )}

      {/* 步骤2：配置数据范围 */}
      {currentStep === 1 && (
        <ZCard title="配置融合范围">
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontWeight: 500, marginBottom: 12 }}>数据类型（可多选）</div>
            <div className={styles.systemGrid}>
              {ENTITY_TYPES.map(et => (
                <div
                  key={et.value}
                  className={`${styles.systemCard} ${
                    selectedEntities.includes(et.value) ? styles.systemCardSelected : ''
                  }`}
                  onClick={() => toggleEntity(et.value)}
                >
                  <div className={styles.systemName}>{et.label}</div>
                  <div className={styles.systemCategory}>{et.desc}</div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ marginBottom: 24 }}>
            <div style={{ fontWeight: 500, marginBottom: 12 }}>回溯时间范围</div>
            <div style={{ display: 'flex', gap: 12 }}>
              {[3, 6, 12].map(m => (
                <ZButton
                  key={m}
                  variant={dateRange.months === m ? 'primary' : 'default'}
                  onClick={() => setDateRange({ months: m })}
                >
                  过去{m}个月
                </ZButton>
              ))}
            </div>
          </div>

          <div style={{ padding: 16, background: 'var(--bg-secondary)', borderRadius: 'var(--radius-md)', marginBottom: 24 }}>
            <div style={{ fontWeight: 500, marginBottom: 8 }}>融合计划摘要</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              来源系统：{selectedSystems.map(getSystemName).join('、')}<br />
              数据类型：{selectedEntities.map(getEntityLabel).join('、')}<br />
              时间范围：过去 {dateRange.months} 个月
            </div>
          </div>

          <div className={styles.actions}>
            <ZButton onClick={() => setCurrentStep(0)}>上一步</ZButton>
            <ZButton variant="primary" loading={loading} onClick={startFusion}>
              开始融合
            </ZButton>
          </div>
        </ZCard>
      )}

      {/* 步骤3：融合进度 */}
      {currentStep === 2 && projectInfo && (
        <ZCard
          title="数据融合进行中"
          extra={<ZButton onClick={refreshProgress}>刷新进度</ZButton>}
        >
          <div className={styles.progressPanel}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span>整体进度</span>
              <span>{projectInfo.progress_pct}%</span>
            </div>
            <div className={styles.progressBar}>
              <div
                className={styles.progressFill}
                style={{ width: `${projectInfo.progress_pct}%` }}
              />
            </div>
            <div className={styles.progressStats}>
              <div className={styles.stat}>
                <span className={styles.statLabel}>总任务数</span>
                <span className={styles.statValue}>{projectInfo.total_tasks}</span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statLabel}>已完成</span>
                <span className={styles.statValue}>{projectInfo.completed_tasks}</span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statLabel}>导入记录数</span>
                <span className={styles.statValue}>
                  {projectInfo.total_records_imported.toLocaleString()}
                </span>
              </div>
            </div>
          </div>

          <div style={{ fontWeight: 500, marginBottom: 12 }}>任务列表</div>
          <div className={styles.taskList}>
            {projectInfo.tasks.map((task) => (
              <div key={task.id} className={styles.taskItem}>
                <div className={`${styles.taskStatus} ${getStatusColor(task.status)}`} />
                <div className={styles.taskInfo}>
                  <div className={styles.taskName}>
                    {getSystemName(task.source_system)} → {getEntityLabel(task.entity_type)}
                  </div>
                  <div className={styles.taskMeta}>
                    {task.status === 'completed'
                      ? `完成 ${task.success_count} 条`
                      : task.status === 'running'
                        ? `处理中 ${task.processed_count} 条`
                        : task.status === 'failed'
                          ? `失败: ${task.last_error}`
                          : '等待中'}
                  </div>
                </div>
                {task.status === 'running' && (
                  <ZBadge type="info" text={`${task.progress_pct}%`} />
                )}
              </div>
            ))}
          </div>

          {projectInfo.status === 'resolving' || projectInfo.status === 'completed' ? (
            <div className={styles.actions}>
              <div />
              <ZButton variant="primary" onClick={() => setCurrentStep(3)}>
                查看经营体检报告
              </ZButton>
            </div>
          ) : null}
        </ZCard>
      )}

      {/* 步骤4：经营体检报告 */}
      {currentStep === 3 && (
        <ZCard title="经营体检报告">
          <div className={styles.reportGrid}>
            <div className={styles.reportCard}>
              <div className={styles.reportCardTitle}>营收健康度</div>
              <div className={styles.reportCardValue}>--</div>
              <div className={styles.reportCardSub}>月均营收 / 客单价 / 翻台率</div>
            </div>
            <div className={styles.reportCard}>
              <div className={styles.reportCardTitle}>成本真相</div>
              <div className={styles.reportCardValue}>--</div>
              <div className={styles.reportCardSub}>食材成本率 / 行业基准对比</div>
            </div>
            <div className={styles.reportCard}>
              <div className={styles.reportCardTitle}>菜品表现</div>
              <div className={styles.reportCardValue}>--</div>
              <div className={styles.reportCardSub}>明星菜 / 金牛 / 问题 / 瘦狗</div>
            </div>
            <div className={styles.reportCard}>
              <div className={styles.reportCardTitle}>会员资产</div>
              <div className={styles.reportCardValue}>--</div>
              <div className={styles.reportCardSub}>活跃 / 沉睡 / 流失预警</div>
            </div>
            <div className={styles.reportCard}>
              <div className={styles.reportCardTitle}>人效分析</div>
              <div className={styles.reportCardValue}>--</div>
              <div className={styles.reportCardSub}>营收/人/时 / 峰值缺口</div>
            </div>
            <div className={styles.reportCard}>
              <div className={styles.reportCardTitle}>供应商评估</div>
              <div className={styles.reportCardValue}>--</div>
              <div className={styles.reportCardSub}>价格稳定性 / 交付准时率</div>
            </div>
          </div>
          <ZEmpty description="融合完成后自动生成6维经营体检报告" />
        </ZCard>
      )}
    </div>
  );
}
