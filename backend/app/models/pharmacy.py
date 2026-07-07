from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float, Date, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base

# ============================================================================
# Pharmacy master / catalog tables (Section B of the pharmacy module build)
# ============================================================================

class PharmacyCompany(Base):
    """Drug manufacturer / company master."""
    __tablename__ = "pharmacy_companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    contact = Column(String(200))
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PharmacySupplier(Base):
    """Supplier / party master used on purchase entries.

    Modelled on the Marg ERP "Modify Ledger" supplier screen — captures
    accounting (opening balance, hold-payment, ledger category), regulatory
    (DL / GST / FSSAI / PAN with expiry dates), and contact fields.
    """
    __tablename__ = "pharmacy_suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)            # "Ledger Name"

    # Accounting
    station = Column(String(100))                          # "Station"
    account_group = Column(String(60), default="Sundry Creditors")
    balancing_method = Column(String(30), default="bill_by_bill")
    opening_balance = Column(Float, default=0.0)
    opening_balance_dr_cr = Column(String(2), default="Dr")  # Dr | Cr
    hold_payment = Column(Boolean, default=False)
    hold_payment_pct = Column(Float, default=0.0)          # "if GSTR1 not upload"
    ledger_date = Column(Date)                             # "Ledger Date"
    freeze_upto = Column(Date)                             # "Freez Upto"

    # Contact
    contact_person = Column(String(100))
    designation = Column(String(100))
    phone_office = Column(String(30))                      # Phone No (Off.)
    phone_residence = Column(String(30))                   # Phone No (Res.)
    mobile = Column(String(30))                            # "Mobile"
    phone = Column(String(20))                             # legacy — kept for back-compat
    fax = Column(String(30))
    email = Column(String(100))
    website = Column(String(200))

    # Address
    mail_to = Column(String(200))                          # "Mail to"
    address = Column(Text)
    pin_code = Column(String(15))
    state = Column(String(80))                             # e.g. "TELANGANA"
    state_code = Column(String(10))                        # e.g. "36"
    country = Column(String(60), default="India")

    # GST
    gst_heading = Column(String(20), default="local")      # local | interstate | composition
    gstin = Column(String(20))                             # legacy column kept
    gstin_no = Column(String(30))                          # "GSTIN No"
    gstin_date = Column(Date)                              # "Dt."

    # Drug License
    dl_number = Column(String(50))                         # "D.L.No."
    dl_expiry = Column(Date)

    # VAT (legacy, pre-GST)
    vat_number = Column(String(40))
    vat_expiry = Column(Date)

    # Service Tax (legacy)
    st_number = Column(String(40))
    st_expiry = Column(Date)

    # Food License (FSSAI)
    food_license_no = Column(String(40))
    food_license_expiry = Column(Date)

    # Extra license slot
    extra_license_no = Column(String(60))
    extra_license_expiry = Column(Date)

    # PAN
    pan_number = Column(String(20))

    # Misc
    narco_sch_h_billing = Column(String(20), default="allow_all")  # allow_all | restrict | block
    bill_import = Column(String(20), default="mobile")
    ledger_category = Column(String(60), default="OTHERS")
    ledger_type = Column(String(30), default="unregistered")  # registered | unregistered | composition
    color_tag = Column(String(20), default="normal")
    is_hidden = Column(Boolean, default=False)             # "Hide"

    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PharmacySalt(Base):
    """Active salt / composition master."""
    __tablename__ = "pharmacy_salts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PharmacyStore(Base):
    """Pharmacy location — one master store plus optional satellite stores."""
    __tablename__ = "pharmacy_stores"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), nullable=False)
    name = Column(String(150), nullable=False)
    store_type = Column(String(20), nullable=False, default="master")  # master | satellite
    parent_store_id = Column(Integer, ForeignKey("pharmacy_stores.id"), nullable=True)
    location = Column(String(200))
    description = Column(Text)
    can_receive_supplier_purchase = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    parent_store = relationship("PharmacyStore", remote_side=[id], foreign_keys=[parent_store_id])


