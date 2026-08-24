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
            Band("Public Internet", 25, 160, 250, 230, "#f97316", "#ffffff"),
            Band("HDB Private VPC", 330, 105, 520, 540, "#3730ff", "#ffffff"),
            Band("Public Subnet", 380, 185, 165, 250, "#94a3b8", "#ffffff"),
            Band("Private Subnet", 560, 185, 245, 250, "#94a3b8", "#ffffff"),
            Band("AWS Managed Services", 910, 105, 610, 650, "#f97316", "#ffffff"),
            Band("Tableau VPC", 1570, 160, 300, 310, "#7c3aed", "#ffffff"),
            Band("Private Subnet", 1605, 230, 245, 225, "#94a3b8", "#ffffff"),
        ],
        nodes=[
            Node("datagov", "DATA.GOV.SG\npublic endpoint", 55, 245, w=190, h=112, fill="#ffffff"),
            Node("igw", "Internet\nGateway", 315, 248, w=95, h=124, fill="#ffffff"),
            Node("nat", "NAT Gateway\noutbound egress", 425, 280, w=95, h=124, fill="#ffffff"),
            Node("fargate", "ECS Fargate\nExtract Validate\nTransform Load", 620, 248, icon="aws-fargate.png", w=150, h=142),
            Node("s3_endpoint", "S3 Gateway Endpoint\nprivate route table", 570, 500, w=230, h=92, fill=COLORS["private_fill"]),
            Node("scheduler", "EventBridge\nScheduler", 950, 155, icon="amazon-eventbridge.png", w=145, h=128, fill=COLORS["schedule"]),
            Node("s3raw", "Amazon S3\nraw zone", 950, 455, icon="amazon-s3.png", w=145, h=128),
            Node("s3curated", "Amazon S3\ncurated zone", 1140, 455, icon="amazon-s3.png", w=145, h=128),
            Node("glue", "AWS Glue\nData Catalog", 1330, 455, icon="aws-glue.png", w=145, h=128),
            Node("athena", "Amazon Athena\nmanaged service", 1330, 300, icon="amazon-athena.png", w=145, h=132),
            Node("results", "S3 query\nresults", 1330, 630, icon="amazon-s3.png", w=145, h=118),
            Node("task_events", "EventBridge Rule\nECS STOPPED", 950, 610, icon="amazon-eventbridge.png", w=145, h=118, fill=COLORS["failure"]),
            Node("ops", "CloudWatch /\nCloudTrail /\nSNS-SQS alert", 1330, 145, icon="amazon-cloudwatch.png", w=145, h=128),
            Node("scheduler_dlq", "Scheduler invoke\nretry / SQS DLQ", 1140, 155, w=145, h=92, fill=COLORS["failure"]),
            Node("vpce_tableau", "Athena Interface\nVPC Endpoint ENI", 1615, 300, icon="aws-privatelink.png", w=135, h=132),
            Node("tableau", "Tableau Server\nBI dashboards", 1765, 300, w=75, h=132, fill="#ffffff"),
        ],
        arrows=[
            ([(620, 320), (528, 320)], False),
            ([(425, 320), (418, 320)], False),
            ([(315, 310), (253, 301)], False),
            ([(1022, 283), (770, 295)], False),
            ([(695, 390), (695, 492)], False),
            ([(800, 530), (942, 519)], False),
            ([(800, 562), (1132, 519)], False),
            ([(770, 360), (870, 360), (870, 605), (1402, 605), (1402, 591)], False),
            ([(1615, 366), (1483, 366)], False),
            ([(1402, 432), (1402, 447)], False),
            ([(1330, 366), (1293, 519)], False),
            ([(1475, 366), (1500, 366), (1500, 689), (1483, 689)], False),
            ([(1765, 366), (1758, 366)], False),
            ([(710, 390), (710, 728), (942, 669)], True),
            ([(950, 219), (880, 219), (880, 728), (942, 669)], True),
            ([(1095, 219), (1132, 219)], True),
            ([(1095, 669), (1322, 209)], True),
        ],
        footer_title="NAT uses the Internet Gateway for outbound public internet access; S3 bucket traffic uses the S3 Gateway Endpoint route path.",
        footer_note="Scheduler DLQ covers RunTask invocation failure; ECS task runtime failure is handled by ECS task-state events and an EventBridge alert rule.",
    )


def generate_overview_diagram(output_path: Path) -> Path:
    return _render(_overview_diagram(), output_path)


def main() -> None:
    generate_overview_diagram(ROOT / "architecture" / "hdb_resale_architecture.png")


if __name__ == "__main__":
    main()
