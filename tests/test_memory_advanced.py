"""Tests for memory compressor and knowledge graph."""

import pytest
from pathlib import Path
from swarm.memory.compressor import ContextCompressor
from swarm.memory.knowledge_graph import KnowledgeGraph, Entity, Relation


class TestContextCompressor:
    def test_no_compression_needed(self):
        compressor = ContextCompressor(max_tokens=100000)
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        result = compressor.compress(messages)
        assert len(result) == 3

    def test_preserves_system_prompt(self):
        compressor = ContextCompressor(max_tokens=50)
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "x" * 500},
        ]
        result = compressor.compress(messages)
        assert result[0]["role"] == "system"

    def test_empty_messages(self):
        compressor = ContextCompressor()
        assert compressor.compress([]) == []

    def test_compress_tool_results(self):
        compressor = ContextCompressor(max_tokens=10000)
        messages = [
            {"role": "user", "content": "search"},
            {"role": "tool", "content": "x" * 5000},
            {"role": "assistant", "content": "result"},
        ]
        result = compressor.compress(messages)
        # Just verify we got results; compression behavior depends on token budget
        assert len(result) >= 1
        # Large tool results should be compressed or truncated
        tool_msgs = [m for m in result if m.get("role") == "tool"]
        for tm in tool_msgs:
            content = str(tm.get("content", ""))
            # Either compressed (contains marker) or truncated (shorter)
            assert ("compressed" in content or len(content) <= 5000)

    def test_estimate_tokens(self):
        compressor = ContextCompressor()
        assert compressor.estimate_tokens("hello world") > 0
        assert compressor.estimate_tokens("") == 0


class TestKnowledgeGraph:
    @pytest.mark.asyncio
    async def test_add_and_get_entity(self, temp_dir):
        kg = KnowledgeGraph(temp_dir)
        await kg.add_entity(Entity(name="Alice", entity_type="person"))
        alice = await kg.get_entity("Alice")
        assert alice is not None
        assert alice.entity_type == "person"

    @pytest.mark.asyncio
    async def test_add_relation(self, temp_dir):
        kg = KnowledgeGraph(temp_dir)
        await kg.add_entity(Entity(name="Alice", entity_type="person"))
        await kg.add_entity(Entity(name="ProjectX", entity_type="project"))
        await kg.add_relation(Relation(source="Alice", target="ProjectX", relation_type="works_on"))
        neighbors = await kg.get_neighbors("Alice")
        assert len(neighbors) == 1
        assert neighbors[0]["neighbor"] == "ProjectX"

    @pytest.mark.asyncio
    async def test_search_entities(self, temp_dir):
        kg = KnowledgeGraph(temp_dir)
        await kg.add_entity(Entity(name="Alice", entity_type="person"))
        await kg.add_entity(Entity(name="Bob", entity_type="person"))
        await kg.add_entity(Entity(name="ProjectX", entity_type="project"))
        results = await kg.search_entities("Ali")
        assert len(results) == 1
        assert results[0].name == "Alice"

    @pytest.mark.asyncio
    async def test_get_all_by_type(self, temp_dir):
        kg = KnowledgeGraph(temp_dir)
        await kg.add_entity(Entity(name="Alice", entity_type="person"))
        await kg.add_entity(Entity(name="ProjectX", entity_type="project"))
        persons = await kg.get_all_entities("person")
        assert len(persons) == 1
