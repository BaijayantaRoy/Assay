"""
Migration script: adds new columns to existing database.db
Run once after upgrading to v0.3.0
"""
import sqlite3
import os
from pathlib import Path

# Match the path logic in backend/database.py
DB_PATH = str(Path(__file__).resolve().parent.parent / "database.db")


MIGRATIONS = [
    # Prompts table - new columns
    "ALTER TABLE prompts ADD COLUMN environment_pins TEXT NOT NULL DEFAULT '{}'",

    # PromptVersions table - new columns
    "ALTER TABLE prompt_versions ADD COLUMN environment TEXT NOT NULL DEFAULT 'development'",

    # EvaluationRuns table - new columns
    "ALTER TABLE evaluation_runs ADD COLUMN dataset_id TEXT",
    "ALTER TABLE evaluation_runs ADD COLUMN evaluator_type TEXT NOT NULL DEFAULT 'llm_judge'",
    "ALTER TABLE evaluation_runs ADD COLUMN avg_score REAL",
    "ALTER TABLE evaluation_runs ADD COLUMN total_rows INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE evaluation_runs ADD COLUMN completed_rows INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE evaluation_runs ADD COLUMN completed_at TEXT",

    # EvaluationResults table - new columns
    "ALTER TABLE evaluation_results ADD COLUMN dataset_row_id TEXT",
    "ALTER TABLE evaluation_results ADD COLUMN rendered_prompt TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE evaluation_results ADD COLUMN reasoning TEXT",
    "ALTER TABLE evaluation_results ADD COLUMN human_annotation TEXT",
    "ALTER TABLE evaluation_results ADD COLUMN model TEXT",
    "ALTER TABLE evaluation_results ADD COLUMN prompt_tokens INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE evaluation_results ADD COLUMN completion_tokens INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE evaluation_results ADD COLUMN estimated_cost_usd REAL NOT NULL DEFAULT 0.0",

    # New tables
    """CREATE TABLE IF NOT EXISTS run_logs (
        id TEXT PRIMARY KEY,
        prompt_version_id TEXT NOT NULL REFERENCES prompt_versions(id),
        source TEXT,
        rendered_prompt TEXT NOT NULL DEFAULT '',
        response TEXT NOT NULL DEFAULT '',
        model TEXT NOT NULL DEFAULT '',
        prompt_tokens INTEGER NOT NULL DEFAULT 0,
        completion_tokens INTEGER NOT NULL DEFAULT 0,
        total_tokens INTEGER NOT NULL DEFAULT 0,
        latency_ms INTEGER NOT NULL DEFAULT 0,
        estimated_cost_usd REAL NOT NULL DEFAULT 0.0,
        variables_used TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",

    """CREATE TABLE IF NOT EXISTS datasets (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id),
        name TEXT NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",

    """CREATE TABLE IF NOT EXISTS dataset_rows (
        id TEXT PRIMARY KEY,
        dataset_id TEXT NOT NULL REFERENCES datasets(id),
        inputs TEXT NOT NULL DEFAULT '{}',
        expected_output TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",

    # v0.5.0 tables
    """CREATE TABLE IF NOT EXISTS compare_runs (
        id TEXT PRIMARY KEY,
        prompt_version_id TEXT NOT NULL REFERENCES prompt_versions(id),
        models TEXT NOT NULL DEFAULT '[]',
        variables TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",

    """CREATE TABLE IF NOT EXISTS compare_results (
        id TEXT PRIMARY KEY,
        compare_run_id TEXT NOT NULL REFERENCES compare_runs(id),
        model TEXT NOT NULL,
        response TEXT NOT NULL DEFAULT '',
        prompt_tokens INTEGER NOT NULL DEFAULT 0,
        completion_tokens INTEGER NOT NULL DEFAULT 0,
        latency_ms INTEGER NOT NULL DEFAULT 0,
        estimated_cost_usd REAL NOT NULL DEFAULT 0.0,
        error TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",

    """CREATE TABLE IF NOT EXISTS ab_tests (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        prompt_id TEXT NOT NULL REFERENCES prompts(id),
        description TEXT,
        status TEXT NOT NULL DEFAULT 'running',
        traffic_split INTEGER NOT NULL DEFAULT 50,
        winner TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",

    """CREATE TABLE IF NOT EXISTS ab_variants (
        id TEXT PRIMARY KEY,
        ab_test_id TEXT NOT NULL REFERENCES ab_tests(id),
        label TEXT NOT NULL,
        prompt_version_id TEXT NOT NULL REFERENCES prompt_versions(id),
        model TEXT NOT NULL DEFAULT 'gpt-4o',
        runs INTEGER NOT NULL DEFAULT 0,
        thumbs_up INTEGER NOT NULL DEFAULT 0,
        thumbs_down INTEGER NOT NULL DEFAULT 0,
        total_cost_usd REAL NOT NULL DEFAULT 0.0,
        avg_latency_ms REAL NOT NULL DEFAULT 0.0,
        avg_score REAL
    )""",

    """CREATE TABLE IF NOT EXISTS golden_cases (
        id TEXT PRIMARY KEY,
        prompt_id TEXT NOT NULL REFERENCES prompts(id),
        name TEXT NOT NULL,
        variables TEXT NOT NULL DEFAULT '{}',
        expected_output TEXT NOT NULL,
        match_type TEXT NOT NULL DEFAULT 'contains',
        match_value TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",

    """CREATE TABLE IF NOT EXISTS prompt_chains (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL REFERENCES projects(id),
        name TEXT NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""",

    """CREATE TABLE IF NOT EXISTS chain_steps (
        id TEXT PRIMARY KEY,
        chain_id TEXT NOT NULL REFERENCES prompt_chains(id),
        step_order INTEGER NOT NULL,
        prompt_version_id TEXT NOT NULL REFERENCES prompt_versions(id),
        model TEXT NOT NULL DEFAULT 'gpt-4o',
        output_variable TEXT NOT NULL,
        config TEXT NOT NULL DEFAULT '{}'
    )""",
]


def run_migrations():
    if not os.path.exists(DB_PATH):
        print(f"No database found at {DB_PATH} — will be created fresh on next startup.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    applied = 0
    skipped = 0

    for sql in MIGRATIONS:
        try:
            cursor.execute(sql)
            conn.commit()
            action = sql.strip().split()[0].upper()
            table = sql.strip().split()[2] if len(sql.strip().split()) > 2 else "?"
            print(f"  OK  {action} {table}")
            applied += 1
        except sqlite3.OperationalError as e:
            err = str(e)
            if "duplicate column name" in err or "already exists" in err:
                skipped += 1
            else:
                print(f"  ERR {sql[:60]}... -> {e}")

    conn.close()
    print(f"\nMigration complete: {applied} applied, {skipped} skipped (already existed).")


if __name__ == "__main__":
    print(f"Migrating database at: {DB_PATH}\n")
    run_migrations()
