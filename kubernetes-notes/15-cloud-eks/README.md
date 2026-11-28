# 15 — Cloud Kubernetes (EKS focus, AKS, GKE)

> 💸 **Cost warning:** an EKS control plane is billed per hour, plus EC2 nodes, NAT gateways, load balancers, EBS volumes and data
> transfer. Labs here cost real money. Always run the **cleanup** section, and set an AWS Budget alert before starting.

## 1. Managed Kubernetes — what you get

| | Self-managed (kubeadm) | Managed (EKS/AKS/GKE) |
|--|------------------------|-----------------------|
| Control plane (API, etcd, scheduler) | you run, patch, back up, scale | provider runs it across AZs, SLA |
| Upgrades | manual kubeadm | one-click/API (you still upgrade nodes & add-ons) |
| Worker nodes | yours | managed node groups / autoprovisioning / serverless (Fargate, Autopilot) |
| Integrations | DIY | IAM, LBs, storage, logging built in |

**Shared responsibility:** provider secures the control plane; **you** own RBAC, workloads, node patching (unless fully managed
modes), network policies, IAM permissions, add-on versions, and cost.

## 2. EKS architecture

```text
 AWS-managed VPC                                      Your VPC (10.0.0.0/16) — 3 AZs
 ┌───────────────────────────────┐                   ┌───────────────────────────────────────────────────┐
 │ EKS control plane (multi-AZ)  │  cross-account    │ public subnets: NAT GW, internet-facing NLB/ALB    │
 │ API servers + etcd            │◄═ENIs in your ═══►│ private subnets: worker nodes (EC2 / Fargate)       │
 │ endpoint: public/private/both │  subnets          │   Pods get VPC IPs from ENIs (Amazon VPC CNI)       │
 └───────────────────────────────┘                   │ add-ons: vpc-cni, coredns, kube-proxy, pod identity │
                                                     │   agent, EBS CSI, AWS Load Balancer Controller       │
                                                     └───────────────────────────────────────────────────┘
```

### Worker node options

| Option | Who manages | Use |
|--------|-------------|-----|
| Managed node groups | AWS manages ASG lifecycle/AMI updates (you trigger) | default choice |
| Self-managed nodes | you | custom AMIs/bootstrap |
| **Karpenter** | Karpenter (you run it) | flexible, cost-optimised autoscaling |
| **EKS Auto Mode** | AWS (Karpenter-based, plus managed core add-ons, LB, storage) | least ops |
| Fargate | AWS (serverless Pod per micro-VM) | isolation, no nodes; no DaemonSets/hostPath/GPUs |

AMIs: Amazon Linux 2023 (AL2 EKS AMIs are deprecated), Bottlerocket (minimal, immutable).

## 3. EKS networking

- **Amazon VPC CNI** (`aws-node` DaemonSet): each Pod gets a **real VPC IP** (secondary IPs on ENIs). Pros: native routing, LBs can
  target Pods directly, security groups see Pod IPs. Cons: IP consumption.
- **Max Pods per node** depends on ENIs × IPs per ENI (e.g. `m5.large` = 29 without prefix delegation). **Prefix delegation**
  (`ENABLE_PREFIX_DELEGATION=true`) assigns /28 prefixes → many more Pods per node.
- IP exhaustion fixes: larger subnets, prefix delegation, **custom networking** with secondary CIDR `100.64.0.0/10`, IPv6 clusters.
- **Security groups for Pods** (branch ENIs) for per-Pod SG rules (e.g. RDS access).
- **NetworkPolicy**: VPC CNI includes a network policy agent (enable it), or use Calico/Cilium.
- Egress: Pods → NAT gateway (SNAT by VPC CNI for non-VPC destinations, `AWS_VPC_K8S_CNI_EXTERNALSNAT`).

## 4. IAM integration

### Humans → cluster: access entries (✅) instead of the `aws-auth` ConfigMap (⚠️ deprecated)

```bash
aws eks create-access-entry --cluster-name lab --principal-arn arn:aws:iam::111122223333:role/DevOpsRole
aws eks associate-access-policy --cluster-name lab --principal-arn arn:aws:iam::111122223333:role/DevOpsRole \
  --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy --access-scope type=cluster
aws eks update-kubeconfig --name lab --region us-east-1     # kubeconfig uses `aws eks get-token` exec plugin
```

Map IAM principals to Kubernetes groups via access entries + RBAC for namespace-scoped access.

### Pods → AWS APIs: EKS Pod Identity (✅) or IRSA

