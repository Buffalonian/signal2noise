import logging


def configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [signalpath] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
