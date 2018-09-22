"""uploader tracking

Revision ID: 2652c7474faf
Revises: f83685c19860
Create Date: 2018-09-22 14:20:25.694884

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2652c7474faf'
down_revision = 'f83685c19860'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'sounds', sa.Column( 'uploader_id', sa.BigInteger, sa.ForeignKey('users.id') )
    )


def downgrade():
    op.drop_column('sounds', 'uploader_id')
