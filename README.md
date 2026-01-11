# MACROmini - Multi-Agent Code Review and Orchestration (mini)

![LOGO](images/logo.png)

### A local, privacy-first AI code review system that automatically analyzes Git staged changes using **5 specialized AI agents** running in parallel. 

Powered by LangGraph, Ollama, and Qwen2.5-Coder.


---

## What It Does

MACROmini uses **5 specialized AI agents** that work in parallel to analyze your code:

### **Security Agent** (Always Active)
- Detects SQL injection, XSS, command injection
- Finds hardcoded secrets, API keys, passwords
- Identifies weak authentication and authorization
- Checks for insecure cryptography and dependencies

### **Quality Agent** (Code Files)
- Identifies code smells and anti-patterns
- Measures cyclomatic complexity
- Detects duplicated code and maintainability issues
- Enforces SOLID principles

### **Performance Agent** (Code Files)
- Spots inefficient algorithms (O(n²) when O(n) possible)
- Detects N+1 query problems
- Finds memory leaks and unnecessary allocations
- Identifies blocking operations and race conditions

### **Style Agent** (Docs/Config/Web Files)
- Reviews markdown documentation quality
- Validates JSON/YAML/TOML configuration
- Checks HTML semantics and accessibility
- Audits CSS organization and best practices

### **Testing Agent** (Test Files)
- Analyzes test coverage gaps
- Identifies test anti-patterns (flaky tests, hard-coded sleeps)
- Reviews test quality (clear assertions, AAA structure)
- Suggests missing edge case tests

### **Key Features**
- **Smart Routing**: Only relevant agents analyze each file type
- **Parallel Execution**: All agents run simultaneously (3-4x faster)
- **Intelligent Deduplication**: Merges overlapping issues from multiple agents
- **Git Integration**: Blocks commits with critical issues via pre-commit hook
- **100% Local**: All analysis runs on your machine - no data leaves your system

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│              Developer Workflow                 │
│           git commit -m "message"               │
└───────────────────┬─────────────────────────────┘
                    ↓
            ┌───────────────┐
            │  Pre-commit   │
            │   Git Hook    │
            └───────┬───────┘
                    ↓
        ┌───────────────────────┐
        │   Code Reviewer       │
        │   (reviewer.py)       │
        └───────┬───────────────┘
                ↓
    ┌──────────────────────────┐
    │                          │
    ↓                          ↓
┌─────────────┐         ┌──────────────────────┐
│  Git Utils  │         │  LangGraph Workflow  │
│             │         │  (graph.py)          │
└─────────────┘         └──────────┬───────────┘
                                   ↓
                        ┌──────────────────────┐
                        │   Router Node        │
                        │ (Smart Agent         │
                        │  Selection)          │
                        └──────────┬───────────┘
                                   ↓
        ┌──────────────────────────┴──────────────────────┐
        │              Parallel Agent Execution           │
        │                                                 │
    ┌───▼───┐  ┌────▼────┐  ┌─────▼─────┐  ┌───▼───┐  ┌───▼────┐
    │Security│ │ Quality │  │Performance│  │ Style │  │Testing │
    │ Agent  │ │  Agent  │  │   Agent   │  │ Agent │  │ Agent  │
    └───┬───┘  └────┬────┘  └─────┬─────┘  └───┬───┘  └───┬────┘
        │           │             │            │          │
        └───────────┴─────────────┴────────────┴──────────┘
                                  ↓
                        ┌─────────┴────────┐
                        │   Aggregator     │
                        │ (Deduplication & │
                        │   Scoring)       │
                        └─────────┬────────┘
                                  ↓
                        ┌─────────┴────────┐
                        │  Final Results   │
                        │  with Verdict    │
                        └──────────────────┘
```

---

## Quick Start

### Installation

#### Option 1: From PyPI (Recommended)

```bash
pip install macromini
```

#### Option 2: From Source (For Development)

```bash
git clone https://github.com/chirpishere/macromini.git
cd macromini
pip install -e .
```

### Prerequisites

- **Python 3.10+** (tested on 3.13)
- **Ollama** installed and running
- **Qwen2.5-Coder:7b** model downloaded
- **Git** repository

### 1. Install Ollama

```bash
# macOS (Homebrew)
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama server
ollama serve

