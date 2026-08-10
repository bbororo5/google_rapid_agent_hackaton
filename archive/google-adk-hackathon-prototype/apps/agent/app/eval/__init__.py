"""Quality evaluation harness (Part B).

Drives the orchestrator over a scenario dataset in real-LLM mode, scores each
analysis result with an LLM judge (3 axes), and writes the scores back to the
same Phoenix trace as EVALUATOR spans plus a JSON+Markdown report.

Run: `PYTHONPATH=. python -m app.eval.run_eval`  (see app/eval/run_eval.py).
"""
