"""Tests for CLI commands and interactive chat."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from swarm.providers.base import LLMResponse


class TestCLICommands:
    """Test that CLI commands work correctly (no real terminal needed)."""

    def test_version_command(self):
        from typer.testing import CliRunner
        from swarm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "Swarm" in result.stdout

    def test_init_command(self):
        import tempfile, os
        from typer.testing import CliRunner
        from swarm.cli.main import app
        # Use a temp directory so we don't overwrite the real config
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                runner = CliRunner()
                result = runner.invoke(app, ["init"], input="n\n")  # Answer no to overwrite
                # Should succeed (either creates or asks to overwrite)
                assert result.exit_code == 0
            finally:
                os.chdir(old_cwd)

    def test_validate_bad_config(self):
        from typer.testing import CliRunner
        from swarm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["validate", "--config", "/nonexistent/config.yaml"])
        assert result.exit_code != 0


class TestInteractiveChat:
    """Test the InteractiveChat class (no terminal)."""

    def test_chat_initialization(self, mock_provider):
        from swarm.cli.chat import InteractiveChat
        chat = InteractiveChat(provider=mock_provider, session_name="test")
        assert chat.session_name == "test"
        assert chat.provider is mock_provider

    def test_loop_created(self, mock_provider):
        from swarm.cli.chat import InteractiveChat
        chat = InteractiveChat(provider=mock_provider, session_name="test")
        assert chat.loop is not None
        assert chat.loop.provider is mock_provider


class TestStreamRenderer:
    """Test the terminal streaming renderer."""

    def test_basic_render(self):
        from swarm.cli.stream import StreamRenderer
        renderer = StreamRenderer()
        # Test outside Live context
        renderer.add("Hello")
        renderer.add(" world")
        assert "Hello world" in renderer._buffer

    def test_finalize_returns_content(self):
        from swarm.cli.stream import StreamRenderer
        renderer = StreamRenderer()
        renderer._buffer = "Test content"
        result = renderer.finalize()
        assert result == "Test content"


class TestSwarmWS:
    """Test the ws command configuration validation."""

    def test_missing_config_shows_error(self):
        from typer.testing import CliRunner
        from swarm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["ws", "--config", "/nonexistent/config.yaml"])
        # Should exit with error
        assert result.exit_code != 0

    def test_validate_with_bad_config(self):
        from typer.testing import CliRunner
        from swarm.cli.main import app
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: [")
            bad_path = f.name
        try:
            runner = CliRunner()
            result = runner.invoke(app, ["validate", "--config", bad_path])
            assert result.exit_code != 0
        finally:
            os.unlink(bad_path)
