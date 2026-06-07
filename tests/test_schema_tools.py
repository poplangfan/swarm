"""Tests for tool schema generation and validation."""

from tools.schema import generate_tool_schema, validate_tool_args


class TestGenerateToolSchema:
    def test_basic_schema(self):
        schema = generate_tool_schema(
            name="get_weather",
            description="Get weather for a city",
            properties={
                "city": {"type": "string", "description": "City name"},
                "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
            },
            required=["city"],
        )
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "get_weather"
        assert "city" in schema["function"]["parameters"]["properties"]
        assert schema["function"]["parameters"]["required"] == ["city"]

    def test_no_required(self):
        schema = generate_tool_schema(
            name="list_items",
            description="List items",
            properties={
                "limit": {"type": "integer", "description": "Max items"},
            },
        )
        assert "required" not in schema["function"]["parameters"]

    def test_auto_adds_type(self):
        schema = generate_tool_schema(
            name="test",
            description="Test",
            properties={
                "name": {"description": "Name without type"},
            },
        )
        prop = schema["function"]["parameters"]["properties"]["name"]
        assert prop["type"] == "string"  # Auto-added default


class TestValidateToolArgs:
    def test_valid_args(self):
        schema = generate_tool_schema(
            name="add",
            description="Add numbers",
            properties={
                "a": {"type": "integer", "description": "First number"},
                "b": {"type": "integer", "description": "Second number"},
            },
            required=["a", "b"],
        )
        errors = validate_tool_args({"a": 1, "b": 2}, schema)
        assert len(errors) == 0

    def test_missing_required(self):
        schema = generate_tool_schema(
            name="search",
            description="Search",
            properties={"query": {"type": "string"}},
            required=["query"],
        )
        errors = validate_tool_args({}, schema)
        assert len(errors) == 1
        assert "Missing" in errors[0]
        assert "query" in errors[0]

    def test_wrong_type(self):
        schema = generate_tool_schema(
            name="set_count",
            description="Set count",
            properties={"count": {"type": "integer"}},
            required=["count"],
        )
        errors = validate_tool_args({"count": "not_a_number"}, schema)
        assert len(errors) == 1
        assert "integer" in errors[0]

    def test_extra_args_ok(self):
        schema = generate_tool_schema(
            name="greet",
            description="Greet",
            properties={"name": {"type": "string"}},
            required=["name"],
        )
        errors = validate_tool_args({"name": "Alice", "extra": "ignored"}, schema)
        assert len(errors) == 0  # Extra args are fine

    def test_empty_args(self):
        schema = generate_tool_schema(
            name="ping",
            description="Ping",
            properties={},
        )
        errors = validate_tool_args({}, schema)
        assert len(errors) == 0
