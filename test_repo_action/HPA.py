import logging
from math import ceil
from typing import Optional

from kubernetes import client
from kubernetes.client import ApiregistrationV1Api, V1DeploymentList
from robusta.api import *
import time



class ScaleHPAParams(ActionParams):
    """
    :var max_replicas: New max_replicas to set this HPA to.
    """

    max_replicas: int

class HPALimitParams(ActionParams):
    """
    :var increase_pct: Increase the HPA max_replicas by this percentage.
    """

    increase_pct: int = 20



@action
def scale_hpa_callback(event: HorizontalPodAutoscalerEvent, params: ScaleHPAParams):
    """
    Update the max_replicas of this HPA to the specified value.

    Usually used as a callback action, when the HPA reaches the max_replicas limit.
    """
    hpa = event.get_horizontalpodautoscaler()
    if not hpa:
        logging.info(f"scale_hpa_callback - no hpa on event: {event}")
        return

    hpa.spec.maxReplicas = params.max_replicas
    hpa.replaceNamespacedHorizontalPodAutoscaler(hpa.metadata.name, hpa.metadata.namespace)
    finding = Finding(
        title=f"Max replicas for HPA *{hpa.metadata.name}* "
        f"in namespace *{hpa.metadata.namespace}* updated to: *{params.max_replicas}*",
        severity=FindingSeverity.INFO,
        source=FindingSource.PROMETHEUS,
        aggregation_key="scale_hpa_callback",
    )
    event.add_finding(finding)


@action
def scale_hpa_callback_2(event: HorizontalPodAutoscalerEvent, params: ScaleHPAParams):
    """
    Update the max_replicas of this HPA to the specified value.

    Usually used as a callback action, when the HPA reaches the max_replicas limit.
    """
    hpa = event.get_horizontalpodautoscaler()
    if not hpa:
        logging.info(f"scale_hpa_callback - no hpa on event: {event}")
        return

    hpa.spec.maxReplicas = params.max_replicas
    hpa.replaceNamespacedHorizontalPodAutoscaler(hpa.metadata.name, hpa.metadata.namespace)
    finding = Finding(
        title=f"Max replicas for HPA *{hpa.metadata.name}* "
        f"in namespace *{hpa.metadata.namespace}* updated to: *{params.max_replicas}*",
        severity=FindingSeverity.INFO,
        source=FindingSource.PROMETHEUS,
        aggregation_key="scale_hpa_callback_2",
    )
    event.add_finding(finding)


@action
def alert_on_hpa_reached_limit_2(event: HorizontalPodAutoscalerChangeEvent, action_params: HPALimitParams):
    """
    Notify when the HPA reaches its maximum replicas and allow fixing it.
    """
    logging.info(f"running alert_on_hpa_reached_limit: {event.obj.metadata.name} ns: {event.obj.metadata.namespace}")

    hpa = event.obj
    if hpa.status.currentReplicas == event.old_obj.status.currentReplicas:
        return  # run only when number of replicas change

    if hpa.status.desiredReplicas != hpa.spec.maxReplicas:
        return  # didn't reached max replicas limit

    avg_cpu = int(hpa.status.currentCPUUtilizationPercentage)
    new_max_replicas_suggestion = ceil((action_params.increase_pct + 100) * hpa.spec.maxReplicas / 100)

    param=ScaleHPAParams(
        max_replicas=new_max_replicas_suggestion,
    )
    
    
    kubernetes_object=hpa
    


    finding = Finding(
        title=f"HPA-TEST *{event.obj.metadata.name}* in namespace *{event.obj.metadata.namespace}* reached max replicas: *{hpa.spec.maxReplicas}*",
        severity=FindingSeverity.LOW,
        source=FindingSource.KUBERNETES_API_SERVER,
        aggregation_key="alert_on_hpa_reached_limit_2",
    )

    finding.add_enrichment(
        [
            MarkdownBlock(f"On average, pods scaled under this HPA are using *{avg_cpu} %* of the requested cpu."),
            # CallbackBlock(CallbackChoice),
            scale_hpa_callback_2(event, param)

        ]
    )
    event.add_finding(finding)