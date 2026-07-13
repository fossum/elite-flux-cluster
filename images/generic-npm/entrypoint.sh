#!/bin/sh
set -e

# Default port to 3000 if not set
export PORT=${PORT:-3000}

# Install dependencies if package.json exists
if [ -f "package.json" ]; then
    echo "Found package.json. Installing dependencies..."
    npm install
else
    echo "Warning: No package.json found in $(pwd)"
fi

# Run the command passed to the container
exec "$@"
