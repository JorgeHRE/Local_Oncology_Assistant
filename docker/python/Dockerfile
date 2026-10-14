# Python environment for tests, linting and the project's tools, so nothing depends on the host's
# Python or a local .venv. The repo is mounted at /app by compose.yml; the editable install in
# this image points at /app/src, so code changes show up without rebuilding.
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[db,dev]"

CMD ["pytest"]
