"""Application entry point: wires the Helper into a request-handling Runner."""
from utils.helpers import Helper


class Runner:
    """Wires a Helper instance into one request-handling call."""

    def execute(self, item):
        """Run one item through the shared Helper and return its result."""
        helper = Helper()
        return helper.run(item)
