FROM node:24-bookworm-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS web
WORKDIR /web
COPY apps/web/package*.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

FROM docker:27-cli@sha256:851f91d241214e7c6db86513b270d58776379aacc5eb9c4a87e5b47115e3065c AS dockercli
FROM python:3.11-slim-bookworm@sha256:528257d48c1da0dcecc2e725d1ae34498d60c965f1241e39cd6a85a8859bdf84
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=dockercli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
COPY apps/__init__.py apps/__init__.py
COPY apps/api/ apps/api/
COPY contracts/ contracts/
COPY installer/ installer/
COPY alembic/ alembic/
COPY zk/revenue_growth/ zk/revenue_growth/
RUN python -m pip install --no-cache-dir '.[postgres]'
COPY --from=web /web/dist/ apps/web/dist/
ENTRYPOINT []
CMD ["python", "-m", "installer.cli"]
