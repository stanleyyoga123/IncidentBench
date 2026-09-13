# Evaluation applications

This directory is the ownership boundary for deployable workloads used by the
evaluation runner.

Each application directory owns its profile, installation source or source
contract, placement policy, namespace, endpoint, and workload-selection rules.
Application-specific Locust journeys live in the matching underscore-named
Python module at this directory's root.

```text
applications/
├── online-boutique/
│   ├── profile.yaml
│   └── kustomize/
├── online_boutique.py
├── sock-shop/
│   ├── profile.yaml
│   └── kustomize/
├── sock_shop.py
├── teastore/
│   ├── profile.yaml
│   └── kustomize/
└── teastore.py
```

Infrastructure must not contain application Deployment, Service, HPA, Helm, or
Kustomize manifests. It owns only the Kubernetes cluster and shared platform
prerequisites.

Profile `loadgenerator_module` values use `resources.applications.<module>`.
Installer `source_default` paths are relative to the workspace root; bundled
paths begin with `EvaluationPlatform/Runner/resources/applications/`. Relative
`placement.root` paths are resolved from `resources/`, for example
`applications/teastore/placements`.
