from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCapabilities:
    dynamic_rings: bool = False
    ttl_elevation: bool = False
    saga_compensation: bool = False
    per_ring_rate_limits: bool = False
    breach_detection: bool = False
    kill_handoff: bool = False
    audit_commitment: bool = False
