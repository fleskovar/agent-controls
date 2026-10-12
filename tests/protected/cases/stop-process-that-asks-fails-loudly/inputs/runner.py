import agent_actions as aa


class AskBeforeStopping(aa.StopProcess):
    """A mistake on purpose: a stop hook cannot ask the user."""

    def run(self, event):
        return aa.ask("Ask the user whether the work is complete.")


context = aa.get_current_context()
context.add(AskBeforeStopping())
aa.run(context)
