from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from sqlalchemy.orm import Session

from .config import AppConfig
from .formatters import sanitize_filename
from .models import GeneratedArticle, PublishTask
from .schemas import loads_list


WECHAT_TITLE_MAX_BYTES = 64
WECHAT_DIGEST_MAX_BYTES = 120


def trim_utf8_bytes(value: str, max_bytes: int, suffix: str = "...") -> str:
    text = " ".join((value or "").split())
    if len(text.encode("utf-8")) <= max_bytes:
        return text

    suffix_bytes = suffix.encode("utf-8")
    budget = max(0, max_bytes - len(suffix_bytes))
    result = ""
    used = 0
    for char in text:
        char_bytes = char.encode("utf-8")
        if used + len(char_bytes) > budget:
            break
        result += char
        used += len(char_bytes)
    return (result.rstrip() + suffix) if result else suffix[:max_bytes]


def strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "")


def wechat_safe_title(value: str) -> str:
    return trim_utf8_bytes(value or "未命名草稿", WECHAT_TITLE_MAX_BYTES)


def wechat_safe_digest(value: str) -> str:
    return trim_utf8_bytes(strip_html(value), WECHAT_DIGEST_MAX_BYTES)


def dumps_wechat_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def article_to_markdown(article: GeneratedArticle) -> str:
    material = article.material
    images = loads_list(material.image_paths_json) if material else []
    lines = [
        f"# {article.title}",
        "",
        f"- 平台：{article.platform}",
        f"- 格式：{article.content_format}",
        "",
        article.content,
    ]
    if images:
        lines.extend(["", "## 图片素材", *[f"- {image}" for image in images]])
    return "\n".join(lines).strip() + "\n"


def write_pending_file(article: GeneratedArticle, config: AppConfig) -> Path:
    date_dir = config.pending_output_dir / datetime.now().strftime("%Y-%m-%d")
    date_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{article.platform}_{article.id}_{sanitize_filename(article.title)}.md"
    file_path = date_dir / file_name
    file_path.write_text(article_to_markdown(article), encoding="utf-8")
    return file_path


class WechatDraftPublisher:
    token_url = "https://api.weixin.qq.com/cgi-bin/token"
    media_upload_url = "https://api.weixin.qq.com/cgi-bin/material/add_material"
    draft_add_url = "https://api.weixin.qq.com/cgi-bin/draft/add"
    freepublish_submit_url = "https://api.weixin.qq.com/cgi-bin/freepublish/submit"
    freepublish_status_url = "https://api.weixin.qq.com/cgi-bin/freepublish/get"

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def get_access_token(self) -> str:
        response = requests.get(
            self.token_url,
            params={
                "grant_type": "client_credential",
                "appid": self.config.wechat_app_id,
                "secret": self.config.wechat_app_secret,
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise RuntimeError(f"微信 access_token 获取失败：{payload}")
        return str(token)

    def upload_thumb(self, access_token: str, image_path: str) -> str:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"公众号封面图不存在：{image_path}")
        with path.open("rb") as image_file:
            response = requests.post(
                self.media_upload_url,
                params={"access_token": access_token, "type": "thumb"},
                files={"media": image_file},
                timeout=60,
            )
        response.raise_for_status()
        payload = response.json()
        media_id = payload.get("media_id")
        if not media_id:
            raise RuntimeError(f"公众号封面图上传失败：{payload}")
        return str(media_id)

    def create_draft(self, article: GeneratedArticle) -> dict[str, Any]:
        if not self.config.has_wechat:
            raise RuntimeError("微信公众号 AppID/AppSecret 未配置")

        image_paths = loads_list(article.material.image_paths_json)
        if not image_paths:
            raise RuntimeError("公众号草稿需要至少一张封面图；已停止调用官方 API")

        access_token = self.get_access_token()
        thumb_media_id = self.upload_thumb(access_token, image_paths[0])
        payload = {
            "articles": [
                {
                    "title": wechat_safe_title(article.title),
                    "thumb_media_id": thumb_media_id,
                    "author": "",
                    "digest": wechat_safe_digest(article.content),
                    "show_cover_pic": 1,
                    "content": article.content,
                    "content_source_url": "",
                    "need_open_comment": 0,
                    "only_fans_can_comment": 0,
                }
            ]
        }
        response = requests.post(
            self.draft_add_url,
            params={"access_token": access_token},
            data=dumps_wechat_json(payload),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("errcode") not in {None, 0}:
            raise RuntimeError(f"公众号草稿创建失败：{result}")
        return result

    def submit_publish(self, access_token: str, media_id: str) -> dict[str, Any]:
        response = requests.post(
            self.freepublish_submit_url,
            params={"access_token": access_token},
            data=dumps_wechat_json({"media_id": media_id}),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("errcode") not in {None, 0}:
            raise RuntimeError(f"公众号发布提交失败：{result}")
        return result

    def get_publish_status(self, access_token: str, publish_id: str) -> dict[str, Any]:
        response = requests.post(
            self.freepublish_status_url,
            params={"access_token": access_token},
            data=dumps_wechat_json({"publish_id": publish_id}),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        if result.get("errcode") not in {None, 0}:
            raise RuntimeError(f"公众号发布状态查询失败：{result}")
        return result

    def create_and_publish(self, article: GeneratedArticle) -> dict[str, Any]:
        draft_result = self.create_draft(article)
        media_id = draft_result.get("media_id")
        if not media_id:
            raise RuntimeError(f"公众号草稿创建成功但未返回 media_id：{draft_result}")

        access_token = self.get_access_token()
        publish_result = self.submit_publish(access_token, str(media_id))
        publish_id = publish_result.get("publish_id")
        status_result: dict[str, Any] | None = None
        if publish_id:
            status_result = self.get_publish_status(access_token, str(publish_id))

        return {
            "draft": draft_result,
            "publish": publish_result,
            "status": status_result,
        }


def choose_publish_mode(article: GeneratedArticle, requested_mode: str | None, config: AppConfig) -> str:
    if requested_mode:
        return requested_mode
    if article.platform == "official_account" and config.has_wechat:
        if config.wechat_auto_publish:
            return "wechat_publish"
        return "wechat_draft"
    return "file"


def publish_article(
    session: Session,
    article: GeneratedArticle,
    config: AppConfig,
    requested_mode: str | None = None,
) -> PublishTask:
    mode = choose_publish_mode(article, requested_mode, config)
    task = PublishTask(
        article=article,
        platform=article.platform,
        mode=mode,
        status="pending",
    )
    session.add(task)
    session.flush()

    try:
        if mode == "wechat_draft":
            result = WechatDraftPublisher(config).create_draft(article)
            task.status = "success"
            task.result_message = json.dumps(result, ensure_ascii=False)
            article.status = "published_draft"
        elif mode == "wechat_publish":
            result = WechatDraftPublisher(config).create_and_publish(article)
            task.status = "success"
            task.result_message = json.dumps(result, ensure_ascii=False)
            article.status = "published"
        elif mode == "file":
            file_path = write_pending_file(article, config)
            task.status = "success"
            task.output_path = str(file_path.resolve())
            task.result_message = "已生成待发布文件"
            article.status = "exported"
        else:
            raise ValueError(f"不支持的发布模式：{mode}")
    except Exception as exc:
        task.status = "failed"
        task.result_message = str(exc)
        article.status = "publish_failed"
    return task
