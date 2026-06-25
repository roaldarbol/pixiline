"""QProcess-backed worker that runs a job's steps in dependency order.

A job first installs the pixi environments its steps need ("Installing
environments"), then runs each step as one ``pixi run`` process, advancing only
when the current one exits 0. Stdout+stderr are merged and streamed live (control
sequences intact) so the Jobs tab's terminal log shows in-place progress. Exactly
one of ``finished`` / ``failed`` / ``canceled`` fires.
"""

from __future__ import annotations

import codecs
import contextlib
import datetime
import subprocess
import sys

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from pixiline import applog
from pixiline.jobs.job import Job, JobState
from pixiline.jobs.termlog import SettledLog
from pixiline.manifest import artifact_present, build_command, step_inputs_met
from pixiline.paths import pixi_executable

_KILL_GRACE_MS = 3000
_INSTALL_LABEL = "Installing environments"


def _kill_process_tree(pid: int) -> None:
    """Forcefully terminate a process *and all its descendants*.

    QProcess.terminate()/kill() only signals the direct child (here ``pixi``), so
    the heavy grandchildren (``nu`` → behaveai/octron → Python/torch) would keep
    running after a cancel. On Windows ``taskkill /T`` kills the whole tree.
    """
    if pid <= 0 or sys.platform != "win32":
        return  # POSIX falls back to QProcess.kill() in the caller
    with contextlib.suppress(OSError):
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


_PHASE_INSTALL = "install"
_PHASE_RUN = "run"


