"""Durable broker dispatch outbox and queue lookup indexes."""
from alembic import op
import sqlalchemy as sa
revision='0005'
down_revision='0004'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('dispatch_events',sa.Column('id',sa.String(36),primary_key=True),sa.Column('topic',sa.String(40),nullable=False),sa.Column('target_id',sa.String(36),nullable=False),sa.Column('status',sa.String(20),nullable=False),sa.Column('available_at',sa.Float,nullable=False),sa.Column('published_at',sa.Float,nullable=False),sa.Column('attempts',sa.Integer,nullable=False),sa.Column('error',sa.Text,nullable=False))
    for col in ['target_id','status','available_at']:op.create_index('ix_dispatch_events_'+col,'dispatch_events',[col])
    op.create_index('ix_outbox_jobs_eligible','outbox_jobs',['status','available_at','lease_until'])
    op.create_index('ix_career_workflows_lease','career_workflows',['status','lease_until'])
    # Existing pending/running jobs are recovered by the relay on startup.

def downgrade():
    op.drop_index('ix_career_workflows_lease',table_name='career_workflows')
    op.drop_index('ix_outbox_jobs_eligible',table_name='outbox_jobs')
    op.drop_table('dispatch_events')
