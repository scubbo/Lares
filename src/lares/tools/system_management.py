"""System management tools for Lares self-management."""

import asyncio
import subprocess

import structlog

log = structlog.get_logger()


async def restart_lares() -> str:
    """
    Restart the Lares systemd services (both MCP server and main bot).

    This tool allows Lares to restart itself, useful for:
    - Applying code updates after git pull
    - Reloading configuration changes
    - Recovering from suspected issues
    - Periodic fresh starts during autonomous operation

    Requires passwordless sudo access for:
    - 'systemctl restart lares-mcp.service'
    - 'systemctl restart lares.service'
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
        #
        # We restart MCP first (quick), then Lares main service.
        # Using shell=True to chain commands properly.
        subprocess.Popen(
            "sudo systemctl restart lares-mcp.service; sudo systemctl restart lares.service",
            shell=True,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        log.info("restart_lares_initiated", services=["lares-mcp", "lares"])
        return "Restart initiated! Goodbye... 👋"

    except Exception as e:
        log.error(
            "restart_lares_exception", error=str(e), error_type=type(e).__name__
        )
        return f"Error restarting: {e}"


async def restart_mcp() -> str:
    """
    Restart only the Lares MCP server (not the main bot).

    Use this when:
    - New MCP tools have been added
    - MCP server configuration changed
    - MCP server is having issues

    This is faster than a full restart since Lares main bot stays running.

    Requires passwordless sudo access for 'systemctl restart lares-mcp.service'.
    See setup-sudoers.sh for configuration.

    Returns:
        Success message confirming MCP restart was initiated.
    """
    log.info("restart_mcp_requested")

    try:
        # Import here to avoid circular dependency
        # Restart MCP server (this is quick, we can wait for it)
        import subprocess

        from lares.tools.discord import send_message
        result = subprocess.run(
            ["sudo", "systemctl", "restart", "lares-mcp.service"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            log.info("restart_mcp_completed")
            await send_message("🔄 MCP server restarted successfully!", reply=False)
            return "MCP server restarted successfully! ✅"
        else:
            error_msg = result.stderr or "Unknown error"
            log.error("restart_mcp_failed", error=error_msg)
            return f"Error restarting MCP server: {error_msg}"

    except subprocess.TimeoutExpired:
        log.error("restart_mcp_timeout")
        return "Error: MCP restart timed out after 30 seconds"
    except Exception as e:
        log.error("restart_mcp_exception", error=str(e), error_type=type(e).__name__)
        return f"Error restarting MCP: {e}"
