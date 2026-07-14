#!/bin/sh
set -e

# Default port to 3000 if not set
export PORT=${PORT:-3000}

# Pull latest code if PULL_REPO is set
if [ -n "$PULL_REPO" ]; then
    echo "PULL_REPO is set. Pulling latest code..."
    git pull
fi

# Install dependencies if package.json exists and we need to
if [ -f "package.json" ]; then
    if [ ! -d "node_modules" ] || [ ! -f "/app/.install-done" ] || [ package.json -nt /app/.install-done ]; then
        echo "Dependencies missing or package.json updated. Installing dependencies..."
        npm install && touch /app/.install-done
    else
        echo "Dependencies up to date."
    fi
else
    echo "Warning: No package.json found in $(pwd)"
fi

# Run the command passed to the container
exec "$@"
