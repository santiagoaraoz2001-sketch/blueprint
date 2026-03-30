"""Exhaustive tests for all 9 agent blocks.

Already tested in test_real_workload.py: chain_of_thought, agent_orchestrator, multi_agent_debate
New coverage: agent_evaluator, agent_memory, agent_text_bridge, code_agent, retrieval_agent, tool_registry
"""

from __future__ import annotations
import pytest

pytestmark = pytest.mark.slow

from .block_test_helpers import (
    node, edge, text_input_node, text_to_dataset_node, metrics_input_node,
    model_selector_node, inference_node, cot_node,
    create_pipeline, validate, validate_config,
    create_and_run, assert_run_complete, assert_replay_nodes,
)


# ═══════════════════════════════════════════════════════════════════════
#  AGENT_TEXT_BRIDGE
# ═══════════════════════════════════════════════════════════════════════

class TestAgentTextBridge:
    def test_standalone(self, live_backend):
        nodes = [
            text_input_node("ti", '{"final_answer": "hello world", "steps": [1,2,3]}'),
            node("atb", "agent_text_bridge"),
        ]
        edges = [edge("ti", "atb", "text", "agent")]
        pid, run = create_and_run("agent:atb:basic", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_custom_extract_field(self, live_backend):
        nodes = [
            text_input_node("ti", '{"result": "success", "data": {"value": 42}}'),
            node("atb", "agent_text_bridge", {"extract_field": "result"}),
        ]
        edges = [edge("ti", "atb", "text", "agent")]
        pid, run = create_and_run("agent:atb:field", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_plain_text_input(self, live_backend):
        nodes = [
            text_input_node("ti", "This is plain text, not JSON"),
            node("atb", "agent_text_bridge"),
        ]
        edges = [edge("ti", "atb", "text", "agent")]
        pid, run = create_and_run("agent:atb:plain", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_max_length(self, live_backend):
        nodes = [
            text_input_node("ti", '{"final_answer": "' + "x" * 500 + '"}'),
            node("atb", "agent_text_bridge", {"max_length": 50}),
        ]
        edges = [edge("ti", "atb", "text", "agent")]
        pid, run = create_and_run("agent:atb:maxlen", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_empty_json(self, live_backend):
        nodes = [
            text_input_node("ti", "{}"),
            node("atb", "agent_text_bridge"),
        ]
        edges = [edge("ti", "atb", "text", "agent")]
        pid, run = create_and_run("agent:atb:empty", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  AGENT_MEMORY
# ═══════════════════════════════════════════════════════════════════════

class TestAgentMemory:
    def test_store_action(self, live_backend):
        nodes = [
            text_input_node("ti", "Remember this: AI is transformative"),
            node("am", "agent_memory", {"action": "store", "memory_key": "fact1"}),
        ]
        edges = [edge("ti", "am", "text", "input")]
        pid, run = create_and_run("agent:am:store", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_list_action(self, live_backend):
        nodes = [node("am", "agent_memory", {"action": "list"})]
        pid, run = create_and_run("agent:am:list", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_clear_action(self, live_backend):
        nodes = [node("am", "agent_memory", {"action": "clear"})]
        pid, run = create_and_run("agent:am:clear", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_store_with_tags(self, live_backend):
        nodes = [
            text_input_node("ti", "Important fact about ML"),
            node("am", "agent_memory", {"action": "store", "memory_key": "ml_fact", "tags": "ml,important"}),
        ]
        edges = [edge("ti", "am", "text", "input")]
        pid, run = create_and_run("agent:am:tags", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_retrieve_action(self, live_backend):
        nodes = [node("am", "agent_memory", {"action": "retrieve", "memory_key": "nonexistent"})]
        pid, run = create_and_run("agent:am:retrieve", nodes, [], stderr_path=live_backend.stderr_path)
        # Should complete even if key doesn't exist
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  TOOL_REGISTRY
# ═══════════════════════════════════════════════════════════════════════

class TestToolRegistry:
    def test_defaults(self, live_backend):
        nodes = [node("tr", "tool_registry", {"include_defaults": True})]
        pid, run = create_and_run("agent:tr:defaults", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_custom_tools(self, live_backend):
        nodes = [node("tr", "tool_registry", {
            "custom_tools": '[{"name": "search", "description": "Search the web", "parameters": {}}]',
        })]
        pid, run = create_and_run("agent:tr:custom", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_no_defaults(self, live_backend):
        nodes = [node("tr", "tool_registry", {"include_defaults": False})]
        pid, run = create_and_run("agent:tr:nodef", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_anthropic_format(self, live_backend):
        nodes = [node("tr", "tool_registry", {"output_format": "anthropic", "include_defaults": True})]
        pid, run = create_and_run("agent:tr:anthro", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  AGENT_EVALUATOR
# ═══════════════════════════════════════════════════════════════════════

class TestAgentEvaluator:
    def test_standalone(self, live_backend):
        nodes = [node("ae", "agent_evaluator")]
        pid, run = create_and_run("agent:ae:basic", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_with_dataset(self, live_backend):
        nodes = [
            text_input_node("ti", "Q: What is 2+2?\nA: 4\nQ: What is 3+3?\nA: 6"),
            text_to_dataset_node("ttd", split_by="newline"),
            node("ae", "agent_evaluator"),
        ]
        edges = [edge("ti", "ttd", "text", "text"), edge("ttd", "ae", "dataset", "dataset")]
        pid, run = create_and_run("agent:ae:dataset", nodes, edges, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_accuracy_method(self, live_backend):
        nodes = [node("ae", "agent_evaluator", {"method": "accuracy"})]
        pid, run = create_and_run("agent:ae:accuracy", nodes, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  CODE_AGENT (needs Ollama)
# ═══════════════════════════════════════════════════════════════════════

class TestCodeAgent:
    def test_python(self, ollama_model, live_backend):
        nodes = [
            model_selector_node("ms", ollama_model),
            text_input_node("ti", "Write a Python function that adds two numbers."),
            node("ca", "code_agent", {"language": "python", "max_tokens": 200, "execute": False}),
        ]
        edges = [edge("ms", "ca", "llm", "llm"), edge("ti", "ca", "text", "input")]
        pid, run = create_and_run("agent:ca:py", nodes, edges,
                                  timeout=120, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_no_execute(self, ollama_model, live_backend):
        nodes = [
            model_selector_node("ms", ollama_model),
            text_input_node("ti", "Print hello world"),
            node("ca", "code_agent", {"language": "python", "execute": False, "max_tokens": 100}),
        ]
        edges = [edge("ms", "ca", "llm", "llm"), edge("ti", "ca", "text", "input")]
        pid, run = create_and_run("agent:ca:noexec", nodes, edges,
                                  timeout=120, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_javascript(self, ollama_model, live_backend):
        nodes = [
            model_selector_node("ms", ollama_model),
            text_input_node("ti", "Write a function to reverse a string in JavaScript."),
            node("ca", "code_agent", {"language": "javascript", "execute": False, "max_tokens": 150}),
        ]
        edges = [edge("ms", "ca", "llm", "llm"), edge("ti", "ca", "text", "input")]
        pid, run = create_and_run("agent:ca:js", nodes, edges,
                                  timeout=120, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)


# ═══════════════════════════════════════════════════════════════════════
#  RETRIEVAL_AGENT (validation only — needs vector store)
# ═══════════════════════════════════════════════════════════════════════

class TestRetrievalAgent:
    def test_validate_config(self, live_backend):
        s, d = validate_config("retrieval_agent", {"top_k": 5, "search_type": "similarity"})
        assert s == 200

    def test_validate_pipeline(self, ollama_model, live_backend):
        nodes = [
            model_selector_node("ms", ollama_model),
            text_input_node("ti", "test query"),
            node("ra", "retrieval_agent", {"top_k": 3}),
        ]
        edges = [edge("ms", "ra", "llm", "llm"), edge("ti", "ra", "text", "input")]
        pid = create_pipeline("agent:ra:val", nodes, edges)
        val = validate(pid)
        assert val["block_count"] == 3


# ═══════════════════════════════════════════════════════════════════════
#  AGENT E2E WORKFLOWS
# ═══════════════════════════════════════════════════════════════════════

class TestAgentWorkflows:
    def test_cot_to_text_bridge(self, ollama_model, live_backend):
        """ms + ti → chain_of_thought → agent_text_bridge"""
        nodes = [
            model_selector_node("ms", ollama_model),
            text_input_node("ti", "What is 5 + 7?"),
            cot_node("cot", num_steps=2, max_tokens=150),
            node("atb", "agent_text_bridge"),
        ]
        edges = [
            edge("ms", "cot", "llm", "llm"),
            edge("ti", "cot", "text", "input"),
            edge("cot", "atb", "response", "agent"),
        ]
        pid, run = create_and_run("wf:agent:cot-bridge", nodes, edges,
                                  timeout=180, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_code_agent_then_parse(self, ollama_model, live_backend):
        """ms + ti → code_agent → response_parser"""
        nodes = [
            model_selector_node("ms", ollama_model),
            text_input_node("ti", "Write a hello world function in Python."),
            node("ca", "code_agent", {"language": "python", "execute": False, "max_tokens": 150}),
            node("rp", "response_parser", {"format": "regex", "regex_pattern": "def\\s+\\w+"}),
        ]
        edges = [
            edge("ms", "ca", "llm", "llm"),
            edge("ti", "ca", "text", "input"),
            edge("ca", "rp", "response", "text"),
        ]
        pid, run = create_and_run("wf:agent:code-parse", nodes, edges,
                                  timeout=120, stderr_path=live_backend.stderr_path)
        assert_run_complete(run)

    def test_memory_store_and_list(self, live_backend):
        """ti → agent_memory(store) then agent_memory(list)"""
        # First: store
        nodes1 = [
            text_input_node("ti", "AI is the future"),
            node("am", "agent_memory", {"action": "store", "memory_key": "wf_test"}),
        ]
        edges1 = [edge("ti", "am", "text", "input")]
        pid1, run1 = create_and_run("wf:agent:mem-store", nodes1, edges1, stderr_path=live_backend.stderr_path)
        assert_run_complete(run1)

        # Second: list
        nodes2 = [node("am", "agent_memory", {"action": "list"})]
        pid2, run2 = create_and_run("wf:agent:mem-list", nodes2, [], stderr_path=live_backend.stderr_path)
        assert_run_complete(run2)
