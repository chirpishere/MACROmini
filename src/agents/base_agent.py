"""
Base Agent for MACROmini

Abstract base class for all specialist agents (Security, Style, Quality, etc.).
Provides common functionality for LLM communication, retry logic, and response parsing.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any
import time
import json
from langchain_core.messages import HumanMessage, SystemMessage

class BaseAgent(ABC):
    """
    Abstract base class for all specialist agents.
    
    Each specialist agent (Security, Style, etc.) inherits from this class
    and only needs to define its specialized system prompt.
    
    The base class handles:
    - LLM communication with retry logic
    - Response parsing and validation
    - Error handling and timing
    - State reading/writing
    """
    
    def __init__(self, name: str, llm):
        """
        Initialize the base agent.
        
        Args:
            name: Agent name (e.g., "security", "style")
            llm: LangChain LLM instance (ChatOllama)
        """
        self.name = name
        self.llm = llm
    
    @abstractmethod
    def _get_system_prompt(self) -> str:
        """
        Get the specialized system prompt for this agent.
        
        This is the ONLY method that subclasses must implement.
        Each agent defines what it looks for in code.
        
        Returns:
            System prompt string
            
        Example for SecurityAgent:
            "You are a security expert. Look for SQL injection, XSS, ..."
        """
        pass
    
    def analyze(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main entry point: Analyze code and return issues.
        
        This method:
        1. Reads file info from state
        2. Calls LLM with specialized prompt
        3. Parses response into structured issues
        4. Returns updated state with results
        
        Args:
            state: ReviewState dictionary
            
        Returns:
            Updated state with:
            - agent_results[agent_name] = list of issues
            - agent_execution_times[agent_name] = seconds taken
            - agent_errors[agent_name] = error message (if failed)
        """
        start_time = time.time()
        
        try:
            file_path = state.get("file_path", "")
            code = state.get("code", "")
            diff = state.get("diff", "")
            file_type = state.get("file_type", "unknown")
        
            issues = self._call_llm_with_retry(
                file_path=file_path,
                code=code,
                diff=diff,
                file_type=file_type
            )
            
            execution_time = time.time() - start_time
            
            return {
                "agent_results": {self.name: issues},
                "agent_execution_times": {self.name: execution_time},
                "agent_errors": {self.name: ""}  # No error
            }
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"{type(e).__name__}: {str(e)}"
            
            return {
                "agent_results": {self.name: []},  # Empty results on error
                "agent_execution_times": {self.name: execution_time},
                "agent_errors": {self.name: error_msg}
            }
        

    def _call_llm_with_retry(
        self,
        file_path: str,
        code: str,
        diff: str,
        file_type: str,
        max_retries: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Call LLM with retry logic.
        
        Attempts to call the LLM up to max_retries times.
        If all attempts fail, raises the last exception.
        
        Args:
            file_path: Path to file being reviewed
            code: Source code content
            diff: Git diff
            file_type: Type of file (python, javascript, etc.)
            max_retries: Maximum number of attempts
            
        Returns:
            List of issue dictionaries
            
        Raises:
            Exception: If all retries fail
        """

        last_exception = None
        
        for attempt in range(max_retries):
            try:
                system_prompt = self._get_system_prompt()
                
                user_prompt = f"""Review this code change and identify issues.

**File:** {file_path}
**Type:** {file_type}
**Code:** {code}
**Diff (what changed):** {diff}

Return a JSON object with this structure:
{{
    "issues": [
        {{
            "type": "security|bug|quality|performance|style",
            "severity": "critical|high|medium|low|info",
            "line_number": 10,
            "description": "What's wrong",
            "suggestion": "How to fix it",
            "code_snippet": "problematic code"
        }}
    ]
}}

If no issues found, return: {{"issues": []}}
"""
                
                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt)
                ]
                
                response = self.llm.invoke(messages)
                
                issues = self._parse_llm_response(response.content)
                
                return issues
            
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  #1s, 2s, 4s
                    time.sleep(wait_time)
                    continue
                else:
                    raise last_exception
                
        raise last_exception        #worst case scenario to avoid crashing
    
    def _parse_llm_response(self, response_text: str) -> List[Dict[str, Any]]:
        """
        Parse LLM JSON response into structured issues.
        
        Handles various response formats:
        - Pure JSON
        - JSON wrapped in markdown code blocks
        - Empty responses
        
        Args:
            response_text: Raw response from LLM
            
        Returns:
            List of issue dictionaries
            
        Raises:
            ValueError: If response cannot be parsed
        """
        if not response_text or not response_text.strip():
            return []
        
        cleaned = response_text.strip()
        
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        
        try:
            data = json.loads(cleaned)
            
            issues = data.get("issues", [])
            
            validated_issues = []
            for issue in issues:
                validated_issue = {
                    "type": issue.get("type", "quality"),
                    "severity": issue.get("severity", "info"),
                    "line_number": issue.get("line_number"),
                    "description": issue.get("description", "No description provided"),
                    "suggestion": issue.get("suggestion", "No suggestion provided"),
                    "code_snippet": issue.get("code_snippet"),
                    "agent": self.name
                }
                validated_issues.append(validated_issue)
            
            return validated_issues
            
        except json.JSONDecodeError as e:
            print(f"\n⚠️  [{self.name}] Failed to parse LLM response:")
            print(f"Response: {response_text[:200]}...")
            print(f"Error: {e}\n")
            
            return []
        except Exception as e:
            print(f"\n⚠️  [{self.name}] Unexpected error parsing response:")
            print(f"Error: {e}\n")
            return []
        

