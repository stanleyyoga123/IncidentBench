kubectl apply -f Agents/RCAAgent/kubernetes/configmap.yaml
kubectl apply -f Agents/RemediatorAgent/kubernetes/configmap.yaml
kubectl apply -f Agents/LearningAgent/kubernetes/configmap.yaml
kubectl rollout restart deployment/rca-agent -n agents
kubectl rollout restart deployment/remediator-agent -n agents
kubectl rollout restart deployment/learning-agent -n agents
