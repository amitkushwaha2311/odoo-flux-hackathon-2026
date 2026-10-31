# =============================================================================
# Brightloop Subscription Intelligence — Production Dockerfile
# Based on official Odoo 20.0 Community Edition
# =============================================================================

FROM odoo:20.0

LABEL maintainer="Brightloop <team@brightloop.io>"
LABEL description="Brightloop Subscription Intelligence on Odoo 20.0 Community"

# Switch to root to configure system files and permissions
USER root

# Ensure required runtime directories exist with correct permissions
RUN mkdir -p /mnt/extra-addons /var/lib/odoo /etc/odoo /var/log/odoo \
    && chown -R odoo:odoo /mnt/extra-addons /var/lib/odoo /etc/odoo /var/log/odoo

# Copy Odoo configuration file
COPY config/odoo.conf /etc/odoo/odoo.conf

# Copy custom application addons
COPY addons/ /mnt/extra-addons/

# Copy Render entrypoint wrapper
# This wrapper resolves a PORT env var collision: Render injects PORT as the
# HTTP listener port, but the official Odoo entrypoint reads PORT as the
# PostgreSQL port. The wrapper remaps variables before calling /entrypoint.sh.
# See scripts/render-entrypoint.sh for full documentation.
COPY scripts/render-entrypoint.sh /render-entrypoint.sh
RUN chmod +x /render-entrypoint.sh

# Ensure proper ownership and permissions for the odoo runtime user
RUN chown -R odoo:odoo /mnt/extra-addons /etc/odoo/odoo.conf \
    && chmod -R 755 /mnt/extra-addons \
    && chmod 644 /etc/odoo/odoo.conf

# Switch back to non-root odoo user
USER odoo

# Expose standard Odoo HTTP and Longpolling / Gevent ports
EXPOSE 8069 8072

# Use the Render wrapper entrypoint instead of /entrypoint.sh directly.
# On Render: set DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, ODOO_MASTER_PASSWORD.
# On local Docker Compose: the compose file overrides ENTRYPOINT back to
# /entrypoint.sh via its own environment variable mapping — no change needed.
ENTRYPOINT ["/render-entrypoint.sh"]
CMD ["odoo", "--config=/etc/odoo/odoo.conf"]

