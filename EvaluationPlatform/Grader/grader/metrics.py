"""Incident measurement API (methodology v2).

Legacy completion-centered percentage-change scoring was removed. Operational
recovery and diagnostic series summaries are implemented in research.py.
"""
from .research import evaluate_incident, diagnostics

__all__ = ['evaluate_incident', 'diagnostics']
