"""add chipbib table

Revision ID: 48a65429a4bd
Revises: 20f2a0c1c611
Create Date: 2024-06-12 20:34:41.025622

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '48a65429a4bd'
down_revision = '20f2a0c1c611'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('chipbib',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.String(length=12), nullable=True),
    sa.Column('bib', sa.Integer(), nullable=True),
    sa.Column('update_time', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('chipbib', schema=None) as batch_op:
        batch_op.create_index('tag_idx', ['tag_id'], unique=False)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('chipbib', schema=None) as batch_op:
        batch_op.drop_index('tag_idx')

    op.drop_table('chipbib')
    # ### end Alembic commands ###