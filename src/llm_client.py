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
    
    def __init__(
        self, 
        model_name: str = "qwen2.5-coder:7b",
        temperature: float = 0.1,
        base_url: str = "http://localhost:11434"
    ):
        """
        Initialize the code reviewer
        
        Args:
            model_name: Ollama model to use (default: qwen2.5-coder:7b)
            temperature: LLM temperature (0.0-1.0). Lower = more focused/deterministic
            base_url: Ollama server URL
        """
        self.model_name = model_name
        self.llm = ChatOllama(
            model=model_name,
            temperature=temperature,
            base_url=base_url,
            format="json"  # Force JSON output
        )
        
        # Set up the output parser with our Pydantic model
        self.parser = JsonOutputParser(pydantic_object=ReviewResult)
        
        # Create the prompt template
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "{format_instructions}\n\nFile: {file_path}\n\nCode to review:\n```\n{code}\n```")
        ])
    
    def review_code(
        self, 
        code: str, 
        file_path: str = "unknown"
    ) -> ReviewResult:
        """
        Review code and return structured results
        
        Args:
            code: The code to review (can be diff or full file)
            file_path: Path to the file being reviewed (for context)
            
        Returns:
            ReviewResult with all issues found, summary, and score
            
        Example:
            >>> reviewer = OllamaCodeReviewer()
            >>> result = reviewer.review_code("def login(pwd): query = f'SELECT * FROM users WHERE pass={pwd}'", "auth.py")
            >>> print(f"Found {len(result.issues)} issues")
            >>> print(f"Score: {result.score}/10")
        """
        try:
            # Create the chain: prompt → LLM → JSON parser
            chain = self.prompt | self.llm | self.parser
            
            # Invoke the chain with our inputs
            result = chain.invoke({
                "format_instructions": self.parser.get_format_instructions(),
                "file_path": file_path,
                "code": code
            })
            
            # Convert dict to ReviewResult (with validation)
            return ReviewResult(**result)
            
        except Exception as e:
            # If anything fails (Ollama down, parsing error, etc.)
            # Return a safe default instead of crashing
            print(f"Error during review: {str(e)}")
            return ReviewResult(
                issues=[],
                summary=f"Review failed: {str(e)}",
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
        


# Example usage and testing
if __name__ == "__main__":
    # Test code with obvious issues
    test_code = """
def login(username, password):
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    result = db.execute(query)
    return result

def calculate_total(items):
    total = 0
    for item in items:
        total += item['price'] * len(items)
    return total
"""
    
    print("Testing Ollama Code Reviewer\n")
    
    reviewer = OllamaCodeReviewer()
    
    # Test connection first
    print("Testing connection to Ollama...")
    if not reviewer.test_connection():
        print("\nPlease start Ollama first:")
        print("ollama serve")
        exit(1)
    
    print("✅ Connected!\n")
    
    # Review the test code
    print("Reviewing test code...\n")
    result = reviewer.review_code(test_code, "test.py")
    
    # Display results
    print(f"📊 Review Results for test.py")
    print(f"{'='*50}")
    print(f"Score: {result.score}/10")
    print(f"Critical Issues: {'Yes' if result.has_critical_issues else 'No'}")
    print(f"\n{result.summary}\n")
    
    print(f"Issues Found: {len(result.issues)}")
    print(f"{'-'*50}")
    
    for i, issue in enumerate(result.issues, 1):
        emoji = "🔴" if issue.severity == IssueSeverity.CRITICAL else "🟡" if issue.severity == IssueSeverity.HIGH else "🔵"
        print(f"\n{emoji} Issue #{i} - {issue.type.value.upper()} ({issue.severity.value})")
        if issue.line_number:
            print(f"   Line: {issue.line_number}")
        print(f"   Problem: {issue.description}")
        print(f"   Fix: {issue.suggestion}")
        if issue.code_snippet:
            print(f"   Code: {issue.code_snippet}")