class PharmacyUserStore(Base):
    """Many-to-many: which pharmacy stores a user may operate."""
    __tablename__ = "pharmacy_user_stores"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    store_id = Column(Integer, ForeignKey("pharmacy_stores.id"), nullable=False, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    store = relationship("PharmacyStore")


class PharmacyRack(Base):
    """Physical rack / shelf location master."""
    __tablename__ = "pharmacy_racks"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), nullable=False)
    location = Column(String(100))
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PharmacyUoM(Base):
    """Unit-of-measure master (TAB, CAP, ML, MG, AMP, …).

    `decimal_supported` enables fractional quantities (e.g. 0.5 ML, 1.5 strips)
    on items/sales that use this UoM.
    """
    __tablename__ = "pharmacy_uoms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    abbreviation = Column(String(20))
    decimal_supported = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PharmacyHSN(Base):
    """HSN (Harmonized System of Nomenclature) tax code master.

    Each row defines an SGST/CGST rate pair; IGST is stored as their sum
    (combined inter-state rate). The same HSN code may appear on multiple rows
    with different tax rates. Medicines link via Medicine.hsn_id.
    """
    __tablename__ = "pharmacy_hsn_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), nullable=False)  # e.g. "30049099"
    description = Column(Text)
    sgst_pct = Column(Float, default=0.0)
    cgst_pct = Column(Float, default=0.0)
    igst_pct = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MedicineCategory(Base):
    __tablename__ = "medicine_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    medicines = relationship("Medicine", back_populates="category")


class Medicine(Base):
    __tablename__ = "medicines"

    id = Column(Integer, primary_key=True, index=True)
    medicine_code = Column(String(20), nullable=False)
    name = Column(String(200), nullable=False)
    generic_name = Column(String(200))
    manufacturer = Column(String(100))  # Legacy free-text. New entries should use company_id.
    category_id = Column(Integer, ForeignKey("medicine_categories.id"), nullable=False)
    dosage_form = Column(String(50))  # tablet, capsule, syrup, injection
    strength = Column(String(50))

    # Pricing — `unit_price` is the legacy single rate (kept as `rate_a` alias).
    # Section C added mrp / purchase_rate / rate_a / rate_b / cost_pcs / default_discount_pct.
    unit_price = Column(Float, nullable=False)
    mrp = Column(Float, default=0.0)                 # Maximum Retail Price
    purchase_rate = Column(Float, default=0.0)       # P-Rate — last seen purchase rate
    rate_a = Column(Float, default=0.0)              # Primary sale rate
    rate_b = Column(Float, default=0.0)              # Alternate sale rate
    cost_pcs = Column(Float, default=0.0)            # Cost per smallest unit (derived)
    default_discount_pct = Column(Float, default=0.0)

    description = Column(Text)
    side_effects = Column(Text)
    contraindications = Column(Text)
    storage_conditions = Column(Text)

    is_active = Column(Boolean, default=True)
    is_hidden = Column(Boolean, default=False)  # hide from sales counter without deleting
    requires_prescription = Column(Boolean, default=True)

    # Patient-safety + regulatory flags.
    # Narcotics (Schedule X) require a 2nd-witness for any MAR administration;
    # high-alert meds (insulin, heparin, KCl) trigger additional safety checks.
    is_narcotic = Column(Boolean, default=False)
    is_high_alert = Column(Boolean, default=False)
    is_schedule_h = Column(Boolean, default=False)
    is_schedule_h1 = Column(Boolean, default=False)
    is_tramadol = Column(Boolean, default=False)
    is_controlled = Column(Boolean, default=False)  # convenience: any controlled drug

    # Item-level default discount (%) applied at sale time unless overridden.
    item_discount_pct = Column(Float, default=0.0)

    # Catalog metadata (Section B)
    barcode = Column(String(50), index=True)
    packaging = Column(String(100))  # e.g. "10 tabs x 10 strips" (display only)
    decimal_supported = Column(Boolean, default=False)
    strip_conversion_factor = Column(Integer, default=1)  # tablets per strip/sheet
    rate_unit = Column(String(10), default="tablet")  # tablet | strip — what MRP/rate_a/rate_b mean

    # Master FKs
    company_id = Column(Integer, ForeignKey("pharmacy_companies.id"), nullable=True)
    rack_id = Column(Integer, ForeignKey("pharmacy_racks.id"), nullable=True)
    salt_id = Column(Integer, ForeignKey("pharmacy_salts.id"), nullable=True)
    uom_id = Column(Integer, ForeignKey("pharmacy_uoms.id"), nullable=True)
    hsn_id = Column(Integer, ForeignKey("pharmacy_hsn_codes.id"), nullable=True)

    # Stock thresholds (Section D)
    min_qty = Column(Integer, default=0)       # alert below this
    max_qty = Column(Integer, default=0)       # informational ceiling
    reorder_qty = Column(Integer, default=0)   # suggested order qty when low

    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Entry date of the most recent confirmed purchase that updated this
    # medicine's mrp / purchase_rate. Used to stop older back-dated purchases
    # from overwriting a more recent master price.
    last_purchase_date = Column(Date)

    category = relationship("MedicineCategory", back_populates="medicines")
    company = relationship("PharmacyCompany")
    rack = relationship("PharmacyRack")
    salt = relationship("PharmacySalt")
    uom = relationship("PharmacyUoM")
    hsn = relationship("PharmacyHSN")
    inventory = relationship("PharmacyInventory", back_populates="medicine")
    prescription_items = relationship("PrescriptionItem", back_populates="medicine")

