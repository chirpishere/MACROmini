"""
State Management for MACROmini

This module defines the ReviewState that flows through the LangGraph.
All agents read from and write to this shared state.
"""

from typing import TypedDict, List, Dict, Any, Annotated
from operator import add


def merge_dicts(left: Dict, right: Dict) -> Dict:
    """
    Merge two dictionaries for parallel agent execution.
    
    When multiple agents run in parallel and update the same dict field,
    LangGraph needs to know how to merge them. This function combines
    the dictionaries without overwriting keys.
    """
    merged = left.copy()
    merged.update(right)
    return merged


class ReviewState(TypedDict):
    """
    Central state for the multi-agent review workflow.
    
    This state flows through all nodes in the LangGraph:
    1. Router reads file info, writes agents_to_invoke
    2. Agents read file info, write to agent_results
    3. Aggregator reads agent_results, writes final output
    
    Fields marked with Annotated[..., merge_dicts] support parallel updates.
    """
    
    # ===== INPUT: File Information (READ-ONLY for agents) =====
    file_path: str              
    code: str                  
    diff: str                 
    file_type: str                  
    change_type: str      
    
    # ===== ROUTING: Which agents to invoke =====
    agents_to_invoke: List[str]     
    
    # ===== AGENT RESULTS: Each agent writes its findings =====
    # Annotated with merge_dicts to handle parallel execution
    agent_results: Annotated[Dict[str, List[Dict[str, Any]]], merge_dicts]
    # Structure: {"security": [{issue1}, {issue2}], "style": [{issue3}]}
    
    # ===== AGGREGATION: Deduplicated and scored results =====
    deduplicated_issues: List[Dict[str, Any]]  
    final_score: int               
    verdict: str             
    
    # ===== METADATA: Execution tracking =====
    agent_execution_times: Annotated[Dict[str, float], merge_dicts]
    agent_errors: Annotated[Dict[str, str], merge_dicts]   
    
    # ===== SUMMARY: For display purposes =====
    summary: Dict[str, Any] 