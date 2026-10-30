"""Structured extraction metadata and generation audit."""
from alembic import op
import sqlalchemy as sa
revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('fact_proposals',sa.Column('structured_fields',sa.JSON(),nullable=False,server_default='[]'))
    op.add_column('fact_proposals',sa.Column('extraction_adapter',sa.String(30),nullable=False,server_default='deterministic'))
    op.create_table('generation_runs',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('document_id',sa.String(36),sa.ForeignKey('documents.id'),nullable=False),
        sa.Column('owner_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('job_id',sa.String(36),sa.ForeignKey('outbox_jobs.id'),nullable=False),
        sa.Column('status',sa.String(30),nullable=False),
        sa.Column('error_code',sa.String(50),nullable=False),
        sa.Column('metadata_json',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.Float(),nullable=False))
    op.create_index('ix_generation_runs_document_id','generation_runs',['document_id'])
    op.create_index('ix_generation_runs_owner_id','generation_runs',['owner_id'])

def downgrade():
    op.drop_table('generation_runs')
    op.drop_column('fact_proposals','extraction_adapter')
    op.drop_column('fact_proposals','structured_fields')
