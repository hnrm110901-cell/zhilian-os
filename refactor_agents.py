#!/usr/bin/env python3
"""
Script to refactor remaining agents to use BaseAgent interface
"""

# Agent configurations with their methods
AGENTS = {
    "inventory": {
        "path": "packages/agents/inventory/src/agent.py",
        "class_name": "InventoryAgent",
        "actions": [
            "monitor_inventory", "predict_consumption", "generate_restock_alerts",
            "check_expiration", "optimize_stock_levels", "get_inventory_report"
        ],
        "init_params": ["store_id", "pinzhi_adapter", "alert_thresholds"]
    },
    "service": {
        "path": "packages/agents/service/src/agent.py",
        "class_name": "ServiceAgent",
        "actions": [
            "collect_feedback", "analyze_feedback", "handle_complaint",
            "monitor_service_quality", "track_staff_performance",
            "generate_improvements", "get_service_report"
        ],
        "init_params": ["store_id", "aoqiwei_adapter", "quality_thresholds"]
    },
    "training": {
        "path": "packages/agents/training/src/agent.py",
        "class_name": "TrainingAgent",
        "actions": [
            "assess_training_needs", "generate_training_plan", "track_training_progress",
            "evaluate_training_effectiveness", "analyze_skill_gaps",
            "manage_certificates", "issue_certificate", "get_training_report"
        ],
        "init_params": ["store_id", "training_config"]
    },
    "decision": {
        "path": "packages/agents/decision/src/agent.py",
        "class_name": "DecisionAgent",
        "actions": [
            "analyze_kpis", "generate_insights", "generate_recommendations",
            "forecast_trends", "optimize_resources", "create_strategic_plan",
            "get_decision_report"
        ],
        "init_params": ["store_id", "schedule_agent", "order_agent", "inventory_agent",
                       "service_agent", "training_agent", "kpi_targets"]
    },
    "reservation": {
        "path": "packages/agents/reservation/src/agent.py",
        "class_name": "ReservationAgent",
        "actions": [
            "create_reservation", "confirm_reservation", "cancel_reservation",
            "create_banquet", "allocate_seating", "send_reminder",
            "analyze_reservations"
        ],
        "init_params": ["store_id", "order_agent", "config"]
    }
}

print("Agent refactoring configuration ready.")
print(f"Total agents to refactor: {len(AGENTS)}")
for name, config in AGENTS.items():
    print(f"  - {name}: {len(config['actions'])} actions")
