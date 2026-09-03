"""Очередь заданий загрузки с параллельным выполнением.

``QueueManager`` — единственное место, порождающее рабочие потоки для
``ProcessManager``. GUI никогда не запускает yt-dlp напрямую: он добавляет
``Job`` в очередь и подписывается на события через колбэки/шину событий.
"""

from __future__ import annotations

import logging
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..core import command_builder
from ..core.command_builder import CommandBuildError
from ..core.models import Job, JobStatus, ProgressInfo
from ..core.validator import validate
from .filesystem_service import FilesystemService
from .process_manager import ProcessManager
from .ytdlp_service import YtdlpService

log = logging.getLogger(__name__)


@dataclass
class QueueCallbacks:
    on_job_added: Callable[[Job], None] | None = None
    on_job_started: Callable[[Job], None] | None = None
    on_job_progress: Callable[[Job, ProgressInfo], None] | None = None
    on_job_stage: Callable[[Job, str], None] | None = None
    on_job_finished: Callable[[Job], None] | None = None
    on_job_log: Callable[[Job, str], None] | None = None
    on_queue_changed: Callable[[], None] | None = None
    on_queue_idle: Callable[[], None] | None = None

    def _call(self, name: str, *args) -> None:
        callback = getattr(self, name)
        if callback is not None:
            try:
                callback(*args)
            except Exception:  # noqa: BLE001 - колбэки не должны ронять очередь
                log.exception("Ошибка в колбэке очереди %s", name)


class QueueManager:
    def __init__(
        self,
        ytdlp: YtdlpService,
        processes: ProcessManager,
        filesystem: FilesystemService,
        network_args_provider: Callable[[], list[str]] | None = None,
        callbacks: QueueCallbacks | None = None,
        parallel_jobs: int = 1,
    ) -> None:
        self.ytdlp = ytdlp
        self.processes = processes
        self.filesystem = filesystem
        self.network_args_provider = network_args_provider or (lambda: [])
        self.callbacks = callbacks or QueueCallbacks()
        self.parallel_jobs = max(1, parallel_jobs)

        self.jobs: list[Job] = []
        self._lock = threading.RLock()
        self._running: set[str] = set()
        self._active = False

    # -- управление ----------------------------------------------------
    def add(self, job: Job) -> None:
        with self._lock:
            self.jobs.append(job)
        self.callbacks._call("on_job_added", job)
        self.callbacks._call("on_queue_changed")

    def start(self) -> None:
        self._active = True
        self._dispatch()

    def set_parallel_jobs(self, count: int) -> None:
        self.parallel_jobs = max(1, count)
        self._dispatch()

    def remove(self, job_id: str) -> bool:
        with self._lock:
            job = self._find(job_id)
            if job is None or job.is_active:
                return False
            self.jobs.remove(job)
        self.callbacks._call("on_queue_changed")
        return True

    def clear_finished(self) -> None:
        with self._lock:
            self.jobs = [job for job in self.jobs if not job.is_finished]
        self.callbacks._call("on_queue_changed")

    def move(self, job_id: str, offset: int) -> bool:
        with self._lock:
            job = self._find(job_id)
            if job is None:
                return False
            index = self.jobs.index(job)
            new_index = max(0, min(len(self.jobs) - 1, index + offset))
            if new_index == index:
                return False
            self.jobs.pop(index)
            self.jobs.insert(new_index, job)
        self.callbacks._call("on_queue_changed")
        return True

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._find(job_id)
            if job is None:
                return False
            if job.status == JobStatus.PENDING.value:
                job.status = JobStatus.CANCELLED.value
                self.callbacks._call("on_queue_changed")
                return True
        return self.processes.cancel(job_id)

    def shutdown(self) -> None:
        self._active = False
        self.processes.cancel_all()

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._running)

    # -- внутренняя механика --------------------------------------------
    def _find(self, job_id: str) -> Job | None:
        for job in self.jobs:
            if job.id == job_id:
                return job
        return None

    def _dispatch(self) -> None:
        if not self._active:
            return
        with self._lock:
            while len(self._running) < self.parallel_jobs:
                next_job = next(
                    (j for j in self.jobs if j.status == JobStatus.PENDING.value), None
                )
                if next_job is None:
                    break
                next_job.status = JobStatus.RUNNING.value
                self._running.add(next_job.id)
                thread = threading.Thread(target=self._run_job, args=(next_job,), daemon=True)
                thread.start()

    def _run_job(self, job: Job) -> None:
        job.started_at = datetime.now()
        self.callbacks._call("on_job_started", job)

        validation = validate(job)
        if not validation.ok:
            job.status = JobStatus.FAILED.value
            job.error = "\n".join(issue.message for issue in validation.errors)
            job.error_category = "invalid_argument"
            self._finish(job)
            return

        # Всё, что ниже, выполняется в фоновом потоке без надзора GUI.
        # Любое неперехваченное исключение здесь тихо убьёт этот поток,
        # оставив job в статусе RUNNING навсегда: слот в self._running не
        # освободится, _finish() не вызовется, и при достижении лимита
        # parallel_jobs очередь перестанет запускать новые задания —
        # внешне выглядит как "программа зависла", без единой ошибки в
        # интерфейсе. Поэтому весь риск обёрнут одним try/except Exception
        # с гарантией, что self._finish(job) будет вызван в любом случае.
        final_path_file = Path(tempfile.gettempdir()) / f"ytgui-final-{job.id}.txt"
        try:
            base_command = self.ytdlp.base_command()
            output_template = self.filesystem.output_template(
                job.output_dir, job.options.output_template
            )
            command = command_builder.build(
                job,
                base_command,
                output_template,
                self.network_args_provider(),
                final_path_file=str(final_path_file),
            )
            job.command = command

            def _stage(j: Job, text: str) -> None:
                j.stage_text = text
                j.status = JobStatus.POSTPROCESSING.value
                self.callbacks._call("on_job_stage", j, text)

            result = self.processes.run_job(
                job,
                command,
                final_path_file=final_path_file,
                on_progress=lambda j, info: self.callbacks._call("on_job_progress", j, info),
                on_stage=_stage,
                on_log=lambda j, line: self.callbacks._call("on_job_log", j, line),
            )
        except (CommandBuildError, RuntimeError, OSError) as exc:
            job.status = JobStatus.FAILED.value
            job.error = str(exc)
            job.error_category = "invalid_argument"
            self._finish(job)
            return
        except Exception as exc:  # noqa: BLE001 - см. комментарий выше
            log.exception("Неожиданная ошибка при выполнении задания %s", job.id)
            job.status = JobStatus.FAILED.value
            job.error = f"Неожиданная ошибка: {exc}"
            job.error_category = None
            self._finish(job)
            return

        if result.cancelled:
            job.status = JobStatus.CANCELLED.value
        elif result.ok:
            job.status = JobStatus.COMPLETED.value
            job.progress = 1.0
        else:
            job.status = JobStatus.FAILED.value
            job.error = result.error.report() if result.error else result.stderr
            job.error_category = result.error.category.value if result.error else None

        job.log_path = str(result.log_path) if result.log_path else job.log_path
        self._finish(job)

    def _finish(self, job: Job) -> None:
        job.finished_at = datetime.now()
        with self._lock:
            self._running.discard(job.id)
        self.callbacks._call("on_job_finished", job)
        self.callbacks._call("on_queue_changed")
        self._dispatch()
        with self._lock:
            idle = not self._running and not any(
                j.status == JobStatus.PENDING.value for j in self.jobs
            )
        if idle:
            self.callbacks._call("on_queue_idle")
