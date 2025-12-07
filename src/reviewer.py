"""
Main Code Reviewer
Combines Git utilities and LLM client to review staged code changes.
"""

from typing import List, Dict
from dataclasses import dataclass
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from git_utils import GitRepository, FileChange, ChangeType
from llm_client import OllamaCodeReviewer, ReviewResult, IssueSeverity, IssueType


@dataclass
class FileReviewResult:
    """Review result for a single file"""
    file_path: str
    change_type: ChangeType
    review: ReviewResult
    lines_changed: int


class CodeReviewer:
    """
    Main code review orchestrator
    Combines Git operations and LLM analysis
    """
    
    def __init__(self, repo_path: str = "."):
        """
        Initialize the code reviewer
        
        Args:
            repo_path: Path to Git repository (default: current directory)
        """
        self.console = Console()
        self.git_repo = GitRepository(repo_path)
        self.llm_reviewer = OllamaCodeReviewer()
    
    def review_staged_changes(self) -> List[FileReviewResult]:
        """
        Review all staged changes
        
        Returns:
            List of FileReviewResult for each changed file
        """
        # Get staged changes
        self.console.print("\n[bold cyan] Analyzing staged changes...[/bold cyan]\n")
        
        try:
            changes = self.git_repo.get_staged_changes()
        except Exception as e:
            self.console.print(f"[red] Error getting staged changes: {e}[/red]")
            return []
        
        if not changes:
            self.console.print("[yellow]  No staged changes found.[/yellow]")
            self.console.print("[dim]Tip: Use 'git add <file>' to stage changes[/dim]")
            return []
        
        self.console.print(f"[green]Found {len(changes)} file(s) to review[/green]\n")
        
        # Review each file
        results = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            
            for change in changes:
                task = progress.add_task(
                    f"Reviewing {change.file_path}...",
                    total=None
                )
                
                if change.change_type == ChangeType.DELETED:
                    progress.update(task, description=f"[dim]Skipped {change.file_path} (deleted)[/dim]")
                    continue
                
                if change.change_type == ChangeType.ADDED:
                    code = self.git_repo.get_full_file_content(change.file_path) # new file so get entire content
                else:
                    # modified file so review only the changed lines with context
                    all_lines = change.added_lines + change.removed_lines
                    if all_lines:
                        code = self.git_repo.get_file_content_with_context(
                            change.file_path,
                            all_lines,
                            context_lines=10
                        )
                    else:
                        code = self.git_repo.get_full_file_content(change.file_path)
                
                # Review with LLM
                review = self.llm_reviewer.review_code(code, change.file_path)
                
                # Store result
                result = FileReviewResult(
                    file_path=change.file_path,
                    change_type=change.change_type,
                    review=review,
                    lines_changed=len(change.added_lines) + len(change.removed_lines)
                )
                results.append(result)
                
                progress.update(task, description=f"[green]✓[/green] {change.file_path}")
        
        return results
    
    def display_results(self, results: List[FileReviewResult]):
        """
        Display review results in a beautiful format
        
        Args:
            results: List of file review results
        """
        if not results:
            return
        
        self.console.print("\n" + "="*70 + "\n")
        self.console.print("[bold cyan] CODE REVIEW RESULTS[/bold cyan]\n")
        
        table = Table(title="Summary", show_header=True, header_style="bold magenta")
        table.add_column("File", style="cyan")
        table.add_column("Lines", justify="right")
        table.add_column("Score", justify="center")
        table.add_column("Issues", justify="center")
        table.add_column("Critical", justify="center")
        
        total_issues = 0
        total_critical = 0
        
        for result in results:
            critical_count = sum(
                1 for issue in result.review.issues 
                if issue.severity == IssueSeverity.CRITICAL
            )
            
            score = result.review.score
            if score >= 8:
                score_str = f"[green]{score}/10[/green]"
            elif score >= 6:
                score_str = f"[yellow]{score}/10[/yellow]"
            else:
                score_str = f"[red]{score}/10[/red]"
            
            critical_str = f"[red]{critical_count}[/red]" if critical_count > 0 else "[green]0[/green]"
            
            table.add_row(
                result.file_path,
                str(result.lines_changed),
                score_str,
                str(len(result.review.issues)),
                critical_str
            )
            
            total_issues += len(result.review.issues)
            total_critical += critical_count
        
        self.console.print(table)
        self.console.print()
        
        # Detailed issues
        for result in results:
            if not result.review.issues:
                continue
            
            self.console.print(f"\n[bold cyan]📄 {result.file_path}[/bold cyan]")
            self.console.print(f"[dim]{result.review.summary}[/dim]\n")
            
            for i, issue in enumerate(result.review.issues, 1):
                if issue.severity == IssueSeverity.CRITICAL:
                    emoji = "🔴"
                    color = "red"
                elif issue.severity == IssueSeverity.HIGH:
                    emoji = "🟡"
                    color = "yellow"
                elif issue.severity == IssueSeverity.MEDIUM:
                    emoji = "🟠"
                    color = "orange1"
                else:
                    emoji = "🔵"
                    color = "blue"
                
                issue_text = f"[bold]{issue.type.value.upper()}[/bold] - {issue.severity.value}\n\n"
                
                if issue.line_number:
                    issue_text += f"📍 Line {issue.line_number}\n\n"
                
                issue_text += f"[bold]Problem:[/bold]\n{issue.description}\n\n"
                issue_text += f"[bold]Suggestion:[/bold]\n{issue.suggestion}"
                
                if issue.code_snippet:
                    issue_text += f"\n\n[bold]Code:[/bold]\n[dim]{issue.code_snippet}[/dim]"
                
                panel = Panel(
                    issue_text,
                    title=f"{emoji} Issue #{i}",
                    border_style=color,
                    padding=(1, 2)
                )
                self.console.print(panel)
        
        self.console.print("\n" + "="*70 + "\n")
        
        if total_critical > 0:
            self.console.print(Panel(
                f"[bold red] REVIEW FAILED[/bold red]\n\n"
                f"Found {total_critical} critical issue(s) that must be fixed.\n"
                f"Total issues: {total_issues}\n\n"
                f"[dim]Fix the critical issues and try again.[/dim]",
                border_style="red",
                padding=(1, 2)
            ))
            return False
        elif total_issues > 0:
            self.console.print(Panel(
                f"[bold yellow]  REVIEW PASSED WITH WARNINGS[/bold yellow]\n\n"
                f"Found {total_issues} non-critical issue(s).\n"
                f"Consider addressing them before committing.\n\n"
                f"[dim]You can proceed with the commit.[/dim]",
                border_style="yellow",
                padding=(1, 2)
            ))
            return True
        else:
            self.console.print(Panel(
                f"[bold green] REVIEW PASSED[/bold green]\n\n"
                f"No issues found! Code looks good.\n\n"
                f"[dim]You can proceed with the commit.[/dim]",
                border_style="green",
                padding=(1, 2)
            ))
            return True
    
    def run(self) -> bool:
        """
        Run the complete code review workflow
        
        Returns:
            True if review passes (no critical issues), False otherwise
        """
        # Check Ollama connection
        self.console.print("[cyan]Checking Ollama connection...[/cyan]")
        if not self.llm_reviewer.test_connection():
            self.console.print("\n[red] Cannot connect to Ollama[/red]")
            self.console.print("[yellow]Make sure Ollama is running:[/yellow]")
            self.console.print("[dim]  ollama serve[/dim]\n")
            return False
        
        self.console.print("[green]✓ Connected to Ollama[/green]")
        
        results = self.review_staged_changes()
        
        if not results:
            return True 
        
        passed = self.display_results(results)
        
        return passed
    

# CLI entry point
if __name__ == "__main__":
    import sys
    
    console = Console()
    
    console.print("\n[bold cyan]MACROmini[/bold cyan]")
    console.print("[dim]Powered by Ollama + Qwen2.5-Coder[/dim]\n")
    
    try:
        reviewer = CodeReviewer()
        passed = reviewer.run()
        
        sys.exit(0 if passed else 1)
        
    except KeyboardInterrupt:
        console.print("\n\n[yellow]Review cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)