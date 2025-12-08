#!/bin/bash
# Install Git hooks for MACROmini

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get repository root
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)

if [ -z "$REPO_ROOT" ]; then
    echo "Not in a Git repository"
    exit 1
fi

echo -e "${GREEN}Installing MACROmini Git hooks...${NC}"

# Create .git/hooks directory if it doesn't exist
mkdir -p "$REPO_ROOT/.git/hooks"

# Copy pre-commit hook
cp "$REPO_ROOT/hooks/pre-commit" "$REPO_ROOT/.git/hooks/pre-commit"

# Make it executable
chmod +x "$REPO_ROOT/.git/hooks/pre-commit"

echo -e "${GREEN}Pre-commit hook installed successfully!${NC}"
echo ""
echo "The hook will now run automatically before each commit."
echo -e "${YELLOW}To bypass the hook (emergency only): git commit --no-verify${NC}"
