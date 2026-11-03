"""Portable workflow schema, bounded expressions, and movement math."""
from __future__ import annotations

import ast
import copy
import json
import math
import operator
import random
import re
from pathlib import Path

MIN_DELAY_MS = 5.0
MAX_FILE_BYTES = 1_000_000
KINDS = ("start", "move", "click", "wait", "set", "if", "repeat", "script", "end")
DEFAULTS = {
    "start": {}, "end": {},
    "move": {"x": "240", "y": "180", "duration_ms": 350, "noise_px": 0},
    "click": {"button": "left", "interval_ms": 150, "jitter_ms": 12},
    "wait": {"ms": 500}, "set": {"name": "counter", "value": "counter + 1"},
    "if": {"condition": "counter < 5"}, "repeat": {"count": "5"},
    "script": {"code": "api.log('Hello, ArcMouse')\napi.wait(100)"},
}


class WorkflowError(ValueError):
    pass


def number(value, low=-1e9, high=1e9):
    if isinstance(value, bool):
        raise WorkflowError("숫자 필드에 true/false를 사용할 수 없습니다.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise WorkflowError(f"올바른 숫자가 아닙니다: {value!r}") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise WorkflowError(f"숫자 범위는 {low:g} ~ {high:g}입니다.")
    return result


def expression(source, variables):
    """No eval, attributes, calls, indexing, strings or unbounded exponentiation."""
    source = str(source)
    if len(source) > 300:
        raise WorkflowError("수식이 너무 깁니다.")
    binary = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
              ast.Div: operator.truediv, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv}
    compare = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
               ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}

    def visit(node, depth=0):
        if depth > 24:
            raise WorkflowError("수식 중첩 한도를 초과했습니다.")
        sub = lambda n: visit(n, depth + 1)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float, bool):
            return node.value if isinstance(node.value, bool) else number(node.value)
        if isinstance(node, ast.Name) and node.id in variables:
            return number(variables[node.id])
        if isinstance(node, ast.BinOp) and type(node.op) in binary:
            return number(binary[type(node.op)](sub(node.left), sub(node.right)))
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return not sub(node.operand)
            if isinstance(node.op, (ast.UAdd, ast.USub)):
                return number(sub(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1))
        if isinstance(node, ast.Compare):
            left = sub(node.left)
            for op, right_node in zip(node.ops, node.comparators):
                if type(op) not in compare:
                    break
                right = sub(right_node)
                if not compare[type(op)](left, right):
                    return False
                left = right
            else:
                return True
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            if isinstance(node.op, ast.And):
                return all(sub(v) for v in node.values)
            return any(sub(v) for v in node.values)
        raise WorkflowError(f"허용되지 않거나 정의되지 않은 수식: {source}")

    try:
        return visit(ast.parse(source, mode="eval").body)
    except (SyntaxError, ZeroDivisionError, OverflowError, RecursionError) as exc:
        raise WorkflowError(f"수식 오류: {source}") from exc


def ports(kind):
    return {"end": (), "if": ("true", "false"), "repeat": ("body", "done")}.get(kind, ("next",))


