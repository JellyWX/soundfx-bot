"""wipe emoji cols

Revision ID: f83685c19860
Revises: 2a7becc019e6
Create Date: 2018-09-06 17:57:08.637951

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f83685c19860'
down_revision = '2a7becc019e6'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('sounds', 'emoji_id')
    op.drop_column('sounds', 'emoji')
    op.add_column( 'sounds', sa.Column('emoji', sa.String(64)) )


def downgrade():
    op.add_column( 'sounds', sa.Column('emoji_id', sa.BigInteger) )
