from __future__ import annotations

from dataclasses import dataclass
import html
import math
from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
ICON_DIR = ROOT / "architecture" / "aws-icons"
CANVAS_SIZE = (1800, 1050)

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
    y_text = node.y + 74
    if node.icon:
        icon_path = ICON_DIR / node.icon
        if icon_path.exists():
            icon = Image.open(icon_path).convert("RGBA").resize((54, 54))
            canvas.paste(icon, (node.x + node.w // 2 - 27, node.y + 16), icon)
        y_text = node.y + 86
    lines: list[str] = []
    for part in node.label.split("\n"):
        lines.extend(wrap(part, width=24) or [""])
    for line in lines[:3]:
        _draw_text(draw, (node.x + node.w // 2, y_text), line, 14, bold=True, anchor="ma")
        y_text += 20


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


def _svg_rect(x: int, y: int, w: int, h: int, fill: str, stroke: str, sw: int = 2, rx: int = 12) -> str:
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def _svg_text(x: int | float, y: int | float, text: str, size: int, *, fill: str = COLORS["ink"], weight: int = 700, anchor: str = "middle") -> str:
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-family="Arial" font-size="{size}" font-weight="{weight}" fill="{fill}">{html.escape(text)}</text>'


def _svg_node(node: Node) -> list[str]:
    parts = [_svg_rect(node.x, node.y, node.w, node.h, node.fill, COLORS["border"])]
    y_text = node.y + 74
    if node.icon:
        parts.append(f'<image href="aws-icons/{html.escape(node.icon)}" x="{node.x + node.w / 2 - 27}" y="{node.y + 16}" width="54" height="54"/>')
        y_text = node.y + 86
    lines: list[str] = []
    for part in node.label.split("\n"):
        lines.extend(wrap(part, width=24) or [""])
    for i, line in enumerate(lines[:3]):
        parts.append(_svg_text(node.x + node.w / 2, y_text + i * 20, line, 14))
    return parts


def _svg_arrow(points: list[tuple[int, int]], dashed: bool = False) -> str:
    path = f"M {points[0][0]} {points[0][1]} " + " ".join(f"L {x} {y}" for x, y in points[1:])
    dash = ' stroke-dasharray="9 8"' if dashed else ""
    return f'<path d="{path}" fill="none" stroke="{COLORS["arrow"]}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#arrow)"{dash}/>'


def _render(diagram: Diagram, output_path: Path) -> Path:
    canvas = Image.new("RGB", CANVAS_SIZE, _rgb(COLORS["bg"]))
    draw = ImageDraw.Draw(canvas)
    _draw_text(draw, (55, 70), diagram.title, 34, bold=True)
    for band in diagram.bands:
        _draw_band(draw, band)
    for node in diagram.nodes:
        _draw_node(canvas, draw, node)
    for points, dashed in diagram.arrows:
        _draw_arrow(draw, points, dashed)
    _draw_text(draw, (70, 946), diagram.footer_title, 19, bold=True)
    _draw_text(draw, (70, 980), diagram.footer_note, 17, fill=COLORS["muted"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
    _write_svg(diagram, output_path.with_suffix(".svg"))
    return output_path


def _write_svg(diagram: Diagram, path: Path) -> None:
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="1050" viewBox="0 0 1800 1050">',
        "<defs>",
        f'<marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth"><path d="M2,2 L10,6 L2,10 Z" fill="{COLORS["arrow"]}"/></marker>',
        "</defs>",
        f'<rect width="1800" height="1050" fill="{COLORS["bg"]}"/>',
        f'<text x="55" y="70" font-family="Arial" font-size="34" font-weight="700" fill="{COLORS["ink"]}">{html.escape(diagram.title)}</text>',
    ]
    for band in diagram.bands:
        parts.append(_svg_rect(band.x, band.y, band.w, band.h, band.fill, band.stroke, 3, 14))
        parts.append(_svg_text(band.x + 20, band.y + 32, band.label, 22, fill=band.stroke, anchor="start"))
    for node in diagram.nodes:
        parts.extend(_svg_node(node))
    for points, dashed in diagram.arrows:
        parts.append(_svg_arrow(points, dashed))
    parts.append(_svg_text(70, 946, diagram.footer_title, 19, anchor="start"))
    parts.append(_svg_text(70, 980, diagram.footer_note, 17, fill=COLORS["muted"], weight=400, anchor="start"))
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def _ingestion_diagram() -> Diagram:
    return Diagram(
        title="HDB Resale Data Ingestion Architecture",
        bands=[
            Band("AWS VPC", 300, 320, 1000, 555, COLORS["vpc"], COLORS["vpc_fill"]),
            Band("Public Subnet", 340, 410, 330, 300, COLORS["public"], COLORS["public_fill"]),
            Band("Private Subnet, AZ A", 760, 410, 500, 300, COLORS["private"], COLORS["private_fill"]),
        ],
        nodes=[
            Node("source", "data.gov.sg\npublic endpoint", 70, 180, fill=COLORS["external"]),
            Node("igw", "Internet Gateway\nVPC edge", 360, 180, fill=COLORS["external"]),
            Node("scheduler", "EventBridge Scheduler\nRunTask trigger", 790, 170, icon="amazon-eventbridge.png", fill=COLORS["schedule"], w=240),
            Node("nat", "NAT Gateway\noutbound egress", 390, 535),
            Node("task", "ECS Fargate Task\nprivate ENI", 890, 530, icon="aws-fargate.png", w=230),
            Node("s3_endpoint", "S3 Gateway Endpoint\nprivate route table", 780, 730, w=240),
            Node("secrets_endpoint", "Secrets Manager\ninterface endpoint ENI", 1030, 730, icon="aws-privatelink.png", w=240),
            Node("s3raw", "Amazon S3\nraw zone", 1345, 360, icon="amazon-s3.png", w=210),
            Node("s3curated", "Amazon S3\ncurated zone", 1345, 535, icon="amazon-s3.png", w=210),
            Node("glue", "AWS Glue\nData Catalog", 1345, 710, icon="aws-glue.png", w=210),
            Node("cloudwatch", "CloudWatch Logs\nand metrics", 1570, 535, icon="amazon-cloudwatch.png", w=210),
            Node("dlq", "Retry policy\nand DLQ", 1570, 710, fill=COLORS["failure"], w=210),
            Node("secrets", "AWS Secrets Manager\nmanaged secrets", 1570, 360, icon="aws-secrets-manager.png", w=210),
        ],
        arrows=[
            ([(910, 304), (910, 522)], False),
            ([(882, 585), (618, 585)], False),
            ([(500, 527), (500, 315), (470, 315), (470, 304)], False),
            ([(352, 243), (298, 243)], False),
            ([(1010, 660), (1010, 722)], True),
            ([(1122, 660), (1122, 722)], True),
            ([(1128, 560), (1310, 560), (1310, 423), (1337, 423)], False),
            ([(1128, 598), (1337, 598)], False),
            ([(1128, 636), (1310, 636), (1310, 773), (1337, 773)], False),
            ([(1278, 793), (1285, 793), (1285, 330), (1675, 330), (1675, 352)], True),
            ([(1128, 580), (1280, 580), (1280, 510), (1675, 510), (1675, 527)], True),
            ([(1128, 646), (1280, 646), (1280, 900), (1675, 900), (1675, 844)], True),
        ],
        footer_title="EventBridge Scheduler starts ECS/Fargate RunTask; only outbound data.gov.sg traffic uses NAT Gateway -> Internet Gateway.",
        footer_note="AWS managed services sit outside subnets; Fargate reaches S3 through a Gateway Endpoint and Secrets Manager through an Interface Endpoint ENI.",
    )


def _exploitation_diagram() -> Diagram:
    return Diagram(
        title="HDB Resale Data Exploitation Architecture",
        bands=[
            Band("AWS Analytics VPC", 55, 150, 1065, 700, COLORS["vpc"], COLORS["vpc_fill"]),
            Band("Private Subnet, AZ A", 90, 245, 450, 445, COLORS["private"], COLORS["private_fill"]),
            Band("Endpoint Subnet", 620, 245, 450, 445, COLORS["private"], COLORS["private_fill"]),
        ],
        nodes=[
            Node("tableau", "Tableau Server\non AWS", 165, 405),
            Node("athena_ep", "Athena Interface\nEndpoint ENI", 690, 405, icon="aws-privatelink.png", w=240),
            Node("s3_endpoint", "S3 Gateway Endpoint\nroute table", 690, 610, w=240),
            Node("athena", "Amazon Athena\nmanaged service", 1230, 295, icon="amazon-athena.png", w=240),
            Node("catalog", "AWS Glue\nData Catalog", 1230, 470, icon="aws-glue.png"),
            Node("s3", "Amazon S3\ncurated parquet/csv", 1230, 645, icon="amazon-s3.png", w=240),
            Node("lake", "Lake Formation\nIAM governance", 1540, 295, icon="aws-lake-formation.png", w=230),
            Node("cloudtrail", "AWS CloudTrail\naudit events", 1540, 470, icon="aws-cloudtrail.png", w=230),
            Node("cloudwatch", "CloudWatch\nquery metrics", 1540, 645, icon="amazon-cloudwatch.png", w=230),
        ],
        arrows=[
            ([(393, 468), (682, 468)], False),
            ([(938, 468), (1222, 358)], False),
            ([(938, 673), (1222, 708)], False),
            ([(1478, 358), (1532, 358)], True),
            ([(1478, 533), (1532, 533)], True),
            ([(1478, 708), (1532, 708)], True),
            ([(1350, 421), (1350, 462)], False),
            ([(1350, 596), (1350, 637)], False),
        ],
        footer_title="Tableau reaches Athena privately through an Athena Interface Endpoint; Athena service remains outside the VPC.",
        footer_note="Athena reads governed curated S3 data through Glue/Lake Formation metadata; S3 Gateway Endpoint avoids NAT for S3 traffic.",
    )


def generate_ingestion_diagram(output_path: Path) -> Path:
    return _render(_ingestion_diagram(), output_path)


def generate_exploitation_diagram(output_path: Path) -> Path:
    return _render(_exploitation_diagram(), output_path)


def main() -> None:
    generate_ingestion_diagram(ROOT / "architecture" / "data_ingestion_architecture.png")
    generate_exploitation_diagram(ROOT / "architecture" / "data_exploitation_architecture.png")


if __name__ == "__main__":
    main()
