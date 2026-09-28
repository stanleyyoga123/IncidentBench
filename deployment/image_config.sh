#!/usr/bin/env bash
# Shared image naming for component builds and Kubernetes deployment.

validate_image_settings() {
  if [[ -z "${IMAGE_REGISTRY:-}" || -z "${IMAGE_TAG:-}" ]]; then
    echo "Error: set IMAGE_REGISTRY and IMAGE_TAG for first-party images." >&2
    return 1
  fi

  # Registry may be a Docker Hub namespace or a registry host with a port and
  # namespace. Reject shell/YAML metacharacters and image tags in this field.
  if [[ ! "$IMAGE_REGISTRY" =~ ^[a-z0-9]+([._-][a-z0-9]+)*(:[0-9]+)?(/[a-z0-9]+([._-][a-z0-9]+)*)*$ ]]; then
    echo "Error: IMAGE_REGISTRY must be a lowercase registry or namespace path, optionally with a host port." >&2
    return 1
  fi
  if [[ ! "$IMAGE_TAG" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]*$ ]] || (( ${#IMAGE_TAG} > 128 )); then
    echo "Error: IMAGE_TAG must be a Docker tag (1-128 letters, digits, dots, underscores, or hyphens)." >&2
    return 1
  fi
}

image_ref() {
  printf '%s/%s:%s\n' "$IMAGE_REGISTRY" "$1" "$IMAGE_TAG"
}

render_image_manifest() {
  local manifest="$1" component="$2" marker image
  marker="incidentbench.invalid/${component}:configure-me"
  image="$(image_ref "$component")"
  if ! grep -Fq "$marker" "$manifest"; then
    echo "Error: expected image marker $marker in $manifest." >&2
    return 1
  fi
  # Only the known first-party image reference is replaced. Secrets and other
  # manifest values are never expanded from the shell environment.
  awk -v marker="$marker" -v image="$image" '
    {
      at = index($0, marker)
      if (at != 0) {
        $0 = substr($0, 1, at - 1) image substr($0, at + length(marker))
      }
      print
    }
  ' "$manifest"
}
