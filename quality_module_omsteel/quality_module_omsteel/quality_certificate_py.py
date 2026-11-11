import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import now_datetime, today

# ربط حقول الكيمياء: MTC Coil (المصدر) -> Quality Certificate Item (شهادة العميل)
CHEM_MAP = {
    "c_carbon": "quality_m_c__carbon",
    "si_silicon": "quality_m_si__silicon",
    "mn_manganese": "quality_m_mn__manganese",
    "p_phosphorus": "quality_m_p__phosphorus",
    "s_sulfur": "quality_m_s__sulfur",
    "cu_copper": "quality_m_cu__copper",
    "als": "quality_m_al__aluminum",
}

# ربط باقي الحقول: MTC Coil -> Quality Certificate Item
DETAIL_MAP = {
    "heat_no": "quality_m_heat_no",
    "grade": "quality_m_steel_grade",
    "specification": "quality_m_standard",
    "size": "quality_m_size",
    "thickness": "quality_m_thickness",
    "length": "quality_m_length",
    "yield_strength": "quality_m_ys_yield_strength_nmm2",
    "tensile_strength": "quality_m_ts_tensile_strength_nmm2",
    "elongation": "quality_m_el_elongation_",
    "bend_test": "quality_m_bend_test",
}

COIL_FIELDS = list(DETAIL_MAP.keys()) + list(CHEM_MAP.keys())


def _get_item_batches(item):
    """يُرجع [(batch_no, qty)] لصف صنف في أمر البيع.
    يدعم batch_no المباشر و Serial and Batch Bundle (ERPNext 15)."""
    batches = []
    if item.get("batch_no"):
        batches.append((item.get("batch_no"), item.get("qty") or 0))
    elif item.get("serial_and_batch_bundle"):
        entries = frappe.get_all(
            "Serial and Batch Entry",
            filters={"parent": item.get("serial_and_batch_bundle")},
            fields=["batch_no", "qty"],
        )
        for e in entries:
            if e.batch_no:
                batches.append((e.batch_no, abs(e.qty or 0)))
    return batches


def _coil_data(batch_no):
    """يجلب كل تفاصيل الكويل من MTC Coil بمطابقة pack_no = اسم الـ Batch."""
    rows = frappe.get_all(
        "MTC Coil", filters={"pack_no": batch_no}, fields=COIL_FIELDS, limit=1
    )
    return rows[0] if rows else {}


@frappe.whitelist()
def create_quality_certificate(sales_order):
    so = frappe.get_doc("Sales Order", sales_order)

    # إشعار التسليم اختياري
    delivery_notes = frappe.get_all(
        "Delivery Note",
        filters={"against_sales_order": sales_order, "docstatus": 1},
        fields=["name", "posting_date"],
    )
    delivery_note = delivery_notes[0] if delivery_notes else None

    qc = frappe.new_doc("Quality Certificate")

    year = now_datetime().year
    qc.quality_m_certificate_no = make_autoname(f"QC-{year}-.####")
    qc.quality_m_customer_name = so.customer
    qc.quality_m_sales_order_no = so.name
    qc.quality_m_certificate_date = today()

    if delivery_note:
        qc.quality_m_delivery_note_no = delivery_note.name
        qc.quality_m_invoice_date = delivery_note.posting_date

    for item in so.items:
        batches = _get_item_batches(item)

        if not batches:
            # لا يوجد Batch على الصف: صف واحد بالكمية الكاملة دون تفاصيل الكويل
            qc.append("quality_certificate_item_chield", {
                "quality_m_item_code": item.item_code,
                "quality_m_item_name": item.item_name,
                "quality_m_qty": item.qty,
            })
            continue

        # صف لكل Batch (كويل) مع سحب كل تفاصيله تلقائياً من الـ MTC
        for batch_no, qty in batches:
            coil = _coil_data(batch_no)
            row = {
                "quality_m_item_code": item.item_code,
                "quality_m_item_name": item.item_name,
                "quality_m_qty": qty,
                "quality_m_lot_no": batch_no,
            }
            for src, dst in DETAIL_MAP.items():
                row[dst] = coil.get(src)
            for src, dst in CHEM_MAP.items():
                row[dst] = coil.get(src)
            qc.append("quality_certificate_item_chield", row)

    qc.insert(ignore_permissions=True)
    qc.save()

    so.db_set("quality_m_sales_order_no_a_001", qc.name)

    return qc.name
