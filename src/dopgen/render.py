from __future__ import annotations

from pathlib import Path

from docxtpl import DocxTemplate

from .ru_dates import (
    format_current_date,
    format_date_long_no_suffix,
    format_delivery_month_year,
    format_pay_date,
)
from .ru_numbers import build_price_full, build_tons_full
from .utils import normalize_contract


TEMPLATE_MAP = {
    ("prepayment", "pickup"): Path("templates/prepayment.docx"),
    ("deferment", "pickup"): Path("templates/deferment_pay.docx"),
    ("prepayment", "delivery"): Path("templates/prepayment_delivery.docx"),
    ("deferment", "delivery"): Path("templates/deferment_delivery.docx"),
}

BASIS_MAP = {
    "pickup": "франко-автотранспортное средство Покупателя на складе Поставщика.",
    "delivery": "франко-автотранспортное средство Поставщика на складе Покупателя.",
}


def choose_template(payment_type: str, delivery_type: str) -> Path:
    key = (payment_type, delivery_type)
    if key not in TEMPLATE_MAP:
        raise ValueError(f"Unsupported template combination: {key}")
    return TEMPLATE_MAP[key]


def build_context(collected: dict, catalogs: dict) -> dict[str, str]:
    client = collected["client_data"]
    product_key = collected["product_key"]
    location_key = collected["location_key"]

    context: dict[str, str] = {
        "dop_num": collected["dop_num"],
        "contract": normalize_contract(client.get("contract", "")),
        "current_date": format_current_date(collected["current_date"]),
        "company_name": client.get("company_name", ""),
        "director_position": client.get("director_position", ""),
        "director_fio": client.get("director_fio", ""),
        "delivery_month_year": format_delivery_month_year(
            collected["delivery_date"], collected["delivery_type"]
        ),
        "product_name": catalogs["products"][product_key],
        "tons_full": build_tons_full(collected["tons"]),
        "price_full": build_price_full(collected["price"]),
        "basis_full": BASIS_MAP[collected["delivery_type"]],
        "location_full": catalogs["locations"][location_key],
        "pay_date": format_pay_date(collected["pay_date"]),
        "initials": client.get("initials", ""),
    }

    if collected["delivery_type"] == "delivery":
        context["unload_address"] = collected["unload_address"]

    return context


def build_output_filename(collected: dict) -> str:
    date_long = format_date_long_no_suffix(collected["current_date"])
    return (
        f"{date_long}_Доп_соглашение_№{collected['dop_num']}_"
        f"{collected['product_key']}_{collected['company_key']}.docx"
    )


def render_docx(template_path: Path, context: dict, output_path: Path) -> None:
    tpl = DocxTemplate(str(template_path))
    tpl.render(context)
    tpl.save(str(output_path))
