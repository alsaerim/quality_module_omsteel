

frappe.ui.form.on('Sales Order', {
    onload: function(frm) {
        check_and_add_button(frm);
    },
    refresh: function(frm) {
        check_and_add_button(frm);
    }
});

function check_and_add_button(frm) {
    if (frm.doc.docstatus === 1) {
        frm.add_custom_button(__('Create Quality Certificate'), function() {
            frappe.call({
                method: "quality_module_omsteel.quality_module_omsteel.quality_certificate_py.create_quality_certificate",
                args: {
                    sales_order: frm.doc.name
                },
                callback: function(r) {
                    if (r.message) {
//                        frappe.msgprint({
//                            title: __("Success"),
//                            message: __("Quality Certificate Created: ") + r.message,
//                            indicator: "green"
//                        });


                        frappe.show_alert({
                            message: __("Quality Certificate Created: ") + r.message,
                            indicator: "green"
                        }, 5);

                        frm.reload_doc();
                    }
                }
            });
        }, __("Quality"));
    }
}


