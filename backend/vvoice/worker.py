"""Run the one-host durable inference worker: python -m vvoice.worker."""
from __future__ import annotations

import argparse
import os
import signal
import threading


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Same configuration file used by the API")
    args = parser.parse_args(argv)
    # This change is local to the explicit worker process, never the parent API.
    os.environ["VASSIL_WORKER_MODE"] = "embedded"
    from vvoice.core.config import load_settings
    from vvoice.core.container import AppContainer
    from vvoice.core.observability import configure_logging
    from vvoice.inference.remote import WorkerControlServer, WorkerControlStore
    from vvoice.shared.jobs.durable import FileLock

    settings = load_settings(args.config)
    configure_logging(debug=settings.runtime.debug, log_level=settings.runtime.log_level)
    host_lock = FileLock(settings.storage.data_dir / ".worker-host.lock")
    if not host_lock.acquire(blocking=False):
        raise RuntimeError("An inference worker already owns this data directory")
    container = control = None
    stopped = threading.Event()

    def stop(_signal, _frame):
        stopped.set()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop)
    try:
        # Acquire ownership before either queue starts: otherwise two simultaneous
        # launches could split ownership of the ASR and TTS queues across hosts.
        container = AppContainer(settings)
        control = WorkerControlServer(
            WorkerControlStore(settings.storage.data_dir / "worker-control.sqlite3"),
            container.tts, container.asr,
        )
        # The API owns production dispatch. Workers only execute accepted TTS/ASR
        # tasks and explicit model-control commands, including after API restart.
        control.start()
        print("Inference worker online; stop with Ctrl+C.", flush=True)
        while not stopped.wait(1):
            if control._thread is not None and not control._thread.is_alive():
                raise RuntimeError("Inference control worker stopped unexpectedly")
    finally:
        try:
            if control is not None:
                control.shutdown()
        finally:
            try:
                if container is not None:
                    container.shutdown()
            finally:
                host_lock.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
