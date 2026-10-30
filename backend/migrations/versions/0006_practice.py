"""Reviewed answers and grounded interview practice."""
from alembic import op
import sqlalchemy as sa
revision='0006'
down_revision='0005'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('reviewed_answers',sa.Column('id',sa.String(36),primary_key=True),sa.Column('owner_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),sa.Column('opportunity_id',sa.String(36),sa.ForeignKey('opportunities.id'),nullable=False),sa.Column('workflow_id',sa.String(36),sa.ForeignKey('career_workflows.id'),nullable=False,unique=True),sa.Column('question',sa.Text,nullable=False),sa.Column('claims',sa.JSON,nullable=False),sa.Column('input_json',sa.JSON,nullable=False),sa.Column('input_hash',sa.String(64),nullable=False),sa.Column('findings',sa.JSON,nullable=False),sa.Column('status',sa.String(30),nullable=False),sa.Column('revision',sa.Integer,nullable=False),sa.Column('approved_hash',sa.String(64),nullable=False),sa.Column('history',sa.JSON,nullable=False),sa.Column('created_at',sa.Float,nullable=False))
    op.create_table('interview_sessions',sa.Column('id',sa.String(36),primary_key=True),sa.Column('owner_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),sa.Column('opportunity_id',sa.String(36),sa.ForeignKey('opportunities.id'),nullable=False),sa.Column('workflow_id',sa.String(36),sa.ForeignKey('career_workflows.id'),nullable=False,unique=True),sa.Column('input_hash',sa.String(64),nullable=False),sa.Column('input_json',sa.JSON,nullable=False),sa.Column('questions',sa.JSON,nullable=False),sa.Column('status',sa.String(30),nullable=False),sa.Column('created_at',sa.Float,nullable=False))
    op.create_table('interview_responses',sa.Column('id',sa.String(36),primary_key=True),sa.Column('session_id',sa.String(36),sa.ForeignKey('interview_sessions.id'),nullable=False),sa.Column('question_id',sa.String(36),nullable=False),sa.Column('text',sa.Text,nullable=False),sa.Column('input_hash',sa.String(64),nullable=False),sa.Column('workflow_id',sa.String(36),sa.ForeignKey('career_workflows.id'),nullable=True,unique=True),sa.Column('feedback',sa.JSON,nullable=False),sa.Column('status',sa.String(30),nullable=False),sa.Column('created_at',sa.Float,nullable=False))
    for table in ('reviewed_answers','interview_sessions'):
        for column in ('owner_id','opportunity_id'):op.create_index(f'ix_{table}_{column}',table,[column])
    op.create_index('ix_interview_responses_session_id','interview_responses',['session_id'])

def downgrade():
    op.drop_table('interview_responses');op.drop_table('interview_sessions');op.drop_table('reviewed_answers')
