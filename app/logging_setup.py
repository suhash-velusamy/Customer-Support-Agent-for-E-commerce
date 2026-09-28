"""Console logging for the CLI and web server: our warnings only, no HTTP request noise."""

import logging


def configure_logging() -> None:
    # force=True: some libraries configure the root logger at INFO when imported.
    logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(message)s", force=True)
    for noisy in ("httpx", "httpcore", "openai", "mcp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # The openai client logs each retry at INFO; keep only real failures.
    logging.getLogger("openai._base_client").setLevel(logging.ERROR)
