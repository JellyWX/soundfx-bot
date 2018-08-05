"""join and leave sounds

Revision ID: cecf191507f3
Revises: 5b77dfda10d5
Create Date: 2018-08-05 15:43:32.812247

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cecf191507f3'
down_revision = '5b77dfda10d5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'users', sa.Column( 'join_sound_id', sa.Integer, sa.ForeignKey('sounds.id') )
    )

    op.add_column(
        'users', sa.Column( 'leave_sound_id', sa.Integer, sa.ForeignKey('sounds.id') )
    )


def downgrade():
    op.drop_column( 'users', 'join_sound_id' )
    op.drop_column( 'users', 'leave_sound_id' )
