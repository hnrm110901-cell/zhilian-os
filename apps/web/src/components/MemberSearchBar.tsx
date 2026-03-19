import React, { useState, useCallback } from 'react';
import { Input, message } from 'antd';
import styles from './MemberSearchBar.module.css';

interface MemberSearchBarProps {
  onSearch: (phone: string) => void;
  loading?: boolean;
  placeholder?: string;
}

export default function MemberSearchBar({
  onSearch,
  loading = false,
  placeholder = '手机号 / 会员码',
}: MemberSearchBarProps) {
  const [value, setValue] = useState('');

  const handleSearch = useCallback(() => {
    const phone = value.trim();
    if (!phone) {
      message.warning('请输入手机号或会员码');
      return;
    }
    if (!/^\d{11}$/.test(phone) && !/^\d{6,}$/.test(phone)) {
      message.warning('请输入有效的手机号或会员码');
      return;
    }
    onSearch(phone);
  }, [value, onSearch]);

  return (
    <div className={styles.bar}>
      <Input.Search
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onSearch={handleSearch}
        placeholder={placeholder}
        loading={loading}
        enterButton="搜索"
        size="large"
        allowClear
      />
    </div>
  );
}
