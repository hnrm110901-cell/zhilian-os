"""hr16 — 离职结算单

Revision ID: hr16
Revises: hr15_approval
Create Date: 2026-03-15

Creates settlement_records table for employee separation settlements.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON

revision = 'hr16'
down_revision = 'hr15_approval'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # settlement_records 表可能已由 z15_settlement_risk 创建，安全跳过
    op.execute(sa.text("""
        DO $$ BEGIN
            CREATE TABLE settlement_records (
                id UUID PRIMARY KEY,
                store_id VARCHAR(50) NOT NULL,
                brand_id VARCHAR(50) NOT NULL,
                employee_id VARCHAR(50) NOT NULL,
                employee_name VARCHAR(100),
                separation_type VARCHAR(30) NOT NULL,
                last_work_date DATE NOT NULL,
                separation_date DATE NOT NULL,
                work_days_last_month INTEGER DEFAULT 0,
                last_month_salary_fen INTEGER DEFAULT 0,
                unused_annual_days INTEGER DEFAULT 0,
                annual_leave_compensation_fen INTEGER DEFAULT 0,
                annual_leave_calc_method VARCHAR(20) DEFAULT 'legal',
                service_years INTEGER DEFAULT 0,
                compensation_months INTEGER DEFAULT 0,
                compensation_base_fen INTEGER DEFAULT 0,
                economic_compensation_fen INTEGER DEFAULT 0,
                compensation_type VARCHAR(20) DEFAULT 'none',
                overtime_pay_fen INTEGER DEFAULT 0,
                bonus_fen INTEGER DEFAULT 0,
                deduction_fen INTEGER DEFAULT 0,
                deduction_detail TEXT,
                total_payable_fen INTEGER DEFAULT 0,
                handover_items JSON,
                handover_completed BOOLEAN DEFAULT false,
                status VARCHAR(20) DEFAULT 'draft',
                approval_instance_id UUID,
                paid_at TIMESTAMP,
                paid_by VARCHAR(100),
                calculation_snapshot JSON,
                remark TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT now(),
                updated_at TIMESTAMP NOT NULL DEFAULT now()
            );
            CREATE INDEX ix_settlement_store_id ON settlement_records (store_id);
            CREATE INDEX ix_settlement_employee_id ON settlement_records (employee_id);
            CREATE INDEX ix_settlement_store_status ON settlement_records (store_id, status);
        EXCEPTION WHEN duplicate_table THEN NULL;
        END $$
    """))


def downgrade() -> None:
    op.execute('DROP TABLE IF EXISTS settlement_records CASCADE')
