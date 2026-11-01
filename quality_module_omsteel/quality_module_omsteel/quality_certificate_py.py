import frappe
from frappe import _


@frappe.whitelist()
def create_quality_certificate(sales_order):

    # إشعار التسليم أصبح اختيارياً: الشهادة تُنشأ قبله
    delivery_notes = frappe.get_all(
        "Delivery Note",
        filters={"against_sales_order": sales_order, "docstatus": 1},
        fields=["name", "posting_date"]
    )

    delivery_note = delivery_notes[0] if delivery_notes else None

    so = frappe.get_doc("Sales Order", sales_order)

    qc = frappe.new_doc("Quality Certificate")

    from frappe.model.naming import make_autoname
    from frappe.utils import now_datetime

    year = now_datetime().year

    qc.quality_m_certificate_no = make_autoname(f"QC-{year}-.####")

    qc.quality_m_customer_name = so.customer
    qc.quality_m_sales_order_no = so.name
    qc.quality_m_certificate_date = frappe.utils.today()

    # تُملأ فقط إذا وُجد إشعار تسليم معتمد
    if delivery_note:
        qc.quality_m_delivery_note_no = delivery_note.name
        qc.quality_m_invoice_date = delivery_note.posting_date

    for item in so.items:
        qc.append("quality_certificate_item_chield", {
            "quality_m_item_code": item.item_code,
            "quality_m_item_name": item.item_name,
            "quality_m_qty": item.qty
        })

    qc.insert(ignore_permissions=True)
    qc.save()

    so.db_set("quality_m_sales_order_no_a_001", qc.name)

    return qc.name
