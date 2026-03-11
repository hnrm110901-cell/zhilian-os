/**
 * 店长人力建议页（移动端）
 * 路由：/sm/workforce
 * 数据：GET /api/v1/workforce/stores/{store_id}/staffing-advice
 *      POST /api/v1/workforce/stores/{store_id}/staffing-advice/confirm
 */
import React, { useCallback, useEffect, useState } from 'react';
import dayjs from 'dayjs';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty, ZModal,
} from '../../design-system/components';
import { Form, InputNumber, Select, Input } from 'antd';
import apiClient from '../../services/api';
import { handleApiError, showSuccess, showError } from '../../utils/message';
import styles from './Workforce.module.css';

const STORE_ID = localStorage.getItem('store_id') || 'S001';
const TOMORROW  = dayjs().add(1, 'day').format('YYYY-MM-DD');

interface PositionBreakdown {
  [position: string]: number;
}

interface Advice {
  exists:                       boolean;
  store_id:                     string;
  advice_date:                  string;
  meal_period:                  string;
  status:                       string | null;
  recommended_headcount:        number | null;
  current_scheduled_headcount:  number | null;
  headcount_delta:              number | null;
  estimated_saving_yuan:        number | null;
  estimated_overspend_yuan:     number | null;
  confidence_score:             number | null;
  position_breakdown:           PositionBreakdown | null;
  reason_1:                     string | null;
  reason_2:                     string | null;
  reason_3:                     string | null;
  confirmed_action:             string | null;
  confirmed_at:                 string | null;
}

const ACTION_LABELS: Record<string, { text: string; type: 'success' | 'info' | 'warning' }> = {
  confirmed: { text: '已确认',    type: 'success' },
  modified:  { text: '修改确认',  type: 'info'    },
  rejected:  { text: '已拒绝',    type: 'warning' },
};

const STATUS_LABELS: Record<string, string> = {
  pending:   '待处理',
  confirmed: '已确认',
  rejected:  '已拒绝',
  expired:   '已过期',
};

