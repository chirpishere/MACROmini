# MACROmini - Multi Agent Code Review and Ochestration (mini)

**Phase 1: Single-Agent Code Reviewer** 

A local, privacy-first AI code review system that automatically analyzes Git staged changes for security vulnerabilities, bugs, code quality issues, and performance problems using Ollama and Qwen2.5-Coder.

> ⚠️ **Note:** This is Phase 1 of the project - a functional single-agent code reviewer. Future phases will add multi-agent orchestration, RAG-based context awareness, and advanced intelligence features.

---

## 🎯 What It Does

- **Automatic Code Review**: Reviews all staged Git changes before commits
- **Security Analysis**: Detects SQL injection, XSS, insecure authentication, secrets in code
- **Bug Detection**: Finds logic errors, null pointer issues, race conditions
- **Quality Checks**: Identifies code smells, anti-patterns, maintainability issues
- **Performance Analysis**: Spots inefficient algorithms, memory leaks, N+1 queries
- **Style Review**: Checks formatting, naming conventions, documentation gaps
- **Git Integration**: Blocks commits with critical issues via pre-commit hook
- **100% Local**: All analysis runs on your machine - no data leaves your system

---

## 🏗️ Architecture (Phase 1)

```
┌─────────────────────────────────────────────────┐
│                 Developer                       │
│          git commit -m "message"                │
└───────────────────┬─────────────────────────────┘
                    ↓
            ┌───────────────┐
            │ Pre-commit    │
            │ Git Hook      │
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
┌─────────────┐         ┌──────────────┐
│ Git Utils   │         │  LLM Client  │
│ (git_utils) │         │ (llm_client) │
└──────┬──────┘         └──────┬───────┘
       ↓                       ↓
   ┌────────┐           ┌──────────┐
   │  Git   │           │  Ollama  │
   │  Repo  │           │  (Local) │
   └────────┘           └──────────┘
```

---

## Quick Start

### Prerequisites

- **Python 3.13+** (or 3.10+)
- **Ollama** installed and running
- **Qwen2.5-Coder:7b** model downloaded
- **Git** repository

### 1. Install Ollama

```bash
# macOS (Homebrew)
brew install ollama

# Start Ollama server
ollama serve

# In another terminal, download the model
ollama pull qwen2.5-coder:7b
```

### 2. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/chirpishere/macromini.git
cd macromini

# Create virtual environment
python -m venv venv

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
echo "def test(): pass" >> test.py

# Stage the changes
git add test.py

# Try to commit - the hook will run automatically!
git commit -m "Add test function"

# Output:
# Running MACROmini...
# Review Results
# ...
```

---

## 📁 Project Structure

```
macromini/
├── src/
│   ├── __init__.py
│   ├── llm_client.py      # Ollama LLM integration with LangChain
│   ├── git_utils.py       # Git operations and diff parsing
│   └── reviewer.py        # Main orchestrator for code review
├── hooks/
│   └── pre-commit         # Git hook template
├── config/
│   └── (future config files)
├── testfiles/             # Test files (not tracked)
├── requirements.txt       # Python dependencies
├── install-hooks.sh       # Hook installation script
└── README.md             # This file
```

---

## 🔧 Components (Phase 1)

### 1. **LLM Client** (`src/llm_client.py`)

- Uses **LangChain** framework for LLM integration
- Connects to **Ollama** running locally
- Structured output with **Pydantic** models
- Retry logic and fallback JSON parsing
- Returns: `ReviewResult` with issues, summary, score (0-10)

**Key Classes:**
- `OllamaCodeReviewer`: Main client
- `CodeIssue`: Individual issue (type, severity, line, description, suggestion)
- `ReviewResult`: Complete review with issues list and quality score

### 2. **Git Utilities** (`src/git_utils.py`)

- Wraps **GitPython** for repository operations
- Gets staged/unstaged changes with diffs
- Parses diff format to extract line numbers
- Handles edge cases: new repos, binary files, renamed files
- Returns: `FileChange` objects with diffs and context

**Key Methods:**
- `get_staged_changes()`: Files ready to commit
- `get_unstaged_changes()`: Working directory changes
- `get_file_content_with_context()`: Code with surrounding lines

### 3. **Code Reviewer** (`src/reviewer.py`)

- Orchestrates the review workflow
- Checks Ollama connection
- Processes each staged file through LLM
- Displays beautiful results with **Rich** library
- Returns exit codes: `0` (pass) or `1` (critical issues)

**Output:**
- Summary table: file, lines changed, score, issues count
- Detailed issue panels with severity indicators
- Final verdict: PASSED / WARNINGS / FAILED

### 4. **Pre-commit Hook** (`hooks/pre-commit`)

- Bash script that Git runs before commits
- Activates virtual environment
- Runs `reviewer.py` on staged changes
- Blocks commit if critical issues found
- Bypass option: `git commit --no-verify`

---

## 🎨 Example Output

```
🔍 Running MACROmini...

