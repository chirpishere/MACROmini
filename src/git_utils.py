"""
Git Utilities for Code Review
Handles Git operations: getting diffs, parsing changes, extracting context.
"""

import re
from pathlib import Path
from typing import List, Optional, Tuple
from enum import Enum
from pydantic import BaseModel, Field
from git import Repo, GitCommandError


class ChangeType(str, Enum):
    """Types of file changes in Git"""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"

class FileChange(BaseModel):
    """Represents a single file change in Git"""
    file_path: str = Field(description="Path to the changed file")
    change_type: ChangeType = Field(description="Type of change")
    diff: str = Field(default="", description="The actual diff content")
    added_lines: List[int] = Field(default_factory=list, description="Line numbers of added lines")
    removed_lines: List[int] = Field(default_factory=list, description="Line numbers of removed lines")
    
    @property
    def has_changes(self) -> bool:
        """Check if this file has actual code changes"""
        return len(self.added_lines) > 0 or len(self.removed_lines) > 0
    

class GitRepository:
    """
    Wrapper for Git repository operations
    Handles getting diffs, parsing changes, and extracting code context
    """
    
    def __init__(self, repo_path: str = "."):
        """
        Initialize Git repository
        
        Args:
            repo_path: Path to the Git repository (default: current directory)
        
        Raises:
            ValueError: If repo_path is not a valid Git repository
        """
        try:
            self.repo = Repo(repo_path)
            self.repo_path = Path(repo_path).resolve()
        except Exception as e:
            raise ValueError(f"Not a valid Git repository: {repo_path}") from e
    
    def get_staged_changes(self, include_context: bool = True) -> List[FileChange]:
        """
        Get files that are staged (git add) and ready to commit
        
        Args:
            include_context: Whether to include surrounding code context
            
        Returns:
            List of FileChange objects for staged files
            
        Example:
            >>> repo = GitRepository()
            >>> changes = repo.get_staged_changes()
            >>> for change in changes:
            ...     print(f"{change.file_path}: {len(change.added_lines)} lines added")
        """
        try:
            # Get staged diff
            diff_index = self.repo.index.diff("HEAD", create_patch=True)
            return self._process_diff(diff_index, include_context)
        except GitCommandError as e:
            # No commits yet (new repo)
            if "ambiguous argument 'HEAD'" in str(e):
                # Get all staged files in new repo
                diff_index = self.repo.index.diff(None, create_patch=True)
                return self._process_diff(diff_index, include_context)
            raise
    
    def get_unstaged_changes(self, include_context: bool = True) -> List[FileChange]:
        """
        Get files with unstaged changes (not yet git add)
        
        Args:
            include_context: Whether to include surrounding code context
            
        Returns:
            List of FileChange objects for unstaged files
        """
        diff_index = self.repo.index.diff(None, create_patch=True)
        return self._process_diff(diff_index, include_context)
    
    def _process_diff(self, diff_index, include_context: bool) -> List[FileChange]:
        """
        Process GitPython diff objects into FileChange objects
        
        Args:
            diff_index: GitPython diff object
            include_context: Whether to get surrounding code
            
        Returns:
            List of FileChange objects
        """
        changes = []
        
        for diff_item in diff_index:
            # Determine file path and change type
            if diff_item.new_file:
                file_path = diff_item.b_path
                change_type = ChangeType.ADDED
            elif diff_item.deleted_file:
                file_path = diff_item.a_path
                change_type = ChangeType.DELETED
            elif diff_item.renamed_file:
                file_path = diff_item.b_path
                change_type = ChangeType.RENAMED
            else:
                file_path = diff_item.b_path
                change_type = ChangeType.MODIFIED
            
            # Skip binary files
            if diff_item.diff and self._is_binary(diff_item.diff):
                continue
            
            # Get the diff text
            diff_text = diff_item.diff.decode('utf-8') if diff_item.diff else ""
            
            # Parse line numbers from diff
            added_lines, removed_lines = self._parse_diff_lines(diff_text)
            
            # Create FileChange object
            file_change = FileChange(
                file_path=file_path,
                change_type=change_type,
                diff=diff_text,
                added_lines=added_lines,
                removed_lines=removed_lines
            )
            
            changes.append(file_change)
        
        return changes
    
    def _parse_diff_lines(self, diff_text: str) -> Tuple[List[int], List[int]]:
        """
        Parse diff text to extract line numbers of changes
        
        Args:
            diff_text: Git diff format text
            
        Returns:
            Tuple of (added_lines, removed_lines)
            
        Example diff format:
            @@ -10,5 +10,6 @@
             context line
            -removed line
            +added line
        """
        added_lines = []
        removed_lines = []
        
        # Track current line numbers
        old_line = 0
        new_line = 0
        
        for line in diff_text.split('\n'):
            # Parse hunk headers: @@ -10,5 +12,6 @@
            hunk_match = re.match(r'@@ -(\d+),?\d* \+(\d+),?\d* @@', line)
            if hunk_match:
                old_line = int(hunk_match.group(1))
                new_line = int(hunk_match.group(2))
                continue
            
            # Skip diff metadata lines
            if line.startswith('---') or line.startswith('+++') or line.startswith('diff'):
                continue
            
            # Parse changes
            if line.startswith('+') and not line.startswith('+++'):
                # Added line
                added_lines.append(new_line)
                new_line += 1
            elif line.startswith('-') and not line.startswith('---'):
                # Removed line
                removed_lines.append(old_line)
                old_line += 1
            else:
                # Context line (unchanged)
                old_line += 1
                new_line += 1
        
        return added_lines, removed_lines
    
    def get_file_content_with_context(
        self, 
        file_path: str, 
        line_numbers: List[int], 
        context_lines: int = 10
    ) -> str:
        """
        Get file content around specific line numbers with context
        
        Args:
            file_path: Path to the file
            line_numbers: Line numbers to get context around
            context_lines: Number of lines before/after to include (default: 10)
            
        Returns:
            String with file content including context lines
            
        Example:
            >>> repo = GitRepository()
            >>> content = repo.get_file_content_with_context("src/auth.py", [50, 51], context_lines=5)
            # Returns lines 45-56 of auth.py
        """
        full_path = self.repo_path / file_path
        
        if not full_path.exists():
            return f"# File not found: {file_path}"
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            return f"# Error reading file: {str(e)}"
        
        if not line_numbers:
            # No specific lines, return whole file (up to reasonable limit)
            return ''.join(lines[:500])  # Max 500 lines
        
        # Find min and max lines with context
        min_line = max(1, min(line_numbers) - context_lines)
        max_line = min(len(lines), max(line_numbers) + context_lines)
        
        # Extract relevant lines (convert to 0-indexed)
        relevant_lines = lines[min_line - 1:max_line]
        
        # Add line numbers for clarity
        numbered_lines = [
            f"{i + min_line:4d} | {line.rstrip()}"
            for i, line in enumerate(relevant_lines)
        ]
        
        return '\n'.join(numbered_lines)
    
    def get_full_file_content(self, file_path: str) -> str:
        """
        Get complete file content (for new files)
        
        Args:
            file_path: Path to the file
            
        Returns:
            Complete file content as string
        """
        full_path = self.repo_path / file_path
        
        if not full_path.exists():
            return f"# File not found: {file_path}"
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"# Error reading file: {str(e)}"
    
    def _is_binary(self, data: bytes) -> bool:
        """
        Check if data is binary (not text)
        
        Args:
            data: Bytes to check
            
        Returns:
            True if binary, False if text
        """
        # Simple heuristic: if there are null bytes, it's binary
        return b'\x00' in data[:8192]  # Check first 8KB
    
    def is_repo_clean(self) -> bool:
        """
        Check if repository has no uncommitted changes
        
        Returns:
            True if clean (no changes), False if there are changes
        """
        return not self.repo.is_dirty()
    
    def get_current_branch(self) -> str:
        """Get the name of the current branch"""
        return self.repo.active_branch.name