# In another terminal, download the model (~4.7GB)
ollama pull qwen2.5-coder:7b
```

### 2. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/chirpishere/macromini.git
cd macromini

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Install Git Hook

```bash
# Run the installation script
./install-hooks.sh

# Or manually:
cp hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

### 4. Test It Out

```bash
# Make some changes to your code
echo "def login(user, pwd): return f'SELECT * FROM users WHERE name={user}'" > test.py

# Stage the changes
git add test.py

# Try to commit - the multi-agent system will run!
git commit -m "Add test function"

# Expected Output:
# 🔍 MACROmini - Multi-Agent Code Review
# ✓ Router completed
# ✓ Security agent completed (found SQL injection!)
# ✓ Quality agent completed (found complexity issues)
# ✓ Performance agent completed
# 
# 📊 RESULTS: REJECT (Critical issues found)
# Fix issues before committing!
```

---

## Project Structure

```
MACROmini/
├── macromini/
│   ├── __init__.py
│   ├── __main__.py                 # Entry point for macromini
│   ├── cli.py                      # Command Line Interface for macromini
│   ├── reviewer.py                 # Main orchestrator & CLI
│   ├── git_utils.py                # Git operations and diff parsing
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base_agent.py           # Abstract agent with LLM logic
│   │   ├── security_agent.py       # Security vulnerability detection
│   │   ├── quality_agent.py        # Code quality analysis
│   │   ├── performance_agent.py    # Performance optimization
│   │   ├── style_agent.py          # Documentation/config style
│   │   └── testing_agent.py        # Test coverage & quality
│   ├── orchestration/
│   │   ├── __init__.py
│   │   ├── state.py                # ReviewState TypedDict
│   │   ├── router.py               # Smart agent selection
│   │   ├── graph.py                # LangGraph workflow
│   │   └── aggregator.py           # Result merging & deduplication
│   ├── security/
│   │   ├── __init__.py
│   │   ├── input_sanitizer.py      # Guardrails to sanitize prompt injections
├── hooks/
│   └── pre-commit                  # Git hook template
├── testfiles/                      # Test files (not tracked)
├── requirements.txt                # Python dependencies
├── .gitignore                      # Files to ignore
├── install-hooks.sh                # Hook installation script
├── pyproject.toml                  # Configures the build system
├── MANIFEST.in                     # Includes non-Python files
├── LICENSE                         # MIT License
└── README.md                       # This file
```

---

## Usage

### Manual Review (Without Committing)

```bash
# Activate virtual environment
source venv/bin/activate

# Stage your changes
git add src/auth.py

# Run reviewer manually   (you might need to change import paths in code for standalone testing)
python src/reviewer.py

# You'll see:
# - Real-time progress as agents complete
# - Which agents analyzed which files
# - Deduplicated results
# - Final verdict
```

### Automatic Review (Via Git Hook)

```bash
# Normal workflow - hook runs automatically
git add src/auth.py
git commit -m "Add authentication"

# If critical issues found:
# ❌ Commit blocked! Fix the 1 critical issue(s).

# After fixing:
git add src/auth.py
git commit -m "Add authentication (fixed SQL injection)"
# ✅ Code review passed! Proceeding with commit.
```

### Using Different Models

```bash
# Use a different Ollama model (default: qwen2.5-coder:7b)
macromini --model deepseek-coder:6.7b

# Use a larger model for more thorough reviews
macromini --model codellama:34b

# Use a faster, smaller model
macromini --model qwen2.5-coder:1.5b
```

### Disabling Security Guardrails

```bash
# Disable prompt injection detection (not recommended)
macromini --no-guardrails

# Combine with custom model
macromini --model deepseek-coder:6.7b --no-guardrails

# Specify repository path and disable guardrails
macromini --repo-path /path/to/repo --no-guardrails
```

