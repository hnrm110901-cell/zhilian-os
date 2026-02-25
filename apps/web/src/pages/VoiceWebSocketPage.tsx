import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Card, Row, Col, Select, Button, Input, Space, Tag, Alert, Spin, Form, Typography, Divider } from 'antd';
import { AudioOutlined, AudioMutedOutlined, SendOutlined, ReloadOutlined } from '@ant-design/icons';
import { apiClient } from '../services/api';
import { handleApiError, showSuccess } from '../utils/message';

const { Option } = Select;
const { TextArea } = Input;
const { Text } = Typography;

interface TranscriptEntry {
  type: 'stt' | 'tts' | 'dialog' | 'system';
  content: string;
  timestamp: string;
}

const VoiceWebSocketPage: React.FC = () => {
  const [storeId, setStoreId] = useState('STORE001');
  const [stores, setStores] = useState<Array<{ store_id: string; name: string }>>([]);
  const [mode, setMode] = useState<'stt' | 'tts' | 'dialog'>('dialog');
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [ttsText, setTtsText] = useState('');
  const [dialogText, setDialogText] = useState('');
  const [sending, setSending] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.get('/stores');
      setStores(res.data?.stores || res.data || []);
    } catch (err) {
      handleApiError(err, '加载门店列表失败');
    }
  }, []);

  useEffect(() => { loadStores(); }, [loadStores]);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript]);

  const addEntry = (type: TranscriptEntry['type'], content: string) => {
    setTranscript(prev => [...prev, { type, content, timestamp: new Date().toLocaleTimeString() }]);
  };

  const connect = () => {
    if (wsRef.current) return;
    setConnecting(true);
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const host = window.location.host;
    const url = `${protocol}://${host}/api/v1/voice-ws/${mode}/${storeId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setConnecting(false);
      addEntry('system', `已连接到 ${mode.toUpperCase()} WebSocket (${storeId})`);
    };
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        const content = data.text || data.transcript || data.response || JSON.stringify(data);
        addEntry(mode, content);
      } catch {
        addEntry(mode, e.data);
      }
    };
    ws.onerror = () => {
      addEntry('system', '连接错误');
      setConnected(false);
      setConnecting(false);
      wsRef.current = null;
    };
    ws.onclose = () => {
      addEntry('system', '连接已断开');
      setConnected(false);
      setConnecting(false);
      wsRef.current = null;
    };
  };

  const disconnect = () => {
    wsRef.current?.close();
    wsRef.current = null;
    setConnected(false);
  };

  const sendTts = async () => {
    if (!ttsText.trim()) return;
    setSending(true);
    try {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ text: ttsText }));
        addEntry('tts', `[发送] ${ttsText}`);
        setTtsText('');
      } else {
        // fallback: REST
        await apiClient.post(`/voice-ws/tts/${storeId}`, { text: ttsText });
        showSuccess('TTS 请求已发送');
        setTtsText('');
      }
    } catch (err) {
      handleApiError(err, 'TTS 发送失败');
    } finally {
      setSending(false);
    }
  };

  const sendDialog = async () => {
    if (!dialogText.trim()) return;
    setSending(true);
    try {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ message: dialogText }));
        addEntry('dialog', `[用户] ${dialogText}`);
        setDialogText('');
      } else {
        handleApiError(new Error('未连接'), '请先连接 WebSocket');
      }
    } catch (err) {
      handleApiError(err, '发送失败');
    } finally {
      setSending(false);
    }
  };

  const entryColor: Record<string, string> = { stt: '#1677ff', tts: '#52c41a', dialog: '#722ed1', system: '#8c8c8c' };
  const entryLabel: Record<string, string> = { stt: 'STT', tts: 'TTS', dialog: '对话', system: '系统' };

  return (
    <div style={{ padding: 24 }}>
      <Row gutter={[16, 16]}>
        <Col xs={24} md={8}>
          <Card title="连接配置">
            <Form layout="vertical">
              <Form.Item label="门店">
                <Select value={storeId} onChange={setStoreId} disabled={connected} style={{ width: '100%' }}>
                  {stores.map(s => <Option key={s.store_id} value={s.store_id}>{s.name || s.store_id}</Option>)}
                  {!stores.length && <Option value="STORE001">STORE001</Option>}
                </Select>
              </Form.Item>
              <Form.Item label="模式">
                <Select value={mode} onChange={(v) => setMode(v)} disabled={connected} style={{ width: '100%' }}>
                  <Option value="stt">STT（语音转文字）</Option>
                  <Option value="tts">TTS（文字转语音）</Option>
                  <Option value="dialog">Dialog（对话）</Option>
                </Select>
              </Form.Item>
              <Form.Item>
                {!connected ? (
                  <Button type="primary" icon={<AudioOutlined />} onClick={connect} loading={connecting} block>
                    连接
                  </Button>
                ) : (
                  <Button danger icon={<AudioMutedOutlined />} onClick={disconnect} block>
                    断开
                  </Button>
                )}
              </Form.Item>
            </Form>

            <Divider />

            {(mode === 'tts' || mode === 'dialog') && (
              <>
                {mode === 'tts' && (
                  <Form.Item label="TTS 文本">
                    <Space.Compact style={{ width: '100%' }}>
                      <Input value={ttsText} onChange={e => setTtsText(e.target.value)} placeholder="输入要合成的文字" />
                      <Button type="primary" icon={<SendOutlined />} onClick={sendTts} loading={sending} />
                    </Space.Compact>
                  </Form.Item>
                )}
                {mode === 'dialog' && (
                  <Form.Item label="对话输入">
                    <TextArea
                      value={dialogText}
                      onChange={e => setDialogText(e.target.value)}
                      rows={3}
                      placeholder="输入对话内容"
                      onPressEnter={e => { if (!e.shiftKey) { e.preventDefault(); sendDialog(); } }}
                    />
                    <Button type="primary" icon={<SendOutlined />} onClick={sendDialog} loading={sending} style={{ marginTop: 8 }} block>
                      发送
                    </Button>
                  </Form.Item>
                )}
              </>
            )}

            {mode === 'stt' && connected && (
              <Alert type="info" message="STT 模式：通过 WebSocket 发送音频数据，此处仅展示转录结果" showIcon />
            )}
          </Card>
        </Col>

        <Col xs={24} md={16}>
          <Card
            title={
              <Space>
                <span>消息记录</span>
                <Tag color={connected ? 'green' : 'default'}>{connected ? '已连接' : '未连接'}</Tag>
              </Space>
            }
            extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => setTranscript([])}>清空</Button>}
          >
            <div style={{ height: 480, overflowY: 'auto', padding: '8px 0' }}>
              {transcript.length === 0 && (
                <div style={{ textAlign: 'center', color: '#999', paddingTop: 80 }}>
                  <AudioOutlined style={{ fontSize: 48, marginBottom: 16 }} />
                  <div>连接后消息将显示在此处</div>
                </div>
              )}
              {transcript.map((entry, i) => (
                <div key={i} style={{ marginBottom: 8, padding: '6px 12px', borderLeft: `3px solid ${entryColor[entry.type]}`, background: '#fafafa' }}>
                  <Space>
                    <Tag color={entryColor[entry.type]} style={{ minWidth: 40, textAlign: 'center' }}>{entryLabel[entry.type]}</Tag>
                    <Text type="secondary" style={{ fontSize: 12 }}>{entry.timestamp}</Text>
                  </Space>
                  <div style={{ marginTop: 4, wordBreak: 'break-all' }}>{entry.content}</div>
                </div>
              ))}
              <div ref={transcriptEndRef} />
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
};

export default VoiceWebSocketPage;
