"""big column

Revision ID: da306233df11
Revises: 80e3d0c08935
Create Date: 2018-10-04 14:05:23.202358

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'da306233df11'
down_revision = '80e3d0c08935'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column( 'sounds', sa.Column('big', sa.Boolean, default=False, nullable=False) )


def downgrade():
    op.drop_column('sounds', 'big')
