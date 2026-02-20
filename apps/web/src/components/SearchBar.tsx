import React, { useState } from 'react';
import { Input, Select, Space, Button, DatePicker } from 'antd';
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons';
import type { RangePickerProps } from 'antd/es/date-picker';

const { RangePicker } = DatePicker;

interface SearchBarProps {
  onSearch?: (value: string) => void;
  onFilter?: (filters: Record<string, any>) => void;
  onRefresh?: () => void;
  placeholder?: string;
  filters?: Array<{
    key: string;
    label: string;
    type: 'select' | 'dateRange';
    options?: Array<{ label: string; value: any }>;
  }>;
  showRefresh?: boolean;
}

export const SearchBar: React.FC<SearchBarProps> = ({
  onSearch,
  onFilter,
  onRefresh,
  placeholder = '搜索...',
  filters = [],
  showRefresh = true,
}) => {
  const [searchValue, setSearchValue] = useState('');
  const [filterValues, setFilterValues] = useState<Record<string, any>>({});

  const handleSearch = () => {
    if (onSearch) {
      onSearch(searchValue);
    }
  };

  const handleFilterChange = (key: string, value: any) => {
    const newFilters = { ...filterValues, [key]: value };
    setFilterValues(newFilters);
    if (onFilter) {
      onFilter(newFilters);
    }
  };

  return (
    <div style={{ marginBottom: 16 }}>
      <Space wrap style={{ width: '100%' }}>
        <Input
          placeholder={placeholder}
          value={searchValue}
          onChange={(e) => setSearchValue(e.target.value)}
          onPressEnter={handleSearch}
          prefix={<SearchOutlined />}
          style={{ width: 280 }}
          allowClear
        />
        {filters.map((filter) => {
          if (filter.type === 'select') {
            return (
              <Select
                key={filter.key}
                placeholder={filter.label}
                style={{ width: 160 }}
                onChange={(value) => handleFilterChange(filter.key, value)}
                options={filter.options}
                allowClear
              />
            );
          }
          if (filter.type === 'dateRange') {
            return (
              <RangePicker
                key={filter.key}
                placeholder={['开始日期', '结束日期']}
                onChange={(dates) => handleFilterChange(filter.key, dates)}
                style={{ width: 260 }}
              />
            );
          }
          return null;
        })}
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
          搜索
        </Button>
        {showRefresh && onRefresh && (
          <Button icon={<ReloadOutlined />} onClick={onRefresh}>
            刷新
          </Button>
        )}
      </Space>
    </div>
  );
};
