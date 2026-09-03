"""Запуск процессов yt-dlp вне GUI-потока.

Аналог ffmpeg_gui/services/process_manager.py: единственное место, где
создаются subprocess'ы yt-dlp. GUI никогда не вызывает эти методы
напрямую — только через QueueManager.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..core.command_builder import POSTPROCESS_PREFIX, PROGRESS_PREFIX
from ..core.error_analyzer import AnalyzedError, analyze
from ..core.models import Job, ProgressInfo, ResultInfo
from .ytdlp_service import creation_flags, subprocess_env

log = logging.getLogger("ytdlp")

ProgressCallback = Callable[[Job, ProgressInfo], None]
StageCallback = Callable[[Job, str], None]
LogCallback = Callable[[Job, str], None]

STDERR_TAIL = 200
TERMINATE_TIMEOUT = 5.0


@dataclass
class RunResult:
    returncode: int
    cancelled: bool = False
    stderr: str = ""
    result: ResultInfo | None = None
    error: AnalyzedError | None = None
    duration: float = 0.0
    log_path: Path | None = None
    extra: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.cancelled and self.error is None


def _parse_progress_json(line: str) -> ProgressInfo | None:
    # Строка приходит из --progress-template yt-dlp и в норме всегда
    # валидный JSON-объект с числовыми полями, но парсинг всё равно
    # обёрнут широко: если формат вдруг изменится/повредится, разбор
    # прогресса не должен уронить весь поток загрузки.
    try:
        data = json.loads(line)
        if not isinstance(data, dict):
            return None
        info = ProgressInfo(
            status=data.get("status", ""),
            downloaded_bytes=data.get("downloaded_bytes"),
            total_bytes=data.get("total_bytes") or data.get("total_bytes_estimate"),
            fragment_index=data.get("fragment_index"),
            fragment_count=data.get("fragment_count"),
            speed=data.get("speed"),
            eta=data.get("eta"),
            elapsed=data.get("elapsed"),
            filename=data.get("filename"),
        )
        if info.total_bytes and info.downloaded_bytes is not None:
            info.fraction = max(0.0, min(1.0, info.downloaded_bytes / info.total_bytes))
        elif info.status == "finished":
            info.fraction = 1.0
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return None
    return info


class ProcessManager:
    """Единственное место, где создаются процессы yt-dlp."""

    def __init__(self, log_dir: Path | None = None) -> None:
        self.log_dir = Path(log_dir) if log_dir else None
        self._processes: dict[str, subprocess.Popen] = {}
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def run_job(
        self,
        job: Job,
        command: list[str],
        final_path_file: Path | None = None,
        on_progress: ProgressCallback | None = None,
        on_stage: StageCallback | None = None,
        on_log: LogCallback | None = None,
    ) -> RunResult:
        started = time.monotonic()
        log_file = self._open_log(job, command)

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                shell=False,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creation_flags(),
                env=subprocess_env(),
            )
        except OSError as exc:
            error = AnalyzedError(analyze("", -1).category, "Не удалось запустить yt-dlp.", str(exc))
            self._write_log(log_file, f"SPAWN ERROR: {exc}")
            self._close_log(log_file)
            return RunResult(-1, stderr=str(exc), error=error, log_path=self._log_path(log_file))

        with self._lock:
            self._processes[job.id] = process
            self._cancelled.discard(job.id)

        stderr_lines: list[str] = []
        stderr_thread = threading.Thread(
            target=self._drain_stderr,
            args=(process, stderr_lines, job, on_log, log_file),
            daemon=True,
        )
        stderr_thread.start()

        last_progress = ProgressInfo()
        output_files: list[str] = []
        try:
            if process.stdout is not None:
                for raw_line in process.stdout:
                    line = raw_line.strip()
                    if not line:
                        continue
                    self._write_log(log_file, line)
                    if line.startswith(PROGRESS_PREFIX):
                        payload = line[len(PROGRESS_PREFIX) :]
                        info = _parse_progress_json(payload)
                        if info is not None:
                            last_progress = info
                            if on_progress:
                                on_progress(job, info)
                    elif line.startswith(POSTPROCESS_PREFIX):
                        payload = line[len(POSTPROCESS_PREFIX) :]
                        stage = _postprocess_stage(payload)
                        if stage and on_stage:
                            on_stage(job, stage)
                    elif on_log:
                        on_log(job, line)
        except (OSError, ValueError) as exc:
            log.debug("Чтение прогресса прервано: %s", exc)

        returncode = process.wait()
        stderr_thread.join(timeout=2)
        with self._lock:
            self._processes.pop(job.id, None)
            cancelled = job.id in self._cancelled
            self._cancelled.discard(job.id)

        elapsed = time.monotonic() - started
        stderr_text = "\n".join(stderr_lines[-STDERR_TAIL:])
        self._write_log(log_file, f"exit code: {returncode}; время: {elapsed:.1f} c")

        if cancelled:
            self._write_log(log_file, "Загрузка отменена пользователем")
            self._close_log(log_file)
            self._discard_final_path_file(final_path_file)
            return RunResult(
                returncode, cancelled=True, stderr=stderr_text, duration=elapsed,
                log_path=self._log_path(log_file),
            )

        if returncode != 0:
            error = analyze(stderr_text, returncode)
            self._write_log(log_file, f"Ошибка: {error.category.value}: {error.reason}")
            self._close_log(log_file)
            self._discard_final_path_file(final_path_file)
            return RunResult(
                returncode, stderr=stderr_text, error=error, duration=elapsed,
                log_path=self._log_path(log_file),
            )

        for path in self._read_final_path_file(final_path_file):
            _track_output_file(output_files, path)

        total_size = sum(_size_of(Path(p)) for p in output_files)
        average_speed = (total_size / elapsed) if elapsed > 0 and total_size else last_progress.speed
        result = ResultInfo(
            output_files=output_files,
            total_size=total_size,
            processing_time=elapsed,
            average_speed=average_speed,
            title=job.label,
        )
        job.output_files = output_files
        self._write_log(log_file, f"Результат: {len(output_files)} файл(ов), {total_size} байт")
        self._close_log(log_file)
        return RunResult(
            returncode, stderr=stderr_text, result=result, duration=elapsed,
            log_path=self._log_path(log_file),
        )

    # ------------------------------------------------------------------
    def cancel(self, job_id: str) -> bool:
        with self._lock:
            process = self._processes.get(job_id)
            if process is None:
                return False
            self._cancelled.add(job_id)

        try:
            process.terminate()
        except OSError as exc:
            log.debug("terminate() не удался: %s", exc)
        try:
            process.wait(timeout=TERMINATE_TIMEOUT)
        except subprocess.TimeoutExpired:
            log.warning("yt-dlp не завершился, отправляю kill()")
            try:
                process.kill()
                process.wait(timeout=TERMINATE_TIMEOUT)
            except (OSError, subprocess.TimeoutExpired) as exc:
                log.error("Не удалось завершить процесс: %s", exc)
                return False
        return True

    def cancel_all(self) -> None:
        with self._lock:
            job_ids = list(self._processes)
        for job_id in job_ids:
            self.cancel(job_id)

    def is_running(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._processes

    @property
    def running_count(self) -> int:
        with self._lock:
            return len(self._processes)

    # ------------------------------------------------------------------
    def _drain_stderr(self, process, sink, job, on_log, log_file) -> None:
        if process.stderr is None:
            return
        try:
            for raw_line in process.stderr:
                line = raw_line.rstrip()
                if not line:
                    continue
                sink.append(line)
                if len(sink) > STDERR_TAIL * 4:
                    del sink[:STDERR_TAIL]
                self._write_log(log_file, line)
                if on_log:
                    on_log(job, line)
        except (OSError, ValueError):
            pass

    def _open_log(self, job: Job, command: list[str]):
        if not self.log_dir:
            return None
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            path = self.log_dir / f"{job.id}.log"
            handle = path.open("a", encoding="utf-8")
        except OSError as exc:
            log.warning("Не удалось открыть лог задания: %s", exc)
            return None
        job.log_path = str(path)
        handle.write(f"=== {job.label} | {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        handle.write("Команда: " + " ".join(command) + "\n")
        handle.flush()
        return handle

    @staticmethod
    def _write_log(handle, message: str) -> None:
        if handle is None:
            return
        try:
            handle.write(message + "\n")
            handle.flush()
        except (OSError, ValueError):
            pass

    @staticmethod
    def _close_log(handle) -> None:
        if handle is None:
            return
        try:
            handle.write("=== конец ===\n")
            handle.close()
        except (OSError, ValueError):
            pass

    @staticmethod
    def _read_final_path_file(path: Path | None) -> list[str]:
        """Читает пути итоговых файлов, записанные yt-dlp через
        ``--print-to-file after_move:...`` (см. command_builder.build)."""
        if path is None:
            return []
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        finally:
            ProcessManager._discard_final_path_file(path)
        return [line.strip() for line in text.splitlines() if line.strip()]

    @staticmethod
    def _discard_final_path_file(path: Path | None) -> None:
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _log_path(handle) -> Path | None:
        if handle is None:
            return None
        try:
            return Path(handle.name)
        except (AttributeError, TypeError):
            return None


def _postprocess_stage(payload: str) -> str | None:
    try:
        data = json.loads(payload)
        if not isinstance(data, dict):
            return None
        name = data.get("postprocessor", "")
        status = data.get("status", "")
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return None
    if not name:
        return None
    labels = {
        "FFmpegMerger": "Объединение видео и аудио",
        "FFmpegVideoConvertor": "Конвертация контейнера",
        "FFmpegExtractAudio": "Извлечение аудио",
        "FFmpegEmbedSubtitle": "Встраивание субтитров",
        "FFmpegMetadata": "Запись метаданных",
        "EmbedThumbnail": "Встраивание обложки",
        "FFmpegThumbnailsConvertor": "Обработка обложки",
        "MoveFiles": "Перемещение файлов",
    }
    label = labels.get(name, name)
    return f"{label}…" if status == "started" else f"{label} — готово"


def _track_output_file(output_files: list[str], filename: str) -> None:
    if filename not in output_files:
        output_files.append(filename)


def _size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0