### Bypass Hook (Emergency Only)

```bash
# Skip the review hook
git commit --no-verify -m "Emergency hotfix"

# shorter alternative
git commit -n -m "Emergency hotfix"
```

**⚠️ Use bypass sparingly** - only for emergencies, WIP commits, or when you're confident the code is safe.

---

### Using as a Python Library

```python
from macromini import CodeReviewer

# Initialize reviewer
reviewer = CodeReviewer(
    repo_path=".",
    model="qwen2.5-coder:7b"
)

# Run review and get result
passed = reviewer.run()

if passed:
    print("✅ Code review passed!")
else:
    print("❌ Code review failed - fix issues before committing")
```

### Command-Line Options

After installation via pip, use the `macromini` command:

```bash
# Basic usage (reviews current directory)
macromini

# Specify repository path
macromini --repo-path /path/to/your/repo

# Use different model
macromini --model gpt-4o-mini

# Show version
macromini --version

# Show help
macromini --help
```

---

## Configuration

### Current Configuration

- **Model**: `qwen2.5-coder:7b`
- **Temperature**: `0` (deterministic)
- **Retry**: 3 attempts with exponential backoff
- **Context**: 10 lines before/after changes
- **Severity Weights**: Critical=20, High=10, Medium=5, Low=2, Info=1
- **Verdict Thresholds**: Approve(<5), Comment(5-15), Reject(>15 or critical)

### Customization

You can modify agent behavior by editing the system prompts in each agent file.

You can also modify the temperature, code context and other scoring/deduplicating defaults.

---

## Troubleshooting

### Review takes too long (>5 minutes)

**Possible causes:**
1. **Model not loaded**: First run loads model into memory (~30s)
2. **Large files**: LLM processes more context
3. **Complex code**: Agents spend more time analyzing

**Solutions:**
```bash
# Pre-load the model
ollama run qwen2.5-coder:7b "hello"

# Review smaller changesets
git add specific-file.py  # Instead of git add .

# Check if Ollama has enough resources
# Recommended: 8GB+ RAM, 4GB VRAM for GPU acceleration
```

### Agents finding too many false positives

**Solution:**
Adjust System prompts for that specific agent.

### "JSON parsing failed" errors

**Solution:**
Retry checks have been added to force json output. 
Test LLM output explicitly to figure out what the output format it.

(The most common error here is that json response appears between markdown blocks. I have fixed that, since this was the only error I noticed. Feel free to tune it according to your needs.)

---

## Dependencies

Core libraries (see `requirements.txt`):

### LangChain Ecosystem
- **langchain** (0.3.7) - LLM application framework
- **langchain-ollama** (0.2.0) - Ollama integration
- **langchain-core** (0.3.15) - Core abstractions
- **langgraph** (0.2.45) - Multi-agent orchestration with state graphs

### Git & Data
- **gitpython** (3.1.43) - Git repository operations
- **pydantic** (2.9.2) - Data validation and parsing

### UI & Utilities
- **rich** (13.9.4) - Beautiful terminal output
- **requests** (2.32.3) - HTTP client for Ollama API
- **pyyaml** (6.0.2) - Configuration parsing (future use)
- **python-dotenv** (1.0.1) - Environment variables (future use)

---

## Privacy & Security

**All analysis happens locally:**
- ✅ Code never leaves your machine
- ✅ No cloud APIs or external services
- ✅ Ollama runs on localhost
- ✅ Complete control over your data

**Note:** The LLM (Qwen2.5-Coder) runs entirely on your hardware. No code is sent to external servers.

---

## Star History

If you find this project useful, please consider giving it a star! ⭐

---

## 📧 Contact

- **Author**: Sharvil Chirputkar (sharvilchirputkar@gmail[dot]com)
- **GitHub**: [@chirpishere](https://github.com/chirpishere)
- **Project**: [MACROmini](https://github.com/chirpishere/macromini)

For questions, feedback, or collaboration, feel free to open an issue!

---

**Built with trust for local, privacy-first AI code review**

