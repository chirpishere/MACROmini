"""
State Management for MACROmini

This module defines the ReviewState TypedDict that flows through the entire
multi-agent code review workflow. The state acts as shared memory, allowing
agents to read input data and contribute their findings.
"""

from typing import TypedDict, List, Optional, Dict
from src.llm_client import CodeIssue


class ReviewState(TypedDict, total=False):
    """
    State object that flows through the multi-agent review system.
    
    This state is shared across all agents in the LangGraph workflow.
    Each agent reads what it needs and contributes its findings.
    
    State Lifecycle:
    1. Input fields are populated by Git utilities
    2. Coordinator decides which agents to invoke
    3. Each agent analyzes and adds its issues (parallel execution)
    4. Aggregator combines all results and calculates final metrics
    5. Complete state is returned to reviewer for display
    """
    
    file_path: str
    file_type: str
    code: str
    diff: str
    change_type: str
    
    agents_to_invoke: List[str]
    
    security_issues: List[CodeIssue]
    quality_issues: List[CodeIssue]
    performance_issues: List[CodeIssue]
    testing_issues: List[CodeIssue]
    documentation_issues: List[CodeIssue]
    style_issues: List[CodeIssue]
    
    #agent metadata fields
    agent_execution_times: Dict[str, float]
    agent_errors: Dict[str, Optional[str]]

    #aggregated result fields
    all_issues: List[CodeIssue]     
    deduplicated_issues: List[CodeIssue]    
    final_score: int               
    has_critical_issues: bool        
    summary: str       
    verdict: str   


def create_initial_state(
    file_path: str,
    file_type: str,
    code: str,
    diff: str,
    change_type: str
) -> ReviewState:
    """
    Create a new ReviewState with initial input values.
    
    This is the entry point for the multi-agent workflow. The state
    is then passed through the LangGraph and populated by agents.
    
    Args:
        file_path: Path to the file being reviewed
        file_type: Type of file (python, javascript, etc.)
        code: Code content to review
        diff: Git diff showing changes
        change_type: Type of change (added, modified, deleted)
        
    Returns:
        ReviewState with input fields populated, ready for agents
        
    Example:
        >>> state = create_initial_state(
        ...     file_path="src/auth.py",
        ...     file_type="python",
        ...     code="def login(username, password): ...",
        ...     diff="+def login...",
        ...     change_type="modified"
        ... )
    """
    return ReviewState(
        file_path=file_path,
        file_type=file_type,
        code=code,
        diff=diff,
        change_type=change_type,
        # Initialize agent result lists as empty
        security_issues=[],
        quality_issues=[],
        performance_issues=[],
        testing_issues=[],
        documentation_issues=[],
        style_issues=[],
        # Initialize metadata dicts as empty
        agent_execution_times={},
        agent_errors={},
        # Routing will be set by coordinator
        agents_to_invoke=[],
    )


def get_all_agent_issues(state: ReviewState) -> List[CodeIssue]:
    """
    Get all issues from all agents in the state.
    This is a convenience function to gather all agent results
    without manually listing each field.
    """
    all_issues = []
    
    # Gather issues from each agent
    if "security_issues" in state:
        all_issues.extend(state["security_issues"])
    if "quality_issues" in state:
        all_issues.extend(state["quality_issues"])
    if "performance_issues" in state:
        all_issues.extend(state["performance_issues"])
    if "testing_issues" in state:
        all_issues.extend(state["testing_issues"])
    if "documentation_issues" in state:
        all_issues.extend(state["documentation_issues"])
    if "style_issues" in state:
        all_issues.extend(state["style_issues"])
    
    return all_issues


def count_issues_by_severity(state: ReviewState) -> Dict[str, int]:
    """
    Count how many issues of each severity level exist.
    
    Args:
        state: ReviewState with agent results
        
    Returns:
        Dictionary mapping severity to count
        
    Example:
        >>> counts = count_issues_by_severity(state)
        >>> print(counts)
        {'critical': 2, 'high': 5, 'medium': 8, 'low': 3, 'info': 1}
    """
    from collections import Counter
    
    all_issues = get_all_agent_issues(state)
    severity_counts = Counter(issue.severity.value for issue in all_issues)
    
    return {
        "critical": severity_counts.get("critical", 0),
        "high": severity_counts.get("high", 0),
        "medium": severity_counts.get("medium", 0),
        "low": severity_counts.get("low", 0),
        "info": severity_counts.get("info", 0),
    }
