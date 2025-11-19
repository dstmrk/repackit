"""Health check HTTP server for monitoring."""

import asyncio
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import database

# Configure logging
logger = logging.getLogger(__name__)

# Get health port from environment
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8444"))

# Health check thresholds
MAX_DAYS_SINCE_LAST_RUN = 2  # Consider stale if task hasn't run in 2 days


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP request handler for health checks."""

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/health":
            self.handle_health_check()
        else:
            self.send_error(404, "Not Found")

    def handle_health_check(self):
        """Handle health check endpoint."""
        try:
            # Run async health check (asyncio.run handles event loop creation/cleanup)
            health_data = asyncio.run(get_health_status())

            # Send response
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(health_data, indent=2).encode())

        except Exception as e:
            logger.error(f"Health check error: {e}", exc_info=True)
            self.send_error(500, f"Internal Server Error: {str(e)}")

    def log_message(self, format, *args):
        """Override to use custom logger."""
        message = format % args
        logger.info(f"{self.address_string()} - {message}")


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
            "last_run": last_run_str,
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
        "timestamp": now.isoformat(),
        "stats": {
            "users": stats["user_count"],
            "products_total": stats["product_count"],
            "products_active": stats["active_product_count"],
        },
        "tasks": tasks,
        "thresholds": {
            "max_days_since_last_run": MAX_DAYS_SINCE_LAST_RUN,
        },
    }


def run_server():
    """Run health check HTTP server."""
    server = HTTPServer(("0.0.0.0", HEALTH_PORT), HealthCheckHandler)
    logger.info(f"Health check server running on port {HEALTH_PORT}")
    server.serve_forever()


def start_health_server():
    """Start health check server in background thread."""
    thread = Thread(target=run_server, daemon=True)
    thread.start()
    logger.info("Health check server started in background")


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Initialize database
    asyncio.run(database.init_db())

    # Run server
    run_server()
