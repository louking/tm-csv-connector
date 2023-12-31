"""result time is float

Revision ID: ca435dabcbcf
Revises: e91f48b7685f
Create Date: 2023-08-01 16:37:23.866955

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'ca435dabcbcf'
down_revision = 'e91f48b7685f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('result', schema=None) as batch_op:
        batch_op.alter_column('time',
               existing_type=mysql.TIME(),
               type_=sa.Float(),
               existing_nullable=True)

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('result', schema=None) as batch_op:
        batch_op.alter_column('time',
               existing_type=sa.Float(),
               type_=mysql.TIME(),
               existing_nullable=True)

    # ### end Alembic commands ###
