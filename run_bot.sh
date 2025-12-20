#!/bin/bash
#
# Multi-CEX-AMM Bot Launcher for Linux/macOS
#
# Usage:
#   ./run_bot.sh              - Run the bot
#   ./run_bot.sh --setup      - Set up virtual environment and install dependencies
#   ./run_bot.sh --help       - Show help message
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
PYTHON_MIN_VERSION="3.8"

print_banner() {
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║           MULTI-EXCHANGE AMM BOT                              ║"
    echo "║                                                               ║"
    echo "║   Exchanges: NonKYC | Bitstorage | Exbitron                   ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_help() {
    echo "Multi-CEX-AMM Bot Launcher"
    echo ""
    echo "Usage:"
    echo "  ./run_bot.sh              Run the bot"
    echo "  ./run_bot.sh --setup      Set up virtual environment and install dependencies"
    echo "  ./run_bot.sh --config     Create config.json from template"
    echo "  ./run_bot.sh --help       Show this help message"
    echo ""
    echo "Configuration:"
    echo "  1. Copy config.example.json to config.json"
    echo "  2. Edit config.json with your API credentials"
    echo "  3. Set 'enabled: true' for the exchanges you want to use"
    echo "  4. Run the bot with ./run_bot.sh"
    echo ""
}

check_python() {
    # Try to find Python 3
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        echo -e "${RED}Error: Python 3 is not installed.${NC}"
        echo "Please install Python 3.8 or higher from https://www.python.org/"
        exit 1
    fi

    # Check Python version
    PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PYTHON_MAJOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.major)')
    PYTHON_MINOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.minor)')

    if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 8 ]); then
        echo -e "${RED}Error: Python 3.8 or higher is required.${NC}"
        echo "Current version: $PYTHON_VERSION"
        exit 1
    fi

    echo -e "${GREEN}Found Python $PYTHON_VERSION${NC}"
}

setup_venv() {
    echo -e "${YELLOW}Setting up virtual environment...${NC}"

    if [ -d "$VENV_DIR" ]; then
        echo -e "${YELLOW}Virtual environment already exists at $VENV_DIR${NC}"
        read -p "Do you want to recreate it? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$VENV_DIR"
        else
            echo "Keeping existing virtual environment."
            return
        fi
    fi

    $PYTHON_CMD -m venv "$VENV_DIR"
    echo -e "${GREEN}Created virtual environment at $VENV_DIR${NC}"

    # Activate and install dependencies
    source "$VENV_DIR/bin/activate"

    echo -e "${YELLOW}Upgrading pip...${NC}"
    pip install --upgrade pip

    echo -e "${YELLOW}Installing dependencies...${NC}"
    if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
        pip install -r "$SCRIPT_DIR/requirements.txt"
    else
        pip install aiohttp
    fi

    echo -e "${GREEN}Setup complete!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Copy config.example.json to config.json"
    echo "  2. Edit config.json with your API credentials"
    echo "  3. Run: ./run_bot.sh"
}

create_config() {
    if [ -f "$SCRIPT_DIR/config.json" ]; then
        echo -e "${YELLOW}config.json already exists.${NC}"
        read -p "Do you want to overwrite it? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Keeping existing config.json"
            return
        fi
    fi

    if [ -f "$SCRIPT_DIR/config.example.json" ]; then
        cp "$SCRIPT_DIR/config.example.json" "$SCRIPT_DIR/config.json"
        echo -e "${GREEN}Created config.json from template.${NC}"
        echo "Please edit config.json with your API credentials."
    else
        echo -e "${RED}Error: config.example.json not found.${NC}"
        exit 1
    fi
}

run_bot() {
    # Activate virtual environment if it exists
    if [ -d "$VENV_DIR" ]; then
        source "$VENV_DIR/bin/activate"
        echo -e "${GREEN}Activated virtual environment${NC}"
    fi

    # Check if aiohttp is installed
    if ! $PYTHON_CMD -c "import aiohttp" 2>/dev/null; then
        echo -e "${RED}Error: aiohttp is not installed.${NC}"
        echo "Run: ./run_bot.sh --setup"
        exit 1
    fi

    # Check for config.json
    if [ ! -f "$SCRIPT_DIR/config.json" ]; then
        echo -e "${YELLOW}Warning: config.json not found.${NC}"
        echo "Using default configuration from amm_bot.py"
        echo "Run './run_bot.sh --config' to create a config file."
        echo ""
    fi

    # Run the bot
    cd "$SCRIPT_DIR"
    $PYTHON_CMD amm_bot.py "$@"
}

# Main entry point
print_banner
check_python

case "${1:-}" in
    --setup)
        setup_venv
        ;;
    --config)
        create_config
        ;;
    --help|-h)
        print_help
        ;;
    *)
        run_bot "$@"
        ;;
esac
