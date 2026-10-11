from contextlib import contextmanager
import threading
import time

from vvoice.core.errors import JobQueueFullError
from vvoice.shared.jobs.durable import FileLock


class AdmissionGate:
    """Bound pending direct callers as well as active native model calls."""
    def __init__(self, *, max_waiters=32, timeout=600, lock_path=None):
        self._slots = threading.BoundedSemaphore(max_waiters)
        self._native = threading.RLock()
        self._local = threading.local()
        self.timeout = timeout
        self._process = FileLock(lock_path) if lock_path is not None else None

    @contextmanager
    def enter(self):
        # Nested lifecycle/deployment calls already own admission. Counting them
        # again could reject the active worker when waiting callers fill the bound.
        if getattr(self._local, 'entered', False):
            yield
            return
        if not self._slots.acquire(blocking=False):
            raise JobQueueFullError('Model capacity is busy; retry later')
        acquired = False
        process_acquired = False
        deadline = time.monotonic() + self.timeout
        try:
            acquired = self._native.acquire(timeout=self.timeout)
            if not acquired:
                raise JobQueueFullError('Timed out waiting for model capacity; retry later')
            if self._process is not None:
                while not self._process.acquire(blocking=False):
                    if time.monotonic() >= deadline:
                        raise JobQueueFullError('Timed out waiting for model capacity; retry later')
                    time.sleep(.05)
                process_acquired = True
            self._local.entered = True
            yield
        finally:
            self._local.entered = False
            if process_acquired:
                self._process.release()
            if acquired:
                self._native.release()
            self._slots.release()


DEFAULT_GATE = AdmissionGate()
