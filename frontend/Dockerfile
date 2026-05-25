FROM node:20-alpine

# Set working directory
WORKDIR /app

# Install dependencies
COPY package.json package-lock.json* ./
RUN npm install

# Copy application code
COPY . .

# Expose Vite dev server port
EXPOSE 5173

# Start Vite dev server with host binding
CMD ["npm", "run", "dev"]
