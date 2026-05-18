from typing import Any, Awaitable, Callable, Dict, List, Optional

from ..engine.core.builder import PipelineBuilder
from .catalog import get_catalog as catalog_list
from .catalog import get_details as catalog_details

ToolHandler = Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]

_active_builder: Optional[PipelineBuilder] = None


def bind_builder(builder: PipelineBuilder) -> None:
    global _active_builder
    _active_builder = builder


def get_tool_specs() -> List[Dict[str, Any]]:
    config_schema = {
        "type": "object",
        "description": (
            "Step configuration dict. Keys and value types depend on the step kind. "
            "Call get_details with the step kind to see required fields, an example config, "
            "and the output shape before filling this in. "
            "Upstream step outputs are referenced as strings using the syntax "
            "$step_id or $step_id['field'], where step_id is the id you gave that step."
        ),
    }
    return [
        _function_spec(
            name="get_catalog",
            description=(
                "List all available step kinds with their purpose, required fields, "
                "and example config. Call this first to understand what steps exist."
            ),
            properties={},
            required=[],
        ),
        _function_spec(
            name="get_details",
            description=(
                "Return full detail for one step kind: required fields, example config, "
                "output shape, and usage notes. Always call this before add_step "
                "if you are unsure what config a step expects."
            ),
            properties={"kind": {"type": "string", "description": "The step kind to inspect, e.g. 'data.market_bars'"}},
            required=["kind"],
        ),
        _function_spec(
            name="add_step",
            description=(
                "Add a new step to the draft and immediately execute it. "
                "Returns the step's output on success, or an error message on failure. "
                "If the step fails, fix the config and call update_step to retry. "
                "Call get_details first if the config shape is unclear."
            ),
            properties={
                "kind": {
                    "type": "string",
                    "description": "Step kind, e.g. 'trigger.manual', 'data.market_bars'.",
                },
                "step_id": {
                    "type": "string",
                    "description": (
                        "Unique identifier for this step. Choose a short descriptive name "
                        "such as 'trigger', 'bars', 'momentum', 'rank', 'chat'. "
                        "This id is used to reference the step's output downstream "
                        "with $step_id or $step_id['field']."
                    ),
                },
                "config": config_schema,
            },
            required=["kind", "step_id", "config"],
        ),
        _function_spec(
            name="update_step",
            description=(
                "Replace the config of an existing step and immediately re-execute it. "
                "Use this to fix a step that returned an error, or to adjust its parameters. "
                "Returns the step's new output on success, or an error on failure."
            ),
            properties={
                "step_id": {
                    "type": "string",
                    "description": "The id of the step to update.",
                },
                "config": config_schema,
            },
            required=["step_id", "config"],
        ),
        _function_spec(
            name="connect_steps",
            description=(
                "Declare that source_id must run before target_id. "
                "Call this after all steps have been added and verified. "
                "A step can only be connected if both its source and target already exist."
            ),
            properties={
                "source_id": {
                    "type": "string",
                    "description": "The step that runs first.",
                },
                "target_id": {
                    "type": "string",
                    "description": "The step that depends on source_id.",
                },
            },
            required=["source_id", "target_id"],
        ),
        _function_spec(
            name="get_pipeline",
            description=(
                "Export the completed draft. Only call this after all steps have been "
                "added, verified (each returned success), and connected in order. "
                "Returns success=true when the pipeline is non-empty and ready to run."
            ),
            properties={},
            required=[],
        ),
    ]


async def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    if _active_builder is None:
        return {"success": False, "error": "Builder not bound", "stage": "tooling"}

    handlers = _tool_handlers(_active_builder)
    if name not in handlers:
        return {"success": False, "error": "Unknown tool: {0}".format(name)}

    try:
        return await handlers[name](arguments)
    except Exception as exc:
        return {"success": False, "error": str(exc), "stage": "tooling"}


def _function_spec(
    name: str,
    description: str,
    properties: Dict[str, Any],
    required: List[str],
) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def _tool_handlers(builder: PipelineBuilder) -> Dict[str, ToolHandler]:
    return {
        "add_step": lambda payload: _add_step(builder, payload),
        "update_step": lambda payload: _update_step(builder, payload),
        "connect_steps": lambda payload: _connect_steps(builder, payload),
        "get_catalog": lambda payload: _get_catalog(payload),
        "get_details": lambda payload: _get_details(payload),
        "get_pipeline": lambda payload: _get_pipeline(builder, payload),
    }


async def _add_step(builder: PipelineBuilder, payload: Dict[str, Any]) -> Dict[str, Any]:
    created_id = builder.add_step(
        kind=payload["kind"],
        config=payload.get("config", {}),
        step_id=payload.get("step_id"),
    )
    result = await _run_step(builder, created_id)
    result["action"] = "add_step"
    return result


async def _update_step(builder: PipelineBuilder, payload: Dict[str, Any]) -> Dict[str, Any]:
    step_id = payload["step_id"]
    builder.update_step(step_id, payload.get("config", {}))
    result = await _run_step(builder, step_id)
    result["action"] = "update_step"
    return result


async def _connect_steps(builder: PipelineBuilder, payload: Dict[str, Any]) -> Dict[str, Any]:
    builder.connect_steps(payload["source_id"], payload["target_id"])
    return {
        "success": True,
        "action": "connect_steps",
        "source_id": payload["source_id"],
        "target_id": payload["target_id"],
    }


async def _get_catalog(_: Dict[str, Any]) -> Dict[str, Any]:
    return {"success": True, "action": "get_catalog", "catalog": catalog_list()}


async def _get_details(payload: Dict[str, Any]) -> Dict[str, Any]:
    details = catalog_details(payload["kind"])
    if "error" in details:
        return {"success": False, "action": "get_details", "error": details["error"]}
    return {"success": True, "action": "get_details", "details": details}


async def _get_pipeline(builder: PipelineBuilder, _: Dict[str, Any]) -> Dict[str, Any]:
    pipeline = builder.get_pipeline()
    if not pipeline["steps"]:
        return {
            "success": False,
            "action": "get_pipeline",
            "error": "Pipeline is empty. Add and verify all steps before exporting.",
            "pipeline": pipeline,
        }
    return {"success": True, "action": "get_pipeline", "pipeline": pipeline}


async def _run_step(builder: PipelineBuilder, step_id: str) -> Dict[str, Any]:
    try:
        output = await builder.execute_step(step_id)
    except Exception as exc:
        return {"success": False, "step_id": step_id, "error": str(exc), "stage": "execution"}
    return {"success": True, "step_id": step_id, "output": output, "stage": "execution"}
