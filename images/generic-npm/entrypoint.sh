#!/bin/sh
set -e

# Default port to 3000 if not set
export PORT=${PORT:-3000}

# Install dependencies if package.json exists and we need to
if [ -f "package.json" ]; then
    if [ ! -d "node_modules" ] || [ package.json -nt node_modules ]; then
        echo "Dependencies missing or package.json updated. Installing dependencies..."
        npm install
    else
        echo "Dependencies up to date."
    fi
else
    echo "Warning: No package.json found in $(pwd)"
fi

# Run the command passed to the container
exec "$@"
