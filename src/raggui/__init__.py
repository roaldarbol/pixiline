"""Thin PySide6 front-end for the Portia sleep pipeline.

It does not import torch / octron / R or do any processing itself: it builds and
runs ``pixi run ...`` commands (exactly like ``scripts/run.nu``) and edits
``config.yaml``. See the pipeline README, section "Notes for building the GUI".
"""

__version__ = "0.1.0"