📊 Review Results
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
File                    Lines    Score    Issues    Critical
────────────────────────────────────────────────────────────────
auth.py                +15/-3   3/10     3         2
utils.py               +8/-2    7/10     2         0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 Critical Issue: SQL Injection Vulnerability
  File: auth.py, Line: 23
  Problem: User input directly interpolated into SQL query
  Fix: Use parameterized queries or an ORM

🟡 High Issue: Missing Error Handling
  File: utils.py, Line: 45
  Problem: No exception handling for file operations
  Fix: Wrap file operations in try-except blocks

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❌ REVIEW FAILED - CRITICAL ISSUES MUST BE FIXED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Please fix the issues above before committing.
To bypass (NOT recommended): git commit --no-verify
```

---

## 🛠️ Usage

### Manual Review (Without Committing)

```bash
# Activate virtual environment
source venv/bin/activate

# Stage your changes
git add file.py

# Run reviewer manually
python src/reviewer.py
```

### Automatic Review (Via Git Hook)

```bash
# Normal workflow - hook runs automatically
git add file.py
git commit -m "Add new feature"

# If critical issues found:
# ❌ Commit blocked! Fix issues first.

# After fixing:
git add file.py
git commit -m "Add new feature (fixed issues)"
# ✅ Code review passed! Proceeding with commit.
```

### Bypass Hook (Emergency Only)

```bash
# Skip the review hook
git commit --no-verify -m "Emergency hotfix"

# or shorter
git commit -n -m "Emergency hotfix"
```

**⚠️ Use bypass sparingly** - only for emergencies, WIP commits, or when you're confident the code is safe.

---

## ⚙️ Configuration (Future)

Phase 1 uses hardcoded settings. Future phases will add:

- `config/config.yaml` for project-wide settings
- Per-language rules and thresholds
- Custom severity levels
- Ignored patterns/files

---

## 🧪 Testing

### Test the Hook

```bash
# Create a test file with intentional issues
cat > test_bad.py << 'EOF'
def login(username, password):
    query = f"SELECT * FROM users WHERE username='{username}'"
    return execute_query(query)
EOF

# Stage and try to commit
git add test_bad.py
git commit -m "Test commit"

# Expected: Commit blocked with SQL injection warning
```

### Test Manual Review

```bash
# Test the LLM client directly
python src/llm_client.py

# Test Git utilities
python -c "from src.git_utils import GitRepository; repo = GitRepository(); print(repo.get_staged_changes())"
```

---

## 🐛 Troubleshooting

### "Connection failed: Could not connect to Ollama"

**Solution:**
```bash
# Make sure Ollama is running
ollama serve

# In another terminal, verify the model is installed
ollama list | grep qwen2.5-coder
```

### "Virtual environment not found"

**Solution:**
```bash
# Create the virtual environment
python -m venv venv

# Activate and install dependencies
source venv/bin/activate
pip install -r requirements.txt
```

### Hook not running

**Solution:**
```bash
# Verify hook is installed and executable
ls -la .git/hooks/pre-commit

# If missing, reinstall:
./install-hooks.sh

# Or manually:
cp hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

### "No module named 'langchain'"

**Solution:**
```bash
# Make sure you're in the virtual environment
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

---

## 📚 Dependencies

Core libraries (see `requirements.txt`):

- **langchain** (0.3.7) - LLM framework
- **langchain-ollama** (0.2.0) - Ollama integration
- **gitpython** (3.1.43) - Git operations
- **pydantic** (2.9.2) - Data validation
- **rich** (13.9.4) - Beautiful terminal output
- **pyyaml** (6.0.2) - Configuration parsing (future)
- **python-dotenv** (1.0.1) - Environment variables (future)
- **requests** (2.32.3) - HTTP client for Ollama API

---

## 🔐 Privacy & Security

**All analysis happens locally:**
- ✅ Code never leaves your machine
- ✅ No cloud APIs or external services
- ✅ Ollama runs on localhost
- ✅ Complete control over your data

**Note:** The LLM (Qwen2.5-Coder) runs entirely on your hardware. No code is sent to external servers.

---

## 🤝 Contributing

This is currently a personal learning project in Phase 1. Contributions will be welcome once the multi-agent architecture is implemented in Phase 2.

---

## 📝 License

MIT License - Feel free to use and modify for your own projects.

---

## 🙏 Acknowledgments

- **Ollama** - Local LLM inference
- **Qwen2.5-Coder** - Excellent code-focused LLM
- **LangChain** - LLM application framework
- **Rich** - Beautiful terminal output

---

## 📧 Contact

For questions or feedback: sharvilchirputkar@gmail.com

---

**Built with ❤️ for local, privacy-first AI code review**

*Last updated: December 7, 2024 - Phase 1 Complete*