class PharmacyInventory(Base):
    """One row per (medicine, batch). Stock is tracked per batch for FIFO + expiry."""
    __tablename__ = "pharmacy_inventory"

    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    batch_number = Column(String(50), nullable=False)
    expiry_date = Column(Date, nullable=False)
    quantity_in_stock = Column(Integer, nullable=False, default=0)
    cost_price = Column(Float, nullable=False)
    selling_price = Column(Float, nullable=False)

    # Legacy free-text supplier — superseded by supplier_id below.
    supplier = Column(String(100))
    purchase_date = Column(Date)

    # Section D additive columns
    mrp = Column(Float, default=0.0)             # per-batch MRP, may differ from medicine.mrp
    purchase_rate = Column(Float, default=0.0)   # P-Rate for this batch
    rate_a = Column(Float, default=0.0)          # per-batch sale Rate A (per strip)
    rate_b = Column(Float, default=0.0)          # per-batch sale Rate B (per strip)
    strip_conversion_factor = Column(Integer, default=1)  # tabs per strip for this batch
    free_quantity = Column(Integer, default=0)
    discount_pct = Column(Float, default=0.0)    # discount applied at purchase time
    hsn_id = Column(Integer, ForeignKey("pharmacy_hsn_codes.id"), nullable=True)
    supplier_id = Column(Integer, ForeignKey("pharmacy_suppliers.id"), nullable=True)
    # Logical FK to Section E pharmacy_purchases.id. Left as plain Integer here
    # so model order at create_all() doesn't depend on Section E. SQLite does
    # not enforce FK constraints by default; reporting joins are explicit.
    purchase_id = Column(Integer, nullable=True)

    store_id = Column(Integer, ForeignKey("pharmacy_stores.id"), nullable=True, index=True)
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    medicine = relationship("Medicine", back_populates="inventory")
    hsn = relationship("PharmacyHSN")
    supplier_ref = relationship("PharmacySupplier")
    store = relationship("PharmacyStore")


