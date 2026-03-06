"""
Simple publish/subscribe event bus for decoupled game systems.
"""


class EventBus:
    """Lightweight event bus — listeners register with on(), fire with emit()."""

    def __init__(self):
        self._listeners: dict[str, list] = {}

    def on(self, event: str, callback):
        """Register a callback for an event name."""
        self._listeners.setdefault(event, []).append(callback)

    def emit(self, event: str, **kwargs):
        """Fire all callbacks registered for the given event."""
        for callback in self._listeners.get(event, []):
            callback(**kwargs)
