## Agent Controls

This project uses Agent Controls. A runner file, usually `.hooks/agent_checks.py`,
runs checks on the lifecycle hooks of the agent.

- When a hook blocks a tool call or a stop, read the reason and do what it tells you. Do not use a different tool or command to avoid the check.
- Do not change a test, a threshold, a flag file (`.hooks/flags.json`), the runner file or the hook configuration to make a check pass. If a check is wrong, stop and tell the user.
- A file that a hook reverted is a protected file. Do not write it again.
- To install, change or debug a check, use the `agent-controls-setup`, `agent-controls-guardrails` and `agent-controls-processes` skills.
