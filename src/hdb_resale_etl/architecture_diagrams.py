from __future__ import annotations

from dataclasses import dataclass
import html
from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


ICON_DIR = Path(__file__).resolve().parents[2] / "architecture" / "aws-icons"


@dataclass(frozen=True)
class Node:
    key: str
    label: str
    x: int
    y: int
    icon: str | None = None
    fill: str = "#ffffff"


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


def _canvas(title: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (1800, 1050), "#f7f9fc")
    draw = ImageDraw.Draw(image)
    draw.text((55, 35), title, fill="#172033", font=_font(34, bold=True))
    return image, draw


def _node(draw: ImageDraw.ImageDraw, node: Node) -> None:
    w, h = 210, 126
    x, y = node.x, node.y
    draw.rounded_rectangle((x, y, x + w, y + h), radius=10, fill=node.fill, outline="#4b5563", width=2)
    if node.icon:
        icon_path = ICON_DIR / node.icon
        if icon_path.exists():
            icon = Image.open(icon_path).convert("RGBA").resize((54, 54))
            draw._image.paste(icon, (x + 78, y + 12), icon)
    lines = []
    for part in node.label.split("\n"):
        lines.extend(wrap(part, width=22) or [""])
    y_text = y + 72
    for line in lines[:3]:
        bbox = draw.textbbox((0, 0), line, font=_font(14, bold=True))
        draw.text((x + (w - (bbox[2] - bbox[0])) // 2, y_text), line, fill="#172033", font=_font(14, bold=True))
        y_text += 18


def _label_box(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], title: str, outline: str, fill: str) -> None:
    draw.rounded_rectangle(xy, radius=16, fill=fill, outline=outline, width=3)
    draw.text((xy[0] + 18, xy[1] + 12), title, fill=outline, font=_font(20, bold=True))


def _arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], label: str = "") -> None:
    draw.line([start, end], fill="#2563eb", width=4)
    x1, y1 = start
    x2, y2 = end
    if abs(x2 - x1) >= abs(y2 - y1):
        points = [(x2, y2), (x2 - 13, y2 - 8), (x2 - 13, y2 + 8)] if x2 >= x1 else [(x2, y2), (x2 + 13, y2 - 8), (x2 + 13, y2 + 8)]
    else:
        points = [(x2, y2), (x2 - 8, y2 - 13), (x2 + 8, y2 - 13)] if y2 >= y1 else [(x2, y2), (x2 - 8, y2 + 13), (x2 + 8, y2 + 13)]
    draw.polygon(points, fill="#2563eb")


def _draw_nodes(draw: ImageDraw.ImageDraw, nodes: list[Node]) -> None:
    for node in nodes:
        _node(draw, node)


def generate_ingestion_diagram(output_path: Path) -> Path:
    image, draw = _canvas("HDB Resale Data Ingestion Architecture")

    draw.text((70, 120), "Public Internet", fill="#334155", font=_font(20, bold=True))
    data = Node("data", "data.gov.sg\npublic endpoint", 70, 160, None, "#e0f2fe")
    igw = Node("igw", "Internet Gateway\nVPC edge", 345, 160, "aws-transit-gateway.png", "#e0f2fe")

    _label_box(draw, (300, 340, 1705, 880), "AWS VPC", "#7c3aed", "#faf5ff")
    _label_box(draw, (340, 405, 820, 770), "Public Subnet", "#047857", "#ecfdf5")
    _label_box(draw, (900, 405, 1660, 770), "Private Subnet", "#0369a1", "#eff6ff")

    nodes = [
        data,
        igw,
        Node("eventbridge", "Amazon EventBridge\nschedule", 950, 210, "amazon-eventbridge.png", "#fff7ed"),
        Node("nat", "NAT Gateway\noutbound egress", 475, 515, "aws-transit-gateway.png", "#ffffff"),
        Node("fargate", "AWS Fargate\ningestion task", 1015, 515, "aws-fargate.png", "#ffffff"),
        Node("s3raw", "Amazon S3\nraw immutable", 1295, 455, "amazon-s3.png", "#ffffff"),
        Node("s3curated", "Amazon S3\ncurated outputs", 1295, 620, "amazon-s3.png", "#ffffff"),
        Node("glue", "AWS Glue\nData Catalog", 1510, 540, "aws-glue.png", "#ffffff"),
        Node("cloudwatch", "Amazon CloudWatch\nlogs and alarms", 1015, 725, "amazon-cloudwatch.png", "#ffffff"),
        Node("secrets", "AWS Secrets Manager\nmanaged secrets", 475, 725, "aws-secrets-manager.png", "#ffffff"),
    ]
    _draw_nodes(draw, nodes)

    _arrow(draw, (1015, 578), (685, 578), "private route")
    _arrow(draw, (475, 560), (555, 286), "via IGW")
    _arrow(draw, (555, 223), (345, 223), "outbound")
    _arrow(draw, (345, 223), (280, 223), "HTTPS")
    _arrow(draw, (1120, 515), (1120, 336), "trigger")
    _arrow(draw, (1225, 570), (1295, 510), "write raw")
    _arrow(draw, (1225, 590), (1295, 675), "write curated")
    _arrow(draw, (1505, 680), (1510, 610), "catalog")
    _arrow(draw, (1120, 641), (1120, 725), "logs")
    _arrow(draw, (685, 760), (1015, 610), "runtime access")

    draw.text((70, 930), "Network direction: private Fargate task -> private route table -> NAT Gateway in public subnet -> Internet Gateway -> data.gov.sg. No unsolicited inbound traffic to private Fargate.", fill="#172033", font=_font(19, bold=True))
    draw.text((70, 965), "Security and scale: least-privilege IAM task role, KMS encrypted S3, S3 gateway endpoint where applicable, CloudWatch/CloudTrail audit, batch files >100 MB supported.", fill="#334155", font=_font(17))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    _write_svg_source(output_path.with_suffix(".svg"), "HDB Resale Data Ingestion Architecture", nodes)
    return output_path