class PharmacyStockLedger(Base):
    """Append-only stock movement ledger.

    Every change to PharmacyInventory.quantity_in_stock — from purchase
    confirmation, sale, Rx dispense, manual adjustment, return, or
    expiry write-off — writes one row here.
    `qty_delta` is signed (+ for additions, − for consumption).
    """
    __tablename__ = "pharmacy_stock_ledger"

    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("pharmacy_inventory.id"), nullable=True, index=True)
    txn_type = Column(String(30), nullable=False)
    # One of: purchase, sale, rx_dispense, adjustment, return_in, return_out, expiry_write_off
    qty_delta = Column(Float, nullable=False)
    reference_type = Column(String(30))  # e.g. "purchase", "sale", "prescription", "adjustment"
    reference_id = Column(Integer)        # FK-by-convention to the source row
    performed_by = Column(Integer, ForeignKey("users.id"))
    notes = Column(Text)
    store_id = Column(Integer, ForeignKey("pharmacy_stores.id"), nullable=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    medicine = relationship("Medicine")
    batch = relationship("PharmacyInventory")
    user = relationship("User")
    store = relationship("PharmacyStore")


class PharmacyPurchase(Base):
    """Procurement / Goods-Receipt header.

    Lifecycle: `draft` (editable) → `confirmed` (editable with reason + inventory
    sync) → optionally `revoked` / `revoked_partial` via POST /purchases/{id}/revoke.
    """
    __tablename__ = "pharmacy_purchases"

    id = Column(Integer, primary_key=True, index=True)
    purchase_number = Column(String(30), unique=True, nullable=False, index=True)
    entry_date = Column(Date, nullable=False)
    supplier_id = Column(Integer, ForeignKey("pharmacy_suppliers.id"), nullable=False)
    invoice_number = Column(String(50))
    bill_date = Column(Date)
    payment_type = Column(String(20), default="cash")   # cash | credit
    purchase_type = Column(String(30))                  # free text — local / interstate / direct / etc.
    status = Column(String(20), default="draft", index=True)  # draft | confirmed

    subtotal = Column(Float, default=0.0)
    total_discount = Column(Float, default=0.0)
    total_tax = Column(Float, default=0.0)
    grand_total = Column(Float, default=0.0)
    tax_mode = Column(String(20), default="exclusive")  # exclusive | inclusive
    notes = Column(Text)

    created_by = Column(Integer, ForeignKey("users.id"))
    confirmed_by = Column(Integer, ForeignKey("users.id"))
    confirmed_at = Column(DateTime)
    # Status `revoked` (nothing sold yet) and `revoked_partial` (proportional
    # reversal because some qty was already sold/dispensed) close out a confirmed
    # purchase. Audit trail lives on these three columns.
    revoked_by = Column(Integer, ForeignKey("users.id"))
    revoked_at = Column(DateTime)
    revoke_reason = Column(Text)
    # Last confirmed-purchase edit (requires reason; inventory adjusted in place).
    edited_by = Column(Integer, ForeignKey("users.id"))
    edited_at = Column(DateTime)
    edit_reason = Column(Text)
    store_id = Column(Integer, ForeignKey("pharmacy_stores.id"), nullable=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    items = relationship("PharmacyPurchaseItem", back_populates="purchase", cascade="all, delete-orphan")
    supplier = relationship("PharmacySupplier")
    store = relationship("PharmacyStore")


class PharmacyPurchaseItem(Base):
    """Per-batch line on a purchase."""
    __tablename__ = "pharmacy_purchase_items"

    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(Integer, ForeignKey("pharmacy_purchases.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    batch_number = Column(String(50), nullable=False)
    expiry_date = Column(Date, nullable=False)
    mrp = Column(Float, default=0.0)
    quantity = Column(Float, nullable=False)
    free_quantity = Column(Float, default=0.0)
    purchase_rate = Column(Float, nullable=False)
    rate_a = Column(Float, default=0.0)          # sale Rate A for this batch (per strip)
    rate_b = Column(Float, default=0.0)          # sale Rate B for this batch (per strip)
    strip_conversion_factor = Column(Integer, default=1)  # tabs per strip for this batch
    discount_pct = Column(Float, default=0.0)
    hsn_id = Column(Integer, ForeignKey("pharmacy_hsn_codes.id"), nullable=True)
    tax_amount = Column(Float, default=0.0)
    line_total = Column(Float, default=0.0)
    # P2.1: snapshot tax % at confirm time so historical reports are stable
    # even when the HSN master rates change later.
    sgst_pct = Column(Float, default=0.0)
    cgst_pct = Column(Float, default=0.0)
    igst_pct = Column(Float, default=0.0)

    # Set on confirm — links back to the inventory batch row this item created.
    inventory_id = Column(Integer, ForeignKey("pharmacy_inventory.id"), nullable=True)

    purchase = relationship("PharmacyPurchase", back_populates="items")
    medicine = relationship("Medicine")
    hsn = relationship("PharmacyHSN")


class PharmacySale(Base):
    """POS counter sale header (Section F).

    Patient + doctor info is captured as free-text per requirements doc 3.1 —
    no cross-module FK linkage to patients / users in this build.
    """
    __tablename__ = "pharmacy_sales"

    id = Column(Integer, primary_key=True, index=True)
    sale_number = Column(String(30), unique=True, nullable=False, index=True)
    sale_date = Column(DateTime, nullable=False, server_default=func.now())
    payment_type = Column(String(20), default="cash")  # cash | credit

    # Patient info (free text, not FK-linked)
    patient_phone = Column(String(20))
    patient_ip_id = Column(String(50))       # In-patient ID (free text)
    patient_name = Column(String(150))
    patient_address = Column(Text)

    # Doctor info (free text)
    doctor_number = Column(String(50))
    doctor_name = Column(String(150))

    subtotal = Column(Float, default=0.0)
    discount_total = Column(Float, default=0.0)
    tax_total = Column(Float, default=0.0)
    grand_total = Column(Float, default=0.0)
    tax_mode = Column(String(20), default="exclusive")  # exclusive | inclusive

    status = Column(String(20), default="completed", index=True)   # completed | voided
    voided_by = Column(Integer, ForeignKey("users.id"))
    voided_at = Column(DateTime)
    void_reason = Column(Text)

    # Inpatient billing: when billing_mode='inpatient_bill', stock is sold but
    # payment is deferred to the admission bill at discharge/interim.
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=True, index=True)
    billing_mode = Column(String(30), default="cash_at_pharmacy")  # cash_at_pharmacy | inpatient_bill
    inpatient_bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"))
    store_id = Column(Integer, ForeignKey("pharmacy_stores.id"), nullable=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    items = relationship("PharmacySaleItem", back_populates="sale", cascade="all, delete-orphan")
    store = relationship("PharmacyStore")


class PharmacySaleItem(Base):
    """Per-batch sale line. `rate_tier` records which medicine rate was used."""
    __tablename__ = "pharmacy_sale_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("pharmacy_sales.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("pharmacy_inventory.id"), nullable=False)
    quantity = Column(Float, nullable=False)  # base tablets deducted from stock
    free_quantity = Column(Float, default=0.0)
    sale_qty = Column(Float, nullable=True)  # legacy single-unit qty (first batch row)
    sale_qty_unit = Column(String(10), default="tablet")  # legacy: tablet | strip
    sale_qty_tabs = Column(Float, nullable=True)
    sale_qty_strips = Column(Float, nullable=True)
    rate = Column(Float, nullable=False)  # per-tablet rate used for billing
    rate_tier = Column(String(10), default="A")   # A | B
    discount_pct = Column(Float, default=0.0)
    tax_pct = Column(Float, default=0.0)
    # P2.1: per-component snapshot at sale time. tax_pct (above) is the sum
    # and stays for back-compat with anything that already reads it.
    sgst_pct = Column(Float, default=0.0)
    cgst_pct = Column(Float, default=0.0)
    igst_pct = Column(Float, default=0.0)
    line_total = Column(Float, default=0.0)
    barcode_scanned = Column(Boolean, default=False)

    sale = relationship("PharmacySale", back_populates="items")
    medicine = relationship("Medicine")
    batch = relationship("PharmacyInventory")


class PharmacyStockAdjustment(Base):
    """Manual stock adjustment requests (admin-initiated).

    Records the reason + before/after counts. Also writes a corresponding
    PharmacyStockLedger row (txn_type='adjustment') for unified history.
    """
    __tablename__ = "pharmacy_stock_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("pharmacy_inventory.id"), nullable=False)
    qty_change = Column(Float, nullable=False)  # signed: + = add, − = remove
    reason = Column(String(200), nullable=False)
    performed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    store_id = Column(Integer, ForeignKey("pharmacy_stores.id"), nullable=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    medicine = relationship("Medicine")
    batch = relationship("PharmacyInventory")
    user = relationship("User")
    store = relationship("PharmacyStore")


class PharmacyTransfer(Base):
    """Inter-store stock transfer (master → satellite). Draft → confirmed lifecycle."""
    __tablename__ = "pharmacy_transfers"

    id = Column(Integer, primary_key=True, index=True)
    transfer_number = Column(String(30), unique=True, nullable=False, index=True)
    entry_date = Column(Date, nullable=False)
    from_store_id = Column(Integer, ForeignKey("pharmacy_stores.id"), nullable=False)
    to_store_id = Column(Integer, ForeignKey("pharmacy_stores.id"), nullable=False)
    status = Column(String(20), default="draft", index=True)  # draft | confirmed | revoked | revoked_partial
    notes = Column(Text)
    item_count = Column(Integer, default=0)
    total_qty = Column(Float, default=0.0)
    created_by = Column(Integer, ForeignKey("users.id"))
    confirmed_by = Column(Integer, ForeignKey("users.id"))
    confirmed_at = Column(DateTime)
    revoked_by = Column(Integer, ForeignKey("users.id"))
    revoked_at = Column(DateTime)
    revoke_reason = Column(Text)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    from_store = relationship("PharmacyStore", foreign_keys=[from_store_id])
    to_store = relationship("PharmacyStore", foreign_keys=[to_store_id])
    items = relationship("PharmacyTransferItem", back_populates="transfer", cascade="all, delete-orphan")


class PharmacyTransferItem(Base):
    __tablename__ = "pharmacy_transfer_items"

    id = Column(Integer, primary_key=True, index=True)
    transfer_id = Column(Integer, ForeignKey("pharmacy_transfers.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    source_batch_id = Column(Integer, ForeignKey("pharmacy_inventory.id"), nullable=False)
    batch_number = Column(String(50), nullable=False)
    expiry_date = Column(Date, nullable=False)
    quantity = Column(Float, nullable=False)
    target_inventory_id = Column(Integer, ForeignKey("pharmacy_inventory.id"), nullable=True)

    transfer = relationship("PharmacyTransfer", back_populates="items")
    medicine = relationship("Medicine")
    source_batch = relationship("PharmacyInventory", foreign_keys=[source_batch_id])
    target_batch = relationship("PharmacyInventory", foreign_keys=[target_inventory_id])


class Prescription(Base):
    __tablename__ = "prescriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    prescription_number = Column(String(50), unique=True, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    consultation_id = Column(Integer, ForeignKey("consultations.id"))
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=True)
    prescription_date = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String(20), default="pending")  # pending, dispensed, partial, cancelled
    notes = Column(Text)
    total_amount = Column(Float, default=0.0)
    dispensed_by_id = Column(Integer, ForeignKey("users.id"))
    dispensed_date = Column(DateTime)
    inpatient_bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)  # which admission bill consumed this Rx
    pharmacy_sale_id = Column(Integer, ForeignKey("pharmacy_sales.id"), nullable=True)  # set when paid at pharmacy counter
    dispense_store_id = Column(Integer, ForeignKey("pharmacy_stores.id"), nullable=True)

    # Cancellation metadata. status='cancelled' is set at the same time these
    # are stamped; see app/services/pharmacy_reversal.py.
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancel_reason = Column(Text, nullable=True)

    items = relationship("PrescriptionItem", back_populates="prescription")
    consultation = relationship("Consultation", back_populates="prescriptions")

class PrescriptionItem(Base):
    __tablename__ = "prescription_items"

    id = Column(Integer, primary_key=True, index=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    quantity_prescribed = Column(Integer, nullable=False)
    quantity_dispensed = Column(Integer, default=0)
    dosage = Column(String(100))  # 1 tablet twice daily
    duration = Column(String(50))  # 7 days
    instructions = Column(Text)
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    status = Column(String(20), default="pending")  # pending, dispensed, partial

    # MAR scheduling fields (used when prescription is for an inpatient admission)
    frequency = Column(String(50))           # e.g. "BD", "TDS", "QID", "Q8H", "ONCE"
    schedule_times = Column(JSON)            # ["08:00", "16:00", "00:00"] for fixed schedules
    duration_days = Column(Integer)          # numeric form of duration for MAR generation
    route = Column(String(30))               # oral, iv, im, sc, topical, inhalation, sublingual, rectal
    is_prn = Column(Boolean, default=False)  # as-needed medication, no fixed schedule

    prescription = relationship("Prescription", back_populates="items")
    medicine = relationship("Medicine", back_populates="prescription_items")