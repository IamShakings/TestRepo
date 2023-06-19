import re
from typing import List

import hikaru
from hikaru.meta import HikaruBase
from pydantic import SecretStr

from robusta.api import (
    ActionParams,
    GitRepoManager,
    K8sOperationType,
    KubernetesAnyChangeEvent,
    action,
    is_matching_diff,
    is_base64_encoded
)

# from robusta.api import *

import base64
import logging

test = """
apiVersion: autoscaling/v1
kind: HorizontalPodAutoscaler
metadata:
  labels:
    kustomize.toolkit.fluxcd.io/name: account-api-service-beta
    kustomize.toolkit.fluxcd.io/namespace: flux-system
  name: therma-account-api-service
  namespace: beta
  resourceVersion: "146686470"
  uid: 4782f6aa-2db5-4aea-ab2a-ddff64feeadb
spec:
  maxReplicas: 5
  minReplicas: 1
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: therma-account-api-service
  targetCPUUtilizationPercentage: 80
"""


class GitAuditParams(ActionParams):
    """
    :var cluster_name: This cluster name. Changes will be audited under this cluster name.
    :var git_url: Audit Git repository url.
    :var git_key: Git repository deployment key with *write* access. To set this up `generate a private/public key pair for GitHub <https://docs.github.com/en/developers/overview/managing-deploy-keys#setup-2>`_.
    :var ignored_changes: List of changes that shouldn't be audited.

    :example git_url: "git@github.com:arikalon1/robusta-audit.git"
    """

    def post_initialization(self):
        secret_key = self.git_key.get_secret_value()

        if is_base64_encoded(secret_key): 
            self.git_key = SecretStr(base64.b64decode(secret_key).decode("utf-8"))
        else:
            self.git_key = SecretStr(secret_key)

    cluster_name: str
    git_url: str
    git_key: SecretStr
    ignored_changes: List[str] = []

    def __str__(self):
        return f"cluster_name={self.cluster_name} git_url={self.git_url} git_key=*****"


def git_safe_name(name):
    return re.sub("[^0-9a-zA-Z\\-]+", "-", name)

def hpa_yaml(name,obj_yaml):
    hpa = f"""
    apiVersion: autoscaling/v1
    kind: HorizontalPodAutoscaler
    metadata:
    name: {name}
    {obj_yaml}
    """

# kinds with no 'spec'
skipped_kinds: List[str] = [
    "Event",
    "ClusterRole",
    "ClusterRoleBinding",
    "ServiceAccount",
    "ConfigMap"
]


def obj_diff(spec: HikaruBase, old_spec: HikaruBase, ignored_changes: List[str]) -> bool:
    if old_spec is None:
        return True

    all_diffs = spec.diff(old_spec)
    filtered_diffs = list(filter(lambda x: not is_matching_diff(x, ignored_changes), all_diffs))
    return len(filtered_diffs) > 0


@action
def git_push_changes(event: KubernetesAnyChangeEvent, action_params: GitAuditParams):
    """
    Audit Kubernetes resources from the cluster to Git as yaml files (cluster/namespace/resources hierarchy).
    Monitor resource changes and save it to a dedicated Git repository.

    Using this audit repository, you can easily detect unplanned changes on your clusters.
    """
    try:
        if event.obj.kind in skipped_kinds:
            return

        if len(event.obj.metadata.ownerReferences) != 0:
            return  # not handling runtime objects

        git_repo = GitRepoManager.get_git_repo(
            action_params.git_url,
            action_params.git_key.get_secret_value(),
        )
        logging.info(f"Key value: {action_params.git_key.get_secret_value()}")

        # git_repo.init_repo()

        name = f"{git_safe_name(event.obj.metadata.name)}.yaml" #therma-<services-name>
        namespace = event.obj.metadata.namespace or "None" # namespace
        # service_name = event.obj.metadata.labels.service # ex. account-service 
        # role = event.obj.metadata.labels.role # ex. api/consumer
        # path = f"{git_safe_name(action_params.cluster_name)}/{git_safe_name(namespace)}"
        
        new_name = name.partition('-')[2]
        findList = new_name
        if "api" in findList.lower():
            path = f"{git_safe_name(namespace)}/{'api'}/{git_safe_name(new_name)}/{'main'}/{'patches'}"  # ex. beta/api/account-service/main/patches
        else:
            path = f"{git_safe_name(namespace)}/{'consumer'}/{git_safe_name(new_name)}/{'main'}/{'patches'}"  # ex. beta/consumer/account-service/main/patches
        
        git_repo.pull_rebase()
        logging.info(f"Pulling possible changes")
        

        if event.operation == K8sOperationType.DELETE:
            git_repo.delete_push(path, name, f"Delete {path}/{name}", action_params.cluster_name)
        elif event.operation == K8sOperationType.CREATE:
            obj_yaml = hikaru.get_yaml(event.obj.spec)
    
            git_repo.commit_push(
                hpa_yaml.hpa(name,obj_yaml),
                path,
                name,
                f"Create {event.obj.kind} named {event.obj.metadata.name} on namespace {namespace}",
                action_params.cluster_name,
            )
        else:  # update
            old_spec = event.old_obj.spec if event.old_obj else None
            if obj_diff(event.obj.spec, old_spec, action_params.ignored_changes):  # we have a change in the spec
                obj_yaml = hikaru.get_yaml(event.obj.spec)
                    
                git_repo.commit_push(
                    # hikaru.get_yaml(event.obj.spec),
                    hpa_yaml.hpa(name,obj_yaml),
                    path,
                    name,
                    f"Update {event.obj.kind} named {event.obj.metadata.name} on namespace {namespace}",
                    action_params.cluster_name,
                )
    except Exception as e:
        logging.error("git audit error", exc_info=True)