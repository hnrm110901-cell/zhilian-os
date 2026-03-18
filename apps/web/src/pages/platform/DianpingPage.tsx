/**
 * 大众点评评论监控页 — /platform/dianping
 *
 * 功能：评论列表（卡片）、情感分析、统计概览、关键词云、商家回复
 * 后端 API: /api/v1/dianping/*
 */
import React, { useState, useEffect, useCallback } from 'react';
import {
  Button, Space, Card, Statistic, Row, Col,
  Select, Input, Tag, Modal, Avatar, Checkbox,
  message, Empty, Typography, Spin, Drawer, Pagination,
  Tooltip,
} from 'antd';
import {
  SyncOutlined, StarFilled, StarOutlined,
  SearchOutlined, MessageOutlined, EyeOutlined,
  CommentOutlined, SmileOutlined, FrownOutlined,
  MehOutlined,
} from '@ant-design/icons';
import { apiClient } from '../../services/api';
import styles from './DianpingPage.module.css';

const { Text, Title } = Typography;
const { TextArea } = Input;

// ── 类型 ─────────────────────────────────────────────────────────

interface DianpingReview {
  id: string;
  brand_id: string;
  store_id: string;
  review_id: string;
  author_name: string;
  author_avatar_url: string | null;
  rating: number;
  content: string;
  images: string[] | null;
  review_date: string | null;
  sentiment: string | null;
  sentiment_score: number | null;
  keywords: string[] | null;
  reply_content: string | null;
  reply_date: string | null;
  is_read: boolean;
  source: string;
  created_at: string | null;
}

interface ReviewListResponse {
  total: number;
  page: number;
  page_size: number;
  reviews: DianpingReview[];
}

interface DianpingStats {
  total_reviews: number;
  avg_rating: number;
  sentiment_distribution: Record<string, number>;
  unread_count: number;
  recent_trend: { date: string; count: number; avg_rating: number }[];
}

interface KeywordItem {
  keyword: string;
  count: number;
}

// ── 常量 ─────────────────────────────────────────────────────────

const BRAND_ID = localStorage.getItem('brand_id') || '';

const SENTIMENT_OPTIONS = [
  { label: '全部情感', value: '' },
  { label: '好评', value: 'positive' },
  { label: '中评', value: 'neutral' },
  { label: '差评', value: 'negative' },
];

const RATING_OPTIONS = [
  { label: '全部星级', value: 0 },
  { label: '5星', value: 5 },
  { label: '4星', value: 4 },
  { label: '3星', value: 3 },
  { label: '2星', value: 2 },
  { label: '1星', value: 1 },
];

// ── 辅助组件 ─────────────────────────────────────────────────────

function RatingStars({ rating }: { rating: number }) {
  return (
    <span className={styles.ratingStars}>
      {[1, 2, 3, 4, 5].map((i) =>
        i <= rating ? (
          <StarFilled key={i} />
        ) : (
          <StarOutlined key={i} className={styles.starEmpty} />
        ),
      )}
    </span>
  );
}

function SentimentTag({ sentiment }: { sentiment: string | null }) {
  if (!sentiment) return null;
  const map: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
    positive: { color: 'green', icon: <SmileOutlined />, label: '好评' },
    neutral: { color: 'default', icon: <MehOutlined />, label: '中评' },
    negative: { color: 'red', icon: <FrownOutlined />, label: '差评' },
  };
  const cfg = map[sentiment] || map.neutral;
  return (
    <Tag color={cfg.color} icon={cfg.icon} className={styles.sentimentTag}>
      {cfg.label}
    </Tag>
  );
}

// ── 主组件 ───────────────────────────────────────────────────────