def generate_exploitation_diagram(output_path: Path) -> Path:
    image, draw = _canvas("HDB Resale Data Exploitation Architecture")
    _label_box(draw, (55, 150, 1700, 850), "AWS Analytics VPC / Data Platform", "#7c3aed", "#faf5ff")
    _label_box(draw, (90, 245, 500, 690), "Private Subnet", "#0369a1", "#eff6ff")

    nodes = [
        Node("tableau", "Tableau Server\non AWS", 165, 405, None, "#ffffff"),
        Node("privatelink", "AWS PrivateLink\nVPC endpoints", 585, 405, "aws-privatelink.png", "#ffffff"),
        Node("athena", "Amazon Athena\nAthena driver", 865, 405, "amazon-athena.png", "#ffffff"),
        Node("catalog", "AWS Glue\nData Catalog", 1150, 300, "aws-glue.png", "#ffffff"),
        Node("s3", "Amazon S3\ncurated parquet/csv", 1150, 510, "amazon-s3.png", "#ffffff"),
        Node("lake", "AWS Lake Formation\naccess governance", 865, 675, "aws-lake-formation.png", "#ffffff"),
        Node("cloudtrail", "AWS CloudTrail\naudit events", 1430, 405, "aws-cloudtrail.png", "#ffffff"),
        Node("cloudwatch", "Amazon CloudWatch\nmetrics and alarms", 1430, 600, "amazon-cloudwatch.png", "#ffffff"),
    ]
    _draw_nodes(draw, nodes)

    _arrow(draw, (375, 468), (585, 468), "JDBC/ODBC")
    _arrow(draw, (795, 468), (865, 468), "private path")
    _arrow(draw, (1075, 445), (1150, 355), "schema")
    _arrow(draw, (1075, 495), (1150, 565), "query data")
    _arrow(draw, (970, 531), (970, 675), "policy")
    _arrow(draw, (1360, 468), (1430, 468), "audit")
    _arrow(draw, (1360, 575), (1430, 650), "metrics")

    draw.text((70, 925), "Tableau on AWS connects to Amazon Athena through the Athena driver. Athena reads curated S3 data using Glue Catalog metadata and Lake Formation/IAM governance.", fill="#172033", font=_font(19, bold=True))
    draw.text((70, 960), "Performance: partition by year/month, prefer Parquet for production curated tables, monitor query cost, cache BI extracts where appropriate.", fill="#334155", font=_font(17))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    _write_svg_source(output_path.with_suffix(".svg"), "HDB Resale Data Exploitation Architecture", nodes)
    return output_path


def _write_svg_source(path: Path, title: str, nodes: list[Node]) -> None:
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="1050" viewBox="0 0 1800 1050">',
        '<rect width="1800" height="1050" fill="#f7f9fc"/>',
        f'<text x="55" y="70" font-family="Arial" font-size="34" font-weight="700" fill="#172033">{html.escape(title)}</text>',
    ]
    for node in nodes:
        parts.append(f'<rect x="{node.x}" y="{node.y}" width="210" height="126" rx="10" fill="{node.fill}" stroke="#4b5563" stroke-width="2"/>')
        if node.icon:
            parts.append(f'<image href="aws-icons/{html.escape(node.icon)}" x="{node.x + 78}" y="{node.y + 12}" width="54" height="54"/>')
        for i, line in enumerate(node.label.split("\n")):
            parts.append(f'<text x="{node.x + 105}" y="{node.y + 88 + i * 18}" text-anchor="middle" font-family="Arial" font-size="14" font-weight="700" fill="#172033">{html.escape(line)}</text>')
    parts.append('</svg>')
    path.write_text("\n".join(parts), encoding="utf-8")


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    generate_ingestion_diagram(root / "architecture" / "data_ingestion_architecture.png")
    generate_exploitation_diagram(root / "architecture" / "data_exploitation_architecture.png")


if __name__ == "__main__":
    main()