import csv
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


DEFAULT_EXCEL = Path("/Users/adair/Downloads/2024 Agency Information_250922.xlsx")
DEFAULT_OUTPUT = Path("output/reporter_acronym_agency_worklist.csv")
NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _column_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref)
    if not match:
        return 0
    value = 0
    for char in match.group(1):
        value = value * 26 + ord(char) - 64
    return value - 1


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    value = cell.find("a:v", NS)
    cell_type = cell.attrib.get("t")
    if cell_type == "s":
        return shared_strings[int(value.text)] if value is not None and value.text else ""
    if cell_type == "inlineStr":
        inline = cell.find("a:is", NS)
        return "".join(node.text or "" for node in inline.iter() if node.tag.endswith("}t")) if inline is not None else ""
    return value.text if value is not None and value.text else ""


def _read_rows(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", NS):
                shared_strings.append("".join(node.text or "" for node in item.findall(".//a:t", NS)))

        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        rows = []
        header = []
        for row in sheet.findall("a:sheetData/a:row", NS):
            cells = {}
            for cell in row.findall("a:c", NS):
                cells[_column_index(cell.attrib["r"])] = _cell_value(cell, shared_strings).strip()
            values = [cells.get(index, "") for index in range(max(cells.keys(), default=-1) + 1)]
            if not header:
                header = values
                continue
            rows.append({header[index]: values[index] if index < len(values) else "" for index in range(len(header))})
        return rows


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _configured_names() -> set[str]:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    try:
        from agencies import AGENCIES
    except Exception:
        return set()

    names = set()
    for agency in AGENCIES:
        for key in ("agency", "name", "short"):
            if agency.get(key):
                names.add(_norm(str(agency[key])))
        if agency.get("agency"):
            names.add(_norm(str(agency["agency"]).replace("Metro", "Metropolitan")))
    return names


def build_worklist(excel_path: Path = DEFAULT_EXCEL, output_path: Path = DEFAULT_OUTPUT) -> list[dict[str, str]]:
    configured = _configured_names()
    rows = []
    for row in _read_rows(excel_path):
        acronym = row.get("Reporter Acronym", "").strip()
        if not acronym:
            continue

        display_name = row.get("Doing Business As", "").strip() or row.get("Agency Name", "").strip()
        possible_names = {
            _norm(display_name),
            _norm(row.get("Agency Name", "")),
            _norm(row.get("Doing Business As", "")),
            _norm(acronym),
        }
        status = "configured" if possible_names & configured else "needs_review"
        total_voms = row.get("Total VOMS", "").strip()
        service_pop = row.get("Service Area Pop", "").strip()
        rows.append(
            {
                "status": status,
                "state": row.get("State", "").strip(),
                "reporter_acronym": acronym,
                "display_name": display_name,
                "agency_name": row.get("Agency Name", "").strip(),
                "city": row.get("City", "").strip(),
                "url": row.get("URL", "").strip(),
                "reporter_type": row.get("Reporter Type", "").strip(),
                "reporting_module": row.get("Reporting Module", "").strip(),
                "total_voms": total_voms,
                "service_area_pop": service_pop,
                "uza_name": row.get("UZA Name", "").strip(),
            }
        )

    def sort_key(item: dict[str, str]) -> tuple[str, int, int, str]:
        try:
            voms = int(float(item["total_voms"] or 0))
        except ValueError:
            voms = 0
        try:
            pop = int(float(item["service_area_pop"] or 0))
        except ValueError:
            pop = 0
        return item["state"], -voms, -pop, item["display_name"]

    rows.sort(key=sort_key)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    worklist = build_worklist()
    needs_review = [row for row in worklist if row["status"] == "needs_review"]
    print(f"Reporter-acronym agencies: {len(worklist)}")
    print(f"Needs review: {len(needs_review)}")
    print(f"Wrote {DEFAULT_OUTPUT}")
