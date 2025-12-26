# Lares Skills

Skills are procedural memory - markdown files that teach Lares how to perform specific tasks.

## Philosophy

Inspired by [Letta Code's skill learning](https://www.letta.com/blog/skill-learning), skills allow Lares to:
- Persist procedural knowledge across context resets
- Load relevant procedures only when needed (context-efficient)
- Learn from successful task completions

## Structure

Each skill file uses this format:

```markdown
---
name: skill-name
description: When to use this skill. Be specific about triggers.
---

# Skill Title

Brief overview.

## Quick Reference
Key commands or patterns.

## Workflow
Step-by-step procedure.

## Common Issues
What can go wrong and how to fix it.

## Anti-patterns
What NOT to do.
```

## Usage

1. **Add skills index to persona** - lightweight pointers, not full content:
   ```
   ## Skills (path/to/skills/)
   Procedural memory - load when relevant:
   - git-workflow.md → committing, pushing
   - perch-tick.md → autonomous decisions
   ```

2. **Load when needed** - read the full skill before performing the task

3. **Create new skills** - after successfully completing a novel task, extract the pattern

## Example Skills

- `git-workflow.md` - Version control patterns
- `perch-tick.md` - Autonomous time decision framework
- `discord-interaction.md` - Communication patterns

These are templates - personalize them for your specific workflows!
