"""Health check HTTP server for monitoring using aiohttp."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

from aiohttp import web

import database
from config import get_config

# Configure logging
logger = logging.getLogger(__name__)

# Load configuration
cfg = get_config()

# Module-level constants for backward compatibility with tests
HEALTH_PORT = cfg.health_port
HEALTH_BIND_ADDRESS = cfg.health_bind_address
MAX_DAYS_SINCE_LAST_RUN = cfg.health_check_max_days


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
    task_name: str,
    system_status: dict,
    threshold: datetime,
    bot_startup_time: datetime | None,
) -> tuple[dict, bool]:
    """
    Check health status of a single task.

    Args:
        task_name: Name of the task (scraper, checker, cleanup)
        system_status: Dict of all system status entries
        threshold: Datetime threshold for considering task stale (2 days ago)
        bot_startup_time: Bot startup time for grace period calculation

    Returns:
        Tuple of (task_status_dict, is_healthy)

    Health Logic:
        - If task never_run AND bot started <2 days ago: healthy (grace period)
        - If task never_run AND bot started ≥2 days ago: unhealthy (should have run)
        - If task has last_run >= threshold: healthy (recent execution)
        - If task has last_run < threshold: unhealthy (stale)
    """
    key = f"last_{task_name}_run"
    task_info = system_status.get(key)

    if task_info is None:
        # Task has never run - check if we're in grace period
        if bot_startup_time and bot_startup_time >= threshold:
            # Bot started within last 2 days, grace period is active
            return {"status": "never_run", "last_run": None}, True
        else:
            # Bot started >2 days ago, task should have run by now
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
        - bot_startup_time: When the bot started (for grace period tracking)
    """
    now = datetime.now(UTC)
    threshold = now - timedelta(days=MAX_DAYS_SINCE_LAST_RUN)

    # Get database stats and system status
    stats = await database.get_stats()
    system_status = await database.get_all_system_status()

    # Get bot startup time for grace period calculation
    bot_startup_info = system_status.get("bot_startup_time")
    bot_startup_time = None
    if bot_startup_info:
        try:
            bot_startup_time = datetime.fromisoformat(bot_startup_info["value"])
            if bot_startup_time.tzinfo is None:
                bot_startup_time = bot_startup_time.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            logger.warning(f"Invalid bot_startup_time: {bot_startup_info['value']}")

    # Check each task's health status
    tasks = {}
    all_healthy = True

    for task_name in ["scraper", "checker", "cleanup"]:
        task_status, is_healthy = _check_task_health(
            task_name, system_status, threshold, bot_startup_time
        )
        tasks[task_name] = task_status
        all_healthy = all_healthy and is_healthy

    result = {
        "status": "healthy" if all_healthy else "unhealthy",
        "timestamp": _format_datetime(now),
        "stats": {
            "users": stats["user_count"],
            "products_total": stats["product_count"],
            "products_unique": stats["unique_product_count"],
            "products_total_count": stats["products_total_count"],
            "total_savings_generated": stats["total_savings_generated"],
        },
        "tasks": tasks,
    }

    # Add bot_startup_time if available
    if bot_startup_time:
        result["bot_startup_time"] = _format_datetime(bot_startup_time)

    return result


async def health_check_handler(request: web.Request) -> web.Response:
    """
    Handle GET /health requests.

    Args:
        request: aiohttp Request object

    Returns:
        Pretty-printed JSON response with health status (indent=2 for browser readability)
    """
    try:
        health_data = await get_health_status()
        # Use json.dumps with indent for pretty-printed output
        json_str = json.dumps(health_data, indent=2, ensure_ascii=False)
        return web.Response(
            text=json_str,
            content_type="application/json",
            charset="utf-8",
        )
    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        error_data = {"status": "error", "message": str(e)}
        json_str = json.dumps(error_data, indent=2, ensure_ascii=False)
        return web.Response(
            text=json_str,
            content_type="application/json",
            charset="utf-8",
            status=500,
        )


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
    - Set cfg.health_bind_address=127.0.0.1 to restrict access to localhost only
    - Use firewall rules to limit access to monitoring services
    - Place behind a reverse proxy that handles HTTPS termination

    Configuration:
    - cfg.health_port: Port to listen on (default: 8444)
    - cfg.health_bind_address: Address to bind to (default: 0.0.0.0)
        - 0.0.0.0 = All interfaces (required for Docker/Kubernetes)
        - 127.0.0.1 = Localhost only (for reverse proxy setups)
    """
    # Create aiohttp application
    app = web.Application()
    app.router.add_get("/health", health_check_handler)

    # Setup and start server
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, cfg.health_bind_address, cfg.health_port)
    await site.start()

    logger.info(
        f"Health check server running on {cfg.health_bind_address}:{cfg.health_port} "
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
