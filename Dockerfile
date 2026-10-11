FROM python:3.12-slim AS build
WORKDIR /build
RUN pip install --no-cache-dir build
COPY pyproject.toml ./
COPY src ./src
RUN python -m build --wheel --outdir /dist

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
LABEL org.opencontainers.image.source=https://github.com/CravenCraven/fsi-scraper
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin scraper
RUN --mount=type=bind,from=build,source=/dist,target=/dist \
    pip install --no-cache-dir /dist/*.whl
    
RUN mkdir -p /corpus && chown scraper:scraper /corpus
USER scraper
WORKDIR /corpus
ENTRYPOINT ["fsi-scraper"]
CMD ["--help"]
