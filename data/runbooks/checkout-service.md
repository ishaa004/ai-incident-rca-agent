# Runbook: checkout-service

Operational runbook for the checkout-service, which handles cart finalization,
payment authorization, and order creation.

## Known failure mode: DB connection pool exhaustion

Symptom: p99 latency climbs sharply, followed by a burst of 5xx errors with
messages like "timeout waiting for connection from pool" or
"QueuePool limit of size N overflow M reached". Usually triggered by a
deploy that removes an explicit `.close()` on a DB session in a new code
path, or by a downstream dependency (e.g. payment-gateway) slowing down and
holding connections open longer than usual, causing the pool to back up.

Mitigation:
1. Check `checkout_service_db_pool_in_use` metric — if pinned at max pool
   size, this is very likely the cause.
2. Check recent deploys for changes touching database session handling.
3. Roll back the most recent deploy if it correlates with pool exhaustion
   onset.
4. As a stopgap, increase pool size via `DB_POOL_MAX_SIZE` env var and
   restart, but this only buys time — the underlying leak or slow dependency
   must still be fixed.

## Known failure mode: payment-gateway timeout cascade

Symptom: checkout-service p99 latency rises, trace spans show most of the
time spent in the `payment-gateway.authorize` span, and error rate rises on
checkout-service without a corresponding error rate rise on payment-gateway
itself (i.e. payment-gateway is slow, not erroring).

Mitigation:
1. Check payment-gateway's own dashboards for elevated latency.
2. Verify checkout-service's circuit breaker for payment-gateway calls is
   configured with a reasonable timeout (should be 2s, not the default 30s).
3. If payment-gateway is degraded, coordinate with the payments team;
   checkout-service cannot fix the root cause but can fail faster.

## Known failure mode: bad deploy / config error

Symptom: error rate jumps to near-100% immediately after a deploy, with no
gradual ramp. Usually a missing environment variable, a bad feature flag
default, or a schema migration that wasn't backward compatible with the
still-running previous version during rollout.

Mitigation:
1. Roll back immediately — do not try to hotfix forward during an active
   incident.
2. Confirm error rate drops to baseline within 2-3 minutes of rollback
   completing.
