# How to Use Context Analysis

Context analysis helps you understand when and why memory compaction triggers in Lares. It's built into Lares and can be enabled with a simple environment variable.

## Quick Start

Just add to your `.env`:
```bash
LARES_CONTEXT_MONITORING=true
```

That's it! When you start Lares, you'll see:
```
[CONTEXT ANALYSIS] Instrumentation activated
  Tracking: message sizes, compaction events, triggers
```

## Manual Testing

To see example output without running Lares:

```bash
source .venv/bin/activate
python tests/test_context_analysis.py
```

## What It Tracks

When activated, the script monitors:

1. **Every message sent/received**:
   - User messages
   - Assistant responses
   - Tool calls and results
   - Perch time messages

2. **Memory compaction events**:
   - When they occur
   - How many messages were compacted
   - What likely triggered it
   - Context size before compaction

3. **Live notifications**:
   ```
   [CONTEXT ANALYSIS] Compaction detected!
     Current size: 125,432 chars
     Trigger: perch_time
   ```

## Understanding the Output

### Live Console Output

During bot operation, you'll see:

```
[CONTEXT ANALYSIS] Instrumentation activated
  Tracking: message sizes, compaction events, triggers

[CONTEXT ANALYSIS] Compaction detected!
  Current size: 52,341 chars
  Trigger: tool_chain_heavy
```

### Accessing the Analyzer

### Using the Memory Report Script (Recommended)

The easiest way to check memory stats is using the provided script.

**Important**: The script requires the virtual environment. Use one of these methods:

```bash
# Method 1: Use the wrapper script (easiest after chmod +x)
chmod +x scripts/memory-report  # Only needed once
./scripts/memory-report
./scripts/memory-report --brief
./scripts/memory-report --export

# Method 2: Use venv Python directly (no chmod needed)
.venv/bin/python scripts/memory_report.py
.venv/bin/python scripts/memory_report.py --brief
.venv/bin/python scripts/memory_report.py --export

# Method 3: Activate venv first
source .venv/bin/activate
python scripts/memory_report.py
python scripts/memory_report.py --brief
python scripts/memory_report.py --export my_report.json
```

**Options:**
- No arguments: Full detailed report
- `--brief` or `-b`: One-line summary
- `--export` or `-e`: Save to JSON (auto-named with timestamp)
- `--export filename.json`: Save to specific file

### Manual Access via Python

You can also access the analyzer directly:

```python
# In a Python REPL or debug console
from lares.memory import _context_analyzer as analyzer

# Get current stats
print(f"Current context size: {analyzer.current_context_size:,} chars")
print(f"Messages tracked: {len(analyzer.message_history)}")
print(f"Compaction events: {len(analyzer.compaction_events)}")

# Generate full report
print(analyzer.generate_report())
```

### Sample Report Output

```
Context Window Analysis Report
========================================

Total compaction events: 3
Current context size: 8,234 chars
Messages in history: 15

Compaction Triggers:
  - perch_time: 2 times
  - tool_chain_heavy: 1 times

Average context size at compaction: 51,234 chars
Average message count at compaction: 42

Recent Compaction Events:
  2024-12-25T10:30:00: perch_time
    Context: 52,341 chars, 45 msgs
  2024-12-25T11:15:00: tool_chain_heavy
    Context: 49,123 chars, 38 msgs
```

## Interpreting Triggers

The analyzer identifies these trigger patterns:

- **`perch_time`**: Compaction during autonomous perch tick
- **`tool_chain_heavy`**: Many tool calls in succession (>5)
- **`size_threshold`**: Context exceeded ~50k chars
- **`conversation_length`**: General accumulation over time

## Using Data to Optimize

### Finding the Right Context Window

1. Run with monitoring for a day
2. Note the average context size at compaction
3. Set `LARES_CONTEXT_WINDOW_LIMIT` to 2x that value

Example:
```
Average context at compaction: 25,000 chars (≈6,250 tokens)
Set: LARES_CONTEXT_WINDOW_LIMIT=12500  # 2x safety margin
```

### Identifying Problem Areas

If most triggers are:
- **`perch_time`**: Consider increasing perch interval
- **`tool_chain_heavy`**: Compress tool results
- **`size_threshold`**: Increase context window limit

## Advanced Usage

### Custom Tracking

Add your own tracking points:

```python
from lares.memory import _context_analyzer as analyzer

# Track custom event
analyzer.track_message(
    message_type="custom_event",
    content="Some content",
    metadata={"source": "my_feature"}
)
```

### Export Data

The easiest way to export data is using the script:

```bash
# Export to auto-named JSON file with timestamp
.venv/bin/python scripts/memory_report.py --export

# Export to specific file
.venv/bin/python scripts/memory_report.py --export analysis_dec25.json
```

Or manually via Python:

```python
import json

# Export compaction events
with open("compaction_analysis.json", "w") as f:
    json.dump(analyzer.compaction_events, f, indent=2)

# Export report
with open("context_report.txt", "w") as f:
    f.write(analyzer.generate_report())
```

## Troubleshooting

### No Output Appearing

Check that:
1. `LARES_CONTEXT_MONITORING=true` in `.env` (not `false`)
2. You restarted Lares after changing the setting
3. Bot is actually sending messages

### Import Errors

The monitoring script might not load if tests/ directory is missing. Check that `tests/test_context_analysis.py` exists.

### Analyzer Not Available

After Lares starts with monitoring enabled, access the analyzer:
```python
from lares.memory import _context_analyzer
```

## Recommended Workflow

1. **Enable monitoring**: Set `LARES_CONTEXT_MONITORING=true` in `.env`
2. **Restart Lares**: The monitoring will activate automatically
3. **Run normally** for a few hours
4. **Check report** to see compaction patterns
5. **Adjust settings**:
   - Increase `LARES_CONTEXT_WINDOW_LIMIT` if needed
   - Adjust `LARES_PERCH_INTERVAL_MINUTES` if perch is triggering it
6. **Disable monitoring** once optimized: Set to `false` (removes overhead)

## Cost Considerations

Remember that larger context windows = higher API costs:

| Context Limit | Tokens | Relative Cost |
|--------------|--------|---------------|
| 10,000       | 10k    | 1x            |
| 50,000       | 50k    | 5x            |
| 100,000      | 100k   | 10x           |
| 200,000      | 200k   | 20x           |

Start conservative (50k) and increase only if needed!