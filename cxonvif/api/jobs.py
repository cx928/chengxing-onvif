"""后台任务注册表 / Background job registry（下载模型、导出模型、刷新硬件画像）。"""

from __future__ import annotations

import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Job:
    id: str
    name: str
    status: str = "running"      # running | done | error
    progress: float = 0.0
    message: str = ""
    result: Any = None
    error: str = ""
    startedAt: float = field(default_factory=time.time)
    finishedAt: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "progress": round(float(self.progress), 3),
            "message": self.message,
            "result": self.result,
            "error": self.error,
            "startedAt": self.startedAt,
            "finishedAt": self.finishedAt,
        }


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._counter = 0

    def start(self, name: str, fn: Callable[[Callable[[float, str], None]], Any]) -> Job:
        with self._lock:
            self._counter += 1
            job = Job(id=f"job{self._counter}", name=name, message="已开始")
            self._jobs[job.id] = job
        thread = threading.Thread(target=self._run, args=(job, fn), name=job.id, daemon=True)
        thread.start()
        return job

    def _run(self, job: Job, fn) -> None:
        def progress(value: float, message: str = "") -> None:
            job.progress = max(0.0, min(1.0, float(value)))
            if message:
                job.message = message

        try:
            job.result = fn(progress)
            job.status = "done"
            job.progress = 1.0
            job.message = job.message or "完成"
        except Exception as exc:
            job.status = "error"
            job.error = str(exc)
            job.message = f"失败：{exc}"
            traceback.print_exc()
        finally:
            job.finishedAt = time.time()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.startedAt, reverse=True)
        return [job.to_dict() for job in jobs[:limit]]

    def cleanup(self, keep_seconds: float = 3600) -> None:
        cutoff = time.time() - keep_seconds
        with self._lock:
            for job_id in [j.id for j in self._jobs.values() if j.finishedAt and j.finishedAt < cutoff]:
                self._jobs.pop(job_id, None)