| | IRSA | EKS Pod Identity |
|--|------|------------------|
| Mechanism | OIDC provider + SA annotation `eks.amazonaws.com/role-arn`; projected token exchanged via STS | Pod Identity Agent DaemonSet + `PodIdentityAssociation` API |
| Setup per cluster | OIDC provider, trust policy per cluster | trust `pods.eks.amazonaws.com` once; reuse roles across clusters |
| Works on | EKS, self-managed | EKS (not Fargate at time of writing) |

**Never** put AWS access keys in Secrets. Block IMDS from Pods (IMDSv2 hop limit 1) so Pods can't use the node role.

## 5. Hands-on: create an EKS cluster with eksctl

### Tools

```bash
# AWS CLI v2
curl -sSLo awscliv2.zip "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip"
unzip -q awscliv2.zip && sudo ./aws/install && rm -rf aws awscliv2.zip    # sudo: installs into /usr/local
aws --version
aws configure sso          # or aws configure — use an IAM Identity Center / role, not root credentials
aws sts get-caller-identity
# eksctl
ARCH=amd64; PLATFORM=$(uname -s)_$ARCH
curl -sLO "https://github.com/eksctl-io/eksctl/releases/latest/download/eksctl_${PLATFORM}.tar.gz"
tar -xzf eksctl_${PLATFORM}.tar.gz -C /tmp && rm eksctl_${PLATFORM}.tar.gz
sudo install -m 0755 /tmp/eksctl /usr/local/bin && eksctl version
```

### Cluster config (`eks-lab.yaml`)

```yaml
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
metadata:
  name: lab
  region: us-east-1
  version: "1.34"                 # pick a currently supported EKS version
vpc:
  cidr: 10.0.0.0/16
  nat:
    gateway: Single               # one NAT GW to save cost (HighlyAvailable = one per AZ for prod)
  clusterEndpoints:
    publicAccess: true            # lab; prod: private + restricted publicAccessCIDRs
    privateAccess: true
accessConfig:
  authenticationMode: API         # access entries only
addons:
  - name: vpc-cni
    configurationValues: '{"env":{"ENABLE_PREFIX_DELEGATION":"true"},"enableNetworkPolicy":"true"}'
  - name: coredns
  - name: kube-proxy
  - name: eks-pod-identity-agent
  - name: aws-ebs-csi-driver
    podIdentityAssociations:
      - serviceAccountName: ebs-csi-controller-sa
        namespace: kube-system
        permissionPolicyARNs: ["arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"]
managedNodeGroups:
  - name: general
    instanceTypes: ["t3.large", "t3a.large"]
    spot: true                    # lab cost saving; use on-demand for critical prod capacity
    minSize: 2
    desiredCapacity: 2
    maxSize: 4
    privateNetworking: true       # nodes in private subnets
    amiFamily: AmazonLinux2023
    labels: { role: general }
    iam:
      withAddonPolicies:
        cloudWatch: true
cloudWatch:
  clusterLogging:
    enableTypes: ["api", "audit", "authenticator"]
```

```bash
eksctl create cluster -f eks-lab.yaml          # ~15–20 min: CloudFormation stacks for VPC, control plane, node group
kubectl get nodes -o wide                      # INTERNAL-IP from private subnets
kubectl get pods -A
eksctl get addons --cluster lab
kubectl -n kube-system get ds aws-node -o yaml | grep -A1 PREFIX
kubectl get node -o jsonpath='{.items[0].status.allocatable.pods}'; echo   # max Pods (higher with prefix delegation)
```

### Storage: default gp3 StorageClass

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp3
  annotations: { storageclass.kubernetes.io/is-default-class: "true" }
provisioner: ebs.csi.aws.com
parameters: { type: gp3, encrypted: "true" }
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
reclaimPolicy: Delete
```

EBS = RWO, zonal. For RWX use **EFS CSI**. S3 via Mountpoint for S3 CSI.

### Load balancers: AWS Load Balancer Controller

```bash
LBC_VERSION=v2.13.4    # check https://github.com/kubernetes-sigs/aws-load-balancer-controller/releases
curl -sLo iam_policy.json https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/${LBC_VERSION}/docs/install/iam_policy.json
aws iam create-policy --policy-name AWSLoadBalancerControllerIAMPolicy --policy-document file://iam_policy.json
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
eksctl create podidentityassociation --cluster lab --namespace kube-system \
  --service-account-name aws-load-balancer-controller --role-name AmazonEKSLBControllerRole-lab \
  --permission-policy-arns arn:aws:iam::${ACCOUNT_ID}:policy/AWSLoadBalancerControllerIAMPolicy
