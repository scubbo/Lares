"""System management tools for Lares self-management."""

import asyncio
import subprocess

import structlog

log = structlog.get_logger()


async def restart_lares() -> str:
    """
    Restart the Lares systemd service.

    This tool allows Lares to restart itself, useful for:
    - Applying code updates after git pull
    - Reloading configuration changes
    - Recovering from suspected issues
    - Periodic fresh starts during autonomous operation

    Requires passwordless sudo access for 'systemctl restart lares.service'.
    See setup-sudoers.sh for configuration.

    Returns:
        Success message confirming restart was initiated.
    """
    log.info("restart_lares_requested")

    # Import here to avoid circular dependency
    from lares.tools.discord import send_message

    try:
        # Send a goodbye message to Discord first
        await send_message(
            "🔄 Restarting now... I'll be back in a moment!", reply=False
        )
        log.info("restart_goodbye_sent")

        # Give Discord a moment to send the message
        await asyncio.sleep(1)

        # Fire-and-forget: spawn restart as detached process so we can return
        # before systemd kills us. start_new_session=True ensures the process
        # survives our death.
        subprocess.Popen(
            ["sudo", "systemctl", "restart", "lares.service"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        log.info("restart_lares_initiated")
        return "Restart initiated! Goodbye... 👋"

    except Exception as e:
        log.error(
            "restart_lares_exception", error=str(e), error_type=type(e).__name__
        )
        return f"Error restarting: {e}"
