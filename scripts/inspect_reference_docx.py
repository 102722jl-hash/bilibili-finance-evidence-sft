from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn


def twips_to_cm(value):
    if value is None:
        return None
    return round(value / 360000, 3)


def paragraph_info(paragraph):
    text = paragraph.text.strip()
    if not text:
        return None
    runs = []
    for run in paragraph.runs:
        if not run.text:
            continue
        color = None
        if run.font.color and run.font.color.rgb:
            color = str(run.font.color.rgb)
        runs.append(
            {
                "text": run.text,
                "bold": run.bold,
                "italic": run.italic,
                "font": run.font.name,
                "size_pt": run.font.size.pt if run.font.size else None,
                "color": color,
            }
        )
    return {
        "text": text,
        "style": paragraph.style.name if paragraph.style else None,
        "alignment": str(paragraph.alignment),
        "runs": runs,
    }


def main():
    path = Path(sys.argv[1])
    doc = Document(path)
    result = {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size": path.stat().st_size,
        "sections": [],
        "paragraphs": [],
        "tables": [],
        "headers": [],
        "footers": [],
        "styles": [],
        "package_parts": [],
    }

    for section in doc.sections:
        result["sections"].append(
            {
                "width_cm": twips_to_cm(section.page_width),
                "height_cm": twips_to_cm(section.page_height),
                "top_cm": twips_to_cm(section.top_margin),
                "bottom_cm": twips_to_cm(section.bottom_margin),
                "left_cm": twips_to_cm(section.left_margin),
                "right_cm": twips_to_cm(section.right_margin),
                "header_cm": twips_to_cm(section.header_distance),
                "footer_cm": twips_to_cm(section.footer_distance),
                "different_first_page": section.different_first_page_header_footer,
            }
        )

        result["headers"].append(
            [info for p in section.header.paragraphs if (info := paragraph_info(p))]
        )
        result["footers"].append(
            [info for p in section.footer.paragraphs if (info := paragraph_info(p))]
        )

    for paragraph in doc.paragraphs:
        info = paragraph_info(paragraph)
        if info:
            result["paragraphs"].append(info)

    for table_index, table in enumerate(doc.tables):
        rows = []
        for row in table.rows:
            rows.append([cell.text.strip() for cell in row.cells])
        grid = []
        tbl_grid = table._tbl.tblGrid
        if tbl_grid is not None:
            for col in tbl_grid:
                grid.append(col.get(qn("w:w")))
        result["tables"].append(
            {
                "index": table_index,
                "style": table.style.name if table.style else None,
                "rows": rows,
                "grid": grid,
            }
        )

    used_styles = {p.style.name for p in doc.paragraphs if p.style}
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                used_styles.update(p.style.name for p in cell.paragraphs if p.style)
    for style in doc.styles:
        if style.name not in used_styles:
            continue
        font = getattr(style, "font", None)
        result["styles"].append(
            {
                "name": style.name,
                "type": str(style.type),
                "font": font.name if font else None,
                "size_pt": font.size.pt if font and font.size else None,
                "bold": font.bold if font else None,
                "color": str(font.color.rgb) if font and font.color and font.color.rgb else None,
            }
        )

    with zipfile.ZipFile(path) as package:
        for item in package.infolist():
            result["package_parts"].append(
                {
                    "name": item.filename,
                    "size": item.file_size,
                    "sha256": hashlib.sha256(package.read(item.filename)).hexdigest(),
                }
            )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
