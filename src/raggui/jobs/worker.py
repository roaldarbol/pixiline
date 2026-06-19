"""QProcess-backed worker that runs a job's steps in sequence.

A job is a chain of pipeline steps; each is one ``pixi run`` process. The worker
launches them one at a time, advancing to the next only when the current one
exits 0. Stdout+stderr are merged and streamed out as ``log`` so the Jobs tab can
show live output. Exactly one of ``finished`` / ``failed`` / ``canceled`` fires.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QProcess, Signal

from raggui.jobs.job import Job, JobState
from raggui.pipeline import build_command, working_directory

_KILL_GRACE_MS = 3000


class Worker(QObject):
    progress = Signal(int, float)        # job_id, fraction in [0, 1]
    step_changed = Signal(int, int, str)  # job_id, step_index, step_name
    log = Signal(int, str)               # job_id, text chunk
    finished = Signal(int)               # job_id
    failed = Signal(int, str)            # job_id, message
    canceled = Signal(int)               # job_id

    def __init__(self, job: Job, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._job = job
        self._proc = QProcess(self)
        self._proc.setWorkingDirectory(working_directory())
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(self._on_step_finished)
        self._proc.errorOccurred.connect(self._on_error)
        self._canceled = False
        self._launch_failed = False

    @property
    def job(self) -> Job:
        return self._job

    def start(self) -> None:
        self._job.state = JobState.RUNNING
        self._job.current_step = 0
        if not self._job.steps:
            # Nothing selected — treat as an immediate, successful no-op.
            self.finished.emit(self._job.id)
            return
        self._start_current_step()

    def cancel(self) -> None:
        self._canceled = True
        if self._proc.state() == QProcess.ProcessState.NotRunning:
            self._job.state = JobState.CANCELED
            self.canceled.emit(self._job.id)
            return
        self._proc.terminate()
        if not self._proc.waitForFinished(_KILL_GRACE_MS):
            self._proc.kill()
            self._proc.waitForFinished(_KILL_GRACE_MS)

    # --- step driving --------------------------------------------------------

    def _start_current_step(self) -> None:
        name = self._job.current_step_name()
        if name is None:
            return
        self.step_changed.emit(self._job.id, self._job.current_step, name)
        self.progress.emit(self._job.id, self._job.fraction())
        cmd = build_command(
            name,
            self._job.input_path,
            self._job.output_base,
            self._job.stem,
            overwrite=self._job.overwrite,
        )
        self._emit_log(f"\n$ {' '.join(cmd)}\n")
        self._proc.start(cmd[0], cmd[1:])

    def _on_step_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        if self._canceled:
            self._job.state = JobState.CANCELED
            self.canceled.emit(self._job.id)
            return
        if self._launch_failed:
            return  # _on_error already reported the failure
        name = self._job.current_step_name() or "?"
        if code != 0 or status != QProcess.ExitStatus.NormalExit:
            message = f"Step '{name}' failed (exit code {code})."
            self._job.state = JobState.FAILED
            self._job.error = message
            self._emit_log(f"\n[{message}]\n")
            self.failed.emit(self._job.id, message)
            return
        # Step succeeded → advance.
        self._job.current_step += 1
        self.progress.emit(self._job.id, self._job.fraction())
        if self._job.current_step >= len(self._job.steps):
            self._job.state = JobState.DONE
            self.finished.emit(self._job.id)
            return
        self._start_current_step()

    def _on_error(self, error: QProcess.ProcessError) -> None:
        # Most important case: the program (pixi) could not be started at all.
        if error == QProcess.ProcessError.FailedToStart and not self._canceled:
            self._launch_failed = True
            message = (
                "Could not launch 'pixi'. Make sure pixi is installed and on PATH "
                "(or set the PIXI_EXE environment variable)."
            )
            self._job.state = JobState.FAILED
            self._job.error = message
            self._emit_log(f"\n[{message}]\n")
            self.failed.emit(self._job.id, message)

    # --- output --------------------------------------------------------------

    def _on_output(self) -> None:
        data = bytes(self._proc.readAllStandardOutput())
        if data:
            self._emit_log(data.decode("utf-8", errors="replace"))

    def _emit_log(self, text: str) -> None:
        self._job.append_log(text)
        self.log.emit(self._job.id, text)
