"""locked column

Revision ID: 2a7becc019e6
Revises: cecf191507f3
Create Date: 2018-08-06 18:10:03.570280

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2a7becc019e6'
down_revision = 'cecf191507f3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('sounds', sa.Column('locked', sa.Boolean, nullable=False, default=False))


def downgrade():
    op.drop_column('sounds', 'locked')
