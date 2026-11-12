import threading
import time

import pytest
from codeact.sandbox_pool import (
    PoolAcquireTimeout,
    PoolClosedError,
    WarmSandboxPool,
)


class FakeBackend:
    def __init__(self) -> None:
        self.next_id = 1
        self.created: list[int] = []
        self.destroyed: list[int] = []
        self.unhealthy: set[int] = set()
        self.block_create = threading.Event()
        self.block_create.set()

    def create(self) -> int:
        self.block_create.wait(timeout=1)
        handle = self.next_id
        self.next_id += 1
        self.created.append(handle)
        return handle

    def destroy(self, handle: int) -> None:
        self.destroyed.append(handle)

    def is_healthy(self, handle: int) -> bool:
        return handle not in self.unhealthy


def wait_for_available(pool: WarmSandboxPool[int], expected: int) -> None:
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        if pool.stats().available == expected:
            return
        time.sleep(0.005)
    raise AssertionError(f"pool did not reach {expected} available sandboxes")


def test_pool_starts_at_fixed_capacity_and_acquires_clean_lease() -> None:
    backend = FakeBackend()
    pool = WarmSandboxPool(backend, size=2)
    pool.start()
    assert pool.stats().available == 2
    with pool.acquire() as lease:
        assert lease.handle in (1, 2)
        assert pool.stats().leased == 1
    wait_for_available(pool, 2)
    assert lease.handle in backend.destroyed
    assert len(backend.created) == 3
    pool.close()


def test_release_is_idempotent_and_never_returns_dirty_handle() -> None:
    backend = FakeBackend()
    pool = WarmSandboxPool(backend, size=1)
    pool.start()
    first = pool.acquire()
    dirty_handle = first.handle
    first.release()
    first.release()
    wait_for_available(pool, 1)
    second = pool.acquire()
    assert second.handle != dirty_handle
    assert backend.destroyed.count(dirty_handle) == 1
    second.release()
    pool.close()


def test_acquire_times_out_when_capacity_is_leased() -> None:
    pool = WarmSandboxPool(FakeBackend(), size=1, acquire_timeout_seconds=0.02)
    pool.start()
    lease = pool.acquire()
    with pytest.raises(PoolAcquireTimeout):
        pool.acquire()
    lease.release()
    pool.close()


def test_unhealthy_available_instance_is_destroyed_and_replaced() -> None:
    backend = FakeBackend()
    pool = WarmSandboxPool(backend, size=1)
    pool.start()
    backend.unhealthy.add(1)
    lease = pool.acquire(timeout_seconds=1)
    assert lease.handle == 2
    assert 1 in backend.destroyed
    lease.release()
    pool.close()


def test_close_is_idempotent_and_rejects_future_operations() -> None:
    backend = FakeBackend()
    pool = WarmSandboxPool(backend, size=2)
    pool.start()
    pool.close()
    pool.close()
    assert sorted(backend.destroyed) == [1, 2]
    with pytest.raises(PoolClosedError):
        pool.acquire()
    with pytest.raises(PoolClosedError):
        pool.start()


def test_invalid_configuration_and_start_failure_cleanup() -> None:
    with pytest.raises(ValueError, match="size"):
        WarmSandboxPool(FakeBackend(), size=0)
    with pytest.raises(ValueError, match="timeout"):
        WarmSandboxPool(FakeBackend(), acquire_timeout_seconds=0)
    with pytest.raises(ValueError, match="retry"):
        WarmSandboxPool(FakeBackend(), replacement_retry_seconds=0)

    class FailingBackend(FakeBackend):
        def create(self) -> int:
            if self.next_id == 2:
                raise RuntimeError("create failed")
            return super().create()

    backend = FailingBackend()
    pool = WarmSandboxPool(backend, size=2)
    with pytest.raises(RuntimeError, match="create failed"):
        pool.start()
    assert backend.destroyed == [1]


def test_replacement_retries_after_transient_create_failures() -> None:
    class FlakyBackend(FakeBackend):
        failures_remaining = 2

        def create(self) -> int:
            if self.created and self.failures_remaining:
                self.failures_remaining -= 1
                raise RuntimeError("temporary Docker failure")
            return super().create()

    backend = FlakyBackend()
    pool = WarmSandboxPool(backend, size=1, replacement_retry_seconds=0.001)
    pool.start()
    pool.acquire().release()
    wait_for_available(pool, 1)
    assert pool.stats().replacement_failures == 2
    pool.close()


def test_concurrent_acquisition_never_exceeds_pool_capacity() -> None:
    backend = FakeBackend()
    pool = WarmSandboxPool(backend, size=2, acquire_timeout_seconds=1)
    pool.start()
    active = 0
    maximum_active = 0
    lock = threading.Lock()
    start = threading.Barrier(7)

    def worker() -> None:
        nonlocal active, maximum_active
        start.wait()
        with pool.acquire():
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.01)
            with lock:
                active -= 1

    workers = [threading.Thread(target=worker) for _ in range(6)]
    for worker_thread in workers:
        worker_thread.start()
    start.wait()
    for worker_thread in workers:
        worker_thread.join()
    assert maximum_active == 2
    wait_for_available(pool, 2)
    pool.close()
