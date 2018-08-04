"""public column

Revision ID: 9530022c381a
Revises:
Create Date: 2018-08-04 14:22:28.742683

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9530022c381a'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.add_column( 'sounds', sa.Column('public', sa.Boolean, nullable=False, default=False) )

    """op.execute('''
    UPDATE sounds
    SET public = 'f'
    '''
    )

    op.alter_column( 'sounds', 'public', nullable=False)"""


def downgrade():
    op.drop_column('sounds', 'public')
