"""Initial profile workflow schema."""
from alembic import op
import sqlalchemy as sa
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Frozen schema snapshot, independent of future application model changes.
    from pathlib import Path
    import json
    snapshot = json.loads((Path(__file__).with_name('0001_schema.json')).read_text())
    for table in snapshot:
        columns = []
        for c in table['columns']:
            typ = {'string':lambda:sa.String(c['length']), 'text':sa.Text, 'integer':sa.Integer, 'float':sa.Float}[c['type']]()
            args = [sa.ForeignKey(c['foreign_key'])] if c['foreign_key'] else []
            columns.append(sa.Column(c['name'], typ, *args, primary_key=c['primary_key'], nullable=c['nullable']))
        op.create_table(table['name'], *columns, *[sa.UniqueConstraint(*u) for u in table['uniques']])
        for idx in table['indexes']: op.create_index(idx['name'], table['name'], idx['columns'], unique=idx['unique'])

def downgrade():
    for name in ['review_events','fact_versions','fact_proposals','outbox_jobs','documents','sessions','users']: op.drop_table(name)
