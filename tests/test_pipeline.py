from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.config import AppConfig
from pipeline.database import create_session_factory, init_database
from pipeline.generation import generate_drafts
from pipeline.publishers import (
    WECHAT_TITLE_MAX_BYTES,
    choose_publish_mode,
    dumps_wechat_json,
    publish_article,
    wechat_safe_title,
)
from pipeline.repository import create_articles, create_material
from pipeline.schemas import normalize_material

from sqlalchemy import create_engine


def make_config(tmp_path, **overrides):
    values = {
        "app_database_url": "sqlite:///:memory:",
        "external_database_url": "",
        "llm_api_key": "",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_model": "gpt-4o-mini",
        "pending_output_dir": tmp_path,
        "wechat_app_id": "",
        "wechat_app_secret": "",
        "wechat_auto_publish": False,
        "wechat_enable_mass_send": False,
        "scheduler_enabled": False,
        "scheduler_interval_minutes": 240,
    }
    values.update(overrides)
    return AppConfig(**values)


def test_normalize_material_accepts_string_lists():
    material = normalize_material(
        {
            "title_hint": "测试标题",
            "raw_content": "测试素材",
            "keywords": "招聘,楼宇出租",
            "target_platforms": "xiaohongshu,zhihu",
            "image_paths": "a.png,b.png",
        }
    )

    assert material.keywords == ["招聘", "楼宇出租"]
    assert material.target_platforms == ["xiaohongshu", "zhihu"]
    assert material.image_paths == ["a.png", "b.png"]


def test_generate_drafts_uses_fallback_without_llm(tmp_path):
    config = make_config(tmp_path)
    material = normalize_material(
        {
            "title_hint": "商引上线",
            "raw_content": "通过地图查看企业和楼宇信息",
            "target_platforms": ["xiaohongshu", "zhihu", "official_account"],
        }
    )

    source, drafts = generate_drafts(material, config)

    assert source == "fallback_template"
    assert set(drafts) == {"xiaohongshu", "zhihu", "official_account"}
    assert drafts["official_account"].content_format == "html"


def test_wechat_safe_title_trims_utf8_bytes():
    long_title = "公众号草稿创建失败标题过长测试" * 6
    safe_title = wechat_safe_title(long_title)

    assert len(safe_title.encode("utf-8")) <= WECHAT_TITLE_MAX_BYTES
    assert safe_title.endswith("...")


def test_wechat_json_keeps_chinese_utf8_unescaped():
    body = dumps_wechat_json({"articles": [{"title": "商引-商机地图小程序上线"}]})

    assert b"\\u" not in body
    assert "商引".encode("utf-8") in body


def test_choose_publish_mode_can_auto_publish_wechat(tmp_path):
    engine = create_engine("sqlite:///:memory:", future=True)
    init_database(engine)
    session_factory = create_session_factory(engine)
    config = make_config(
        tmp_path,
        wechat_app_id="appid",
        wechat_app_secret="secret",
        wechat_auto_publish=True,
    )
    session = session_factory()
    try:
        material_input = normalize_material(
            {
                "title_hint": "公众号自动发布",
                "raw_content": "正文内容",
                "target_platforms": ["official_account"],
            }
        )
        material = create_material(session, material_input)
        _, drafts = generate_drafts(material_input, config)
        article = create_articles(session, material, drafts)[0]

        assert choose_publish_mode(article, None, config) == "wechat_publish"
        assert choose_publish_mode(article, "wechat_draft", config) == "wechat_draft"
    finally:
        session.close()


def test_file_publish_records_success_and_output(tmp_path):
    engine = create_engine("sqlite:///:memory:", future=True)
    init_database(engine)
    session_factory = create_session_factory(engine)
    config = make_config(tmp_path)

    session = session_factory()
    try:
      material_input = normalize_material(
          {
              "title_hint": "待导出文章",
              "raw_content": "正文内容",
              "target_platforms": ["zhihu"],
          }
      )
      material = create_material(session, material_input)
      _, drafts = generate_drafts(material_input, config)
      article = create_articles(session, material, drafts)[0]
      task = publish_article(session, article, config, requested_mode="file")
      session.commit()

      assert task.status == "success"
      assert Path(task.output_path).exists()
      assert article.status == "exported"
    finally:
      session.close()
