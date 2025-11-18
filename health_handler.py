"""Health check HTTP server for monitoring."""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
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
            # Run async health check
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            health_data = loop.run_until_complete(get_health_status())
            loop.close()

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
        logger.info("%s - %s" % (self.address_string(), format % args))


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
    now = datetime.now()
    threshold = now - timedelta(days=MAX_DAYS_SINCE_LAST_RUN)

    # Get database stats
    stats = await database.get_stats()

    # Get system status for all tasks
    system_status = await database.get_all_system_status()

    # Check each task status
    tasks = {}
    all_healthy = True

    for task_name in ["scraper", "checker", "cleanup"]:
        key = f"last_{task_name}_run"
        task_info = system_status.get(key)

        if task_info is None:
            # Task has never run
            tasks[task_name] = {
                "status": "never_run",
                "last_run": None,
            }
            all_healthy = False
        else:
            # Parse last run timestamp
            last_run_str = task_info["value"]
            try:
                last_run = datetime.fromisoformat(last_run_str)
                is_healthy = last_run >= threshold

                tasks[task_name] = {
                    "status": "ok" if is_healthy else "stale",
                    "last_run": last_run_str,
                }

                if not is_healthy:
                    all_healthy = False

            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid timestamp for {key}: {last_run_str}")
                tasks[task_name] = {
                    "status": "error",
                    "last_run": last_run_str,
                }
                all_healthy = False

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
