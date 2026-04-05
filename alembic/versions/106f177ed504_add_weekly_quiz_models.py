"""Add weekly quiz models

Revision ID: 106f177ed504
Revises: 47d10c483121
Create Date: 2026-02-04 10:14:27.439819

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '106f177ed504'
down_revision: Union[str, None] = '47d10c483121'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create weekly_quizzes table
    op.create_table('weekly_quizzes',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('questions', sa.JSON(), nullable=False),
        sa.Column('week_start_date', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create weekly_quiz_attempts table
    op.create_table('weekly_quiz_attempts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('quiz_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('answers', sa.JSON(), nullable=True),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('total_questions', sa.Integer(), nullable=False),
        sa.Column('correct_answers', sa.Integer(), nullable=False),
        sa.Column('time_taken_seconds', sa.Integer(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['quiz_id'], ['weekly_quizzes.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('weekly_quiz_attempts')
    op.drop_table('weekly_quizzes')
