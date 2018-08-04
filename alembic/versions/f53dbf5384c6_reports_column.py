"""reports column

Revision ID: f53dbf5384c6
Revises: 9530022c381a
Create Date: 2018-08-04 17:08:17.244722

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f53dbf5384c6'
down_revision = '9530022c381a'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column( 'sounds', sa.Column('reports', sa.Integer, default=0) )


def downgrade():
    op.drop_column('sounds', 'reports')
