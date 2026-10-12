import agent_actions as aa


class ModeGuard(aa.PreToolProcess):
    """A guardrail with a bug: it expects an argument that the tool does not send."""

    def run(self, event: aa.HookInput) -> aa.ProcessResult:
        arguments = event.tool.arguments if event.tool else {}
        return aa.allow() if arguments["mode"] == "safe" else aa.block("The mode is not safe.")


context = aa.get_current_context()
context.add(ModeGuard())
aa.run(context)
