from __future__ import annotations

import importlib
import json
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


def test_config_endpoint_hides_server_secrets_and_does_not_persist_user_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "app_database_url": "sqlite:///data/pipeline.db",
                "llm": {
                    "api_key": "saved-api-key",
                    "base_url": "https://example.test/v1",
                    "model": "old-model",
                },
                "database": {
                    "url": "mysql+pymysql://user:password@127.0.0.1:3306/source",
                },
                "publish": {
                    "pending_output_dir": "data/pending",
                },
                "wechat": {
                    "app_id": "wx-old",
                    "app_secret": "saved-secret",
                    "auto_publish": False,
                    "enable_mass_send": False,
                },
                "scheduler": {
                    "enabled": False,
                    "interval_minutes": 240,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONTENT_PIPELINE_CONFIG", str(config_path))

    app_module = importlib.import_module("app")
    app_module = importlib.reload(app_module)
    client = app_module.app.test_client()

    response = client.get("/api/config")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "saved-api-key" not in body
    assert "saved-secret" not in body
    assert "password" not in body
    assert response.get_json()["data"]["config"]["llm"]["api_key_configured"] is True

    response = client.post(
        "/api/config",
        json={
            "config": {
                "app_database_url": "sqlite:///data/pipeline.db",
                "llm": {
                    "api_key": "",
                    "base_url": "https://example.test/v2",
                    "model": "new-model",
                },
                "database": {
                    "url": "",
                },
                "publish": {
                    "pending_output_dir": "data/outbox",
                },
                "wechat": {
                    "app_id": "wx-new",
                    "app_secret": "",
                    "auto_publish": True,
                    "enable_mass_send": False,
                },
                "scheduler": {
                    "enabled": False,
                    "interval_minutes": 30,
                },
            }
        },
    )

    assert response.status_code == 200
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["llm"]["api_key"] == "saved-api-key"
    assert saved["llm"]["model"] == "old-model"
    assert saved["database"]["url"] == "mysql+pymysql://user:password@127.0.0.1:3306/source"
    assert saved["wechat"]["app_id"] == "wx-old"
    assert saved["wechat"]["app_secret"] == "saved-secret"
    assert saved["wechat"]["auto_publish"] is False


def test_request_config_uses_browser_config_without_persisting(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "app_database_url": "sqlite:///data/pipeline.db",
                "llm": {
                    "api_key": "server-key",
                    "base_url": "https://server.example/v1",
                    "model": "server-model",
                },
                "database": {
                    "url": "",
                },
                "publish": {
                    "pending_output_dir": "data/pending",
                },
                "wechat": {
                    "app_id": "",
                    "app_secret": "",
                    "auto_publish": False,
                    "enable_mass_send": False,
                },
                "scheduler": {
                    "enabled": False,
                    "interval_minutes": 240,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONTENT_PIPELINE_CONFIG", str(config_path))

    app_module = importlib.import_module("app")
    app_module = importlib.reload(app_module)
    request_config = app_module.config_for_request(
        {
            "config": {
                "app_database_url": "sqlite:///data/pipeline.db",
                "llm": {
                    "api_key": "browser-key",
                    "base_url": "https://browser.example/v1",
                    "model": "browser-model",
                },
                "database": {
                    "url": "mysql+pymysql://browser:secret@127.0.0.1:3306/source",
                },
                "publish": {
                    "pending_output_dir": "data/browser-pending",
                },
                "wechat": {
                    "app_id": "wx-browser",
                    "app_secret": "browser-secret",
                    "auto_publish": True,
                    "enable_mass_send": False,
                },
                "scheduler": {
                    "enabled": False,
                    "interval_minutes": 30,
                },
            }
        }
    )

    assert request_config.llm_api_key == "browser-key"
    assert request_config.llm_base_url == "https://browser.example/v1"
    assert request_config.llm_model == "browser-model"
    assert request_config.external_database_url.startswith("mysql+pymysql://browser")
    assert request_config.wechat_app_id == "wx-browser"
    assert request_config.wechat_app_secret == "browser-secret"
    assert request_config.wechat_auto_publish is True

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["llm"]["api_key"] == "server-key"
    assert saved["llm"]["model"] == "server-model"
