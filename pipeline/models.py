from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title_hint: Mapped[str] = mapped_column(String(255), default="")
    raw_content: Mapped[str] = mapped_column(Text, default="")
    keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    target_platforms_json: Mapped[str] = mapped_column(Text, default="[]")
    image_paths_json: Mapped[str] = mapped_column(Text, default="[]")
    source_type: Mapped[str] = mapped_column(String(50), default="manual")
    source_ref: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    articles: Mapped[list["GeneratedArticle"]] = relationship(
        back_populates="material",
        cascade="all, delete-orphan",
    )


class GeneratedArticle(Base):
    __tablename__ = "generated_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    platform: Mapped[str] = mapped_column(String(50), index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    content_format: Mapped[str] = mapped_column(String(50), default="text")
    status: Mapped[str] = mapped_column(String(50), default="generated")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    material: Mapped[Material] = relationship(back_populates="articles")
    publish_tasks: Mapped[list["PublishTask"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )
    generation_history_links: Mapped[list["GenerationRunArticle"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
        foreign_keys="GenerationRunArticle.article_id",
    )
    followup_sources: Mapped[list["ArticleFollowUp"]] = relationship(
        back_populates="source_article",
        cascade="all, delete-orphan",
        foreign_keys="ArticleFollowUp.source_article_id",
    )
    followup_results: Mapped[list["ArticleFollowUp"]] = relationship(
        back_populates="result_article",
        cascade="all, delete-orphan",
        foreign_keys="ArticleFollowUp.result_article_id",
    )


class GenerationRun(Base):
    __tablename__ = "generation_runs"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title_hint: Mapped[str] = mapped_column(String(255), default="")
    raw_content: Mapped[str] = mapped_column(Text, default="")
    keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    target_platforms_json: Mapped[str] = mapped_column(Text, default="[]")
    image_paths_json: Mapped[str] = mapped_column(Text, default="[]")
    source_type: Mapped[str] = mapped_column(String(50), default="manual")
    source_ref: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    articles: Mapped[list["GenerationRunArticle"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class GenerationRunArticle(Base):
    __tablename__ = "generation_run_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("generation_runs.id"), index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("generated_articles.id"), index=True)
    platform: Mapped[str] = mapped_column(String(50), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    run: Mapped[GenerationRun] = relationship(back_populates="articles")
    article: Mapped[GeneratedArticle] = relationship(back_populates="generation_history_links")


class ArticleFollowUp(Base):
    __tablename__ = "article_followups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_article_id: Mapped[int] = mapped_column(ForeignKey("generated_articles.id"), index=True)
    result_article_id: Mapped[int] = mapped_column(ForeignKey("generated_articles.id"), index=True)
    instruction: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    source_article: Mapped[GeneratedArticle] = relationship(
        back_populates="followup_sources",
        foreign_keys=[source_article_id],
    )
    result_article: Mapped[GeneratedArticle] = relationship(
        back_populates="followup_results",
        foreign_keys=[result_article_id],
    )


class PublishTask(Base):
    __tablename__ = "publish_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("generated_articles.id"), index=True)
    platform: Mapped[str] = mapped_column(String(50), index=True)
    mode: Mapped[str] = mapped_column(String(50), default="file")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    result_message: Mapped[str] = mapped_column(Text, default="")
    output_path: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    article: Mapped[GeneratedArticle] = relationship(back_populates="publish_tasks")


class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    filename: Mapped[str] = mapped_column(String(255), default="")
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    result_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    items: Mapped[list["BatchItem"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )


class BatchItem(Base):
    __tablename__ = "batch_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("batch_jobs.id"), index=True)
    row_number: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    title_hint: Mapped[str] = mapped_column(String(255), default="")
    raw_content: Mapped[str] = mapped_column(Text, default="")
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped[BatchJob] = relationship(back_populates="items")


class TaskJob(Base):
    __tablename__ = "task_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(80), default="", index=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    celery_task_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    queue_name: Mapped[str] = mapped_column(String(80), default="default", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    progress_message: Mapped[str] = mapped_column(Text, default="")
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ObservabilityLog(Base):
    __tablename__ = "observability_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), default="", index=True)
    level: Mapped[str] = mapped_column(String(20), default="info", index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    path: Mapped[str] = mapped_column(String(255), default="", index=True)
    method: Mapped[str] = mapped_column(String(16), default="")
    status_code: Mapped[int] = mapped_column(Integer, default=0, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class LlmCallMetric(Base):
    __tablename__ = "llm_call_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation: Mapped[str] = mapped_column(String(80), default="", index=True)
    platform: Mapped[str] = mapped_column(String(50), default="", index=True)
    model: Mapped[str] = mapped_column(String(120), default="", index=True)
    success: Mapped[int] = mapped_column(Integer, default=1, index=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[str] = mapped_column(String(40), default="0")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ImageAsset(Base):
    __tablename__ = "image_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_name: Mapped[str] = mapped_column(String(255), default="")
    original_path: Mapped[str] = mapped_column(Text, default="")
    topic: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(50), default="processed", index=True)
    result_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    variants: Mapped[list["ImageVariant"]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
    )


class ImageVariant(Base):
    __tablename__ = "image_variants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("image_assets.id"), index=True)
    platform: Mapped[str] = mapped_column(String(50), index=True)
    usage: Mapped[str] = mapped_column(String(50), default="cover")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    output_path: Mapped[str] = mapped_column(Text, default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    asset: Mapped[ImageAsset] = relationship(back_populates="variants")
