"""Health check HTTP server for monitoring using aiohttp."""

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta

from aiohttp import web

import database

# Configure logging
logger = logging.getLogger(__name__)

# Get health check configuration from environment
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8444"))
HEALTH_BIND_ADDRESS = os.getenv("HEALTH_BIND_ADDRESS", "0.0.0.0")

# Health check thresholds
MAX_DAYS_SINCE_LAST_RUN = 2  # Consider stale if task hasn't run in 2 days


def _format_datetime(dt: datetime) -> str:
    """
    Format datetime to yyyy-mm-dd hh:mm:ss format.

    Args:
        dt: Datetime object to format

    Returns:
        Formatted string
    """
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _check_task_health(
    task_name: str, system_status: dict, threshold: datetime
) -> tuple[dict, bool]:
    """
    Check health status of a single task.

    Args:
        task_name: Name of the task (scraper, checker, cleanup)
        system_status: Dict of all system status entries
        threshold: Datetime threshold for considering task stale

    Returns:
        Tuple of (task_status_dict, is_healthy)
    """
    key = f"last_{task_name}_run"
    task_info = system_status.get(key)

    if task_info is None:
        return {"status": "never_run", "last_run": None}, False

    last_run_str = task_info["value"]
    try:
        last_run = datetime.fromisoformat(last_run_str)
        # Ensure timezone-aware for comparison (assume UTC if naive)
        if last_run.tzinfo is None:
            last_run = last_run.replace(tzinfo=UTC)

        is_healthy = last_run >= threshold
        status_dict = {
            "status": "ok" if is_healthy else "stale",
            "last_run": _format_datetime(last_run),
        }
        return status_dict, is_healthy

    except (ValueError, TypeError):
        logger.warning(f"Invalid timestamp for {key}: {last_run_str}")
        return {"status": "error", "last_run": last_run_str}, False


async def get_health_status() -> dict:
    """
    Get complete health status.

    Returns:
        Dict with health information:
        - status: "healthy" or "unhealthy"
        - timestamp: Current ISO timestamp
        - stats: User and product counts
        - tasks: Status of scheduled tasks (scraper, checker, cleanup)
    """
    now = datetime.now(UTC)
    threshold = now - timedelta(days=MAX_DAYS_SINCE_LAST_RUN)

    # Get database stats and system status
    stats = await database.get_stats()
    system_status = await database.get_all_system_status()

    # Check each task's health status
    tasks = {}
    all_healthy = True

    for task_name in ["scraper", "checker", "cleanup"]:
        task_status, is_healthy = _check_task_health(task_name, system_status, threshold)
        tasks[task_name] = task_status
        all_healthy = all_healthy and is_healthy

    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "timestamp": _format_datetime(now),
        "stats": {
            "users": stats["user_count"],
            "products_total": stats["product_count"],
            "products_active": stats["active_product_count"],
        },
        "tasks": tasks,
    }


async def health_check_handler(request: web.Request) -> web.Response:
    """
    Handle GET /health requests.

    Args:
        request: aiohttp Request object

    Returns:
        JSON response with health status
    """
    try:
        health_data = await get_health_status()
        return web.json_response(health_data)
    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def start_health_server():
    """
    Start aiohttp health check server.

    Security Note:
    This server uses HTTP (not HTTPS) intentionally for internal health checks.
    In production deployments, HTTPS should be handled by infrastructure:
    - Reverse proxy (nginx, Caddy, Traefik)
    - Load balancer (AWS ALB, Google Cloud Load Balancer)
    - CDN/WAF (Cloudflare, Fastly)

    The health check endpoint does not transmit sensitive data and is typically
    accessed by monitoring services (UptimeRobot, Datadog) or orchestration
    platforms (Kubernetes, Docker Swarm) within a secured network.

    For enhanced security in production:
    - Set HEALTH_BIND_ADDRESS=127.0.0.1 to restrict access to localhost only
    - Use firewall rules to limit access to monitoring services
    - Place behind a reverse proxy that handles HTTPS termination

    Configuration:
    - HEALTH_PORT: Port to listen on (default: 8444)
    - HEALTH_BIND_ADDRESS: Address to bind to (default: 0.0.0.0)
        - 0.0.0.0 = All interfaces (required for Docker/Kubernetes)
        - 127.0.0.1 = Localhost only (for reverse proxy setups)
    """
    # Create aiohttp application
    app = web.Application()
    app.router.add_get("/health", health_check_handler)

    # Setup and start server
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, HEALTH_BIND_ADDRESS, HEALTH_PORT)
    await site.start()

    logger.info(
        f"Health check server running on {HEALTH_BIND_ADDRESS}:{HEALTH_PORT} "
        f"(HTTP - HTTPS should be handled by reverse proxy)"
    )

    # Keep server running forever
    await asyncio.Event().wait()


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    async def main():
        """Main function for standalone execution."""
        # Initialize database
        await database.init_db()

        # Start server
        await start_health_server()

    # Run async main
    asyncio.run(main())
