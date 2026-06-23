from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.config import AppConfig
from pipeline.batch import create_batch_job, parse_batch_file
from pipeline.compliance import check_text
from pipeline.database import create_session_factory, init_database
from pipeline.image_processing import process_image
from pipeline.generation import (
    build_system_prompt,
    build_user_prompt,
    generate_drafts,
    material_for_platform,
)
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


def test_normalize_material_defaults_to_all_five_platforms():
    material = normalize_material(
        {
            "title_hint": "B2B topic",
            "raw_content": "Source material",
        }
    )

    assert material.target_platforms == [
        "xiaohongshu",
        "zhihu",
        "official_account",
        "toutiao",
        "shipinhao",
    ]


def test_normalize_material_accepts_zhihu_qa_without_defaulting_to_it():
    material = normalize_material(
        {
            "title_hint": "问答选题",
            "raw_content": "问答素材",
            "target_platforms": "zhihu_qa",
        }
    )

    assert material.target_platforms == ["zhihu_qa"]


def test_generation_prompts_include_task_rules():
    material = normalize_material(
        {
            "title_hint": "Office leasing update",
            "raw_content": "Useful material for office leasing operators.",
            "keywords": ["招商", "办公租赁"],
            "target_platforms": ["official_account", "xiaohongshu", "toutiao", "shipinhao", "zhihu_qa"],
        }
    )

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(material)

    assert "去 AI 化" in system_prompt
    assert "B 端" in system_prompt
    assert "广告法极限词" in system_prompt
    assert "公众号" in user_prompt
    assert "小红书" in user_prompt
    assert "今日头条" in user_prompt
    assert "视频号" in user_prompt
    assert "商引羚航" in user_prompt
    assert "Jade一城探访记" in user_prompt
    assert "一城探访手记" in user_prompt
    assert "知乎 Q&A" in user_prompt
    assert "先用 1-2 句话直接回答" in user_prompt
    assert '"shipinhao"' in user_prompt
    assert '"zhihu_qa"' in user_prompt


def test_material_for_platform_keeps_source_fields():
    material = normalize_material(
        {
            "title_hint": "Topic",
            "raw_content": "Content",
            "keywords": ["招商"],
            "target_platforms": ["official_account", "toutiao"],
            "image_paths": ["cover.jpg"],
            "source_type": "manual",
            "source_ref": "row-1",
        }
    )

    platform_material = material_for_platform(material, "toutiao")

    assert platform_material.target_platforms == ["toutiao"]
    assert platform_material.title_hint == material.title_hint
    assert platform_material.raw_content == material.raw_content
    assert platform_material.keywords == material.keywords
    assert platform_material.image_paths == material.image_paths
    assert platform_material.source_ref == "row-1"


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


def test_generate_drafts_supports_new_platform_fallbacks(tmp_path):
    config = make_config(tmp_path)
    material = normalize_material(
        {
            "title_hint": "Business update",
            "raw_content": "A useful source material for the operations team.",
            "target_platforms": ["toutiao", "shipinhao"],
        }
    )

    source, drafts = generate_drafts(material, config)

    assert source == "fallback_template"
    assert set(drafts) == {"toutiao", "shipinhao"}
    assert drafts["toutiao"].content_format == "markdown"
    assert drafts["shipinhao"].content_format == "script"


def test_generate_drafts_supports_zhihu_qa_fallback(tmp_path):
    config = make_config(tmp_path)
    material = normalize_material(
        {
            "title_hint": "办公选址工具",
            "raw_content": "帮助企业快速查看楼宇和企业信息。",
            "target_platforms": ["zhihu_qa"],
        }
    )

    source, drafts = generate_drafts(material, config)

    assert source == "fallback_template"
    assert set(drafts) == {"zhihu_qa"}
    assert drafts["zhihu_qa"].content_format == "markdown"
    assert "问题：" in drafts["zhihu_qa"].content


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


def test_root_returns_frontend_dev_hint_when_dist_is_missing(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setenv("CONTENT_PIPELINE_CONFIG", str(config_path))

    app_module = importlib.import_module("app")
    app_module = importlib.reload(app_module)
    client = app_module.app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert "Frontend build not found" in response.get_json()["message"]


def test_unknown_api_route_returns_404(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setenv("CONTENT_PIPELINE_CONFIG", str(config_path))

    app_module = importlib.import_module("app")
    app_module = importlib.reload(app_module)
    client = app_module.app.test_client()

    response = client.get("/api/not-found")

    assert response.status_code == 404
    assert response.get_json()["success"] is False


def test_compliance_checker_flags_sensitive_terms():
    result = check_text("这是唯一保证有效的方案，总之建议立即扫码了解", "toutiao")

    assert result["status"] == "high_risk"
    assert result["risk_count"] >= 3


def test_parse_batch_csv_and_create_job(tmp_path):
    csv_content = "标题,素材正文,关键词,目标平台\n选题A,正文A,招商,头条\n".encode("utf-8-sig")
    materials = parse_batch_file("batch.csv", csv_content)

    assert len(materials) == 1
    assert materials[0].title_hint == "选题A"

    engine = create_engine("sqlite:///:memory:", future=True)
    init_database(engine)
    session_factory = create_session_factory(engine)
    session = session_factory()
    try:
        job = create_batch_job(session, "batch.csv", materials)
        session.commit()
        assert job.total_count == 1
        assert job.items[0].title_hint == "选题A"
    finally:
        session.close()


def test_parse_batch_csv_maps_zhihu_qa_aliases():
    csv_content = "标题,素材正文,目标平台\n选题A,正文A,知乎问答\n选题B,正文B,知乎Q&A\n".encode("utf-8-sig")
    materials = parse_batch_file("batch.csv", csv_content)

    assert [material.target_platforms for material in materials] == [["zhihu_qa"], ["zhihu_qa"]]


def test_process_image_creates_platform_variants(tmp_path):
    try:
        from PIL import Image
    except ImportError:
        return

    source = tmp_path / "source.jpg"
    Image.new("RGB", (1200, 800), color=(120, 160, 200)).save(source)

    variants = process_image(source, tmp_path / "out", "测试选题", ["official_account", "xiaohongshu"])

    assert variants
    assert {item["platform"] for item in variants} == {"official_account", "xiaohongshu"}
    assert all(Path(item["output_path"]).exists() for item in variants)
    assert all(item["file_size"] <= 2 * 1024 * 1024 for item in variants)
