"""
LLM Client for Code Review
Handles all communication with Ollama and structures the review results.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser


class IssueType(str, Enum):
    """Types of issues the reviewer can detect"""
    SECURITY = "security"
    BUG = "bug"
    QUALITY = "quality"
    PERFORMANCE = "performance"
    STYLE = "style"

class IssueSeverity(str, Enum):
    """Severity levels for issues"""
    CRITICAL = "critical"  # Must fix (security, crashes)
    HIGH = "high"          # Should fix (bugs, major issues)
    MEDIUM = "medium"      # Nice to fix (code smells)
    LOW = "low"            # Optional (minor style issues)
    INFO = "info"          # Just FYI (suggestions)


class CodeIssue(BaseModel):
    """A single issue found in the code"""
    type: IssueType = Field(description="Type of issue")
    severity: IssueSeverity = Field(description="How critical is this")
    line_number: Optional[int] = Field(None, description="Line number (if applicable)")
    description: str = Field(description="What's wrong")
    suggestion: str = Field(description="How to fix it")
    code_snippet: Optional[str] = Field(None, description="Problematic code")

class ReviewResult(BaseModel):
    """Complete review result"""
    issues: List[CodeIssue] = Field(default_factory=list, description="All issues found")
    summary: str = Field(description="Overall summary of the review")
    has_critical_issues: bool = Field(description="Are there any critical issues?")
    score: int = Field(ge=0, le=10, description="Code quality score (0-10)")


SYSTEM_PROMPT = """You are an expert code reviewer focused on finding security vulnerabilities, bugs, code quality issues, and performance problems.

Your task:
1. Analyze the provided code changes
2. Identify issues in these categories:
   - SECURITY: SQL injection, XSS, authentication issues, secrets in code, insecure dependencies
   - BUG: Logic errors, null pointer issues, race conditions, off-by-one errors
   - QUALITY: Code smells, anti-patterns, maintainability issues, poor naming
   - PERFORMANCE: Inefficient algorithms, unnecessary loops, memory leaks, N+1 queries
   - STYLE: Formatting, naming conventions, documentation gaps

3. For each issue, provide:
   - type: one of "security", "bug", "quality", "performance", "style"
   - severity: one of "critical", "high", "medium", "low", "info"
   - line_number: integer (if identifiable)
   - description: clear description of the problem
   - suggestion: actionable fix
   - code_snippet: relevant code (optional)

4. IMPORTANT: You MUST provide:
   - issues: array of issue objects (can be empty if no issues)
   - summary: string describing overall code quality (1-2 sentences)
   - has_critical_issues: boolean (true if any critical severity issues found)
   - score: integer from 0 to 10 (NOT 0-100!)
     - 10 = perfect code
     - 8-9 = very good, minor issues only
     - 6-7 = acceptable, some issues
     - 4-5 = needs work, multiple issues
     - 0-3 = serious problems, must fix

