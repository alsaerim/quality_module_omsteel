import re

import frappe
from frappe import _

# عناصر الكيمياء كما تظهر في رأس جدول الشهادة
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

STD_PREFIX = ("ASTM", "EN", "GB", "JIS", "DIN", "BS")
PACK = r"[A-Z0-9]*[A-Z][A-Z0-9]*"

# صف الكيمياء: تسلسل + Pack No + Heat No + الوزن + العدد + (C.C.T + قيم الكيمياء)
CHEM_ROW = re.compile(
    r"^\s*\d+\s+(" + PACK + r")\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d[\d\s]*\d|\d)\s*$"
)


def _std_grade(text):
    """يستخرج الدرجة والمواصفة (يتعامل مع EN و ASTM)."""
    grade = std = None
    gm = re.search(r"Grade\s+(.+?)\s+车号", text) or re.search(r"Grade\s+([^\n]+)", text)
    if gm:
        val = gm.group(1).strip()
        toks = val.split()
        if toks and toks[0] in STD_PREFIX:
            std = " ".join(toks[:2]).strip()
            grade = toks[1] if len(toks) > 1 else val
        else:
            grade = toks[0] if toks else val
    sm = re.search(r"(EN\s?\d{4,}-\d(?:[:：]\s?\d{4})?)", text)
    if sm and not std:
        std = sm.group(1).replace(" ", "")
    return grade, std


def _parse_mech(text):
    """يستخرج الأبعاد والخواص الميكانيكية لكل كويل من الجدول الثاني.
    يُرجع dict: pack_no -> {thickness, width, length, ys, ts, el, bend}."""
    out = {}
    started = False
    for ln in text.splitlines():
        if re.search(r"\bThick\b", ln):
            started = True
            continue
        if not started:
            continue
        toks = ln.split()
        if len(toks) < 8 or not toks[0].isdigit():
            continue
        if not re.fullmatch(PACK, toks[1]) or not re.fullmatch(r"\d+(?:\.\d+)?", toks[2]):
            continue
        pack = toks[1]
        ys = ts = el = bend = None
        for i in range(5, len(toks) - 2):
            if (re.fullmatch(r"\d+", toks[i]) and re.fullmatch(r"\d+", toks[i + 1])
                    and re.fullmatch(r"\d+\.\d+", toks[i + 2])):
                ys, ts, el = toks[i], toks[i + 1], toks[i + 2]
                bend = toks[i + 3] if i + 3 < len(toks) else None
                break
        out[pack] = {
            "thickness": toks[2], "width": toks[3], "length": toks[4],
            "ys": ys, "ts": ts, "el": el, "bend": bend,
        }
    return out


def _parse_chem(text):
    """يستخرج صفوف الكيمياء (يتعامل مع اختلاف عدد العناصر بين الصفحات)."""
    elems, exps = [], []
    for ln in text.splitlines():
        e = [x for x in ln.split() if x in ELSET]
        if len(e) >= 4 and not elems:
            elems = e
        if "T." in ln and re.search(r"10\s*-\d", ln):
            ex = re.findall(r"10\s*(-\d)", ln)
            if len(ex) > len(exps):
                exps = [int(x) for x in ex]
    coils = []
    for ln in text.splitlines():
        m = CHEM_ROW.match(ln.strip())
        if not m:
            continue
        nums = [int(x) for x in m.group(5).split()]
        if len(nums) < 2:
            continue
        chem_vals = nums[1:]
        if not (len(elems) == len(exps) == len(chem_vals)):
            continue
        chem = {FMAP[elems[j]]: round(chem_vals[j] * (10 ** exps[j]), 6)
                for j in range(len(elems))}
        coils.append({
            "pack_no": m.group(1), "heat_no": m.group(2),
            "weight_kg": int(m.group(3)), "chem": chem,
        })
    return coils


def _parse_page(text):
    """يدمج الكيمياء + الميكانيكا + المواصفة/الدرجة/المصنع لكل كويل."""
    grade, spec = _std_grade(text)
    man = re.search(r"Manufacturer[:：]\s*(.+)", text)
    manufacturer = man.group(1).strip() if man else None
    mech = _parse_mech(text)

    coils = []
    for c in _parse_chem(text):
        m = mech.get(c["pack_no"], {})
        width, thick = m.get("width"), m.get("thickness")
        size = "{0} × {1}".format(width, thick) if (width and thick) else None
        c.update({
            "grade": grade,
            "specification": spec,
            "manufacturer": manufacturer,
            "thickness": thick,
            "width": width,
            "length": m.get("length"),
            "size": size,
            "yield_strength": m.get("ys"),
            "tensile_strength": m.get("ts"),
            "elongation": m.get("el"),
            "bend_test": m.get("bend"),
        })
        coils.append(c)
    return coils


@frappe.whitelist()
def extract_coils_from_pdf(docname):
    """يقرأ الـ PDF المرفق ويملأ جدول اللفائف بكل التفاصيل تلقائياً."""
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
            "grade": c.get("grade") or doc.grade,
            "item_code": doc.get("default_item"),
            "specification": c.get("specification"),
            "manufacturer": c.get("manufacturer"),
            "thickness": c.get("thickness"),
            "width": c.get("width"),
            "length": c.get("length"),
            "size": c.get("size"),
            "yield_strength": c.get("yield_strength"),
            "tensile_strength": c.get("tensile_strength"),
            "elongation": c.get("elongation"),
            "bend_test": c.get("bend_test"),
        })
        for fieldname, value in c["chem"].items():
            row.set(fieldname, value)
        total += c["weight_kg"]

    doc.total_weight = total
    doc.save()
    return {"coils": len(all_coils), "weight": total}
