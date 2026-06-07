"""Tests for config system."""

import pytest
from pydantic import ValidationError
from config.schema import LLMConfig, FeishuConfig, SwarmConfig
from config.loader import _resolve_env_vars, load_config


class TestLLMConfig:
    def test_defaults(self):
        cfg = LLMConfig(api_key="sk-test")
        assert cfg.provider == "anthropic"
        assert cfg.model == "deepseek-v4-pro"
        assert cfg.max_tokens == 4096

    def test_validation_fails_on_invalid_provider(self):
        with pytest.raises(ValidationError):
            LLMConfig(api_key="x", provider="invalid")


class TestFeishuConfig:
    def test_valid_domains(self):
        cfg = FeishuConfig(app_id="x", app_secret="y", domain="feishu")
        assert cfg.domain == "feishu"
        cfg2 = FeishuConfig(app_id="x", app_secret="y", domain="lark")
        assert cfg2.domain == "lark"

    def test_invalid_domain_fails(self):
        with pytest.raises(ValidationError):
            FeishuConfig(app_id="x", app_secret="y", domain="not_a_domain")


class TestEnvVarResolution:
    def test_resolves_simple_var(self):
        import os
        os.environ["TEST_VAR"] = "resolved_value"
        result = _resolve_env_vars({"key": "${TEST_VAR}"})
        assert result["key"] == "resolved_value"

    def test_resolves_with_default(self):
        result = _resolve_env_vars({"key": "${MISSING_VAR:-default_val}"})
        assert result["key"] == "default_val"

    def test_recursive_resolution(self):
        import os
        os.environ["NESTED"] = "inner"
        result = _resolve_env_vars({"a": {"b": "${NESTED}"}})
        assert result["a"]["b"] == "inner"


class TestConfigLoad:
    def test_load_from_dict(self):
        data = {
            "llm": {"api_key": "sk-test", "base_url": "https://api.openai.com/v1"},
            "feishu": {"app_id": "x", "app_secret": "y"},
        }
        cfg = SwarmConfig.model_validate(data)
        assert cfg.llm.api_key == "sk-test"
        assert cfg.feishu.app_id == "x"
