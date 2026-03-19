import React, { useState, useCallback } from 'react';
import { message } from 'antd';
import MemberSearchBar from '../../components/MemberSearchBar';
import MemberProfileCard, { type MemberProfile as MemberProfileType } from '../../components/MemberProfileCard';
import CouponSelector from '../../components/CouponSelector';
import { apiClient } from '../../services/api';
import { useAuthStore } from '../../stores/authStore';
import styles from './MemberProfile.module.css';

export default function MemberProfile() {
  const [profile, setProfile] = useState<MemberProfileType | null>(null);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [couponTarget, setCouponTarget] = useState<string | null>(null);

  const user = useAuthStore((s) => s.user);
  const storeId = user?.store_id || '';

  const handleSearch = useCallback(async (phone: string) => {
    setLoading(true);
    setSearched(true);
    try {
      const data = await apiClient.get<MemberProfileType>(
        `/api/v1/bff/member-profile/${storeId}/${phone}`,
      );
      setProfile(data);
    } catch (err) {
      message.error('查询失败，请稍后重试');
      setProfile(null);
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  const handleIssueCoupon = useCallback((consumerId: string) => {
    setCouponTarget(consumerId);
  }, []);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>会员识客</div>
      </div>
      <MemberSearchBar onSearch={handleSearch} loading={loading} />
      <div className={styles.content}>
        {searched && (
          <MemberProfileCard
            profile={profile}
            loading={loading}
            onIssueCoupon={handleIssueCoupon}
          />
        )}
      </div>
      {couponTarget && (
        <CouponSelector
          visible={!!couponTarget}
          onClose={() => setCouponTarget(null)}
          consumerId={couponTarget}
          storeId={storeId}
          phone={profile?.identity?.phone}
        />
      )}
    </div>
  );
}
