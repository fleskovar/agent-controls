import re

import agent_actions as aa

TOKEN = re.compile(r"\b(sk-[A-Za-z0-9]{8,}|ghp_[A-Za-z0-9]{8,})\b")


class BlockSecretsInPrompt(aa.PromptProcess):
    """Blocks a prompt that carries what looks like an API token."""

    def run(self, event: aa.HookInput) -> aa.ProcessResult:
        found = TOKEN.search(event.prompt or "")
        return (
            aa.allow()
            if found is None
            else aa.block(
                "Your prompt contains what looks like an API token. "
                "Remove it and name the secret instead, for example OPENAI_API_KEY."
            )
        )


context = aa.get_current_context()
context.add(BlockSecretsInPrompt())
aa.run(context)
