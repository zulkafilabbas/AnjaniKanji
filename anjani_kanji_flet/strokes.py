from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from xml.etree import ElementTree as ET

import flet as ft
import flet.canvas as cv

from .storage import AppStorage

KANJIVG_BASE = "https://cdn.jsdelivr.net/gh/KanjiVG/kanjivg@master/kanji"
PATH_TOKEN_RE = re.compile(r"[MmZzLlHhVvCcSsQqTtAa]|[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?")
Point = tuple[float, float]


@dataclass(frozen=True)
class SampledStroke:
    subpaths: tuple[tuple[Point, ...], ...]
    length: float


@dataclass(frozen=True)
class StrokeFrameSet:
    view_box: tuple[float, float, float, float]
    strokes: tuple[SampledStroke, ...]


def kanji_vg_url(character: str) -> str:
    return f"{KANJIVG_BASE}/{ord(character):05x}.svg"


def load_stroke_svg(storage: AppStorage, character: str) -> str | None:
    cached = storage.get_stroke_cache(character)
    if cached:
        return cached
    try:
        with urlopen(kanji_vg_url(character)) as response:
            svg = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError):
        return None
    storage.put_stroke_cache(character, svg)
    return svg


@lru_cache(maxsize=256)
def build_stroke_frames(svg_text: str) -> StrokeFrameSet | None:
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError:
        return None
    _strip_text_nodes(root)
    view_box = _parse_view_box(root)
    strokes: list[SampledStroke] = []
    for element in root.iter():
        if not element.tag.endswith("path"):
            continue
        data = element.attrib.get("d")
        if not data:
            continue
        stroke = _sample_svg_path(data)
        if stroke and stroke.length > 0:
            strokes.append(stroke)
    if not strokes:
        return None
    return StrokeFrameSet(view_box=view_box, strokes=tuple(strokes))


def canvas_shapes(frame_set: StrokeFrameSet, stroke_progress: float, canvas_size: float = 360.0, padding: float = 18.0) -> list[cv.Path]:
    min_x, min_y, width, height = frame_set.view_box
    drawable = max(1.0, canvas_size - padding * 2)
    scale = min(drawable / max(width, 1.0), drawable / max(height, 1.0))
    offset_x = padding + (drawable - width * scale) / 2 - min_x * scale
    offset_y = padding + (drawable - height * scale) / 2 - min_y * scale

    def tx(x: float) -> float:
        return x * scale + offset_x

    def ty(y: float) -> float:
        return y * scale + offset_y

    completed = min(len(frame_set.strokes), max(0, int(stroke_progress)))
    fraction = max(0.0, min(1.0, stroke_progress - completed))

    shapes: list[cv.Path] = []
    for stroke in frame_set.strokes[:completed]:
        path = _path_from_subpaths(stroke.subpaths, tx, ty, scale)
        if path:
            shapes.append(path)

    if completed < len(frame_set.strokes) and fraction > 0:
        partial = _trim_subpaths(frame_set.strokes[completed], frame_set.strokes[completed].length * fraction)
        path = _path_from_subpaths(partial, tx, ty, scale)
        if path:
            shapes.append(path)

    return shapes


def _path_from_subpaths(
    subpaths: tuple[tuple[Point, ...], ...],
    tx,
    ty,
    scale: float,
) -> cv.Path | None:
    elements: list[cv.Path.PathElement] = []
    for subpath in subpaths:
        if len(subpath) < 2:
            continue
        elements.append(cv.Path.MoveTo(tx(subpath[0][0]), ty(subpath[0][1])))
        for point in subpath[1:]:
            elements.append(cv.Path.LineTo(tx(point[0]), ty(point[1])))
    if not elements:
        return None
    return cv.Path(
        elements=elements,
        paint=ft.Paint(
            color="#8ef7aa",
            style=ft.PaintingStyle.STROKE,
            stroke_width=max(2.0, 3.0 * scale / 3.0),
            stroke_cap=ft.StrokeCap.ROUND,
            stroke_join=ft.StrokeJoin.ROUND,
            anti_alias=True,
        ),
    )


