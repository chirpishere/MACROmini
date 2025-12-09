"""
Base Agent for MACROmini Multi-Agent System

This module provides the BaseAgent abstract class that all specialist agents
(Security, Quality, Performance, Testing, Documentation, Style) inherit from.

The BaseAgent implements the Template Method pattern, providing:
- Common workflow for all agents
- Automatic retry logic
- Execution time tracking
- Error handling
- Agent attribution
"""

import time
from abc import ABC, abstractmethod
from typing import List, Optional
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from src.llm_client import CodeIssue, ReviewResult
from src.orchestration.state import ReviewState


class BaseAgent(ABC):
    """
    Abstract base class for all code review agents.
    
    Each specialist agent (Security, Quality, etc.) inherits from this class
    and implements the _create_prompt() method to define their expertise.
    
    The base class handles:
    - LLM communication with retry logic
    - JSON parsing and validation
    - Execution time tracking
    - Error handling and graceful degradation
    - Agent attribution (marking which agent found each issue)
    
    Usage:
        class SecurityAgent(BaseAgent):
            def _create_prompt(self) -> ChatPromptTemplate:
                return ChatPromptTemplate.from_messages([
                    ("system", "You are a security expert..."),
                    ("human", "Review this code: {code}")
                ])
    """


    def __init__(self, llm: ChatOllama, agent_name: str = "base"):
        """
        Initialize the base agent.
        
        Args:
            llm: ChatOllama instance for LLM communication
            agent_name: Name of the agent (e.g., "security", "quality")
        """
        self.llm = llm
        self.agent_name = agent_name
        self.prompt = self._create_prompt()
        self.parser = JsonOutputParser(pydantic_object=ReviewResult)


    #public API called by LangGraph
    def analyze(self, state: ReviewState) -> ReviewState:
        """
        Main entry point for agent analysis.
        
        This method implements the complete workflow:
        1. Extract code from state
        2. Call LLM with retry logic
        3. Parse and validate results
        4. Add agent attribution to issues
        5. Update state with results and metrics
        6. Return updated state
        
        Args:
            state: Current review state with code to analyze
            
        Returns:
            Updated state with agent's findings added
            
        Note:
            This method handles errors gracefully - if analysis fails,
            it returns an empty issue list rather than crashing.
        """
        start_time = time.time()
        
        try:
            # Step 1: Call LLM with retry logic
            issues = self._call_llm_with_retry(state)
            
            # Step 2: Add agent attribution to each issue
            for issue in issues:
                issue.agent = self.agent_name
            
            # Step 3: Update state with results
            self._update_state_with_issues(state, issues)
            
            # Step 4: Track execution metrics
            execution_time = time.time() - start_time
            self._update_state_metadata(state, execution_time, error=None)
            
            return state
            
        except Exception as e:
            # Graceful degradation: log error but don't crash
            execution_time = time.time() - start_time
            self._update_state_metadata(state, execution_time, error=str(e))
            
            # Return state with empty issues (other agents continue)
            self._update_state_with_issues(state, [])
            return state
        
    
    #protected methods, subclasses can overrride these
    @abstractmethod
    def _create_prompt(self) -> ChatPromptTemplate:
        """
        Create the specialized prompt for this agent.
        
        Each agent MUST implement this method to define their expertise.
        The prompt should instruct the LLM to focus on the agent's domain.
        
        Returns:
            ChatPromptTemplate with system and human messages
            
        Example:
            return ChatPromptTemplate.from_messages([
                ("system", "You are a {domain} expert..."),
                ("human", "Review this code:\\n{code}")
            ])
        """
        pass

    def _call_llm_with_retry(
        self, 
        state: ReviewState, 
        max_retries: int = 2
    ) -> List[CodeIssue]:
        """
        Call LLM with automatic retry on transient failures.
        
        Args:
            state: Review state containing code to analyze
            max_retries: Maximum number of retry attempts
            
        Returns:
            List of issues found by the agent
            
        Raises:
            Exception: If all retries are exhausted
        """
        for attempt in range(max_retries + 1):
            try:
                return self._call_llm(state)
            except Exception as e:
                if attempt == max_retries:
                    raise

                time.sleep(1)
    
    def _call_llm(self, state: ReviewState) -> List[CodeIssue]:
        """
        Call the LLM and parse the response.
        
        Args:
            state: Review state containing code to analyze
            
        Returns:
            List of CodeIssue objects found by the agent
        """
        #chain
        chain = self.prompt | self.llm | self.parser
        
        result = chain.invoke({
            "format_instructions": self.parser.get_format_instructions(),
            "file_path": state.get("file_path", "unknown"),
            "file_type": state.get("file_type", "unknown"),
            "code": state.get("code", ""),
            "diff": state.get("diff", ""),
        })
        
        if isinstance(result, dict):
            review_result = ReviewResult(**result)
            return review_result.issues
        else:
            return result.issues if hasattr(result, 'issues') else []
    
    def _update_state_with_issues(
        self, 
        state: ReviewState, 
        issues: List[CodeIssue]
    ) -> None:
        """
        Update state with this agent's findings.
        
        Args:
            state: Review state to update
            issues: List of issues found by this agent
        """
        # Map agent name to state field
        issue_field = f"{self.agent_name}_issues"
        
        if issue_field not in state:
            state[issue_field] = []
        
        state[issue_field] = issues
    
    def _update_state_metadata(
        self, 
        state: ReviewState, 
        execution_time: float, 
        error: Optional[str]
    ) -> None:
        """
        Update state with agent execution metadata.
        
        Args:
            state: Review state to update
            execution_time: Time taken by agent in seconds
            error: Error message if agent failed, None if successful
        """
        # Initialize metadata dicts if not present
        if "agent_execution_times" not in state:
            state["agent_execution_times"] = {}
        if "agent_errors" not in state:
            state["agent_errors"] = {}
        
        state["agent_execution_times"][self.agent_name] = round(execution_time, 2)
        state["agent_errors"][self.agent_name] = error

