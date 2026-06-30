from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import ArticleFollowUp, GeneratedArticle, GenerationRun, GenerationRunArticle, Material, PublishTask
from .schemas import ArticleDraft, MaterialInput, dumps_list, loads_list


def create_material(session: Session, material_input: MaterialInput) -> Material:
    material = Material(
        title_hint=material_input.title_hint,
        raw_content=material_input.raw_content,
        keywords_json=dumps_list(material_input.keywords),
        target_platforms_json=dumps_list(material_input.target_platforms),
        image_paths_json=dumps_list(material_input.image_paths),
        source_type=material_input.source_type,
        source_ref=material_input.source_ref,
    )
    session.add(material)
    session.flush()
    return material


def create_articles(
    session: Session,
    material: Material,
    drafts: dict[str, ArticleDraft],
) -> list[GeneratedArticle]:
    articles: list[GeneratedArticle] = []
    for draft in drafts.values():
        article = GeneratedArticle(
            material=material,
            platform=draft.platform,
            title=draft.title,
            content=draft.content,
            content_format=draft.content_format,
            status="generated",
        )
        session.add(article)
        articles.append(article)
    session.flush()
    return articles


def get_article(session: Session, article_id: int) -> GeneratedArticle | None:
    return session.get(GeneratedArticle, article_id)


def create_follow_up_article(
    session: Session,
    source_article: GeneratedArticle,
    draft: ArticleDraft,
    instruction: str,
    model: str,
) -> tuple[GeneratedArticle, ArticleFollowUp]:
    article = GeneratedArticle(
        material_id=source_article.material_id,
        platform=source_article.platform,
        title=draft.title,
        content=draft.content,
        content_format=draft.content_format or source_article.content_format,
        status="revised",
    )
    session.add(article)
    session.flush()
    follow_up = ArticleFollowUp(
        source_article=source_article,
        result_article=article,
        instruction=instruction,
        model=model,
    )
    session.add(follow_up)
    session.flush()
    return article, follow_up


def list_article_followups(session: Session, article_id: int) -> list[ArticleFollowUp]:
    stmt = (
        select(ArticleFollowUp)
        .where(
            or_(
                ArticleFollowUp.source_article_id == article_id,
                ArticleFollowUp.result_article_id == article_id,
            )
        )
        .order_by(ArticleFollowUp.created_at.asc())
    )
    return list(session.scalars(stmt).all())


def recent_tasks(session: Session, limit: int = 30) -> list[PublishTask]:
    stmt = select(PublishTask).order_by(PublishTask.created_at.desc()).limit(max(1, min(limit, 100)))
    return list(session.scalars(stmt).all())


def get_or_create_generation_run(
    session: Session,
    run_id: str,
    material_input: MaterialInput,
    expected_platforms: list[str],
) -> GenerationRun:
    run = session.get(GenerationRun, run_id)
    if run:
        run.updated_at = datetime.utcnow()
        return run

    run = GenerationRun(
        id=run_id,
        title_hint=material_input.title_hint,
        raw_content=material_input.raw_content,
        keywords_json=dumps_list(material_input.keywords),
        target_platforms_json=dumps_list(expected_platforms or material_input.target_platforms),
        image_paths_json=dumps_list(material_input.image_paths),
        source_type=material_input.source_type,
        source_ref=material_input.source_ref,
    )
    session.add(run)
    session.flush()
    return run


def link_generation_articles(
    session: Session,
    run: GenerationRun,
    articles: list[GeneratedArticle],
) -> None:
    existing_article_ids = {
        link.article_id for link in run.articles
    }
    for article in articles:
        if article.id in existing_article_ids:
            continue
        session.add(
            GenerationRunArticle(
                run=run,
                article=article,
                platform=article.platform,
            )
        )
    run.updated_at = datetime.utcnow()
    session.flush()


def list_generation_runs(
    session: Session,
    limit: int = 20,
    offset: int = 0,
    query: str = "",
    platform: str = "",
) -> list[GenerationRun]:
    stmt = select(GenerationRun).order_by(GenerationRun.created_at.desc())
    if query:
        like_query = f"%{query}%"
        stmt = stmt.where(
            or_(
                GenerationRun.title_hint.like(like_query),
                GenerationRun.raw_content.like(like_query),
            )
        )
    if platform:
        stmt = stmt.where(GenerationRun.target_platforms_json.like(f'%"{platform}"%'))
    stmt = stmt.offset(max(0, offset)).limit(max(1, min(limit, 100)))
    return list(session.scalars(stmt).unique().all())


def get_generation_run(session: Session, run_id: str) -> GenerationRun | None:
    return session.get(GenerationRun, run_id)


def material_payload(material: Material) -> dict[str, object]:
    return {
        "id": material.id,
        "title_hint": material.title_hint,
        "raw_content": material.raw_content,
        "keywords": loads_list(material.keywords_json),
        "target_platforms": loads_list(material.target_platforms_json),
        "image_paths": loads_list(material.image_paths_json),
        "source_type": material.source_type,
        "source_ref": material.source_ref,
        "created_at": material.created_at.isoformat(),
    }


def article_payload(article: GeneratedArticle) -> dict[str, object]:
    return {
        "id": article.id,
        "material_id": article.material_id,
        "platform": article.platform,
        "title": article.title,
        "content": article.content,
        "format": article.content_format,
        "status": article.status,
        "created_at": article.created_at.isoformat(),
    }


def follow_up_payload(follow_up: ArticleFollowUp) -> dict[str, object]:
    return {
        "id": follow_up.id,
        "source_article_id": follow_up.source_article_id,
        "result_article_id": follow_up.result_article_id,
        "instruction": follow_up.instruction,
        "model": follow_up.model,
        "created_at": follow_up.created_at.isoformat(),
    }


def task_payload(task: PublishTask) -> dict[str, object]:
    return {
        "id": task.id,
        "article_id": task.article_id,
        "platform": task.platform,
        "mode": task.mode,
        "status": task.status,
        "result_message": task.result_message,
        "output_path": task.output_path,
        "created_at": task.created_at.isoformat(),
    }


def generation_run_payload(run: GenerationRun) -> dict[str, object]:
    articles = [link.article for link in sorted(run.articles, key=lambda item: item.created_at)]
    generated_platforms = list(dict.fromkeys(article.platform for article in articles))
    return {
        "id": run.id,
        "title_hint": run.title_hint,
        "keywords": loads_list(run.keywords_json),
        "target_platforms": loads_list(run.target_platforms_json),
        "generated_platforms": generated_platforms,
        "article_count": len(articles),
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


def generation_run_detail_payload(run: GenerationRun) -> dict[str, object]:
    payload = generation_run_payload(run)
    articles = [link.article for link in sorted(run.articles, key=lambda item: item.created_at)]
    payload.update(
        {
            "material": {
                "title_hint": run.title_hint,
                "raw_content": run.raw_content,
                "keywords": loads_list(run.keywords_json),
                "target_platforms": loads_list(run.target_platforms_json),
                "image_paths": loads_list(run.image_paths_json),
                "source_type": run.source_type,
                "source_ref": run.source_ref,
            },
            "articles": [article_payload(article) for article in articles],
        }
    )
    return payload
