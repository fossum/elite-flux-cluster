FROM node:lts-alpine

# Install some useful build tools just in case native deps are needed
RUN apk add --no-cache python3 make g++ git

# Set working directory
WORKDIR /app

# Copy the entrypoint script
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Default command to run
# We check if there's a dev script, if not run start, if not node server.js
CMD ["sh", "-c", "if [ -f package.json ]; then if grep -q '\"dev\"' package.json; then npm run dev; elif grep -q '\"start\"' package.json; then npm start; else node server.js; fi; else node server.js; fi"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
