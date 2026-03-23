"""initial schema — all tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0001_initial'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── blueprint_projects ──
    op.create_table(
        'blueprint_projects',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('paper_number', sa.String(), nullable=True),
        sa.Column('paper_title', sa.String(), nullable=True),
        sa.Column('paper_subtitle', sa.String(), nullable=True),
        sa.Column('target_venue', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), server_default=''),
        sa.Column('status', sa.String(), server_default='planned'),
        sa.Column('blocked_by', sa.String(), nullable=True),
        sa.Column('priority', sa.Integer(), server_default='5'),
        sa.Column('github_repo', sa.String(), nullable=True),
        sa.Column('xlsx_plan_path', sa.String(), nullable=True),
        sa.Column('notes', sa.Text(), server_default=''),
        sa.Column('hypothesis', sa.Text(), nullable=True),
        sa.Column('key_result', sa.Text(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('total_experiments', sa.Integer(), server_default='0'),
        sa.Column('completed_experiments', sa.Integer(), server_default='0'),
        sa.Column('current_phase', sa.String(), nullable=True),
        sa.Column('completion_criteria', sa.Text(), nullable=True),
        sa.Column('estimated_compute_hours', sa.Float(), server_default='0'),
        sa.Column('estimated_cost_usd', sa.Float(), server_default='0'),
        sa.Column('actual_compute_hours', sa.Float(), server_default='0'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── blueprint_experiments ──
    op.create_table(
        'blueprint_experiments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), server_default=''),
        sa.Column('status', sa.String(), server_default='planning'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['blueprint_projects.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── experiment_phases ──
    op.create_table(
        'experiment_phases',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('phase_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), server_default='planned'),
        sa.Column('blocked_by_phase', sa.String(), nullable=True),
        sa.Column('total_runs', sa.Integer(), server_default='0'),
        sa.Column('completed_runs', sa.Integer(), server_default='0'),
        sa.Column('research_question', sa.Text(), nullable=True),
        sa.Column('finding', sa.Text(), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['blueprint_projects.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── blueprint_pipelines ──
    op.create_table(
        'blueprint_pipelines',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('experiment_id', sa.String(), nullable=True),
        sa.Column('project_id', sa.String(), nullable=True),
        sa.Column('experiment_phase_id', sa.String(), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), server_default=''),
        sa.Column('definition', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['experiment_id'], ['blueprint_experiments.id']),
        sa.ForeignKeyConstraint(['project_id'], ['blueprint_projects.id']),
        sa.ForeignKeyConstraint(['experiment_phase_id'], ['experiment_phases.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── blueprint_runs ──
    op.create_table(
        'blueprint_runs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('pipeline_id', sa.String(), nullable=False),
        sa.Column('mlflow_run_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), server_default='pending'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('last_heartbeat', sa.DateTime(), nullable=True),
        sa.Column('config_snapshot', sa.JSON(), nullable=True),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('outputs_snapshot', sa.JSON(), nullable=True),
        sa.Column('metrics_log', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['pipeline_id'], ['blueprint_pipelines.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── blueprint_live_runs ──
    op.create_table(
        'blueprint_live_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_id', sa.String(), nullable=False),
        sa.Column('pipeline_name', sa.String(), server_default=''),
        sa.Column('project_name', sa.String(), server_default=''),
        sa.Column('current_block', sa.String(), server_default=''),
        sa.Column('current_block_index', sa.Integer(), server_default='0'),
        sa.Column('total_blocks', sa.Integer(), server_default='0'),
        sa.Column('block_progress', sa.Float(), server_default='0'),
        sa.Column('overall_progress', sa.Float(), server_default='0'),
        sa.Column('eta_seconds', sa.Float(), nullable=True),
        sa.Column('model_path', sa.String(), nullable=True),
        sa.Column('status', sa.String(), server_default='running'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['blueprint_runs.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── blueprint_datasets ──
    op.create_table(
        'blueprint_datasets',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('source', sa.String(), server_default='local'),
        sa.Column('source_path', sa.String(), server_default=''),
        sa.Column('description', sa.Text(), server_default=''),
        sa.Column('row_count', sa.Integer(), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('column_count', sa.Integer(), nullable=True),
        sa.Column('columns', sa.JSON(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── blueprint_artifacts ──
    op.create_table(
        'blueprint_artifacts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('run_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('type', sa.String(), server_default='file'),
        sa.Column('path', sa.String(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['blueprint_runs.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── blueprint_papers ──
    op.create_table(
        'blueprint_papers',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('project_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('content', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['blueprint_projects.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('blueprint_papers')
    op.drop_table('blueprint_artifacts')
    op.drop_table('blueprint_datasets')
    op.drop_table('blueprint_live_runs')
    op.drop_table('blueprint_runs')
    op.drop_table('blueprint_pipelines')
    op.drop_table('experiment_phases')
    op.drop_table('blueprint_experiments')
    op.drop_table('blueprint_projects')
