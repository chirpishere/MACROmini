"""
Git Utilities for Code Review
Handles Git operations: getting diffs, parsing changes, extracting context.
"""

import re
import subprocess
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
    
    def __init__(self, repo_path: str = ".", debug: bool = False):
        """
        Initialize Git repository
        
        Args:
            repo_path: Path to the Git repository (default: current directory)
            debug: Enable debug logging
            
        Raises:
            ValueError: If repo_path is not a valid Git repository
        """
        self.debug = debug
        try:
            self.repo = Repo(repo_path)
            self.repo_path = Path(repo_path).resolve()
        except Exception as e:
            raise ValueError(f"Not a valid Git repository: {repo_path}") from e
    
    def get_staged_files_from_git(self) -> List[str]:
        """
        Get list of staged files using git command (more reliable)
        
        Returns:
            List of file paths that are staged
        """
        try:
            # Run git diff --cached --name-only to get staged files
            result = subprocess.run(
                ['git', 'diff', '--cached', '--name-only'],
                capture_output=True,
                text=True,
                cwd=self.repo_path
            )
            
            if result.returncode != 0:
                if self.debug:
                    print(f"Git command failed: {result.stderr}")
                return []
            
            files = [line.strip() for line in result.stdout.split('\n') if line.strip()]
            
            if self.debug:
                print(f"DEBUG: git diff --cached --name-only returned: {files}")
            
            return files
        except Exception as e:
            if self.debug:
                print(f"DEBUG: Error running git command: {e}")
            return []
    
    def get_staged_changes(self, include_context: bool = True) -> List[FileChange]:
        """
        Get files that are staged (git add) and ready to commit
        
        Args:
            include_context: Whether to include surrounding code context
            
        Returns:
            List of FileChange objects for staged files
        """
        # First get the list of files that are actually staged
        staged_files = self.get_staged_files_from_git()
        
        if self.debug:
            print(f"DEBUG: Total staged files from git: {len(staged_files)}")
            for file in staged_files:
                print(f"  - {file}")
        
        if not staged_files:
            return []
        
        try:
            # Get staged diff
            diff_index = self.repo.index.diff("HEAD", create_patch=True, R=True)
            changes = self._process_diff(diff_index, include_context, staged_files)
            
            if self.debug:
                print(f"DEBUG: Processed {len(changes)} changes from diff_index")
            
            return changes
            
        except GitCommandError as e:
            # this is in case of a new repo with no commits yet
            if "ambiguous argument 'HEAD'" in str(e):
                if self.debug:
                    print("DEBUG: No HEAD commit (new repository)")
                
                changes = []
                for file_path in staged_files:
                    try:
                        full_path = self.repo_path / file_path
                        if full_path.exists():
                            with open(full_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            
                            lines = content.split('\n')
                            diff_text = f"""--- /dev/null
                                        +++ b/{file_path}
                                        @@ -0,0 +1,{len(lines)} @@
                                        """ + '\n'.join([f"+{line}" for line in lines])
                            
                            # parse line numbers
                            added_lines = list(range(1, len(lines) + 1))
                            
                            file_change = FileChange(
                                file_path=file_path,
                                change_type=ChangeType.ADDED,
                                diff=diff_text,
                                added_lines=added_lines,
                                removed_lines=[]
                            )
                            changes.append(file_change)
                            
                            if self.debug:
                                print(f"DEBUG: Created ADDED change for {file_path} with {len(added_lines)} lines")
                        else:
                            if self.debug:
                                print(f"DEBUG: File {file_path} does not exist, skipping")
                    except Exception as file_error:
                        if self.debug:
                            print(f"DEBUG: Error processing {file_path}: {file_error}")
                
                return changes
            else:
                if self.debug:
                    print(f"DEBUG: GitCommandError: {e}")
                raise
    
    def get_unstaged_changes(self, include_context: bool = True) -> List[FileChange]:
        """
        Get files with unstaged changes (not yet git add)
        
        Args:
            include_context: Whether to include surrounding code context
            
        Returns:
            List of FileChange objects for unstaged files
        """
        diff_index = self.repo.index.diff(None, create_patch=True, R=True)
        return self._process_diff(diff_index, include_context)
    
    def _process_diff(self, diff_index, include_context: bool, staged_files: List[str] = None) -> List[FileChange]:
        """
        Process GitPython diff objects into FileChange objects
        
        Args:
            diff_index: GitPython diff object
            include_context: Whether to get surrounding code
            staged_files: Optional list of staged files to filter by
            
        Returns:
            List of FileChange objects
        """
        changes = []
        
        for diff_item in diff_index:
            if self.debug:
                print(f"\nDEBUG: Processing diff item")
                print(f"  a_path: {diff_item.a_path}")
                print(f"  b_path: {diff_item.b_path}")
                print(f"  new_file: {diff_item.new_file}")
                print(f"  deleted_file: {diff_item.deleted_file}")
                print(f"  renamed_file: {diff_item.renamed_file}")
            
            # Compare with GitPython change_type which is more reliable
            # 'A': added, 'D': deleted, 'M': modified, 'R': renamed
            git_change_type = getattr(diff_item, 'change_type', None)
            
            if self.debug:
                print(f"  git_change_type: {git_change_type}")
            
            if git_change_type == 'A':
                # Added file
                change_type = ChangeType.ADDED
                file_path = diff_item.b_path
                if self.debug:
                    print(f"  Determined: ADDED file: {file_path}")
            elif git_change_type == 'D':
                # Deleted file
                change_type = ChangeType.DELETED
                file_path = diff_item.a_path
                if self.debug:
                    print(f"  Determined: DELETED file: {file_path}")
            elif git_change_type == 'R' or git_change_type == 'C':
                # Renamed or copied file
                change_type = ChangeType.RENAMED
                file_path = diff_item.b_path or diff_item.a_path
                if self.debug:
                    print(f"  Determined: RENAMED file: {file_path} (from {diff_item.a_path} to {diff_item.b_path})")
            elif git_change_type == 'M':
                # Modified file
                change_type = ChangeType.MODIFIED
                file_path = diff_item.b_path or diff_item.a_path
                if self.debug:
                    print(f"  Determined: MODIFIED file: {file_path}")
            else:
                # Fallback to flag-based detection
                if diff_item.new_file:
                    change_type = ChangeType.ADDED
                    file_path = diff_item.b_path
                elif diff_item.deleted_file:
                    change_type = ChangeType.DELETED
                    file_path = diff_item.a_path
                elif diff_item.renamed_file:
                    change_type = ChangeType.RENAMED
                    file_path = diff_item.b_path or diff_item.a_path
                else:
                    change_type = ChangeType.MODIFIED
                    file_path = diff_item.b_path or diff_item.a_path
                
                if self.debug:
                    print(f"  Fallback determined: {change_type} file: {file_path}")
            
            if not file_path:
                if self.debug:
                    print(f"  WARNING: Could not determine file path, skipping")
                continue
            
            # If staged_files is provided, only include files that are actually staged
            if staged_files is not None and file_path not in staged_files:
                if self.debug:
                    print(f"  Skipping {file_path} - not in staged files list")
                continue
            
            # Skip binary files
            if diff_item.diff and self._is_binary(diff_item.diff):
                if self.debug:
                    print(f"  Skipping binary file: {file_path}")
                continue
            
            # Get the diff text
            diff_text = diff_item.diff.decode('utf-8', errors='ignore') if diff_item.diff else ""
            
            added_lines, removed_lines = self._parse_diff_lines(diff_text)
            
            file_change = FileChange(
                file_path=file_path,
                change_type=change_type,
                diff=diff_text,
                added_lines=added_lines,
                removed_lines=removed_lines
            )
            
            if self.debug:
                print(f"  Created FileChange: {file_path} ({change_type})")
                print(f"    Added lines: {len(added_lines)}, Removed lines: {len(removed_lines)}")
            
            changes.append(file_change)
        
        if self.debug:
            print(f"\nDEBUG: Total changes processed: {len(changes)}")
            for change in changes:
                print(f"  - {change.file_path}: {change.change_type}")
        
        return changes
    
    def _parse_diff_lines(self, diff_text: str) -> Tuple[List[int], List[int]]:
        """
        Parse diff text to extract line numbers of changes
        
        Args:
            diff_text: Git diff format text
            
        Returns:
            Tuple of (added_lines, removed_lines)
        """
        added_lines = []
        removed_lines = []
        
        old_line = 0
        new_line = 0
        
        for line in diff_text.split('\n'):
            # hunk headers at the beginning of diff
            hunk_match = re.match(r'@@ -(\d+),?\d* \+(\d+),?\d* @@', line)
            if hunk_match:
                old_line = int(hunk_match.group(1))
                new_line = int(hunk_match.group(2))
                continue
            
            if line.startswith('---') or line.startswith('+++') or line.startswith('diff'):
                continue
            
            # Parse changes
            if line.startswith('+') and not line.startswith('+++'):
                added_lines.append(new_line)
                new_line += 1
            elif line.startswith('-') and not line.startswith('---'):
                removed_lines.append(old_line)
                old_line += 1
            else:
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
            context_lines: Number of lines before/after to include
            
        Returns:
            String with file content including context lines
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
            return ''.join(lines[:500])  # Max 500 lines
        
        min_line = max(1, min(line_numbers) - context_lines)
        max_line = min(len(lines), max(line_numbers) + context_lines)
        
        relevant_lines = lines[min_line - 1:max_line]
        
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
        # binary files
        return b'\x00' in data[:8192]
    
    def is_repo_clean(self) -> bool:
        """
        Check if repository has no uncommitted changes
        
        Returns:
            True if clean (no changes), False if there are changes
        """
        return not self.repo.is_dirty()
    
    def get_current_branch(self) -> str:
        """Get the name of the current branch"""
        try:
            return self.repo.active_branch.name
        except:
            return "detached HEAD"
    
    def stage_file(self, file_path: str) -> bool:
        """
        Stage a file for commit
        
        Args:
            file_path: Path to file to stage
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.repo.git.add(file_path)
            return True
        except Exception as e:
            if self.debug:
                print(f"DEBUG: Failed to stage {file_path}: {e}")
            return False
