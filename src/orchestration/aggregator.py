"""
Result Aggregator for MACROmini

Combines results from multiple specialist agents, deduplicates issues,
resolves severity conflicts, and calculates final review verdict.
"""

from typing import List, Dict, Any, Tuple, Optional
from difflib import SequenceMatcher
from collections import defaultdict

from src.orchestration.state import get_all_agent_issues, count_issues_by_severity

AGENT_WEIGHTS = {
    "security": 2.0,      # Highest priority
    "quality": 1.5,
    "performance": 1.3,
    "testing": 1.2,
    "documentation": 1.0,
    "style": 0.5,         # Lowest priority
}

SEVERITY_WEIGHTS = {
    "critical": 10,
    "high": 5,
    "medium": 2,
    "low": 1,
    "info": 0.5,
}

# Deduplication thresholds
SIMILARITY_THRESHOLD = 0.75
LINE_PROXIMITY = 2

# Verdict thresholds
REJECT_SCORE_THRESHOLD = 15
COMMENT_SCORE_THRESHOLD = 5


def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two text strings using SequenceMatcher.
    """
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def are_issues_similar(issue1: Dict[str, Any], issue2: Dict[str, Any]) -> bool:
    """
    Determine if two issues are likely duplicates.
    
    Uses fuzzy matching on line number proximity and text similarity.
    
    Args:
        issue1: First issue dictionary
        issue2: Second issue dictionary
        
    Returns:
        True if issues are likely duplicates
    """
    line1 = issue1.get("line_number")
    line2 = issue2.get("line_number")
    
    if line1 is None or line2 is None:
        desc_similarity = calculate_text_similarity(
            issue1.get("description", ""),
            issue2.get("description", "")
        )
        return desc_similarity > 0.9
    
    line_distance = abs(line1 - line2)
    if line_distance > LINE_PROXIMITY:
        return False
    
    desc_similarity = calculate_text_similarity(
        issue1.get("description", ""),
        issue2.get("description", "")
    )
    
    return desc_similarity >= SIMILARITY_THRESHOLD


def get_severity_priority(severity: str) -> int:
    """
    Get numeric priority for severity level (higher = more severe).
    
    Args:
        severity: Severity string (critical, high, medium, low, info)
        
    Returns:
        Priority number (5=critical, 1=info)
    """
    priority_map = {
        "critical": 5,
        "high": 4,
        "medium": 3,
        "low": 2,
        "info": 1,
    }
    return priority_map.get(severity.lower(), 0)


def merge_duplicate_issues(issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Merge a group of duplicate issues into a single issue.
    
    Strategy:
    - Take highest severity
    - Concatenate unique descriptions
    - Combine agent lists
    - Average confidence scores
    - Keep most specific suggestion
    """
    if len(issues) == 1:
        return issues[0]
    
    # Sort by severity
    sorted_issues = sorted(
        issues,
        key=lambda x: get_severity_priority(x.get("severity", "info")),
        reverse=True
    )
    
    merged = sorted_issues[0].copy()
    
    #get unique set of agents to avoid repeated agent issues
    agents = set()
    for issue in issues:
        agent = issue.get("agent", "unknown")
        agents.add(agent)
    
    descriptions = []
    seen_descriptions = set()
    for issue in sorted_issues:
        desc = issue.get("description", "").strip()
        is_unique = True
        for seen in seen_descriptions:
            if calculate_text_similarity(desc, seen) > 0.8:
                is_unique = False
                break
        
        if is_unique and desc:
            descriptions.append(desc)
            seen_descriptions.add(desc)
    
    merged["description"] = " | ".join(descriptions) if len(descriptions) > 1 else descriptions[0]
    
    # Combine suggestions (take longest/most detailed)
    suggestions = [issue.get("suggestion", "") for issue in sorted_issues]
    merged["suggestion"] = max(suggestions, key=len) if suggestions else ""
    
    confidences = [issue.get("confidence", 1.0) for issue in issues]
    avg_confidence = sum(confidences) / len(confidences)
    #boosted confidence when multiple agents agree
    merged["confidence"] = min(1.0, avg_confidence * (1 + 0.1 * (len(issues) - 1)))
    
    # Store which agents found this issue
    merged["agents"] = sorted(list(agents))
    merged["duplicate_count"] = len(issues)
    
    return merged


