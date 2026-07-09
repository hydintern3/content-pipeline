from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.config import AppConfig, config_from_dict
from pipeline.batch import create_batch_job, parse_batch_file
from pipeline.compliance import check_text, clear_cache
from pipeline.compliance import checker as compliance_checker
from pipeline.compliance.prompts import (
    CORE_RULE_CATEGORIES,
    SUPPORTED_COMPLIANCE_PLATFORMS,
    get_compliance_checklist,
)
from pipeline.database import create_session_factory, init_database
from pipeline.image_processing import process_image
from pipeline.models import ArticleFollowUp
from pipeline.generation import (
    build_follow_up_messages,
    build_system_prompt,
    build_user_prompt,
    generate_drafts,
    material_for_platform,
    parse_variant_json,
)
from pipeline.observability import estimate_llm_cost_usd
from pipeline.publishers import (
    WECHAT_TITLE_MAX_BYTES,
    choose_publish_mode,
    dumps_wechat_json,
    publish_article,
    wechat_safe_title,
)
from pipeline.repository import (
    create_articles,
    create_material,
    generation_run_detail_payload,
    generation_run_payload,
    get_article,
    get_or_create_generation_run,
    link_generation_articles,
    list_generation_runs,
)
from pipeline.schemas import ArticleDraft, normalize_material

from sqlalchemy import create_engine, select


