"""
LangGraph Orchestration for MACROmini

Defines the multi-agent workflow graph:
1. Router Node - Selects which agents to invoke based on file type
2. Agent Nodes - Up to 5 specialist agents run in parallel:
   - Security: Always runs for all files
   - Quality: Runs for code files
   - Performance: Runs for code files
   - Style: Runs for documentation/config/web files
   - Testing: Runs for test files
3. Aggregator Node - Combines results and calculates verdict

The graph supports streaming for real-time progress updates.
"""

from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END

from orchestration.state import ReviewState
from orchestration.router import detect_file_type, determine_agents_to_invoke
from orchestration.aggregator import aggregate_review_results
from agents.security_agent import SecurityAgent
from agents.quality_agent import QualityAgent
from agents.performance_agent import PerformanceAgent
from agents.style_agent import StyleAgent
from agents.testing_agent import TestingAgent


def router_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Router node: Determines which agents should analyze the file.
    
    Args:
        state: Current ReviewState
        
    Returns:
        Updated state with agents_to_invoke list
    """
    file_path = state.get("file_path", "")
    
    file_type = detect_file_type(file_path)
    
    agents = determine_agents_to_invoke(file_path, file_type)
    
    return {
        "file_type": file_type,
        "agents_to_invoke": agents
    }


def create_agent_node(agent_name: str, llm):
    """
    Factory function to create an agent node.
    
    Args:
        agent_name: Name of the agent ("security", "quality", "performance", "style", "testing")
        llm: LangChain LLM instance
        
    Returns:
        A function that runs the agent
    """
    if agent_name == "security":
        agent = SecurityAgent(llm)
    elif agent_name == "quality":
        agent = QualityAgent(llm)
    elif agent_name == "performance":
        agent = PerformanceAgent(llm)
    elif agent_name == "style":
        agent = StyleAgent(llm)
    elif agent_name == "testing":
        agent = TestingAgent(llm)
    else:
        raise ValueError(f"Unknown agent: {agent_name}")
    
    def agent_node(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Agent node: Runs a specific agent's analysis.
        
        Args:
            state: Current ReviewState
            
        Returns:
            Updated state with agent's results
        """
        return agent.analyze(state)
    
    return agent_node


def aggregator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggregator node: Combines results from all agents.
    
    Args:
        state: Current ReviewState with all agent results
        
    Returns:
        Updated state with final verdict and score
    """
    return aggregate_review_results(state)


def should_run_security(state: Dict[str, Any]) -> bool:
    """Check if security agent should run."""
    agents = state.get("agents_to_invoke", [])
    return "security" in agents


def should_run_quality(state: Dict[str, Any]) -> bool:
    """Check if quality agent should run."""
    agents = state.get("agents_to_invoke", [])
    return "quality" in agents


def should_run_performance(state: Dict[str, Any]) -> bool:
    """Check if performance agent should run."""
    agents = state.get("agents_to_invoke", [])
    return "performance" in agents


def should_run_style(state: Dict[str, Any]) -> bool:
    """Check if style agent should run."""
    agents = state.get("agents_to_invoke", [])
    return "style" in agents


def should_run_testing(state: Dict[str, Any]) -> bool:
    """Check if testing agent should run."""
    agents = state.get("agents_to_invoke", [])
    return "testing" in agents


def create_review_graph(llm):
    """
    Create the LangGraph workflow for multi-agent code review.
    
    Graph structure:
        START
          ↓
        [Router] - Detects file type, selects agents
          ↓
        ┌──────┬──────┬──────┬──────┬──────┐
        ↓      ↓      ↓      ↓      ↓      ↓
    [Security][Quality][Performance][Style][Testing] (parallel, conditionally)
        ↓      ↓      ↓      ↓      ↓      
        └──────┴──────┴──────┴──────┴──────┘
          ↓
      [Aggregator] - Combines results
          ↓
        END
    
    Routing Logic:
    - Test files: security + testing
    - Docs/config/web files: security + style
    - Other code files: security + quality + performance
    
    Args:
        llm: LangChain LLM instance (ChatOllama)
        
    Returns:
        Compiled LangGraph
    """
    # Create the graph
    workflow = StateGraph(ReviewState)
    
    # Add nodes
    workflow.add_node("router", router_node)
    workflow.add_node("security", create_agent_node("security", llm))
    workflow.add_node("quality", create_agent_node("quality", llm))
    workflow.add_node("performance", create_agent_node("performance", llm))
    workflow.add_node("style", create_agent_node("style", llm))
    workflow.add_node("testing", create_agent_node("testing", llm))
    workflow.add_node("aggregator", aggregator_node)
    
    # Set entry point
    workflow.set_entry_point("router")
    
    # Add conditional edges from router to each agent
    workflow.add_conditional_edges(
        "router",
        should_run_security,
        {
            True: "security",
            False: "aggregator"
        }
    )
    
    workflow.add_conditional_edges(
        "router",
        should_run_quality,
        {
            True: "quality",
            False: "aggregator"
        }
    )
    
    workflow.add_conditional_edges(
        "router",
        should_run_performance,
        {
            True: "performance",
            False: "aggregator"
        }
    )
    
    workflow.add_conditional_edges(
        "router",
        should_run_style,
        {
            True: "style",
            False: "aggregator"
        }
    )
    
    workflow.add_conditional_edges(
        "router",
        should_run_testing,
        {
            True: "testing",
            False: "aggregator"
        }
    )
    
    # Add edges from all agents to aggregator
    workflow.add_edge("security", "aggregator")
    workflow.add_edge("quality", "aggregator")
    workflow.add_edge("performance", "aggregator")
    workflow.add_edge("style", "aggregator")
    workflow.add_edge("testing", "aggregator")
    
    # Add edge from aggregator to END
    workflow.add_edge("aggregator", END)
    
    # Compile the graph
    return workflow.compile()


def stream_multi_agent_review(
    file_path: str,
    code: str,
    diff: str,
    llm,
    change_type: str = "MODIFIED"
):
    """
    Run multi-agent review with streaming updates.
    
    This is the main entry point for running a code review.
    It streams updates as each node completes, allowing real-time
    progress display.
    
    Args:
        file_path: Path to file being reviewed
        code: Source code content
        diff: Git diff
        llm: LangChain LLM instance
        change_type: Type of change (ADDED, MODIFIED, DELETED)
        
    Yields:
        Dict updates as each node completes
        
    Example:
        >>> for update in stream_multi_agent_review("test.py", code, diff, llm):
        ...     print(f"Node completed: {list(update.keys())[0]}")
        Node completed: router
        Node completed: security
        Node completed: quality
        Node completed: performance
        Node completed: aggregator
    """
    graph = create_review_graph(llm)
    
    initial_state = {
        "file_path": file_path,
        "code": code,
        "diff": diff,
        "file_type": "unknown",
        "change_type": change_type,
        "agents_to_invoke": [],
        "agent_results": {},
        "deduplicated_issues": [],
        "final_score": 0,
        "verdict": "unknown",
        "agent_execution_times": {},
        "agent_errors": {},
        "summary": {}
    }
    
    for update in graph.stream(initial_state):
        yield update