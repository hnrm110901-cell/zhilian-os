/**
 * 店长人力建议页（移动端）
 * 路由：/sm/workforce
 * 数据：GET /api/v1/workforce/stores/{store_id}/staffing-advice
 *      POST /api/v1/workforce/stores/{store_id}/staffing-advice/confirm
 */
import React, { useCallback, useEffect, useState } from 'react';
import dayjs from 'dayjs';
import {
  ZCard, ZKpi, ZBadge, ZButton, ZSkeleton, ZEmpty, ZModal, ZSelect,
} from '../../design-system/components';
import type { SelectOption } from '../../design-system/components/ZSelect';
import apiClient from '../../services/api';
import { handleApiError, showSuccess, showError } from '../../utils/message';
import styles from './Workforce.module.css';

const STORE_ID = localStorage.getItem('store_id') || '';
const TOMORROW  = dayjs().add(1, 'day').format('YYYY-MM-DD');

type ActionType = 'confirmed' | 'modified' | 'rejected';

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
  confirmed: { text: '已确认',   type: 'success' },
  modified:  { text: '修改确认', type: 'info'    },
  rejected:  { text: '已拒绝',   type: 'warning' },
};

const ACTION_OPTIONS: SelectOption[] = [
  { value: 'confirmed', label: '直接确认' },
  { value: 'modified',  label: '修改后确认' },
  { value: 'rejected',  label: '拒绝'     },
];

export default function SmWorkforce() {
  const [advice,      setAdvice]      = useState<Advice | null>(null);
  const [loading,     setLoading]     = useState(true);
  const [modal,       setModal]       = useState(false);
  const [submitting,  setSubmitting]  = useState(false);

  // 表单状态（替代 Ant Design Form）
  const [formAction,   setFormAction]   = useState<ActionType>('confirmed');
  const [formHeadcount, setFormHeadcount] = useState<string>('');
  const [formReason,    setFormReason]    = useState('');
  const [formError,     setFormError]     = useState('');

  const openModal = () => {
    setFormAction('confirmed');
    setFormHeadcount('');
    setFormReason('');
    setFormError('');
    setModal(true);
  };

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
    // 手动校验
    if (formAction === 'modified') {
      const n = parseInt(formHeadcount, 10);
      if (!formHeadcount || isNaN(n) || n < 1) {
        setFormError('请输入有效的人数（≥ 1）');
        return;
      }
    }
    if (formAction === 'rejected' && !formReason.trim()) {
      setFormError('请输入拒绝原因');
      return;
    }
    setFormError('');
    setSubmitting(true);
    try {
      await apiClient.post(
        `/api/v1/workforce/stores/${STORE_ID}/staffing-advice/confirm`,
        {
          advice_date:        TOMORROW,
          meal_period:        'all_day',
          action:             formAction,
          modified_headcount: formAction === 'modified' ? parseInt(formHeadcount, 10) : undefined,
          rejection_reason:   formAction === 'rejected'  ? formReason.trim()          : undefined,
        }
      );
      showSuccess('处理成功');
      setModal(false);
      load();
    } catch {
      showError('提交失败，请重试');
    } finally {
      setSubmitting(false);
    }
  };

  const a = advice;
  const savingYuan    = a?.estimated_saving_yuan ?? 0;
  const confidencePct = a?.confidence_score != null ? Math.round(a.confidence_score * 100) : null;
  const reasons       = [a?.reason_1, a?.reason_2, a?.reason_3].filter(Boolean);
  const isHandled     = !!a?.confirmed_action;

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
                ? <ZBadge
                    type={confidencePct >= 75 ? 'success' : confidencePct >= 55 ? 'info' : 'warning'}
                    text={`置信度 ${confidencePct}%`}
                  />
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
              <ZButton onClick={openModal}>处理建议</ZButton>
            )}
          </ZCard>
        </div>
      )}

      {/* 处理弹窗 */}
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
        <div className={styles.formBody}>
          {/* 处理动作 */}
          <div className={styles.fieldRow}>
            <label className={styles.fieldLabel}>处理动作 *</label>
            <ZSelect
              options={ACTION_OPTIONS}
              value={formAction}
              onChange={(v) => {
                setFormAction(v as ActionType);
                setFormError('');
              }}
            />
          </div>

          {/* 修改后人数 */}
          {formAction === 'modified' && (
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>修改后人数 *</label>
              <input
                type="number"
                min={1}
                value={formHeadcount}
                onChange={(e) => { setFormHeadcount(e.target.value); setFormError(''); }}
                placeholder="请输入人数"
                className={styles.numInput}
              />
            </div>
          )}

          {/* 拒绝原因 */}
          {formAction === 'rejected' && (
            <div className={styles.fieldRow}>
              <label className={styles.fieldLabel}>拒绝原因 *</label>
              <textarea
                value={formReason}
                onChange={(e) => { setFormReason(e.target.value); setFormError(''); }}
                placeholder="请输入拒绝原因"
                rows={3}
                className={styles.textArea}
              />
            </div>
          )}

          {/* 错误提示 */}
          {formError && <div className={styles.formError}>{formError}</div>}
        </div>
      </ZModal>
    </div>
  );
}