def validate(flow, complete=True):
    if not isinstance(flow, dict) or flow.get("version") != 1:
        raise WorkflowError("지원하지 않는 워크플로 버전입니다.")
    nodes = flow.get("nodes")
    if not isinstance(nodes, list) or not (2 if complete else 0) <= len(nodes) <= 500:
        raise WorkflowError("노드는 2~500개여야 합니다.")
    by_id = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise WorkflowError("노드 형식 오류")
        key, kind = node.get("id"), node.get("type")
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,80}",key) or key in by_id or kind not in KINDS:
            raise WorkflowError("중복 ID 또는 알 수 없는 노드입니다.")
        by_id[key] = node
        number(node.get("x", 0), 0, 10000)
        number(node.get("y", 0), 0, 10000)
        if not isinstance(node.get("params", {}), dict) or not isinstance(node.get("edges", {}), dict):
            raise WorkflowError(f"{key}: 속성/연결 형식 오류")
        p = node.get("params", {})
        for name in DEFAULTS[kind]:
            if name not in p:
                raise WorkflowError(f"{key}: {name} 필드가 필요합니다.")
        if kind == "move":
            number(p["duration_ms"], 5, 60_000)
            number(p["noise_px"], 0, 100)
        elif kind == "click":
            if p["button"] not in ("left", "right", "middle"):
                raise WorkflowError("지원하지 않는 버튼입니다.")
            number(p["interval_ms"], 0, 60_000)
            number(p["jitter_ms"], 0, 10_000)
        elif kind == "wait":
            number(p["ms"], 0, 3_600_000)
        elif kind == "set":
            if not isinstance(p["name"], str) or not p["name"].isidentifier() or p["name"].startswith("_"):
                raise WorkflowError("변수 이름은 문자로 시작하는 식별자여야 합니다.")
        elif kind == "script":
            if not isinstance(p["code"], str) or len(p["code"]) > 50_000:
                raise WorkflowError("스크립트 크기 한도를 초과했습니다.")
            try:
                compile(p["code"], f"<node:{key}>", "exec")
            except SyntaxError as exc:
                raise WorkflowError(str(exc)) from exc
        for name in ("x", "y", "value", "condition", "count"):
            if name in p:
                # Validate expression grammar without requiring variable values yet.
                try:
                    tree = ast.parse(str(p[name]), mode="eval")
                    names = {n.id: 1 for n in ast.walk(tree) if isinstance(n, ast.Name)}
                    expression(p[name], names)
                except WorkflowError as exc:
                    if not str(exc).startswith("수식 오류"):
                        raise
                except (SyntaxError, RecursionError) as exc:
                    raise WorkflowError(f"{key}: 잘못된 수식") from exc
    if not complete:
        for node in nodes:
            if any(port not in ports(node["type"]) or dest not in by_id
                   for port, dest in node.get("edges", {}).items()):
                raise WorkflowError("존재하지 않는 연결 대상 또는 포트")
        return by_id, None
    starts = [n for n in nodes if n["type"] == "start"]
    if len(starts) != 1 or not any(n["type"] == "end" for n in nodes):
        raise WorkflowError("시작 노드 1개와 종료 노드가 필요합니다.")
    for node in nodes:
        for port in ports(node["type"]):
            if node.get("edges", {}).get(port) not in by_id:
                raise WorkflowError(f"{node['id']}: {port} 연결이 필요합니다.")
        if set(node.get("edges", {})) - set(ports(node["type"])):
            raise WorkflowError(f"{node['id']}: 지원하지 않는 연결 포트")
    seen, todo = set(), [starts[0]["id"]]
    while todo:
        key = todo.pop()
        if key not in seen:
            seen.add(key)
            todo.extend(by_id[key].get("edges", {}).values())
    if not any(by_id[key]["type"] == "end" for key in seen):
        raise WorkflowError("시작 노드에서 종료 노드로 가는 경로가 없습니다.")
    return by_id, starts[0]["id"]


def load(path):
    if Path(path).stat().st_size > MAX_FILE_BYTES:
        raise WorkflowError("워크플로 파일은 1 MB 이하여야 합니다.")
    data = Path(path).read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise WorkflowError("워크플로 파일은 1 MB 이하여야 합니다.")
    flow = json.loads(data)
    validate(flow, complete=False)
    for i,node in enumerate(flow["nodes"]):
        node.setdefault("x", 60+(i%3)*260)
        node.setdefault("y", 60+(i//3)*120)
    return flow


def safe_interval(mean, deviation, rng=None):
    rng = rng or random
    mean, deviation = number(mean, 0, 60_000), number(deviation, 0, 10_000)
    # Truncated Gaussian avoids very long tails and always enforces the floor.
    offset = max(-3 * deviation, min(3 * deviation, rng.gauss(0, deviation)))
    return max(MIN_DELAY_MS, mean + offset)


def bezier(start, end, steps=40, bend=0.18):
    x0, y0 = start
    x3, y3 = end
    dx, dy = x3 - x0, y3 - y0
    x1, y1 = x0 + dx / 3 - dy * bend, y0 + dy / 3 + dx * bend
    x2, y2 = x0 + dx * 2 / 3 - dy * bend, y0 + dy * 2 / 3 + dx * bend
    for i in range(1, steps + 1):
        t = i / steps
        t = t * t * (3 - 2 * t)
        u = 1 - t
        yield (u**3*x0 + 3*u*u*t*x1 + 3*u*t*t*x2 + t**3*x3,
               u**3*y0 + 3*u*u*t*y1 + 3*u*t*t*y2 + t**3*y3)


def demo():
    specs = [
        ("start", "start", 30, 35, {}, {"next": "init"}),
        ("init", "set", 285, 35, {"name": "counter", "value": "0"}, {"next": "loop"}),
        ("loop", "repeat", 540, 35, {"count": "5"}, {"body": "move", "done": "end"}),
        ("move", "move", 795, 220, {}, {"next": "click"}),
        ("click", "click", 540, 220, {}, {"next": "increment"}),
        ("increment", "set", 285, 220, {}, {"next": "wait"}),
        ("wait", "wait", 30, 220, {}, {"next": "loop"}),
        ("end", "end", 795, 35, {}, {}),
    ]
    return {"version": 1, "name": "첫 번째 워크플로", "nodes": [
        {"id": key, "type": kind, "x": x, "y": y,
         "params": {**copy.deepcopy(DEFAULTS[kind]), **params}, "edges": edges}
        for key, kind, x, y, params, edges in specs]}
