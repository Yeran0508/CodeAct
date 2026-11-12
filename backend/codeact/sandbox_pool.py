from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

HandleT = TypeVar("HandleT")


class SandboxBackend(Protocol[HandleT]):
    def create(self) -> HandleT: ...

    def destroy(self, handle: HandleT) -> None: ...

    def is_healthy(self, handle: HandleT) -> bool: ...


class PoolClosedError(RuntimeError):
    pass


class PoolAcquireTimeout(TimeoutError):
    pass


@dataclass(frozen=True)
class PoolStats:
    target_size: int
    live: int
    available: int
    leased: int
    replacements_in_flight: int
    replacement_failures: int


class SandboxLease(Generic[HandleT]):
    def __init__(self, pool: WarmSandboxPool[HandleT], handle: HandleT) -> None:
        self._pool = pool
        self.handle = handle
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._pool._release(self.handle)

    def __enter__(self) -> SandboxLease[HandleT]:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()


class WarmSandboxPool(Generic[HandleT]):
    """Bounded clean-instance pool; every completed lease is destroyed and replaced."""

    def __init__(
        self,
        backend: SandboxBackend[HandleT],
        *,
        size: int = 4,
        acquire_timeout_seconds: float = 10.0,
        replacement_retry_seconds: float = 0.1,
    ) -> None:
        if size < 1:
            raise ValueError("pool size must be positive")
        if acquire_timeout_seconds <= 0:
            raise ValueError("acquire timeout must be positive")
        if replacement_retry_seconds <= 0:
            raise ValueError("replacement retry interval must be positive")
        self.backend = backend
        self.size = size
        self.acquire_timeout_seconds = acquire_timeout_seconds
        self.replacement_retry_seconds = replacement_retry_seconds
        self._available: queue.Queue[HandleT] = queue.Queue(maxsize=size)
        self._live: set[HandleT] = set()
        self._lock = threading.Lock()
        self._closed = False
        self._started = False
        self._replacement_threads: set[threading.Thread] = set()
        self._replacement_failures = 0
        self._close_event = threading.Event()

    def start(self) -> None:
        with self._lock:
            if self._closed:
                raise PoolClosedError("sandbox pool is closed")
            if self._started:
                return
            self._started = True
        created: list[HandleT] = []
        try:
            for _ in range(self.size):
                created.append(self.backend.create())
        except BaseException:
            for handle in created:
                self.backend.destroy(handle)
            with self._lock:
                self._started = False
            raise
        with self._lock:
            if self._closed:
                for handle in created:
                    self.backend.destroy(handle)
                raise PoolClosedError("sandbox pool closed during startup")
            self._live.update(created)
            for handle in created:
                self._available.put_nowait(handle)

    def acquire(self, timeout_seconds: float | None = None) -> SandboxLease[HandleT]:
        with self._lock:
            if self._closed:
                raise PoolClosedError("sandbox pool is closed")
            if not self._started:
                raise RuntimeError("sandbox pool must be started before acquire")
        timeout = self.acquire_timeout_seconds if timeout_seconds is None else timeout_seconds
        if timeout <= 0:
            raise ValueError("acquire timeout must be positive")
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PoolAcquireTimeout("timed out waiting for a clean sandbox")
            try:
                handle = self._available.get(timeout=remaining)
            except queue.Empty as error:
                raise PoolAcquireTimeout("timed out waiting for a clean sandbox") from error
            with self._lock:
                if self._closed:
                    self._remove_and_destroy(handle)
                    raise PoolClosedError("sandbox pool is closed")
            if self.backend.is_healthy(handle):
                return SandboxLease(self, handle)
            self._discard(handle)

    def _discard(self, handle: HandleT) -> None:
        with self._lock:
            self._live.discard(handle)
        self.backend.destroy(handle)
        self._schedule_replacement()

    def _release(self, handle: HandleT) -> None:
        with self._lock:
            was_live = handle in self._live
            self._live.discard(handle)
            closed = self._closed
        if not was_live:
            return
        self.backend.destroy(handle)
        if not closed:
            self._schedule_replacement()

    def _schedule_replacement(self) -> None:
        thread = threading.Thread(target=self._replace_once, daemon=True)
        with self._lock:
            if self._closed:
                return
            self._replacement_threads.add(thread)
        thread.start()

    def _replace_once(self) -> None:
        current = threading.current_thread()
        try:
            while not self._close_event.is_set():
                try:
                    handle = self.backend.create()
                except Exception:
                    with self._lock:
                        self._replacement_failures += 1
                    if self._close_event.wait(self.replacement_retry_seconds):
                        return
                    continue
                with self._lock:
                    if self._closed:
                        destroy = True
                    else:
                        self._live.add(handle)
                        self._available.put_nowait(handle)
                        destroy = False
                if destroy:
                    self.backend.destroy(handle)
                return
        finally:
            with self._lock:
                self._replacement_threads.discard(current)

    def _remove_and_destroy(self, handle: HandleT) -> None:
        self._live.discard(handle)
        self.backend.destroy(handle)

    def stats(self) -> PoolStats:
        with self._lock:
            live = len(self._live)
            available = self._available.qsize()
            return PoolStats(
                target_size=self.size,
                live=live,
                available=available,
                leased=live - available,
                replacements_in_flight=len(self._replacement_threads),
                replacement_failures=self._replacement_failures,
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._close_event.set()
            threads = tuple(self._replacement_threads)
        for thread in threads:
            thread.join(timeout=5)
        with self._lock:
            handles = tuple(self._live)
            self._live.clear()
            while True:
                try:
                    self._available.get_nowait()
                except queue.Empty:
                    break
        for handle in handles:
            self.backend.destroy(handle)
