"""
Aggregator for MACROmini

Combines results from multiple agents into a final review.
Includes smart deduplication that merges issues pointing to the same code segment.
"""

from typing import Dict, List, Any, Optional, Tuple


SEVERITY_WEIGHTS = {
    "critical": 20,
    "high": 10,
    "medium": 5,
    "low": 2,
    "info": 1
}

# Severity ordering for comparison (higher index = more severe)
SEVERITY_ORDER = ["info", "low", "medium", "high", "critical"]

def get_line_range(issue: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    """
    Extract the line range from an issue.
    
    Args:
        issue: Issue dictionary
        
    Returns:
        Tuple of (start_line, end_line) or None if no line info
    """
    line_num = issue.get("line_number")
    
    if line_num is None:
        return None
    
    if isinstance(line_num, int):
        return (line_num, line_num)
    
    if isinstance(line_num, (tuple, list)) and len(line_num) == 2:
        return (line_num[0], line_num[1])
    
    return None


def ranges_overlap(range1: Tuple[int, int], range2: Tuple[int, int]) -> bool:
    """
    Check if two line ranges overlap or are adjacent.
    
    Args:
        range1: (start1, end1)
        range2: (start2, end2)
        
    Returns:
        True if ranges overlap or are within 2 lines of each other
    """
    start1, end1 = range1
    start2, end2 = range2
    
    # Check for overlap or adjacency (within 2 lines)
    # This catches issues that are part of the same code block
    return not (end1 + 2 < start2 or end2 + 2 < start1)


def merge_issues(issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge multiple issues pointing to the same code segment.
    Keeps the highest severity issue and tracks all contributing agents.
    
    Args:
        issues: List of issues to merge
        
    Returns:
        Single merged issue with combined information
    """
    # Sort by severity (highest first)
    sorted_issues = sorted(
        issues,
        key=lambda x: SEVERITY_ORDER.index(x.get("severity", "info").lower()),
        reverse=True
    )
    
    merged = sorted_issues[0].copy()
    
    agents = []
    descriptions = []
    suggestions = []
    
    for issue in issues:
        agent = issue.get("agent", "unknown")
        if agent not in agents:
            agents.append(agent)
        
        desc = issue.get("description", "")
        if desc and desc not in descriptions:
            descriptions.append(desc)
        
        sugg = issue.get("suggestion", "")
        if sugg and sugg not in suggestions:
            suggestions.append(sugg)
    
    merged["found_by_agents"] = agents
    merged["agent_count"] = len(agents)
    
    if len(descriptions) > 1:
        merged["description"] = descriptions[0]
        merged["related_concerns"] = descriptions[1:]
    
    if len(suggestions) > 1:
        merged["suggestion"] = " | ".join(suggestions)
    
    return merged


def deduplicate_issues(all_issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate issues by grouping those pointing to the same or overlapping code segments.
    For each segment, keep only the highest severity issue.
    
    Strategy:
    1. Group issues by line range (with overlap detection)
    2. For each group, merge into single issue with highest severity
    3. Track which agents contributed to each deduplicated issue
    
    Args:
        all_issues: All issues from all agents
        
    Returns:
        Deduplicated list of issues
    """
    issues_with_lines = []
    issues_without_lines = []
    
    for issue in all_issues:
        line_range = get_line_range(issue)
        if line_range:
            issues_with_lines.append((line_range, issue))
        else:
            issues_without_lines.append(issue)
    
    # Group overlapping issues
    groups = []
    
    for line_range, issue in issues_with_lines:
        merged_into_group = False
        
        for group in groups:
            for existing_range, _ in group:
                if ranges_overlap(line_range, existing_range):
                    group.append((line_range, issue))
                    merged_into_group = True
                    break
            
            if merged_into_group:
                break
        
        #no overlap found, create new group
        if not merged_into_group:
            groups.append([(line_range, issue)])
    
    #merge issues within each group
    deduplicated = []
    
    for group in groups:
        group_issues = [issue for _, issue in group]
        
        if len(group_issues) > 1:
            merged_issue = merge_issues(group_issues)
            deduplicated.append(merged_issue)
        else:
            issue = group_issues[0]
            issue["found_by_agents"] = [issue.get("agent", "unknown")]
            issue["agent_count"] = 1
            deduplicated.append(issue)

    for issue in issues_without_lines:
        issue["found_by_agents"] = [issue.get("agent", "unknown")]
        issue["agent_count"] = 1
        deduplicated.append(issue)
    
    return deduplicated


def aggregate_review_results(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggregate results from all agents with smart deduplication.
    
    Process:
    1. Collect all issues from all agents
    2. Deduplicate by line range (merge overlapping issues)
    3. Calculate score based on unique issues only
    4. Determine verdict
    
    Args:
        state: ReviewState with agent_results filled
        
    Returns:
        Updated state with:
        - deduplicated_issues: Unique issues (merged by line segment)
        - final_score: Weighted score based on unique issues
        - verdict: "approve", "comment", or "reject"
        - summary: Statistics about the review
    """
    agent_results = state.get("agent_results", {})
    
    all_issues = []
    for agent_name, issues in agent_results.items():
        for issue in issues:
            issue["agent"] = agent_name
            all_issues.append(issue)
    
    deduplicated_issues = deduplicate_issues(all_issues)
    
    total_score = 0
    severity_counts = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "info": 0
    }
    
    for issue in deduplicated_issues:
        severity = issue.get("severity", "info").lower()
        weight = SEVERITY_WEIGHTS.get(severity, 1)
        total_score += weight
        
        if severity in severity_counts:
            severity_counts[severity] += 1
    
    if severity_counts["critical"] > 0:
        verdict = "reject"
    elif total_score > 15:
        verdict = "reject"
    elif total_score > 5:
        verdict = "comment"
    else:
        verdict = "approve"
    
    summary = {
        "total_issues": len(deduplicated_issues),
        "original_issues": len(all_issues),
        "deduplication_savings": len(all_issues) - len(deduplicated_issues),
        "by_severity": severity_counts,
        "agents_run": list(agent_results.keys()),
        "agent_count": len(agent_results)
    }
    
    return {
        "deduplicated_issues": deduplicated_issues,
        "final_score": total_score,
        "verdict": verdict,
        "summary": summary
    }