# Example usage and testing
if __name__ == "__main__":
    print("🔧 Testing Git Utilities\n")
    
    try:
        # Initialize repository (current directory)
        repo = GitRepository()
        print(f"✅ Repository loaded: {repo.repo_path}")
        print(f"   Branch: {repo.get_current_branch()}")
        print(f"   Clean: {repo.is_repo_clean()}\n")
        
        # Get staged changes
        print("📋 Staged Changes:")
        staged = repo.get_staged_changes()
        
        if not staged:
            print("   No staged changes found.")
            print("   Try: git add <file>")
        else:
            for change in staged:
                print(f"\n📄 {change.file_path} ({change.change_type.value})")
                print(f"   +{len(change.added_lines)} lines added")
                print(f"   -{len(change.removed_lines)} lines removed")
                
                if change.added_lines:
                    print(f"   Added at lines: {change.added_lines[:5]}{'...' if len(change.added_lines) > 5 else ''}")
                
                # Show a snippet of the diff
                if change.diff:
                    diff_lines = change.diff.split('\n')[:10]
                    print(f"   Diff preview:")
                    for line in diff_lines:
                        print(f"      {line}")
        
        # Get unstaged changes
        print("\n\n📝 Unstaged Changes:")
        unstaged = repo.get_unstaged_changes()
        
        if not unstaged:
            print("   No unstaged changes found.")
        else:
            for change in unstaged:
                print(f"\n📄 {change.file_path} ({change.change_type.value})")
                print(f"   +{len(change.added_lines)} lines added")
                print(f"   -{len(change.removed_lines)} lines removed")
        
        # Test context extraction
        if staged and staged[0].added_lines:
            print("\n\n🔍 Testing Context Extraction:")
            first_change = staged[0]
            context = repo.get_file_content_with_context(
                first_change.file_path,
                first_change.added_lines[:3],  # First 3 changed lines
                context_lines=5
            )
            print(f"\nContext around changes in {first_change.file_path}:")
            print(context)
        
    except ValueError as e:
        print(f"❌ Error: {e}")
        print("\nMake sure you're in a Git repository!")
        print("Try: git init")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

