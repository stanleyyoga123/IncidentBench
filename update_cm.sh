kubectl apply -f RCAAgent/kubernetes/configmap.yaml 
kubectl apply -f RemediatorAgent/kubernetes/configmap.yaml
kubectl apply -f LearningAgent/kubernetes/configmap.yaml
kubectl rollout restart deployment/rca-agent -n agents
kubectl rollout restart deployment/remediator-agent -n agents
kubectl rollout restart deployment/learning-agent -n agents