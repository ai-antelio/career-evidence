"""Application timeline and account privacy lifecycle."""
from alembic import op
import sqlalchemy as sa
revision='0007'
down_revision='0006'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('application_tracking',sa.Column('application_id',sa.String(36),sa.ForeignKey('applications.id'),primary_key=True),sa.Column('revision',sa.Integer,nullable=False),sa.Column('status',sa.String(30),nullable=False),sa.Column('notes',sa.Text,nullable=False),sa.Column('next_action',sa.Text,nullable=False),sa.Column('follow_up_at',sa.String(40),nullable=True),sa.Column('submitted_snapshot',sa.JSON,nullable=True))
    op.create_table('application_events',sa.Column('id',sa.String(36),primary_key=True),sa.Column('application_id',sa.String(36),sa.ForeignKey('applications.id'),nullable=False),sa.Column('kind',sa.String(30),nullable=False),sa.Column('status',sa.String(30),nullable=False),sa.Column('note',sa.Text,nullable=False),sa.Column('created_at',sa.Float,nullable=False))
    op.create_index('ix_application_events_application_id','application_events',['application_id'])
    op.create_table('audit_events',sa.Column('id',sa.String(36),primary_key=True),sa.Column('owner_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),sa.Column('action',sa.String(100),nullable=False),sa.Column('resource',sa.String(250),nullable=False),sa.Column('status_code',sa.Integer,nullable=False),sa.Column('created_at',sa.Float,nullable=False))
    op.create_index('ix_audit_events_owner_id','audit_events',['owner_id'])
    op.create_table('account_deletion_jobs',sa.Column('id',sa.String(36),primary_key=True),sa.Column('owner_id',sa.String(36),nullable=True,unique=True),sa.Column('status',sa.String(30),nullable=False),sa.Column('storage_keys',sa.JSON,nullable=False),sa.Column('attempts',sa.Integer,nullable=False),sa.Column('error',sa.String(100),nullable=False),sa.Column('created_at',sa.Float,nullable=False),sa.Column('completed_at',sa.Float,nullable=True))
    op.create_index('ix_account_deletion_jobs_status','account_deletion_jobs',['status'])

def downgrade():
    for name in ['account_deletion_jobs','audit_events','application_events','application_tracking']:op.drop_table(name)
