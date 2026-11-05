import re

import frappe
from frappe import _

# أسماء العناصر كما تظهر في رأس الجدول بالشهادة
ELSET = {"C", "Si", "Mn", "P", "S", "Als", "Alt", "Ni", "Cu", "Mo",
         "V", "Nb", "Ti", "N", "Cr", "Ceq"}

# ربط اسم العنصر في الشهادة باسم الحقل في MTC Coil
FMAP = {
    "C": "c_carbon", "Si": "si_silicon", "Mn": "mn_manganese",
    "P": "p_phosphorus", "S": "s_sulfur", "Als": "als", "Alt": "alt",
    "Ni": "ni_nickel", "Cu": "cu_copper", "Mo": "mo_molybdenum",
    "V": "v_vanadium", "Nb": "nb_niobium", "Ti": "ti_titanium",
    "N": "n_nitrogen", "Cr": "cr_chromium", "Ceq": "ceq",
}

# صف البيانات: تسلسل + Pack No + Heat No + الوزن + العدد + (C.C.T + قيم الكيمياء)
ROW_RE = re.compile(
    r"^\s*\d+\s+([A-Z0-9]*[A-Z][A-Z0-9]*)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d[\d\s]*\d|\d)\s*$"
)


def _parse_page(text):
    """يُرجع قائمة لفائف من نص صفحة واحدة. يتعامل مع اختلاف عدد العناصر بين الصفحات."""
    grade = re.search(r"Grade\s+([A-Z0-9]+)", text)
    elems, exps = [], []
    for ln in text.splitlines():
        e = [x for x in ln.split() if x in ELSET]
        if len(e) >= 4 and not elems:
            elems = e  # صف أسماء العناصر (ترتيبها وعددها)
        if "T." in ln and re.search(r"10\s*-\d", ln):
            ex = re.findall(r"10\s*(-\d)", ln)
            if len(ex) > len(exps):
                exps = [int(x) for x in ex]  # صف المعاملات الأسّية

    coils = []
    for ln in text.splitlines():
        m = ROW_RE.match(ln.strip())
        if not m:
            continue
        nums = [int(x) for x in m.group(5).split()]
        if len(nums) < 2:
            continue
        chem_vals = nums[1:]  # نتجاوز C.C.T (أول رقم)
        if not (len(elems) == len(exps) == len(chem_vals)):
            continue
        chem = {
            FMAP[elems[j]]: round(chem_vals[j] * (10 ** exps[j]), 6)
            for j in range(len(elems))
        }
        coils.append({
            "pack_no": m.group(1),
            "heat_no": m.group(2),
            "weight_kg": int(m.group(3)),
            "grade": grade.group(1) if grade else None,
            "chem": chem,
        })
    return coils


@frappe.whitelist()
def extract_coils_from_pdf(docname):
    """يقرأ الـ PDF المرفق ويملأ جدول اللفائف تلقائياً."""
    import pdfplumber

    doc = frappe.get_doc("Mill Test Certificate", docname)
    if not doc.mtc_pdf:
        frappe.throw(_("يرجى إرفاق ملف الـ PDF أولاً"))

    file_doc = frappe.get_doc("File", {"file_url": doc.mtc_pdf})
    path = file_doc.get_full_path()

    all_coils = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            all_coils.extend(_parse_page(page.extract_text() or ""))

    if not all_coils:
        frappe.throw(_("تعذّر استخراج أي لفيفة من الملف"))

    doc.set("coils", [])
    total = 0.0
    for c in all_coils:
        row = doc.append("coils", {
            "pack_no": c["pack_no"],
            "heat_no": c["heat_no"],
            "weight_kg": c["weight_kg"],
            "grade": c["grade"] or doc.grade,
            "item_code": doc.get("default_item"),
        })
        for fieldname, value in c["chem"].items():
            row.set(fieldname, value)
        total += c["weight_kg"]

    doc.total_weight = total
    doc.save()
    return {"coils": len(all_coils), "weight": total}
