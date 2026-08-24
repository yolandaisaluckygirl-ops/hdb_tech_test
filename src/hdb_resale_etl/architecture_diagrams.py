from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
ICON_DIR = ROOT / "architecture" / "aws-icons"
CANVAS_SIZE = (1900, 860)

COLORS = {
    "bg": "#f7f9fc",
    "ink": "#172033",
    "muted": "#334155",
    "border": "#475569",
    "arrow": "#2563eb",
    "vpc": "#7c3aed",
    "vpc_fill": "#fbf7ff",
    "public": "#047857",
    "public_fill": "#ecfdf5",
    "private": "#0369a1",
    "private_fill": "#eff6ff",
    "external": "#e0f2fe",
    "service": "#ffffff",
    "schedule": "#fff7ed",
    "failure": "#fff1f2",
}


@dataclass(frozen=True)
class Node:
    key: str
    label: str
    x: int
    y: int
    w: int = 220
    h: int = 126
    icon: str | None = None
    fill: str = COLORS["service"]
    dashed: bool = False


@dataclass(frozen=True)
class Band:
    label: str
    x: int
    y: int
    w: int
    h: int
    stroke: str
    fill: str


@dataclass(frozen=True)
class Diagram:
    title: str
    bands: list[Band]
    nodes: list[Node]
    arrows: list[tuple[list[tuple[int, int]], bool]]
    footer_title: str
    footer_note: str


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int, *, bold: bool = False, fill: str = COLORS["ink"], anchor: str = "la") -> None:
    draw.text(xy, text, font=_font(size, bold), fill=_rgb(fill), anchor=anchor)


