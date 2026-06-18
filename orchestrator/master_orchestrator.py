"""
Healthcare Orchestra — Master Orchestrator.

Priority-based agent scheduler that:
- Runs in a loop with configurable intervals
- Calls Database().sync_from_healthbridge() first to refresh data
- Dispatches each enabled agent in priority order
- Each agent gets the Database instance and runs its logic
- Logs all agent actions to the agent_log table
- Supports --once flag for single-run mode
- Handles graceful shutdown on SIGINT/SIGTERM
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from datetime import datetime
from typing import NoReturn

from config import config
from db_adapter import Database
from agents import AGENT_META

logger = logging.getLogger("healthcare_orchestra.orchestrator")

# ---------------------------------------------------------------------------
# Global shutdown flag
# ---------------------------------------------------------------------------

_shutdown_requested = False


def _handle_signal(signum: int, _frame) -> None:
    """Set shutdown flag on SIGINT/SIGTERM."""
    global _shutdown_requested
    signame = signal.Signals(signum).name
    logger.warning("Received %s — shutting down gracefully...", signame)
    _shutdown_requested = True


def _setup_signal_handlers() -> None:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)


# ---------------------------------------------------------------------------
# Agent last-run tracking (for interval-based scheduling)
# ---------------------------------------------------------------------------

_last_run: dict[str, float] = {}


def _is_agent_due(agent_name: str) -> bool:
    """Check if an agent is due to run based on its interval."""
    interval = config.AGENT_INTERVALS.get(agent_name, 60)
    last = _last_run.get(agent_name, 0.0)
    return (time.time() - last) >= (interval * 60)


def _mark_run(agent_name: str) -> None:
    _last_run[agent_name] = time.time()


# ---------------------------------------------------------------------------
# Orchestrator run
# ---------------------------------------------------------------------------


def run_orchestrator_once(db: Database, force_agents: list[str] | None = None) -> dict:
    """Execute one full orchestrator cycle.

    Args:
        db: Database instance.
        force_agents: Optional list of agent names to run (ignores intervals/enabled).

    Returns:
        dict mapping agent names to their result dicts.
    """
    results: dict[str, dict] = {}

    # Step 1: Sync from HealthBridge
    logger.info("Syncing data from HealthBridge...")
    try:
        sync_counts = db.sync_from_healthbridge()
        logger.info(
            "Sync complete: %d patients, %d meds, %d labs, %d appointments",
            sync_counts.get("patients", 0),
            sync_counts.get("medications", 0),
            sync_counts.get("lab_orders", 0),
            sync_counts.get("appointments", 0),
        )
    except Exception as exc:
        logger.error("HealthBridge sync failed: %s", exc)
        db.log_agent_action(
            agent_name="orchestrator",
            action="sync_failed",
            details=f"HealthBridge sync error: {exc}",
            status="error",
        )
        # Continue anyway with local data

    # Step 2: Dispatch enabled agents in priority order
    if force_agents:
        agents_to_run = force_agents
    else:
        agents_to_run = [
            name for name in config.AGENT_PRIORITY
            if config.AGENTS.get(name, False)
        ]

    if not agents_to_run:
        logger.warning("No agents are enabled — nothing to do")
        db.log_agent_action(
            agent_name="orchestrator",
            action="no_agents",
            details="No enabled agents found",
        )
        return results

    for agent_name in agents_to_run:
        if _shutdown_requested:
            logger.warning("Shutdown requested — stopping agent dispatch")
            break

        meta = AGENT_META.get(agent_name)
        if not meta:
            logger.warning("Unknown agent: %s — skipping", agent_name)
            continue

        if not force_agents and not _is_agent_due(agent_name):
            logger.debug("Agent %s is not due yet — skipping", agent_name)
            continue

        agent_func = meta.get("function")
        description = meta.get("description", "")
        logger.info(
            "Running agent: %s (%s)...", agent_name, description
        )

        try:
            agent_result = agent_func(db)
            results[agent_name] = agent_result
            logger.info(
                "Agent %s completed: %s",
                agent_name,
                _summarize_result(agent_result),
            )
            _mark_run(agent_name)
        except Exception as exc:
            logger.exception(
                "Agent %s failed with exception", agent_name
            )
            db.log_agent_action(
                agent_name=agent_name,
                action="run_failed",
                details=f"Unhandled exception: {exc}",
                status="error",
            )
            results[agent_name] = {"error": str(exc)}
            _mark_run(agent_name)  # mark so we don't retry immediately

        if agent_name in config.AGENT_PRIORITY:
            priority_index = config.AGENT_PRIORITY.index(agent_name)
            logger.debug(
                "Agent %s (priority %d/%d) finished",
                agent_name,
                priority_index + 1,
                len(config.AGENT_PRIORITY),
            )

    db.log_agent_action(
        agent_name="orchestrator",
        action="cycle_complete",
        details=f"Ran agents: {list(results.keys())}",
    )

    return results


def _summarize_result(result: dict) -> str:
    """Create a compact summary of an agent's result dict."""
    if not result:
        return "empty result"
    if "error" in result:
        return f"ERROR: {result['error']}"
    parts = []
    for k, v in result.items():
        if k == "errors":
            parts.append(f"errors={v}")
        elif isinstance(v, int):
            parts.append(f"{k}={v}")
    return ", ".join(parts) if parts else str(result)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run_orchestrator_loop(single_run: bool = False) -> NoReturn:
    """Run the orchestrator in a loop (or single-shot).

    Args:
        single_run: If True, runs once and exits.
    """
    _setup_signal_handlers()

    logger.info(
        "Healthcare Orchestra Orchestrator starting "
        "(single_run=%s)",
        single_run,
    )

    db = Database()

    if single_run:
        logger.info("Running single orchestrator cycle...")
        run_orchestrator_once(db)
        db.close()
        logger.info("Orchestrator single run complete")
        return

    # Continuous loop
    logger.info(
        "Agent intervals: %s",
        ", ".join(
            f"{name}={interval}m"
            for name, interval in config.AGENT_INTERVALS.items()
        ),
    )

    # Run all agents immediately on first start
    logger.info("Running initial agent cycle...")
    run_orchestrator_once(db)

    cycle_count = 1
    while not _shutdown_requested:
        # Sleep in small increments so we can respond to signals
        check_interval = 30  # seconds
        slept = 0
        sleep_max = 300  # maximum 5 min between checks

        while slept < sleep_max and not _shutdown_requested:
            time.sleep(min(check_interval, sleep_max - slept))
            slept += check_interval

        if _shutdown_requested:
            break

        cycle_count += 1
        logger.info(
            "Orchestrator cycle %d starting...", cycle_count
        )
        run_orchestrator_once(db)

    db.close()
    logger.info(
        "Orchestrator stopped after %d cycles", cycle_count
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
    )
    single_run = "--once" in sys.argv
    run_orchestrator_loop(single_run=single_run)
