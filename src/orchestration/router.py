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
    ".mjs": "javascript",
    ".cjs": "javascript",
    
    # Web
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    
    # Configuration
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "config",
    ".conf": "config",
    ".env": "env",
    
    # Documentation
    ".md": "markdown",
    ".rst": "restructuredtext",
    ".txt": "text",
    
    # Database
    ".sql": "sql",
    
    # Shell
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    
    # Other
    ".xml": "xml",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
}


TEST_FILE_PATTERNS = [
    "test_",      
    "_test.",      
    ".test.",        
    ".spec.",          
    "tests/",          
    "/test/",     
]


CONFIG_FILE_PATTERNS = [
    "config",         
    "settings",    
    ".env",           
    "dockerfile",      
    "docker-compose",
    "requirements",    
    "package.json",    
    "tsconfig",   
    "webpack",        
    "babel",        
    "eslint",         
    "pytest",    
    "setup.",      
    "pyproject.toml",
]


DOC_FILE_PATTERNS = [
    "readme", 
    "changelog",     
    "license",     
    "contributing",    
    "docs/",   
    "/doc/",      
]


def detect_file_type(file_path: str) -> str:
    """
    Detect the file type based on file extension.
    """
    _, ext = os.path.splitext(file_path)
    return FILE_TYPE_MAPPING.get(ext.lower(), "unknown")

def is_test_file(file_path: str) -> bool:
    """
    Check if a file is a test file based on naming patterns.
    """
    file_path_lower = file_path.lower()
    return any(pattern in file_path_lower for pattern in TEST_FILE_PATTERNS)


def is_config_file(file_path: str) -> bool:
    """
    Check if a file is a configuration file based on naming patterns.
    """
    file_path_lower = file_path.lower()
    return any(pattern in file_path_lower for pattern in CONFIG_FILE_PATTERNS)


def is_documentation_file(file_path: str) -> bool:
    """
    Check if a file is a documentation file based on naming patterns.
    """
    file_path_lower = file_path.lower()
    file_type = detect_file_type(file_path)
    
    if file_type in ["markdown", "restructuredtext", "text"]:
        return any(pattern in file_path_lower for pattern in DOC_FILE_PATTERNS)
    
    return False


def determine_agents_to_invoke(file_path: str, file_type: str) -> List[str]:
    """
    Determine which agents should analyze a given file.
    
    Routing logic:
    - Code files (Python, JS, TS): All 6 agents
    - Test files: Quality, Testing, Documentation, Style (skip Security, Performance)
    - Config files: Security, Documentation, Style (check for secrets, formatting)
    - Documentation files: Documentation, Style only
    - SQL files: Security, Quality, Performance, Documentation, Style
    - Unknown files: Security, Quality, Documentation, Style (conservative)
    """

    is_test = is_test_file(file_path)
    is_config = is_config_file(file_path)
    is_doc = is_documentation_file(file_path)
    
    if is_doc:
        return ["documentation", "style"]
    
    if is_config:
        return ["security", "documentation", "style"]
    
    if is_test:
        return ["quality", "testing", "documentation", "style"]
    
    if file_type in ["python", "javascript", "typescript"]:
        return ["security", "quality", "performance", "testing", "documentation", "style"]
    
    if file_type == "sql":
        return ["security", "quality", "performance", "documentation", "style"]
    
    if file_type in ["go", "rust", "java", "ruby", "php"]:
        return ["security", "quality", "performance", "testing", "documentation", "style"]
    
    if file_type in ["html", "css", "scss", "sass"]:
        return ["quality", "documentation", "style"]
    
    if file_type == "shell":
        return ["security", "quality", "documentation", "style"]
    
    if file_type in ["json", "yaml", "toml", "xml"]:
        return ["security", "documentation", "style"]
    
    return ["security", "quality", "documentation", "style"]


def get_routing_summary(file_path: str) -> dict:
    """
    Get a summary of routing decisions for a file (useful for debugging).
    """
    file_type = detect_file_type(file_path)
    agents = determine_agents_to_invoke(file_path, file_type)
    
    return {
        "file_path": file_path,
        "file_type": file_type,
        "is_test": is_test_file(file_path),
        "is_config": is_config_file(file_path),
        "is_documentation": is_documentation_file(file_path),
        "agents_to_invoke": agents,
        "agent_count": len(agents),
    }