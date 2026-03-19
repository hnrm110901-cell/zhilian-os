/**
 * 我的培训 — 员工H5端
 * 路由：/emp/training
 * 功能：进行中课程（进度条）、已完成课程（证书）、可报名课程
 */
import React, { useCallback, useEffect, useState } from 'react';
import { apiClient } from '../../services/api';
import styles from './MyTrainingPage.module.css';

const EMP_ID = localStorage.getItem('employee_id') || 'EMP_001';

interface CourseItem {
  enrollment_id: string;
  course_id: string;
  course_title: string;
  category: string;
  course_type: string;
  status: string;
  progress_pct: number;
  score: number | null;
  certificate_no: string | null;
  enrolled_at: string | null;
  completed_at: string | null;
  credits: number;
  is_mandatory: boolean;
  duration_minutes: number;
}

const CATEGORY_LABELS: Record<string, string> = {
  food_safety: '食品安全', service: '服务技能', management: '管理能力',
  onboarding: '入职培训', compliance: '合规', other: '其他',
};

const STATUS_LABELS: Record<string, string> = {
  enrolled: '已报名', in_progress: '学习中', completed: '已完成',
  expired: '已过期', failed: '未通过',
};

const MyTrainingPage: React.FC = () => {
  const [courses, setCourses] = useState<CourseItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'learning' | 'completed'>('learning');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await apiClient.get<{ code: number; data: CourseItem[] }>(
        `/api/v1/hr/self-service/my-courses?employee_id=${EMP_ID}`
      );
      setCourses(res.data || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const learningCourses = courses.filter(
    (c) => c.status === 'enrolled' || c.status === 'in_progress'
  );
  const completedCourses = courses.filter(
    (c) => c.status === 'completed' || c.status === 'failed'
  );

  const displayCourses = activeTab === 'learning' ? learningCourses : completedCourses;

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>我的培训</h1>

      {/* 统计 */}
      <div className={styles.statsRow}>
        <div className={styles.statBox}>
          <div className={styles.statNum}>{learningCourses.length}</div>
          <div className={styles.statLabel}>学习中</div>
        </div>
        <div className={styles.statBox}>
          <div className={styles.statNum}>{completedCourses.length}</div>
          <div className={styles.statLabel}>已完成</div>
        </div>
        <div className={styles.statBox}>
          <div className={styles.statNum}>
            {courses.reduce((sum, c) => sum + (c.status === 'completed' ? c.credits : 0), 0)}
          </div>
          <div className={styles.statLabel}>获得学分</div>
        </div>
      </div>

      {/* Tab切换 */}
      <div className={styles.tabBar}>
        <button
          className={`${styles.tab} ${activeTab === 'learning' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('learning')}
        >
          学习中 ({learningCourses.length})
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'completed' ? styles.tabActive : ''}`}
          onClick={() => setActiveTab('completed')}
        >
          已完成 ({completedCourses.length})
        </button>
      </div>

      {loading ? (
        <div className={styles.loading}>加载中...</div>
      ) : displayCourses.length === 0 ? (
        <div className={styles.empty}>
          {activeTab === 'learning' ? '暂无进行中的课程' : '暂无已完成的课程'}
        </div>
      ) : (
        <div className={styles.courseList}>
          {displayCourses.map((course) => (
            <div key={course.enrollment_id} className={styles.courseCard}>
              <div className={styles.courseHeader}>
                <div className={styles.courseTitle}>{course.course_title}</div>
                {course.is_mandatory && (
                  <span className={styles.mandatoryBadge}>必修</span>
                )}
              </div>
              <div className={styles.courseMeta}>
                <span>{CATEGORY_LABELS[course.category] || course.category}</span>
                <span>{course.duration_minutes}分钟</span>
                <span>{course.credits}学分</span>
              </div>

              {/* 进行中：显示进度条 */}
              {(course.status === 'enrolled' || course.status === 'in_progress') && (
                <div className={styles.progressWrap}>
                  <div className={styles.progressBar}>
                    <div
                      className={styles.progressFill}
                      style={{ width: `${course.progress_pct}%` }}
                    />
                  </div>
                  <span className={styles.progressText}>{course.progress_pct}%</span>
                </div>
              )}

              {/* 已完成：显示分数和证书 */}
              {course.status === 'completed' && (
                <div className={styles.completedInfo}>
                  {course.score != null && (
                    <span className={styles.scoreTag}>成绩: {course.score}分</span>
                  )}
                  {course.certificate_no && (
                    <span className={styles.certTag}>证书: {course.certificate_no}</span>
                  )}
                  {course.completed_at && (
                    <span className={styles.completedDate}>
                      完成于 {course.completed_at.split('T')[0]}
                    </span>
                  )}
                </div>
              )}

              {course.status === 'failed' && (
                <div className={styles.failedTag}>
                  未通过 {course.score != null ? `(${course.score}分)` : ''}
                </div>
              )}

              <div className={styles.courseStatus}>
                {STATUS_LABELS[course.status] || course.status}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default MyTrainingPage;
