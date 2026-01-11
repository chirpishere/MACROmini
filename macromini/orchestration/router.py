"""
Router for MACROmini

Determines which specialist agents should analyze a given file based on
file type, file category (test, config, docs), and content characteristics.
"""

from typing import List
import os


FILE_TYPE_MAPPING = {
    # Python
    ".py": "python",
    ".pyi": "python",
    
    # JavaScript/TypeScript
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    
    # Web
    ".html": "html",
    ".css": "css",
    
    # Configuration
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".env": "env",
    
    # Documentation
    ".md": "markdown",
    ".txt": "text",
    
    # Database
    ".sql": "sql",
    
    # Shell
    ".sh": "shell",
    ".bash": "bash",
}


def detect_file_type(file_path: str) -> str:
    """
    Detect the file type based on file extension.
    
    Args:
        file_path: Path to the file
        
    Returns:
        File type string (e.g., "python", "javascript", "unknown")
    """
    _, ext = os.path.splitext(file_path)
    return FILE_TYPE_MAPPING.get(ext.lower(), "unknown")


def determine_agents_to_invoke(file_path: str, file_type: str) -> List[str]:
    """
    Determine which agents should analyze a given file.
    
    Routing logic:
    - Test files (test_*.py, *_test.py, test/*.py): security + testing
    - Docs/config/web files (.md, .json, .yaml, .html, .css): security + style
    - All other code files: security + quality + performance
    
    Args:
        file_path: Path to the file being reviewed
        file_type: Type of file (from detect_file_type)
        
    Returns:
        List of agent names to invoke
    """
    file_name = os.path.basename(file_path).lower()
    file_dir = os.path.dirname(file_path).lower()
    
    # Test files
    if (file_name.startswith("test_") or 
        file_name.endswith("_test.py") or 
        file_name.endswith("_test.js") or
        "/test/" in file_path.lower() or
        "/tests/" in file_path.lower()):
        return ["security", "testing"]
    
    # Documentation, config, and web files
    if file_type in ["markdown", "json", "yaml", "toml", "html", "css", "text"]:
        return ["security", "style"]
    
    # All other code files (Python, JavaScript, TypeScript, etc.)
    return ["security", "quality", "performance"]


def get_routing_summary(file_path: str) -> dict:
    """
    Get a summary of routing decisions for a file.
    
    Useful for debugging and understanding which agents will review a file.
    
    Args:
        file_path: Path to the file
        
    Returns:
        Dictionary with routing information including:
        - file_path: The input file path
        - file_type: Detected file type
        - agents_to_invoke: List of agents that will review this file
        - agent_count: Number of agents
    """
    file_type = detect_file_type(file_path)
    agents = determine_agents_to_invoke(file_path, file_type)
    
    return {
        "file_path": file_path,
        "file_type": file_type,
        "agents_to_invoke": agents,
        "agent_count": len(agents),
    }