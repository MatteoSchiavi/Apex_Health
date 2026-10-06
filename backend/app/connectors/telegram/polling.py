"""Inert entrypoint for legacy Compose configurations.

Older deployment checkouts may still start this module as the `bot` service.
It performs no Telegram calls and waits only so the old updater can finish its
transition; current Compose files omit this service and remove its container.
"""

import logging
import signal
import threading

logger = logging.getLogger("legacy.telegram.disabled")


def main() -> None:
    logger.warning(
        "Legacy bot service is disabled; remove it by updating the Compose stack."
    )
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    while not stopped.wait(3600):
        pass


if __name__ == "__main__":
    main()