helm repo add eks https://aws.github.io/eks-charts && helm repo update
VPC_ID=$(aws eks describe-cluster --name lab --query cluster.resourcesVpcConfig.vpcId --output text)
helm install aws-load-balancer-controller eks/aws-load-balancer-controller -n kube-system \
  --set clusterName=lab --set region=us-east-1 --set vpcId=$VPC_ID \
  --set serviceAccount.create=true --set serviceAccount.name=aws-load-balancer-controller
kubectl -n kube-system rollout status deploy/aws-load-balancer-controller
```

Subnet discovery tags (eksctl sets them): public `kubernetes.io/role/elb=1`, private `kubernetes.io/role/internal-elb=1`.

NLB for a Service (L4, IP targets):

```yaml
apiVersion: v1
kind: Service
metadata:
  name: web
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: external
    service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: ip
    service.beta.kubernetes.io/aws-load-balancer-scheme: internet-facing
spec:
  type: LoadBalancer
  selector: { app: web }
  ports: [{ port: 80, targetPort: 8080 }]
```

ALB for HTTP routing (Ingress class `alb`):

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: web
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP":80},{"HTTPS":443}]'
    alb.ingress.kubernetes.io/ssl-redirect: "443"
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:us-east-1:111122223333:certificate/abcd-1234   # ACM cert
    alb.ingress.kubernetes.io/group.name: shared-public     # share one ALB across many Ingresses (saves cost)
    alb.ingress.kubernetes.io/healthcheck-path: /healthz
spec:
  ingressClassName: alb
  rules:
    - host: shop.example.com
      http:
        paths:
          - { path: /, pathType: Prefix, backend: { service: { name: web, port: { number: 80 } } } }
```

```bash
kubectl get ingress web -w        # ADDRESS = k8s-sharedpublic-xxxx.us-east-1.elb.amazonaws.com
kubectl -n kube-system logs deploy/aws-load-balancer-controller | tail    # reconcile errors (IAM, subnets, cert)
```

Point DNS at it with Route 53 (manually or via **ExternalDNS** with Pod Identity).

## 6. Autoscaling on EKS

- HPA + metrics-server (`eksctl` can install the metrics-server add-on).
- **Karpenter** (recommended) or Cluster Autoscaler for nodes (chapter 09). Karpenter needs: controller IAM role (Pod Identity),
  node IAM role + access entry, SQS interruption queue, subnet/SG discovery tags.
- EKS Auto Mode handles node provisioning for you.

## 7. Security on EKS

- Private API endpoint (or `publicAccessCidrs`), access entries with least privilege, SSO roles.
- Pod Identity for workloads; IMDSv2 required with hop limit 1 on nodes.
- Secrets envelope encryption with KMS (default on newer clusters); External Secrets + Secrets Manager.
- PSA labels, NetworkPolicy (VPC CNI agent), security groups for Pods.
- ECR image scanning (enhanced = Inspector), signed images.
- GuardDuty EKS Protection / Runtime Monitoring; audit logs to CloudWatch.
- Keep EKS version within standard support (extended support costs extra per cluster-hour).

## 8. Monitoring on EKS

| Option | What |
|--------|------|
| CloudWatch Container Insights (add-on `amazon-cloudwatch-observability`) | node/Pod metrics, logs via Fluent Bit |
| Amazon Managed Service for Prometheus + Amazon Managed Grafana | managed Prometheus remote-write + Grafana |
| Self-hosted kube-prometheus-stack + Loki | chapter 11 |
| AWS X-Ray / ADOT (AWS Distro for OpenTelemetry) | traces |
| Control plane logs | api/audit/authenticator/controllerManager/scheduler → CloudWatch Logs |

## 9. Cost optimisation

1. **Right-size requests** (VPA recommendations, Kubecost/OpenCost) — requests drive node count.
2. **Karpenter consolidation** + mixed instance types + **Spot** for stateless/fault-tolerant workloads; Graviton (arm64) for
   ~20–40 % better price/performance.
3. **Savings Plans** for baseline on-demand capacity.
4. **Share load balancers** (ALB `group.name`, one Gateway) instead of one LB per Service.
5. **NAT gateway data** is expensive: VPC endpoints for ECR/S3/STS/CloudWatch; keep traffic in-AZ (topology-aware routing).
6. **Cross-AZ traffic** costs: `trafficDistribution: PreferClose`.
7. Scale non-prod to zero at night (KEDA cron, Karpenter limits); delete idle clusters.
8. Storage: gp3 over gp2, delete orphaned volumes/snapshots, lifecycle ECR images.
9. Log retention limits in CloudWatch.

## 10. AKS and GKE comparison

