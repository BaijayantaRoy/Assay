from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone
from sqlmodel import Field, SQLModel, Relationship, JSON, Column, Text


def _utcnow() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Organization & Project
# ---------------------------------------------------------------------------

class Organization(SQLModel, table=True):
    __tablename__ = "organizations"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    slug: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=_utcnow)

    projects: List["Project"] = Relationship(back_populates="organization")


class Project(SQLModel, table=True):
    __tablename__ = "projects"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    description: Optional[str] = None
    organization_id: UUID = Field(foreign_key="organizations.id")

    organization: Organization = Relationship(back_populates="projects")
    prompts: List["Prompt"] = Relationship(back_populates="project")


# ---------------------------------------------------------------------------
# Prompt & Versions (with environment support)
# ---------------------------------------------------------------------------

class Prompt(SQLModel, table=True):
    __tablename__ = "prompts"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id")
    name: str = Field(index=True)
    description: Optional[str] = None
    tags: List[str] = Field(default=[], sa_type=JSON)
    created_at: datetime = Field(default_factory=_utcnow)
    latest_version_id: Optional[UUID] = None

    # Environment pins: {"production": version_id, "staging": version_id}
    environment_pins: dict = Field(default={}, sa_type=JSON)

    project: Project = Relationship(back_populates="prompts")
    versions: List["PromptVersion"] = Relationship(back_populates="prompt")


class PromptVersion(SQLModel, table=True):
    __tablename__ = "prompt_versions"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    prompt_id: UUID = Field(foreign_key="prompts.id")
    version_number: int
    content: str = Field(sa_column=Column(Text))
    # config holds model params: {"model": "gpt-6.1-sol", "temperature": 0.7, ...}
    config: dict = Field(default={}, sa_type=JSON)
    variables: List[str] = Field(default=[], sa_type=JSON)
    commit_message: Optional[str] = None
    # environment label: "development" | "staging" | "production"
    environment: str = Field(default="development")
    created_at: datetime = Field(default_factory=_utcnow)

    prompt: Prompt = Relationship(back_populates="versions")
    run_logs: List["RunLog"] = Relationship(back_populates="version")


# ---------------------------------------------------------------------------
# Run Logs (production tracing)
# ---------------------------------------------------------------------------

class RunLog(SQLModel, table=True):
    __tablename__ = "run_logs"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    prompt_version_id: UUID = Field(foreign_key="prompt_versions.id")
    # Caller identity (e.g. app name, API key tag)
    source: Optional[str] = Field(default=None)
    # The fully-rendered prompt after variable substitution
    rendered_prompt: str = Field(sa_column=Column(Text))
    # Raw LLM response
    response: str = Field(sa_column=Column(Text))
    model: str
    # Cost / token tracking
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    latency_ms: int = Field(default=0)
    estimated_cost_usd: float = Field(default=0.0)
    # Metadata
    variables_used: dict = Field(default={}, sa_type=JSON)
    created_at: datetime = Field(default_factory=_utcnow)

    version: PromptVersion = Relationship(back_populates="run_logs")


# ---------------------------------------------------------------------------
# Evaluation (Datasets + Runs + Results)
# ---------------------------------------------------------------------------

class Dataset(SQLModel, table=True):
    __tablename__ = "datasets"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id")
    name: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)

    rows: List["DatasetRow"] = Relationship(back_populates="dataset")
    runs: List["EvaluationRun"] = Relationship(back_populates="dataset")


class DatasetRow(SQLModel, table=True):
    __tablename__ = "dataset_rows"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    dataset_id: UUID = Field(foreign_key="datasets.id")
    # Input variables as JSON {variable_name: value}
    inputs: dict = Field(default={}, sa_type=JSON)
    # Optional expected/reference output
    expected_output: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=_utcnow)

    dataset: Dataset = Relationship(back_populates="rows")


class EvaluationRun(SQLModel, table=True):
    __tablename__ = "evaluation_runs"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    prompt_version_id: UUID = Field(foreign_key="prompt_versions.id")
    dataset_id: Optional[UUID] = Field(default=None, foreign_key="datasets.id")
    status: str = Field(default="queued")  # queued | running | completed | failed
    evaluator_type: str = Field(default="llm_judge")  # llm_judge | human | exact_match
    # Summary scores
    avg_score: Optional[float] = None
    total_rows: int = Field(default=0)
    completed_rows: int = Field(default=0)
    created_at: datetime = Field(default_factory=_utcnow)
    completed_at: Optional[datetime] = None

    dataset: Optional[Dataset] = Relationship(back_populates="runs")
    results: List["EvaluationResult"] = Relationship(back_populates="run")


