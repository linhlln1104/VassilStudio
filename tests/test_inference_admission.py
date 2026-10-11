from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from vvoice.core.errors import JobQueueFullError
from vvoice.inference.admission import AdmissionGate


def test_active_worker_can_reenter_when_admission_capacity_is_full(tmp_path):
    gate = AdmissionGate(max_waiters=1, timeout=.1, lock_path=tmp_path / 'native.lock')
    with ThreadPoolExecutor(max_workers=1) as executor:
        with gate.enter():
            with gate.enter():
                pass
            with pytest.raises(JobQueueFullError, match='capacity is busy'):
                executor.submit(lambda: execute(gate)).result(timeout=2)
        assert executor.submit(lambda: execute(gate)).result(timeout=2)


def execute(gate):
    with gate.enter():
        return True


def test_separate_gate_instances_serialize_shared_native_resource(tmp_path):
    path = tmp_path / 'native.lock'
    first, second = AdmissionGate(lock_path=path), AdmissionGate(lock_path=path)
    attempted, entered = threading.Event(), threading.Event()

    def other():
        attempted.set()
        with second.enter():
            entered.set()

    with ThreadPoolExecutor(max_workers=1) as executor:
        with first.enter():
            future = executor.submit(other)
            assert attempted.wait(2)
            assert not entered.wait(.1)
        future.result(timeout=2)
    assert entered.is_set()
