# Architecture: Checkout Flow

Overview of the services involved when a user completes checkout.

## Request path

1. `frontend` calls `checkout-service` POST `/checkout`.
2. `checkout-service` validates the cart, then calls `inventory-service` to
   reserve stock, then calls `payment-gateway` to authorize payment, then
   writes the order to its own Postgres database, then calls
   `notification-service` (fire-and-forget) to send a confirmation email.
3. `payment-gateway` calls the external card processor API and returns an
   authorization result to `checkout-service`.

## Database

`checkout-service` owns a Postgres database (`checkout_db`) accessed via a
connection pool (SQLAlchemy `QueuePool`, default max size 20, configurable
via `DB_POOL_MAX_SIZE`). All request handlers are expected to release their
session back to the pool via a `try/finally` in the request middleware;
handlers that open a session outside the standard request lifecycle (e.g.
background tasks) must close it explicitly.

## Timeouts and circuit breakers

`checkout-service`'s client for `payment-gateway` has a circuit breaker
(opens after 5 consecutive failures or timeouts within 30s) and a
configurable per-call timeout (`PAYMENT_GATEWAY_TIMEOUT_MS`, default 2000ms).
`inventory-service` calls use a 500ms timeout with 2 retries.
