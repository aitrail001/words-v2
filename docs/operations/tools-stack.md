# Tools Stack Setup

Use this after `make tools-up` or `make stack-build` when you want the admin database browser and Redis browser configured for the current stack.

## Prerequisites

1. Start the stack.
   ```bash
   make stack-build
   make tools-up
   ```
2. Confirm the services are healthy.
   ```bash
   make stack-ps
   ```

## pgAdmin

pgAdmin stores its server registrations in the named volume `words_pgadmin_data`, and the pgAdmin image bakes the Postgres connection definition into the container. The connection comes back automatically after a clean recreate, with no host bind mounts required for the tools stack.

1. Open pgAdmin at `http://localhost:5050`.
2. Log in with the credentials from `.env.stack.mac`:
   - email: `PGADMIN_EMAIL`
   - password: `PGADMIN_PASSWORD`
3. Expand the `Words Stack` server group.
4. Open `words-stack-postgres`.
5. Expand `Databases` to see the current databases:
   - `vocabapp_dev_full`
   - `vocabapp_test_full`
   - `vocabapp_test_template_full`
   - `vocabapp_test_template_smoke`

If pgAdmin ever starts without the connection, rebuild the tools image and restart the tools stack.

## Redis Commander

Redis Commander is preconfigured in `compose.tools.yml` with `REDIS_HOSTS=local:redis:6379` and stores its state in `words_redis_commander_data`.

1. Open Redis Commander at `http://localhost:8081`.
2. Confirm the `local` Redis connection is present.
3. If the connection is missing, stop and restart the tools stack:
   ```bash
   make tools-down
   make tools-up
   ```
4. The visible Redis endpoint should be:
   - host: `redis`
   - port: `6379`

## Verification

1. Reopen pgAdmin and confirm the Postgres server registration remains after a stack restart.
2. Reopen Redis Commander and confirm the `local` Redis connection remains after a stack restart.
3. If either UI loses its configuration after recreation, the named volume for that tool was not preserved.
