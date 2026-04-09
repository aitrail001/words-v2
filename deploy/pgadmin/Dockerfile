FROM dpage/pgadmin4:latest

USER root

COPY --chown=5050:0 docs/operations/pgadmin/servers.json /pgadmin4/servers.json
COPY --chown=5050:0 docs/operations/pgadmin/pgpass /var/lib/pgadmin/pgpass

RUN chmod 600 /var/lib/pgadmin/pgpass
