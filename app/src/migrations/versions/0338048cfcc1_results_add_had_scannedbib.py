"""results: add had_scannedbib

Revision ID: 0338048cfcc1
Revises: c059e4296731
Create Date: 2024-02-16 19:24:34.547552

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0338048cfcc1'
down_revision = 'c059e4296731'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('result', schema=None) as batch_op:
        batch_op.add_column(sa.Column('had_scannedbib', sa.Boolean(), nullable=True))

    # ### end Alembic commands ###

    # all existing results should be marked as confirmed
    from sqlalchemy.sql import table, column
    result = table('result',
                   column('had_scannedbib', sa.Boolean())
                   )
    op.execute(
        result.update()
        .values({'had_scannedbib': op.inline_literal(False)})
    )

def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('result', schema=None) as batch_op:
        batch_op.drop_column('had_scannedbib')

    # ### end Alembic commands ###