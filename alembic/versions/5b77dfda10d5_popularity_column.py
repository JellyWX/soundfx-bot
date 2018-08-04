"""popularity column

Revision ID: 5b77dfda10d5
Revises: f53dbf5384c6
Create Date: 2018-08-05 00:29:30.118920

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5b77dfda10d5'
down_revision = 'f53dbf5384c6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column( 'sounds', sa.Column('plays', sa.Integer, default=0) )
    op.add_column( 'sounds', sa.Column('safe', sa.Boolean, default=False) )


def downgrade():
    op.drop_column( 'sounds', 'plays' )
    op.drop_column( 'sounds', 'safe' )