class EvaluationResult(SQLModel, table=True):
    __tablename__ = "evaluation_results"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    evaluation_run_id: UUID = Field(foreign_key="evaluation_runs.id")
    dataset_row_id: Optional[UUID] = Field(default=None, foreign_key="dataset_rows.id")
    # The rendered prompt for this row
    rendered_prompt: str = Field(sa_column=Column(Text))
    # LLM output for this row
    output: str = Field(sa_column=Column(Text))
    # Score: 0.0 - 1.0
    score: Optional[float] = None
    # Evaluator reasoning / feedback
    reasoning: Optional[str] = Field(default=None, sa_column=Column(Text))
    # Human annotation: thumbs_up | thumbs_down | None
    human_annotation: Optional[str] = None
    model: Optional[str] = None
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    estimated_cost_usd: float = Field(default=0.0)
    created_at: datetime = Field(default_factory=_utcnow)

    run: EvaluationRun = Relationship(back_populates="results")


# ---------------------------------------------------------------------------
# Multi-Model Comparator
# ---------------------------------------------------------------------------

class CompareRun(SQLModel, table=True):
    __tablename__ = "compare_runs"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    prompt_version_id: UUID = Field(foreign_key="prompt_versions.id")
    models: List[str] = Field(default=[], sa_type=JSON)
    variables: dict = Field(default={}, sa_type=JSON)
    created_at: datetime = Field(default_factory=_utcnow)

    results: List["CompareResult"] = Relationship(back_populates="run")


class CompareResult(SQLModel, table=True):
    __tablename__ = "compare_results"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    compare_run_id: UUID = Field(foreign_key="compare_runs.id")
    model: str
    response: str = Field(sa_column=Column(Text))
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    latency_ms: int = Field(default=0)
    estimated_cost_usd: float = Field(default=0.0)
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)

    run: Optional[CompareRun] = Relationship(back_populates="results")


# ---------------------------------------------------------------------------
# A/B Testing
# ---------------------------------------------------------------------------

class ABTest(SQLModel, table=True):
    __tablename__ = "ab_tests"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    prompt_id: UUID = Field(foreign_key="prompts.id")
    description: Optional[str] = None
    status: str = Field(default="running")  # running | paused | concluded
    traffic_split: int = Field(default=50)  # % traffic to variant_b
    winner: Optional[str] = None  # "a" | "b" | None
    created_at: datetime = Field(default_factory=_utcnow)

    variants: List["ABVariant"] = Relationship(back_populates="test")


class ABVariant(SQLModel, table=True):
    __tablename__ = "ab_variants"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    ab_test_id: UUID = Field(foreign_key="ab_tests.id")
    label: str  # "A" or "B"
    prompt_version_id: UUID = Field(foreign_key="prompt_versions.id")
    model: str = Field(default="gpt-6.1-sol")
    runs: int = Field(default=0)
    thumbs_up: int = Field(default=0)
    thumbs_down: int = Field(default=0)
    total_cost_usd: float = Field(default=0.0)
    avg_latency_ms: float = Field(default=0.0)
    avg_score: Optional[float] = None

    test: Optional[ABTest] = Relationship(back_populates="variants")


# ---------------------------------------------------------------------------
# Golden Dataset / Regression Tests
# ---------------------------------------------------------------------------

class GoldenCase(SQLModel, table=True):
    __tablename__ = "golden_cases"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    prompt_id: UUID = Field(foreign_key="prompts.id")
    name: str
    variables: dict = Field(default={}, sa_type=JSON)
    expected_output: str = Field(sa_column=Column(Text))
    match_type: str = Field(default="contains")  # contains | exact | llm_judge | regex
    match_value: Optional[str] = None  # regex pattern or judge criteria
    created_at: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Prompt Chains
# ---------------------------------------------------------------------------

class PromptChain(SQLModel, table=True):
    __tablename__ = "prompt_chains"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="projects.id")
    name: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=_utcnow)

    steps: List["ChainStep"] = Relationship(back_populates="chain")


class ChainStep(SQLModel, table=True):
    __tablename__ = "chain_steps"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    chain_id: UUID = Field(foreign_key="prompt_chains.id")
    step_order: int
    prompt_version_id: UUID = Field(foreign_key="prompt_versions.id")
    model: str = Field(default="gpt-6.1-sol")
    output_variable: str  # name of variable where this step's output is stored
    config: dict = Field(default={}, sa_type=JSON)

    chain: Optional[PromptChain] = Relationship(back_populates="steps")

# ---------------------------------------------------------------------------
# LLM Model Registry
# ---------------------------------------------------------------------------

class LLMModel(SQLModel, table=True):
    __tablename__ = "llm_models"
    id: str = Field(primary_key=True, description="The API model identifier, e.g. gpt-6.1-sol")
    name: str = Field(index=True)
    provider: str = Field(index=True)
    context_window: str = Field(default="128k")
    input_cost_per_m: float = Field(default=0.0)
    output_cost_per_m: float = Field(default=0.0)
    is_active: bool = Field(default=True)
    updated_at: datetime = Field(default_factory=_utcnow)
