"""Application approval and immutable export records."""
from alembic import op
import sqlalchemy as sa
revision='0004'
down_revision='0003'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('applications',sa.Column('id',sa.String(36),primary_key=True),sa.Column('owner_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),sa.Column('opportunity_id',sa.String(36),sa.ForeignKey('opportunities.id'),nullable=False,unique=True),sa.Column('status',sa.String(30),nullable=False),sa.Column('current_approval_id',sa.String(36),nullable=True),sa.Column('created_at',sa.Float,nullable=False))
    op.execute(sa.text("INSERT INTO applications (id,owner_id,opportunity_id,status,current_approval_id,created_at) SELECT id,owner_id,id,'drafting',NULL,0 FROM opportunities"))
    op.create_index('ix_applications_owner_id','applications',['owner_id'])
    op.create_table('artifact_approvals',sa.Column('id',sa.String(36),primary_key=True),sa.Column('application_id',sa.String(36),sa.ForeignKey('applications.id'),nullable=False),sa.Column('artifact_id',sa.String(36),sa.ForeignKey('resume_artifacts.id'),nullable=False,unique=True),sa.Column('actor_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),sa.Column('content_hash',sa.String(64),nullable=False),sa.Column('input_hash',sa.String(64),nullable=False),sa.Column('approved_at',sa.Float,nullable=False),sa.Column('invalidated_reason',sa.Text,nullable=False))
    op.create_index('ix_artifact_approvals_application_id','artifact_approvals',['application_id'])
    op.create_table('artifact_exports',sa.Column('id',sa.String(36),primary_key=True),sa.Column('approval_id',sa.String(36),sa.ForeignKey('artifact_approvals.id'),nullable=False),sa.Column('format',sa.String(10),nullable=False),sa.Column('renderer_version',sa.String(30),nullable=False),sa.Column('content_hash',sa.String(64),nullable=False),sa.Column('file_hash',sa.String(64),nullable=False),sa.Column('file_bytes',sa.LargeBinary,nullable=False),sa.Column('created_at',sa.Float,nullable=False),sa.UniqueConstraint('approval_id','format'))

def downgrade():
    op.drop_table('artifact_exports');op.drop_table('artifact_approvals');op.drop_table('applications')
