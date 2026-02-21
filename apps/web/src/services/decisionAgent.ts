import { apiClient } from './api';

// Decision Agent 数据类型定义
export interface KPIMetric {
  metric_id: string;
  metric_name: string;
  category: string;
  current_value: number;
  target_value: number;
  previous_value: number;
  unit: string;
  achievement_rate: number;
  trend: string;
  status: string;
}

export interface BusinessInsight {
  insight_id: string;
  title: string;
  description: string;
  category: string;
  impact_level: string;
  data_points: Array<{ label: string; value: number }>;
  discovered_at: string;
}

export interface Recommendation {
  recommendation_id: string;
  title: string;
  description: string;
  decision_type: string;
  priority: string;
  rationale: string;
  expected_impact: string;
  action_items: string[];
  estimated_cost: number | null;
  estimated_roi: number | null;
  created_at: string;
}

export interface DecisionReport {
  store_id: string;
  report_date: string;
  period_start: string;
  period_end: string;
  kpi_summary: {
    total_kpis: number;
    status_distribution: Record<string, number>;
    on_track_rate: number;
    key_kpis: KPIMetric[];
  };
  insights_summary: {
    total_insights: number;
    high_impact: number;
    key_insights: BusinessInsight[];
  };
  recommendations_summary: {
    total_recommendations: number;
    priority_distribution: Record<string, number>;
    critical_recommendations: Recommendation[];
  };
  overall_health_score: number;
  action_required: number;
}

// Decision Agent Service
class DecisionAgentService {
  /**
   * 获取决策综合报告
   */
  async getDecisionReport(params?: {
    start_date?: string;
    end_date?: string;
  }): Promise<DecisionReport> {
    const response = await apiClient.callAgent('decision', {
      action: 'get_decision_report',
      params: params || {},
    });

    return response.output_data.data as DecisionReport;
  }

  /**
   * 分析KPI指标
   */
  async analyzeKPIs(params?: {
    start_date?: string;
    end_date?: string;
  }): Promise<KPIMetric[]> {
    const response = await apiClient.callAgent('decision', {
      action: 'analyze_kpis',
      params: params || {},
    });

    return response.output_data.data as KPIMetric[];
  }

  /**
   * 生成业务洞察
   */
  async generateInsights(params?: {
    start_date?: string;
    end_date?: string;
  }): Promise<BusinessInsight[]> {
    const response = await apiClient.callAgent('decision', {
      action: 'generate_insights',
      params: params || {},
    });

    return response.output_data.data as BusinessInsight[];
  }

  /**
   * 生成业务建议
   */
  async generateRecommendations(params?: {
    decision_type?: string;
    start_date?: string;
    end_date?: string;
  }): Promise<Recommendation[]> {
    const response = await apiClient.callAgent('decision', {
      action: 'generate_recommendations',
      params: params || {},
    });

    return response.output_data.data as Recommendation[];
  }
}

export const decisionAgentService = new DecisionAgentService();
export default decisionAgentService;
