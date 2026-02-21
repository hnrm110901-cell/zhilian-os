export interface AgentRequest {
  agent_type: string;
  input_data: Record<string, any>;
}

export interface AgentResponse {
  agent_type: string;
  output_data: Record<string, any>;
  execution_time: number;
}

export interface HealthStatus {
  status: string;
  timestamp: string;
}

// 排班相关类型
export interface Employee {
  id: string;
  name: string;
  skills: string[];
}

export interface ScheduleRequest {
  action: 'run' | 'adjust' | 'get';
  store_id?: string;
  date?: string;
  employees?: Employee[];
  schedule_id?: string;
  adjustments?: any[];
  start_date?: string;
  end_date?: string;
}

// 预定相关类型
export interface ReservationRequest {
  action: 'create' | 'confirm' | 'cancel' | 'get';
  reservation_data?: {
    customer_name: string;
    customer_phone: string;
    party_size: number;
    reservation_date: string;
    reservation_time: string;
    special_requests?: string;
  };
  reservation_id?: string;
  reason?: string;
}