export default function SmWorkforce() {
  const [advice,     setAdvice]     = useState<Advice | null>(null);
  const [loading,    setLoading]    = useState(true);
  const [modal,      setModal]      = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form]                      = Form.useForm();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await apiClient.get(
        `/api/v1/workforce/stores/${STORE_ID}/staffing-advice`,
        { params: { date: TOMORROW, meal_period: 'all_day' } }
      );
      setAdvice(resp);
    } catch (e) {
      handleApiError(e, '人力建议加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSubmit = async () => {
    let values: Record<string, any>;
    try { values = await form.validateFields(); }
    catch { return; }

    setSubmitting(true);
    try {
      await apiClient.post(
        `/api/v1/workforce/stores/${STORE_ID}/staffing-advice/confirm`,
        {
          advice_date:           TOMORROW,
          meal_period:           'all_day',
          action:                values.action,
          modified_headcount:    values.action === 'modified' ? values.modified_headcount : undefined,
          rejection_reason:      values.action === 'rejected'  ? values.rejection_reason  : undefined,
        }
      );
      showSuccess('处理成功');
      setModal(false);
      form.resetFields();
      load();
    } catch (e) {
      showError('提交失败，请重试');
    } finally {
      setSubmitting(false);
    }
  };

  const a = advice;
  const savingYuan = a?.estimated_saving_yuan ?? 0;
  const confidencePct = a?.confidence_score != null ? Math.round(a.confidence_score * 100) : null;
  const reasons = [a?.reason_1, a?.reason_2, a?.reason_3].filter(Boolean);
  const isHandled = !!a?.confirmed_action;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>明日人力建议</div>
        <div className={styles.subtitle}>{TOMORROW}</div>
      </div>

      {loading ? (
        <div className={styles.body}><ZSkeleton rows={4} /></div>
      ) : !a?.exists ? (
        <div className={styles.body}>
          <ZEmpty
            title="暂无明日建议"
            description="建议通常在每日07:00自动生成"
          />
        </div>
      ) : (
        <div className={styles.body}>
          {/* KPI 行 */}
          <div className={styles.kpiRow}>
            <ZCard>
              <ZKpi
                value={a.recommended_headcount ?? '-'}
                label="建议人数"
                unit="人"
                change={a.headcount_delta ?? undefined}
                changeLabel="较今日"
                size="lg"
              />
            </ZCard>
            <ZCard>
              <ZKpi
                value={savingYuan > 0 ? savingYuan.toFixed(0) : (a.estimated_overspend_yuan ?? 0).toFixed(0)}
                label={savingYuan > 0 ? '预计节省' : '预计超支'}
                unit="元"
                size="lg"
              />
            </ZCard>
          </div>

          {/* 岗位分解 */}
          {a.position_breakdown && Object.keys(a.position_breakdown).length > 0 && (
            <ZCard title="岗位分解">
              <div className={styles.posGrid}>
                {Object.entries(a.position_breakdown).map(([pos, cnt]) => (
                  <div key={pos} className={styles.posItem}>
                    <span className={styles.posName}>{pos}</span>
                    <span className={styles.posCnt}>{cnt} 人</span>
                  </div>
                ))}
              </div>
            </ZCard>
          )}

          {/* 推理链 */}
          {reasons.length > 0 && (
            <ZCard
              title="AI 推理依据"
              extra={confidencePct != null
                ? <ZBadge type={confidencePct >= 75 ? 'success' : confidencePct >= 55 ? 'info' : 'warning'} text={`置信度 ${confidencePct}%`} />
                : null
              }
            >
              <div className={styles.reasons}>
                {reasons.map((r, i) => (
                  <div key={i} className={styles.reasonItem}>
                    <span className={styles.reasonNum}>{i + 1}</span>
                    <span className={styles.reasonText}>{r}</span>
                  </div>
                ))}
              </div>
            </ZCard>
          )}

          {/* 处理状态 / 操作区 */}
          <ZCard title="处理">
            {isHandled ? (
              <div className={styles.handledRow}>
                <ZBadge
                  type={ACTION_LABELS[a.confirmed_action!]?.type ?? 'default'}
                  text={ACTION_LABELS[a.confirmed_action!]?.text ?? a.confirmed_action!}
                />
                {a.confirmed_at && (
                  <span className={styles.handledTime}>
                    {dayjs(a.confirmed_at).format('MM-DD HH:mm')}
                  </span>
                )}
              </div>
            ) : (
              <ZButton onClick={() => { form.resetFields(); setModal(true); }}>
                处理建议
              </ZButton>
            )}
          </ZCard>
        </div>
      )}

      <ZModal
        open={modal}
        title="处理人力建议"
        onClose={() => setModal(false)}
        footer={
          <>
            <ZButton variant="ghost" onClick={() => setModal(false)}>取消</ZButton>
            <ZButton loading={submitting} onClick={handleSubmit}>确认提交</ZButton>
          </>
        }
      >
        <Form form={form} layout="vertical" initialValues={{ action: 'confirmed' }}>
          <Form.Item label="处理动作" name="action" rules={[{ required: true }]}>
            <Select>
              <Select.Option value="confirmed">直接确认</Select.Option>
              <Select.Option value="modified">修改后确认</Select.Option>
              <Select.Option value="rejected">拒绝</Select.Option>
            </Select>
          </Form.Item>
          <Form.Item noStyle shouldUpdate>
            {({ getFieldValue }) => (
              <>
                {getFieldValue('action') === 'modified' && (
                  <Form.Item label="修改后人数" name="modified_headcount" rules={[{ required: true, message: '请输入人数' }]}>
                    <InputNumber min={1} style={{ width: '100%' }} />
                  </Form.Item>
                )}
                {getFieldValue('action') === 'rejected' && (
                  <Form.Item label="拒绝原因" name="rejection_reason" rules={[{ required: true, message: '请输入原因' }]}>
                    <Input placeholder="请输入拒绝原因" />
                  </Form.Item>
                )}
              </>
            )}
          </Form.Item>
        </Form>
      </ZModal>
    </div>
  );
}
