"""
Command-line interface for MACROmini.
Supports async execution for true parallel agent processing.
"""

import argparse
import sys
import asyncio
from pathlib import Path
from macromini.reviewer import CodeReviewer


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="MACROmini - Multi-Agent Code Review Orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--repo-path",
        type=str,
        default=".",
        help="Path to the git repository (default: current directory)",
    )
    
    parser.add_argument(
        "--model",
        type=str,
        default="qwen2.5-coder:7b",
        help="LLM model to use (default: qwen2.5-coder:7b)",
    )
    
    parser.add_argument(
        "--no-guardrails",
        action="store_true",
        help="Disable security guardrails for prompt injection detection",
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {get_version()}",
    )
    
    args = parser.parse_args()
    
    try:
        repo_path = Path(args.repo_path).resolve()
        reviewer = CodeReviewer(
            repo_path=str(repo_path),
            model=args.model,
            enable_guardrails=not args.no_guardrails,
        )
        
        print(f"🔍 Reviewing staged changes in: {repo_path}")
        print(f"📊 Using model: {args.model}")
        if args.no_guardrails:
            print("⚠️  Security guardrails disabled")
        print()
        
        # Run async code review
        passed = asyncio.run(reviewer.run())
        
        if passed:
            print("\n✅ Code review completed successfully!")
        else:
            print("\n❌ Code review found critical issues!")
            sys.exit(1)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def get_version():
    """Get the package version."""
    try:
        from macromini import __version__
        return __version__
    except ImportError:
        return "unknown"


if __name__ == "__main__":
    main()