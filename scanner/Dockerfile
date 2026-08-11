FROM python:3.11-alpine

ARG SKILL_SCANNER_VERSION=1.0.2

WORKDIR /app

COPY backports/apply_1_0_2_llm_base_url_backport.py /tmp/apply_1_0_2_llm_base_url_backport.py
COPY backports/apply_1_0_2_llm_failure_backport.py /tmp/apply_1_0_2_llm_failure_backport.py

RUN apk add --no-cache --virtual .build-deps gcc musl-dev libffi-dev && \
    pip install --no-cache-dir \
    "cisco-ai-skill-scanner==${SKILL_SCANNER_VERSION}" \
        "litellm==1.90.2" && \
    python /tmp/apply_1_0_2_llm_base_url_backport.py /usr/local/lib/python3.11/site-packages && \
    python /tmp/apply_1_0_2_llm_failure_backport.py /usr/local/lib/python3.11/site-packages && \
    rm /tmp/apply_1_0_2_llm_base_url_backport.py /tmp/apply_1_0_2_llm_failure_backport.py && \
    apk del .build-deps && \
    addgroup -S app && \
    adduser -S app -G app && \
    mkdir -p /tmp/skillhub-scans && \
    chown app:app /tmp/skillhub-scans

USER app

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s \
  CMD wget -qO- http://127.0.0.1:8000/health || exit 1

CMD ["skill-scanner-api", "--host", "0.0.0.0", "--port", "8000"]
