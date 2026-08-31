FROM python:3.12-slim

ARG KUBECTL_VERSION=v1.30.4
ARG HELM_VERSION=v3.16.1
ARG TARGETARCH

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl openssh-client postgresql-client tmux \
    && case "${TARGETARCH:-amd64}" in \
        amd64) KUBECTL_ARCH=amd64 ;; \
        arm64) KUBECTL_ARCH=arm64 ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${KUBECTL_ARCH}/kubectl" -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl \
    && curl -fsSL "https://get.helm.sh/helm-${HELM_VERSION}-linux-${KUBECTL_ARCH}.tar.gz" -o /tmp/helm.tar.gz \
    && tar -xzf /tmp/helm.tar.gz -C /tmp \
    && mv "/tmp/linux-${KUBECTL_ARCH}/helm" /usr/local/bin/helm \
    && chmod +x /usr/local/bin/helm \
    && rm -rf /tmp/helm.tar.gz "/tmp/linux-${KUBECTL_ARCH}" \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

COPY Evaluation/requirements.txt .
RUN pip install -r requirements.txt

COPY Evaluation /app
COPY Infrastructure /infrastructure
COPY MCPTools/kubernetes/application-role-binding.yaml /MCPTools/kubernetes/application-role-binding.yaml
RUN chmod +x \
    /app/run.sh \
    /app/run_single.sh \
    /app/run_tc.sh \
    /app/cleanup_chaos_state.sh \
    /app/prerun/run.sh \
    /app/prerun/cleanup.sh \
    /app/testbed/run.sh \
    /app/postrun/run.sh

ENTRYPOINT ["/app/run.sh"]
CMD ["--help"]
