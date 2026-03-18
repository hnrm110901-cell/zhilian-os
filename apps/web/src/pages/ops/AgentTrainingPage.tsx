import React, { useState } from 'react';
import { ZCard, ZBadge, ZKpi } from '../../design-system/components';
import type { ZTableColumn } from '../../design-system/components';
import ZTable from '../../design-system/components/ZTable';
import styles from './AgentTrainingPage.module.css';

// TODO: GET /api/v1/ops/agent-training/tasks
// TODO: GET /api/v1/ops/agent-training/samples/{agent_id}

// ── 类型 ─────────────────────────────────────────────────────────────────────

interface TrainingTask {
  id: string;
  agentName: string;
  dataSource: string;
  sampleCount: number;
  accuracy: number;
  status: string;
  lastTrained: string;
}

interface TrainingSample {
  id: string;
  input: string;
  expectedOutput: string;
  agentOutput: string;
  correct: boolean;
  reviewNote: string;
}

// ── Mock 数据 ────────────────────────────────────────────────────────────────

const MOCK_TASKS: TrainingTask[] = [
  { id: 'T001', agentName: 'ScheduleAgent', dataSource: '排班历史记录', sampleCount: 12500, accuracy: 94.2, status: '已完成', lastTrained: '2026-03-16 02:00' },
  { id: 'T002', agentName: 'InventoryAgent', dataSource: '库存流水+盘点', sampleCount: 28000, accuracy: 91.8, status: '已完成', lastTrained: '2026-03-15 02:00' },
  { id: 'T003', agentName: 'OrderAgent', dataSource: '订单明细', sampleCount: 45000, accuracy: 96.1, status: '已完成', lastTrained: '2026-03-16 02:00' },
  { id: 'T004', agentName: 'PerformanceAgent', dataSource: 'KPI日快照', sampleCount: 8200, accuracy: 89.5, status: '训练中', lastTrained: '2026-03-17 02:00' },
  { id: 'T005', agentName: 'DecisionAgent', dataSource: '决策日志', sampleCount: 3600, accuracy: 87.3, status: '已完成', lastTrained: '2026-03-14 02:00' },
  { id: 'T006', agentName: 'ServiceAgent', dataSource: '服务评价+工单', sampleCount: 15800, accuracy: 92.7, status: '已完成', lastTrained: '2026-03-15 02:00' },
  { id: 'T007', agentName: 'PrivateDomainAgent', dataSource: '会员行为日志', sampleCount: 52000, accuracy: 90.4, status: '排队中', lastTrained: '2026-03-13 02:00' },
  { id: 'T008', agentName: 'SupplierAgent', dataSource: '采购单+供应商', sampleCount: 6800, accuracy: 88.1, status: '已完成', lastTrained: '2026-03-16 02:00' },
];

const MOCK_SAMPLES: TrainingSample[] = [
  {
    id: 'S001',
    input: '2026-03-15 周六 午餐峰值 预订12桌 当前在岗8人',
    expectedOutput: '建议增加2名服务员至10人，预计峰值接待能力提升25%',
    agentOutput: '建议增加3名服务员，补充至11人，考虑到节假日客流可能超出预期',
    correct: false,
    reviewNote: '人数估算偏高，以历史数据均值为准',
  },
  {
    id: 'S002',
    input: '冰柜温度传感器显示 -5°C，正常范围 -18°C～-22°C',
    expectedOutput: '立即告警，通知厨师长检查设备，评估食材损失风险约¥2,400',
    agentOutput: '立即告警，通知厨师长检查设备，预估食材损失¥2,200～¥2,800',
    correct: true,
    reviewNote: '',
  },
  {
    id: 'S003',
    input: '库存：猪肉剩余3kg，日均消耗2.5kg，明日预计订单120单',
    expectedOutput: '建议今日补货5kg，供应商联系：湘湖肉类，预计送达时间4小时',
    agentOutput: '建议补货5kg，通知供应商',
    correct: false,
    reviewNote: '缺少供应商信息和预计送达时间，输出不完整',
  },
  {
    id: 'S004',
    input: '会员王某 RFM评分：R=45天，F=1次，M=¥180',
    expectedOutput: '流失风险高，建议48小时内发送唤回券¥20，召回成功率约38%',
    agentOutput: '判定为高流失风险会员，建议发送促销消息并推送优惠券',
    correct: false,
    reviewNote: '缺少具体券面额、时效和预期转化率',
  },
];

// ── 组件 ─────────────────────────────────────────────────────────────────────

