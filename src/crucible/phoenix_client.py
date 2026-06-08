"""Thin plumbing over the Arize Phoenix SDK.

Three deterministic seams the Crucible loop depends on:
  1. init_tracing()   -> register OpenTelemetry tracing to Phoenix Cloud.
  2. log_experiment() -> record one scored candidate run as a Phoenix experiment.
  3. promote_prompt()  -> persist the winning prompt to the Phoenix prompt registry.

This is SDK plumbing, not agent-driven logic: given an already-scored EvalResult we
replay the stored predictions into Phoenix rather than re-running the agent.

--------------------------------------------------------------------------------
API CONFIRMED against (lookup 2026-06-08):
  - arize-phoenix-otel 0.13.0 PyPI README + github.com/Arize-ai/gemini-hackathon:
        phoenix.otel.register(project_name=..., endpoint=<fqdn>/v1/traces,
                              auto_instrument=True) -> TracerProvider.
        Docs: when passing `endpoint` directly you MUST give the fully-qualified
        traces path (".../v1/traces"), which is exactly collector_endpoint + /v1/traces.
  - arize-phoenix-client 2.7.0 PyPI README + Phoenix docs:
        Client(base_url=..., api_key=...)
        client.datasets.create_dataset(name, inputs=[...], outputs=[...],
                                       metadata=[...], dataset_description=...)
        client.experiments.run_experiment(dataset, task, evaluators,
                                          experiment_name=...) -> obj with .runs
        client.prompts.create(name, version=PromptVersion(messages=[...],
                              model_name=...), prompt_description=...)
        phoenix.client.types.PromptVersion(messages=[{role, content}], model_name=...)

API POINTS STILL UNCONFIRMED (verify at the spike with real creds):
  - The exact attribute on the run_experiment() return object that yields a stable
    leaderboard identifier. Docs show `.runs` (a list); an `experiment_name`/`id`
    attribute is likely but unverified. We therefore RETURN the experiment_name we
    pass in (deterministic and sufficient for the leaderboard) and best-effort read
    `.id` / `.name` if present.
  - Whether create_dataset auto-creates vs. errors on a duplicate name across re-runs.
    We make the dataset name unique per (db_id, version) to sidestep collisions.
  - PromptVersion field name for the messages arg: positional in some docs samples,
    `messages=` keyword in others. We pass it positionally to match both.
  - model_name for PromptVersion is required by the SDK; we read GEMINI_MODEL
    (default "gemini-3-pro") since Crucible targets Gemini.
"""
from __future__ import annotations

import os
from typing import Any

from crucible.types import EvalResult, ItemResult

# Default project name when PHOENIX_PROJECT_NAME is unset.
_DEFAULT_PROJECT = "crucible"
# Phoenix Cloud OTLP/HTTP traces path appended to the collector endpoint.
_TRACES_PATH = "/v1/traces"
# Gemini is Crucible's target model; PromptVersion requires a model name.
_DEFAULT_MODEL = "gemini-3-pro"


def init_tracing() -> Any:
    """Register OpenTelemetry tracing to Phoenix Cloud.

    Reads PHOENIX_PROJECT_NAME (default "crucible") and PHOENIX_COLLECTOR_ENDPOINT.
    The traces endpoint is the collector endpoint + "/v1/traces". auto_instrument=True
    turns on every installed OpenInference instrumentor (e.g. google-adk).

    Returns whatever phoenix.otel.register returns (a TracerProvider).
    """
    from phoenix.otel import register

    project_name = os.environ.get("PHOENIX_PROJECT_NAME", _DEFAULT_PROJECT)
    collector_endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT")

    register_kwargs: dict[str, Any] = {
        "project_name": project_name,
        "auto_instrument": True,
    }
    # Only pin the endpoint when configured; otherwise let register() fall back to
    # PHOENIX_COLLECTOR_ENDPOINT / localhost defaults.
    if collector_endpoint:
        register_kwargs["endpoint"] = collector_endpoint.rstrip("/") + _TRACES_PATH

    return register(**register_kwargs)