const DianpingPage: React.FC = () => {
  // 列表状态
  const [reviews, setReviews] = useState<DianpingReview[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [loading, setLoading] = useState(false);

  // 筛选
  const [filterStore, setFilterStore] = useState('');
  const [filterSentiment, setFilterSentiment] = useState('');
  const [filterRating, setFilterRating] = useState(0);
  const [filterIsRead, setFilterIsRead] = useState<boolean | undefined>(undefined);
  const [searchKeyword, setSearchKeyword] = useState('');

  // 门店选项
  const [storeOptions, setStoreOptions] = useState<{ label: string; value: string }[]>([{ label: '全部门店', value: '' }]);
  useEffect(() => {
    apiClient.get('/api/v1/stores').then((res: any) => {
      const list: any[] = res.stores || res || [];
      setStoreOptions([
        { label: '全部门店', value: '' },
        ...list.map((s: any) => ({ label: s.name || s.store_id || s.id, value: s.store_id || s.id })),
      ]);
    }).catch(() => {});
  }, []);

  // 统计
  const [stats, setStats] = useState<DianpingStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);

  // 关键词云
  const [keywords, setKeywords] = useState<KeywordItem[]>([]);

  // 回复
  const [replyDrawerOpen, setReplyDrawerOpen] = useState(false);
  const [replyTarget, setReplyTarget] = useState<DianpingReview | null>(null);
  const [replyContent, setReplyContent] = useState('');
  const [replying, setReplying] = useState(false);

  // 同步
  const [syncing, setSyncing] = useState(false);

  // ── 数据加载 ─────────────────────────────────────────────────────

  const fetchReviews = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, any> = {
        brand_id: BRAND_ID,
        page,
        page_size: pageSize,
      };
      if (filterStore) params.store_id = filterStore;
      if (filterSentiment) params.sentiment = filterSentiment;
      if (filterRating > 0) params.rating = filterRating;
      if (filterIsRead !== undefined) params.is_read = filterIsRead;
      if (searchKeyword) params.keyword = searchKeyword;

      const data = await apiClient.get<ReviewListResponse>('/api/v1/dianping/reviews', { params });
      setReviews(data.reviews);
      setTotal(data.total);
    } catch {
      message.error('加载评论失败');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, filterStore, filterSentiment, filterRating, filterIsRead, searchKeyword]);

  const fetchStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const data = await apiClient.get<DianpingStats>('/api/v1/dianping/stats', {
        params: { brand_id: BRAND_ID },
      });
      setStats(data);
    } catch {
      /* 静默降级 */
    } finally {
      setStatsLoading(false);
    }
  }, []);

  const fetchKeywords = useCallback(async () => {
    try {
      const data = await apiClient.get<{ keywords: KeywordItem[] }>('/api/v1/dianping/keywords', {
        params: { brand_id: BRAND_ID },
      });
      setKeywords(data.keywords);
    } catch {
      /* 静默降级 */
    }
  }, []);

  useEffect(() => {
    fetchReviews();
  }, [fetchReviews]);

  useEffect(() => {
    fetchStats();
    fetchKeywords();
  }, [fetchStats, fetchKeywords]);

  // ── 操作 ─────────────────────────────────────────────────────────

  const handleSync = async () => {
    setSyncing(true);
    try {
      const storeId = filterStore || '';
      await apiClient.post('/api/v1/dianping/sync', {
        brand_id: BRAND_ID,
        store_id: storeId,
      });
      message.success('评论同步完成');
      fetchReviews();
      fetchStats();
      fetchKeywords();
    } catch {
      message.error('同步失败');
    } finally {
      setSyncing(false);
    }
  };

  const handleReply = async () => {
    if (!replyTarget || !replyContent.trim()) return;
    setReplying(true);
    try {
      await apiClient.post(`/api/v1/dianping/reviews/${replyTarget.review_id}/reply`, {
        reply_content: replyContent.trim(),
      });
      message.success('回复成功');
      setReplyDrawerOpen(false);
      setReplyContent('');
      setReplyTarget(null);
      fetchReviews();
    } catch {
      message.error('回复失败');
    } finally {
      setReplying(false);
    }
  };

  const handleMarkRead = async (reviewIds: string[]) => {
    try {
      await apiClient.post('/api/v1/dianping/reviews/mark-read', {
        review_ids: reviewIds,
      });
      message.success('已标记为已读');
      fetchReviews();
      fetchStats();
    } catch {
      message.error('操作失败');
    }
  };

  const openReplyDrawer = (review: DianpingReview) => {
    setReplyTarget(review);
    setReplyContent(review.reply_content || '');
    setReplyDrawerOpen(true);
  };

  // ── 渲染统计行 ───────────────────────────────────────────────────

  const renderStats = () => {
    if (!stats) return null;
    const posCount = stats.sentiment_distribution.positive || 0;
    const negCount = stats.sentiment_distribution.negative || 0;
    const posRate = stats.total_reviews > 0
      ? Math.round((posCount / stats.total_reviews) * 100)
      : 0;

    return (
      <Row gutter={[16, 16]} className={styles.statsRow}>
        <Col xs={12} sm={6}>
          <Card size="small" className={styles.statsCard}>
            <Statistic
              title="平均评分"
              value={stats.avg_rating}
              precision={1}
              suffix="/ 5"
              prefix={<StarFilled style={{ color: '#fadb14' }} />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" className={styles.statsCard}>
            <Statistic title="总评论数" value={stats.total_reviews} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" className={styles.statsCard}>
            <Statistic
              title="好评率"
              value={posRate}
              suffix="%"
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" className={styles.statsCard}>
            <Statistic
              title="未读 / 差评"
              value={stats.unread_count}
              suffix={`/ ${negCount}`}
              valueStyle={negCount > 0 ? { color: '#ff4d4f' } : undefined}
            />
          </Card>
        </Col>
      </Row>
    );
  };

  // ── 渲染筛选栏 ───────────────────────────────────────────────────

  const renderToolbar = () => (
    <div className={styles.toolbar}>
      <div className={styles.filters}>
        <Select
          value={filterStore}
          onChange={(v) => { setFilterStore(v); setPage(1); }}
          options={storeOptions}
          style={{ width: 140 }}
          size="small"
        />
        <Select
          value={filterSentiment}
          onChange={(v) => { setFilterSentiment(v); setPage(1); }}
          options={SENTIMENT_OPTIONS}
          style={{ width: 120 }}
          size="small"
        />
        <Select
          value={filterRating}
          onChange={(v) => { setFilterRating(v); setPage(1); }}
          options={RATING_OPTIONS}
          style={{ width: 110 }}
          size="small"
        />
        <Checkbox
          checked={filterIsRead === false}
          onChange={(e) => {
            setFilterIsRead(e.target.checked ? false : undefined);
            setPage(1);
          }}
        >
          仅未读
        </Checkbox>
        <Input
          prefix={<SearchOutlined />}
          placeholder="搜索评论内容"
          value={searchKeyword}
          onChange={(e) => setSearchKeyword(e.target.value)}
          onPressEnter={() => { setPage(1); fetchReviews(); }}
          style={{ width: 180 }}
          size="small"
          allowClear
        />
      </div>
      <Button
        type="primary"
        icon={<SyncOutlined spin={syncing} />}
        onClick={handleSync}
        loading={syncing}
        size="small"
      >
        同步评论
      </Button>
    </div>
  );

  // ── 渲染评论卡片 ─────────────────────────────────────────────────

  const renderReviewCard = (review: DianpingReview) => {
    const cardClass = `${styles.reviewCard} ${!review.is_read ? styles.reviewCardUnread : ''}`;
    const dateStr = review.review_date
      ? new Date(review.review_date).toLocaleDateString('zh-CN', {
          year: 'numeric', month: '2-digit', day: '2-digit',
        })
      : '';

    return (
      <Card key={review.id} size="small" className={cardClass}>
        {/* 头部：头像 + 名称 + 评分 | 情感标签 + 来源 + 日期 */}
        <div className={styles.reviewHeader}>
          <div className={styles.authorInfo}>
            <Avatar
              src={review.author_avatar_url}
              size={36}
            >
              {review.author_name?.[0]}
            </Avatar>
            <div>
              <div className={styles.authorName}>{review.author_name}</div>
              <RatingStars rating={review.rating} />
            </div>
          </div>
          <div className={styles.reviewMeta}>
            <SentimentTag sentiment={review.sentiment} />
            <Tag>{review.source === 'meituan' ? '美团' : '大众点评'}</Tag>
            <span>{dateStr}</span>
          </div>
        </div>

        {/* 评论内容 */}
        <div className={styles.reviewContent}>{review.content}</div>

        {/* 图片 */}
        {review.images && review.images.length > 0 && (
          <div className={styles.reviewImages}>
            {review.images.map((url, idx) => (
              <img
                key={idx}
                src={url}
                alt={`评论图片${idx + 1}`}
                className={styles.reviewImage}
                onClick={() => window.open(url, '_blank')}
              />
            ))}
          </div>
        )}

        {/* 关键词标签 */}
        {review.keywords && review.keywords.length > 0 && (
          <div className={styles.keywordsRow}>
            {review.keywords.map((kw) => (
              <Tag key={kw} color="blue" style={{ fontSize: 11 }}>
                {kw}
              </Tag>
            ))}
          </div>
        )}

        {/* 商家回复 */}
        {review.reply_content && (
          <div className={styles.replySection}>
            <div className={styles.replyLabel}>
              商家回复
              {review.reply_date && (
                <span style={{ marginLeft: 8 }}>
                  {new Date(review.reply_date).toLocaleDateString('zh-CN')}
                </span>
              )}
            </div>
            <div className={styles.replyText}>{review.reply_content}</div>
          </div>
        )}

        {/* 底部操作 */}
        <div className={styles.reviewFooter}>
          <Space size="small">
            {review.sentiment_score !== null && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                情感分: {review.sentiment_score.toFixed(2)}
              </Text>
            )}
          </Space>
          <Space size="small">
            {!review.is_read && (
              <Button
                size="small"
                type="text"
                icon={<EyeOutlined />}
                onClick={() => handleMarkRead([review.review_id])}
              >
                已读
              </Button>
            )}
            <Button
              size="small"
              type="text"
              icon={<MessageOutlined />}
              onClick={() => openReplyDrawer(review)}
            >
              {review.reply_content ? '编辑回复' : '回复'}
            </Button>
          </Space>
        </div>
      </Card>
    );
  };

  // ── 渲染关键词云 ─────────────────────────────────────────────────

  const renderKeywordCloud = () => {
    if (keywords.length === 0) return null;
    const maxCount = Math.max(...keywords.map((k) => k.count));
    return (
      <Card
        size="small"
        title={<><CommentOutlined /> 热门关键词</>}
        style={{ marginBottom: 16 }}
      >
        <div className={styles.keywordCloud}>
          {keywords.map((item) => {
            const ratio = maxCount > 0 ? item.count / maxCount : 0.5;
            const fontSize = 12 + Math.round(ratio * 12);
            return (
              <Tooltip key={item.keyword} title={`出现 ${item.count} 次`}>
                <span
                  className={styles.keywordItem}
                  style={{ fontSize }}
                >
                  {item.keyword}
                </span>
              </Tooltip>
            );
          })}
        </div>
      </Card>
    );
  };

  // ── 主渲染 ───────────────────────────────────────────────────────

  return (
    <div className={styles.page}>
      {/* 页头 */}
      <div className={styles.pageHeader}>
        <div>
          <Title level={4} style={{ margin: 0 }}>
            大众点评评论监控
          </Title>
          <Text type="secondary">
            实时监控大众点评和美团平台评论，AI情感分析，及时回复管理
          </Text>
        </div>
      </div>

      {/* 统计卡片 */}
      {statsLoading ? (
        <div className={styles.spinCenter}><Spin /></div>
      ) : (
        renderStats()
      )}

      {/* 关键词云 */}
      {renderKeywordCloud()}

      {/* 筛选栏 */}
      {renderToolbar()}

      {/* 评论列表 */}
      {loading ? (
        <div className={styles.spinCenter}><Spin size="large" /></div>
      ) : reviews.length === 0 ? (
        <Empty description="暂无评论数据，点击「同步评论」获取最新评论" />
      ) : (
        <>
          {reviews.map(renderReviewCard)}
          <div style={{ textAlign: 'right', marginTop: 16 }}>
            <Pagination
              current={page}
              pageSize={pageSize}
              total={total}
              onChange={(p) => setPage(p)}
              showTotal={(t) => `共 ${t} 条评论`}
              showSizeChanger={false}
            />
          </div>
        </>
      )}

      {/* 回复抽屉 */}
      <Drawer
        title={replyTarget ? `回复 ${replyTarget.author_name} 的评论` : '回复评论'}
        open={replyDrawerOpen}
        onClose={() => { setReplyDrawerOpen(false); setReplyTarget(null); }}
        width={480}
        footer={
          <div style={{ textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setReplyDrawerOpen(false)}>取消</Button>
              <Button
                type="primary"
                onClick={handleReply}
                loading={replying}
                disabled={!replyContent.trim()}
              >
                提交回复
              </Button>
            </Space>
          </div>
        }
      >
        {replyTarget && (
          <>
            <Card size="small" style={{ marginBottom: 16 }}>
              <div className={styles.authorInfo}>
                <Avatar src={replyTarget.author_avatar_url} size={32}>
                  {replyTarget.author_name?.[0]}
                </Avatar>
                <div>
                  <Text strong>{replyTarget.author_name}</Text>
                  <div><RatingStars rating={replyTarget.rating} /></div>
                </div>
              </div>
              <div style={{ marginTop: 8 }}>{replyTarget.content}</div>
            </Card>
            <TextArea
              rows={6}
              value={replyContent}
              onChange={(e) => setReplyContent(e.target.value)}
              placeholder="输入回复内容..."
              maxLength={500}
              showCount
            />
          </>
        )}
      </Drawer>
    </div>
  );
};

export default DianpingPage;
