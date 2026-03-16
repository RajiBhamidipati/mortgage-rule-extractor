# ── Stage 1: Build frontend ──
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python backend + built frontend ──
FROM python:3.12-slim
WORKDIR /app

# Install backend dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy canonical dictionary and evals (needed at runtime)
COPY canonical/ ./canonical/
COPY evals/ ./evals/

# Copy built frontend into expected location
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Railway sets PORT env var
ENV PORT=8000
EXPOSE 8000

# Run from backend dir so relative imports work
WORKDIR /app/backend
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