def _draw_node(canvas: Image.Image, draw: ImageDraw.ImageDraw, node: Node) -> None:
    outline = COLORS["border"]
    draw.rounded_rectangle((node.x, node.y, node.x + node.w, node.y + node.h), radius=12, fill=_rgb(node.fill), outline=_rgb(outline), width=2)
    y_text = node.y + 36
    if node.icon:
        icon_path = ICON_DIR / node.icon
        if icon_path.exists():
            icon = Image.open(icon_path).convert("RGBA").resize((54, 54))
            canvas.paste(icon, (node.x + node.w // 2 - 27, node.y + 18), icon)
        y_text = node.y + 92
    lines: list[str] = []
    for part in node.label.split("\n"):
        lines.extend(wrap(part, width=max(10, node.w // 9)) or [""])
    for line in lines[:3]:
        _draw_text(draw, (node.x + node.w // 2, y_text), line, 13, bold=True, anchor="ma")
        y_text += 18


def _draw_band(draw: ImageDraw.ImageDraw, band: Band) -> None:
    draw.rounded_rectangle((band.x, band.y, band.x + band.w, band.y + band.h), radius=14, fill=_rgb(band.fill), outline=_rgb(band.stroke), width=3)
    _draw_text(draw, (band.x + 20, band.y + 32), band.label, 22, bold=True, fill=band.stroke)


def _draw_arrow(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], dashed: bool = False) -> None:
    for start, end in zip(points, points[1:]):
        if dashed:
            _draw_dashed_line(draw, start, end)
        else:
            draw.line((*start, *end), fill=_rgb(COLORS["arrow"]), width=4)
    _draw_arrow_head(draw, points[-2], points[-1])


def _draw_dashed_line(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int]) -> None:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    distance = math.hypot(dx, dy)
    if distance == 0:
        return
    ux = dx / distance
    uy = dy / distance
    pos = 0.0
    while pos < distance:
        dash_end = min(pos + 12, distance)
        draw.line(
            (
                start[0] + ux * pos,
                start[1] + uy * pos,
                start[0] + ux * dash_end,
                start[1] + uy * dash_end,
            ),
            fill=_rgb(COLORS["arrow"]),
            width=4,
        )
        pos += 22


def _draw_arrow_head(draw: ImageDraw.ImageDraw, previous: tuple[int, int], tip: tuple[int, int]) -> None:
    angle = math.atan2(tip[1] - previous[1], tip[0] - previous[0])
    length = 16
    spread = math.pi / 7
    points = [tip]
    for sign in (1, -1):
        points.append((tip[0] - length * math.cos(angle + sign * spread), tip[1] - length * math.sin(angle + sign * spread)))
    draw.polygon(points, fill=_rgb(COLORS["arrow"]))


def _render(diagram: Diagram, output_path: Path) -> Path:
    canvas = Image.new("RGB", CANVAS_SIZE, _rgb(COLORS["bg"]))
    draw = ImageDraw.Draw(canvas)
    _draw_text(draw, (55, 54), diagram.title, 30, bold=True)
    for band in diagram.bands:
        _draw_band(draw, band)
    for node in diagram.nodes:
        _draw_node(canvas, draw, node)
    for points, dashed in diagram.arrows:
        _draw_arrow(draw, points, dashed)
    _draw_text(draw, (55, 780), diagram.footer_title, 18, bold=True)
    _draw_text(draw, (55, 810), diagram.footer_note, 16, fill=COLORS["muted"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    return output_path


def _overview_diagram() -> Diagram:
    return Diagram(
        title="HDB Resale Data Platform Architecture",
        bands=[
            Band("Public", 25, 160, 255, 250, "#f97316", "#ffffff"),
            Band("HDB Private VPC", 330, 105, 930, 510, "#3730ff", "#ffffff"),
            Band("Public Subnet", 365, 180, 150, 350, "#94a3b8", "#ffffff"),
            Band("Private Subnet", 555, 180, 495, 350, "#94a3b8", "#ffffff"),
            Band("AWS Managed", 1285, 160, 245, 250, "#f97316", "#ffffff"),
            Band("Tableau VPC", 1560, 160, 310, 250, "#7c3aed", "#ffffff"),
        ],
        nodes=[
            Node("datagov", "DATA.GOV.SG\npublic endpoint", 55, 245, w=195, h=112, fill="#ffffff"),
            Node("nat", "NAT Gateway\noutbound egress", 388, 248, w=105, h=124, fill="#ffffff"),
            Node("scheduler", "EventBridge\nScheduler", 600, 420, icon="amazon-eventbridge.png", w=135, h=128, fill=COLORS["schedule"]),
            Node("fargate", "ECS Fargate\nETL task", 600, 248, icon="aws-fargate.png", w=135, h=128),
            Node("s3raw", "Amazon S3\nraw zone", 760, 248, icon="amazon-s3.png", w=135, h=128),
            Node("s3curated", "Amazon S3\ncurated zone", 920, 248, icon="amazon-s3.png", w=135, h=128),
            Node("glue", "AWS Glue\nData Catalog", 1080, 248, icon="aws-glue.png", w=135, h=128),
            Node("vpce_hdb", "Athena\nPrivateLink", 1080, 430, icon="aws-privatelink.png", w=135, h=132),
            Node("athena", "Amazon Athena\nmanaged service", 1340, 228, icon="amazon-athena.png", w=145, h=132),
            Node("results", "S3 query\nresults", 1340, 455, icon="amazon-s3.png", w=145, h=118),
            Node("vpce_tableau", "Athena\nPrivateLink", 1590, 228, icon="aws-privatelink.png", w=140, h=132),
            Node("tableau", "Tableau\nBI dashboards", 1755, 228, w=100, h=132, fill="#ffffff"),
            Node("task_failure", "Task stopped\nnon-zero exit", 600, 655, w=175, h=86, fill=COLORS["failure"]),
            Node("scheduler_dlq", "Scheduler invoke\nretry / DLQ", 815, 655, w=175, h=86, fill=COLORS["failure"]),
        ],
        arrows=[
            ([(600, 312), (495, 312)], False),
            ([(388, 312), (258, 301)], False),
            ([(735, 312), (752, 312)], False),
            ([(895, 312), (912, 312)], False),
            ([(655, 420), (655, 384)], False),
            ([(1340, 294), (1223, 294)], False),
            ([(1340, 330), (1268, 330), (1268, 402), (988, 402), (988, 384)], False),
            ([(1412, 360), (1412, 447)], False),
            ([(1590, 294), (1493, 294)], False),
            ([(1755, 294), (1738, 294)], False),
            ([(668, 376), (668, 647)], True),
            ([(660, 548), (902, 647)], True),
        ],
        footer_title="NAT Gateway stays in the public subnet; private ETL traffic uses it only for data.gov.sg and services without VPC endpoints.",
        footer_note="Athena remains an AWS managed service: it reads Glue Catalog metadata, scans curated S3 data, and writes query results to controlled S3 output.",
    )


def generate_overview_diagram(output_path: Path) -> Path:
    return _render(_overview_diagram(), output_path)


def main() -> None:
    generate_overview_diagram(ROOT / "architecture" / "hdb_resale_architecture.png")


if __name__ == "__main__":
    main()
