# Runbook: payment-gateway

Operational runbook for payment-gateway, which wraps the external card
processor API and is called by checkout-service during order finalization.

## Known failure mode: upstream card processor latency

Symptom: payment-gateway's own p99 latency rises, specifically in the
`processor.charge` span, while payment-gateway's internal CPU/memory look
normal. This is almost always the external card processor being slow, not a
bug in payment-gateway.

Mitigation:
1. Check the processor's public status page.
2. If confirmed upstream, there is no code fix — communicate expected
   duration to dependent teams (notably checkout-service) so they can decide
   whether to fail fast or queue-and-retry.

## Known failure mode: connection pool exhaustion talking to processor

Symptom: `payment-gateway_outbound_pool_in_use` metric pinned at max,
`processor.charge` spans show most of their duration waiting to acquire a
connection rather than in the actual network call. Distinguish from the
upstream-latency case above by checking whether the *processor's own*
reported latency (in their status page / support channel) is elevated — if
not, this is a local pool sizing issue, not the processor.

Mitigation:
1. Increase `PROCESSOR_POOL_MAX_SIZE`.
2. Check for a recent change to the outbound HTTP client configuration.
