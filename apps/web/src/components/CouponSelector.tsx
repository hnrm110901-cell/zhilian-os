import React, { useState, useEffect, useCallback } from 'react';
import { Modal, List, message, Tag } from 'antd';
import { ZButton } from '../design-system/components';
import { apiClient } from '../services/api';
import styles from './CouponSelector.module.css';

interface Coupon {
  id: string;
  name: string;
  source: 'weishenghuo' | 'service_voucher';
  value_display?: string;
  expires?: string;
}

interface CouponSelectorProps {
  visible: boolean;
  onClose: () => void;
  consumerId: string;
  storeId: string;
  phone?: string;
}

export default function CouponSelector({
  visible, onClose, consumerId, storeId, phone,
}: CouponSelectorProps) {
  const [coupons, setCoupons] = useState<Coupon[]>([]);
  const [loading, setLoading] = useState(false);
  const [distributing, setDistributing] = useState<string | null>(null);

  useEffect(() => {
    if (!visible || !storeId || !consumerId) return;
    let cancelled = false;
    setLoading(true);
    const params = phone ? `?phone=${encodeURIComponent(phone)}` : '';
    apiClient.get<{ coupons: Coupon[] }>(
      `/api/v1/bff/member-profile/${storeId}/available-coupons/${consumerId}${params}`,
    ).then((res) => {
      if (!cancelled) setCoupons(res.coupons || []);
    }).catch(() => {
      if (!cancelled) setCoupons([]);
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [visible, consumerId, storeId, phone]);

  const handleDistribute = useCallback(async (coupon: Coupon) => {
    setDistributing(coupon.id);
    try {
      await apiClient.post(`/api/v1/bff/member-profile/${storeId}/distribute-coupon`, {
        consumer_id: consumerId,
        coupon_source: coupon.source,
        coupon_id: coupon.id,
        coupon_name: coupon.name,
        phone,
      });
      message.success(`已发放: ${coupon.name}`);
      onClose();
    } catch {
      message.error('发券失败');
    } finally {
      setDistributing(null);
    }
  }, [consumerId, storeId, phone, onClose]);

  return (
    <Modal
      title="选择优惠券"
      open={visible}
      onCancel={onClose}
      footer={null}
      width={400}
    >
      <div className={styles.selector}>
        <List
          loading={loading}
          dataSource={coupons}
          locale={{ emptyText: '暂无可用券' }}
          renderItem={(coupon) => (
            <List.Item
              actions={[
                <ZButton
                  key="send"
                  variant="primary"
                  onClick={() => handleDistribute(coupon)}
                  disabled={distributing !== null}
                >
                  发放
                </ZButton>,
              ]}
            >
              <List.Item.Meta
                title={coupon.name}
                description={
                  <>
                    <Tag color={coupon.source === 'weishenghuo' ? 'orange' : 'green'}>
                      {coupon.source === 'weishenghuo' ? '微生活' : '服务券'}
                    </Tag>
                    {coupon.value_display && <span>{coupon.value_display}</span>}
                  </>
                }
              />
            </List.Item>
          )}
        />
      </div>
    </Modal>
  );
}
