"""
LangGraph Workflow for MACROmini

Orchestrates parallel execution of specialist agents with intelligent routing,
result aggregation, streaming support, and caching.
"""

from typing import Dict, Any, List, Optional, Iterator
from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama
import time
import hashlib
import json
from functools import lru_cache

from src.orchestration.state import ReviewState, create_initial_state
from src.orchestration.router import detect_file_type, determine_agents_to_invoke
from src.orchestration.aggregator import aggregate_review_results
from src.agents.security_agent import SecurityAgent
from src.agents.quality_agent import QualityAgent
from src.agents.performance_agent import PerformanceAgent
from src.agents.testing_agent import TestingAgent
from src.agents.documentation_agent import DocumentationAgent
from src.agents.style_agent import StyleAgent

AGENT_TIMEOUT = 30
CACHE_ENABLED = True
CACHE_MAX_SIZE = 128


def _generate_cache_key(file_path: str, code: str, diff: str, agent_name: str) -> str:
    """
    Generate a unique cache key for agent analysis results.
    
    Cache key is based on: file_path + code + diff + agent_name
    Uses SHA256 hash for consistent, short keys.
    """
    content = f"{file_path}||{code}||{diff}||{agent_name}"
    return hashlib.sha256(content.encode()).hexdigest()

#LRU cache decorator
@lru_cache(maxsize=CACHE_MAX_SIZE)
def _get_cached_result(cache_key: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached agent result.
    This returns None if not in cache as LRU evicts oldest entries.
    """
    # LRU cache handles this automatically
    return None  # Placeholder, actual caching happens via decorator

def _cache_result(cache_key: str, result: Dict[str, Any]) -> None:
    """
    Cache agent result.
    """
    # Store in our custom cache decorator
    _get_cached_result.__wrapped__.__setitem__(cache_key, result)


def router_node(state: ReviewState) -> Dict[str, Any]:
    """
    Router node that determines which agents should analyze the file.
    """
    file_path = state["file_path"]
    file_type = state.get("file_type", detect_file_type(file_path))
    
    agents_to_invoke = determine_agents_to_invoke(file_path, file_type)
    
    return {
        "file_type": file_type,
        "agents_to_invoke": agents_to_invoke,
    }


def create_agent_node(agent, agent_name: str, timeout: int = AGENT_TIMEOUT):
    """
    Factory function to create agent node with timeout and caching.
    This function erturns a Node function which is langgraph-compatible
    """
    def agent_node(state: ReviewState) -> Dict[str, Any]:
        """
        Agent node with timeout, caching, and error handling.
        """
        if CACHE_ENABLED:
            cache_key = _generate_cache_key(
                state["file_path"],
                state["code"],
                state.get("diff", ""),
                agent_name
            )
            
            cached = _get_cached_result(cache_key)
            if cached is not None:
                print(f"[CACHE HIT] {agent_name} - using cached result")
                return cached
        
        start_time = time.time()
        
        try:
            result = agent.analyze(state)
            
            execution_time = time.time() - start_time
            
            if execution_time > timeout:
                print(f"[WARNING] {agent_name} exceeded timeout ({execution_time:.2f}s > {timeout}s)")
            
            if CACHE_ENABLED:
                _cache_result(cache_key, result)
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            error_result = {
                f"{agent_name}_issues": [],
                "agent_errors": {
                    agent_name: f"Timeout or error after {execution_time:.2f}s: {str(e)}"
                }
            }
            return error_result
    
    return agent_node

def aggregator_node(state: ReviewState) -> Dict[str, Any]:
    """
    Aggregator node that combines results from all agents.
    """

    return aggregate_review_results(state)


def should_run_agent(agent_name: str):
    """
    Create conditional edge function for agent routing.
    
    Returns a function that checks if agent should run based on
    the agents_to_invoke list in state.
    LangGraph only the state argument.
    Hence we cannot bake the agent name directly into the check function.
    """
    def check(state: ReviewState) -> bool:
        agents = state.get("agents_to_invoke", [])
        return agent_name in agents
    
    return check


def create_review_graph(llm: ChatOllama) -> StateGraph:
    """
    Create the multi-agent review workflow graph.
    
    Graph structure:
    1. START → router (determine which agents to invoke)
    2. router → conditional routing to agents (parallel execution)
    3. All agents → aggregator (combine and deduplicate)
    4. aggregator → END
    
    Args:
        llm: Language model instance for agents
        
    Returns:
        Compiled LangGraph workflow
    """

    #initialize agents
    security_agent = SecurityAgent(llm)
    quality_agent = QualityAgent(llm)
    performance_agent = PerformanceAgent(llm)
    testing_agent = TestingAgent(llm)
    documentation_agent = DocumentationAgent(llm)
    style_agent = StyleAgent(llm)
    
    #workflow graph object
    workflow = StateGraph(ReviewState)
    
    #router node
    workflow.add_node("router", router_node)
    
    #agent nodes
    workflow.add_node("security", create_agent_node(security_agent, "security"))
    workflow.add_node("quality", create_agent_node(quality_agent, "quality"))
    workflow.add_node("performance", create_agent_node(performance_agent, "performance"))
    workflow.add_node("testing", create_agent_node(testing_agent, "testing"))
    workflow.add_node("documentation", create_agent_node(documentation_agent, "documentation"))
    workflow.add_node("style", create_agent_node(style_agent, "style"))
    
    #aggregator node
    workflow.add_node("aggregator", aggregator_node)
    
    #entry point
    workflow.set_entry_point("router")
    
    #conditional edges from router to agents
    workflow.add_conditional_edges(
        "router",
        lambda state: state.get("agents_to_invoke", []),
        {
            #map of agent name: node name
            "security": "security",
            "quality": "quality",
            "performance": "performance",
            "testing": "testing",
            "documentation": "documentation",
            "style": "style",
        }
    )
    
    #edges from all agents to aggregator
    for agent_name in ["security", "quality", "performance", "testing", "documentation", "style"]:
        workflow.add_edge(agent_name, "aggregator")
    
    workflow.add_edge("aggregator", END)
    
    return workflow.compile()

#Prefer stream_multi_agent_review, but I have created one just in case
#This can be used to run CI/CD pipeline code as streaming output isn't necessary
def run_multi_agent_review(
    file_path: str,
    code: str,
    diff: str,
    llm: ChatOllama,
    change_type: str = "modified"
) -> ReviewState:
    """
    Run multi-agent code review on a file.
    """

    file_type = detect_file_type(file_path)
    initial_state = create_initial_state(
        file_path=file_path,
        file_type=file_type,
        code=code,
        diff=diff,
        change_type=change_type
    )
    
    # Create and run workflow
    graph = create_review_graph(llm)
    final_state = graph.invoke(initial_state)
    
    return final_state


def stream_multi_agent_review(
    file_path: str,
    code: str,
    diff: str,
    llm: ChatOllama,
    change_type: str = "modified"
) -> Iterator[Dict[str, Any]]:
    """
    Stream multi-agent code review results as agents complete.
    
    Yields state updates as each agent finishes, allowing for
    progressive display of results.
    """
    # Create initial state
    file_type = detect_file_type(file_path)
    initial_state = create_initial_state(
        file_path=file_path,
        file_type=file_type,
        code=code,
        diff=diff,
        change_type=change_type
    )
    
    # Create workflow
    graph = create_review_graph(llm)
    
    # Stream results
    for output in graph.stream(initial_state):
        yield output


def clear_cache():
    """
    Clear the agent result cache.
    Useful for testing or while forcing re-analysis.
    """
    _get_cached_result.cache_clear()
    print(f"[CACHE] Cleared {CACHE_MAX_SIZE}-entry LRU cache")


def get_cache_info():
    """
    Get cache statistics.
    
    Returns:
        CacheInfo(hits, misses, maxsize, currsize)
    """
    return _get_cached_result.cache_info()