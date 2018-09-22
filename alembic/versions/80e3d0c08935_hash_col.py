"""hash col

Revision ID: 80e3d0c08935
Revises: 2652c7474faf
Create Date: 2018-09-22 19:37:10.516328

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '80e3d0c08935'
down_revision = '2652c7474faf'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('sounds', sa.Column('hash', sa.String(32)))


def downgrade():
    op.drop_column('sounds', 'hash')
