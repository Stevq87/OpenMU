"""Keep unit tests hermetic: ambient KUBECONFIG must not leak into the app singleton."""

import os

for key in (
    "KUBECONFIG",
    "SAAS_KUBECONFIG",
    "KUBE_CONTEXT",
    "SAAS_KUBE_CONTEXT",
    "SAAS_K8S_API_SERVER",
):
    os.environ.pop(key, None)
