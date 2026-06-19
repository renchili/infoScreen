FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    git \
    nodejs \
    npm \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /repo

COPY ci/requirements-dev.txt /tmp/requirements-dev.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements-dev.txt

CMD ["bash", "ci/run_all.sh"]
