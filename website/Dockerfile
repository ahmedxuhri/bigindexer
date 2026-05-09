FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm ci --omit=dev

# Copy application files
COPY server.js ./
COPY public ./public

# Expose port
EXPOSE 3000

# Start server directly with node
CMD ["/bin/sh", "-c", "node server.js"]
