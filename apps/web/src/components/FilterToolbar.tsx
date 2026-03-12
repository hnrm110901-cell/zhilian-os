/**
 * FilterToolbar — 统一页面头部筛选区
 * 适用于所有列表页：异常中心 / 节能任务 / 采购单 / 会员列表 / 绩效报告等
 *
 * 用法示例：
 * <FilterToolbar
 *   search={{ placeholder: '搜索异常描述…', onSearch }}
 *   filters={[
 *     { key: 'severity', label: '严重等级', options: [{ value: 'high', label: '高危' }] },
 *     { key: 'status',   label: '状态',     options: [...] },
 *   ]}
 *   onFilterChange={(key, value) => setFilters(prev => ({ ...prev, [key]: value }))}
 *   actions={[
 *     { label: '扫描异常', icon: <ScanOutlined />, onClick: openScanModal },
 *     { label: '导出',    icon: <ExportOutlined />, onClick: handleExport, type: 'default' },
 *   ]}
 *   summary="共 12 条"
 *   extra={<Tag color="mint">3 条高危</Tag>}
 * />
 */
import React, { useState, useCallback } from 'react';
import { Input, Select, Button, Space, Tag, Tooltip, Divider } from 'antd';
import {
  SearchOutlined,
  FilterOutlined,
  ReloadOutlined,
  ClearOutlined,
} from '@ant-design/icons';

const { Option } = Select;

// ── 类型定义 ─────────────────────────────────────────────────────────────────

export interface FilterOption {
  value: string | number;
  label: string;
  color?: string;  // antd Tag color, e.g. 'red' / 'orange' / 'blue'
}

export interface FilterDef {
  key: string;
  label: string;
  options: FilterOption[];
  width?: number;
  allowClear?: boolean;
  multiple?: boolean;
}

export interface ToolbarAction {
  key?: string;
  label: string;
  icon?: React.ReactNode;
  onClick: () => void;
  type?: 'primary' | 'default' | 'dashed' | 'link' | 'text';
  danger?: boolean;
  disabled?: boolean;
  tooltip?: string;
  loading?: boolean;
}

export interface FilterToolbarProps {
  /** 搜索框配置 */
  search?: {
    placeholder?: string;
    onSearch: (value: string) => void;
    width?: number;
  };

  /** 筛选器定义列表 */
  filters?: FilterDef[];

  /** 筛选值变更回调 */
  onFilterChange?: (key: string, value: string | string[] | undefined) => void;

  /** 当前筛选值（受控） */
  filterValues?: Record<string, string | string[] | undefined>;

  /** 右侧操作按钮 */
  actions?: ToolbarAction[];

  /** 汇总文字，如 "共 24 条" */
  summary?: React.ReactNode;

  /** 标题区右侧额外内容（如 Badge / Tag） */
  extra?: React.ReactNode;

  /** 是否显示刷新按钮（右侧） */
  onRefresh?: () => void;
  refreshLoading?: boolean;

  /** 是否显示"重置筛选"按钮 */
  showReset?: boolean;
  onReset?: () => void;

  style?: React.CSSProperties;
  className?: string;
}

// ── 主组件 ───────────────────────────────────────────────────────────────────

const FilterToolbar: React.FC<FilterToolbarProps> = ({
  search,
  filters = [],
  onFilterChange,
  filterValues = {},
  actions = [],
  summary,
  extra,
  onRefresh,
  refreshLoading,
  showReset,
  onReset,
  style,
  className,
}) => {
  const [searchValue, setSearchValue] = useState('');

  const handleSearch = useCallback((value: string) => {
    setSearchValue(value);
    search?.onSearch(value);
  }, [search]);

  const handleReset = useCallback(() => {
    setSearchValue('');
    search?.onSearch('');
    onReset?.();
  }, [search, onReset]);

  const hasActiveFilters = Object.values(filterValues).some(v =>
    v !== undefined && v !== '' && !(Array.isArray(v) && v.length === 0)
  ) || searchValue !== '';

  return (
    <div
      className={className}
      style={{
        display: 'flex',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 8,
        padding: '8px 0',
        ...style,
      }}
    >
      {/* 搜索框 */}
      {search && (
        <Input.Search
          value={searchValue}
          onChange={e => setSearchValue(e.target.value)}
          onSearch={handleSearch}
          placeholder={search.placeholder ?? '搜索…'}
          allowClear
          prefix={<SearchOutlined style={{ color: '#bbb' }} />}
          style={{ width: search.width ?? 220 }}
          size="small"
          onClear={() => handleSearch('')}
        />
      )}

      {/* 筛选器 */}
      {filters.length > 0 && (
        <>
          {filters.length > 0 && search && (
            <Divider type="vertical" style={{ margin: '0 2px', height: 20 }} />
          )}
          <FilterOutlined style={{ color: '#999', fontSize: 13 }} />
          {filters.map(f => (
            <Select
              key={f.key}
              value={filterValues[f.key]}
              onChange={value => onFilterChange?.(f.key, value)}
              placeholder={f.label}
              allowClear={f.allowClear !== false}
              mode={f.multiple ? 'multiple' : undefined}
              style={{ width: f.width ?? 120 }}
              size="small"
            >
              {f.options.map(opt => (
                <Option key={String(opt.value)} value={opt.value}>
                  {opt.color ? (
                    <Tag color={opt.color} style={{ fontSize: 11, margin: 0 }}>
                      {opt.label}
                    </Tag>
                  ) : opt.label}
                </Option>
              ))}
            </Select>
          ))}
        </>
      )}

      {/* 重置按钮 */}
      {(showReset || hasActiveFilters) && (
        <Tooltip title="清除所有筛选">
          <Button
            size="small"
            type="text"
            icon={<ClearOutlined />}
            onClick={handleReset}
            style={{ color: '#999' }}
          >
            重置
          </Button>
        </Tooltip>
      )}

      {/* 汇总 + 额外内容 */}
      {(summary || extra) && (
        <Space size={6} style={{ marginLeft: 4 }}>
          {summary && (
            <span style={{ fontSize: 12, color: '#888' }}>{summary}</span>
          )}
          {extra}
        </Space>
      )}

      {/* 弹性空间，将操作按钮推到右侧 */}
      <div style={{ flex: 1 }} />

      {/* 右侧操作按钮 */}
      {actions.length > 0 && (
        <Space size={6}>
          {actions.map((action, i) => {
            const btn = (
              <Button
                key={action.key ?? i}
                type={action.type ?? 'default'}
                size="small"
                icon={action.icon}
                onClick={action.onClick}
                danger={action.danger}
                disabled={action.disabled}
                loading={action.loading}
              >
                {action.label}
              </Button>
            );
            return action.tooltip ? (
              <Tooltip key={action.key ?? i} title={action.tooltip}>
                {btn}
              </Tooltip>
            ) : btn;
          })}
        </Space>
      )}

      {/* 刷新按钮 */}
      {onRefresh && (
        <Tooltip title="刷新">
          <Button
            size="small"
            type="text"
            icon={<ReloadOutlined />}
            onClick={onRefresh}
            loading={refreshLoading}
          />
        </Tooltip>
      )}
    </div>
  );
};

export default FilterToolbar;
