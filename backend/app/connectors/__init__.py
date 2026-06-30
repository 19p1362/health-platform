"""HealthBridge Platform — EHR Connectors Module

Provides abstract and concrete implementations for connecting to
external Electronic Health Record (EHR) systems including:
- ABDM (Ayushman Bharat Digital Mission)
- OpenMRS (Open Medical Record System)
- Generic FHIR R4 servers
"""

from app.connectors.base import BaseEHRConnector, ConnectionStatus
from app.connectors.abdm import ABDMConnector
from app.connectors.openmrs import OpenMRSConnector
from app.connectors.fhir_standard import FHIRStandardConnector

__all__ = [
    "BaseEHRConnector",
    "ConnectionStatus",
    "ABDMConnector",
    "OpenMRSConnector",
    "FHIRStandardConnector",
]
