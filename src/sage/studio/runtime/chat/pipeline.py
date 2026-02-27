from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import sage.flownet.api as fn

from sage.studio.runtime.chat.actors import (
    ChatFlowErrorHandler,
    ExtractMessage,
    GenerateAIResponse,
    OrchestratedResponseActor,
    SessionFilter,
    SessionKeyByTailShard,
    SessionStateProcessor,
)
from sage.studio.runtime.chat.contracts import ChatPipelineSettings


@dataclass(slots=True, frozen=True)
class ChatActorRefs:
    session_filter_ref: Any
    extract_message_ref: Any
    key_tail_ref: Any
    process_state_ref: Any
    generate_response_ref: Any
    error_handler_ref: Any


def create_chat_actor_refs() -> ChatActorRefs:
    return ChatActorRefs(
        session_filter_ref=fn.create_actor(SessionFilter).handle,
        extract_message_ref=fn.create_actor(ExtractMessage).handle,
        key_tail_ref=fn.create_actor(SessionKeyByTailShard).handle,
        process_state_ref=fn.create_actor(SessionStateProcessor).handle,
        generate_response_ref=fn.create_actor(OrchestratedResponseActor).handle,
        error_handler_ref=fn.create_actor(ChatFlowErrorHandler).handle,
    )


def build_chat_pipeline(
    *,
    actor_refs: ChatActorRefs,
    settings: ChatPipelineSettings,
    partition_plan: Any | None,
    partition_addresses: list[str] | None,
):
    if partition_plan is None and not partition_addresses:
        raise ValueError("chat pipeline requires partition_plan or partition_addresses.")

    @fn.flow
    def chat_pipeline(stream):
        with fn.exception_handler(actor_refs.error_handler_ref):
            normalized = stream.filter(actor_refs.session_filter_ref).map(actor_refs.extract_message_ref)
            normalized = _apply_pre_partition_extensions(normalized, settings=settings)

            if partition_plan is not None:
                partitioned = normalized.key_by(
                    key_fn=actor_refs.key_tail_ref,
                    num_partitions=settings.num_partitions,
                    plan=partition_plan,
                    stage_id=settings.stage_id,
                )
            else:
                partitioned = normalized.key_by(
                    key_fn=actor_refs.key_tail_ref,
                    num_partitions=settings.num_partitions,
                    addresses=list(partition_addresses or []),
                    stage_id=settings.stage_id,
                )

            processed = (
                partitioned
                .process_with_state(
                    actor_refs.process_state_ref,
                    state_spec={"key_field": "session_id"},
                    state_ttl_s=settings.state_ttl_s,
                )
            )
            processed = _apply_post_state_extensions(processed, settings=settings)
            events = processed.flatmap(actor_refs.generate_response_ref)
            events = _apply_post_generation_extensions(events, settings=settings)
            return events

    return chat_pipeline


def _apply_pre_partition_extensions(stream: Any, *, settings: ChatPipelineSettings):
    _ = settings.feature_profile_id
    _ = settings.canvas_flow_ref
    return stream


def _apply_post_state_extensions(stream: Any, *, settings: ChatPipelineSettings):
    _ = settings.feature_profile_id
    return stream


def _apply_post_generation_extensions(stream: Any, *, settings: ChatPipelineSettings):
    _ = settings.canvas_flow_ref
    return stream


__all__ = ["ChatActorRefs", "build_chat_pipeline", "create_chat_actor_refs"]
