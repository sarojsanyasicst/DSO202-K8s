# Deployment resources

| Folder | Purpose | Plan milestone |
| --- | --- | --- |
| `kind/` | Named local cluster, node topology, loopback port mappings | P07 |
| `platform/` | Validated version matrix and infrastructure settings | P01, P07, P10, P11 |
| `plain/` | Explicit Kubernetes resources used before Helm | P07–P09 |
| `helm/cloudcart/` | Application chart equivalent to the plain resources | P10 |
| `gitops/` | Argo CD project/application definitions | P10 |

These folders are placeholders. No usable YAML or Helm chart is present. Preserve the five application components, local storage limits, and explicit deployment ownership described in the [design](../docs/superpowers/specs/2026-10-16-cloudcart-design.md).
