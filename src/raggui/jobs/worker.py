"""QProcess-backed worker that runs a job's steps in sequence.

A job first installs the pixi environments its steps need ("Installing
environments"), then runs each step as one ``pixi run`` process, advancing only
when the current one exits 0 *and* produced its declared output. Stdout+stderr are
merged and streamed live (carriage returns normalized) so the Jobs tab shows
progress; a heartbeat marks long, quiet phases so they don't look hung. Exactly
one of ``finished`` / ``failed`` / ``canceled`` fires.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from raggui.jobs.job import Job, JobState
from raggui.paths import pixi_executable
from raggui.pipeline import (
    artifact_present,
    build_command,
    env_available,
    missing_needs,
    step_by_name,
    working_directory,
)

_KILL_GRACE_MS = 3000
_HEARTBEAT_MS = 15000
_INSTALL_LABEL = "Installing environments"

_PHASE_INSTALL = "install"
_PHASE_RUN = "run"


class Worker(QObject):
    progress = Signal(int, float)        # job_id, fraction in [0, 1]
    step_changed = Signal(int, int, str)  # job_id, step_index, label
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
        # Force child Python tools (behaveai / octron) to stream their progress
        # instead of block-buffering when stdout isn't a TTY, so the log is live.
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        self._proc.setProcessEnvironment(env)
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(self._on_step_finished)
        self._proc.errorOccurred.connect(self._on_error)
        self._canceled = False
        self._launch_failed = False
        self._phase = _PHASE_INSTALL
        self._phase_label = ""
        self._phase_started = 0.0
        self._heartbeat = QTimer(self)
        self._heartbeat.setInterval(_HEARTBEAT_MS)
        self._heartbeat.timeout.connect(self._on_heartbeat)

    @property
    def job(self) -> Job:
        return self._job

    def start(self) -> None:
        self._job.state = JobState.RUNNING
        self._job.current_step = 0
        if not self._job.steps:
            self.finished.emit(self._job.id)  # nothing selected — no-op
            return
        self._start_install()

    def cancel(self) -> None:
        self._canceled = True
        self._heartbeat.stop()
        if self._proc.state() == QProcess.ProcessState.NotRunning:
            self._job.state = JobState.CANCELED
            self.canceled.emit(self._job.id)
            return
        self._proc.terminate()
        if not self._proc.waitForFinished(_KILL_GRACE_MS):
            self._proc.kill()
            self._proc.waitForFinished(_KILL_GRACE_MS)

    # --- phases --------------------------------------------------------------

    def _start_install(self) -> None:
        """Install the pixi environments this job's steps need, up front."""
        self._phase = _PHASE_INSTALL
        by_name = step_by_name()
        envs: list[str] = []
        for name in self._job.steps:
            step = by_name.get(name)
            if step is None or not step.env:
                continue
            if not env_available(step.env):
                self._fail(
                    f"Step '{name}' needs environment '{step.env}', which isn't defined in "
                    "pixi.toml (is it commented out?). Remove the step from config.yaml `steps:` "
                    "or restore the environment."
                )
                return
            if step.env not in envs:
                envs.append(step.env)
        self.step_changed.emit(self._job.id, -1, _INSTALL_LABEL)
        self.progress.emit(self._job.id, 0.0)
        cmd = [pixi_executable(), "install"]
        for env in envs:
            cmd += ["-e", env]
        self._launch(cmd, _INSTALL_LABEL)

    def _start_current_step(self) -> None:
        self._phase = _PHASE_RUN
        name = self._job.current_step_name()
        if name is None:
            return
        step = step_by_name().get(name)
        # Fail fast if a required input isn't there (a prior step didn't produce
        # it, or the run started mid-chain without the prerequisites on disk).
        if step is not None:
            missing = missing_needs(step, self._job.input_path, self._job.output_base, self._job.stem)
            if missing:
                self._fail(f"Step '{name}' is missing required input(s): {', '.join(missing)}")
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
        self._launch(cmd, name)

    def _launch(self, cmd: list[str], label: str) -> None:
        self._phase_label = label
        self._phase_started = time.monotonic()
        self._emit_log(f"\n$ {self._fmt(cmd)}\n")
        self._heartbeat.start()
        self._proc.start(cmd[0], cmd[1:])

    # --- process completion --------------------------------------------------

    def _on_step_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        self._heartbeat.stop()
        if self._canceled:
            self._job.state = JobState.CANCELED
            self.canceled.emit(self._job.id)
            return
        if self._launch_failed:
            return  # _on_error already reported the failure
        failed = code != 0 or status != QProcess.ExitStatus.NormalExit

        if self._phase == _PHASE_INSTALL:
            if failed:
                self._fail(f"Installing environments failed (exit code {code}).")
                return
            self._start_current_step()  # environments ready → begin the steps
            return

        # Run phase.
        name = self._job.current_step_name() or "?"
        if failed:
            self._fail(f"Step '{name}' failed (exit code {code}).")
            return
        # Exited 0 — but verify it actually produced its declared output, so a
        # silent failure doesn't let the chain march on into missing data.
        step = step_by_name().get(name)
        if step and step.makes and not artifact_present(step.makes, self._job.output_base, self._job.stem):
            self._fail(f"Step '{name}' finished but did not produce its output: {step.makes}")
            return
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
            self._fail(
                "Could not launch 'pixi'. Make sure pixi is installed and on PATH "
                "(or set the PIXI_EXE environment variable)."
            )

    def _fail(self, message: str) -> None:
        """Mark the job failed, stop the chain, and report (log + signal)."""
        self._heartbeat.stop()
        self._job.state = JobState.FAILED
        self._job.error = message
        self._emit_log(f"\n[{message}]\n")
        self.failed.emit(self._job.id, message)

    # --- output --------------------------------------------------------------

    def _on_output(self) -> None:
        data = bytes(self._proc.readAllStandardOutput())
        if data:
            # Tools redraw progress with carriage returns; turn them into newlines
            # so each update is visible in the (non-terminal) log pane.
            text = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
            self._emit_log(text)

    def _on_heartbeat(self) -> None:
        elapsed = int(time.monotonic() - self._phase_started)
        self._emit_log(f"… {self._phase_label} — still working ({elapsed}s elapsed)…\n")

    def _emit_log(self, text: str) -> None:
        self._job.append_log(text)
        self.log.emit(self._job.id, text)

    @staticmethod
    def _fmt(cmd: list[str]) -> str:
        return " ".join(f'"{c}"' if " " in c else c for c in cmd)
