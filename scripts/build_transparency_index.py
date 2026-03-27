#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List


BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
DATA_DIR = BASE_DIR / "data"
SUMMARY_PATH = DATA_DIR / "transparency_summary.json"
SEARCH_INDEX_PATH = DATA_DIR / "search_index.json"
CONCEPT_INDEX_PATH = DATA_DIR / "concept_index.json"
CONCEPTS_DIR = DATA_DIR / "concepts"
CONCEPT_MANIFEST_PATH = CONCEPTS_DIR / "manifest.json"
LEGACY_INDEX_PATH = DATA_DIR / "transparency_index.json"
PROFILES_DIR = DATA_DIR / "profiles"
MAX_ASSET_FILE_SIZE = 24 * 1024 * 1024


def parse_amount(value: str) -> float:
    if value is None:
        return 0.0
    raw = value.strip()
    if not raw:
        return 0.0
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            candidate = raw.replace(".", "").replace(",", ".")
        else:
            candidate = raw.replace(",", "")
    elif "," in raw:
        candidate = raw.replace(".", "").replace(",", ".")
    else:
        candidate = raw
    try:
        parsed = float(candidate)
        if raw.isdigit() and parsed >= 10_000_000:
            return parsed / 1_000_000
        return parsed
    except ValueError:
        return 0.0


def parse_year(text: str) -> int | None:
    match = re.search(r"(20\d{2})", text or "")
    return int(match.group(1)) if match else None


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def normalize_row(row: Dict[str, str]) -> Dict[str, str]:
    return {key: normalize_text(value) for key, value in row.items() if normalize_text(value)}


def normalize_department_name(value: str) -> str:
    normalized = normalize_text(value)
    if not normalized:
        return ""
    normalized = re.sub(r"^\d+\s*-\s*", "", normalized)
    normalized = re.sub(r"^\d+\s+", "", normalized)
    return normalized.strip() or normalize_text(value)


def ascii_signature(value: str) -> str:
    normalized = normalize_text(value).upper()
    normalized = unicodedata.normalize("NFKD", normalized).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^A-Z]+", " ", normalized)
    normalized = normalized.replace("AO ", "ANO ")
    normalized = re.sub(r"\bA O\b", "ANO", normalized)
    normalized = "".join(char for char in normalized if char not in "AEIOU ")
    return normalized.strip()


