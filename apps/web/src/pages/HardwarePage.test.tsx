import { describe, expect, it } from 'vitest';

import {
  formatIsoDateTime,
  getChecklistStatusMeta,
  getNetworkModeMeta,
  getNodeStatusMeta,
  getShokzStatusMeta,
  summarizeDeploymentCost,
} from './HardwarePage';

describe('HardwarePage helpers', () => {
  it('maps edge node statuses and network modes to readable labels', () => {
    expect(getNetworkModeMeta('cloud')).toEqual({ color: 'blue', label: '云端模式' });
    expect(getNetworkModeMeta('edge')).toEqual({ color: 'gold', label: '边缘模式' });
    expect(getNodeStatusMeta('online')).toEqual({ color: 'green', label: '在线' });
    expect(getNodeStatusMeta('syncing')).toEqual({ color: 'processing', label: '同步中' });
  });

  it('maps shokz device statuses to readable labels', () => {
    expect(getShokzStatusMeta('connected')).toEqual({ color: 'green', label: '已连接' });
    expect(getShokzStatusMeta('low_battery')).toEqual({ color: 'orange', label: '低电量' });
    expect(getShokzStatusMeta('disconnected')).toEqual({ color: 'default', label: '未连接' });
  });

  it('maps commissioning checklist status', () => {
    expect(getChecklistStatusMeta(true)).toEqual({ color: 'green', label: '通过' });
    expect(getChecklistStatusMeta(false)).toEqual({ color: 'orange', label: '待处理' });
  });

  it('summarizes deployment cost from backend summary payload', () => {
    const result = summarizeDeploymentCost({
      summary: {
        total_hardware_cost: 3300,
        total_implementation_cost: 1000,
        total_cost_per_store: 4300,
        deployment_time_hours: 3.5,
        roi_months: 2,
      },
    });

    expect(result).toEqual({
      hardwareCost: 3300,
      implementationCost: 1000,
      totalCost: 4300,
      deploymentTimeHours: 3.5,
      roiMonths: 2,
      recommendedNodes: 1,
      recommendedShokz: 2,
    });
  });

  it('formats ISO time and tolerates empty values', () => {
    expect(formatIsoDateTime('2026-03-15T08:30:00')).not.toBe('-');
    expect(formatIsoDateTime(null)).toBe('-');
    expect(formatIsoDateTime(undefined)).toBe('-');
  });
});
