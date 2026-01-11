"""
MACROmini - Multi-Agent Code Review Orchestration

A lightweight, intelligent code review system powered by multiple specialized AI agents.
"""

__version__ = "0.1.0"
__author__ = "Sharvil Chirputkar"
__email__ = "sharvilchirputkar@gmail.com"

from macromini.reviewer import CodeReviewer
from macromini.git_utils import GitRepository

__all__ = [
    "CodeReviewer",
    "GitRepository",
    "__version__",
]