| | **EKS** | **AKS** | **GKE** |
|--|---------|---------|---------|
| Control plane cost | per-hour fee | free tier (no SLA) / standard tier with SLA | fee per cluster (free tier credit for one zonal/Autopilot) |
| Default CNI | Amazon VPC CNI (VPC IPs) | Azure CNI (overlay or Cilium-powered) / kubenet ⚠️ retiring | VPC-native + Dataplane V2 (Cilium/eBPF) |
| Node mgmt | managed node groups, Karpenter, Auto Mode, Fargate | node pools, Node Auto-Provisioning (Karpenter-based), virtual nodes | node pools, NAP, **Autopilot** (fully managed, per-Pod billing) |
| Identity for Pods | Pod Identity / IRSA | Microsoft Entra Workload ID | Workload Identity Federation |
| Human auth | IAM + access entries | Entra ID + Azure RBAC | Google IAM + RBAC |
| LB integration | AWS Load Balancer Controller (ALB/NLB) | Azure LB; App Gateway for Containers | Cloud Load Balancing; GKE Gateway controller |
| Storage | EBS, EFS, FSx, S3 CSI | Azure Disk, Azure Files, Blob CSI | Persistent Disk/Hyperdisk, Filestore |
| Monitoring | CloudWatch Container Insights, AMP/AMG | Azure Monitor, Managed Prometheus/Grafana | Cloud Monitoring/Logging, Managed Service for Prometheus |
| Upgrades | manual trigger; extended support paid | auto-upgrade channels | release channels with auto-upgrade |

```bash
# AKS quick start (Azure CLI)
az group create -n rg-lab -l eastus
az aks create -g rg-lab -n aks-lab --node-count 2 --network-plugin azure --network-plugin-mode overlay --network-dataplane cilium --generate-ssh-keys
az aks get-credentials -g rg-lab -n aks-lab
# GKE quick start (gcloud)
gcloud container clusters create-auto gke-lab --region us-central1     # Autopilot
gcloud container clusters get-credentials gke-lab --region us-central1
```

## 11. Cleanup (do this!)

```bash
kubectl delete ingress --all -A; kubectl delete svc --field-selector spec.type=LoadBalancer -A   # let the controller delete LBs first
sleep 60
helm uninstall aws-load-balancer-controller -n kube-system
eksctl delete cluster -f eks-lab.yaml --disable-nodegroup-eviction
aws elbv2 describe-load-balancers --query 'LoadBalancers[].LoadBalancerName'     # verify nothing left
aws ec2 describe-volumes --filters Name=status,Values=available --query 'Volumes[].VolumeId'   # orphaned EBS volumes
aws iam delete-policy --policy-arn arn:aws:iam::${ACCOUNT_ID}:policy/AWSLoadBalancerControllerIAMPolicy
```

Deleting LoadBalancer Services/Ingresses **before** the cluster matters: otherwise ALBs/NLBs and their security groups can be left
behind and block VPC deletion.

---

## Interview questions

1. **What does EKS manage vs you?** AWS: control plane & etcd HA/patching. You: nodes (unless Auto Mode/Fargate), add-ons, RBAC,
   workloads, networking policy, IAM.
2. **How do Pods get IPs on EKS?** VPC CNI assigns secondary IPs/prefixes from node ENIs — real VPC addresses.
3. **Why might a node only fit ~17–29 Pods?** ENI/IP limits per instance type; fix with prefix delegation.
4. **IRSA vs Pod Identity?** Both give Pods IAM roles via tokens; Pod Identity avoids per-cluster OIDC trust setup.
5. **aws-auth vs access entries?** ConfigMap mapping (deprecated, error-prone) vs managed API with IAM-auditable access policies.
6. **NLB vs ALB?** L4 TCP/UDP with static IPs/client IP preservation vs L7 HTTP routing with WAF/ACM integration.
7. **What is target-type ip?** LB sends directly to Pod IPs (no NodePort hop).
8. **How do you autoscale nodes on EKS?** Karpenter (or Cluster Autoscaler, or EKS Auto Mode).
9. **Top EKS cost drivers?** Nodes (over-requested), NAT data processing, LBs, cross-AZ traffic, extended support, logs.
10. **EKS vs GKE Autopilot vs AKS?** Similar managed control planes; differ in networking defaults, identity, node automation, pricing.

**Scenario:** Pods stuck `ContainerCreating` with "failed to assign an IP address" on EKS. → Subnet IP exhaustion or ENI limits; enable
prefix delegation, add subnets/secondary CIDR, use larger instances.

**Follow-ups:** How does Karpenter handle Spot interruptions? How would you design multi-account EKS networking (Transit Gateway,
shared VPC)? How do you upgrade EKS with zero downtime (control plane → add-ons → node groups with PDBs / blue-green node groups)?
