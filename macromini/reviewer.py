"""
Main Code Reviewer for MACROmini
Combines Git utilities and multi-agent LLM system to review staged code changes.
Supports async parallel execution of agents.
"""

from typing import List, Dict, Any
from dataclasses import dataclass
from pathlib import Path
import asyncio
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from langchain_ollama import ChatOllama

from macromini.git_utils import GitRepository, FileChange, ChangeType
from macromini.orchestration.graph import stream_multi_agent_review
from macromini.orchestration.state import ReviewState
from macromini.security import InputSanitizer


@dataclass
class FileReviewResult:
    """Review result for a single file"""
    file_path: str
    change_type: ChangeType
    review_state: ReviewState
    lines_changed: int


class CodeReviewer:
    """
    Main code review orchestrator
    Combines Git operations and multi-agent LLM analysis
    """
    
    def __init__(self, repo_path: str = ".", model: str = "qwen2.5-coder:7b", enable_guardrails: bool = True):
        """
        Initialize the code reviewer
        
        Args:
            repo_path: Path to Git repository (default: current directory)
            model: Ollama model to use (default: qwen2.5-coder:7b)
            enable_guardrails: Enable security guardrails (default: True)
        """
        self.console = Console()
        self.git_repo = GitRepository(repo_path)
        self.llm = ChatOllama(model=model, temperature=0)
        self.sanitizer = InputSanitizer()
        self.security_warnings = []
        self.enable_guardrails = enable_guardrails
    
    def _detect_language(self, file_path: str) -> str:
        """
        Detect programming language from file extension
        
        Args:
            file_path: Path to the file
            
        Returns:
            Language string ('python', 'javascript', 'c', or 'other')
        """
        extension = Path(file_path).suffix.lower()
        
        language_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.jsx': 'javascript',
            '.ts': 'javascript',
            '.tsx': 'javascript',
            '.c': 'c',
            '.cpp': 'c',
            '.cc': 'c',
            '.cxx': 'c',
            '.h': 'c',
            '.hpp': 'c',
            '.java': 'c',
            '.cs': 'c',
            '.go': 'c',
        }
        
        return language_map.get(extension, 'other')
    
    def _apply_guardrails(self, file_path: str, code: str, diff: str) -> tuple[str, str]:
        """
        Apply security guardrails to code and diff
        
        Args:
            file_path: Path to the file being reviewed
            code: Full code content
            diff: Git diff content
            
        Returns:
            Tuple of (sanitized_code, sanitized_diff)
        """
        if not self.enable_guardrails:
            return code, diff
        
        language = self._detect_language(file_path)
        
        # Detect injections in code first (before sanitizing)
        code_detections = self.sanitizer.detect_injections(code, language)
        
        # Sanitize code using the detections we just found (avoids re-detecting)
        sanitized_code, _ = self._sanitize_with_detections(code, code_detections, language, 'warn')
        
        # Detect and sanitize diff separately
        sanitized_diff, _ = self.sanitizer.sanitize(diff, language=language, mode='warn')
        
        # Filter code detections to medium and high confidence only
        filtered_detections = [d for d in code_detections if d.confidence in ['medium', 'high']]
        
        # Store warnings for display
        if filtered_detections:
            self.security_warnings.append({
                'file_path': file_path,
                'detections': filtered_detections
            })
        
        return sanitized_code, sanitized_diff
    
    def _sanitize_with_detections(self, text: str, detections: List, language: str, mode: str) -> tuple[str, List[str]]:
        """
        Sanitize text using pre-computed detections (avoids re-detecting).
        
        Args:
            text: Text to sanitize
            detections: Pre-computed InjectionDetection objects
            language: Programming language
            mode: Sanitization mode ('warn', 'redact', 'remove')
            
        Returns:
            Tuple of (sanitized_text, warnings)
        """
        warnings = []
        
        high_confidence = [d for d in detections if d.confidence == 'high']
        medium_confidence = [d for d in detections if d.confidence == 'medium']
        
        if not (high_confidence or medium_confidence):
            return text, warnings
        
        lines = text.split('\n')
        
        detections_by_line = {}
        for detection in high_confidence + medium_confidence:
            if detection.line_number not in detections_by_line:
                detections_by_line[detection.line_number] = []
            detections_by_line[detection.line_number].append(detection)
        
        for line_num, line_detections in detections_by_line.items():
            idx = line_num - 1
            if idx >= len(lines):  # Safety check
                continue
                
            original_line = lines[idx]
            
            has_high = any(d.confidence == 'high' for d in line_detections)
            confidence = 'HIGH' if has_high else 'MEDIUM'
            
            patterns = [d.pattern_type for d in line_detections]
            contexts = [d.context for d in line_detections]
            
            warning = (f"Line {line_num} [{confidence} CONFIDENCE]: "
                      f"Detected {', '.join(set(patterns))} "
                      f"in {', '.join(set(contexts))}")
            warnings.append(warning)
            
            if mode == "redact":
                if has_high:
                    lines[idx] = f"# [REDACTED - INJECTION ATTEMPT] {original_line[:50]}..."
                else:
                    lines[idx] = f"# [FLAGGED - REVIEW REQUIRED]\n{original_line}"
            
            elif mode == "warn":
                warning_comment = f"# [SECURITY] Line {line_num}: {', '.join(set(patterns))}"
                lines[idx] = f"{warning_comment}\n{original_line}"
            
            elif mode == "remove":
                if has_high:
                    lines[idx] = f"# [REMOVED - HIGH RISK]"
        
        sanitized_text = '\n'.join(lines)
        return sanitized_text, warnings
    
    def _display_security_warnings(self):
        """
        Display security warnings if any were detected
        """
        if not self.security_warnings:
            return
        
        self.console.print("\n[bold red]🔒 SECURITY WARNINGS DETECTED[/bold red]\n")
        
        for warning in self.security_warnings:
            file_path = warning['file_path']
            detections = warning['detections']
            
            self.console.print(f"[bold yellow]⚠️  {file_path}[/bold yellow]")
            
            for detection in detections:
                confidence = detection.confidence.upper()
                pattern_type = detection.pattern_type
                snippet = detection.matched_text[:100] + "..." if len(detection.matched_text) > 100 else detection.matched_text
                
                if detection.confidence == 'high':
                    color = 'red'
                    emoji = '🔴'
                elif detection.confidence == 'medium':
                    color = 'yellow'
                    emoji = '🟡'
                else:
                    continue  # Skip low confidence
                
                warning_text = f"[{color}]{emoji} {confidence} confidence - {pattern_type}[/{color}]\n"
                warning_text += f"[dim]Line {detection.line_number} ({detection.context}): {snippet}[/dim]"
                
                self.console.print(Panel(
                    warning_text,
                    border_style=color,
                    padding=(0, 2)
                ))
            
            self.console.print()
        
        self.console.print(Panel(
            "[bold red]⚠️  POTENTIAL PROMPT INJECTION DETECTED[/bold red]\n\n"
            "The code contains patterns that may be prompt injection attempts.\n"
            "These patterns have been sanitized before analysis.\n\n"
            "[dim]If these are legitimate code patterns, you can disable guardrails with --no-guardrails[/dim]",
            border_style="red",
            padding=(1, 2)
        ))
        self.console.print()
    
    async def review_staged_changes(self) -> List[FileReviewResult]:
        """
        Review all staged changes (ASYNC with parallel agent execution).
        
        Returns:
            List of FileReviewResult for each changed file
        """
        self.console.print("\n[bold cyan]🚀 Analyzing staged changes...[/bold cyan]\n")
        
        try:
            changes = self.git_repo.get_staged_changes()
        except Exception as e:
            self.console.print(f"[red]❌ Error getting staged changes: {e}[/red]")
            return []
        
        if not changes:
            self.console.print("[yellow]⚠️  No staged changes found.[/yellow]")
            self.console.print("[dim]Tip: Use 'git add <file>' to stage changes[/dim]")
            return []
        
        self.console.print(f"[green]✓ Found {len(changes)} file(s) to review[/green]\n")
        
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
                    # new file so get entire content
                    code = self.git_repo.get_full_file_content(change.file_path)
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
                
                diff = change.diff
                
                # Apply security guardrails
                sanitized_code, sanitized_diff = self._apply_guardrails(
                    change.file_path, code, diff
                )
                
                # Review with multi-agent system (streaming, async, parallel)
                final_state = None
                async for update in stream_multi_agent_review(
                    file_path=change.file_path,
                    code=sanitized_code,
                    diff=sanitized_diff,
                    llm=self.llm,
                    change_type=change.change_type.value
                ):
                    node_name = list(update.keys())[0] if update else "unknown"
                    final_state = update.get(node_name, {})
                
                # Store result
                result = FileReviewResult(
                    file_path=change.file_path,
                    change_type=change.change_type,
                    review_state=final_state,
                    lines_changed=len(change.added_lines) + len(change.removed_lines)
                )
                results.append(result)
                
                progress.update(task, description=f"[green]✓[/green] {change.file_path}")
        
        return results
    
    def display_results(self, results: List[FileReviewResult]):
        """
        Display review results in a beautiful format (Multi-Agent)
        
        Args:
            results: List of file review results
        """
        if not results:
            return
        
        self.console.print("\n" + "="*70 + "\n")
        self.console.print("[bold cyan]MACROMINI RESULTS[/bold cyan]\n")
        
        table = Table(title="Summary", show_header=True, header_style="bold magenta")
        table.add_column("File", style="cyan")
        table.add_column("Lines", justify="right")
        table.add_column("Score", justify="center")
        table.add_column("Issues", justify="center")
        table.add_column("Verdict", justify="center")
        
        total_issues = 0
        total_critical = 0
        
        for result in results:
            state = result.review_state
            deduplicated_issues = state.get("deduplicated_issues", [])
            score = state.get("final_score", 0)
            verdict = state.get("verdict", "unknown")
            
            critical_count = sum(
                1 for issue in deduplicated_issues 
                if issue.get("severity", "").lower() == "critical"
            )
            
            if score < 5:
                score_str = f"[green]{score}[/green]"
            elif score < 15:
                score_str = f"[yellow]{score}[/yellow]"
            else:
                score_str = f"[red]{score}[/red]"
            
            if verdict == "approve":
                verdict_str = "[green]✓ APPROVE[/green]"
            elif verdict == "comment":
                verdict_str = "[yellow]⚠ COMMENT[/yellow]"
            else:
                verdict_str = "[red]✗ REJECT[/red]"
            
            table.add_row(
                result.file_path,
                str(result.lines_changed),
                score_str,
                str(len(deduplicated_issues)),
                verdict_str
            )
            
            total_issues += len(deduplicated_issues)
            total_critical += critical_count
        
        self.console.print(table)
        self.console.print()
        
        for result in results:
            state = result.review_state
            deduplicated_issues = state.get("deduplicated_issues", [])
            summary_info = state.get("summary", {})
            
            if not deduplicated_issues:
                continue
            
            self.console.print(f"\n[bold cyan]📄 {result.file_path}[/bold cyan]")
            
            # Show aggregation stats with deduplication info
            if summary_info:
                original_count = summary_info.get('original_issues', 0)
                dedup_savings = summary_info.get('deduplication_savings', 0)
                agents_list = ', '.join(summary_info.get('agents_run', []))
                
                stats_text = f"[dim]Agents: {agents_list} | Issues: {summary_info.get('total_issues', 0)}"
                
                if dedup_savings > 0:
                    stats_text += f" (merged {dedup_savings} duplicate{'s' if dedup_savings > 1 else ''})"
                
                stats_text += "[/dim]\n"
                self.console.print(stats_text)
            
            for i, issue in enumerate(deduplicated_issues, 1):
                severity = issue.get("severity", "info").lower()
                
                if severity == "critical":
                    emoji = "🔴"
                    color = "red"
                elif severity == "high":
                    emoji = "🟡"
                    color = "yellow"
                elif severity == "medium":
                    emoji = "🟠"
                    color = "orange1"
                else:
                    emoji = "🔵"
                    color = "blue"
                
                # Show which agents found this issue (may be multiple after deduplication)
                found_by = issue.get("found_by_agents", [issue.get("agent", "unknown")])
                agent_count = issue.get("agent_count", 1)
                
                if agent_count > 1:
                    agent_text = f"Found by: {', '.join(found_by)} ({agent_count} agents agree)"
                else:
                    agent_text = f"Found by: {found_by[0]}"
                
                issue_text = f"[bold]{issue.get('type', 'unknown').upper()}[/bold] - {severity.upper()}\n"
                issue_text += f"[dim]{agent_text}[/dim]\n\n"
                
                line_num = issue.get("line_number")
                if line_num:
                    issue_text += f"📍 Line {line_num}\n\n"
                
                issue_text += f"[bold]Problem:[/bold]\n{issue.get('description', 'No description')}\n\n"
                
                # Show related concerns if multiple agents found similar issues
                related = issue.get("related_concerns", [])
                if related:
                    issue_text += f"[bold]Related Concerns:[/bold]\n"
                    for concern in related:
                        issue_text += f"  • {concern}\n"
                    issue_text += "\n"
                
                issue_text += f"[bold]Suggestion:[/bold]\n{issue.get('suggestion', 'No suggestion')}"
                
                code_snippet = issue.get("code_snippet")
                if code_snippet:
                    issue_text += f"\n\n[bold]Code:[/bold]\n[dim]{code_snippet}[/dim]"
                
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
    
    async def run(self) -> bool:
        """
        Run the complete code review workflow (ASYNC).
        
        Returns:
            True if review passes (no critical issues), False otherwise
        """
        # Check Ollama connection
        self.console.print("[cyan]Checking Ollama connection...[/cyan]")
        try:
            # Test connection by making a simple call (async)
            await self.llm.ainvoke("test")
            self.console.print("[green]✓ Connected to Ollama[/green]")
        except Exception as e:
            self.console.print(f"\n[red]Cannot connect to Ollama: {e}[/red]")
            self.console.print("[yellow]Make sure Ollama is running:[/yellow]")
            self.console.print("[dim]  ollama serve[/dim]\n")
            return False
        
        # Display security warnings before review
        self._display_security_warnings()
        
        results = await self.review_staged_changes()
        
        if not results:
            return True 
        
        passed = self.display_results(results)
        
        return passed
    
#CLI entry point for standalone testing
if __name__ == "__main__":
    import sys
    
    console = Console()
    
    console.print("\n[bold cyan]MACROmini - Multi-Agent Code Review and Orchestration[/bold cyan]")
    console.print("[dim]Phase 2: Powered by Ollama + LangGraph + 5 Specialist Agents[/dim]\n")
    
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