def _row_from_item_result(result: ItemResult) -> dict[str, Any]:
    """Serialize one ItemResult into a flat experiment row.

    Matches the frozen contract: question, gold_sql, predicted_sql, is_match, error,
    difficulty.
    """
    return {
        "question": result.item.question,
        "gold_sql": result.item.gold_sql,
        "predicted_sql": result.predicted_sql,
        "is_match": result.is_match,
        "error": result.error,
        "difficulty": result.item.difficulty,
    }


def _build_client() -> Any:
    """Construct a Phoenix REST client from environment variables."""
    from phoenix.client import Client

    return Client(
        base_url=os.environ.get("PHOENIX_COLLECTOR_ENDPOINT"),
        api_key=os.environ.get("PHOENIX_API_KEY"),
    )


def log_experiment(result: EvalResult, db_id: str) -> str:
    """Record one candidate version's scored run as a Phoenix experiment.

    Builds a Phoenix dataset from the serialized ItemResult rows, replays each stored
    prediction as the task output, and scores it with an evaluator that surfaces the
    already-computed execution match. Returns the experiment name used on the
    leaderboard.

    This is deterministic plumbing: the predictions are precomputed, so the task simply
    echoes the stored prediction rather than re-invoking the agent.
    """
    rows = [_row_from_item_result(item) for item in result.item_results]

    name = f"crucible-{db_id}-v{result.spec_version}-{result.split}"
    client = _build_client()

    # inputs/outputs/metadata are parallel lists; one entry per dataset Example.
    # Inputs carry the question (the agent's input); outputs/metadata carry the
    # gold answer and the serialized run fields used by the evaluator.
    dataset = client.datasets.create_dataset(
        name=name,
        inputs=[{"question": row["question"]} for row in rows],
        outputs=[{"gold_sql": row["gold_sql"]} for row in rows],
        metadata=rows,
        dataset_description=f"Crucible run db={db_id} v{result.spec_version} ({result.split})",
    )

    def task(metadata: dict[str, Any]) -> dict[str, Any]:
        """Replay the stored prediction for this example (no live agent call)."""
        return {
            "predicted_sql": metadata.get("predicted_sql"),
            "is_match": metadata.get("is_match"),
            "error": metadata.get("error"),
        }

    def execution_match(output: dict[str, Any]) -> float:
        """Per-example execution-match score taken from the stored result."""
        return 1.0 if output.get("is_match") else 0.0

    experiment = client.experiments.run_experiment(
        dataset=dataset,
        task=task,
        evaluators=[execution_match],
        experiment_name=name,
        experiment_metadata={
            "db_id": db_id,
            "spec_version": result.spec_version,
            "split": result.split,
            "execution_match": result.score,  # aggregate run-level metric
        },
    )

    # Prefer a server-assigned identifier when the SDK exposes one; otherwise fall
    # back to the deterministic name we created (sufficient for the leaderboard).
    return (
        getattr(experiment, "name", None)
        or getattr(experiment, "id", None)
        or name
    )


def promote_prompt(name: str, system_prompt: str, few_shots) -> None:
    """Persist the winning prompt to the Phoenix prompt registry.

    The system prompt plus any few-shot (question, sql) pairs are stored as a single
    versioned chat prompt. Re-promoting under the same name creates a new version.

    few_shots is an iterable of (question, sql) pairs (tuple[tuple[str, str], ...]).
    """
    from phoenix.client.types import PromptVersion

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for question, sql in few_shots:
        messages.append({"role": "user", "content": question})
        messages.append({"role": "assistant", "content": sql})

    client = _build_client()
    model_name = os.environ.get("GEMINI_MODEL", _DEFAULT_MODEL)

    client.prompts.create(
        name=name,
        version=PromptVersion(messages, model_name=model_name),
        prompt_description="Crucible winning text-to-SQL prompt",
    )
