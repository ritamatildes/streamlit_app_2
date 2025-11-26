#!/bin/bash
# Source the default bashrc first
if [ -f ~/.bashrc ]; then
    source ~/.bashrc
fi

# Try to activate venv if it exists
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
    echo "🐍 Virtual environment activated!"
else
    echo "💡 No virtual environment found. Run 'setup-venv' to create one!"
fi
