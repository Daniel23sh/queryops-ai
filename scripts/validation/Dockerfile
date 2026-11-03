FROM node:22-bookworm-slim AS node
FROM python:3.12-slim-bookworm
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
WORKDIR /src
COPY backend/pyproject.toml backend/pyproject.toml
COPY backend/app backend/app
RUN pip install --no-cache-dir -e './backend[dev]'
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci && npx playwright install --with-deps chromium
COPY . .
ENV PYTHONUNBUFFERED=1 CI=1
CMD ["python", "scripts/validation/gate.py"]
