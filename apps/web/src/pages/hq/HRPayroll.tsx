import React, { useState } from 'react';
import { ZCard, ZKpi, ZButton, ZEmpty } from '../../design-system/components';
import styles from './HRPayroll.module.css';

export default function HRPayroll() {
  const [year] = useState(new Date().getFullYear());
  const [month] = useState(new Date().getMonth() + 1);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <span className={styles.title}>薪资管理 · {year}年{month}月</span>
        <ZButton variant="primary" size="sm">创建批次</ZButton>
      </div>

      <div className={styles.kpiRow}>
        <ZCard><ZKpi value={0} label="本月批次" unit="个" /></ZCard>
        <ZCard><ZKpi value="¥0" label="税前总额" /></ZCard>
        <ZCard><ZKpi value="¥0" label="实发总额" /></ZCard>
      </div>

      <ZCard title="薪资批次">
        <ZEmpty title="暂无薪资批次" description="点击「创建批次」开始本月薪资核算" />
      </ZCard>
    </div>
  );
}