const AgentTrainingPage: React.FC = () => {
  const [selectedTask, setSelectedTask] = useState<TrainingTask | null>(null);

  const columns: ZTableColumn<TrainingTask>[] = [
    { key: 'agentName', dataIndex: 'agentName', title: 'Agent名称' },
    { key: 'dataSource', dataIndex: 'dataSource', title: '数据源' },
    { key: 'sampleCount', dataIndex: 'sampleCount', title: '样本数', align: 'right',
      render: (v: number) => v.toLocaleString(),
    },
    { key: 'accuracy', dataIndex: 'accuracy', title: '当前准确率', align: 'center',
      render: (v: number) => {
        const cls = v >= 92 ? styles.accuracyHigh : v >= 88 ? styles.accuracyMid : styles.accuracyLow;
        return <span className={cls}>{v}%</span>;
      },
    },
    { key: 'status', dataIndex: 'status', title: '状态',
      render: (v: string) => {
        const typeMap: Record<string, 'success' | 'warning' | 'info'> = {
          '已完成': 'success', '训练中': 'warning', '排队中': 'info',
        };
        return <ZBadge type={typeMap[v] || 'default'} text={v} />;
      },
    },
    { key: 'lastTrained', dataIndex: 'lastTrained', title: '最后训练' },
    { key: 'actions', title: '操作', align: 'center',
      render: (_: unknown, row: TrainingTask) => (
        <button
          className={`${styles.reviewBtn} ${selectedTask?.id === row.id ? styles.reviewBtnActive : ''}`}
          onClick={() => setSelectedTask(row.id === selectedTask?.id ? null : row)}
        >
          审核样本
        </button>
      ),
    },
  ];

  const correctRate = MOCK_SAMPLES.filter((s) => s.correct).length / MOCK_SAMPLES.length * 100;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div>
          <h2>Agent 训练数据</h2>
          <p>AI Agent 训练任务管理，配置训练数据集与评估指标</p>
        </div>
      </div>

      {/* 整体指标 */}
      <div className={styles.kpiRow}>
        <ZCard><ZKpi label="总样本数" value="172.9K" change={8.3} changeLabel="较上周" /></ZCard>
        <ZCard><ZKpi label="平均准确率" value="91.3" unit="%" status="good" /></ZCard>
        <ZCard><ZKpi label="已完成训练" value={6} unit="个Agent" /></ZCard>
        <ZCard><ZKpi label="待训练" value={2} unit="个Agent" /></ZCard>
      </div>

      {/* 训练任务列表 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>训练任务列表</div>
        <ZCard noPadding>
          <ZTable<TrainingTask>
            columns={columns}
            dataSource={MOCK_TASKS}
            rowKey="id"
          />
        </ZCard>
      </div>

      {/* 样本审核面板 */}
      <div className={styles.section}>
        <div className={styles.sectionTitle}>
          样本审核面板
          {selectedTask && (
            <span className={styles.reviewingAgent}> — {selectedTask.agentName}</span>
          )}
        </div>
        <ZCard>
          {!selectedTask ? (
            <div className={styles.reviewPlaceholder}>
              点击训练任务的「审核样本」按钮，查看并审核样本数据
            </div>
          ) : (
            <div className={styles.reviewContent}>
              <div className={styles.reviewStats}>
                <span className={styles.reviewStat}>
                  样本总数: <strong>{selectedTask.sampleCount.toLocaleString()}</strong>
                </span>
                <span className={styles.reviewStat}>
                  抽检通过率: <strong className={correctRate >= 60 ? styles.accuracyHigh : styles.accuracyLow}>{correctRate.toFixed(0)}%</strong>
                </span>
              </div>
              <div className={styles.sampleList}>
                {MOCK_SAMPLES.map((sample) => (
                  <div key={sample.id} className={`${styles.sampleCard} ${sample.correct ? styles.sampleCorrect : styles.sampleWrong}`}>
                    <div className={styles.sampleHeader}>
                      <span className={styles.sampleId}>样本 {sample.id}</span>
                      <ZBadge type={sample.correct ? 'success' : 'error'} text={sample.correct ? '通过' : '不通过'} />
                    </div>
                    <div className={styles.sampleRow}>
                      <span className={styles.sampleLabel}>输入</span>
                      <span className={styles.sampleText}>{sample.input}</span>
                    </div>
                    <div className={styles.sampleRow}>
                      <span className={styles.sampleLabel}>期望输出</span>
                      <span className={styles.sampleText}>{sample.expectedOutput}</span>
                    </div>
                    <div className={styles.sampleRow}>
                      <span className={styles.sampleLabel}>Agent输出</span>
                      <span className={`${styles.sampleText} ${sample.correct ? '' : styles.sampleDiff}`}>{sample.agentOutput}</span>
                    </div>
                    {!sample.correct && sample.reviewNote && (
                      <div className={styles.reviewNote}>审核备注：{sample.reviewNote}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </ZCard>
      </div>
    </div>
  );
};

export default AgentTrainingPage;