def deduplicate_issues(all_issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Deduplicate issues found by multiple agents.
    
    Simple strategy: Issues within ±5 lines are considered duplicates.
    Merge them by combining descriptions from different agents.
    """
    if not all_issues:
        return []
    
    LINE_RANGE = 5  # Issues within 5 lines are duplicates
    
    clusters: List[List[Dict[str, Any]]] = []
    processed_ids = set()
    
    for issue in all_issues:
        issue_id = id(issue)
        if issue_id in processed_ids:
            continue
        
        # Start new cluster with this issue
        cluster = [issue]
        processed_ids.add(issue_id)
        
        issue_line = issue.get("line_number")
        
        # Find other issues within line range
        for other_issue in all_issues:
            other_id = id(other_issue)
            if other_id in processed_ids:
                continue
            
            other_line = other_issue.get("line_number")
            
            # Check if within range
            if issue_line is not None and other_line is not None:
                if abs(issue_line - other_line) <= LINE_RANGE:
                    cluster.append(other_issue)
                    processed_ids.add(other_id)
            elif issue_line is None and other_line is None:
                # Both have no line number - group by description similarity
                if calculate_text_similarity(
                    issue.get("description", ""),
                    other_issue.get("description", "")
                ) > 0.8:
                    cluster.append(other_issue)
                    processed_ids.add(other_id)
        
        clusters.append(cluster)
    
    # Merge each cluster
    deduplicated = [merge_duplicate_issues(cluster) for cluster in clusters]
    
    return deduplicated


def calculate_weighted_score(issues: List[Dict[str, Any]]) -> float:
    """
    Calculate weighted score based on issue severity and agent importance.
    
    Formula: sum(severity_weight * agent_weight * confidence) for each issue
    Higher weighted score implies severe errors
    """
    score = 0.0
    
    for issue in issues:
        severity = issue.get("severity", "info").lower()
        agents = issue.get("agents", [issue.get("agent", "unknown")])
        confidence = issue.get("confidence", 1.0)
        
        severity_weight = SEVERITY_WEIGHTS.get(severity, 0)
        
        # Get highest agent weight
        agent_weight = max(
            [AGENT_WEIGHTS.get(agent, 1.0) for agent in agents],
            default=1.0
        )
        
        issue_score = severity_weight * agent_weight * confidence
        score += issue_score
    
    return round(score, 2)


def determine_verdict(
    score: float,
    severity_counts: Dict[str, int]
) -> str:
    """
    Determine final review verdict based on score and issue counts.
    
    Verdict logic:
    - REJECT: Any critical issues OR score > 15
    - COMMENT: Any high issues OR score > 5
    - APPROVE: Otherwise
    """

    if severity_counts.get("critical", 0) > 0:
        return "reject"
    
    if score > REJECT_SCORE_THRESHOLD:
        return "reject"
    
    if severity_counts.get("high", 0) > 0:
        return "comment"
    
    if score > COMMENT_SCORE_THRESHOLD:
        return "comment"
    
    return "approve"


def aggregate_review_results(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main aggregation function for multi-agent review results.
    
    Performs:
    1. Collection of all agent issues
    2. Deduplication (fuzzy matching)
    3. Severity conflict resolution (handled in merge)
    4. Weighted scoring
    5. Final verdict determination
    """
    
    
    # Collect all issues from all agents
    all_issues = get_all_agent_issues(state)
    
    # Deduplicate issues
    deduplicated_issues = deduplicate_issues(all_issues)
    
    # Count issues by severity
    severity_counts = count_issues_by_severity(deduplicated_issues)
    
    # Calculate weighted score
    weighted_score = calculate_weighted_score(deduplicated_issues)
    
    # Determine final verdict
    verdict = determine_verdict(weighted_score, severity_counts)
    
    # Generate summary statistics
    total_issues = len(deduplicated_issues)
    original_count = len(all_issues)
    duplicates_removed = original_count - total_issues
    
    return {
        "all_issues": all_issues,
        "deduplicated_issues": deduplicated_issues,
        "final_score": weighted_score,
        "verdict": verdict,
        "summary": {
            "total_issues": total_issues,
            "original_count": original_count,
            "duplicates_removed": duplicates_removed,
            "severity_counts": severity_counts,
        }
    }