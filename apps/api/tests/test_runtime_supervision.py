from datetime import UTC, datetime, timedelta

import pytest
from hypervisor.models import ExecutionRing
from hypervisor.rings.breach_detector import RingBreachDetector
from hypervisor.security.rate_limiter import AgentRateLimiter

from app.runtime_supervision import (
    ActionSpec,
    ExecutionTier,
    LocalRuntimeSupervisor,
    MicrosoftAgentHypervisorProvider,
    SupervisionConfigurationError,
    SupervisionElevationError,
)


@pytest.mark.asyncio
async def test_local_provider_is_portable_and_reports_unsupported_elevation():
    provider = LocalRuntimeSupervisor()
    handle = await provider.start(
        task_id="TASK-LOCAL",
        agent_id="did:local:developer",
        trust_score=0.5,
        phases=[],
    )

    decision = await provider.before_action(
        handle,
        ActionSpec(capability="filesystem.write"),
    )

    assert decision.allowed is True
    assert provider.capabilities.dynamic_rings is False
    with pytest.raises(SupervisionConfigurationError, match="does not support TTL elevation"):
        await provider.elevate(
            handle,
            target_tier=ExecutionTier.PRIVILEGED,
            ttl_seconds=60,
            reason="test",
        )


@pytest.mark.asyncio
async def test_microsoft_provider_runs_supervised_saga_and_commits_audit():
    provider = MicrosoftAgentHypervisorProvider()
    phases = [{"id": "intake"}, {"id": "implementation"}]
    handle = await provider.start(
        task_id="TASK-MS",
        agent_id="did:local:developer",
        trust_score=0.8,
        phases=phases,
    )

    decision = await provider.before_action(
        handle,
        ActionSpec(capability="filesystem.write",
                   undo_api="workbench://restore"),
    )
    transition = await provider.transition(handle, phase_id="intake")
    result = await provider.terminate(handle, reason="manual")

    assert handle.tier is ExecutionTier.STANDARD
    assert decision.allowed is True
    assert decision.required_tier is ExecutionTier.STANDARD
    assert transition.saga_id == handle.workflow_id
    assert result.terminated is True
    assert result.compensation_triggered is True
    assert result.audit_commitment is not None
    assert result.evidence["audit_commitment_source"] == "autodev_terminal_evidence"
    assert provider.hypervisor.get_session(handle.session_id) is not None
    assert handle.session_id not in provider.hypervisor._active_ids
    managed = provider.hypervisor.get_session(handle.session_id)
    saga = managed.saga.get_saga(handle.workflow_id)
    assert saga.steps[0].state.value == "compensated"


@pytest.mark.asyncio
async def test_microsoft_provider_applies_ttl_elevation_to_action_check():
    provider = MicrosoftAgentHypervisorProvider()
    handle = await provider.start(
        task_id="TASK-ELEVATE",
        agent_id="did:local:reviewer",
        trust_score=0.9,
        phases=[{"id": "approval"}],
    )

    grant = await provider.elevate(
        handle,
        target_tier=ExecutionTier.PRIVILEGED,
        ttl_seconds=60,
        reason="approved release action",
        attestation="reviewer:approved",
    )
    decision = await provider.before_action(
        handle,
        ActionSpec(capability="pull_request.create", reversible=False),
    )

    assert grant.elevated_tier is ExecutionTier.PRIVILEGED
    assert decision.allowed is True
    assert decision.agent_tier is ExecutionTier.PRIVILEGED


@pytest.mark.asyncio
async def test_microsoft_provider_normalizes_elevation_denial():
    provider = MicrosoftAgentHypervisorProvider()
    handle = await provider.start(
        task_id="TASK-ELEVATION-DENIED",
        agent_id="did:local:reviewer",
        trust_score=0.9,
        phases=[{"id": "approval"}],
    )

    with pytest.raises(SupervisionElevationError, match="no_sponsorship"):
        await provider.elevate(
            handle,
            target_tier=ExecutionTier.PRIVILEGED,
            ttl_seconds=60,
            reason="missing reviewer attestation",
        )