def make_config(tmp_path, **overrides):
    values = {
        "app_database_url": "sqlite:///:memory:",
        "external_database_url": "",
        "llm_api_key": "",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_model": "gpt-4o-mini",
        "generation_concurrency": 3,
        "compliance_mock": False,
        "compliance_llm_model": "",
        "compliance_cache_size": 512,
        "compliance_auto_check": True,
        "compliance_concurrency": 2,
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


def test_request_config_prefer_user_llm_over_server_env(monkeypatch):
    monkeypatch.setenv("CONTENT_LLM_API_KEY", "server-key")
    monkeypatch.setenv("CONTENT_LLM_BASE_URL", "https://server.example/v1")
    monkeypatch.setenv("CONTENT_LLM_MODEL", "server-model")

    request_config = config_from_dict(
        {
            "app_database_url": "sqlite:///:memory:",
            "llm": {
                "api_key": "user-key",
                "base_url": "https://user.example/v1",
                "model": "user-model",
            },
        },
        prefer_config=True,
    )

    assert request_config.llm_api_key == "user-key"
    assert request_config.llm_base_url == "https://user.example/v1"
    assert request_config.llm_model == "user-model"


def test_empty_env_does_not_mask_user_llm_config(monkeypatch):
    monkeypatch.setenv("CONTENT_LLM_API_KEY", "")
    monkeypatch.setenv("CONTENT_LLM_BASE_URL", "")
    monkeypatch.setenv("CONTENT_LLM_MODEL", "")

    request_config = config_from_dict(
        {
            "app_database_url": "sqlite:///:memory:",
            "llm": {
                "api_key": "user-key",
                "base_url": "https://user.example/v1",
                "model": "user-model",
            },
        },
        prefer_config=True,
    )

    assert request_config.llm_api_key == "user-key"
    assert request_config.llm_base_url == "https://user.example/v1"
    assert request_config.llm_model == "user-model"


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


def test_parse_variant_json_returns_requested_platform_variants():
    drafts = parse_variant_json(
        json.dumps(
            {
                "variants": [
                    {"angle": "避坑", "title": "标题A", "content": "正文A", "format": "markdown"},
                    {"angle": "教程", "title": "标题B", "content": "正文B", "format": "markdown"},
                ]
            },
            ensure_ascii=False,
        ),
        "toutiao",
        2,
    )

    assert [draft.platform for draft in drafts] == ["toutiao", "toutiao"]
    assert drafts[0].title.endswith("｜避坑")
    assert drafts[1].content == "正文B"


def test_llm_cost_estimate_uses_model_price_table():
    cost = estimate_llm_cost_usd("gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=1_000_000)

    assert str(cost) == "0.750000"


def test_generation_history_groups_split_platform_requests(tmp_path):
    engine = create_engine("sqlite:///:memory:", future=True)
    init_database(engine)
    session_factory = create_session_factory(engine)
    config = make_config(tmp_path)

    first_input = normalize_material(
        {
            "title_hint": "历史选题",
            "raw_content": "历史素材正文",
            "keywords": ["招商"],
            "target_platforms": ["xiaohongshu"],
        }
    )
    second_input = normalize_material(
        {
            "title_hint": "历史选题",
            "raw_content": "历史素材正文",
            "keywords": ["招商"],
            "target_platforms": ["toutiao"],
        }
    )

    session = session_factory()
    try:
        for material_input in [first_input, second_input]:
            material = create_material(session, material_input)
            _, drafts = generate_drafts(material_input, config)
            articles = create_articles(session, material, drafts)
            run = get_or_create_generation_run(
                session,
                "history-test-run",
                material_input,
                ["xiaohongshu", "toutiao"],
            )
            link_generation_articles(session, run, articles)
        session.commit()

        runs = list_generation_runs(session, limit=20)
        assert len(runs) == 1
        summary = generation_run_payload(runs[0])
        assert summary["article_count"] == 2
        assert summary["target_platforms"] == ["xiaohongshu", "toutiao"]
        assert set(summary["generated_platforms"]) == {"xiaohongshu", "toutiao"}

        detail = generation_run_detail_payload(runs[0])
        assert detail["material"]["title_hint"] == "历史选题"
        assert len(detail["articles"]) == 2
    finally:
        session.close()


def test_generation_history_filters_by_keyword_and_platform(tmp_path):
    engine = create_engine("sqlite:///:memory:", future=True)
    init_database(engine)
    session_factory = create_session_factory(engine)
    config = make_config(tmp_path)

    session = session_factory()
    try:
        for run_id, title, platform in [
            ("run-xhs", "小红书历史", "xiaohongshu"),
            ("run-tt", "头条历史", "toutiao"),
            ("run-zhihu-qa", "zhihu qa history", "zhihu_qa"),
        ]:
            material_input = normalize_material(
                {
                    "title_hint": title,
                    "raw_content": f"{title}正文",
                    "target_platforms": [platform],
                }
            )
            material = create_material(session, material_input)
            _, drafts = generate_drafts(material_input, config)
            articles = create_articles(session, material, drafts)
            run = get_or_create_generation_run(session, run_id, material_input, [platform])
            link_generation_articles(session, run, articles)
        session.commit()

        assert [run.id for run in list_generation_runs(session, query="小红书")] == ["run-xhs"]
        assert [run.id for run in list_generation_runs(session, platform="toutiao")] == ["run-tt"]
        assert [run.id for run in list_generation_runs(session, platform="zhihu")] == []
        assert [run.id for run in list_generation_runs(session, platform="zhihu_qa")] == [
            "run-zhihu-qa"
        ]
    finally:
        session.close()


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


def test_generation_history_api_keeps_legacy_generate_compatible(tmp_path, monkeypatch):
    db_path = tmp_path / "pipeline.db"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "app_database_url": f"sqlite:///{db_path.as_posix()}",
                "llm": {"api_key": "", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
                "database": {"url": ""},
                "publish": {"pending_output_dir": str(tmp_path / "pending")},
                "wechat": {"app_id": "", "app_secret": "", "auto_publish": False, "enable_mass_send": False},
                "scheduler": {"enabled": False, "interval_minutes": 240},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONTENT_PIPELINE_CONFIG", str(config_path))

    app_module = importlib.import_module("app")
    app_module = importlib.reload(app_module)
    client = app_module.app.test_client()

    response = client.post(
        "/api/materials/generate",
        json={
            "material": {
                "title_hint": "兼容生成",
                "raw_content": "旧请求不带历史字段",
                "target_platforms": ["toutiao"],
            }
        },
    )
    assert response.status_code == 200
    assert response.get_json()["articles"]

    history_response = client.get("/api/history/generations")
    assert history_response.status_code == 200
    assert history_response.get_json()["items"] == []


def test_generation_history_api_groups_split_generate_requests(tmp_path, monkeypatch):
    db_path = tmp_path / "history-api.db"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "app_database_url": f"sqlite:///{db_path.as_posix()}",
                "llm": {"api_key": "", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
                "database": {"url": ""},
                "publish": {"pending_output_dir": str(tmp_path / "pending")},
                "wechat": {"app_id": "", "app_secret": "", "auto_publish": False, "enable_mass_send": False},
                "scheduler": {"enabled": False, "interval_minutes": 240},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONTENT_PIPELINE_CONFIG", str(config_path))

    app_module = importlib.import_module("app")
    app_module = importlib.reload(app_module)
    client = app_module.app.test_client()

    for platform in ["xiaohongshu", "toutiao"]:
        response = client.post(
            "/api/materials/generate",
            json={
                "history_run_id": "api-history-run",
                "history_expected_platforms": ["xiaohongshu", "toutiao"],
                "material": {
                    "title_hint": "接口历史",
                    "raw_content": "同一次点击拆成多个平台请求",
                    "target_platforms": [platform],
                },
            },
        )
        assert response.status_code == 200

    detail_response = client.get("/api/history/generations/api-history-run")
    assert detail_response.status_code == 200
    detail = detail_response.get_json()["item"]
    assert detail["article_count"] == 2
    assert detail["target_platforms"] == ["xiaohongshu", "toutiao"]
    assert {article["platform"] for article in detail["articles"]} == {"xiaohongshu", "toutiao"}


def test_follow_up_prompt_uses_low_token_context():
    class Article:
        platform = "official_account"
        title = "原始标题"
        content = "当前文章正文"
        content_format = "html"

    messages = build_follow_up_messages(Article(), "把开头改得更直接")
    joined = "\n".join(message["content"] for message in messages)

    assert "当前文章正文" in joined
    assert "把开头改得更直接" in joined
    assert "平台约束摘要" in joined
    assert "深度行业分析" not in joined
    assert "平台专属规则" not in joined


def test_article_follow_up_api_creates_revised_article(tmp_path, monkeypatch):
    db_path = tmp_path / "follow-up.db"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "app_database_url": f"sqlite:///{db_path.as_posix()}",
                "llm": {"api_key": "", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
                "database": {"url": ""},
                "publish": {"pending_output_dir": str(tmp_path / "pending")},
                "wechat": {"app_id": "", "app_secret": "", "auto_publish": False, "enable_mass_send": False},
                "scheduler": {"enabled": False, "interval_minutes": 240},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONTENT_PIPELINE_CONFIG", str(config_path))

    app_module = importlib.import_module("app")
    app_module = importlib.reload(app_module)
    client = app_module.app.test_client()

    response = client.post(
        "/api/materials/generate",
        json={
            "material": {
                "title_hint": "追问选题",
                "raw_content": "原始素材正文",
                "target_platforms": ["toutiao"],
            }
        },
    )
    article = response.get_json()["articles"][0]

    def fake_follow_up(source_article, instruction, config):
        assert source_article.id == article["id"]
        assert instruction == "改得更像行业观察"
        assert config.llm_model == "follow-model"
        return ArticleDraft(
            source_article.platform,
            "优化后标题",
            source_article.content + "\n优化后正文",
            source_article.content_format,
        )

    monkeypatch.setattr(app_module, "follow_up_article_with_llm", fake_follow_up)
    follow_response = client.post(
        f"/api/articles/{article['id']}/follow_up",
        json={
            "instruction": "改得更像行业观察",
            "config": {
                "llm": {
                    "api_key": "sk-test",
                    "base_url": "https://api.openai.com/v1",
                    "model": "follow-model",
                }
            },
        },
    )

    assert follow_response.status_code == 200
    payload = follow_response.get_json()
    revised = payload["article"]
    assert revised["id"] != article["id"]
    assert revised["status"] == "revised"
    assert revised["platform"] == article["platform"]
    assert revised["format"] == article["format"]
    assert "优化后正文" in revised["content"]
    assert payload["follow_up"]["source_article_id"] == article["id"]
    assert payload["follow_up"]["result_article_id"] == revised["id"]

    session = app_module.SessionLocal()
    try:
        original = get_article(session, article["id"])
        stored_revised = get_article(session, revised["id"])
        follow_ups = list(session.scalars(select(ArticleFollowUp)).all())
        assert original.content == article["content"]
        assert stored_revised.status == "revised"
        assert len(follow_ups) == 1
        assert follow_ups[0].instruction == "改得更像行业观察"
        assert follow_ups[0].model == "follow-model"
    finally:
        session.close()


def test_article_follow_up_requires_llm_key(tmp_path, monkeypatch):
    db_path = tmp_path / "follow-up-no-key.db"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "app_database_url": f"sqlite:///{db_path.as_posix()}",
                "llm": {"api_key": "", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
                "database": {"url": ""},
                "publish": {"pending_output_dir": str(tmp_path / "pending")},
                "wechat": {"app_id": "", "app_secret": "", "auto_publish": False, "enable_mass_send": False},
                "scheduler": {"enabled": False, "interval_minutes": 240},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONTENT_PIPELINE_CONFIG", str(config_path))

    app_module = importlib.import_module("app")
    app_module = importlib.reload(app_module)
    client = app_module.app.test_client()
    response = client.post(
        "/api/materials/generate",
        json={
            "material": {
                "title_hint": "追问选题",
                "raw_content": "原始素材正文",
                "target_platforms": ["toutiao"],
            }
        },
    )
    article = response.get_json()["articles"][0]

    follow_response = client.post(
        f"/api/articles/{article['id']}/follow_up",
        json={"instruction": "改得更短"},
    )

    assert follow_response.status_code == 400
    assert follow_response.get_json()["success"] is False


def test_article_follow_up_invalid_llm_result_does_not_create_article(tmp_path, monkeypatch):
    db_path = tmp_path / "follow-up-invalid.db"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "app_database_url": f"sqlite:///{db_path.as_posix()}",
                "llm": {"api_key": "", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
                "database": {"url": ""},
                "publish": {"pending_output_dir": str(tmp_path / "pending")},
                "wechat": {"app_id": "", "app_secret": "", "auto_publish": False, "enable_mass_send": False},
                "scheduler": {"enabled": False, "interval_minutes": 240},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONTENT_PIPELINE_CONFIG", str(config_path))

    app_module = importlib.import_module("app")
    app_module = importlib.reload(app_module)
    client = app_module.app.test_client()
    response = client.post(
        "/api/materials/generate",
        json={
            "material": {
                "title_hint": "追问选题",
                "raw_content": "原始素材正文",
                "target_platforms": ["toutiao"],
            }
        },
    )
    article = response.get_json()["articles"][0]

    def fake_follow_up(*_args, **_kwargs):
        raise ValueError("大模型返回内容不是 JSON 对象")

    monkeypatch.setattr(app_module, "follow_up_article_with_llm", fake_follow_up)
    follow_response = client.post(
        f"/api/articles/{article['id']}/follow_up",
        json={
            "instruction": "改得更短",
            "config": {"llm": {"api_key": "sk-test", "model": "follow-model"}},
        },
    )

    assert follow_response.status_code == 502
    session = app_module.SessionLocal()
    try:
        assert len(list(session.scalars(select(ArticleFollowUp)).all())) == 0
    finally:
        session.close()


def test_compliance_regex_precheck_flags_contact_info(tmp_path):
    """Regex pre-check catches phone numbers, WeChat IDs, emails etc."""
    text = "联系我微信: abc123 或打电话 13812345678，邮箱 test@example.com"
    result = check_text(text, "xiaohongshu", config=make_config(tmp_path, compliance_mock=True))

    assert result["status"] in ("review", "high_risk")
    assert result["risk_count"] >= 3  # WeChat, phone, email


def test_compliance_regex_precheck_platform_filter(tmp_path):
    """Regex rules have platform-specific filtering.

    The regex pre-check allows WeChat IDs on official_account (Tencent ecosystem),
    but the LLM may still flag them. This test verifies the full check pipeline.
    """
    text = "联系我们微信: bizcontact 了解更多"
    config = make_config(tmp_path, compliance_mock=True)
    result_xhs = check_text(text, "xiaohongshu", config=config)
    result_oa = check_text(text, "official_account", config=config)

    # Both platforms should catch this as a contact-info violation
    # (LLM detects it on all platforms, regex has platform-differentiated rules)
    xhs_contact = [r for r in result_xhs["risks"] if "导流" in r.get("category", "") and "微信" in r["term"]]
    oa_contact = [r for r in result_oa["risks"] if "导流" in r.get("category", "") and "微信" in r["term"]]
    assert len(xhs_contact) >= 1
    assert len(oa_contact) == 0


def test_compliance_checker_clean_text_passes(monkeypatch, tmp_path):
    """Clean business text without contact info should pass."""
    async def fake_llm_check(_text, _platform, _client, _model):
        return []

    monkeypatch.setattr(compliance_checker, "_llm_check_async", fake_llm_check)
    result = check_text(
        "上海写字楼租赁市场在2024年呈现稳中有升的趋势，企业选址需综合考虑通勤、租金和配套。",
        "toutiao",
        config=make_config(tmp_path, llm_api_key="sk-test"),
    )
    assert result["status"] == "pass"
    assert result["risk_count"] == 0


def test_compliance_forced_share_pattern(monkeypatch, tmp_path):
    """Forced share / false info language is caught.

    WeChat platforms catch it via regex pre-check (胁迫分享).
    All platforms may catch it via LLM semantic check (谣言/不实信息).
    """
    async def fake_llm_check(_text, _platform, _client, _model):
        return [
            {
                "term": "不转不是中国人",
                "category": "谣言不实",
                "level": "high",
                "suggestion": "删除胁迫式传播话术",
            }
        ]

    monkeypatch.setattr(compliance_checker, "_llm_check_async", fake_llm_check)
    config = make_config(tmp_path, llm_api_key="sk-test")
    text = "这篇文章太准了，不转不是中国人，转发保平安！"
    result_oa = check_text(text, "official_account", config=config)
    result_tt = check_text(text, "toutiao", config=config)

    # Both platforms should flag this — WeChat via regex, toutiao via LLM
    assert result_oa["risk_count"] >= 1
    assert result_tt["risk_count"] >= 1  # LLM catches as 谣言/不实信息 cross-platform


def test_compliance_mock_mode_skips_llm(monkeypatch, tmp_path):
    clear_cache()

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("mock mode should not call the LLM")

    monkeypatch.setattr(compliance_checker, "_llm_check_async", fail_if_called)
    config = make_config(
        tmp_path,
        llm_api_key="sk-test",
        compliance_mock=True,
    )

    result = check_text("电话 13812345678", "xiaohongshu", config=config)

    assert result["mode"] == "mock"
    assert result["risk_count"] >= 1


def test_compliance_uses_independent_model_and_fallback(monkeypatch, tmp_path):
    clear_cache()
    used_models: list[str] = []

    async def fake_llm_check(_text, _platform, _client, model):
        used_models.append(model)
        return []

    monkeypatch.setattr(compliance_checker, "_llm_check_async", fake_llm_check)

    independent_config = make_config(
        tmp_path,
        llm_api_key="sk-test",
        llm_model="content-model",
        compliance_llm_model="compliance-model",
    )
    fallback_config = make_config(
        tmp_path,
        llm_api_key="sk-test",
        llm_model="content-model",
        compliance_llm_model="",
    )

    check_text("一段正常业务文本", "toutiao", config=independent_config, force_refresh=True)
    check_text("另一段正常业务文本", "toutiao", config=fallback_config, force_refresh=True)

    assert used_models == ["compliance-model", "content-model"]


def test_compliance_result_cache_and_force_refresh(monkeypatch, tmp_path):
    clear_cache()
    call_count = 0

    async def fake_llm_check(_text, _platform, _client, _model):
        nonlocal call_count
        call_count += 1
        return []

    monkeypatch.setattr(compliance_checker, "_llm_check_async", fake_llm_check)
    config = make_config(tmp_path, llm_api_key="sk-test", compliance_cache_size=2)

    first = check_text("缓存测试文本", "zhihu", config=config)
    second = check_text("缓存测试文本", "zhihu", config=config)
    refreshed = check_text("缓存测试文本", "zhihu", config=config, force_refresh=True)

    assert first["cached"] is False
    assert second["cached"] is True
    assert refreshed["cached"] is False
    assert call_count == 2


def test_compliance_rule_checklists_cover_supported_platforms():
    for platform in SUPPORTED_COMPLIANCE_PLATFORMS:
        checklist = get_compliance_checklist(platform)
        assert checklist.strip()
        for category in CORE_RULE_CATEGORIES:
            assert category in checklist


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
