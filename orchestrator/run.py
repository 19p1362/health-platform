"""
Healthcare Orchestra — Main Entry Point.

Provides a unified CLI for all system components:

    python run.py                  # Run everything: migrate + seed + dashboard + orchestrator
    python run.py --migrate        # Create database tables
    python run.py --seed           # Add sample data
    python run.py --dashboard      # Start Flask dashboard server
    python run.py --orchestrator   # Start agent loop
    python run.py --whatsapp       # Start webhook only (no agents)
    python run.py --once           # Run orchestrator once & exit

Multiple flags can be combined.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from threading import Thread

from config import config
from db_adapter import Database

logger = logging.getLogger("healthcare_orchestra.run")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG if config.DEBUG else logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
    )


def _run_migrate() -> None:
    """Create/verify database tables."""
    logger.info("Running database migration...")
    try:
        db = Database()
        logger.info("Database tables created/verified at %s", db.db_path)
        db.close()
    except Exception as exc:
        logger.error("Migration failed: %s", exc)
        sys.exit(1)


def _run_seed() -> None:
    """Seed sample data."""
    logger.info("Seeding sample data...")
    try:
        db = Database()
        counts = db.seed_sample_data()
        logger.info(
            "Sample data seeded: patients=%d, meds=%d, "
            "followups=%d, appointments=%d, labs=%d",
            counts.get("patients", 0),
            counts.get("medications", 0),
            counts.get("follow_ups", 0),
            counts.get("appointments", 0),
            counts.get("lab_orders", 0),
        )
        db.close()
    except Exception as exc:
        logger.error("Seed failed: %s", exc)
        sys.exit(1)


def _run_dashboard() -> None:
    """Start the Flask dashboard server in the current thread (blocking)."""
    sys.path.insert(0, str(__file__))
    from dashboard.server import app

    logger.info(
        "Starting dashboard server on port %s (debug=%s)",
        config.DASHBOARD_PORT, config.DEBUG,
    )
    app.run(
        host="0.0.0.0",
        port=config.DASHBOARD_PORT,
        debug=config.DEBUG,
        use_reloader=False,  # Don't reload in threaded mode
    )


def _run_orchestrator(single_run: bool = False) -> None:
    """Start the orchestrator agent loop."""
    from master_orchestrator import run_orchestrator_loop

    logger.info(
        "Starting orchestrator%s",
        " (single run)" if single_run else "",
    )
    run_orchestrator_loop(single_run=single_run)


def _run_whatsapp_only() -> None:
    """Start only the WhatsApp webhook server (no agents)."""
    sys.path.insert(0, str(__file__))
    from dashboard.server import app

    logger.info(
        "Starting WhatsApp webhook server on port %s "
        "(agents disabled)",
        config.DASHBOARD_PORT,
    )
    app.run(
        host="0.0.0.0",
        port=config.DASHBOARD_PORT,
        debug=False,
        use_reloader=False,
    )


def main() -> None:
    _setup_logging()

    parser = argparse.ArgumentParser(
        description="Healthcare Orchestra — AI-powered healthcare agent system",
    )
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Create/update database tables",
    )
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Seed database with sample data",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="Start the Flask dashboard server",
    )
    parser.add_argument(
        "--orchestrator",
        action="store_true",
        help="Start the agent orchestrator loop",
    )
    parser.add_argument(
        "--whatsapp",
        action="store_true",
        help="Start WhatsApp webhook only (no agents)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run orchestrator once and exit (with --orchestrator)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="run_all",
        help="Run migrate + seed + dashboard + orchestrator (default)",
    )

    args = parser.parse_args()

    # Default: run everything
    run_all = args.run_all or not any([
        args.migrate, args.seed, args.dashboard,
        args.orchestrator, args.whatsapp,
    ])

    # --- Phase 1: Database setup (always runs first) ---
    if run_all or args.migrate:
        _run_migrate()

    if run_all or args.seed:
        _run_seed()

    # --- Phase 2: Decide what to start ---
    start_orchestrator = run_all or args.orchestrator
    start_dashboard = run_all or args.dashboard
    start_whatsapp = args.whatsapp

    # --once is only valid with --orchestrator
    single_run = args.once and (args.orchestrator or run_all)

    threads: list[Thread] = []

    # Dashboard & WhatsApp share the Flask server, so they're mutually exclusive
    if start_dashboard:
        dash_thread = Thread(target=_run_dashboard, daemon=True)
        dash_thread.start()
        threads.append(dash_thread)
        logger.info("Dashboard thread started")
        # Brief pause to let Flask bind the port
        time.sleep(1)

    if start_whatsapp:
        whatsapp_thread = Thread(target=_run_whatsapp_only, daemon=True)
        whatsapp_thread.start()
        threads.append(whatsapp_thread)
        logger.info("WhatsApp webhook thread started")
        time.sleep(1)

    if single_run:
        # Run orchestrator once (blocking, then exit)
        _run_orchestrator(single_run=True)
    elif start_orchestrator:
        # Background thread for continuous orchestrator
        orch_thread = Thread(
            target=_run_orchestrator,
            args=(False,),
            daemon=True,
        )
        orch_thread.start()
        threads.append(orch_thread)
        logger.info("Orchestrator thread started")

    if not threads and not single_run:
        logger.warning(
            "No components started. Use --dashboard, --orchestrator, "
            "--whatsapp, or --all (default)."
        )
        return

    # Keep main thread alive if we have daemon threads
    if threads:
        logger.info(
            "Healthcare Orchestra running with %d component(s). "
            "Press Ctrl+C to stop.",
            len(threads),
        )
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutdown requested — exiting")
    elif single_run:
        logger.info("Single run complete — exiting")


if __name__ == "__main__":
    main()
