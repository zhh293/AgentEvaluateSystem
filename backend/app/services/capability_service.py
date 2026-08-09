from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import yaml

from app.core.exceptions import ValidationException


PARSER_VERSION = "1.0.0"
_HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head")


@dataclass(frozen=True)
class ParsedCapability:
    key: str
    kind: str
    name: str
    description: str
    operation: dict[str, Any]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    constraints: list[Any]
    source_pointer: str


@dataclass(frozen=True)
class ParsedCatalog:
    spec_type: str
    spec_digest: str
    capabilities: tuple[ParsedCapability, ...]
    warnings: tuple[str, ...] = ()


def parse_interface_spec(content: bytes, filename: str) -> ParsedCatalog:
    if not content or len(content) > 2 * 1024 * 1024:
        raise ValidationException("功能说明书为空或超过 2MB 限制")
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValidationException("功能说明书必须使用 UTF-8 编码") from exc
    try:
        payload = json.loads(text) if filename.lower().endswith(".json") else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValidationException(f"功能说明书无法解析: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValidationException("功能说明书根节点必须是对象")
    digest = hashlib.sha256(content).hexdigest()
    if "openapi" in payload:
        return _parse_openapi(payload, digest)
    if payload.get("type") == "cli":
        return _parse_cli(payload, digest)
    raise ValidationException("仅支持 OpenAPI 3.x 或平台结构化 CLI 说明书")


def _parse_openapi(payload: dict[str, Any], digest: str) -> ParsedCatalog:
    version = str(payload.get("openapi", ""))
    if not version.startswith("3."):
        raise ValidationException("仅支持 OpenAPI 3.x")
    paths = payload.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise ValidationException("OpenAPI paths 不能为空")
    capabilities: list[ParsedCapability] = []
    operation_ids: set[str] = set()
    for path, path_item in sorted(paths.items()):
        if not isinstance(path, str) or not path.startswith("/") or not isinstance(path_item, dict):
            raise ValidationException(f"OpenAPI path 定义不合法: {path}")
        for method in _HTTP_METHODS:
            operation = path_item.get(method)
            if operation is None:
                continue
            if not isinstance(operation, dict):
                raise ValidationException(f"OpenAPI operation 必须是对象: {method.upper()} {path}")
            operation_id = str(operation.get("operationId") or f"{method.upper()} {path}")
            if operation_id in operation_ids:
                raise ValidationException(f"OpenAPI operationId 重复: {operation_id}")
            operation_ids.add(operation_id)
            request_body = _resolve_local_refs(operation.get("requestBody") or {}, payload)
            responses = _resolve_local_refs(operation.get("responses") or {}, payload)
            parameters = _resolve_local_refs(operation.get("parameters", path_item.get("parameters", [])), payload)
            capabilities.append(ParsedCapability(
                key=f"HTTP:{method.upper()}:{path}", kind="http",
                name=str(operation.get("summary") or operation_id),
                description=str(operation.get("description") or ""),
                operation={"method": method.upper(), "path": path, "operation_id": operation_id},
                input_schema={"parameters": parameters, "request_body": request_body},
                output_schema={"responses": responses},
                constraints=list(operation.get("security") or []),
                source_pointer=f"#/paths/{_pointer(path)}/{method}",
            ))
    if not capabilities:
        raise ValidationException("OpenAPI 没有任何可测试 operation")
    return ParsedCatalog("openapi", digest, tuple(capabilities))


def _parse_cli(payload: dict[str, Any], digest: str) -> ParsedCatalog:
    if int(payload.get("schema_version", 0)) != 1:
        raise ValidationException("CLI 说明书必须声明 schema_version: 1")
    executable = payload.get("executable")
    commands = payload.get("commands")
    if not isinstance(executable, list) or not executable or not all(isinstance(x, str) and x for x in executable):
        raise ValidationException("CLI executable 必须是非空 argv 数组")
    if not isinstance(commands, list) or not commands:
        raise ValidationException("CLI commands 不能为空")
    capabilities: list[ParsedCapability] = []
    ids: set[str] = set()
    for index, command in enumerate(commands):
        if not isinstance(command, dict):
            raise ValidationException(f"CLI commands[{index}] 必须是对象")
        command_id = command.get("id")
        args = command.get("args")
        if not isinstance(command_id, str) or not command_id or command_id in ids:
            raise ValidationException(f"CLI command id 为空或重复: {command_id}")
        if not isinstance(args, list) or not all(isinstance(x, str) and x for x in args):
            raise ValidationException(f"CLI command args 必须是 argv 数组: {command_id}")
        ids.add(command_id)
        capabilities.append(ParsedCapability(
            key=f"CLI:{command_id}", kind="cli", name=str(command.get("name") or command_id),
            description=str(command.get("description") or ""),
            operation={"executable": executable, "args": args, "command_id": command_id},
            input_schema={"input": command.get("input", {}), "options": command.get("options", [])},
            output_schema=command.get("output", {}) if isinstance(command.get("output", {}), dict) else {},
            constraints=list(command.get("constraints") or []), source_pointer=f"#/commands/{index}",
        ))
    return ParsedCatalog("cli", digest, tuple(capabilities))


def _pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _resolve_local_refs(value: Any, document: dict[str, Any], stack: tuple[str, ...] = ()) -> Any:
    """Resolve local JSON Pointer references and reject network/file references."""
    if isinstance(value, list):
        return [_resolve_local_refs(item, document, stack) for item in value]
    if not isinstance(value, dict):
        return value
    reference = value.get("$ref")
    if reference is not None:
        if not isinstance(reference, str) or not reference.startswith("#/"):
            raise ValidationException(f"OpenAPI 仅允许文档内 $ref: {reference}")
        if reference in stack:
            return {"$ref": reference}
        target: Any = document
        for encoded in reference[2:].split("/"):
            token = encoded.replace("~1", "/").replace("~0", "~")
            if not isinstance(target, dict) or token not in target:
                raise ValidationException(f"OpenAPI $ref 不存在: {reference}")
            target = target[token]
        resolved = _resolve_local_refs(target, document, stack + (reference,))
        siblings = {key: item for key, item in value.items() if key != "$ref"}
        if siblings and isinstance(resolved, dict):
            return {**resolved, **_resolve_local_refs(siblings, document, stack)}
        return resolved
    return {key: _resolve_local_refs(item, document, stack) for key, item in value.items()}
