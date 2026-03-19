import React, { useRef, useState } from 'react';
import { ZCard, ZButton, ZEmpty, ZBadge } from '../../design-system/components';
import styles from './HRImport.module.css';

interface ImportResult {
  imported: number;
  skipped: number;
  errors: string[];
  total: number;
}

export default function HRImport() {
  const [file, setFile] = useState<File | null>(null);
  const [orgNodeId, setOrgNodeId] = useState(
    () => localStorage.getItem('org_node_id') || 'xj-s01',
  );
  const [result, setResult] = useState<ImportResult | null>(null);
  const [loading, setLoading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const dropped = e.dataTransfer.files[0];
    if (dropped) setFile(dropped);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) setFile(selected);
  };

  const handleImport = async () => {
    if (!file) return;
    setLoading(true);
    setResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const resp = await fetch(
        `/api/v1/hr/import/employees?org_node_id=${encodeURIComponent(orgNodeId)}`,
        {
          method: 'POST',
          body: formData,
          headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
        },
      );
      const data = await resp.json();
      setResult(data);
    } catch {
      setResult({ imported: 0, skipped: 0, errors: ['导入请求失败'], total: 0 });
    } finally {
      setLoading(false);
    }
  };

  const downloadTemplate = () => {
    window.open('/api/v1/hr/import/template', '_blank');
  };

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>员工数据导入</h2>
        <ZButton variant="ghost" size="sm" onClick={downloadTemplate}>
          下载模板
        </ZButton>
      </div>

      <ZCard title="组织节点">
        <div className={styles.orgField}>
          <label className={styles.label}>目标组织节点 ID</label>
          <input
            className={styles.input}
            value={orgNodeId}
            onChange={(e) => setOrgNodeId(e.target.value)}
            placeholder="如 xj-s01"
          />
        </div>
      </ZCard>

      <ZCard title="上传文件">
        <div
          className={styles.dropZone}
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
        >
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,.xls,.csv"
            className={styles.fileInput}
            onChange={handleFileChange}
          />
          {file ? (
            <div className={styles.fileInfo}>
              <span className={styles.fileName}>{file.name}</span>
              <span className={styles.fileSize}>
                {(file.size / 1024).toFixed(1)} KB
              </span>
            </div>
          ) : (
            <div className={styles.dropHint}>
              <span className={styles.dropIcon}>+</span>
              <span>拖拽Excel文件到此处，或点击选择文件</span>
              <span className={styles.dropSub}>支持 .xlsx / .xls / .csv</span>
            </div>
          )}
        </div>
        <div className={styles.importAction}>
          <ZButton
            variant="primary"
            size="sm"
            onClick={handleImport}
            disabled={!file || loading}
          >
            {loading ? '导入中...' : '开始导入'}
          </ZButton>
        </div>
      </ZCard>

      {result && (
        <ZCard title="导入结果">
          <div className={styles.resultRow}>
            <ZBadge type="success" text={`成功导入 ${result.imported} 人`} />
            {result.skipped > 0 && (
              <ZBadge type="warning" text={`跳过 ${result.skipped} 条`} />
            )}
            {result.errors.length > 0 && (
              <ZBadge type="critical" text={`${result.errors.length} 条错误`} />
            )}
          </div>
          {result.errors.length > 0 && (
            <ul className={styles.errorList}>
              {result.errors.map((err, i) => (
                <li key={i} className={styles.errorItem}>{err}</li>
              ))}
            </ul>
          )}
        </ZCard>
      )}

      {!result && (
        <ZCard>
          <ZEmpty title="等待导入" description="选择文件后点击「开始导入」" />
        </ZCard>
      )}
    </div>
  );
}
