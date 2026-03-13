from __future__ import annotations

from typing import Any

from .llm_client import LLMClient
from .models import AnalysisResult, ExecutionPlan, InputDocument, SkillConfig
from .prompts import (
    build_adaptation_evaluation_messages,
    build_audience_analysis_messages,
    build_chunk_summary_messages,
    build_episode_recommendation_messages,
    build_final_report_messages,
    build_structural_summary_messages,
    build_summary_merge_messages,
)
from .router import chunk_document_text


class NovelEvaluationAnalyzer:
    """Run the staged novel evaluation workflow."""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm_client = llm_client

    def run(
        self,
        *,
        plan: ExecutionPlan,
        skill_config: SkillConfig,
        document: InputDocument,
        reference_texts: dict[str, str],
    ) -> AnalysisResult:
        stage_outputs: dict[str, Any] = {}
        working_summary = self._run_structural_stage(plan, skill_config, document)
        stage_outputs["structural_summary"] = working_summary

        adaptation_refs = _select_reference_subset(reference_texts, "adaptation")
        stage_outputs["adaptation_evaluation"] = self.llm_client.generate_json(
            "adaptation_evaluation",
            build_adaptation_evaluation_messages(
                skill_config,
                working_summary,
                adaptation_refs,
            ),
        )

        episode_refs = _select_reference_subset(reference_texts, "episode")
        stage_outputs["episode_recommendation"] = self.llm_client.generate_json(
            "episode_recommendation",
            build_episode_recommendation_messages(
                skill_config,
                working_summary,
                document,
                episode_refs,
            ),
        )

        stage_outputs["audience_analysis"] = self.llm_client.generate_json(
            "audience_analysis",
            build_audience_analysis_messages(skill_config, working_summary),
        )

        final_payload = self.llm_client.generate_json(
            "final_report_generation",
            build_final_report_messages(skill_config, document, stage_outputs),
        )
        stage_outputs["final_report_generation"] = final_payload

        return AnalysisResult(
            stage_outputs=stage_outputs,
            final_sections=final_payload.get("sections", {}),
            metadata={
                "chunked": plan.needs_chunking,
                "provider": self.llm_client.settings.provider,
                "model": self.llm_client.settings.model,
            },
        )

    def _run_structural_stage(
        self,
        plan: ExecutionPlan,
        skill_config: SkillConfig,
        document: InputDocument,
    ) -> dict[str, Any]:
        if not plan.needs_chunking:
            return self.llm_client.generate_json(
                "structural_summary",
                build_structural_summary_messages(skill_config, document),
            )

        chunks = chunk_document_text(
            document.text,
            chunk_size=plan.chunk_size,
            overlap=plan.chunk_overlap,
            stem=document.path.stem,
        )
        document.chunks = chunks
        chunk_summaries: list[dict[str, Any]] = []
        total_chunks = len(chunks)
        for chunk in chunks:
            chunk_summaries.append(
                self.llm_client.generate_json(
                    f"structural_summary:{chunk.chunk_id}",
                    build_chunk_summary_messages(skill_config, chunk, total_chunks),
                )
            )

        merged = self.llm_client.generate_json(
            "structural_summary_merge",
            build_summary_merge_messages(skill_config, chunk_summaries),
        )
        merged["chunk_summaries"] = chunk_summaries
        return merged


def _select_reference_subset(reference_texts: dict[str, str], keyword: str) -> dict[str, str]:
    matched = {
        path: text
        for path, text in reference_texts.items()
        if keyword.lower() in path.lower()
    }
    return matched or reference_texts
