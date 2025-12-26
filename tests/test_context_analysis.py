#!/usr/bin/env python3
"""
Instrumentation to analyze when and why memory compaction triggers.

This script adds logging to track:
1. Message count and size accumulation
2. Context window usage patterns
3. What triggers compaction events
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List


class ContextAnalyzer:
    """Analyze context window usage and compaction patterns."""

    def __init__(self, state_file: str = None):
        self.state_file = state_file or os.path.expanduser("~/.lares/context_analysis.json")
        self.message_history: List[Dict[str, Any]] = []
        self.compaction_events: List[Dict[str, Any]] = []
        self.current_context_size = 0

        # Create directory if needed
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)

        # Load existing state if available
        self._load_state()

    def _load_state(self):
        """Load state from file if it exists."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.message_history = state.get('message_history', [])
                    self.compaction_events = state.get('compaction_events', [])
                    self.current_context_size = state.get('current_context_size', 0)
            except Exception:
                pass  # Start fresh if load fails

    def _save_state(self):
        """Save current state to file."""
        state = {
            'message_history': self.message_history[-100:],  # Keep last 100 messages
            'compaction_events': self.compaction_events,
            'current_context_size': self.current_context_size,
            'last_updated': datetime.now().isoformat()
        }
        with open(self.state_file, 'w') as f:
            json.dump(state, f)

    def track_message(self, message_type: str, content: str, metadata: Dict = None):
        """Track a message added to context."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": message_type,
            "content_length": len(content) if content else 0,
            "metadata": metadata or {},
            "cumulative_size": self.current_context_size + len(content if content else "")
        }

        self.message_history.append(entry)
        self.current_context_size = entry["cumulative_size"]

        # Save state after each message
        self._save_state()

        return entry

    def track_compaction(self, summary: str, messages_compacted: int):
        """Track when compaction occurs."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "messages_before": len(self.message_history),
            "messages_compacted": messages_compacted,
            "context_size_before": self.current_context_size,
            "summary_length": len(summary) if summary else 0,
            "trigger_pattern": self._analyze_trigger()
        }

        self.compaction_events.append(event)

        # Reset after compaction
        self.message_history = self.message_history[-5:]  # Keep last 5 for context
        self.current_context_size = sum(m["content_length"] for m in self.message_history)

        # Save state after compaction
        self._save_state()

        return event

    def _analyze_trigger(self) -> Dict[str, Any]:
        """Analyze what likely triggered compaction."""
        if not self.message_history:
            return {"trigger": "unknown"}

        # Look at recent message patterns
        recent_messages = self.message_history[-10:]

        # Count message types
        type_counts = {}
        for msg in recent_messages:
            msg_type = msg["type"]
            type_counts[msg_type] = type_counts.get(msg_type, 0) + 1

        # Identify likely trigger
        if "perch_time" in [m["type"] for m in recent_messages[-3:]]:
            trigger = "perch_time"
        elif type_counts.get("tool_call", 0) > 5:
            trigger = "tool_chain_heavy"
        elif self.current_context_size > 50000:  # Estimated threshold
            trigger = "size_threshold"
        else:
            trigger = "conversation_length"

        return {
            "trigger": trigger,
            "recent_types": type_counts,
            "context_size": self.current_context_size,
            "message_count": len(self.message_history)
        }

    def generate_report(self) -> str:
        """Generate analysis report."""
        if not self.compaction_events:
            return "No compaction events recorded yet."

        report = ["Context Window Analysis Report", "=" * 40, ""]

        # Summary stats
        report.append(f"Total compaction events: {len(self.compaction_events)}")
        report.append(f"Current context size: {self.current_context_size:,} chars")
        report.append(f"Messages in history: {len(self.message_history)}")
        report.append("")

        # Compaction patterns
        report.append("Compaction Triggers:")
        triggers = {}
        for event in self.compaction_events:
            trigger = event["trigger_pattern"]["trigger"]
            triggers[trigger] = triggers.get(trigger, 0) + 1

        for trigger, count in sorted(triggers.items(), key=lambda x: x[1], reverse=True):
            report.append(f"  - {trigger}: {count} times")

        report.append("")

        # Average stats
        if self.compaction_events:
            avg_size = sum(e["context_size_before"] for e in self.compaction_events) / len(self.compaction_events)
            avg_msgs = sum(e["messages_before"] for e in self.compaction_events) / len(self.compaction_events)

            report.append(f"Average context size at compaction: {avg_size:,.0f} chars")
            report.append(f"Average message count at compaction: {avg_msgs:.0f}")

        report.append("")

        # Recent events
        report.append("Recent Compaction Events:")
        for event in self.compaction_events[-3:]:
            report.append(f"  {event['timestamp']}: {event['trigger_pattern']['trigger']}")
            report.append(f"    Context: {event['context_size_before']:,} chars, {event['messages_before']} msgs")

        return "\n".join(report)


def instrument_memory_module():
    """
    Monkey-patch the memory module to add instrumentation.

    This should be called early in the application startup.
    """
    import sys
    sys.path.insert(0, 'src')

    from lares import memory

    # Create global analyzer with file persistence
    analyzer = ContextAnalyzer(state_file=os.path.expanduser("~/.lares/context_analysis.json"))

    # Store original functions
    original_send_message = memory.send_message
    original_send_tool_result = memory.send_tool_result

    # Wrapped send_message
    def instrumented_send_message(client, agent_id, message, retry_on_compaction=True):
        print(f"[MONITOR DEBUG] instrumented_send_message called with message: {message[:50]}...", flush=True)
        # Track the message
        analyzer.track_message("user_message", message)

        # Call original
        response = original_send_message(client, agent_id, message, retry_on_compaction)

        # Track response
        if response.text:
            analyzer.track_message("assistant_response", response.text)

        # Track compaction if it occurred
        if response.system_alert:
            analyzer.track_compaction(response.system_alert, 20)  # Estimate

            # Print live analysis
            print("\n[CONTEXT ANALYSIS] Compaction detected!")
            print(f"  Current size: {analyzer.current_context_size:,} chars")
            print(f"  Trigger: {analyzer.compaction_events[-1]['trigger_pattern']['trigger']}")

        return response

    # Wrapped send_tool_result
    def instrumented_send_tool_result(client, agent_id, tool_call_id, result, status="success", retry_on_compaction=True):
        # Track tool result
        analyzer.track_message("tool_result", result, {"tool_id": tool_call_id[:20]})

        # Call original
        response = original_send_tool_result(client, agent_id, tool_call_id, result, status, retry_on_compaction)

        # Track response
        if response.text:
            analyzer.track_message("tool_response", response.text)

        # Track compaction if it occurred
        if response.system_alert:
            analyzer.track_compaction(response.system_alert, 15)  # Estimate

        return response

    # Apply patches
    memory.send_message = instrumented_send_message
    memory.send_tool_result = instrumented_send_tool_result
    memory._context_analyzer = analyzer  # Store reference for access

    print("[CONTEXT ANALYSIS] Instrumentation activated")
    print("  Tracking: message sizes, compaction events, triggers")
    print("  Access analyzer: from lares.memory import _context_analyzer")

    return analyzer


if __name__ == "__main__":
    # Test the analyzer
    analyzer = ContextAnalyzer()

    # Simulate some activity
    for i in range(10):
        analyzer.track_message("user_message", "x" * 1000)
        analyzer.track_message("assistant_response", "y" * 2000)

    analyzer.track_compaction("Summary of conversation", 10)

    for i in range(5):
        analyzer.track_message("perch_time", "z" * 500)

    analyzer.track_compaction("Another summary", 5)

    # Generate report
    print(analyzer.generate_report())