def grant_family_signature(value: str) -> str:
    normalized = normalize_text(value).upper()
    normalized = unicodedata.normalize("NFKD", normalized).encode("ascii", "ignore").decode("ascii")
    replacements = [
        (r"\bBEQUES\b|\bBECAS\b", "BECAS"),
        (r"\bCURS\b|\bCURSO\b", "CURSO"),
        (r"\bPRESTACIONS\b|\bPRESTACIONES\b", "PRESTACIONES"),
        (r"\bECONOMIQUES\b|\bECONOMICAS\b", "ECONOMICAS"),
        (r"\bSUBVENCIO\b|\bSUBVENCION\b|\bSUBVENCIONS\b|\bSUBVENCIONES\b", "SUBVENCIONES"),
        (r"\bPROPIETARIS\b|\bPROPIETARIOS\b", "PROPIETARIOS"),
        (r"\bHABITATGES\b|\bHABITATGE\b|\bVIVIENDAS\b|\bVIVIENDA\b", "VIVIENDAS"),
        (r"\bLLOGUER\b|\bALQUILER\b", "ALQUILER"),
        (r"\bJOVES\b|\bJOVENES\b", "JOVENES"),
        (r"\bARRENDATARIES\b|\bARRENDATARIS\b|\bARRENDATARIAS\b|\bARRENDATARIOS\b", "ARRENDATARIOS"),
        (r"\bREHABILITACIO\b|\bREHABILITACION\b", "REHABILITACION"),
        (r"\bLLIBRES\b|\bLIBROS\b", "LIBROS"),
        (r"\bMUSICA\b|\bMUSICA\b", "MUSICA"),
        (r"\bAJUDES\b|\bAYUDAS\b", "AYUDAS"),
        (r"\bCONVOCATORIA\b|\bCONVOCATORIA\b|\bCONVOCATORIA\b", "CONVOCATORIA"),
        (r"\bEXERCICI\b|\bEJERCICIO\b", "EJERCICIO"),
    ]
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized)
    normalized = re.sub(r"\b[IVXLCDM]+\b", " ", normalized)
    normalized = re.sub(r"\b\d+[A-Z]*\b", " ", normalized)
    normalized = re.sub(r"[^A-Z]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return ascii_signature(normalized)


def parse_grant_amount(value: str) -> float:
    raw = normalize_text(value)
    if not raw:
        return 0.0
    if "," in raw or "." in raw:
        return parse_amount(raw)
    if raw.isdigit():
        parsed = int(raw)
        while parsed >= 1_000_000:
            parsed //= 100
        return float(parsed)
    return parse_amount(raw)


def grant_amount_signature(value: str) -> str:
    raw = normalize_text(value)
    if raw.isdigit():
        return raw.lstrip("0").rstrip("0") or "0"
    parsed = parse_grant_amount(raw)
    return f"{parsed:.2f}".rstrip("0").rstrip(".")


def best_grant_row(rows: List[Dict[str, str]]) -> Dict[str, str]:
    def quality(row: Dict[str, str]) -> tuple:
        title = row.get("TITOL", "")
        return (
            -title.count("?"),
            -title.count("Ã"),
            -title.count("�"),
            len(normalize_text(title)),
        )

    return max(rows, key=quality)


def normalize_grant_amount(row: Dict[str, str], source_name: str) -> float:
    amount = parse_grant_amount(row.get("IMPORT", "0"))
    raw_amount = normalize_text(row.get("IMPORT", ""))
    title = normalize_text(row.get("TITOL", "")).upper()
    beneficiary = normalize_text(row.get("BENEFICIARI", "")).upper()

    # The historical "fins-el-2020" grants file mixes several scholarship rows
    # where amounts are exported as cents without a decimal separator.
    if (
        source_name == "subvencions__concessions-de-subvencions-i-ajuts-minhap-fins-el-2020.csv"
        and beneficiary == "PERSONA FÍSICA".upper()
        and "CONVOCATÒRIA BEQUES PEL CURS 2020/21" in title
    ):
        return amount / 100

    persona_keywords = (
        "PRESTACIONS ECON",
        "PRESTACIONES ECON",
        "BEQUES",
        "BECAS",
        "LLIBRES DE TEXT",
        "LIBROS DE TEXTO",
        "ALQUILER",
        "LLOGUER",
        "ALQUILER SOCIAL",
        "LLOGUER SOCIAL",
        "VIVIENDA DE ALQUILER",
        "HABITATGE DE LLOGUER",
        "ARRENDATARI",
        "IBI",
        "RESIDUOS MUNICIPALES",
        "RESIDUS MUNICIPALS",
        "DEPORTISTAS",
        "DEPORTISTA",
        "PREMIS DOLORS VIVES",
        "PREMIOS DOLORS VIVES",
        "ESCUELA DE MÚSICA",
        "ESCOLA MUNICIPAL DE MÚSICA",
        "JOVENES EMPRENDEDORES",
        "JOVES EMPRENEDORS",
        "ACTIVIDAD EMPRESARIAL",
        "ACTIVITAT EMPRESARIAL",
        "NUEVAS EMPRESAS",
        "NOVES EMPRESES",
        "CASCO ANTIGUO",
        "REHABILITACIÓN DE EDIFICIOS",
        "REHABILITACIO D EDIFICIS",
    )
    if beneficiary == "PERSONA FÍSICA".upper() and raw_amount.isdigit() and amount >= 1000:
        if any(keyword in title for keyword in persona_keywords):
            return amount / 100

    if beneficiary == "G17125832 FONS CATALÀ DE COOPERACIÓ AL DESENVOLUPAMENT" and raw_amount.isdigit():
        while amount >= 20_000:
            amount /= 10
        return amount

    if beneficiary == "G43068634 AAEET" and raw_amount.isdigit():
        while amount >= 20_000:
            amount /= 10
        return amount

    if beneficiary == "Q4373004C CAMBRA OFICIAL DE COMERÇ I INDÚSTRIA DE VALLS" and raw_amount.isdigit():
        if "VALLS OCASI" in title or "VEHICLE USAT" in title:
            while amount >= 5_000:
                amount /= 10
            return amount
        while amount >= 20_000:
            amount /= 10
        return amount

    return amount


def build_grant_reference_maps() -> tuple[Dict[tuple[str, str], float], Dict[tuple[str, str], float]]:
    exact_references: Dict[tuple[str, str], float] = {}
    family_references: Dict[tuple[str, str], float] = {}
    for path in sorted(RAW_DIR.glob("subvencions__*.csv")):
        source_name = path.name
        for row in read_csv(path):
            beneficiary = normalize_text(row.get("BENEFICIARI", ""))
            exact_signature = ascii_signature(row.get("TITOL", ""))
            family_signature = grant_family_signature(row.get("TITOL", ""))
            if not beneficiary or not exact_signature:
                continue
            amount = normalize_grant_amount(row, source_name)
            if amount <= 0:
                continue
            exact_key = (beneficiary, exact_signature)
            previous = exact_references.get(exact_key)
            if previous is None or amount < previous:
                exact_references[exact_key] = amount
            if family_signature:
                family_key = (beneficiary, family_signature)
                previous = family_references.get(family_key)
                if previous is None or amount < previous:
                    family_references[family_key] = amount
    return exact_references, family_references


def adjust_grant_amount_with_reference(
    row: Dict[str, str],
    source_name: str,
    exact_references: Dict[tuple[str, str], float],
    family_references: Dict[tuple[str, str], float],
) -> float:
    amount = normalize_grant_amount(row, source_name)
    raw_amount = normalize_text(row.get("IMPORT", ""))
    if not raw_amount.isdigit():
        return amount

    beneficiary = normalize_text(row.get("BENEFICIARI", ""))
    title_signature = ascii_signature(row.get("TITOL", ""))
    family_signature = grant_family_signature(row.get("TITOL", ""))
    reference = exact_references.get((beneficiary, title_signature)) or family_references.get((beneficiary, family_signature))
    if not reference or reference <= 0 or amount <= 0:
        if beneficiary == "G17125832 FONS CATALÀ DE COOPERACIÓ AL DESENVOLUPAMENT" and amount >= 100_000:
            while amount >= 20_000:
                amount /= 10
        return amount

    adjusted = amount
    while adjusted >= reference * 9.5:
        adjusted /= 10
    return adjusted


def profile_id(kind: str, name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", normalize_text(name).lower()).strip("-")
    return f"{kind}:{slug or 'sense-identificar'}"


def profile_filename(pid: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "-", pid.lower()).strip("-")
    return f"{safe}.json"


def top_items(values: Iterable[Dict], limit: int = 15, sort_field: str = "amount") -> List[Dict]:
    return sorted(values, key=lambda item: item.get(sort_field, 0), reverse=True)[:limit]


def read_csv(path: Path) -> Iterable[dict]:
    with path.open(encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def ensure_profile(profiles: Dict[str, Dict], kind: str, name: str, **extra: str) -> Dict:
    normalized_name = normalize_text(name) or "Sense identificar"
    pid = profile_id(kind, normalized_name)
    profile = profiles.setdefault(
        pid,
        {
            "id": pid,
            "file": profile_filename(pid),
            "kind": kind,
            "name": normalized_name,
            "cif": "",
            "city": "",
            "province": "",
            "organization": "",
            "record_count": 0,
            "visible_record_count": 0,
            "total_amount": 0.0,
            "years": {},
            "sources": defaultdict(lambda: {"amount": 0.0, "count": 0}),
            "records": [],
        },
    )
    for key, value in extra.items():
        if value and not profile.get(key):
            profile[key] = value
    return profile


def add_record(profile: Dict, source: str, year: int, amount: float, record: Dict, *, include_in_totals: bool = True) -> None:
    profile["record_count"] += 1
    if include_in_totals:
        profile["visible_record_count"] += 1
        profile["total_amount"] += amount
        year_bucket = profile["years"].setdefault(str(year), {"amount": 0.0, "count": 0})
        year_bucket["amount"] += amount
        year_bucket["count"] += 1
        profile["sources"][source]["amount"] += amount
        profile["sources"][source]["count"] += 1
    profile["records"].append(record)


def prepare_output_dirs() -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    for existing in PROFILES_DIR.glob("*.json"):
        existing.unlink()
    CONCEPTS_DIR.mkdir(parents=True, exist_ok=True)
    for existing in CONCEPTS_DIR.glob("*.json"):
        existing.unlink()


def profile_index_entry(profile: Dict) -> Dict:
    sources = dict(profile["sources"])
    invoices = sources.get("invoices", {"amount": 0.0, "count": 0})
    supplier_spend = sources.get("supplier_spend", {"amount": 0.0, "count": 0})
    grants = sources.get("grants", {"amount": 0.0, "count": 0})
    budget = sources.get("budget", {"amount": 0.0, "count": 0})

    if invoices.get("count"):
        display_amount = invoices["amount"]
        display_count = invoices["count"]
        display_source = "invoices"
    elif supplier_spend.get("count"):
        display_amount = supplier_spend["amount"]
        display_count = supplier_spend["count"]
        display_source = "supplier_spend"
    elif grants.get("count"):
        display_amount = grants["amount"]
        display_count = grants["count"]
        display_source = "grants"
    else:
        display_amount = budget.get("amount", 0.0)
        display_count = budget.get("count", 0)
        display_source = "budget"

    return {
        "id": profile["id"],
        "file": profile["file"],
        "kind": profile["kind"],
        "name": profile["name"],
        "cif": profile["cif"],
        "city": profile["city"],
        "province": profile["province"],
        "organization": profile["organization"],
        "record_count": profile["record_count"],
        "visible_record_count": profile["visible_record_count"],
        "total_amount": profile["total_amount"],
        "display_amount": display_amount,
        "display_count": display_count,
        "display_source": display_source,
        "years": profile["years"],
        "sources": sources,
    }


def profile_detail_entry(profile: Dict) -> Dict:
    entry = profile_index_entry(profile)
    entry["records"] = sorted(
        profile["records"],
        key=lambda record: (record.get("year", 0), record.get("date") or "", record.get("amount", 0.0)),
        reverse=True,
    )
    return entry


def chunk_records(records: List[Dict], max_size: int = MAX_ASSET_FILE_SIZE, *, overhead: int = 512) -> List[List[Dict]]:
    chunks: List[List[Dict]] = []
    current_chunk: List[Dict] = []
    current_size = overhead

    for record in records:
        encoded_size = len(json.dumps(record, ensure_ascii=False).encode("utf-8")) + 2
        if current_chunk and current_size + encoded_size > max_size:
            chunks.append(current_chunk)
            current_chunk = []
            current_size = overhead
        current_chunk.append(record)
        current_size += encoded_size

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def write_profile_detail(detail: Dict) -> None:
    destination = PROFILES_DIR / detail["file"]
    payload = json.dumps(detail, ensure_ascii=False)

    if len(payload.encode("utf-8")) <= MAX_ASSET_FILE_SIZE:
        destination.write_text(payload, encoding="utf-8")
        return

    year_files = {}
    records_by_year = defaultdict(list)
    for record in detail["records"]:
        records_by_year[str(record.get("year", "sense-any"))].append(record)

    base_name = Path(detail["file"]).stem
    for year, records in sorted(records_by_year.items(), reverse=True):
        shards = chunk_records(records)
        year_files[year] = []
        for index, shard_records in enumerate(shards, start=1):
            suffix = f"-part-{index}" if len(shards) > 1 else ""
            shard_name = f"{base_name}-year-{year}{suffix}.json"
            shard_payload = {
                "id": detail["id"],
                "year": year,
                "part": index,
                "parts": len(shards),
                "records": shard_records,
            }
            (PROFILES_DIR / shard_name).write_text(json.dumps(shard_payload, ensure_ascii=False), encoding="utf-8")
            year_files[year].append(shard_name)

    manifest = dict(detail)
    manifest["records"] = []
    manifest["sharded"] = True
    manifest["year_files"] = year_files
    destination.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def build() -> dict:
    invoices_by_year = defaultdict(lambda: {"amount": 0.0, "count": 0})
    invoice_suppliers_by_year = defaultdict(
        lambda: defaultdict(lambda: {"name": "", "amount": 0.0, "count": 0, "cif": "", "city": "", "province": ""})
    )
    supplier_spend_by_year = defaultdict(
        lambda: defaultdict(lambda: {"name": "", "amount": 0.0, "count": 0, "cif": "", "city": "", "province": ""})
    )
    department_spend_by_year = defaultdict(lambda: defaultdict(lambda: {"name": "", "amount": 0.0, "count": 0}))
    contracts_by_year = defaultdict(lambda: {"amount": 0.0, "count": 0})
    contract_suppliers_by_year = defaultdict(
        lambda: defaultdict(lambda: {"name": "", "amount": 0.0, "count": 0, "cif": "", "department": "", "type": ""})
    )
    contract_departments_by_year = defaultdict(lambda: defaultdict(lambda: {"name": "", "amount": 0.0, "count": 0}))
    grants_by_year = defaultdict(lambda: {"amount": 0.0, "count": 0})
    grant_beneficiaries_by_year = defaultdict(lambda: defaultdict(lambda: {"name": "", "amount": 0.0, "count": 0}))
    budget_by_year = defaultdict(lambda: {"initial": 0.0, "final": 0.0, "available": 0.0, "count": 0})
    budget_departments_by_year = defaultdict(
        lambda: defaultdict(lambda: {"name": "", "initial": 0.0, "final": 0.0, "available": 0.0, "count": 0})
    )

    profiles: Dict[str, Dict] = {}
    concept_records: List[Dict] = []
    exact_grant_references, family_grant_references = build_grant_reference_maps()

    for path in sorted(RAW_DIR.glob("*.csv")):
        name = path.name
        year = parse_year(name)
        if year is None:
            continue

        if name.startswith("registre-factures__"):
            for row in read_csv(path):
                amount = parse_amount(row.get("IMPORT_TOTAL", "0"))
                supplier = normalize_text(row.get("PROVEIDOR", ""))
                department = normalize_department_name(row.get("DEPARTAMENT", ""))
                organization = normalize_text(row.get("NOM_ENS", ""))
                status = normalize_text(row.get("ESTAT_FACTURA", ""))
                is_cancelled = "cancel" in status.lower()

                if not is_cancelled:
                    invoices_by_year[year]["amount"] += amount
                    invoices_by_year[year]["count"] += 1

                record = {
                    "source": "invoices",
                    "source_label": "Factures",
                    "year": year,
                    "amount": amount,
                    "date": row.get("DATA_FACTURA") or row.get("DATA_REGISTRE") or "",
                    "organization": organization,
                    "department": department,
                    "counterparty": supplier,
                    "title": normalize_text(row.get("DESCRIPCIO", "")),
                    "reference": row.get("REFERENCIA_FACTURA") or row.get("REFERENCIA") or "",
                    "status": status,
                    "is_cancelled": is_cancelled,
                    "source_file": name,
                    "raw_fields": normalize_row(row),
                }
                concept_records.append(
                    {
                        "source": record["source"],
                        "source_label": record["source_label"],
                        "year": record["year"],
                        "amount": record["amount"],
                        "date": record["date"],
                        "organization": record["organization"],
                        "department": record["department"],
                        "counterparty": record["counterparty"],
                        "title": record["title"],
                        "reference": record["reference"],
                        "status": record["status"],
                        "is_cancelled": record["is_cancelled"],
                        "source_file": record["source_file"],
                        "raw_fields": record["raw_fields"],
                    }
                )

                if supplier and not is_cancelled:
                    item = invoice_suppliers_by_year[year][supplier]
                    item["name"] = supplier
                    item["amount"] += amount
                    item["count"] += 1
                if supplier:
                    add_record(
                        ensure_profile(profiles, "entity", supplier, organization=organization),
                        "invoices",
                        year,
                        amount,
                        record,
                        include_in_totals=not is_cancelled,
                    )

                if department and not is_cancelled:
                    item = department_spend_by_year[year][department]
                    item["name"] = department
                    item["amount"] += amount
                    item["count"] += 1
                if department:
                    add_record(
                        ensure_profile(profiles, "department", department, organization=organization),
                        "invoices",
                        year,
                        amount,
                        record,
                        include_in_totals=not is_cancelled,
                    )

                if organization:
                    add_record(
                        ensure_profile(profiles, "organization", organization),
                        "invoices",
                        year,
                        amount,
                        record,
                        include_in_totals=not is_cancelled,
                    )

        elif name.startswith("proveidors__despesa-per-prove-dor-"):
            for row in read_csv(path):
                amount = parse_amount(row.get("IMPORT_FACTURAT", "0"))
                supplier = normalize_text(row.get("PROVEIDOR", ""))
                organization = normalize_text(row.get("NOM_ENS", ""))
                if not supplier:
                    continue
                item = supplier_spend_by_year[year][supplier]
                item["name"] = supplier
                item["amount"] = max(item["amount"], amount)
                item["count"] += 1
                item["cif"] = row.get("CIF", "") or item["cif"]
                item["city"] = row.get("POBL_ENT", "") or item["city"]
                item["province"] = row.get("PROV_ENT", "") or item["province"]

                record = {
                    "source": "supplier_spend",
                    "source_label": "Despesa per proveïdor",
                    "year": year,
                    "amount": amount,
                    "date": f"{year}-12-31",
                    "organization": organization,
                    "department": "",
                    "counterparty": supplier,
                    "title": f"Import total facturat pel proveïdor a {year}",
                    "reference": row.get("CIF", "") or "",
                    "status": "",
                    "is_cancelled": False,
                    "source_file": name,
                    "raw_fields": normalize_row(row),
                }
                concept_records.append(
                    {
                        "source": record["source"],
                        "source_label": record["source_label"],
                        "year": record["year"],
                        "amount": record["amount"],
                        "date": record["date"],
                        "organization": record["organization"],
                        "department": record["department"],
                        "counterparty": record["counterparty"],
                        "title": record["title"],
                        "reference": record["reference"],
                        "status": record["status"],
                        "is_cancelled": record["is_cancelled"],
                        "source_file": record["source_file"],
                        "raw_fields": record["raw_fields"],
                    }
                )
                add_record(
                    ensure_profile(
                        profiles,
                        "entity",
                        supplier,
                        cif=row.get("CIF", ""),
                        city=row.get("POBL_ENT", ""),
                        province=row.get("PROV_ENT", ""),
                        organization=organization,
                    ),
                    "supplier_spend",
                    year,
                    amount,
                    record,
                )
                if organization:
                    add_record(ensure_profile(profiles, "organization", organization), "supplier_spend", year, amount, record)

        elif name.startswith("contractacio__contractes-menors-"):
            for row in read_csv(path):
                amount = parse_amount(row.get("IMPORT", "0"))
                supplier = normalize_text(row.get("NOM_ADJ", ""))
                department = normalize_department_name(row.get("DEPARTAMENT", ""))
                contract_type = normalize_text(row.get("TIPUS", ""))
                organization = normalize_text(row.get("NOM_ENS", ""))

                contracts_by_year[year]["amount"] += amount
                contracts_by_year[year]["count"] += 1

                record = {
                    "source": "contracts",
                    "source_label": "Contractes menors",
                    "year": year,
                    "amount": amount,
                    "date": row.get("DATA_ADJUDICACIO") or "",
                    "organization": organization,
                    "department": department,
                    "counterparty": supplier,
                    "title": normalize_text(row.get("DESCRIPCIO", "")),
                    "reference": row.get("EXPEDIENT", "") or "",
                    "status": contract_type,
                    "is_cancelled": False,
                    "source_file": name,
                    "raw_fields": normalize_row(row),
                }
                concept_records.append(
                    {
                        "source": record["source"],
                        "source_label": record["source_label"],
                        "year": record["year"],
                        "amount": record["amount"],
                        "date": record["date"],
                        "organization": record["organization"],
                        "department": record["department"],
                        "counterparty": record["counterparty"],
                        "title": record["title"],
                        "reference": record["reference"],
                        "status": record["status"],
                        "is_cancelled": record["is_cancelled"],
                        "source_file": record["source_file"],
                        "raw_fields": record["raw_fields"],
                    }
                )

                if supplier:
                    item = contract_suppliers_by_year[year][supplier]
                    item["name"] = supplier
                    item["amount"] += amount
                    item["count"] += 1
                    item["cif"] = row.get("CIF_ADJ", "") or item["cif"]
                    item["department"] = department or item["department"]
                    item["type"] = contract_type or item["type"]
                    add_record(
                        ensure_profile(
                            profiles,
                            "entity",
                            supplier,
                            cif=row.get("CIF_ADJ", ""),
                            city=row.get("POBLACIO_ADJ", ""),
                            province=row.get("PROVINCIA_ADJ", ""),
                            organization=organization,
                        ),
                        "contracts",
                        year,
                        amount,
                        record,
                    )

                if department:
                    item = contract_departments_by_year[year][department]
                    item["name"] = department
                    item["amount"] += amount
                    item["count"] += 1
                    add_record(ensure_profile(profiles, "department", department, organization=organization), "contracts", year, amount, record)

                if organization:
                    add_record(ensure_profile(profiles, "organization", organization), "contracts", year, amount, record)

        elif name.startswith("subvencions__"):
            grant_groups = defaultdict(list)
            for row in read_csv(path):
                beneficiary = normalize_text(row.get("BENEFICIARI", ""))
                organization = normalize_text(row.get("NOM_ENS", ""))
                normalized_amount = adjust_grant_amount_with_reference(
                    row,
                    name,
                    exact_grant_references,
                    family_grant_references,
                )
                signature = (
                    normalize_text((row.get("DATA_DE_CONCESSIO") or "")[:10]),
                    beneficiary,
                    organization,
                    ascii_signature(row.get("TITOL", "")),
                    f"{normalized_amount:.2f}",
                )
                grant_groups[signature].append(row)

            for rows in grant_groups.values():
                row = best_grant_row(rows)
                amount = min(
                    adjust_grant_amount_with_reference(
                        candidate,
                        name,
                        exact_grant_references,
                        family_grant_references,
                    )
                    for candidate in rows
                )
                beneficiary = normalize_text(row.get("BENEFICIARI", ""))
                organization = normalize_text(row.get("NOM_ENS", ""))

                grants_by_year[year]["amount"] += amount
                grants_by_year[year]["count"] += 1

                record = {
                    "source": "grants",
                    "source_label": "Ajuts i subvencions",
                    "year": year,
                    "amount": amount,
                    "date": row.get("DATA_DE_CONCESSIO") or "",
                    "organization": organization,
                    "department": "",
                    "counterparty": beneficiary,
                    "title": normalize_text(row.get("TITOL", "")),
                    "reference": row.get("CLAU", "") or "",
                    "status": normalize_text(row.get("INSTRUMENT", "")),
                    "is_cancelled": False,
                    "source_file": name,
                    "raw_fields": normalize_row(row),
                }
                concept_records.append(
                    {
                        "source": record["source"],
                        "source_label": record["source_label"],
                        "year": record["year"],
                        "amount": record["amount"],
                        "date": record["date"],
                        "organization": record["organization"],
                        "department": record["department"],
                        "counterparty": record["counterparty"],
                        "title": record["title"],
                        "reference": record["reference"],
                        "status": record["status"],
                        "is_cancelled": record["is_cancelled"],
                        "source_file": record["source_file"],
                        "raw_fields": record["raw_fields"],
                    }
                )

                if beneficiary:
                    item = grant_beneficiaries_by_year[year][beneficiary]
                    item["name"] = beneficiary
                    item["amount"] += amount
                    item["count"] += 1
                    add_record(ensure_profile(profiles, "entity", beneficiary, organization=organization), "grants", year, amount, record)

                if organization:
                    add_record(ensure_profile(profiles, "organization", organization), "grants", year, amount, record)

        elif name.startswith("pressupostos__estat-partides-pressupost-ries-"):
            for row in read_csv(path):
                initial = parse_amount(row.get("PRV_INI", "0"))
                final = parse_amount(row.get("PRV_DEF", "0"))
                available = parse_amount(row.get("DISPONIBLE", "0"))
                department = normalize_department_name(row.get("COD_ORGANIC", ""))
                description = normalize_text(row.get("DES_PARTIDA", ""))
                organization = normalize_text(row.get("NOM_ENS", ""))

                budget_by_year[year]["initial"] += initial
                budget_by_year[year]["final"] += final
                budget_by_year[year]["available"] += available
                budget_by_year[year]["count"] += 1

                record = {
                    "source": "budget",
                    "source_label": "Pressupost",
                    "year": year,
                    "amount": final,
                    "date": f"{year}-01-01",
                    "organization": organization,
                    "department": department,
                    "counterparty": "",
                    "title": description,
                    "reference": f"{row.get('COD_ORGANIC', '')}/{row.get('COD_FUNCIONAL', '')}/{row.get('COD_ECONOMIC', '')}",
                    "status": f"Inicial {initial:.2f} · Disponible {available:.2f}",
                    "is_cancelled": False,
                    "source_file": name,
                    "raw_fields": normalize_row(row),
                }
                concept_records.append(
                    {
                        "source": record["source"],
                        "source_label": record["source_label"],
                        "year": record["year"],
                        "amount": record["amount"],
                        "date": record["date"],
                        "organization": record["organization"],
                        "department": record["department"],
                        "counterparty": record["counterparty"],
                        "title": record["title"],
                        "reference": record["reference"],
                        "status": record["status"],
                        "is_cancelled": record["is_cancelled"],
                        "source_file": record["source_file"],
                        "raw_fields": record["raw_fields"],
                    }
                )

                if department:
                    label = f"{department} · {description}" if description else department
                    item = budget_departments_by_year[year][label]
                    item["name"] = label
                    item["initial"] += initial
                    item["final"] += final
                    item["available"] += available
                    item["count"] += 1
                    add_record(ensure_profile(profiles, "department", department, organization=organization), "budget", year, final, record)

                if organization:
                    add_record(ensure_profile(profiles, "organization", organization), "budget", year, final, record)

    years = sorted(set(invoices_by_year) | set(contracts_by_year) | set(grants_by_year) | set(budget_by_year), reverse=True)
    year_summaries = []
    for year in years:
        year_summaries.append(
            {
                "year": year,
                "invoices": {
                    **invoices_by_year[year],
                    "top_suppliers": top_items(invoice_suppliers_by_year[year].values()),
                    "top_supplier_spend": top_items(supplier_spend_by_year[year].values()),
                    "top_departments": top_items(department_spend_by_year[year].values()),
                },
                "contracts": {
                    **contracts_by_year[year],
                    "top_suppliers": top_items(contract_suppliers_by_year[year].values()),
                    "top_departments": top_items(contract_departments_by_year[year].values()),
                },
                "grants": {
                    **grants_by_year[year],
                    "top_beneficiaries": top_items(grant_beneficiaries_by_year[year].values()),
                },
                "budget": {
                    **budget_by_year[year],
                    "top_lines": top_items(budget_departments_by_year[year].values(), sort_field="final"),
                },
            }
        )

    all_profiles = sorted(profiles.values(), key=lambda item: (item["total_amount"], item["visible_record_count"]), reverse=True)
    overview = {
        "years": years,
        "latest_year": year_summaries[0]["year"] if year_summaries else None,
        "profile_count": len(all_profiles),
    }

    prepare_output_dirs()
    search_profiles = []
    for profile in all_profiles:
        profile["sources"] = dict(profile["sources"])
        profile["years"] = dict(sorted(profile["years"].items(), reverse=True))
        detail = profile_detail_entry(profile)
        write_profile_detail(detail)
        search_profiles.append(profile_index_entry(profile))

    summary_payload = {"overview": overview, "years": year_summaries}
    search_payload = {"overview": overview, "profiles": search_profiles}
    concepts_by_year = defaultdict(list)
    for record in concept_records:
        concepts_by_year[str(record["year"])].append(record)

    concept_manifest = {"overview": overview, "years": {}}

    SUMMARY_PATH.write_text(json.dumps(summary_payload, ensure_ascii=False), encoding="utf-8")
    SEARCH_INDEX_PATH.write_text(json.dumps(search_payload, ensure_ascii=False), encoding="utf-8")
    for year, records in concepts_by_year.items():
        shards = chunk_records(records)
        files = []
        for index, shard_records in enumerate(shards, start=1):
            suffix = f"_part_{index}" if len(shards) > 1 else ""
            file_name = f"concept_index_{year}{suffix}.json"
            (CONCEPTS_DIR / file_name).write_text(
                json.dumps(
                    {"year": int(year), "part": index, "parts": len(shards), "records": shard_records},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            files.append(file_name)
        concept_manifest["years"][year] = {"files": files, "count": len(records)}
    CONCEPT_MANIFEST_PATH.write_text(json.dumps(concept_manifest, ensure_ascii=False), encoding="utf-8")
    CONCEPT_INDEX_PATH.write_text(
        json.dumps({"notice": "Usa data/concepts/manifest.json i els fitxers anuals."}, ensure_ascii=False),
        encoding="utf-8",
    )
    LEGACY_INDEX_PATH.write_text(
        json.dumps(
            {
                "notice": "Aquest fitxer ja no conté totes les dades. Usa transparency_summary.json, search_index.json, data/profiles/*.json i data/concepts/*.json.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {
        "summary_path": str(SUMMARY_PATH),
        "search_index_path": str(SEARCH_INDEX_PATH),
        "concept_index_path": str(CONCEPT_MANIFEST_PATH),
        "profile_count": len(search_profiles),
    }


def main() -> int:
    payload = build()
    print(f"Resum generat a {payload['summary_path']}")
    print(f"Index de cerca generat a {payload['search_index_path']}")
    print(f"Index de conceptes generat a {payload['concept_index_path']}")
    print(f"Perfils generats: {payload['profile_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
