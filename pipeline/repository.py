from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import GeneratedArticle, Material, PublishTask
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


def recent_tasks(session: Session, limit: int = 30) -> list[PublishTask]:
    stmt = select(PublishTask).order_by(PublishTask.created_at.desc()).limit(max(1, min(limit, 100)))
    return list(session.scalars(stmt).all())


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

