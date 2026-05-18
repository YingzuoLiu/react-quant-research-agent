from typing import List

from .models import Pipeline


class PipelineValidator:
    def validate(self, pipeline: Pipeline) -> None:
        self._ensure_unique_ids(pipeline)
        self._ensure_all_edges_point_to_known_steps(pipeline)

    def validate_required_kinds(
        self,
        pipeline: Pipeline,
        required_kinds: List[str],
    ) -> None:
        present_kinds = {step.kind for step in pipeline.steps}
        missing_kinds = [
            kind for kind in required_kinds
            if kind not in present_kinds
        ]

        if missing_kinds:
            raise ValueError(
                "Pipeline is incomplete. Missing required step kinds: {0}".format(
                    ", ".join(missing_kinds)
                )
            )

    def _ensure_unique_ids(self, pipeline: Pipeline) -> None:
        step_ids = [step.id for step in pipeline.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Duplicate step ids")

    def _ensure_all_edges_point_to_known_steps(self, pipeline: Pipeline) -> None:
        known_ids = {step.id for step in pipeline.steps}
        for step in pipeline.steps:
            self._validate_targets(step.id, step.next or [], known_ids)

    def _validate_targets(self, source_id: str, targets, known_ids) -> None:
        for target in targets:
            if target not in known_ids:
                raise ValueError(
                    "Unknown target '{0}' referenced by '{1}'".format(
                        target,
                        source_id,
                    )
                )
