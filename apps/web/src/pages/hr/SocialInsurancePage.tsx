/**
 * 社保公积金配置页面
 * 路由: /social-insurance
 * 功能: 区域费率配置 + 员工参保方案
 */
import React, { useCallback, useEffect, useState } from 'react';
import { hrService } from '../../services/hrService';
import type { SocialInsuranceConfigItem, EmployeeInsuranceItem } from '../../services/hrService';
import styles from './SocialInsurancePage.module.css';

const STORE_ID = localStorage.getItem('store_id') || '';
const CURRENT_YEAR = new Date().getFullYear();

const SocialInsurancePage: React.FC = () => {
  const [configs, setConfigs] = useState<SocialInsuranceConfigItem[]>([]);
  const [employees, setEmployees] = useState<EmployeeInsuranceItem[]>([]);
  const [tab, setTab] = useState<'configs' | 'employees'>('configs');
  const [loading, setLoading] = useState(true);

  const loadConfigs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await hrService.getSocialInsuranceConfigs(CURRENT_YEAR);
      setConfigs(data.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  const loadEmployees = useCallback(async () => {
    setLoading(true);
    try {
      const data = await hrService.getEmployeeInsurances(STORE_ID, CURRENT_YEAR);
      setEmployees(data.items || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => {
    if (tab === 'configs') loadConfigs();
    else loadEmployees();
  }, [tab, loadConfigs, loadEmployees]);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>社保公积金</h1>
        <div className={styles.tabs}>
          <button
            className={`${styles.tab} ${tab === 'configs' ? styles.tabActive : ''}`}
            onClick={() => setTab('configs')}
          >区域费率</button>
          <button
            className={`${styles.tab} ${tab === 'employees' ? styles.tabActive : ''}`}
            onClick={() => setTab('employees')}
          >员工参保</button>
        </div>
      </div>

      {loading ? (
        <div className={styles.empty}>加载中...</div>
      ) : tab === 'configs' ? (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>地区</th>
                <th>年度</th>
                <th>基数下限(元)</th>
                <th>基数上限(元)</th>
                <th>企业合计(%)</th>
                <th>个人合计(%)</th>
                <th>养老(企/个)</th>
                <th>医疗(企/个)</th>
                <th>公积金(企/个)</th>
              </tr>
            </thead>
            <tbody>
              {configs.length === 0 ? (
                <tr><td colSpan={9} className={styles.empty}>暂无配置</td></tr>
              ) : configs.map(c => (
                <tr key={c.id}>
                  <td>{c.region_name}</td>
                  <td>{c.effective_year}</td>
                  <td>{c.base_floor_yuan.toFixed(0)}</td>
                  <td>{c.base_ceiling_yuan.toFixed(0)}</td>
                  <td className={styles.highlight}>{c.total_employer_pct.toFixed(1)}%</td>
                  <td className={styles.highlight}>{c.total_employee_pct.toFixed(1)}%</td>
                  <td>{c.pension_employer_pct}/{c.pension_employee_pct}%</td>
                  <td>{c.medical_employer_pct}/{c.medical_employee_pct}%</td>
                  <td>{c.housing_fund_employer_pct}/{c.housing_fund_employee_pct}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>员工</th>
                <th>岗位</th>
                <th>参保地区</th>
                <th>缴费基数(元)</th>
                <th>养老</th>
                <th>医疗</th>
                <th>失业</th>
                <th>公积金</th>
              </tr>
            </thead>
            <tbody>
              {employees.length === 0 ? (
                <tr><td colSpan={8} className={styles.empty}>暂无员工参保记录</td></tr>
              ) : employees.map(e => (
                <tr key={e.id}>
                  <td>{e.employee_name}</td>
                  <td>{e.position}</td>
                  <td>{e.region_name}</td>
                  <td>{e.personal_base_yuan.toFixed(0)}</td>
                  <td>{e.has_pension ? '参' : '-'}</td>
                  <td>{e.has_medical ? '参' : '-'}</td>
                  <td>{e.has_unemployment ? '参' : '-'}</td>
                  <td>
                    {e.has_housing_fund ? (
                      e.housing_fund_pct_override
                        ? `参(${e.housing_fund_pct_override}%)`
                        : '参'
                    ) : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default SocialInsurancePage;
