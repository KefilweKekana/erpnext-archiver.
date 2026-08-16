from frappe.model.document import Document


class ArchivedFiscalYear(Document):
    def autoname(self):
        self.name = self.fiscal_year