def _trim_subpaths(stroke: SampledStroke, target_length: float) -> tuple[tuple[Point, ...], ...]:
    remaining = max(0.0, min(stroke.length, target_length))
    result: list[tuple[Point, ...]] = []

    for subpath in stroke.subpaths:
        if len(subpath) < 2:
            continue
        if remaining <= 0:
            break
        partial: list[Point] = [subpath[0]]
        for start, end in zip(subpath, subpath[1:]):
            segment = _distance(start, end)
            if segment <= 0:
                continue
            if remaining >= segment:
                partial.append(end)
                remaining -= segment
                continue
            ratio = remaining / segment
            partial.append((start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio))
            remaining = 0
            break
        if len(partial) >= 2:
            result.append(tuple(partial))

    return tuple(result)


def _sample_svg_path(data: str) -> SampledStroke | None:
    tokens = PATH_TOKEN_RE.findall(data)
    if not tokens:
        return None

    subpaths: list[tuple[Point, ...]] = []
    current: list[Point] = []
    index = 0
    command = ""
    x = 0.0
    y = 0.0
    start_x = 0.0
    start_y = 0.0
    last_cubic_cp: Point | None = None
    last_quad_cp: Point | None = None

    def is_command(token: str) -> bool:
        return len(token) == 1 and token.isalpha()

    def take_number() -> float:
        nonlocal index
        value = float(tokens[index])
        index += 1
        return value

    def begin_subpath(px: float, py: float) -> None:
        nonlocal current, start_x, start_y
        if len(current) >= 2:
            subpaths.append(tuple(current))
        current = [(px, py)]
        start_x, start_y = px, py

    def add_point(px: float, py: float) -> None:
        if not current:
            begin_subpath(px, py)
            return
        if current[-1] != (px, py):
            current.append((px, py))

    while index < len(tokens):
        if is_command(tokens[index]):
            command = tokens[index]
            index += 1
        if not command:
            break

        if command in "Mm":
            first = True
            while index + 1 < len(tokens) and not is_command(tokens[index]):
                nx = take_number()
                ny = take_number()
                if command == "m":
                    nx += x
                    ny += y
                x, y = nx, ny
                if first:
                    begin_subpath(x, y)
                    first = False
                else:
                    add_point(x, y)
                last_cubic_cp = None
                last_quad_cp = None
            continue

        if command in "Ll":
            while index + 1 < len(tokens) and not is_command(tokens[index]):
                nx = take_number()
                ny = take_number()
                if command == "l":
                    nx += x
                    ny += y
                x, y = nx, ny
                add_point(x, y)
                last_cubic_cp = None
                last_quad_cp = None
            continue

        if command in "Hh":
            while index < len(tokens) and not is_command(tokens[index]):
                nx = take_number()
                x = x + nx if command == "h" else nx
                add_point(x, y)
                last_cubic_cp = None
                last_quad_cp = None
            continue

        if command in "Vv":
            while index < len(tokens) and not is_command(tokens[index]):
                ny = take_number()
                y = y + ny if command == "v" else ny
                add_point(x, y)
                last_cubic_cp = None
                last_quad_cp = None
            continue

        if command in "Cc":
            while index + 5 < len(tokens) and not is_command(tokens[index]):
                cp1x = take_number()
                cp1y = take_number()
                cp2x = take_number()
                cp2y = take_number()
                nx = take_number()
                ny = take_number()
                if command == "c":
                    cp1x += x
                    cp1y += y
                    cp2x += x
                    cp2y += y
                    nx += x
                    ny += y
                for point in _sample_cubic((x, y), (cp1x, cp1y), (cp2x, cp2y), (nx, ny)):
                    add_point(*point)
                x, y = nx, ny
                last_cubic_cp = (cp2x, cp2y)
                last_quad_cp = None
            continue

        if command in "Ss":
            while index + 3 < len(tokens) and not is_command(tokens[index]):
                if last_cubic_cp is None:
                    cp1x, cp1y = x, y
                else:
                    cp1x = x + (x - last_cubic_cp[0])
                    cp1y = y + (y - last_cubic_cp[1])
                cp2x = take_number()
                cp2y = take_number()
                nx = take_number()
                ny = take_number()
                if command == "s":
                    cp2x += x
                    cp2y += y
                    nx += x
                    ny += y
                for point in _sample_cubic((x, y), (cp1x, cp1y), (cp2x, cp2y), (nx, ny)):
                    add_point(*point)
                x, y = nx, ny
                last_cubic_cp = (cp2x, cp2y)
                last_quad_cp = None
            continue

        if command in "Qq":
            while index + 3 < len(tokens) and not is_command(tokens[index]):
                cp1x = take_number()
                cp1y = take_number()
                nx = take_number()
                ny = take_number()
                if command == "q":
                    cp1x += x
                    cp1y += y
                    nx += x
                    ny += y
                for point in _sample_quadratic((x, y), (cp1x, cp1y), (nx, ny)):
                    add_point(*point)
                x, y = nx, ny
                last_quad_cp = (cp1x, cp1y)
                last_cubic_cp = None
            continue

        if command in "Tt":
            while index + 1 < len(tokens) and not is_command(tokens[index]):
                if last_quad_cp is None:
                    cp1x, cp1y = x, y
                else:
                    cp1x = x + (x - last_quad_cp[0])
                    cp1y = y + (y - last_quad_cp[1])
                nx = take_number()
                ny = take_number()
                if command == "t":
                    nx += x
                    ny += y
                for point in _sample_quadratic((x, y), (cp1x, cp1y), (nx, ny)):
                    add_point(*point)
                x, y = nx, ny
                last_quad_cp = (cp1x, cp1y)
                last_cubic_cp = None
            continue

        if command in "Aa":
            while index + 6 < len(tokens) and not is_command(tokens[index]):
                _rx = take_number()
                _ry = take_number()
                _rotation = take_number()
                _large_arc = take_number()
                _sweep = take_number()
                nx = take_number()
                ny = take_number()
                if command == "a":
                    nx += x
                    ny += y
                add_point(nx, ny)
                x, y = nx, ny
                last_cubic_cp = None
                last_quad_cp = None
            continue

        if command in "Zz":
            if current and current[-1] != (start_x, start_y):
                current.append((start_x, start_y))
            x, y = start_x, start_y
            last_cubic_cp = None
            last_quad_cp = None
            continue

        break

    if len(current) >= 2:
        subpaths.append(tuple(current))

    if not subpaths:
        return None

    length = sum(_polyline_length(subpath) for subpath in subpaths)
    return SampledStroke(subpaths=tuple(subpaths), length=length)


