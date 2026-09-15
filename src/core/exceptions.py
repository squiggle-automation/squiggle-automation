class ExecutionError(Exception):
    """Generic error from execution"""

    pass


class ExecutionCancledError(ExecutionError):
    """Execution did not start due to configuration"""

    pass


class ExecutionInputError(ExecutionError):
    """Execution failed to create input data"""

    pass


class ExecutionRuntimeError(ExecutionError):
    """Execution failed during runtime"""

    pass


class ExecutionOutputError(ExecutionError):
    """Execution failed to process output data"""

    pass


class ExecutionRetryError(ExecutionError):
    """Execution is not retried because it did not fail"""

    pass