class Worker(QObject):
    progress = Signal(int, float)  # job_id, fraction in [0, 1]
    step_changed = Signal(int, int, str)  # job_id, step_index, label
    log = Signal(int, str)  # job_id, text chunk
    finished = Signal(int)  # job_id
    failed = Signal(int, str)  # job_id, message
    canceled = Signal(int)  # job_id

    def __init__(self, job: Job, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._job = job
        self._proc = QProcess(self)
        # Run from the pipeline's own workspace root (where its pixi.toml lives).
        self._proc.setWorkingDirectory(str(job.pipeline.root))
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        # Stream live (no block-buffering when stdout isn't a TTY), force colour
        # on, and pin a width so progress bars size to the log terminal's screen.
        env = QProcessEnvironment.systemEnvironment()
        # pixiline runs under `pixi run gui`, which exports PIXI_*/SSL_CERT vars that
        # would leak into the pipeline's own `pixi run` (wrong manifest, missing
        # certs). Drop them so the child resolves the pipeline's manifest cleanly.
        for leaked in (
            "PIXI_PROJECT_MANIFEST",
            "PIXI_PROJECT_ROOT",
            "PIXI_ENVIRONMENT_NAME",
            "PIXI_PROJECT_NAME",
            "PIXI_IN_SHELL",
            "SSL_CERT_DIR",
            "SSL_CERT_FILE",
        ):
            env.remove(leaked)
        env.insert("PYTHONUNBUFFERED", "1")
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("FORCE_COLOR", "1")  # honoured by rich/click/etc.
        env.insert("CLICOLOR_FORCE", "1")
        # loguru (octron/behaveai) ignores FORCE_COLOR; on Windows it only colours
        # when stdout is a TTY *or* TERM is set (loguru._colorama.should_colorize).
        # We pipe stdout, so without this its output comes through plain.
        env.insert("TERM", "xterm-256color")
        env.insert("COLUMNS", "120")
        env.insert("LINES", "300")
        self._proc.setProcessEnvironment(env)
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._proc.readyReadStandardOutput.connect(self._on_output)
        self._proc.finished.connect(self._on_step_finished)
        self._proc.errorOccurred.connect(self._on_error)
        self._canceled = False
        self._launch_failed = False
        self._phase = _PHASE_INSTALL
        self._logfile: SettledLog | None = None
        self._produced: set[str] = set()  # output globs of steps that have run

    @property
    def job(self) -> Job:
        return self._job

    def start(self) -> None:
        self._job.state = JobState.RUNNING
        self._job.current_step = 0
        if not self._job.steps:
            self.finished.emit(self._job.id)  # nothing selected — no-op
            return
        # A settled plain-text log of this run, timestamped so a later separate run
        # doesn't overwrite an earlier one, under the recording's logs/ folder.
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self._logfile = SettledLog(self._job.output_base / self._job.stem / "logs" / f"{stamp}.log")
        applog.log.info(
            f"Job {self._job.id} started: {self._job.pipeline.name} / {self._job.stem} | "
            f"steps: {', '.join(self._job.steps)} | output: {self._job.output_base}"
        )
        # A bold, coloured run header with a divider rule, to set this run apart
        # from the tool output below. (Our own text, so colouring it is fair game.)
        title = f"{self._job.stem}  —  {' → '.join(self._job.steps)}"
        rule = "─" * len(title)
        self._emit_log(f"\x1b[1;36m{title}\x1b[0m\n\x1b[36m{rule}\x1b[0m\n")
        self._start_install()

    def cancel(self) -> None:
        self._canceled = True
        if self._proc.state() == QProcess.ProcessState.NotRunning:
            self._job.state = JobState.CANCELED
            applog.log.info(f"Job {self._job.id} canceled")
            self._emit_log("\n\x1b[1;33m⊘  Job canceled\x1b[0m\n")  # bold amber
            self._close_log()
            self.canceled.emit(self._job.id)
            return
        # pixi doesn't kill its task tree, so terminate()/kill() would leave the
        # heavy grandchildren (octron/torch) running — kill the whole tree.
        _kill_process_tree(int(self._proc.processId()))
        if not self._proc.waitForFinished(_KILL_GRACE_MS):
            self._proc.kill()  # backstop (and non-Windows, where _kill is a no-op)
            self._proc.waitForFinished(_KILL_GRACE_MS)

    # --- phases --------------------------------------------------------------

    def _start_install(self) -> None:
        """Install the pixi environments this job's steps need, up front."""
        self._phase = _PHASE_INSTALL
        pipeline = self._job.pipeline
        envs: list[str] = []
        for name in self._job.steps:
            step = pipeline.step(name)
            if step is None or not step.env:
                continue
            if step.env not in pipeline.environments:
                self._fail(
                    f"Step '{name}' needs environment '{step.env}', which isn't defined in "
                    f"{pipeline.name}'s pixi.toml (is it commented out?)."
                )
                return
            if step.env not in envs:
                envs.append(step.env)
        self.step_changed.emit(self._job.id, -1, _INSTALL_LABEL)
        self.progress.emit(self._job.id, 0.0)
        cmd = [pixi_executable(), "install"]
        for env in envs:
            cmd += ["-e", env]
        self._launch(cmd)

    def _start_current_step(self) -> None:
        self._phase = _PHASE_RUN
        pipeline = self._job.pipeline
        # Snakemake-style: advance past selected steps whose inputs aren't available
        # for this file (Pixi caching separately skips steps with up-to-date outputs).
        while True:
            name = self._job.current_step_name()
            if name is None:
                self._finish()
                return
            step = pipeline.step(name)
            if step is None:
                self._fail(f"Step '{name}' is not defined in the pipeline.")
                return
            # Skip if already done (its output marker exists). Pixi's own caching is
            # inert on these paths, so pixiline decides; delete the output to re-run.
            if step.outputs and all(
                artifact_present(o, self._job.output_base, self._job.stem) for o in step.outputs
            ):
                self._emit_log(
                    f"\n[skipping '{name}': output already present — delete it to re-run]\n"
                )
                applog.log.info(f"Job {self._job.id}: step '{name}' skipped (already done)")
                self._produced |= set(step.outputs)
                self._job.current_step += 1
                self.progress.emit(self._job.id, self._job.fraction())
                continue
            if not step_inputs_met(
                step,
                has_input=True,
                output_base=self._job.output_base,
                stem=self._job.stem,
                produced=self._produced,
            ):
                self._emit_log(f"\n[skipping '{name}': required inputs not available]\n")
                applog.log.info(f"Job {self._job.id}: step '{name}' skipped (inputs unavailable)")
                self._job.current_step += 1
                self.progress.emit(self._job.id, self._job.fraction())
                continue
            break
        applog.log.info(f"Job {self._job.id}: step '{name}' running")
        self.step_changed.emit(self._job.id, self._job.current_step, name)
        self.progress.emit(self._job.id, self._job.fraction())
        cmd = build_command(step, self._job.values, pixi_executable())
        self._launch(cmd)

    def _launch(self, cmd: list[str]) -> None:
        self._emit_log(f"\n$ {self._fmt(cmd)}\n")
        self._proc.start(cmd[0], cmd[1:])

    # --- process completion --------------------------------------------------

    def _on_step_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        if self._canceled:
            self._job.state = JobState.CANCELED
            applog.log.info(f"Job {self._job.id} canceled")
            self._emit_log("\n\x1b[1;33m⊘  Job canceled\x1b[0m\n")  # bold amber
            self._close_log()
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
        applog.log.info(f"Job {self._job.id}: step '{name}' done")
        step = self._job.pipeline.step(name)
        if step is not None:
            self._produced |= set(step.outputs)  # its outputs now exist on disk
        self._job.current_step += 1
        self.progress.emit(self._job.id, self._job.fraction())
        self._start_current_step()  # runs the next step, or skips/finishes

    def _on_error(self, error: QProcess.ProcessError) -> None:
        # Most important case: the program (pixi) could not be started at all.
        if error == QProcess.ProcessError.FailedToStart and not self._canceled:
            self._launch_failed = True
            self._fail(
                "Could not launch 'pixi'. Make sure pixi is installed and on PATH "
                "(or set the PIXI_EXE environment variable)."
            )

    def _finish(self) -> None:
        """All selected steps have run or been skipped — the job is done."""
        self._job.state = JobState.DONE
        applog.log.info(f"Job {self._job.id} done")
        self._emit_log("\n\x1b[1;32m✓  Job finished\x1b[0m\n")  # bold green
        self._close_log()
        self.finished.emit(self._job.id)

    def _fail(self, message: str) -> None:
        """Mark the job failed, stop the chain, and report (log + signal)."""
        self._job.state = JobState.FAILED
        self._job.error = message
        applog.log.error(f"Job {self._job.id} failed: {message}")
        self._emit_log(f"\n\x1b[1;31m✗  Job failed: {message}\x1b[0m\n")  # bold red
        self._close_log()
        self.failed.emit(self._job.id, message)

    # --- output --------------------------------------------------------------

    def _on_output(self) -> None:
        data = bytes(self._proc.readAllStandardOutput())
        if data:
            # Emit raw (control sequences intact) so the terminal log view can
            # render in-place progress + colour. Incremental decode handles
            # multi-byte chars split across reads.
            text = self._decoder.decode(data)
            if text:
                self._emit_log(text)

    def _emit_log(self, text: str) -> None:
        self._job.append_log(text)
        if self._logfile is not None:
            self._logfile.feed(text)
        self.log.emit(self._job.id, text)

    def _close_log(self) -> None:
        if self._logfile is not None:
            self._logfile.close()
            self._logfile = None

    @staticmethod
    def _fmt(cmd: list[str]) -> str:
        return " ".join(f'"{c}"' if " " in c else c for c in cmd)