def _sample_cubic(start: Point, cp1: Point, cp2: Point, end: Point, steps: int = 24) -> list[Point]:
    points: list[Point] = []
    for step in range(1, steps + 1):
        t = step / steps
        mt = 1.0 - t
        x = (
            mt * mt * mt * start[0]
            + 3 * mt * mt * t * cp1[0]
            + 3 * mt * t * t * cp2[0]
            + t * t * t * end[0]
        )
        y = (
            mt * mt * mt * start[1]
            + 3 * mt * mt * t * cp1[1]
            + 3 * mt * t * t * cp2[1]
            + t * t * t * end[1]
        )
        points.append((x, y))
    return points


def _sample_quadratic(start: Point, cp: Point, end: Point, steps: int = 20) -> list[Point]:
    points: list[Point] = []
    for step in range(1, steps + 1):
        t = step / steps
        mt = 1.0 - t
        x = mt * mt * start[0] + 2 * mt * t * cp[0] + t * t * end[0]
        y = mt * mt * start[1] + 2 * mt * t * cp[1] + t * t * end[1]
        points.append((x, y))
    return points


def _polyline_length(points: tuple[Point, ...]) -> float:
    return sum(_distance(start, end) for start, end in zip(points, points[1:]))


def _distance(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _parse_view_box(root: ET.Element) -> tuple[float, float, float, float]:
    raw = root.attrib.get("viewBox")
    if raw:
        parts = [float(part) for part in raw.replace(",", " ").split()]
        if len(parts) == 4:
            return parts[0], parts[1], parts[2], parts[3]
    width = float(root.attrib.get("width", "109").replace("px", ""))
    height = float(root.attrib.get("height", "109").replace("px", ""))
    return 0.0, 0.0, width, height


def _strip_text_nodes(root: ET.Element) -> None:
    for parent in list(root.iter()):
        removable: list[ET.Element] = []
        for child in list(parent):
            if child.tag.endswith("text"):
                removable.append(child)
        for child in removable:
            parent.remove(child)
