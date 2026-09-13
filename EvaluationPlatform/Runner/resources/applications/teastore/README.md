# TeaStore

Evaluation-owned Kustomize packaging of
[DescartesResearch/TeaStore](https://github.com/DescartesResearch/TeaStore).

Upstream publishes two Kubernetes examples: Ribbon (client-side load balancing
with `USE_POD_IP`) and ClusterIP. This tree uses **ClusterIP**, matching Online
Boutique and TeaStore's Helm default (`clientside_loadbalancer: false`). Every
service has a Kubernetes Service; pods register the Service DNS name, and kube
load-balancing replaces Ribbon.

```text
kustomize/
├── base/                         # One Deployment+Service per microservice
├── overlays/canonical-six-node/  # role=services, soft spread, HPA
└── overlays/cpu-constrained-six-node/
```

`teastore-webui` is the storefront (six replicas, HPA 6–30). The other
replicated services start at two replicas. `teastore-db` stays at one replica
because the bundled MySQL image is not clustered, and it opts out of Istio
injection.

Optional browser access uses NodePort 30081 on `teastore-webui-external` so it
does not collide with Online Boutique's 30080.

The Locust journey lives in `resources/applications/teastore.py` and follows TeaStore's
example login / browse / cart / checkout paths.