Be thorough but focus on real issues that matter. Avoid nitpicks unless they're part of critical problems.
"""


class OllamaCodeReviewer:
    """Client for reviewing code using Ollama LLM"""
    
    # Constants
    DEFAULT_MODEL = "qwen2.5-coder:7b"
    DEFAULT_TEMPERATURE = 0.1
    DEFAULT_BASE_URL = "http://localhost:11434"
    MAX_RETRIES = 3
    RETRY_DELAY = 1  # seconds
    
    def __init__(
        self, 
        model_name: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE,
        base_url: str = DEFAULT_BASE_URL
    ):
        """
        Initialize the code reviewer
        
        Args:
            model_name: Ollama model to use (default: qwen2.5-coder:7b)
            temperature: LLM temperature (0.0-1.0). Lower = more focused/deterministic
            base_url: Ollama server URL
        """
        self.model_name = model_name
        self.base_url = base_url
        
        self._check_model_availability()
        
        self.llm = ChatOllama(
            model=model_name,
            temperature=temperature,
            base_url=base_url,
            format="json"
        )
        
        self.parser = JsonOutputParser(pydantic_object=ReviewResult)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "{format_instructions}\n\nFile: {file_path}\n\nCode to review:\n```\n{code}\n```")
        ])
    
    def review_code(
        self, 
        code: str, 
        file_path: str = "unknown",
        max_retries: int = 2
    ) -> ReviewResult:
        """
        Review code and return structured results
        
        Args:
            code: The code to review (can be diff or full file)
            file_path: Path to the file being reviewed (for context)
            max_retries: Number of retry attempts for transient failures
            
        Returns:
            ReviewResult with all issues found, summary, and score
            
        Example:
            >>> reviewer = OllamaCodeReviewer()
            >>> result = reviewer.review_code("def login(pwd): query = f'SELECT * FROM users WHERE pass={pwd}'", "auth.py")
            >>> print(f"Found {len(result.issues)} issues")
            >>> print(f"Score: {result.score}/10")
        """
        import time
        
        for attempt in range(max_retries):
            try:
                chain = self.prompt | self.llm | self.parser
                
                result = chain.invoke({
                    "format_instructions": self.parser.get_format_instructions(),
                    "file_path": file_path,
                    "code": code
                })
                
                review_result = self._parse_with_fallback(result)
                if review_result:
                    return review_result
                
                if attempt < max_retries - 1:
                    print(f"Parsing failed, retrying ({attempt + 1}/{max_retries})...")
                    time.sleep(1)
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"Error during review: {str(e)}")
                    return self._create_fallback_result(str(e))
                
                # Otherwise, retry
                print(f" Error: {str(e)}, retrying ({attempt + 1}/{max_retries})...")
                time.sleep(1)
        
        return self._create_fallback_result("Max retries exceeded")
    
    def _parse_with_fallback(self, result: dict) -> Optional[ReviewResult]:
        """
        Try to parse result into ReviewResult, with fallback fixes
        
        Args:
            result: Raw dictionary from LLM
            
        Returns:
            ReviewResult or None if parsing fails
        """
        try:
            return ReviewResult(**result)
        except Exception as e:
            fixed = self._fix_result_data(result)
            if fixed:
                try:
                    return ReviewResult(**fixed)
                except:
                    pass
            return None
    
    def _fix_result_data(self, data: dict) -> Optional[dict]:
        """
        Fix common LLM output issues
        
        Args:
            data: Raw result dictionary
            
        Returns:
            Fixed dictionary or None
        """
        try:
            # Ensure required fields exist
            data.setdefault("issues", [])
            data.setdefault("summary", "Code reviewed")
            
            if "score" in data and data["score"] > 10:
                data["score"] = min(10, data["score"] // 10)
            data.setdefault("score", 5)
            
            if "has_critical_issues" not in data:
                has_critical = any(
                    issue.get("severity") == "critical"
                    for issue in data.get("issues", [])
                    if isinstance(issue, dict)
                )
                data["has_critical_issues"] = has_critical
            
            for issue in data.get("issues", []):
                if not isinstance(issue, dict):
                    continue
                issue.setdefault("type", "quality")
                issue.setdefault("severity", "info")
                issue.setdefault("description", "Issue detected")
                issue.setdefault("suggestion", "Review and fix")
            
            return data
        except Exception as e:
            print(f"Could not fix result data: {e}")
            return None
    
    def _create_fallback_result(self, error_message: str) -> ReviewResult:
        """Create safe fallback result for failures"""
        return ReviewResult(
            issues=[],
            summary=f"Review failed: {error_message[:100]}",
            has_critical_issues=False,
            score=5
        )
    
    def test_connection(self) -> bool:
        """
        Test if Ollama is running and the model is available
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            response = self.llm.invoke("Hello")
            return True
        except Exception as e:
            print(f"Connection failed: {str(e)}")
            print(f"Make sure Ollama is running: ollama serve")
            print(f"And the model is installed: ollama pull {self.model_name}")
            return False
    
    def _check_model_availability(self) -> None:
        """Check if the specified model is available in Ollama"""
        import requests
        from rich.console import Console
        
        console = Console()
        
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                available_models = [model["name"] for model in data.get("models", [])]
                
                if self.model_name not in available_models:
                    console.print(f"[yellow]  Model '{self.model_name}' not found[/yellow]")
                    console.print(f"[cyan]Available models:[/cyan]")
                    for model in available_models:
                        console.print(f"  - {model}")
                    console.print(f"\n[cyan]To install the model, run:[/cyan]")
                    console.print(f"  ollama pull {self.model_name}")
                    raise ValueError(f"Model {self.model_name} not available")
        except requests.exceptions.ConnectionError:
            console.print("[red] Cannot connect to Ollama server[/red]")
            console.print("[cyan]Make sure Ollama is running:[/cyan]")
            console.print("  ollama serve")
            raise ConnectionError("Ollama server not running")

