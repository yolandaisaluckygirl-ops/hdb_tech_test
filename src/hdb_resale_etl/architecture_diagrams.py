from __future__ import annotations

from pathlib import Path
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


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


def _box(draw: ImageDraw.ImageDraw, xy: tuple[int, int, int, int], text: str, fill: str, outline: str = "#2f3a4a") -> None:
    draw.rounded_rectangle(xy, radius=14, fill=fill, outline=outline, width=2)
    x1, y1, x2, y2 = xy
    lines = []
    for part in text.split("\n"):
        lines.extend(wrap(part, width=23) or [""])
    line_height = 22
    total_height = line_height * len(lines)
    y = y1 + ((y2 - y1) - total_height) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=_font(15, bold=True))
        draw.text((x1 + ((x2 - x1) - (bbox[2] - bbox[0])) // 2, y), line, fill="#172033", font=_font(15, bold=True))
        y += line_height


def _arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int]) -> None:
    draw.line([start, end], fill="#3f5f8f", width=4)
    x, y = end
    draw.polygon([(x, y), (x - 12, y - 7), (x - 12, y + 7)], fill="#3f5f8f")


def _canvas(title: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (1600, 900), "#f7f9fc")
    draw = ImageDraw.Draw(image)
    draw.text((55, 35), title, fill="#172033", font=_font(34, bold=True))
    return image, draw


def generate_ingestion_diagram(output_path: Path) -> Path:
    image, draw = _canvas("HDB Resale Data Ingestion Architecture")
    boxes = {
        "data": (70, 165, 300, 265, "data.gov.sg\nPublic Endpoint", "#d9ecff"),
        "nat": (390, 165, 620, 265, "Private Subnet\nNAT Gateway / Egress", "#e7f5df"),
        "scheduler": (710, 95, 940, 195, "EventBridge\nMonthly Schedule", "#fff2cc"),
        "compute": (710, 250, 940, 350, "ECS Fargate / Glue\nPython ETL", "#fff2cc"),
        "raw": (1030, 110, 1260, 210, "S3 Raw Zone\nImmutable CSV", "#e8ddff"),
        "curated": (1030, 275, 1260, 375, "S3 Curated Zone\nCleaned / Hashed", "#e8ddff"),
        "catalog": (1345, 275, 1545, 375, "Glue Data Catalog\nPartition Metadata", "#ffdfe1"),
        "monitoring": (710, 505, 940, 605, "CloudWatch\nLogs / Alarms", "#f4e6d8"),
        "secrets": (390, 505, 620, 605, "Secrets Manager\nAPI Key / DB Secrets", "#f4e6d8"),
    }
    for x1, y1, x2, y2, text, fill in boxes.values():
        _box(draw, (x1, y1, x2, y2), text, fill)
    _arrow(draw, (300, 215), (390, 215))
    _arrow(draw, (620, 215), (710, 300))
    _arrow(draw, (825, 195), (825, 250))
    _arrow(draw, (940, 300), (1030, 160))
    _arrow(draw, (940, 310), (1030, 325))
    _arrow(draw, (1260, 325), (1345, 325))
    _arrow(draw, (825, 350), (825, 505))
    _arrow(draw, (620, 555), (710, 325))
    draw.text((70, 760), "Security notes: private ETL runtime, controlled outbound egress, encrypted S3 buckets, least-privilege IAM, audit logs.", fill="#28364a", font=_font(20))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path


def generate_exploitation_diagram(output_path: Path) -> Path:
    image, draw = _canvas("HDB Resale Data Exploitation Architecture")
    boxes = {
        "tableau": (70, 200, 320, 310, "Tableau on AWS\nPrivate Subnet", "#d9ecff"),
        "endpoint": (410, 200, 660, 310, "VPC Endpoint / PrivateLink\nPrivate Traffic Where Possible", "#e7f5df"),
        "athena": (750, 200, 1000, 310, "Amazon Athena\nSQL Query Service", "#fff2cc"),
        "catalog": (1090, 105, 1340, 215, "Glue Data Catalog\nSchemas / Partitions", "#ffdfe1"),
        "s3": (1090, 295, 1340, 405, "S3 Curated Zone\nCleaned + Hashed Data", "#e8ddff"),
        "lake": (750, 505, 1000, 615, "Lake Formation / IAM\nAccess Governance", "#f4e6d8"),
        "logs": (1090, 505, 1340, 615, "CloudTrail + CloudWatch\nAudit / Monitoring", "#f4e6d8"),
    }
    for x1, y1, x2, y2, text, fill in boxes.values():
        _box(draw, (x1, y1, x2, y2), text, fill)
    _arrow(draw, (320, 255), (410, 255))
    _arrow(draw, (660, 255), (750, 255))
    _arrow(draw, (1000, 255), (1090, 160))
    _arrow(draw, (1000, 265), (1090, 350))
    _arrow(draw, (875, 310), (875, 505))
    _arrow(draw, (1000, 560), (1090, 560))
    draw.text((70, 760), "Performance notes: partition curated data by year/month, store analytics files as Parquet in production, monitor query cost and latency.", fill="#28364a", font=_font(20))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return output_path


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    generate_ingestion_diagram(root / "architecture" / "data_ingestion_architecture.png")
    generate_exploitation_diagram(root / "architecture" / "data_exploitation_architecture.png")


if __name__ == "__main__":
    main()
