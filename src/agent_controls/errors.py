"""Errors that stop a run. The CLI prints the message and exits with code 1."""


class AgentControlsError(Exception):
    """Base class for all framework errors."""


class IncompatibleProcessError(AgentControlsError):
    """A process cannot attach to a hook, or the harness cannot deliver what it returns."""


class IncompatibleResultError(AgentControlsError):
    """A process returned a verdict or a context that the hook cannot deliver."""


class ProcessFailedError(AgentControlsError):
    """A process raised an exception on a hook that cannot block."""


class RunnerFileError(AgentControlsError):
    """The runner file is missing, fails, or does not call `agent_controls.run(context)`."""


class StateError(AgentControlsError):
    """A state file is corrupt, or a state variable is not JSON-serializable."""


class PayloadError(AgentControlsError):
    """The hook payload is not a JSON object."""