@pytest.mark.asyncio
async def test_microsoft_provider_expires_ttl_elevation():
    provider = MicrosoftAgentHypervisorProvider()
    handle = await provider.start(
        task_id="TASK-EXPIRED",
        agent_id="did:local:reviewer",
        trust_score=0.9,
        phases=[{"id": "approval"}],
    )
    grant = await provider.elevate(
        handle,
        target_tier=ExecutionTier.PRIVILEGED,
        ttl_seconds=60,
        reason="short release window",
        attestation="reviewer:approved",
    )
    provider.elevation_manager._elevations[grant.grant_id].expires_at = (
        datetime.now(UTC) - timedelta(seconds=1)
    )

    with pytest.raises(Exception, match="insufficient for required ring"):
        await provider.before_action(
            handle,
            ActionSpec(capability="pull_request.create", reversible=False),
        )


@pytest.mark.asyncio
async def test_microsoft_provider_enforces_per_ring_rate_limit():
    limiter = AgentRateLimiter(
        ring_limits={ExecutionRing.RING_2_STANDARD: (0.0, 1.0)}
    )
    provider = MicrosoftAgentHypervisorProvider(
        rate_limiter=limiter,
        breach_detector=RingBreachDetector(baseline_rate=1_000_000_000.0),
    )
    handle = await provider.start(
        task_id="TASK-RATE",
        agent_id="did:local:developer",
        trust_score=0.8,
        phases=[{"id": "implementation"}],
    )
    action = ActionSpec(capability="filesystem.write")

    await provider.before_action(handle, action)
    with pytest.raises(Exception, match="exceeded rate limit"):
        await provider.before_action(handle, action)


@pytest.mark.asyncio
async def test_microsoft_provider_demotes_and_holds_repeated_ring_escalation():
    provider = MicrosoftAgentHypervisorProvider(
        breach_detector=RingBreachDetector(baseline_rate=0.01),
    )
    handle = await provider.start(
        task_id="TASK-BREACH",
        agent_id="did:local:developer",
        trust_score=0.8,
        phases=[{"id": "implementation"}],
    )
    action = ActionSpec(
        capability="pull_request.create",
        read_only=False,
        reversible=False,
    )

    with pytest.raises(Exception, match="insufficient for required ring"):
        await provider.before_action(handle, action)
    with pytest.raises(Exception, match="circuit breaker tripped"):
        await provider.before_action(handle, action)

    managed = provider.hypervisor.get_session(handle.session_id)
    participant = managed.sso.get_participant(handle.agent_id)
    assert participant.ring is ExecutionRing.RING_3_SANDBOX
    with pytest.raises(Exception, match="circuit breaker tripped"):
        await provider.before_action(handle, action)


@pytest.mark.asyncio
async def test_microsoft_provider_does_not_trip_breaker_for_same_tier_writes():
    provider = MicrosoftAgentHypervisorProvider(
        breach_detector=RingBreachDetector(baseline_rate=0.01),
    )
    handle = await provider.start(
        task_id="TASK-WRITE-BURST",
        agent_id="did:local:developer",
        trust_score=0.8,
        phases=[{"id": "implementation"}],
    )
    action = ActionSpec(capability="filesystem.write", read_only=False)

    for _ in range(5):
        decision = await provider.before_action(handle, action)
        assert decision.allowed is True

    assert provider.breach_detector.is_breaker_tripped(
        handle.agent_id, handle.session_id
    ) is False


@pytest.mark.asyncio
async def test_microsoft_provider_does_not_trip_breaker_for_burst_reads():
    provider = MicrosoftAgentHypervisorProvider(
        breach_detector=RingBreachDetector(baseline_rate=0.01),
    )
    handle = await provider.start(
        task_id="TASK-READ-BURST",
        agent_id="did:local:architect",
        trust_score=0.7,
        phases=[{"id": "assessment"}],
    )
    action = ActionSpec(capability="repository.read", read_only=True)

    for _ in range(5):
        decision = await provider.before_action(handle, action)
        assert decision.allowed is True

    assert provider.breach_detector.is_breaker_tripped(
        handle.agent_id, handle.session_id
    ) is False
