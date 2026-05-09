import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { ConfirmDialog } from '../../components/ui/confirm-dialog';
import { useToast } from '../../hooks/use-toast';
import { useAuth } from '../../contexts/AuthContext';
import { printPdfFromUrl } from '../../utils/printPdf';
import {
  Plus, Search, Edit2, Trash2, Bed, Activity, Clock, User, Users,
  FileText, Loader2, X, ChevronLeft, ChevronRight, DollarSign, Stethoscope,
  ClipboardList, LayoutDashboard, Scissors, Shield, Upload, Download, Paperclip,
  HeartPulse, Pill, AlertTriangle, Check, XCircle, Wallet, Package, Receipt, FileCheck, Building2,
  Sparkles, CalendarDays, ArrowRightLeft, UserPlus, FileSignature, AlertOctagon, RotateCcw, Skull,
  CalendarRange, Printer
} from 'lucide-react';
import axios from 'axios';

// ============================================================
// Status badge helpers
// ============================================================
const admissionStatusColor = {
  admitted: 'bg-blue-100 text-blue-800',
  discharged: 'bg-green-100 text-green-800',
  transferred: 'bg-yellow-100 text-yellow-800',
};

const otStatusColor = {
  scheduled: 'bg-blue-100 text-blue-800',
  in_progress: 'bg-yellow-100 text-yellow-800',
  completed: 'bg-green-100 text-green-800',
  cancelled: 'bg-red-100 text-red-800',
  postponed: 'bg-orange-100 text-orange-800',
};

const roomTypeLabel = { general: 'General', private: 'Private', icu: 'ICU', emergency: 'Emergency', operation: 'Operation' };

const claimStatusColor = {
  none: 'bg-gray-100 text-gray-800',
  draft: 'bg-yellow-100 text-yellow-800',
  submitted: 'bg-blue-100 text-blue-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
};

const claimStatusLabel = { none: 'No Claim', draft: 'Draft', submitted: 'Submitted', approved: 'Approved', rejected: 'Rejected' };

// Map between activeTab keys and URL path segments under /dashboard/inpatient
// Empty string = the bare /dashboard/inpatient root (Ward Overview).
const TAB_TO_PATH = {
  dashboard: '',
  admissions: 'admissions',
  triage: 'triage',
  discharge: 'discharge',
  ot: 'ot',
  preauth: 'preauth',
  reservations: 'reservations',
  roster: 'duty-roster',
  housekeeping: 'housekeeping',
  incidents: 'incidents',
  quality: 'quality',
  rooms: 'rooms',
  setup: 'billing-setup',
  procedures: 'procedures',
  reports: 'reports',
};
const PATH_TO_TAB = Object.fromEntries(
  Object.entries(TAB_TO_PATH).map(([k, v]) => [v, k])
);

const InpatientModule = () => {
  const { toast } = useToast();
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  // Roles that should see billing-related views inside an admission.
  // Clinical-only roles (nurse, doctor) are intentionally excluded.
  const userRoles = useMemo(() => {
    if (!user) return [];
    return user.role_names || [user.role?.name].filter(Boolean);
  }, [user]);
  const canViewBilling = useMemo(() => {
    const billingRoles = ['super_admin', 'hospital_admin', 'billing_admin', 'receptionist', 'frontdesk', 'inpatient_admin'];
    return userRoles.some(r => billingRoles.includes(r));
  }, [userRoles]);
  const isAdminLike = useMemo(() => userRoles.some(r => ['super_admin', 'hospital_admin', 'inpatient_admin'].includes(r)), [userRoles]);
  const isDoctorRole = useMemo(() => userRoles.includes('doctor'), [userRoles]);
  const isNurseRole = useMemo(() => userRoles.includes('nurse'), [userRoles]);

  // Effective permission map (module → permission keys) loaded from backend.
  // Used to gate UI elements so users only see actions they can actually perform.
  const [permsLoaded, setPermsLoaded] = useState(false);
  const [myPerms, setMyPerms] = useState({ is_admin: false, modules: {} });
  useEffect(() => {
    let cancelled = false;
    axios.get('/api/admin/me/permissions').then(res => {
      if (cancelled) return;
      setMyPerms(res.data || { is_admin: false, modules: {} });
      setPermsLoaded(true);
    }).catch(() => { setPermsLoaded(true); });
    return () => { cancelled = true; };
  }, []);
  const hasPerm = useCallback((module, key) => {
    if (myPerms?.is_admin) return true;
    const mods = myPerms?.modules || {};
    if (mods['*']?.includes('*')) return true;
    const list = mods[module] || [];
    return list.includes('*') || list.includes(key);
  }, [myPerms]);
  const ip = useCallback((key) => hasPerm('inpatient', key), [hasPerm]);
  // Nurse-only users get a nurse-scoped Visit form (no Doctor Visit option,
  // visitor list limited to nurses, and the form defaults to nurse_visit).
  const isNurseOnly = isNurseRole && !isDoctorRole && !isAdminLike;
  const defaultVisitType = isNurseOnly ? 'nurse_visit' : 'doctor_visit';
  // activeTab is derived from the URL — when the user clicks a nav item the
  // browser navigates and this re-derives. Setting activeTab now means navigating.
  const activeTab = useMemo(() => {
    const segs = location.pathname.split('/').filter(Boolean);
    // ['dashboard', 'inpatient', 'sub-page?']
    const sub = segs[2] || '';
    return PATH_TO_TAB[sub] || 'dashboard';
  }, [location.pathname]);

  const setActiveTab = useCallback((nextKey) => {
    const seg = TAB_TO_PATH[nextKey];
    if (seg === undefined) return;
    const target = seg ? `/dashboard/inpatient/${seg}` : '/dashboard/inpatient';
    if (location.pathname !== target) navigate(target);
  }, [navigate, location.pathname]);
  const [loading, setLoading] = useState(false);
  const [confirmState, setConfirmState] = useState({ open: false });

  // Dashboard
  const [dashboardData, setDashboardData] = useState(null);

  // Admissions
  const [admissions, setAdmissions] = useState([]);
  const [triageQueue, setTriageQueue] = useState([]);
  const [triageLoading, setTriageLoading] = useState(false);
  const [admissionSearch, setAdmissionSearch] = useState('');
  const [showAdmissionDialog, setShowAdmissionDialog] = useState(false);
  const [admissionForm, setAdmissionForm] = useState({
    patient_id: '', admitting_doctor_id: '', room_id: '', admission_type: 'elective',
    admission_reason: '', condition_on_admission: 'stable', estimated_stay_days: '',
    admission_notes: '', insurance_provider: '', policy_number: '', claim_reference: '', emergency_contact: '', bed_number: '', bed_id: '',
    triage_level: '', chief_complaint: '', arrival_mode: 'walk_in', ambulance_details: '',
    is_mlc: false, mlc_type: '', mlc_number: '', police_station_informed: '',
    is_observation: false, deposit_waived: false, deposit_waiver_reason: '',
  });
  const [showQuickAdmitDialog, setShowQuickAdmitDialog] = useState(false);
  const [quickAdmitForm, setQuickAdmitForm] = useState({
    first_name: '', last_name: 'UNKNOWN', age: '', gender: '', primary_phone: '',
    admitting_doctor_id: '', room_id: '', bed_id: '',
    admission_reason: '', condition_on_admission: 'critical',
    triage_level: '1', chief_complaint: '', arrival_mode: 'walk_in', ambulance_details: '',
    is_mlc: false, mlc_type: '', mlc_number: '', police_station_informed: '',
    is_observation: false, deposit_waived: false, deposit_waiver_reason: '',
    emergency_contact: '',
  });
  const [patientSearchResults, setPatientSearchResults] = useState([]);
  const [patientSearchQuery, setPatientSearchQuery] = useState('');
  const [selectedPatientName, setSelectedPatientName] = useState('');
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [patientSearching, setPatientSearching] = useState(false);
  const [doctorsList, setDoctorsList] = useState([]);
  const [availableRooms, setAvailableRooms] = useState([]);

  // Activity slide-over
  const [activityAdmission, setActivityAdmission] = useState(null);
  const [activityTab, setActivityTab] = useState('visits');
  const [visits, setVisits] = useState([]);
  const [billData, setBillData] = useState(null);
  const [showVisitDialog, setShowVisitDialog] = useState(false);
  const [visitForm, setVisitForm] = useState({ visit_type: defaultVisitType, visitor_id: '', notes: '', vitals_reviewed: false, labs_reviewed: false, pain_assessed: false, mobility_checked: false, plan_for_today: '', family_updated: false });
  const [admissionMedications, setAdmissionMedications] = useState([]);
  const [admissionLabOrders, setAdmissionLabOrders] = useState([]);
  const [availableLabTests, setAvailableLabTests] = useState([]);
  const [showLabOrderDialog, setShowLabOrderDialog] = useState(false);
  const [labOrderForm, setLabOrderForm] = useState({ test_ids: [], priority: 'normal', notes: '' });
  const [labTestSearch, setLabTestSearch] = useState('');
  // Inpatient prescription (Add Medication) state
  const BLANK_RX_ITEM = { medicine_id: '', medicine_name: '', dosage: '', duration: '', quantity_prescribed: 1, instructions: '' };
  const [showPrescriptionDialog, setShowPrescriptionDialog] = useState(false);
  const [prescriptionForm, setPrescriptionForm] = useState({ notes: '', items: [{ ...BLANK_RX_ITEM }] });
  const [medicineSearchResults, setMedicineSearchResults] = useState([]);
  const [medicineSearchTargetIdx, setMedicineSearchTargetIdx] = useState(null);

  // Rooms
  const [rooms, setRooms] = useState([]);
  const [showRoomDialog, setShowRoomDialog] = useState(false);
  const [editingRoom, setEditingRoom] = useState(null);
  const [roomForm, setRoomForm] = useState({
    room_number: '', room_type: 'general', floor: '', department: '',
    bed_count: 1, room_charge_per_day: '',  amenities: '',
  });

  // Bed Management
  const [selectedRoomForBeds, setSelectedRoomForBeds] = useState(null);
  const [roomBeds, setRoomBeds] = useState([]);
  const [newBedLabel, setNewBedLabel] = useState('');
  const [showBedManager, setShowBedManager] = useState(false);
  const [admissionBeds, setAdmissionBeds] = useState([]);  // beds for selected room in admission form
  const [admissionDocs, setAdmissionDocs] = useState([]);
  const [docUploading, setDocUploading] = useState(false);
  const [billDiscount, setBillDiscount] = useState({ type: 'flat', value: 0 });
  const [billTaxPct, setBillTaxPct] = useState(0);
  // Review & Edit Final Bill — operator-editable line items + discount/tax.
  // `source` ties each line back to the auto-computed source so the backend
  // can stamp source records' bill_id and prevent double-billing.
  const [showReviewBillDialog, setShowReviewBillDialog] = useState(false);
  const [reviewBillItems, setReviewBillItems] = useState([]);
  const [reviewBillDiscount, setReviewBillDiscount] = useState({ type: 'flat', value: 0 });
  const [reviewBillTaxPct, setReviewBillTaxPct] = useState(0);
  const [nursingNotes, setNursingNotes] = useState([]);
  const [dietOrders, setDietOrders] = useState([]);
  const [showDietDialog, setShowDietDialog] = useState(false);
  const [dietForm, setDietForm] = useState({ diet_type: 'regular', meal_instructions: '', allergies: '', notes: '' });
  // Per-meal log dialog
  const [mealLogDialog, setMealLogDialog] = useState({ open: false, orderId: null, meal_time: 'lunch', status: 'served', notes: '' });
  // Kitchen ticket print dialog
  const [kitchenTicketDialog, setKitchenTicketDialog] = useState({ open: false, meal_time: 'lunch', department: '' });
  // LOA dialog state
  const [loaDialog, setLoaDialog] = useState({ open: false, admissionId: null,
    start_datetime: '', expected_return_datetime: '', reason: '',
    approved_by_doctor_id: '', notes: '', bed_held: true });
  const [loaList, setLoaList] = useState([]);
  // E2 — Monthly outcomes report
  const [reportSubTab, setReportSubTab] = useState('outcomes');
  const [outcomesMonth, setOutcomesMonth] = useState(() => {
    const d = new Date(); d.setDate(0); // last day of previous month
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  });
  const [outcomesData, setOutcomesData] = useState(null);
  // E3 — Doctor productivity report
  const [productivityRange, setProductivityRange] = useState(() => {
    const today = new Date();
    const start = new Date(Date.now() - 30 * 86400 * 1000);
    return { from: start.toISOString().slice(0, 10), to: today.toISOString().slice(0, 10), doctor_id: '' };
  });
  const [productivityData, setProductivityData] = useState(null);
  const [showNursingNoteDialog, setShowNursingNoteDialog] = useState(false);
  const [nursingNoteForm, setNursingNoteForm] = useState({ shift: 'morning', note_type: 'general', content: '' });
  const [editingNursingNote, setEditingNursingNote] = useState(null);
  const [nursingShiftFilter, setNursingShiftFilter] = useState('all');

  // Vitals
  const [vitals, setVitals] = useState([]);
  const [latestVitals, setLatestVitals] = useState(null);
  const [showVitalsDialog, setShowVitalsDialog] = useState(false);
  const VITALS_BLANK = {
    shift: 'morning', bp_systolic: '', bp_diastolic: '', heart_rate: '', respiratory_rate: '',
    temperature_c: '', spo2: '', blood_glucose: '', pain_score: '', gcs_score: '',
    weight_kg: '', height_cm: '', position: '', notes: '',
  };
  const [vitalsForm, setVitalsForm] = useState(VITALS_BLANK);

  // Allergies (patient-level, displayed alongside admission)
  const [admissionAllergies, setAdmissionAllergies] = useState([]);
  const [showAllergyDialog, setShowAllergyDialog] = useState(false);
  const [allergyForm, setAllergyForm] = useState({ allergy_type: 'drug', allergen: '', severity: 'moderate', reaction: '', notes: '' });

  // MAR
  const [mar, setMar] = useState([]);
  const [marDate, setMarDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [showAdministerDialog, setShowAdministerDialog] = useState(false);
  const [administeringDose, setAdministeringDose] = useState(null);
  const [administerForm, setAdministerForm] = useState({ status: 'given', dose_given: '', route: '', site: '', reason_if_not_given: '', notes: '' });
  const [showPrnDialog, setShowPrnDialog] = useState(false);
  const [prnForm, setPrnForm] = useState({ prescription_item_id: '', dose_given: '', route: '', site: '', prn_indication: '', notes: '' });

  // Phase 2: Deposits + balance
  const [deposits, setDeposits] = useState([]);
  const [balance, setBalance] = useState(null);
  const [showDepositDialog, setShowDepositDialog] = useState(false);
  const [depositForm, setDepositForm] = useState({ amount: '', payment_method: 'cash', deposit_type: 'initial', reference_number: '', notes: '' });
  const [showRefundDialog, setShowRefundDialog] = useState(false);
  const [refundForm, setRefundForm] = useState({ amount: '', payment_method: 'cash', reference_number: '', notes: '' });

  // Phase 2: Ancillary charges (per-admission)
  const [ancillaryCharges, setAncillaryCharges] = useState([]);
  const [ancillaryServices, setAncillaryServices] = useState([]);
  const [showAncillaryDialog, setShowAncillaryDialog] = useState(false);
  const [ancillaryForm, setAncillaryForm] = useState({ service_id: '', quantity: 1, unit_price: '', notes: '' });

  // Phase 2: Bills history + interim
  const [admissionBills, setAdmissionBills] = useState([]);

  // Phase 2: Package
  const [admissionPackage, setAdmissionPackage] = useState(null);
  const [showApplyPackageDialog, setShowApplyPackageDialog] = useState(false);
  const [applyPackageForm, setApplyPackageForm] = useState({ package_id: '', agreed_price: '', notes: '' });

  // Phase 2: Catalogs (admin)
  const [packagesList, setPackagesList] = useState([]);
  const [tpaList, setTpaList] = useState([]);
  const [setupSubTab, setSetupSubTab] = useState('ancillary');

  // Procedure catalog (drives OT charge auto-fill)
  const [proceduresList, setProceduresList] = useState([]);
  const [showProcedureDialog, setShowProcedureDialog] = useState(false);
  const [editingProcedure, setEditingProcedure] = useState(null);
  const [procedureForm, setProcedureForm] = useState({ name: '', default_rate: '', description: '' });
  const [showServiceDialog, setShowServiceDialog] = useState(false);
  const [editingService, setEditingService] = useState(null);
  const [serviceForm, setServiceForm] = useState({ service_name: '', service_code: '', category: 'imaging', default_charge: '', charge_unit: 'per_session', description: '' });
  const [showPackageDialog, setShowPackageDialog] = useState(false);
  const [editingPackage, setEditingPackage] = useState(null);
  const [packageForm, setPackageForm] = useState({ package_name: '', package_code: '', base_price: '', included_room_type: '', included_stay_days: 0, included_services: [], excess_per_day_charge: 0, description: '' });
  const [showTpaDialog, setShowTpaDialog] = useState(false);
  const [editingTpa, setEditingTpa] = useState(null);
  const [tpaForm, setTpaForm] = useState({ tpa_name: '', tpa_code: '', address: '', phone: '', email: '', default_discount_percent: 0, contract_details: '' });

  // Phase 2: Pre-authorisations
  const [preauths, setPreauths] = useState([]);
  const [preauthSearch, setPreauthSearch] = useState('');
  const [preauthStatusFilter, setPreauthStatusFilter] = useState('');
  const [showPreauthDialog, setShowPreauthDialog] = useState(false);
  const [preauthForm, setPreauthForm] = useState({ patient_id: '', admission_id: '', insurance_provider: '', policy_number: '', tpa_id: '', requested_amount: '', notes: '' });
  const [activePreauth, setActivePreauth] = useState(null);
  const [showPreauthDecisionDialog, setShowPreauthDecisionDialog] = useState(false);
  const [preauthDecisionForm, setPreauthDecisionForm] = useState({ status: 'approved', approved_amount: '', validity_days: '', approval_reference: '', notes: '' });
  const [preauthPatientSearch, setPreauthPatientSearch] = useState('');
  const [preauthPatientResults, setPreauthPatientResults] = useState([]);
  const [preauthSelectedPatient, setPreauthSelectedPatient] = useState(null);

  // Phase 2: Bill split
  const [billForSplit, setBillForSplit] = useState(null);
  const [splitRows, setSplitRows] = useState([]);
  const [showSplitDialog, setShowSplitDialog] = useState(false);

  // Phase 2: OT charges
  const [showOTChargesDialog, setShowOTChargesDialog] = useState(false);
  const [editingOT, setEditingOT] = useState(null);
  const [otChargesForm, setOtChargesForm] = useState({ surgeon_fee: 0, anaesthetist_fee: 0, ot_room_charge: 0, equipment_charge: 0, consumables_charge: 0, procedure_charge: 0, other_charges: 0 });

  // Phase 3: Bed transfer history + inter-ward transfer
  const [transferHistory, setTransferHistory] = useState([]);
  const [pendingTransfers, setPendingTransfers] = useState([]);
  const [showWardTransferDialog, setShowWardTransferDialog] = useState(false);
  const [wardTransferForm, setWardTransferForm] = useState({ to_room_id: '', to_bed_id: '', reason: '', transfer_note: '' });
  const [wardTransferBeds, setWardTransferBeds] = useState([]);

  // Phase 3: Housekeeping
  const [cleaningBeds, setCleaningBeds] = useState([]);
  const [turnoverStats, setTurnoverStats] = useState(null);

  // Phase 3: Reservations
  const [reservations, setReservations] = useState([]);
  const [showReservationDialog, setShowReservationDialog] = useState(false);
  const [reservationForm, setReservationForm] = useState({ patient_id: '', bed_id: '', room_id: '', room_type: '', reserved_for_date: '', reservation_reason: 'elective', notes: '' });
  const [reservationPatientSearch, setReservationPatientSearch] = useState('');
  const [reservationPatientResults, setReservationPatientResults] = useState([]);
  const [reservationSelectedPatient, setReservationSelectedPatient] = useState(null);
  const [showConvertReservationDialog, setShowConvertReservationDialog] = useState(false);
  const [convertingReservation, setConvertingReservation] = useState(null);
  const [convertForm, setConvertForm] = useState({ admitting_doctor_id: '', admission_type: 'elective', admission_reason: '', condition_on_admission: 'stable' });

  // Phase 3: Nurse assignments
  const [nurseAssignments, setNurseAssignments] = useState([]);
  const [nursesList, setNursesList] = useState([]);
  const [showNurseAssignDialog, setShowNurseAssignDialog] = useState(false);
  const [nurseAssignForm, setNurseAssignForm] = useState({ nurse_id: '', shift: 'morning', assignment_date: new Date().toISOString().slice(0, 10), is_primary: false, notes: '' });
  const [onDutyNurses, setOnDutyNurses] = useState([]);
  const [restrictToOnDuty, setRestrictToOnDuty] = useState(true);

  // Phase 4: Consents
  const [consents, setConsents] = useState([]);
  const [consentTemplates, setConsentTemplates] = useState([]);
  const [showConsentDialog, setShowConsentDialog] = useState(false);
  const [consentForm, setConsentForm] = useState({ consent_type: 'surgical', template_id: '', procedure_name: '', doctor_id: '', risks_explained: '', patient_signature: '', signed_by: 'patient', guardian_name: '', guardian_relationship: '', witness_name: '', witness_signature: '', notes: '' });
  const [showConsentTemplateDialog, setShowConsentTemplateDialog] = useState(false);
  const [editingConsentTemplate, setEditingConsentTemplate] = useState(null);
  const [consentTemplateForm, setConsentTemplateForm] = useState({ consent_type: 'surgical', template_name: '', content: '', language: 'english' });
  const [showWithdrawConsentDialog, setShowWithdrawConsentDialog] = useState(false);
  const [withdrawingConsent, setWithdrawingConsent] = useState(null);
  const [withdrawReason, setWithdrawReason] = useState('');

  // Phase 4: Incidents
  const [incidents, setIncidents] = useState([]);
  const [incidentFilter, setIncidentFilter] = useState({ status: '', severity: '', incident_type: '' });
  const [incidentReport, setIncidentReport] = useState(null);
  const [showIncidentDialog, setShowIncidentDialog] = useState(false);
  const [incidentForm, setIncidentForm] = useState({ incident_type: 'fall', severity: 'medium', incident_date: new Date().toISOString().slice(0, 16), admission_id: '', patient_id: '', location: '', description: '', immediate_action: '', witnessed_by: '' });
  const [showInvestigateDialog, setShowInvestigateDialog] = useState(false);
  const [investigatingIncident, setInvestigatingIncident] = useState(null);
  const [investigateForm, setInvestigateForm] = useState({ investigation_notes: '', root_cause: '', resolution: '', corrective_actions: '', preventive_measures: '', new_status: '' });

  // Phase 4: Readmissions
  const [readmissions, setReadmissions] = useState([]);

  // ICU: Intake/Output
  const [ioEntries, setIoEntries] = useState([]);
  const [ioBalance, setIoBalance] = useState(null);
  const [ioDate, setIoDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [showIoDialog, setShowIoDialog] = useState(false);
  const [ioForm, setIoForm] = useState({ io_type: 'intake', category: 'oral', amount_ml: '', shift: 'morning', notes: '' });

  // ICU: Critical lab alerts
  const [criticalAlerts, setCriticalAlerts] = useState([]);
  const [admissionCriticalAlerts, setAdmissionCriticalAlerts] = useState([]);

  // Nurse shift roster (duty schedule)
  const [rosterWeekStart, setRosterWeekStart] = useState(() => {
    // Start the week on Monday for hospital convention
    const today = new Date();
    const dow = today.getDay(); // 0=Sun, 1=Mon, ...
    const offset = dow === 0 ? -6 : 1 - dow;
    today.setDate(today.getDate() + offset);
    today.setHours(0, 0, 0, 0);
    return today;
  });
  const [rosterGrid, setRosterGrid] = useState(null);
  const [rosterCoverage, setRosterCoverage] = useState([]);
  const [rosterMinPerShift, setRosterMinPerShift] = useState(2);
  const [showRosterCellDialog, setShowRosterCellDialog] = useState(false);
  const [rosterCellEdit, setRosterCellEdit] = useState(null); // { nurse, date, shift, existing }
  const [rosterCellForm, setRosterCellForm] = useState({ status: 'working', ward: '', notes: '' });
  const [showBulkRosterDialog, setShowBulkRosterDialog] = useState(false);
  const [bulkRosterForm, setBulkRosterForm] = useState({
    nurse_ids: [], from_date: '', to_date: '', shifts: ['morning'], status: 'working', ward: '', notes: '', overwrite: false,
  });

  // Phase 4: Mortality
  const [mortalityList, setMortalityList] = useState([]);
  const [showMortalityDialog, setShowMortalityDialog] = useState(false);
  // B6 — Body release / mortuary tracking
  const [showBodyReleaseDialog, setShowBodyReleaseDialog] = useState(false);
  const [bodyReleaseAdmId, setBodyReleaseAdmId] = useState(null);
  const [bodyReleaseRec, setBodyReleaseRec] = useState(null);
  const [bodyReleaseTrack, setBodyReleaseTrack] = useState({
    mortuary_slot: '', body_in_mortuary_at: '', body_out_mortuary_at: '',
    embalming_done: false, embalming_at: '', embalmed_by: '',
    post_mortem_required: false, pm_hospital: '', pm_doctor: '',
    pm_referred_at: '', pm_completed_at: '', pm_report_received: false, pm_report_number: '',
    police_noc_required: false, police_noc_received: false,
    police_noc_number: '', police_noc_received_at: '', notes: '',
  });
  const [bodyReleaseAction, setBodyReleaseAction] = useState({
    released_to_name: '', released_to_relationship: '', released_to_phone: '',
    released_to_id_proof_type: 'aadhar', released_to_id_proof_number: '',
    released_to_address: '', witness_name: '', witness_phone: '', witness_id_proof: '',
    transport_details: '', notes: '',
    force_missing_noc: false, force_missing_pm: false, override_reason: '',
  });
  const [mortalityAdmission, setMortalityAdmission] = useState(null);
  const [mortalityForm, setMortalityForm] = useState({ cause_of_death: '', time_of_death: '', death_certificate_number: '', mlc_required: false, mlc_number: '', autopsy_done: false, autopsy_findings: '', body_handed_over_to: '', body_handover_relationship: '', body_handover_time: '', body_handover_id_proof: '' });
  // DAMA — Discharge Against Medical Advice
  const [showDamaDialog, setShowDamaDialog] = useState(false);
  const [damaAdmission, setDamaAdmission] = useState(null);
  const [damaForm, setDamaForm] = useState({
    attending_doctor_id: '', medical_advice_given: '', risks_explained: '', language_used: 'english',
    patient_acknowledges_advice: false, patient_absolves_hospital: false,
    signed_by: 'patient', guardian_name: '', guardian_relationship: '',
    primary_signature: '', primary_signature_type: 'typed',
    witness_name: '', witness_designation: '', witness_signature: '', witness_signature_type: 'typed',
    notes: '',
  });

  // Pagination
  const PAGE_SIZE = 50;
  const [admissionsPage, setAdmissionsPage] = useState(0);
  const [admissionsTotal, setAdmissionsTotal] = useState(0);
  const [dischargePage, setDischargePage] = useState(0);
  const [dischargeTotal, setDischargeTotal] = useState(0);

  // Discharge history
  const [dischargeSearch, setDischargeSearch] = useState('');
  const [dischargedAdmissions, setDischargedAdmissions] = useState([]);
  const [showDischargeDialog, setShowDischargeDialog] = useState(false);
  const [dischargeAdmission, setDischargeAdmission] = useState(null);
  const [dischargeForm, setDischargeForm] = useState({
    discharge_type: 'normal', condition_on_discharge: 'stable', discharge_summary: '',
    diagnosis_on_discharge: '', treatment_given: '', medications_prescribed: '',
    follow_up_instructions: '', follow_up_date: '', diet_instructions: '', activity_restrictions: '',
  });
  // Backend may 409 with one of three gate codes: outstanding_balance,
  // unacknowledged_critical_alerts, missing_surgical_consent. We collect the
  // details and require the user to type a single reason that overrides them.
  const [dischargeBlockers, setDischargeBlockers] = useState([]);
  const [overrideReason, setOverrideReason] = useState('');
  // Bill cancel dialog (admission bills only)
  const [cancelBillDialog, setCancelBillDialog] = useState({ open: false, bill: null, reason: '' });

  // OT Schedule
  const [otSchedules, setOtSchedules] = useState([]);
  const [showOTDialog, setShowOTDialog] = useState(false);
  const [otForm, setOtForm] = useState({
    patient_id: '', surgeon_id: '', anaesthetist_id: '', ot_room_number: '',
    procedure_name: '', procedure_id: '', scheduled_date: '', estimated_duration_minutes: '', pre_op_notes: '', admission_id: '',
  });

  // ============================================================
  // Data fetching
  // ============================================================
  const fetchDashboard = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/dashboard');
      setDashboardData(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchAdmissions = useCallback(async (status = 'admitted', page = 0) => {
    try {
      const res = await axios.get('/api/inpatient/admissions', {
        params: { status, skip: page * PAGE_SIZE, limit: PAGE_SIZE }
      });
      const { items, total } = res.data;
      if (status === 'admitted') {
        setAdmissions(items);
        setAdmissionsTotal(total);
      } else {
        setDischargedAdmissions(items);
        setDischargeTotal(total);
      }
    } catch { /* silent */ }
  }, []);

  const fetchTriageQueue = useCallback(async () => {
    setTriageLoading(true);
    try {
      const res = await axios.get('/api/inpatient/admissions/triage-queue');
      setTriageQueue(res.data?.items || []);
    } catch { setTriageQueue([]); }
    finally { setTriageLoading(false); }
  }, []);

  const fetchRooms = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/rooms');
      setRooms(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchDoctors = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/doctors');
      setDoctorsList(res.data || []);
    } catch {
      try {
        const res = await axios.get('/api/admin/users');
        const docs = (res.data || []).filter(u => (u.role_names || [u.role?.name]).some(r => r === 'doctor'));
        setDoctorsList(docs);
      } catch { /* silent */ }
    }
  }, []);

  const fetchAvailableRooms = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/rooms', { params: { available_only: true } });
      setAvailableRooms(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchVisits = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/visits`);
      setVisits(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchBill = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/bill`);
      setBillData(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchMedications = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/prescriptions`);
      setAdmissionMedications(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchLabOrders = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/lab-orders`);
      setAdmissionLabOrders(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchAvailableLabTests = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/lab-tests-available`);
      setAvailableLabTests(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchOTSchedules = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/ot');
      setOtSchedules(res.data);
    } catch { /* silent */ }
  }, []);

  const fetchVitals = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/vitals`, { params: { limit: 50 } });
      setVitals(res.data || []);
      setLatestVitals((res.data && res.data[0]) || null);
    } catch { setVitals([]); setLatestVitals(null); }
  }, []);

  const fetchAdmissionAllergies = useCallback(async (patientId) => {
    if (!patientId) { setAdmissionAllergies([]); return; }
    try {
      const res = await axios.get(`/api/patients/${patientId}/allergies`, { params: { active_only: true } });
      setAdmissionAllergies(res.data || []);
    } catch { setAdmissionAllergies([]); }
  }, []);

  const fetchMAR = useCallback(async (admissionId, date = null) => {
    try {
      const params = date ? { target_date: date } : {};
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/mar`, { params });
      setMar(res.data || []);
    } catch { setMar([]); }
  }, []);

  const fetchDeposits = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/deposits`);
      setDeposits(res.data || []);
    } catch { setDeposits([]); }
  }, []);

  const fetchBalance = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/balance`);
      setBalance(res.data);
    } catch { setBalance(null); }
  }, []);

  const fetchAncillaryCharges = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/ancillary-charges`);
      setAncillaryCharges(res.data || []);
    } catch { setAncillaryCharges([]); }
  }, []);

  const fetchAncillaryServices = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/ancillary-services', { params: { active_only: true } });
      setAncillaryServices(res.data || []);
    } catch { setAncillaryServices([]); }
  }, []);

  const fetchProcedures = useCallback(async (activeOnly = true) => {
    try {
      const res = await axios.get('/api/inpatient/procedures', { params: { active_only: activeOnly } });
      setProceduresList(res.data || []);
    } catch { setProceduresList([]); }
  }, []);

  const resetProcedureForm = () => {
    setProcedureForm({ name: '', default_rate: '', description: '' });
    setEditingProcedure(null);
  };

  const handleProcedureSubmit = async (e) => {
    e.preventDefault();
    const payload = {
      name: procedureForm.name.trim(),
      default_rate: parseFloat(procedureForm.default_rate) || 0,
      description: procedureForm.description || null,
    };
    if (!payload.name) {
      toast({ variant: 'destructive', title: 'Error', description: 'Name is required' });
      return;
    }
    try {
      if (editingProcedure) {
        await axios.put(`/api/inpatient/procedures/${editingProcedure.id}`, payload);
        toast({ title: 'Success', description: 'Procedure updated' });
      } else {
        await axios.post('/api/inpatient/procedures', payload);
        toast({ title: 'Success', description: 'Procedure added' });
      }
      setShowProcedureDialog(false);
      resetProcedureForm();
      fetchProcedures(false);
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast({
        variant: 'destructive',
        title: 'Error',
        description: typeof detail === 'string' ? detail : 'Failed to save procedure',
      });
    }
  };

  const handleProcedureDelete = (procedureId) => {
    setConfirmState({
      open: true,
      title: 'Remove procedure',
      message: 'Remove this procedure from the catalog? Existing OT records keep their values.',
      onConfirm: async () => {
        setConfirmState({ open: false });
        try {
          await axios.delete(`/api/inpatient/procedures/${procedureId}`);
          toast({ title: 'Removed', description: 'Procedure removed from catalog' });
          fetchProcedures(false);
        } catch (err) {
          const detail = err.response?.data?.detail;
          toast({
            variant: 'destructive',
            title: 'Error',
            description: typeof detail === 'string' ? detail : 'Failed to remove procedure',
          });
        }
      },
    });
  };

  const startEditProcedure = (proc) => {
    setEditingProcedure(proc);
    setProcedureForm({
      name: proc.name || '',
      default_rate: proc.default_rate ?? '',
      description: proc.description || '',
    });
    setShowProcedureDialog(true);
  };

  const fetchAdmissionBills = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/bills`);
      setAdmissionBills(res.data || []);
    } catch { setAdmissionBills([]); }
  }, []);

  const fetchAdmissionPackage = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/package`);
      setAdmissionPackage(res.data);
    } catch { setAdmissionPackage(null); }
  }, []);

  const fetchPackages = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/packages', { params: { active_only: true } });
      setPackagesList(res.data || []);
    } catch { setPackagesList([]); }
  }, []);

  const fetchTpaList = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/tpa', { params: { active_only: true } });
      setTpaList(res.data || []);
    } catch { setTpaList([]); }
  }, []);

  // Phase 3 fetchers
  const fetchTransferHistory = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/transfers`);
      setTransferHistory(res.data || []);
    } catch { setTransferHistory([]); }
  }, []);

  const fetchPendingTransfers = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/transfers/pending');
      setPendingTransfers(res.data || []);
    } catch { setPendingTransfers([]); }
  }, []);

  const fetchCleaningBeds = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/beds/needs-cleaning');
      setCleaningBeds(res.data || []);
    } catch { setCleaningBeds([]); }
  }, []);

  const fetchTurnoverStats = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/beds/turnover-stats');
      setTurnoverStats(res.data);
    } catch { setTurnoverStats(null); }
  }, []);

  const fetchReservations = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/reservations', { params: { active_only: true } });
      setReservations(res.data || []);
    } catch { setReservations([]); }
  }, []);

  const fetchNurseAssignments = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/nurse-assignments`);
      setNurseAssignments(res.data || []);
    } catch { setNurseAssignments([]); }
  }, []);

  const fetchNursesList = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/nurses');
      setNursesList(res.data || []);
    } catch {
      try {
        const res = await axios.get('/api/admin/users');
        const nurses = (res.data || []).filter(u => (u.role_names || [u.role?.name]).some(r => r === 'nurse'));
        setNursesList(nurses);
      } catch { setNursesList([]); }
    }
  }, []);

  // Phase 4 fetchers
  const fetchConsents = useCallback(async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/consents`);
      setConsents(res.data || []);
    } catch { setConsents([]); }
  }, []);

  const fetchConsentTemplates = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/consent-templates', { params: { active_only: true } });
      setConsentTemplates(res.data || []);
    } catch { setConsentTemplates([]); }
  }, []);

  const fetchIncidents = useCallback(async () => {
    try {
      const params = {};
      if (incidentFilter.status) params.status = incidentFilter.status;
      if (incidentFilter.severity) params.severity = incidentFilter.severity;
      if (incidentFilter.incident_type) params.incident_type = incidentFilter.incident_type;
      const res = await axios.get('/api/inpatient/incidents', { params });
      setIncidents(res.data || []);
    } catch { setIncidents([]); }
  }, [incidentFilter]);

  const fetchIncidentReport = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/incidents/reports/monthly');
      setIncidentReport(res.data);
    } catch { setIncidentReport(null); }
  }, []);

  const fetchReadmissions = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/reports/readmissions');
      setReadmissions(res.data || []);
    } catch { setReadmissions([]); }
  }, []);

  const fetchIoEntries = useCallback(async (admissionId, targetDate = null) => {
    try {
      const params = targetDate ? { target_date: targetDate } : {};
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/io`, { params });
      setIoEntries(res.data || []);
    } catch { setIoEntries([]); }
  }, []);

  const fetchIoBalance = useCallback(async (admissionId, targetDate = null) => {
    try {
      const params = targetDate ? { target_date: targetDate } : {};
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/io/balance`, { params });
      setIoBalance(res.data);
    } catch { setIoBalance(null); }
  }, []);

  const fetchCriticalAlerts = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/critical-alerts', { params: { status: 'new' } });
      setCriticalAlerts(res.data || []);
    } catch { setCriticalAlerts([]); }
  }, []);

  const fetchAdmissionCriticalAlerts = useCallback(async (admissionId) => {
    try {
      const res = await axios.get('/api/inpatient/critical-alerts', { params: { admission_id: admissionId } });
      setAdmissionCriticalAlerts(res.data || []);
    } catch { setAdmissionCriticalAlerts([]); }
  }, []);

  // Roster fetchers
  const _toIso = (d) => {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  };

  const fetchRosterGrid = useCallback(async () => {
    if (!rosterWeekStart) return;
    const start = new Date(rosterWeekStart);
    const end = new Date(rosterWeekStart);
    end.setDate(end.getDate() + 6);
    try {
      const res = await axios.get('/api/inpatient/roster/grid', {
        params: { from_date: _toIso(start), to_date: _toIso(end) },
      });
      setRosterGrid(res.data);
    } catch { setRosterGrid(null); }
  }, [rosterWeekStart]);

  const fetchRosterCoverage = useCallback(async () => {
    if (!rosterWeekStart) return;
    const start = new Date(rosterWeekStart);
    const end = new Date(rosterWeekStart);
    end.setDate(end.getDate() + 6);
    try {
      const res = await axios.get('/api/inpatient/roster/coverage', {
        params: { from_date: _toIso(start), to_date: _toIso(end), min_per_shift: rosterMinPerShift },
      });
      setRosterCoverage(res.data.shifts || []);
    } catch { setRosterCoverage([]); }
  }, [rosterWeekStart, rosterMinPerShift]);

  const fetchMortalityList = useCallback(async () => {
    try {
      const res = await axios.get('/api/inpatient/reports/mortality');
      setMortalityList(res.data || []);
    } catch { setMortalityList([]); }
  }, []);

  // E2 — monthly outcomes
  const fetchMonthlyOutcomes = useCallback(async (month) => {
    try {
      const params = month ? { month } : {};
      const res = await axios.get('/api/inpatient/reports/monthly-outcomes', { params });
      setOutcomesData(res.data);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to load monthly outcomes';
      toast({ variant: 'destructive', title: 'Error', description: msg });
      setOutcomesData(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // E3 — doctor productivity
  const fetchDoctorProductivity = useCallback(async (range) => {
    try {
      const params = { date_from: range.from, date_to: range.to };
      if (range.doctor_id) params.doctor_id = range.doctor_id;
      const res = await axios.get('/api/inpatient/reports/doctor-productivity', { params });
      setProductivityData(res.data);
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast({ variant: 'destructive', title: 'Error',
        description: typeof detail === 'string' ? detail : 'Failed to load doctor productivity' });
      setProductivityData(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchPreauths = useCallback(async () => {
    try {
      const params = preauthStatusFilter ? { status: preauthStatusFilter } : {};
      const res = await axios.get('/api/inpatient/preauth', { params });
      let data = res.data || [];
      if (preauthSearch) {
        const q = preauthSearch.toLowerCase();
        data = data.filter(p =>
          (p.patient_name || '').toLowerCase().includes(q) ||
          (p.insurance_provider || '').toLowerCase().includes(q) ||
          (p.tpa_name || '').toLowerCase().includes(q)
        );
      }
      setPreauths(data);
    } catch { setPreauths([]); }
  }, [preauthStatusFilter, preauthSearch]);

  useEffect(() => {
    fetchDashboard();
    fetchDoctors();
  }, [fetchDashboard, fetchDoctors]);

  useEffect(() => {
    if (activeTab === 'admissions') { fetchAdmissions('admitted', admissionsPage); fetchAvailableRooms(); }
    if (activeTab === 'triage') { fetchTriageQueue(); }
    if (activeTab === 'rooms') { fetchRooms(); }
    if (activeTab === 'discharge') fetchAdmissions('discharged', dischargePage);
    if (activeTab === 'ot') fetchOTSchedules();
    if (activeTab === 'dashboard') fetchDashboard();
    if (activeTab === 'preauth') fetchPreauths();
    if (activeTab === 'setup') {
      fetchAncillaryServices();
      fetchPackages();
      fetchTpaList();
    }
    if (activeTab === 'housekeeping') {
      fetchCleaningBeds();
      fetchTurnoverStats();
      fetchPendingTransfers();
    }
    if (activeTab === 'reservations') {
      fetchReservations();
      fetchAvailableRooms();
    }
    if (activeTab === 'incidents') {
      fetchIncidents();
      fetchIncidentReport();
    }
    if (activeTab === 'quality') {
      fetchReadmissions();
      fetchMortalityList();
    }
    if (activeTab === 'reports') {
      if (reportSubTab === 'outcomes') fetchMonthlyOutcomes(outcomesMonth);
      if (reportSubTab === 'productivity') fetchDoctorProductivity(productivityRange);
      fetchDoctors();
    }
    if (activeTab === 'roster') {
      fetchRosterGrid();
      fetchRosterCoverage();
      fetchNursesList();  // for the bulk-assign multi-select
    }
    if (activeTab === 'procedures') fetchProcedures(false);
    if (activeTab === 'ot') fetchProcedures(true);  // OT scheduling needs the active catalog
  }, [activeTab, admissionsPage, dischargePage, fetchAdmissions, fetchRooms, fetchDashboard, fetchAvailableRooms, fetchOTSchedules, fetchPreauths, fetchAncillaryServices, fetchPackages, fetchTpaList, fetchCleaningBeds, fetchTurnoverStats, fetchPendingTransfers, fetchReservations, fetchIncidents, fetchIncidentReport, fetchReadmissions, fetchMortalityList, fetchRosterGrid, fetchRosterCoverage, fetchNursesList, fetchProcedures, fetchTriageQueue]);

  // ============================================================
  // Patient search typeahead
  // ============================================================
  useEffect(() => {
    if (!patientSearchQuery.trim()) { setPatientSearchResults([]); setPatientSearching(false); return; }
    setPatientSearching(true);
    const timer = setTimeout(async () => {
      try {
        const res = await axios.post('/api/patients/search', {
          search_term: patientSearchQuery.trim(),
          sort_by: 'name',
          sort_order: 'asc',
        });
        setPatientSearchResults(res.data?.patients || []);
      } catch {
        setPatientSearchResults([]);
      } finally {
        setPatientSearching(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [patientSearchQuery]);

  // Re-fetch MAR when the date changes for an open admission
  useEffect(() => {
    if (activityAdmission && activityTab === 'mar') {
      fetchMAR(activityAdmission.id, marDate);
    }
  }, [marDate, activityAdmission, activityTab, fetchMAR]);

  // ============================================================
  // Handlers
  // ============================================================

  // Admission
  const handleCreateAdmission = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        ...admissionForm,
        patient_id: parseInt(admissionForm.patient_id),
        admitting_doctor_id: parseInt(admissionForm.admitting_doctor_id),
        room_id: parseInt(admissionForm.room_id),
        estimated_stay_days: admissionForm.estimated_stay_days ? parseInt(admissionForm.estimated_stay_days) : null,
        bed_id: admissionForm.bed_id ? parseInt(admissionForm.bed_id) : null,
        triage_level: admissionForm.triage_level ? parseInt(admissionForm.triage_level) : null,
        // Strip emergency-only fields when not an emergency admission
        ...(admissionForm.admission_type !== 'emergency' ? {
          triage_level: null, chief_complaint: null, arrival_mode: null,
          ambulance_details: null, is_mlc: false, mlc_type: null, mlc_number: null,
          police_station_informed: null, is_observation: false,
          deposit_waived: false, deposit_waiver_reason: null,
        } : {}),
      };
      await axios.post('/api/inpatient/admissions', payload);
      toast({ title: 'Success', description: 'Patient admitted successfully' });
      setShowAdmissionDialog(false);
      resetAdmissionForm();
      fetchAdmissions('admitted');
      fetchDashboard();
      fetchAvailableRooms();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to create admission';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleQuickAdmit = async (e) => {
    e.preventDefault();
    if (!quickAdmitForm.first_name.trim() || !quickAdmitForm.admitting_doctor_id || !quickAdmitForm.room_id) {
      toast({ variant: 'destructive', title: 'Missing fields', description: 'Name, doctor, and room are required.' });
      return;
    }
    if (quickAdmitForm.is_mlc && !quickAdmitForm.mlc_type) {
      toast({ variant: 'destructive', title: 'MLC type required', description: 'Select the MLC type when flagging as medico-legal.' });
      return;
    }
    setLoading(true);
    try {
      const payload = {
        ...quickAdmitForm,
        age: quickAdmitForm.age ? parseInt(quickAdmitForm.age) : null,
        admitting_doctor_id: parseInt(quickAdmitForm.admitting_doctor_id),
        room_id: parseInt(quickAdmitForm.room_id),
        bed_id: quickAdmitForm.bed_id ? parseInt(quickAdmitForm.bed_id) : null,
        triage_level: parseInt(quickAdmitForm.triage_level || '3'),
        gender: quickAdmitForm.gender || null,
        primary_phone: quickAdmitForm.primary_phone || '0000000000',
      };
      await axios.post('/api/inpatient/admissions/quick-admit', payload);
      toast({ title: 'Emergency admission created', description: 'Reception must complete patient KYC.' });
      setShowQuickAdmitDialog(false);
      setQuickAdmitForm({
        first_name: '', last_name: 'UNKNOWN', age: '', gender: '', primary_phone: '',
        admitting_doctor_id: '', room_id: '', bed_id: '',
        admission_reason: '', condition_on_admission: 'critical',
        triage_level: '1', chief_complaint: '', arrival_mode: 'walk_in', ambulance_details: '',
        is_mlc: false, mlc_type: '', mlc_number: '', police_station_informed: '',
        is_observation: false, deposit_waived: false, deposit_waiver_reason: '',
        emergency_contact: '',
      });
      fetchAdmissions('admitted');
      fetchDashboard();
      fetchAvailableRooms();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to admit patient';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const resetAdmissionForm = () => {
    setAdmissionForm({ patient_id: '', admitting_doctor_id: '', room_id: '', admission_type: 'elective',
      admission_reason: '', condition_on_admission: 'stable', estimated_stay_days: '',
      admission_notes: '', insurance_provider: '', policy_number: '', claim_reference: '', emergency_contact: '', bed_number: '', bed_id: '',
      triage_level: '', chief_complaint: '', arrival_mode: 'walk_in', ambulance_details: '',
      is_mlc: false, mlc_type: '', mlc_number: '', police_station_informed: '',
      is_observation: false, deposit_waived: false, deposit_waiver_reason: '' });
    setSelectedPatientName('');
    setSelectedPatient(null);
    setPatientSearchQuery('');
    setPatientSearchResults([]);
  };

  // Activity
  const openActivity = (admission) => {
    setActivityAdmission(admission);
    setActivityTab('visits');
    setBillDiscount({ type: 'flat', value: 0 });
    setBillTaxPct(0);
    fetchVisits(admission.id);
    fetchBill(admission.id);
    fetchMedications(admission.id);
    fetchLabOrders(admission.id);
    fetchAdmissionDocs(admission.id);
    fetchNursingNotes(admission.id);
    fetchDietOrders(admission.id);
    fetchVitals(admission.id);
    fetchAdmissionAllergies(admission.patient_id);
    fetchMAR(admission.id, marDate);
    fetchDeposits(admission.id);
    fetchBalance(admission.id);
    fetchAncillaryCharges(admission.id);
    fetchAncillaryServices();
    fetchAdmissionBills(admission.id);
    fetchAdmissionPackage(admission.id);
    fetchPackages();
    fetchTransferHistory(admission.id);
    fetchNurseAssignments(admission.id);
    fetchNursesList();
    fetchConsents(admission.id);
    fetchConsentTemplates();
    fetchIoEntries(admission.id, ioDate);
    fetchIoBalance(admission.id, ioDate);
    fetchAdmissionCriticalAlerts(admission.id);
  };

  // Re-fetch I/O when date changes
  useEffect(() => {
    if (activityAdmission && activityTab === 'io') {
      fetchIoEntries(activityAdmission.id, ioDate);
      fetchIoBalance(activityAdmission.id, ioDate);
    }
  }, [ioDate, activityAdmission, activityTab, fetchIoEntries, fetchIoBalance]);

  // Visit
  const handleCreateVisit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/visits`, {
        visit_type: visitForm.visit_type,
        visitor_id: parseInt(visitForm.visitor_id),
        notes: visitForm.notes || null,
        // Round-checklist (only sent for doctor_visit; backend ignores otherwise)
        vitals_reviewed: !!visitForm.vitals_reviewed,
        labs_reviewed: !!visitForm.labs_reviewed,
        pain_assessed: !!visitForm.pain_assessed,
        mobility_checked: !!visitForm.mobility_checked,
        plan_for_today: visitForm.plan_for_today || null,
        family_updated: !!visitForm.family_updated,
      });
      toast({ title: 'Success', description: 'Visit recorded' });
      setShowVisitDialog(false);
      setVisitForm({ visit_type: defaultVisitType, visitor_id: '', notes: '', vitals_reviewed: false, labs_reviewed: false, pain_assessed: false, mobility_checked: false, plan_for_today: '', family_updated: false });
      fetchVisits(activityAdmission.id);
      fetchBill(activityAdmission.id);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to record visit';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleDeleteVisit = async (visitId) => {
    try {
      await axios.delete(`/api/inpatient/visits/${visitId}`);
      toast({ title: 'Success', description: 'Visit deleted' });
      fetchVisits(activityAdmission.id);
      fetchBill(activityAdmission.id);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to delete' });
    }
  };

  // Inpatient prescription
  const searchMedicines = useCallback(async (query, idx) => {
    setMedicineSearchTargetIdx(idx);
    if (!query || query.trim().length < 2) { setMedicineSearchResults([]); return; }
    try {
      const res = await axios.get('/api/medicines/', { params: { search: query.trim(), limit: 15 } });
      setMedicineSearchResults(res.data || []);
    } catch { setMedicineSearchResults([]); }
  }, []);

  const handleCreateInpatientPrescription = async (e) => {
    e.preventDefault();
    const items = prescriptionForm.items
      .map(it => ({
        medicine_id: it.medicine_id ? parseInt(it.medicine_id) : null,
        medicine_name: it.medicine_id ? null : (it.medicine_name?.trim() || null),
        quantity_prescribed: Math.max(1, parseInt(it.quantity_prescribed) || 1),
        dosage: it.dosage?.trim() || '',
        duration: it.duration?.trim() || '',
        instructions: it.instructions?.trim() || null,
      }))
      .filter(it => (it.medicine_id || it.medicine_name) && it.dosage && it.duration);
    if (items.length === 0) {
      toast({ variant: 'destructive', title: 'Error', description: 'Add at least one medicine with dosage and duration' });
      return;
    }
    setLoading(true);
    try {
      await axios.post('/api/prescriptions/', {
        patient_id: activityAdmission.patient_id,
        admission_id: activityAdmission.id,
        notes: prescriptionForm.notes || null,
        items,
      });
      toast({ title: 'Prescription created' });
      setShowPrescriptionDialog(false);
      setPrescriptionForm({ notes: '', items: [{ ...BLANK_RX_ITEM }] });
      setMedicineSearchResults([]);
      fetchMedications(activityAdmission.id);
      fetchBill(activityAdmission.id);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to create prescription';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  // Lab Order
  const handleCreateLabOrder = async (e) => {
    e.preventDefault();
    if (!labOrderForm.test_ids.length) {
      toast({ variant: 'destructive', title: 'Error', description: 'Select at least one lab test' });
      return;
    }
    setLoading(true);
    try {
      await axios.post('/api/lab/orders', {
        patient_id: activityAdmission.patient_id,
        admission_id: activityAdmission.id,
        test_ids: labOrderForm.test_ids,
        priority: labOrderForm.priority,
        notes: labOrderForm.notes || null,
        force: false,
      });
      toast({ title: 'Success', description: 'Lab orders created' });
      setShowLabOrderDialog(false);
      setLabOrderForm({ test_ids: [], priority: 'normal', notes: '' });
      setLabTestSearch('');
      fetchLabOrders(activityAdmission.id);
      fetchBill(activityAdmission.id);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail?.message === 'Duplicate orders found') {
        const dupes = detail.duplicates.map(d => d.test_name).join(', ');
        toast({ variant: 'destructive', title: 'Duplicate Orders', description: `Already ordered today: ${dupes}. Remove them from selection or force-submit.` });
      } else {
        const msg = typeof detail === 'string' ? detail : 'Failed to create lab orders';
        toast({ variant: 'destructive', title: 'Error', description: msg });
      }
    } finally { setLoading(false); }
  };

  const toggleLabTest = (testId) => {
    setLabOrderForm(prev => ({
      ...prev,
      test_ids: prev.test_ids.includes(testId)
        ? prev.test_ids.filter(id => id !== testId)
        : [...prev.test_ids, testId],
    }));
  };

  // ============================================================
  // Review & Edit Final Bill — opens after discharge with the auto-computed
  // breakdown loaded as editable lines. Operator can add/remove/edit lines,
  // apply flat or percentage discount + tax, and commit the final bill.
  // ============================================================
  const openReviewBillDialog = async () => {
    if (!activityAdmission) return;
    try {
      const safeFetch = (path, params) => axios.get(path, params ? { params } : undefined).then(r => r.data).catch(() => null);
      const [billPayload, rxList, labList] = await Promise.all([
        safeFetch(`/api/inpatient/admissions/${activityAdmission.id}/bill`, { unbilled_only: true }),
        safeFetch(`/api/inpatient/admissions/${activityAdmission.id}/prescriptions`),
        safeFetch(`/api/inpatient/admissions/${activityAdmission.id}/lab-orders`),
      ]);
      const b = billPayload || {};
      const items = [];

      // Room
      if (b.room_total > 0 && b.room) {
        const rate = b.room?.charge_per_day || 0;
        const days = rate ? +(b.room_total / rate).toFixed(2) : 1;
        items.push({
          source: 'room', source_id: null,
          item_type: 'room_charge',
          item_name: `Room ${b.room.room_number || ''} (${b.room.room_type || ''}) — ${days} day${days === 1 ? '' : 's'}`,
          quantity: Math.max(1, Math.round(days)),
          unit_price: rate,
          total_price: b.room_total,
        });
      }

      // Visits — backend returns visit_summary as {visit_type: {count, total, items: [...]}}
      const visitsObj = b.visits || {};
      Object.entries(visitsObj).forEach(([vtype, group]) => {
        (group.items || []).forEach(v => {
          if (v.billed) return;
          items.push({
            source: 'visit', source_id: v.id,
            item_type: vtype,
            item_name: `${vtype.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}${v.visitor ? ' - ' + v.visitor : ''}`,
            quantity: 1,
            unit_price: parseFloat(v.amount || 0),
            total_price: parseFloat(v.amount || 0),
          });
        });
      });

      // OT
      (b.ot_entries || []).forEach(o => {
        if (o.billed) return;
        items.push({
          source: 'ot', source_id: o.id,
          item_type: 'ot_procedure',
          item_name: `OT: ${o.procedure || ''}`,
          quantity: 1,
          unit_price: parseFloat(o.total || 0),
          total_price: parseFloat(o.total || 0),
        });
      });

      // Ancillary
      (b.ancillary_entries || []).forEach(a => {
        if (a.billed) return;
        items.push({
          source: 'ancillary', source_id: a.id,
          item_type: 'ancillary',
          item_name: `${a.service_name || 'Service'}${a.category ? ' (' + a.category + ')' : ''}`,
          quantity: parseInt(a.quantity || 1),
          unit_price: parseFloat(a.unit_price || 0),
          total_price: parseFloat(a.total_amount || 0),
        });
      });

      // Pharmacy — flatten per-medicine line for unbilled pharmacy prescriptions only
      (rxList || []).forEach(rx => {
        if (rx.type !== 'pharmacy') return;
        if (rx.inpatient_bill_id) return; // already on a bill
        if (rx.status === 'pending') return; // not dispensed yet — not billable
        (rx.medicines || []).forEach(m => {
          const total = parseFloat(m.total_price || 0);
          if (total <= 0) return;
          items.push({
            source: 'pharmacy_rx', source_id: rx.id,
            item_type: 'pharmacy',
            item_name: `Rx: ${m.name || 'Medicine'}${m.dosage ? ' (' + m.dosage + ')' : ''}`,
            quantity: parseInt(m.quantity || 1),
            unit_price: parseFloat(m.unit_price || 0),
            total_price: total,
          });
        });
      });

      // Lab orders
      (labList || []).forEach(l => {
        if (l.inpatient_bill_id) return;
        if (l.status === 'cancelled') return;
        items.push({
          source: 'lab_order', source_id: l.id,
          item_type: 'lab_test',
          item_name: `Lab: ${l.test_name || 'Test'}${l.order_number ? ' (' + l.order_number + ')' : ''}`,
          quantity: 1,
          unit_price: parseFloat(l.amount || 0),
          total_price: parseFloat(l.amount || 0),
        });
      });

      setReviewBillItems(items);
      setReviewBillDiscount({ type: billDiscount.type || 'flat', value: billDiscount.value || 0 });
      setReviewBillTaxPct(billTaxPct || 0);
      setShowReviewBillDialog(true);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to load bill items';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    }
  };

  const reviewBillSubtotal = reviewBillItems.reduce((s, it) => s + (parseFloat(it.total_price) || 0), 0);
  const reviewBillDiscountAmount = (() => {
    const v = parseFloat(reviewBillDiscount.value) || 0;
    if (v <= 0) return 0;
    if (reviewBillDiscount.type === 'percentage') return Math.round(reviewBillSubtotal * v) / 100;
    return Math.min(v, reviewBillSubtotal);
  })();
  const reviewBillAfterDiscount = Math.max(0, reviewBillSubtotal - reviewBillDiscountAmount);
  const reviewBillTaxAmount = (() => {
    const t = parseFloat(reviewBillTaxPct) || 0;
    if (t <= 0) return 0;
    return Math.round(reviewBillAfterDiscount * t) / 100;
  })();
  const reviewBillGrandTotal = +(reviewBillAfterDiscount + reviewBillTaxAmount).toFixed(2);

  const handleSubmitReviewedBill = async () => {
    if (!activityAdmission) return;
    if (reviewBillItems.length === 0) {
      toast({ variant: 'destructive', title: 'Error', description: 'At least one bill line is required' });
      return;
    }
    setLoading(true);
    try {
      const payload = {
        items_override: reviewBillItems.map(it => ({
          source: it.source || 'custom',
          source_id: it.source_id || null,
          item_type: it.item_type || 'custom',
          item_name: it.item_name || '',
          quantity: Math.max(1, parseInt(it.quantity) || 1),
          unit_price: parseFloat(it.unit_price) || 0,
          total_price: parseFloat(it.total_price) || 0,
        })),
      };
      if (parseFloat(reviewBillDiscount.value) > 0) {
        payload.discount_type = reviewBillDiscount.type;
        payload.discount_value = parseFloat(reviewBillDiscount.value);
      }
      if (parseFloat(reviewBillTaxPct) > 0) {
        payload.tax_percentage = parseFloat(reviewBillTaxPct);
      }
      const res = await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/bill/finalize`, payload);
      toast({ title: 'Bill finalized', description: `${res.data.bill_number} — ₹${res.data.total_amount}` });
      setShowReviewBillDialog(false);
      fetchBill(activityAdmission.id);
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : (detail?.message || 'Failed to finalize bill');
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  // Finalize bill
  const handleFinalizeBill = async () => {
    if (!activityAdmission) return;
    setLoading(true);
    try {
      const payload = {};
      if (billDiscount.value > 0) {
        payload.discount_type = billDiscount.type;
        payload.discount_value = parseFloat(billDiscount.value);
      }
      if (billTaxPct > 0) {
        payload.tax_percentage = parseFloat(billTaxPct);
      }
      const res = await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/bill/finalize`, payload);
      toast({ title: 'Success', description: `Bill ${res.data.bill_number} finalized — Total: ₹${res.data.total_amount}` });
      fetchBill(activityAdmission.id);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to finalize bill' });
    } finally { setLoading(false); }
  };

  // Insurance claim status update
  const handleClaimStatusUpdate = async (admissionId, data) => {
    setLoading(true);
    try {
      const res = await axios.put(`/api/inpatient/admissions/${admissionId}/claim-status`, data);
      toast({ title: 'Success', description: `Claim status updated to ${data.claim_status}` });
      // Update activityAdmission in place
      setActivityAdmission(prev => prev ? { ...prev, ...res.data } : prev);
      // Refresh admissions list
      fetchAdmissions();
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast({ variant: 'destructive', title: 'Error', description: typeof detail === 'string' ? detail : 'Failed to update claim status' });
    } finally { setLoading(false); }
  };

  // Discharge
  const openDischargeDialog = async (admission) => {
    setDischargeAdmission(admission);
    // Discharge medications are NOT auto-filled from inpatient prescriptions —
    // ward drugs and take-home prescriptions are separate clinical concepts.
    // Doctor builds the take-home list explicitly.
    setDischargeForm({ discharge_type: 'normal', condition_on_discharge: 'stable', discharge_summary: '',
      diagnosis_on_discharge: '', treatment_given: '', medications_prescribed: '',
      take_home_medications: [],
      follow_up_instructions: '', follow_up_date: '', diet_instructions: '', activity_restrictions: '' });
    setDischargeBlockers([]);
    setOverrideReason('');
    setShowDischargeDialog(true);
  };

  const handleDischarge = async (e) => {
    e.preventDefault();
    // If gates are blocking, require a non-empty override_reason before retrying.
    if (dischargeBlockers.length > 0 && !overrideReason.trim()) {
      toast({ variant: 'destructive', title: 'Override reason required',
        description: 'Type a reason to override the safety gates.' });
      return;
    }
    setLoading(true);
    try {
      const payload = { ...dischargeForm };
      if (payload.follow_up_date) payload.follow_up_date = new Date(payload.follow_up_date).toISOString();
      else delete payload.follow_up_date;
      // Clean the take-home meds: drop empty rows; coerce quantity to int.
      const meds = (payload.take_home_medications || [])
        .filter(m => (m.medicine_name || '').trim())
        .map(m => ({
          medicine_id: m.medicine_id ? parseInt(m.medicine_id) : null,
          medicine_name: m.medicine_name.trim(),
          dosage: m.dosage?.trim() || null,
          frequency: m.frequency?.trim() || null,
          duration: m.duration?.trim() || null,
          quantity: m.quantity ? parseInt(m.quantity) : null,
          instructions: m.instructions?.trim() || null,
        }));
      payload.take_home_medications = meds.length ? meds : null;
      // Don't send the legacy free-text dump; the structured list replaces it.
      payload.medications_prescribed = payload.medications_prescribed || null;
      // If we previously hit gates, attach the matching force flags + reason.
      if (dischargeBlockers.length > 0) {
        const codes = dischargeBlockers.map(b => b.code);
        if (codes.includes('outstanding_balance')) payload.force_outstanding_balance = true;
        if (codes.includes('unacknowledged_critical_alerts')) payload.force_unacknowledged_alerts = true;
        if (codes.includes('missing_surgical_consent')) payload.force_missing_consents = true;
        payload.override_reason = overrideReason.trim();
      }
      await axios.post(`/api/inpatient/admissions/${dischargeAdmission.id}/discharge`, payload);
      const wasDeath = dischargeForm.discharge_type === 'death';
      const wasDama = dischargeForm.discharge_type === 'against_advice';
      const admDoctorId = dischargeAdmission.admitting_doctor_id;
      toast({ title: wasDeath ? 'Discharge recorded — please fill mortality details'
        : wasDama ? 'Discharge recorded — please complete the DAMA form'
        : 'Patient discharged successfully' });
      setShowDischargeDialog(false);
      const admId = dischargeAdmission.id;
      setDischargeAdmission(null);
      fetchAdmissions('admitted');
      fetchDashboard();
      if (activityAdmission?.id === admId) setActivityAdmission(null);
      // On death, immediately prompt for mortality details
      if (wasDeath) {
        setMortalityAdmission({ id: admId, discharge: {} });
        setMortalityForm({
          cause_of_death: dischargeForm.diagnosis_on_discharge || '',
          time_of_death: new Date().toISOString().slice(0, 16),
          death_certificate_number: '', mlc_required: false, mlc_number: '',
          autopsy_done: false, autopsy_findings: '',
          body_handed_over_to: '', body_handover_relationship: '',
          body_handover_time: '', body_handover_id_proof: '',
        });
        setShowMortalityDialog(true);
      }
      // On DAMA, immediately prompt for the signed form
      if (wasDama) {
        setDamaAdmission({ id: admId });
        setDamaForm({
          attending_doctor_id: admDoctorId || '',
          medical_advice_given: dischargeForm.treatment_given || '',
          risks_explained: '',
          language_used: 'english',
          patient_acknowledges_advice: false, patient_absolves_hospital: false,
          signed_by: 'patient', guardian_name: '', guardian_relationship: '',
          primary_signature: '', primary_signature_type: 'typed',
          witness_name: '', witness_designation: '', witness_signature: '', witness_signature_type: 'typed',
          notes: '',
        });
        setShowDamaDialog(true);
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      const isGate = err.response?.status === 409 && detail && typeof detail === 'object' && detail.code &&
        ['outstanding_balance', 'unacknowledged_critical_alerts', 'missing_surgical_consent'].includes(detail.code);
      const isLoaBlock = err.response?.status === 409 && detail && typeof detail === 'object' && detail.code === 'active_loa';
      if (isGate) {
        // Accumulate blockers — the next retry may surface another gate, and
        // we want all override flags set when the user finally confirms.
        setDischargeBlockers(prev => prev.some(b => b.code === detail.code) ? prev : [...prev, detail]);
        // Keep the dialog open so the user can read the blockers and type a reason.
      } else if (isLoaBlock) {
        toast({ variant: 'destructive', title: 'Patient is on Leave',
          description: 'Mark the LOA as returned, no-show, or cancelled before discharging.' });
      } else {
        const msg = typeof detail === 'string' ? detail : 'Failed to discharge patient';
        toast({ variant: 'destructive', title: 'Error', description: msg });
      }
    } finally { setLoading(false); }
  };

  const handleCancelBill = async () => {
    if (!cancelBillDialog.bill || !cancelBillDialog.reason.trim()) {
      toast({ variant: 'destructive', title: 'Reason required',
        description: 'Type why you are cancelling this bill.' });
      return;
    }
    setLoading(true);
    try {
      const billId = cancelBillDialog.bill.id;
      const admId = activityAdmission?.id || dischargeAdmission?.id;
      const res = await axios.post(
        `/api/inpatient/admissions/${admId}/bills/${billId}/cancel`,
        { reason: cancelBillDialog.reason.trim() },
      );
      const r = res.data?.released || {};
      const released = (r.visits || 0) + (r.ot || 0) + (r.ancillary || 0) + (r.prescriptions || 0) + (r.lab_orders || 0);
      toast({ title: 'Bill cancelled', description: `Released ${released} item(s) for re-billing.` });
      setCancelBillDialog({ open: false, bill: null, reason: '' });
      if (admId) {
        fetchAdmissionBills(admId);
        // Refresh bill preview if the activity panel is showing it
        try { await axios.get(`/api/inpatient/admissions/${admId}/bill`); } catch { /* ignore */ }
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      let msg = 'Failed to cancel bill';
      if (typeof detail === 'string') msg = detail;
      else if (detail?.code === 'bill_has_payments') msg = `Cannot cancel — ₹${detail.amount_paid} has been paid. Refund first.`;
      else if (detail?.message) msg = detail.message;
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  // Room CRUD
  const handleSaveRoom = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = { ...roomForm, bed_count: parseInt(roomForm.bed_count), room_charge_per_day: parseFloat(roomForm.room_charge_per_day) };
      if (editingRoom) {
        await axios.put(`/api/inpatient/rooms/${editingRoom.id}`, payload);
        toast({ title: 'Success', description: 'Room updated' });
      } else {
        await axios.post('/api/inpatient/rooms', payload);
        toast({ title: 'Success', description: 'Room created' });
      }
      setShowRoomDialog(false);
      setEditingRoom(null);
      resetRoomForm();
      fetchRooms();
      fetchDashboard();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to save room' });
    } finally { setLoading(false); }
  };

  const resetRoomForm = () => setRoomForm({ room_number: '', room_type: 'general', floor: '', department: '', bed_count: 1, room_charge_per_day: '', amenities: '' });

  const handleEditRoom = (room) => {
    setEditingRoom(room);
    setRoomForm({ room_number: room.room_number, room_type: room.room_type, floor: room.floor || '', department: room.department || '',
      bed_count: room.bed_count, room_charge_per_day: room.room_charge_per_day, amenities: room.amenities || '' });
    setShowRoomDialog(true);
  };

  const handleDeleteRoom = async (roomId) => {
    try {
      await axios.delete(`/api/inpatient/rooms/${roomId}`);
      toast({ title: 'Success', description: 'Room deactivated' });
      fetchRooms();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to delete room' });
    }
  };

  // Bed Management
  const fetchBeds = async (roomId) => {
    try {
      const res = await axios.get(`/api/inpatient/rooms/${roomId}/beds`);
      setRoomBeds(res.data);
    } catch { setRoomBeds([]); }
  };

  const openBedManager = (room) => {
    setSelectedRoomForBeds(room);
    fetchBeds(room.id);
    setNewBedLabel('');
    setShowBedManager(true);
  };

  const handleAddBed = async () => {
    if (!newBedLabel.trim() || !selectedRoomForBeds) return;
    try {
      await axios.post(`/api/inpatient/rooms/${selectedRoomForBeds.id}/beds`, { bed_label: newBedLabel.trim() });
      setNewBedLabel('');
      fetchBeds(selectedRoomForBeds.id);
      fetchRooms();
      toast({ title: 'Success', description: 'Bed added' });
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to add bed' });
    }
  };

  const handleUpdateBedStatus = async (bedId, newStatus) => {
    try {
      await axios.patch(`/api/inpatient/beds/${bedId}`, { status: newStatus });
      fetchBeds(selectedRoomForBeds.id);
      fetchRooms();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to update bed' });
    }
  };

  const handleDeleteBed = async (bedId) => {
    try {
      await axios.delete(`/api/inpatient/beds/${bedId}`);
      fetchBeds(selectedRoomForBeds.id);
      fetchRooms();
      toast({ title: 'Success', description: 'Bed removed' });
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to delete bed' });
    }
  };

  // Admission Documents
  const fetchAdmissionDocs = async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/documents`);
      setAdmissionDocs(res.data);
    } catch { setAdmissionDocs([]); }
  };

  const handleDocUpload = async (admissionId, file, docType, docName, notes) => {
    setDocUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('document_type', docType);
      formData.append('document_name', docName || file.name);
      if (notes) formData.append('notes', notes);
      await axios.post(`/api/inpatient/admissions/${admissionId}/documents`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      toast({ title: 'Success', description: 'Document uploaded' });
      fetchAdmissionDocs(admissionId);
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast({ variant: 'destructive', title: 'Error', description: typeof detail === 'string' ? detail : 'Upload failed' });
    } finally { setDocUploading(false); }
  };

  const handleDocDelete = async (docId) => {
    try {
      await axios.delete(`/api/inpatient/documents/${docId}`);
      toast({ title: 'Success', description: 'Document deleted' });
      if (activityAdmission) fetchAdmissionDocs(activityAdmission.id);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to delete document' });
    }
  };

  // Nursing Notes
  const fetchNursingNotes = async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/nursing-notes`);
      setNursingNotes(res.data);
    } catch { setNursingNotes([]); }
  };

  const handleCreateNursingNote = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (editingNursingNote) {
        await axios.put(`/api/inpatient/nursing-notes/${editingNursingNote.id}`, nursingNoteForm);
        toast({ title: 'Success', description: 'Nursing note updated' });
      } else {
        await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/nursing-notes`, nursingNoteForm);
        toast({ title: 'Success', description: 'Nursing note added' });
      }
      setShowNursingNoteDialog(false);
      setEditingNursingNote(null);
      setNursingNoteForm({ shift: 'morning', note_type: 'general', content: '' });
      fetchNursingNotes(activityAdmission.id);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to save nursing note';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleDeleteNursingNote = async (noteId) => {
    try {
      await axios.delete(`/api/inpatient/nursing-notes/${noteId}`);
      toast({ title: 'Success', description: 'Nursing note deleted' });
      fetchNursingNotes(activityAdmission.id);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to delete nursing note' });
    }
  };

  // Diet Orders
  const fetchDietOrders = async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/diet-orders`);
      setDietOrders(res.data);
    } catch { setDietOrders([]); }
  };

  const handleCreateDietOrder = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/diet-orders`, dietForm);
      toast({ title: 'Success', description: 'Diet order created' });
      setShowDietDialog(false);
      setDietForm({ diet_type: 'regular', meal_instructions: '', allergies: '', notes: '' });
      fetchDietOrders(activityAdmission.id);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to create diet order';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleToggleDietOrder = async (orderId, isActive) => {
    try {
      await axios.put(`/api/inpatient/diet-orders/${orderId}`, { is_active: !isActive });
      toast({ title: 'Success', description: isActive ? 'Diet order deactivated' : 'Diet order reactivated' });
      fetchDietOrders(activityAdmission.id);
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to update diet order' });
    }
  };

  const handleDeleteDietOrder = async (orderId) => {
    try {
      await axios.delete(`/api/inpatient/diet-orders/${orderId}`);
      toast({ title: 'Success', description: 'Diet order deleted' });
      fetchDietOrders(activityAdmission.id);
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to delete diet order' });
    }
  };

  const handleLogMeal = async () => {
    if (!mealLogDialog.orderId) return;
    setLoading(true);
    try {
      await axios.post(`/api/inpatient/diet-orders/${mealLogDialog.orderId}/meal-log`, {
        meal_time: mealLogDialog.meal_time,
        status: mealLogDialog.status,
        notes: mealLogDialog.notes || null,
      });
      toast({ title: 'Meal logged', description: `${mealLogDialog.meal_time}: ${mealLogDialog.status}` });
      setMealLogDialog({ open: false, orderId: null, meal_time: 'lunch', status: 'served', notes: '' });
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to log meal';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handlePrintKitchenTicket = async () => {
    const params = { meal_time: kitchenTicketDialog.meal_time, include_header: true };
    if (kitchenTicketDialog.department.trim()) params.department = kitchenTicketDialog.department.trim();
    setKitchenTicketDialog({ open: false, meal_time: 'lunch', department: '' });
    await printPdfFromUrl(`/api/inpatient/diet/kitchen-ticket/pdf`, params);
  };

  const fetchLoaList = useCallback(async (admissionId) => {
    if (!admissionId) return;
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/loa`);
      setLoaList(res.data || []);
    } catch { setLoaList([]); }
  }, []);

  const openLoaDialog = (admission) => {
    const nowLocal = new Date().toISOString().slice(0, 16);
    const tomorrowLocal = new Date(Date.now() + 24 * 3600 * 1000).toISOString().slice(0, 16);
    setLoaDialog({
      open: true, admissionId: admission.id,
      start_datetime: nowLocal,
      expected_return_datetime: tomorrowLocal,
      reason: '',
      approved_by_doctor_id: admission.admitting_doctor_id || '',
      notes: '', bed_held: true,
    });
    fetchLoaList(admission.id);
  };

  const handleCreateLoa = async () => {
    if (!loaDialog.reason.trim() || !loaDialog.approved_by_doctor_id) {
      toast({ variant: 'destructive', title: 'Missing fields',
        description: 'Reason and approving doctor are required.' });
      return;
    }
    setLoading(true);
    try {
      await axios.post(`/api/inpatient/admissions/${loaDialog.admissionId}/loa`, {
        start_datetime: new Date(loaDialog.start_datetime).toISOString(),
        expected_return_datetime: new Date(loaDialog.expected_return_datetime).toISOString(),
        reason: loaDialog.reason.trim(),
        approved_by_doctor_id: parseInt(loaDialog.approved_by_doctor_id, 10),
        notes: loaDialog.notes || null,
        bed_held: !!loaDialog.bed_held,
      });
      toast({ title: 'LOA started' });
      fetchLoaList(loaDialog.admissionId);
      fetchAdmissions('admitted');
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to start LOA';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleLoaAction = async (loaId, action) => {
    setLoading(true);
    try {
      await axios.patch(`/api/inpatient/loa/${loaId}/${action}`, action === 'return' ? {} : undefined);
      toast({ title: action === 'return' ? 'Patient marked returned' :
        action === 'cancel' ? 'LOA cancelled' : 'LOA marked as no-show' });
      if (loaDialog.admissionId) fetchLoaList(loaDialog.admissionId);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error',
        description: err.response?.data?.detail || 'Failed' });
    } finally { setLoading(false); }
  };

  // Vitals
  const handleRecordVitals = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {};
      Object.entries(vitalsForm).forEach(([k, v]) => {
        if (v === '' || v === null) return;
        if (['bp_systolic', 'bp_diastolic', 'heart_rate', 'respiratory_rate', 'spo2', 'pain_score', 'gcs_score'].includes(k)) {
          payload[k] = parseInt(v);
        } else if (['temperature_c', 'blood_glucose', 'weight_kg', 'height_cm'].includes(k)) {
          payload[k] = parseFloat(v);
        } else {
          payload[k] = v;
        }
      });
      await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/vitals`, payload);
      toast({ title: 'Vitals recorded' });
      setShowVitalsDialog(false);
      setVitalsForm(VITALS_BLANK);
      fetchVitals(activityAdmission.id);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to record vitals';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleDeleteVitals = async (vitalId) => {
    try {
      await axios.delete(`/api/inpatient/vitals/${vitalId}`);
      toast({ title: 'Vitals entry removed' });
      fetchVitals(activityAdmission.id);
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to delete entry' });
    }
  };

  // Allergies
  const handleCreateAllergy = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post(`/api/patients/${activityAdmission.patient_id}/allergies`, allergyForm);
      toast({ title: 'Allergy recorded' });
      setShowAllergyDialog(false);
      setAllergyForm({ allergy_type: 'drug', allergen: '', severity: 'moderate', reaction: '', notes: '' });
      fetchAdmissionAllergies(activityAdmission.patient_id);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to record allergy';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleDeleteAllergy = async (allergyId) => {
    try {
      await axios.delete(`/api/patients/allergies/${allergyId}`);
      toast({ title: 'Allergy removed' });
      fetchAdmissionAllergies(activityAdmission.patient_id);
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to delete allergy' });
    }
  };

  // MAR
  const handleGenerateMAR = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/mar/generate`, null, { params: { horizon_hours: 24 } });
      toast({ title: 'MAR generated', description: `${res.data.created} new doses scheduled (${res.data.skipped_existing} already existed)` });
      fetchMAR(activityAdmission.id, marDate);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to generate MAR' });
    } finally { setLoading(false); }
  };

  const openAdministerDialog = (dose) => {
    setAdministeringDose(dose);
    setAdministerForm({
      status: 'given',
      dose_given: dose.dosage || '',
      route: dose.route || '',
      site: '',
      reason_if_not_given: '',
      notes: '',
    });
    setShowAdministerDialog(true);
  };

  const handleAdminister = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = { ...administerForm };
      if (payload.status === 'given') {
        delete payload.reason_if_not_given;
      }
      await axios.post(`/api/inpatient/mar/${administeringDose.id}/administer`, payload);
      toast({ title: 'Dose updated' });
      setShowAdministerDialog(false);
      fetchMAR(activityAdmission.id, marDate);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to update dose';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  // Phase 2: Deposits + Refund
  const handleCreateDeposit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/deposits`, {
        amount: parseFloat(depositForm.amount),
        payment_method: depositForm.payment_method,
        deposit_type: depositForm.deposit_type,
        reference_number: depositForm.reference_number || null,
        notes: depositForm.notes || null,
      });
      toast({ title: 'Deposit recorded' });
      setShowDepositDialog(false);
      setDepositForm({ amount: '', payment_method: 'cash', deposit_type: 'topup', reference_number: '', notes: '' });
      fetchDeposits(activityAdmission.id);
      fetchBalance(activityAdmission.id);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to record deposit';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleCreateRefund = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/refund`, {
        amount: parseFloat(refundForm.amount),
        payment_method: refundForm.payment_method,
        reference_number: refundForm.reference_number || null,
        notes: refundForm.notes || null,
      });
      toast({ title: 'Refund issued' });
      setShowRefundDialog(false);
      setRefundForm({ amount: '', payment_method: 'cash', reference_number: '', notes: '' });
      fetchDeposits(activityAdmission.id);
      fetchBalance(activityAdmission.id);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to issue refund';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handlePrintDepositReceipt = async (depositId) => {
    await printPdfFromUrl(`/api/inpatient/deposits/${depositId}/receipt/pdf`, { include_header: true });
  };

  // Phase 2: Ancillary charge
  const handleCreateAncillaryCharge = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        service_id: parseInt(ancillaryForm.service_id),
        quantity: parseFloat(ancillaryForm.quantity) || 1,
        notes: ancillaryForm.notes || null,
      };
      if (ancillaryForm.unit_price) payload.unit_price = parseFloat(ancillaryForm.unit_price);
      await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/ancillary-charges`, payload);
      toast({ title: 'Charge added' });
      setShowAncillaryDialog(false);
      setAncillaryForm({ service_id: '', quantity: 1, unit_price: '', notes: '' });
      fetchAncillaryCharges(activityAdmission.id);
      fetchBill(activityAdmission.id);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to add charge';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleDeleteAncillaryCharge = async (chargeId) => {
    try {
      await axios.delete(`/api/inpatient/ancillary-charges/${chargeId}`);
      toast({ title: 'Charge removed' });
      fetchAncillaryCharges(activityAdmission.id);
      fetchBill(activityAdmission.id);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed' });
    }
  };

  // Phase 2: Interim bill
  const handleGenerateInterim = async () => {
    setLoading(true);
    try {
      const payload = {
        discount_type: billDiscount.type,
        discount_value: billDiscount.value || 0,
        tax_percentage: billTaxPct || 0,
      };
      const res = await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/bill/interim`, payload);
      toast({ title: 'Interim bill created', description: `${res.data.bill_number} — ₹${res.data.total_amount.toFixed(2)}` });
      fetchBill(activityAdmission.id);
      fetchAdmissionBills(activityAdmission.id);
      fetchBalance(activityAdmission.id);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to create interim bill';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  // Phase 2: Apply / remove package
  const handleApplyPackage = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        package_id: parseInt(applyPackageForm.package_id),
        notes: applyPackageForm.notes || null,
      };
      if (applyPackageForm.agreed_price) payload.agreed_price = parseFloat(applyPackageForm.agreed_price);
      await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/package`, payload);
      toast({ title: 'Package applied' });
      setShowApplyPackageDialog(false);
      setApplyPackageForm({ package_id: '', agreed_price: '', notes: '' });
      fetchAdmissionPackage(activityAdmission.id);
      fetchBill(activityAdmission.id);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to apply package';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleRemovePackage = async () => {
    try {
      await axios.delete(`/api/inpatient/admissions/${activityAdmission.id}/package`);
      toast({ title: 'Package removed' });
      fetchAdmissionPackage(activityAdmission.id);
      fetchBill(activityAdmission.id);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed' });
    }
  };

  // Phase 2: Catalog CRUD
  const handleSubmitService = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        ...serviceForm,
        default_charge: parseFloat(serviceForm.default_charge) || 0,
      };
      if (editingService) {
        await axios.put(`/api/inpatient/ancillary-services/${editingService.id}`, payload);
      } else {
        await axios.post('/api/inpatient/ancillary-services', payload);
      }
      toast({ title: 'Service saved' });
      setShowServiceDialog(false);
      setEditingService(null);
      setServiceForm({ service_name: '', service_code: '', category: 'imaging', default_charge: '', charge_unit: 'per_session', description: '' });
      fetchAncillaryServices();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleDeleteService = async (id) => {
    try {
      await axios.delete(`/api/inpatient/ancillary-services/${id}`);
      toast({ title: 'Service deactivated' });
      fetchAncillaryServices();
    } catch { toast({ variant: 'destructive', title: 'Error', description: 'Failed' }); }
  };

  const handleSubmitPackage = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        ...packageForm,
        base_price: parseFloat(packageForm.base_price) || 0,
        included_stay_days: parseInt(packageForm.included_stay_days) || 0,
        excess_per_day_charge: parseFloat(packageForm.excess_per_day_charge) || 0,
      };
      if (editingPackage) {
        await axios.put(`/api/inpatient/packages/${editingPackage.id}`, payload);
      } else {
        await axios.post('/api/inpatient/packages', payload);
      }
      toast({ title: 'Package saved' });
      setShowPackageDialog(false);
      setEditingPackage(null);
      setPackageForm({ package_name: '', package_code: '', base_price: '', included_room_type: '', included_stay_days: 0, included_services: [], excess_per_day_charge: 0, description: '' });
      fetchPackages();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleDeletePackage = async (id) => {
    try {
      await axios.delete(`/api/inpatient/packages/${id}`);
      toast({ title: 'Package deactivated' });
      fetchPackages();
    } catch { toast({ variant: 'destructive', title: 'Error', description: 'Failed' }); }
  };

  const handleSubmitTpa = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        ...tpaForm,
        default_discount_percent: parseFloat(tpaForm.default_discount_percent) || 0,
      };
      if (editingTpa) {
        await axios.put(`/api/inpatient/tpa/${editingTpa.id}`, payload);
      } else {
        await axios.post('/api/inpatient/tpa', payload);
      }
      toast({ title: 'TPA saved' });
      setShowTpaDialog(false);
      setEditingTpa(null);
      setTpaForm({ tpa_name: '', tpa_code: '', address: '', phone: '', email: '', default_discount_percent: 0, contract_details: '' });
      fetchTpaList();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleDeleteTpa = async (id) => {
    try {
      await axios.delete(`/api/inpatient/tpa/${id}`);
      toast({ title: 'TPA deactivated' });
      fetchTpaList();
    } catch { toast({ variant: 'destructive', title: 'Error', description: 'Failed' }); }
  };

  // Phase 2: Pre-auth
  const handleCreatePreauth = async (e) => {
    e.preventDefault();
    if (!preauthSelectedPatient) {
      toast({ variant: 'destructive', title: 'Error', description: 'Pick a patient' });
      return;
    }
    setLoading(true);
    try {
      const payload = {
        patient_id: preauthSelectedPatient.id,
        admission_id: preauthForm.admission_id ? parseInt(preauthForm.admission_id) : null,
        insurance_provider: preauthForm.insurance_provider,
        policy_number: preauthForm.policy_number || null,
        tpa_id: preauthForm.tpa_id ? parseInt(preauthForm.tpa_id) : null,
        requested_amount: parseFloat(preauthForm.requested_amount),
        notes: preauthForm.notes || null,
      };
      await axios.post('/api/inpatient/preauth', payload);
      toast({ title: 'Pre-authorisation requested' });
      setShowPreauthDialog(false);
      setPreauthForm({ patient_id: '', admission_id: '', insurance_provider: '', policy_number: '', tpa_id: '', requested_amount: '', notes: '' });
      setPreauthSelectedPatient(null);
      fetchPreauths();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handlePreauthDecision = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        status: preauthDecisionForm.status,
        approved_amount: preauthDecisionForm.approved_amount ? parseFloat(preauthDecisionForm.approved_amount) : null,
        validity_days: preauthDecisionForm.validity_days ? parseInt(preauthDecisionForm.validity_days) : null,
        approval_reference: preauthDecisionForm.approval_reference || null,
        notes: preauthDecisionForm.notes || null,
      };
      await axios.post(`/api/inpatient/preauth/${activePreauth.id}/decision`, payload);
      toast({ title: 'Decision recorded' });
      setShowPreauthDecisionDialog(false);
      fetchPreauths();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  // Phase 2: Bill split
  const openSplitDialog = async (bill) => {
    setBillForSplit(bill);
    try {
      const res = await axios.get(`/api/inpatient/bills/${bill.id}/split`);
      const existing = res.data || [];
      if (existing.length > 0) {
        setSplitRows(existing.map(s => ({ payer_type: s.payer_type, payer_name: s.payer_name, tpa_id: s.tpa_id || '', amount: s.amount })));
      } else {
        setSplitRows([{ payer_type: 'cash', payer_name: 'Patient', tpa_id: '', amount: bill.total_amount }]);
      }
    } catch { setSplitRows([{ payer_type: 'cash', payer_name: 'Patient', tpa_id: '', amount: bill.total_amount }]); }
    fetchTpaList();
    setShowSplitDialog(true);
  };

  const handleSubmitSplit = async (e) => {
    e.preventDefault();
    const total = splitRows.reduce((s, r) => s + (parseFloat(r.amount) || 0), 0);
    if (Math.abs(total - billForSplit.total_amount) > 0.01) {
      toast({ variant: 'destructive', title: 'Error', description: `Splits sum to ₹${total.toFixed(2)}, must equal ₹${billForSplit.total_amount.toFixed(2)}` });
      return;
    }
    setLoading(true);
    try {
      await axios.post(`/api/inpatient/bills/${billForSplit.id}/split`, {
        splits: splitRows.map(r => ({
          payer_type: r.payer_type,
          payer_name: r.payer_name,
          tpa_id: r.tpa_id ? parseInt(r.tpa_id) : null,
          amount: parseFloat(r.amount),
        })),
      });
      toast({ title: 'Bill split saved' });
      setShowSplitDialog(false);
      setBillForSplit(null);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  // OT charges
  const openOTChargesDialog = (ot) => {
    setEditingOT(ot);
    setOtChargesForm({
      surgeon_fee: ot.surgeon_fee || 0,
      anaesthetist_fee: ot.anaesthetist_fee || 0,
      ot_room_charge: ot.ot_room_charge || 0,
      equipment_charge: ot.equipment_charge || 0,
      consumables_charge: ot.consumables_charge || 0,
      procedure_charge: ot.procedure_charge || 0,
      other_charges: ot.other_charges || 0,
    });
    setShowOTChargesDialog(true);
  };

  const handleSaveOTCharges = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {};
      Object.entries(otChargesForm).forEach(([k, v]) => {
        const num = parseFloat(v);
        if (!isNaN(num)) payload[k] = num;
      });
      await axios.put(`/api/inpatient/ot/${editingOT.id}/charges`, payload);
      toast({ title: 'OT charges saved' });
      setShowOTChargesDialog(false);
      fetchOTSchedules();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  // Phase 3: Inter-ward transfer
  const handleInitiateWardTransfer = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        to_room_id: parseInt(wardTransferForm.to_room_id),
        to_bed_id: wardTransferForm.to_bed_id ? parseInt(wardTransferForm.to_bed_id) : null,
        reason: wardTransferForm.reason,
        transfer_note: wardTransferForm.transfer_note,
      };
      await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/transfer-ward`, payload);
      toast({ title: 'Ward transfer initiated', description: 'Awaiting acceptance by receiving ward' });
      setShowWardTransferDialog(false);
      setWardTransferForm({ to_room_id: '', to_bed_id: '', reason: '', transfer_note: '' });
      fetchTransferHistory(activityAdmission.id);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleAcceptTransfer = async (transferId) => {
    try {
      await axios.patch(`/api/inpatient/transfers/${transferId}/accept`);
      toast({ title: 'Transfer accepted' });
      if (activityAdmission) fetchTransferHistory(activityAdmission.id);
      fetchPendingTransfers();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    }
  };

  const handleCancelPendingTransfer = async (transferId) => {
    try {
      await axios.patch(`/api/inpatient/transfers/${transferId}/cancel`);
      toast({ title: 'Transfer cancelled' });
      if (activityAdmission) fetchTransferHistory(activityAdmission.id);
      fetchPendingTransfers();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed' });
    }
  };

  // Phase 3: Housekeeping
  const handleMarkBedAvailable = async (bedId) => {
    try {
      await axios.patch(`/api/inpatient/beds/${bedId}/status`, { status: 'available' });
      toast({ title: 'Bed marked available' });
      fetchCleaningBeds();
      fetchTurnoverStats();
      fetchRooms();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed' });
    }
  };

  const handleMarkBedMaintenance = async (bedId, status) => {
    try {
      await axios.patch(`/api/inpatient/beds/${bedId}/status`, { status });
      toast({ title: `Bed marked ${status}` });
      fetchCleaningBeds();
      fetchRooms();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed' });
    }
  };

  // Phase 3: Reservations
  const handleCreateReservation = async (e) => {
    e.preventDefault();
    if (!reservationSelectedPatient && !reservationForm.patient_id) {
      toast({ variant: 'destructive', title: 'Error', description: 'Pick a patient' });
      return;
    }
    setLoading(true);
    try {
      const payload = {
        patient_id: reservationSelectedPatient?.id,
        reserved_for_date: new Date(reservationForm.reserved_for_date).toISOString(),
        reservation_reason: reservationForm.reservation_reason,
        notes: reservationForm.notes || null,
      };
      if (reservationForm.bed_id) payload.bed_id = parseInt(reservationForm.bed_id);
      if (reservationForm.room_id) payload.room_id = parseInt(reservationForm.room_id);
      if (reservationForm.room_type) payload.room_type = reservationForm.room_type;
      if (!payload.bed_id && !payload.room_id && !payload.room_type) {
        toast({ variant: 'destructive', title: 'Error', description: 'Pick a bed, room, or room type' });
        setLoading(false); return;
      }
      await axios.post('/api/inpatient/reservations', payload);
      toast({ title: 'Reservation created' });
      setShowReservationDialog(false);
      setReservationForm({ patient_id: '', bed_id: '', room_id: '', room_type: '', reserved_for_date: '', reservation_reason: 'elective', notes: '' });
      setReservationSelectedPatient(null);
      fetchReservations();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleCancelReservation = async (id) => {
    try {
      await axios.patch(`/api/inpatient/reservations/${id}/cancel`);
      toast({ title: 'Reservation cancelled' });
      fetchReservations();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed' });
    }
  };

  const handleConvertReservation = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        admitting_doctor_id: parseInt(convertForm.admitting_doctor_id),
        admission_type: convertForm.admission_type,
        admission_reason: convertForm.admission_reason || null,
        condition_on_admission: convertForm.condition_on_admission,
      };
      await axios.post(`/api/inpatient/reservations/${convertingReservation.id}/convert`, payload);
      toast({ title: 'Reservation converted to admission' });
      setShowConvertReservationDialog(false);
      setConvertingReservation(null);
      fetchReservations();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  // Patient typeahead for reservations
  useEffect(() => {
    if (reservationPatientSearch.length < 2) { setReservationPatientResults([]); return; }
    const t = setTimeout(async () => {
      try {
        const res = await axios.get('/api/patients/', { params: { search: reservationPatientSearch } });
        setReservationPatientResults(res.data.patients || res.data || []);
      } catch { setReservationPatientResults([]); }
    }, 300);
    return () => clearTimeout(t);
  }, [reservationPatientSearch]);

  // Phase 3: Nurse assignment
  const handleAssignNurse = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/assign-nurse`, {
        nurse_id: parseInt(nurseAssignForm.nurse_id),
        shift: nurseAssignForm.shift,
        assignment_date: nurseAssignForm.assignment_date,
        is_primary: nurseAssignForm.is_primary,
        notes: nurseAssignForm.notes || null,
      });
      toast({ title: 'Nurse assigned' });
      setShowNurseAssignDialog(false);
      setNurseAssignForm({ nurse_id: '', shift: 'morning', assignment_date: new Date().toISOString().slice(0, 10), is_primary: false, notes: '' });
      fetchNurseAssignments(activityAdmission.id);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleRemoveNurseAssignment = async (assignmentId) => {
    try {
      await axios.delete(`/api/inpatient/nurse-assignments/${assignmentId}`);
      toast({ title: 'Assignment removed' });
      fetchNurseAssignments(activityAdmission.id);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed' });
    }
  };

  // Phase 4: Consents
  const handleCreateConsent = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = { ...consentForm };
      if (payload.template_id) payload.template_id = parseInt(payload.template_id);
      else delete payload.template_id;
      if (payload.doctor_id) payload.doctor_id = parseInt(payload.doctor_id);
      else delete payload.doctor_id;
      await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/consents`, payload);
      toast({ title: 'Consent recorded' });
      setShowConsentDialog(false);
      setConsentForm({ consent_type: 'surgical', template_id: '', procedure_name: '', doctor_id: '', risks_explained: '', patient_signature: '', signed_by: 'patient', guardian_name: '', guardian_relationship: '', witness_name: '', witness_signature: '', notes: '' });
      fetchConsents(activityAdmission.id);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleWithdrawConsent = async (e) => {
    e.preventDefault();
    if (!withdrawReason.trim()) return;
    setLoading(true);
    try {
      await axios.post(`/api/inpatient/consents/${withdrawingConsent.id}/withdraw`, { withdrawal_reason: withdrawReason });
      toast({ title: 'Consent withdrawn' });
      setShowWithdrawConsentDialog(false);
      setWithdrawingConsent(null);
      setWithdrawReason('');
      fetchConsents(activityAdmission.id);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed' });
    } finally { setLoading(false); }
  };

  const handlePrintConsent = async (consentId) => {
    await printPdfFromUrl(`/api/inpatient/consents/${consentId}/pdf`, { include_header: true });
  };

  const handleSubmitConsentTemplate = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (editingConsentTemplate) {
        await axios.put(`/api/inpatient/consent-templates/${editingConsentTemplate.id}`, consentTemplateForm);
      } else {
        await axios.post('/api/inpatient/consent-templates', consentTemplateForm);
      }
      toast({ title: 'Template saved' });
      setShowConsentTemplateDialog(false);
      setEditingConsentTemplate(null);
      setConsentTemplateForm({ consent_type: 'surgical', template_name: '', content: '', language: 'english' });
      fetchConsentTemplates();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed' });
    } finally { setLoading(false); }
  };

  const handleDeleteConsentTemplate = async (id) => {
    try {
      await axios.delete(`/api/inpatient/consent-templates/${id}`);
      toast({ title: 'Template deactivated' });
      fetchConsentTemplates();
    } catch { toast({ variant: 'destructive', title: 'Error', description: 'Failed' }); }
  };

  // Phase 4: Incidents
  const handleCreateIncident = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        incident_type: incidentForm.incident_type,
        severity: incidentForm.severity,
        incident_date: new Date(incidentForm.incident_date).toISOString(),
        description: incidentForm.description,
        immediate_action: incidentForm.immediate_action || null,
        location: incidentForm.location || null,
        witnessed_by: incidentForm.witnessed_by || null,
      };
      if (incidentForm.admission_id) payload.admission_id = parseInt(incidentForm.admission_id);
      if (incidentForm.patient_id) payload.patient_id = parseInt(incidentForm.patient_id);
      await axios.post('/api/inpatient/incidents', payload);
      toast({ title: 'Incident reported' });
      setShowIncidentDialog(false);
      setIncidentForm({ incident_type: 'fall', severity: 'medium', incident_date: new Date().toISOString().slice(0, 16), admission_id: '', patient_id: '', location: '', description: '', immediate_action: '', witnessed_by: '' });
      fetchIncidents();
      fetchIncidentReport();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed' });
    } finally { setLoading(false); }
  };

  const handleInvestigateIncident = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = { ...investigateForm };
      if (!payload.new_status) delete payload.new_status;
      await axios.post(`/api/inpatient/incidents/${investigatingIncident.id}/investigate`, payload);
      toast({ title: 'Investigation updated' });
      setShowInvestigateDialog(false);
      setInvestigatingIncident(null);
      fetchIncidents();
      fetchIncidentReport();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed' });
    } finally { setLoading(false); }
  };

  // Phase 4: Mortality
  const openMortalityDialog = (admission) => {
    setMortalityAdmission(admission);
    const d = admission.discharge || {};
    setMortalityForm({
      cause_of_death: d.cause_of_death || '',
      time_of_death: d.time_of_death ? new Date(d.time_of_death).toISOString().slice(0, 16) : '',
      death_certificate_number: d.death_certificate_number || '',
      mlc_required: !!d.mlc_required,
      mlc_number: d.mlc_number || '',
      autopsy_done: !!d.autopsy_done,
      autopsy_findings: d.autopsy_findings || '',
      body_handed_over_to: d.body_handed_over_to || '',
      body_handover_relationship: d.body_handover_relationship || '',
      body_handover_time: d.body_handover_time ? new Date(d.body_handover_time).toISOString().slice(0, 16) : '',
      body_handover_id_proof: d.body_handover_id_proof || '',
    });
    setShowMortalityDialog(true);
  };

  const handleSaveMortality = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = { ...mortalityForm };
      if (payload.time_of_death) payload.time_of_death = new Date(payload.time_of_death).toISOString();
      else delete payload.time_of_death;
      if (payload.body_handover_time) payload.body_handover_time = new Date(payload.body_handover_time).toISOString();
      else delete payload.body_handover_time;
      await axios.put(`/api/inpatient/admissions/${mortalityAdmission.id}/discharge/mortality`, payload);
      toast({ title: 'Mortality details saved' });
      setShowMortalityDialog(false);
      fetchMortalityList();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed' });
    } finally { setLoading(false); }
  };

  const handlePrintDeathCertificate = async (admissionId) => {
    await printPdfFromUrl(`/api/inpatient/admissions/${admissionId}/death-certificate/pdf`, { include_header: true });
  };

  // ---- Body release / mortuary tracking ----
  const openBodyRelease = async (admissionId) => {
    setBodyReleaseAdmId(admissionId);
    try {
      const r = await axios.get(`/api/inpatient/admissions/${admissionId}/body-release`);
      const d = r.data || {};
      setBodyReleaseRec(d);
      const fmt = (v) => v ? new Date(v).toISOString().slice(0, 16) : '';
      setBodyReleaseTrack({
        mortuary_slot: d.mortuary_slot || '',
        body_in_mortuary_at: fmt(d.body_in_mortuary_at),
        body_out_mortuary_at: fmt(d.body_out_mortuary_at),
        embalming_done: !!d.embalming_done, embalming_at: fmt(d.embalming_at),
        embalmed_by: d.embalmed_by || '',
        post_mortem_required: !!d.post_mortem_required,
        pm_hospital: d.pm_hospital || '', pm_doctor: d.pm_doctor || '',
        pm_referred_at: fmt(d.pm_referred_at), pm_completed_at: fmt(d.pm_completed_at),
        pm_report_received: !!d.pm_report_received, pm_report_number: d.pm_report_number || '',
        police_noc_required: !!d.police_noc_required, police_noc_received: !!d.police_noc_received,
        police_noc_number: d.police_noc_number || '',
        police_noc_received_at: fmt(d.police_noc_received_at),
        notes: d.notes || '',
      });
      setBodyReleaseAction({
        released_to_name: d.released_to_name || '', released_to_relationship: d.released_to_relationship || '',
        released_to_phone: d.released_to_phone || '',
        released_to_id_proof_type: d.released_to_id_proof_type || 'aadhar',
        released_to_id_proof_number: d.released_to_id_proof_number || '',
        released_to_address: d.released_to_address || '',
        witness_name: d.witness_name || '', witness_phone: d.witness_phone || '',
        witness_id_proof: d.witness_id_proof || '',
        transport_details: d.transport_details || '', notes: '',
        force_missing_noc: false, force_missing_pm: false, override_reason: '',
      });
      setShowBodyReleaseDialog(true);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error',
        description: typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to load body release record' });
    }
  };

  const saveBodyReleaseTracking = async () => {
    try {
      const r = await axios.put(`/api/inpatient/admissions/${bodyReleaseAdmId}/body-release`, bodyReleaseTrack);
      setBodyReleaseRec(r.data);
      toast({ title: 'Saved', description: 'Mortuary tracking updated.' });
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error',
        description: typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Save failed' });
    }
  };

  const performBodyRelease = async () => {
    if (!bodyReleaseAction.released_to_name?.trim() || !bodyReleaseAction.released_to_relationship?.trim()
        || !bodyReleaseAction.released_to_id_proof_number?.trim() || !bodyReleaseAction.witness_name?.trim()) {
      toast({ variant: 'destructive', title: 'Missing required fields',
        description: 'Releasee name, relationship, ID proof number, and witness name are required.' });
      return;
    }
    try {
      const r = await axios.post(`/api/inpatient/admissions/${bodyReleaseAdmId}/body-release/release`, bodyReleaseAction);
      setBodyReleaseRec(r.data);
      toast({ title: 'Body released', description: 'Handover recorded — print the form for the family.' });
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : (detail?.message || 'Release failed');
      toast({ variant: 'destructive', title: 'Cannot release', description: msg });
    }
  };

  const printBodyRelease = (admissionId) => {
    printPdfFromUrl(`/api/inpatient/admissions/${admissionId}/body-release/pdf`, { include_header: true });
  };

  const handleSaveDama = async (e) => {
    e.preventDefault();
    if (!damaForm.patient_acknowledges_advice || !damaForm.patient_absolves_hospital) {
      toast({ variant: 'destructive', title: 'Acknowledgements required',
        description: 'Both checkboxes must be ticked for the form to have legal weight.' });
      return;
    }
    if (damaForm.signed_by === 'guardian' && !damaForm.guardian_name?.trim()) {
      toast({ variant: 'destructive', title: 'Guardian name required' });
      return;
    }
    setLoading(true);
    try {
      const payload = { ...damaForm };
      if (!payload.attending_doctor_id) delete payload.attending_doctor_id;
      else payload.attending_doctor_id = parseInt(payload.attending_doctor_id, 10);
      await axios.post(`/api/inpatient/admissions/${damaAdmission.id}/dama`, payload);
      toast({ title: 'DAMA form saved' });
      setShowDamaDialog(false);
      const admId = damaAdmission.id;
      setDamaAdmission(null);
      // Offer to print the signed PDF immediately
      setTimeout(() => {
        printPdfFromUrl(`/api/inpatient/admissions/${admId}/dama/pdf`, { include_header: true });
      }, 200);
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast({ variant: 'destructive', title: 'Error',
        description: typeof detail === 'string' ? detail : 'Failed to save DAMA form' });
    } finally { setLoading(false); }
  };

  const handlePrintDama = async (admissionId) => {
    await printPdfFromUrl(`/api/inpatient/admissions/${admissionId}/dama/pdf`, { include_header: true });
  };

  // ICU: I/O record
  const handleRecordIO = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/io`, {
        io_type: ioForm.io_type,
        category: ioForm.category,
        amount_ml: parseFloat(ioForm.amount_ml),
        shift: ioForm.shift,
        notes: ioForm.notes || null,
      });
      toast({ title: 'I/O entry recorded' });
      setShowIoDialog(false);
      setIoForm({ io_type: 'intake', category: 'oral', amount_ml: '', shift: 'morning', notes: '' });
      fetchIoEntries(activityAdmission.id, ioDate);
      fetchIoBalance(activityAdmission.id, ioDate);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleDeleteIO = async (entryId) => {
    try {
      await axios.delete(`/api/inpatient/io/${entryId}`);
      fetchIoEntries(activityAdmission.id, ioDate);
      fetchIoBalance(activityAdmission.id, ioDate);
    } catch { toast({ variant: 'destructive', title: 'Error', description: 'Failed' }); }
  };

  // ICU: Critical alert acknowledge
  const handleAcknowledgeAlert = async (alertId, markAddressed = false, notes = '') => {
    try {
      await axios.patch(`/api/inpatient/critical-alerts/${alertId}/acknowledge`, {
        mark_addressed: markAddressed,
        addressed_notes: notes || null,
      });
      toast({ title: markAddressed ? 'Alert addressed' : 'Alert acknowledged' });
      if (activityAdmission) fetchAdmissionCriticalAlerts(activityAdmission.id);
      fetchCriticalAlerts();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed' });
    }
  };

  // Roster handlers
  const openRosterCell = (nurse, dateIso, shift, existing) => {
    setRosterCellEdit({ nurse, dateIso, shift, existing });
    setRosterCellForm({
      status: existing?.status || 'working',
      ward: existing?.ward || '',
      notes: existing?.notes || '',
    });
    setShowRosterCellDialog(true);
  };

  const handleSaveRosterCell = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { nurse, dateIso, shift, existing } = rosterCellEdit;
      if (existing) {
        await axios.put(`/api/inpatient/roster/${existing.id}`, rosterCellForm);
      } else {
        await axios.post('/api/inpatient/roster', {
          nurse_id: nurse.id,
          roster_date: dateIso,
          shift,
          status: rosterCellForm.status,
          ward: rosterCellForm.ward || null,
          notes: rosterCellForm.notes || null,
        });
      }
      toast({ title: 'Roster updated' });
      setShowRosterCellDialog(false);
      fetchRosterGrid();
      fetchRosterCoverage();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  const handleDeleteRosterCell = async () => {
    if (!rosterCellEdit?.existing) return;
    setLoading(true);
    try {
      await axios.delete(`/api/inpatient/roster/${rosterCellEdit.existing.id}`);
      toast({ title: 'Roster entry removed' });
      setShowRosterCellDialog(false);
      fetchRosterGrid();
      fetchRosterCoverage();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed' });
    } finally { setLoading(false); }
  };

  const handleBulkRoster = async (e) => {
    e.preventDefault();
    if (bulkRosterForm.nurse_ids.length === 0) {
      toast({ variant: 'destructive', title: 'Error', description: 'Pick at least one nurse' });
      return;
    }
    if (bulkRosterForm.shifts.length === 0) {
      toast({ variant: 'destructive', title: 'Error', description: 'Pick at least one shift' });
      return;
    }
    setLoading(true);
    try {
      const res = await axios.post('/api/inpatient/roster/bulk', {
        nurse_ids: bulkRosterForm.nurse_ids.map(Number),
        from_date: bulkRosterForm.from_date,
        to_date: bulkRosterForm.to_date,
        shifts: bulkRosterForm.shifts,
        status: bulkRosterForm.status,
        ward: bulkRosterForm.ward || null,
        notes: bulkRosterForm.notes || null,
        overwrite: bulkRosterForm.overwrite,
      });
      toast({ title: 'Bulk roster applied', description: `Created ${res.data.created}, overwritten ${res.data.overwritten}, skipped ${res.data.skipped}` });
      setShowBulkRosterDialog(false);
      fetchRosterGrid();
      fetchRosterCoverage();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  // When the Assign Nurse dialog is open, refetch on-duty nurses each time
  // shift or date changes
  useEffect(() => {
    if (!showNurseAssignDialog) return;
    if (!nurseAssignForm.assignment_date || !nurseAssignForm.shift) {
      setOnDutyNurses([]); return;
    }
    axios.get('/api/inpatient/roster/on-duty', {
      params: { target_date: nurseAssignForm.assignment_date, shift: nurseAssignForm.shift },
    })
      .then(r => setOnDutyNurses(r.data || []))
      .catch(() => setOnDutyNurses([]));
  }, [showNurseAssignDialog, nurseAssignForm.assignment_date, nurseAssignForm.shift]);

  const shiftWeek = (deltaDays) => {
    const d = new Date(rosterWeekStart);
    d.setDate(d.getDate() + deltaDays);
    setRosterWeekStart(d);
  };

  // Patient typeahead for pre-auth
  useEffect(() => {
    if (preauthPatientSearch.length < 2) { setPreauthPatientResults([]); return; }
    const t = setTimeout(async () => {
      try {
        const res = await axios.get('/api/patients/', { params: { search: preauthPatientSearch } });
        setPreauthPatientResults(res.data.patients || res.data || []);
      } catch { setPreauthPatientResults([]); }
    }, 300);
    return () => clearTimeout(t);
  }, [preauthPatientSearch]);

  const handleRecordPRN = async (e) => {
    e.preventDefault();
    if (!prnForm.prescription_item_id) {
      toast({ variant: 'destructive', title: 'Error', description: 'Pick a prescribed medication' });
      return;
    }
    setLoading(true);
    try {
      await axios.post(`/api/inpatient/admissions/${activityAdmission.id}/mar/prn`, {
        prescription_item_id: parseInt(prnForm.prescription_item_id),
        dose_given: prnForm.dose_given,
        route: prnForm.route || null,
        site: prnForm.site || null,
        prn_indication: prnForm.prn_indication || null,
        notes: prnForm.notes || null,
      });
      toast({ title: 'PRN dose recorded' });
      setShowPrnDialog(false);
      setPrnForm({ prescription_item_id: '', dose_given: '', route: '', site: '', prn_indication: '', notes: '' });
      fetchMAR(activityAdmission.id, marDate);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string' ? err.response.data.detail : 'Failed to record PRN';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally { setLoading(false); }
  };

  // OT Schedule
  const handleCreateOT = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const payload = {
        patient_id: parseInt(otForm.patient_id),
        surgeon_id: parseInt(otForm.surgeon_id),
        anaesthetist_id: otForm.anaesthetist_id ? parseInt(otForm.anaesthetist_id) : null,
        admission_id: otForm.admission_id ? parseInt(otForm.admission_id) : null,
        ot_room_number: otForm.ot_room_number,
        procedure_name: otForm.procedure_name,
        procedure_id: otForm.procedure_id ? parseInt(otForm.procedure_id) : null,
        scheduled_date: new Date(otForm.scheduled_date).toISOString(),
        estimated_duration_minutes: otForm.estimated_duration_minutes ? parseInt(otForm.estimated_duration_minutes) : null,
        pre_op_notes: otForm.pre_op_notes || null,
      };
      await axios.post('/api/inpatient/ot', payload);
      toast({ title: 'Success', description: 'OT scheduled successfully' });
      setShowOTDialog(false);
      setOtForm({ patient_id: '', surgeon_id: '', anaesthetist_id: '', ot_room_number: '', procedure_name: '', procedure_id: '', scheduled_date: '', estimated_duration_minutes: '', pre_op_notes: '', admission_id: '' });
      fetchOTSchedules();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: err.response?.data?.detail || 'Failed to schedule OT' });
    } finally { setLoading(false); }
  };

  const handleUpdateOTStatus = async (otId, newStatus) => {
    try {
      await axios.patch(`/api/inpatient/ot/${otId}/status`, null, { params: { status: newStatus } });
      toast({ title: 'Success', description: `OT status updated to ${newStatus}` });
      fetchOTSchedules();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to update status' });
    }
  };

  // PDF
  const handlePrintDischargePdf = async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/discharge/pdf`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      printPdfFromUrl(url);
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to generate discharge PDF' });
    }
  };

  const handlePrintBillPdf = async (admissionId) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/bill/pdf`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
      printPdfFromUrl(url);
    } catch (err) {
      // Blob responses hide the JSON detail — read it back as text.
      let msg = 'Failed to generate bill PDF';
      try {
        if (err.response?.data instanceof Blob) {
          const text = await err.response.data.text();
          const json = JSON.parse(text);
          if (typeof json.detail === 'string') msg = json.detail;
          else if (json.detail?.message) msg = json.detail.message;
        } else if (typeof err.response?.data?.detail === 'string') {
          msg = err.response.data.detail;
        }
      } catch { /* keep default msg */ }
      toast({ variant: 'destructive', title: 'Error', description: msg });
    }
  };

  // Filtered admissions
  const filteredAdmissions = admissions.filter(a => {
    if (!admissionSearch) return true;
    const q = admissionSearch.toLowerCase();
    return (a.patient_name || '').toLowerCase().includes(q) ||
           (a.admission_number || '').toLowerCase().includes(q) ||
           (a.room_number || '').toLowerCase().includes(q);
  });

  const filteredDischarged = dischargedAdmissions.filter(a => {
    if (!dischargeSearch) return true;
    const q = dischargeSearch.toLowerCase();
    return (a.patient_name || '').toLowerCase().includes(q) ||
           (a.admission_number || '').toLowerCase().includes(q);
  });

  const daysSince = (dateStr) => {
    if (!dateStr) return 0;
    return Math.max(1, Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000));
  };

  // ============================================================
  // RENDER
  // ============================================================
  // The internal sidebar that previously listed Ward Overview / Active Admissions / etc.
  // has been moved to the main left navigation in Dashboard.js. This module is now
  // purely the content area for whichever inpatient route is active.
  // When admissions tab is left, drop the open admission slide-over so reopening starts fresh.
  useEffect(() => {
    if (activeTab !== 'admissions') {
      setActivityAdmission(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab]);

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      {/* ============ MAIN CONTENT ============ */}
      <div className="flex-1 overflow-hidden flex flex-col min-w-0">
        {/* Quick Actions Bar */}
        <div className="border-b bg-white px-6 py-3 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            {ip('admit_patients') && (
              <Button size="sm" onClick={() => { resetAdmissionForm(); fetchAvailableRooms(); setShowAdmissionDialog(true); }}>
                <Plus className="h-4 w-4 mr-1" /> Admit Patient
              </Button>
            )}
            {ip('admit_patients') && (
              <Button size="sm" variant="destructive" onClick={() => { fetchAvailableRooms(); setShowQuickAdmitDialog(true); }}>
                <Plus className="h-4 w-4 mr-1" /> Emergency Admit
              </Button>
            )}
            {ip('schedule_ot') && (
              <Button size="sm" variant="outline" onClick={() => setShowOTDialog(true)}>
                <Scissors className="h-4 w-4 mr-1" /> Schedule OT
              </Button>
            )}
            {activityAdmission && ip('record_visits') && (
              <Button size="sm" variant="outline" onClick={() => { setVisitForm({ visit_type: defaultVisitType, visitor_id: '', notes: '', vitals_reviewed: false, labs_reviewed: false, pain_assessed: false, mobility_checked: false, plan_for_today: '', family_updated: false }); setShowVisitDialog(true); }}>
                <Stethoscope className="h-4 w-4 mr-1" /> New Visit
              </Button>
            )}
          </div>
          {activityAdmission && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-gray-500">Patient:</span>
              <span className="font-medium">{activityAdmission.patient_name}</span>
              <Badge className={admissionStatusColor[activityAdmission.status] || ''}>{activityAdmission.status}</Badge>
              <Button variant="ghost" size="sm" onClick={() => setActivityAdmission(null)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          )}
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-hidden">

          {/* ============ WARD OVERVIEW ============ */}
          {activeTab === 'dashboard' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
          <div className="flex justify-end">
            <Button size="sm" variant="outline"
              onClick={() => printPdfFromUrl('/api/inpatient/reports/census/pdf', { include_header: true })}>
              <Printer className="h-4 w-4 mr-1" /> Print daily census
            </Button>
          </div>
          {dashboardData ? (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <Card>
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-gray-500">Total Beds</p>
                        <p className="text-2xl font-bold">{dashboardData.total_beds}</p>
                      </div>
                      <Bed className="h-8 w-8 text-blue-500" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-gray-500">Occupied</p>
                        <p className="text-2xl font-bold text-orange-600">{dashboardData.occupied}</p>
                      </div>
                      <Activity className="h-8 w-8 text-orange-500" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-gray-500">Available</p>
                        <p className="text-2xl font-bold text-green-600">{dashboardData.available}</p>
                      </div>
                      <Bed className="h-8 w-8 text-green-500" />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-gray-500">Today Admissions</p>
                        <p className="text-2xl font-bold">{dashboardData.today_admissions}</p>
                      </div>
                      <Plus className="h-8 w-8 text-purple-500" />
                    </div>
                  </CardContent>
                </Card>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card>
                  <CardContent className="pt-6">
                    <p className="text-sm text-gray-500">Active Admissions</p>
                    <p className="text-2xl font-bold">{dashboardData.active_admissions}</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <p className="text-sm text-gray-500">Pending Discharges</p>
                    <p className="text-2xl font-bold text-yellow-600">{dashboardData.pending_discharges}</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <p className="text-sm text-gray-500">Avg Stay (days)</p>
                    <p className="text-2xl font-bold">{dashboardData.avg_stay_days}</p>
                  </CardContent>
                </Card>
              </div>

              {/* By Type breakdown */}
              {dashboardData.by_type && Object.keys(dashboardData.by_type).length > 0 && (
                <Card>
                  <CardHeader><CardTitle className="text-lg">Bed Occupancy by Type</CardTitle></CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      {Object.entries(dashboardData.by_type).map(([type, data]) => (
                        <div key={type} className="border rounded-lg p-3 text-center">
                          <p className="font-semibold text-sm">{roomTypeLabel[type] || type}</p>
                          <p className="text-xs text-gray-500 mt-1">
                            {data.occupied}/{data.total} occupied
                          </p>
                          <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                            <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${data.total > 0 ? (data.occupied / data.total * 100) : 0}%` }} />
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          ) : (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
            </div>
          )}
          </div>
          )}

          {/* ============ ACTIVE ADMISSIONS (split view) ============ */}
          {activeTab === 'admissions' && (
            <div className="flex h-full">
              {/* Left: Admissions list */}
              <div className={`${activityAdmission ? 'w-1/2 border-r' : 'w-full'} overflow-y-auto p-6 transition-all space-y-4`}>
                <div className="relative max-w-sm">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <Input placeholder="Search by name, ID, room..." value={admissionSearch} onChange={e => setAdmissionSearch(e.target.value)} className="pl-10" />
                </div>

                {filteredAdmissions.length === 0 ? (
                  <Card><CardContent className="py-12 text-center text-gray-500">No active admissions found.</CardContent></Card>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left py-2 text-sm">Patient</th>
                          <th className="text-left py-2 text-sm">Room / Bed</th>
                          {!activityAdmission && <th className="text-left py-2 text-sm">Doctor</th>}
                          <th className="text-left py-2 text-sm">Admitted</th>
                          <th className="text-left py-2 text-sm">Days</th>
                          <th className="text-left py-2 text-sm">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredAdmissions.map(adm => (
                          <tr key={adm.id} className={`border-b cursor-pointer transition-colors ${activityAdmission?.id === adm.id ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                              onClick={() => openActivity(adm)}>
                            <td className="py-2">
                              <div className="flex items-center gap-1 flex-wrap">
                                <span className="font-medium text-sm">{adm.patient_name || 'N/A'}</span>
                                {adm.claim_status && adm.claim_status !== 'none' && (
                                  <Shield className="h-3 w-3 text-blue-500" title={`Claim: ${claimStatusLabel[adm.claim_status]}`} />
                                )}
                                {adm.is_readmission && (
                                  <Badge className="text-xs bg-purple-100 text-purple-800" title={`${adm.days_since_last_discharge} days since last discharge`}>
                                    <RotateCcw className="h-3 w-3 mr-0.5" /> Readmit
                                  </Badge>
                                )}
                                {adm.admission_type === 'emergency' && (
                                  <Badge className="text-xs bg-red-100 text-red-800" title={adm.chief_complaint || 'Emergency admission'}>
                                    ER{adm.triage_level ? ` T${adm.triage_level}` : ''}
                                  </Badge>
                                )}
                                {adm.is_mlc && (
                                  <Badge className="text-xs bg-yellow-200 text-yellow-900" title={`MLC: ${adm.mlc_type || ''} ${adm.mlc_number ? '#' + adm.mlc_number : ''}`}
                                    onClick={(e) => { e.stopPropagation(); printPdfFromUrl(`/api/inpatient/admissions/${adm.id}/mlc/pdf`, `MLC_${adm.admission_number}.pdf`); }}>
                                    MLC
                                  </Badge>
                                )}
                                {adm.is_observation && (
                                  <Badge className="text-xs bg-blue-100 text-blue-800" title="Observation case — room rent skipped">
                                    Obs
                                  </Badge>
                                )}
                                {adm.deposit_waived && (
                                  <Badge className="text-xs bg-amber-100 text-amber-800" title={`Deposit waived: ${adm.deposit_waiver_reason || ''}`}>
                                    Waiver
                                  </Badge>
                                )}
                                {adm.registration_complete === false && (
                                  <Badge className="text-xs bg-orange-100 text-orange-800" title="Patient KYC pending — complete registration">
                                    KYC Pending
                                  </Badge>
                                )}
                              </div>
                              <div className="text-xs text-gray-500">{adm.admission_number}</div>
                            </td>
                            <td className="py-2 text-sm">{adm.room_number} {(adm.bed_label || adm.bed_number) ? `/ ${adm.bed_label || adm.bed_number}` : ''}<br /><span className="text-xs text-gray-500">{roomTypeLabel[adm.room_type] || adm.room_type}</span></td>
                            {!activityAdmission && <td className="py-2 text-sm">{adm.doctor_name || 'N/A'}</td>}
                            <td className="py-2 text-sm">{adm.admission_date ? new Date(adm.admission_date).toLocaleDateString() : ''}</td>
                            <td className="py-2 text-sm">{daysSince(adm.admission_date)}</td>
                            <td className="py-2">
                              <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                                {adm.status === 'admitted' && ip('discharge_patients') && (
                                  <Button variant="ghost" size="sm" className="text-red-500" onClick={() => openDischargeDialog(adm)} title="Discharge">
                                    <ChevronRight className="h-4 w-4" />
                                  </Button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {admissionsTotal > PAGE_SIZE && (
                      <div className="flex items-center justify-between pt-4 border-t mt-2">
                        <span className="text-sm text-gray-500">
                          Showing {admissionsPage * PAGE_SIZE + 1}–{Math.min((admissionsPage + 1) * PAGE_SIZE, admissionsTotal)} of {admissionsTotal}
                        </span>
                        <div className="flex gap-2">
                          <Button variant="outline" size="sm" disabled={admissionsPage === 0}
                            onClick={() => setAdmissionsPage(p => p - 1)}>
                            <ChevronLeft className="h-4 w-4 mr-1" /> Prev
                          </Button>
                          <Button variant="outline" size="sm" disabled={(admissionsPage + 1) * PAGE_SIZE >= admissionsTotal}
                            onClick={() => setAdmissionsPage(p => p + 1)}>
                            Next <ChevronRight className="h-4 w-4 ml-1" />
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Right: Patient detail (inline) */}
              {activityAdmission && (
                <div className="w-1/2 overflow-y-auto flex flex-col">
                  <div className="sticky top-0 bg-white border-b p-4 flex items-center justify-between z-10">
                    <div>
                      <h2 className="font-semibold">{activityAdmission.patient_name}</h2>
                      <p className="text-xs text-gray-500">{activityAdmission.admission_number} &bull; {roomTypeLabel[activityAdmission.room_type] || activityAdmission.room_type} - {activityAdmission.room_number} &bull; Dr. {activityAdmission.doctor_name || 'N/A'}</p>
                      {balance && (
                        <div className="flex items-center gap-2 mt-1">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
                            balance.balance > 0 ? 'bg-green-100 text-green-800' :
                            balance.balance < 0 ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-700'
                          }`}>
                            <Wallet className="h-3 w-3" />
                            {balance.balance > 0 ? `Credit ₹${balance.balance.toFixed(2)}` :
                             balance.balance < 0 ? `Owes ₹${Math.abs(balance.balance).toFixed(2)}` :
                             `Settled`}
                          </span>
                          <span className="text-xs text-gray-400">Deposits ₹{balance.net_deposits.toFixed(2)} · Billed ₹{balance.total_billed.toFixed(2)}</span>
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {activityAdmission.status === 'admitted' && (
                        <>
                          {ip('update_admission') && (
                            <Button size="sm" variant="outline" onClick={() => openLoaDialog(activityAdmission)}>
                              <CalendarRange className="h-4 w-4 mr-1" /> Leave
                            </Button>
                          )}
                          {ip('discharge_patients') && (
                            <Button size="sm" variant="outline" className="text-red-600" onClick={() => openDischargeDialog(activityAdmission)}>Discharge</Button>
                          )}
                        </>
                      )}
                      <Button variant="ghost" size="sm" onClick={() => setActivityAdmission(null)}><X className="h-4 w-4" /></Button>
                    </div>
                  </div>

                  {/* Critical lab value alerts banner */}
                  {admissionCriticalAlerts.filter(a => a.status === 'new').length > 0 && (
                    <div className="mx-4 mt-4 rounded-md border-l-4 border-red-700 bg-red-100 p-3">
                      <div className="flex items-start gap-2">
                        <AlertOctagon className="h-5 w-5 text-red-700 mt-0.5 flex-shrink-0" />
                        <div className="flex-1">
                          <p className="text-sm font-semibold text-red-900">
                            {admissionCriticalAlerts.filter(a => a.status === 'new').length} critical lab value alert(s)
                          </p>
                          <div className="space-y-1 mt-1">
                            {admissionCriticalAlerts.filter(a => a.status === 'new').slice(0, 3).map(a => (
                              <div key={a.id} className="text-xs flex items-center justify-between gap-2 bg-white/70 rounded p-1.5">
                                <span>
                                  <b>{a.parameter_name}</b> = {a.actual_value}
                                  {a.critical_min != null && a.critical_max != null && <span className="text-gray-600"> (range: {a.critical_min}–{a.critical_max})</span>}
                                </span>
                                <div className="flex gap-1">
                                  <Button size="sm" variant="ghost" className="h-6 text-xs" onClick={() => handleAcknowledgeAlert(a.id, false)}>Ack</Button>
                                  <Button size="sm" variant="outline" className="h-6 text-xs" onClick={() => handleAcknowledgeAlert(a.id, true)}>Addressed</Button>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Allergy alert banner — patient-level, always visible */}
                  {admissionAllergies.length > 0 && (
                    <div className={`mx-4 mt-4 rounded-md border-l-4 p-3 ${
                      admissionAllergies.some(a => a.severity === 'anaphylaxis' || a.severity === 'severe')
                        ? 'border-red-600 bg-red-50' : 'border-orange-500 bg-orange-50'
                    }`}>
                      <div className="flex items-start gap-2">
                        <AlertTriangle className={`h-5 w-5 mt-0.5 flex-shrink-0 ${
                          admissionAllergies.some(a => a.severity === 'anaphylaxis' || a.severity === 'severe')
                            ? 'text-red-600' : 'text-orange-600'
                        }`} />
                        <div className="flex-1">
                          <p className="text-sm font-semibold text-gray-900">Active allergies</p>
                          <div className="flex flex-wrap gap-1.5 mt-1">
                            {admissionAllergies.map(a => (
                              <span key={a.id} className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
                                a.severity === 'anaphylaxis' ? 'bg-red-200 text-red-900' :
                                a.severity === 'severe' ? 'bg-red-100 text-red-800' :
                                a.severity === 'moderate' ? 'bg-orange-100 text-orange-800' :
                                'bg-yellow-100 text-yellow-800'
                              }`} title={a.reaction || ''}>
                                {a.allergen} ({a.severity})
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="p-4 flex-1">
                    {(() => {
                      const TAB_GROUPS = {
                        clinical: { label: 'Clinical', tabs: [
                          { v: 'vitals', l: 'Vitals' },
                          { v: 'mar', l: 'MAR' },
                          { v: 'io', l: 'I/O' },
                          { v: 'nursing', l: 'Nursing' },
                          { v: 'diet', l: 'Diet' },
                          { v: 'allergies', l: 'Allergies' },
                          { v: 'consents', l: 'Consents' },
                        ]},
                        orders: { label: 'Orders & Care', tabs: [
                          { v: 'visits', l: 'Visits' },
                          { v: 'lab', l: 'Lab' },
                          { v: 'medications', l: 'Meds' },
                        ]},
                        ...(canViewBilling ? {
                          billing: { label: 'Billing', tabs: [
                            { v: 'bill', l: 'Bill' },
                            { v: 'deposits', l: 'Deposits' },
                            { v: 'insurance', l: 'Insurance' },
                          ]},
                        } : {}),
                        operations: { label: 'Operations', tabs: [
                          { v: 'staff', l: 'Staff' },
                          { v: 'docs', l: 'Docs' },
                        ]},
                      };
                      const groupOf = (tab) => Object.entries(TAB_GROUPS).find(([, g]) => g.tabs.some(t => t.v === tab))?.[0] || 'clinical';
                      const currentGroup = groupOf(activityTab);
                      const subTabs = TAB_GROUPS[currentGroup].tabs;
                      return (
                        <Tabs value={activityTab} onValueChange={setActivityTab}>
                          {/* Primary group selector */}
                          <div className="flex gap-1 border-b mb-2">
                            {Object.entries(TAB_GROUPS).map(([k, g]) => (
                              <button
                                key={k}
                                type="button"
                                className={`px-4 py-2 text-sm transition-colors ${
                                  currentGroup === k
                                    ? 'border-b-2 border-blue-600 font-semibold text-blue-700'
                                    : 'text-gray-500 hover:text-gray-700'
                                }`}
                                onClick={() => setActivityTab(g.tabs[0].v)}
                              >
                                {g.label}
                              </button>
                            ))}
                          </div>
                          {/* Sub-tabs for the active group */}
                          <TabsList className="grid w-full text-xs" style={{ gridTemplateColumns: `repeat(${subTabs.length}, minmax(0, 1fr))` }}>
                            {subTabs.map(t => (
                              <TabsTrigger key={t.v} value={t.v}>{t.l}</TabsTrigger>
                            ))}
                          </TabsList>

                      {/* Visits sub-tab */}
                      <TabsContent value="visits" className="space-y-3 mt-3">
                        <Button size="sm" onClick={() => { setVisitForm({ visit_type: defaultVisitType, visitor_id: '', notes: '', vitals_reviewed: false, labs_reviewed: false, pain_assessed: false, mobility_checked: false, plan_for_today: '', family_updated: false }); setShowVisitDialog(true); }}>
                          <Plus className="h-4 w-4 mr-1" /> Add Visit
                        </Button>
                        {visits.length === 0 ? (
                          <p className="text-sm text-gray-500 text-center py-4">No visits recorded yet.</p>
                        ) : (
                          <div className="space-y-2">
                            {visits.map(v => (
                              <div key={v.id} className="border rounded-lg p-3 text-sm">
                                <div className="flex items-center justify-between">
                                  <div>
                                    <span className="font-medium">{v.visit_type.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}</span>
                                    <span className="text-gray-500 ml-2">by {v.visitor_name || 'N/A'}</span>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <span className="text-gray-600">₹{parseFloat(v.charge_amount || 0).toFixed(2)}</span>
                                    {v.billed ? (
                                      <Badge className="bg-green-100 text-green-800 text-xs">Billed</Badge>
                                    ) : (
                                      <Button variant="ghost" size="sm" className="text-red-500 h-6 w-6 p-0"
                                        onClick={() => setConfirmState({ open: true, title: 'Delete Visit', message: 'Delete this visit?',
                                          onConfirm: () => { setConfirmState({ open: false }); handleDeleteVisit(v.id); } })}>
                                        <Trash2 className="h-3 w-3" />
                                      </Button>
                                    )}
                                  </div>
                                </div>
                                <p className="text-xs text-gray-400 mt-1">{v.visit_datetime ? new Date(v.visit_datetime).toLocaleString() : ''}</p>
                                {v.notes && <p className="text-xs text-gray-600 mt-1">{v.notes}</p>}
                              </div>
                            ))}
                          </div>
                        )}
                      </TabsContent>

                      {/* Nursing Notes sub-tab */}
                      <TabsContent value="nursing" className="space-y-3 mt-3">
                        <div className="flex items-center gap-2">
                          <Button size="sm" onClick={() => {
                            setEditingNursingNote(null);
                            setNursingNoteForm({ shift: 'morning', note_type: 'general', content: '' });
                            setShowNursingNoteDialog(true);
                          }}>
                            <Plus className="h-4 w-4 mr-1" /> Add Note
                          </Button>
                          <Select value={nursingShiftFilter} onValueChange={setNursingShiftFilter}>
                            <SelectTrigger className="w-[140px] h-8 text-xs">
                              <SelectValue placeholder="Filter shift" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="all">All Shifts</SelectItem>
                              <SelectItem value="morning">Morning</SelectItem>
                              <SelectItem value="afternoon">Afternoon</SelectItem>
                              <SelectItem value="night">Night</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        {(() => {
                          const filtered = nursingShiftFilter === 'all' ? nursingNotes : nursingNotes.filter(n => n.shift === nursingShiftFilter);
                          return filtered.length === 0 ? (
                            <p className="text-sm text-gray-500 text-center py-4">No nursing notes recorded yet.</p>
                          ) : (
                            <div className="space-y-2">
                              {filtered.map(n => (
                                <div key={n.id} className="border rounded-lg p-3 text-sm">
                                  <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                      <Badge className={n.shift === 'morning' ? 'bg-yellow-100 text-yellow-800' : n.shift === 'afternoon' ? 'bg-orange-100 text-orange-800' : 'bg-indigo-100 text-indigo-800'}>
                                        {n.shift.charAt(0).toUpperCase() + n.shift.slice(1)}
                                      </Badge>
                                      <Badge variant="outline">{n.note_type.charAt(0).toUpperCase() + n.note_type.slice(1)}</Badge>
                                      <span className="text-gray-500 text-xs">by {n.nurse_name || 'N/A'}</span>
                                    </div>
                                    <div className="flex items-center gap-1">
                                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => {
                                        setEditingNursingNote(n);
                                        setNursingNoteForm({ shift: n.shift, note_type: n.note_type, content: n.content });
                                        setShowNursingNoteDialog(true);
                                      }}>
                                        <Edit2 className="h-3 w-3" />
                                      </Button>
                                      <Button variant="ghost" size="sm" className="text-red-500 h-6 w-6 p-0"
                                        onClick={() => setConfirmState({ open: true, title: 'Delete Note', message: 'Delete this nursing note?',
                                          onConfirm: () => { setConfirmState({ open: false }); handleDeleteNursingNote(n.id); } })}>
                                        <Trash2 className="h-3 w-3" />
                                      </Button>
                                    </div>
                                  </div>
                                  <p className="text-xs text-gray-400 mt-1">{n.created_at ? new Date(n.created_at).toLocaleString() : ''}</p>
                                  <p className="text-sm text-gray-700 mt-1 whitespace-pre-wrap">{n.content}</p>
                                </div>
                              ))}
                            </div>
                          );
                        })()}
                      </TabsContent>

                      {/* Diet sub-tab */}
                      <TabsContent value="diet" className="space-y-3 mt-3">
                        <div className="flex items-center gap-2">
                          <Button size="sm" onClick={() => {
                            setDietForm({ diet_type: 'regular', meal_instructions: '', allergies: '', notes: '' });
                            setShowDietDialog(true);
                          }}>
                            <Plus className="h-4 w-4 mr-1" /> New Diet Order
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => setKitchenTicketDialog({ open: true, meal_time: 'lunch', department: '' })}>
                            <Printer className="h-4 w-4 mr-1" /> Kitchen Ticket
                          </Button>
                        </div>
                        {dietOrders.length === 0 ? (
                          <p className="text-sm text-gray-500 text-center py-4">No diet orders.</p>
                        ) : (
                          <div className="space-y-2">
                            {dietOrders.map(d => (
                              <div key={d.id} className={`border rounded-lg p-3 text-sm ${!d.is_active ? 'opacity-50' : ''}`}>
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-2">
                                    <Badge className={d.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}>
                                      {d.diet_type.replace('_', ' ').toUpperCase()}
                                    </Badge>
                                    {d.is_active && <Badge className="bg-blue-100 text-blue-800 text-xs">Active</Badge>}
                                    <span className="text-gray-500 text-xs">by {d.ordered_by_name || 'N/A'}</span>
                                  </div>
                                  <div className="flex items-center gap-1">
                                    {d.is_active && (
                                      <Button variant="outline" size="sm" className="h-6 text-xs px-2"
                                        onClick={() => setMealLogDialog({ open: true, orderId: d.id, meal_time: 'lunch', status: 'served', notes: '' })}>
                                        Log meal
                                      </Button>
                                    )}
                                    <Button variant="ghost" size="sm" className="h-6 text-xs px-2"
                                      onClick={() => handleToggleDietOrder(d.id, d.is_active)}>
                                      {d.is_active ? 'Deactivate' : 'Reactivate'}
                                    </Button>
                                    <Button variant="ghost" size="sm" className="text-red-500 h-6 w-6 p-0"
                                      onClick={() => setConfirmState({ open: true, title: 'Delete Diet Order', message: 'Delete this diet order?',
                                        onConfirm: () => { setConfirmState({ open: false }); handleDeleteDietOrder(d.id); } })}>
                                      <Trash2 className="h-3 w-3" />
                                    </Button>
                                  </div>
                                </div>
                                <p className="text-xs text-gray-400 mt-1">{d.created_at ? new Date(d.created_at).toLocaleString() : ''}</p>
                                {d.meal_instructions && <p className="text-xs mt-1"><span className="font-medium">Meals:</span> {d.meal_instructions}</p>}
                                {d.allergies && <p className="text-xs mt-1 text-red-600"><span className="font-medium">Allergies:</span> {d.allergies}</p>}
                                {d.notes && <p className="text-xs mt-1 text-gray-600">{d.notes}</p>}
                              </div>
                            ))}
                          </div>
                        )}
                      </TabsContent>

                      {/* Lab Orders sub-tab */}
                      <TabsContent value="lab" className="space-y-3 mt-3">
                        {ip('order_labs') && (
                          <Button size="sm" onClick={() => { setLabOrderForm({ test_ids: [], priority: 'normal', notes: '' }); setLabTestSearch(''); fetchAvailableLabTests(activityAdmission.id); setShowLabOrderDialog(true); }}>
                            <Plus className="h-4 w-4 mr-1" /> Order Lab Tests
                          </Button>
                        )}
                        {admissionLabOrders.length === 0 ? (
                          <p className="text-sm text-gray-500 text-center py-4">No lab orders for this admission.</p>
                        ) : (
                          <div className="space-y-2">
                            {admissionLabOrders.map(order => (
                              <div key={order.id} className="border rounded-lg p-3 text-sm">
                                <div className="flex items-center justify-between">
                                  <div>
                                    <span className="font-medium">{order.test_name}</span>
                                    {order.test_code && <span className="text-gray-400 ml-1 text-xs">({order.test_code})</span>}
                                  </div>
                                  <Badge className={
                                    order.status === 'completed' ? 'bg-green-100 text-green-800' :
                                    order.status === 'processing' ? 'bg-blue-100 text-blue-800' :
                                    order.status === 'collected' ? 'bg-purple-100 text-purple-800' :
                                    order.status === 'cancelled' ? 'bg-red-100 text-red-800' :
                                    'bg-yellow-100 text-yellow-800'
                                  }>
                                    {order.status}
                                  </Badge>
                                </div>
                                <div className="flex items-center justify-between mt-1">
                                  <span className="text-xs text-gray-500">{order.doctor_name || 'N/A'}</span>
                                  <span className="text-xs text-gray-600">₹{parseFloat(order.amount || 0).toFixed(2)}</span>
                                </div>
                                {order.priority !== 'normal' && (
                                  <Badge className="mt-1 bg-red-100 text-red-800 text-xs">{order.priority.toUpperCase()}</Badge>
                                )}
                                <p className="text-xs text-gray-400 mt-1">{order.order_date ? new Date(order.order_date).toLocaleString() : ''}</p>
                                {order.has_report && <p className="text-xs text-green-600 mt-1">Report available</p>}
                                {order.notes && <p className="text-xs text-gray-600 mt-1">{order.notes}</p>}
                              </div>
                            ))}
                          </div>
                        )}
                      </TabsContent>

                      {/* Medications sub-tab */}
                      <TabsContent value="medications" className="space-y-3 mt-3">
                        {ip('prescribe_medications') && (
                          <div className="flex justify-end">
                            <Button size="sm" onClick={() => {
                              setPrescriptionForm({ notes: '', items: [{ ...BLANK_RX_ITEM }] });
                              setMedicineSearchResults([]);
                              setShowPrescriptionDialog(true);
                            }}>
                              <Plus className="h-4 w-4 mr-1" /> Add Prescription
                            </Button>
                          </div>
                        )}
                        {admissionMedications.length === 0 ? (
                          <p className="text-sm text-gray-500 text-center py-4">No prescriptions linked to this admission.</p>
                        ) : (
                          <div className="space-y-3">
                            {admissionMedications.map(rx => (
                              <div key={`${rx.type}-${rx.id}`} className="border rounded-lg p-3 text-sm">
                                <div className="flex items-center justify-between mb-2">
                                  <div>
                                    <span className="font-medium">{rx.prescription_number}</span>
                                    <span className="text-gray-500 ml-2">by {rx.doctor_name}</span>
                                  </div>
                                  <Badge className={rx.status === 'dispensed' ? 'bg-green-100 text-green-800' : rx.status === 'pending' ? 'bg-yellow-100 text-yellow-800' : 'bg-gray-100 text-gray-800'}>
                                    {rx.status}
                                  </Badge>
                                </div>
                                <p className="text-xs text-gray-400 mb-2">{rx.date ? new Date(rx.date).toLocaleString() : ''}</p>
                                {rx.medicines && rx.medicines.length > 0 && (
                                  <div className="bg-gray-50 rounded p-2 space-y-1">
                                    {rx.medicines.map((med, idx) => (
                                      <div key={idx} className="flex justify-between text-xs">
                                        <span>{med.name} {med.dosage ? `- ${med.dosage}` : ''} {med.duration ? `(${med.duration})` : ''}</span>
                                        {rx.type === 'pharmacy' && <span className="text-gray-600">₹{parseFloat(med.total_price || 0).toFixed(2)}</span>}
                                      </div>
                                    ))}
                                  </div>
                                )}
                                {rx.type === 'pharmacy' && rx.total_amount > 0 && (
                                  <div className="flex justify-between mt-2 pt-1 border-t font-medium text-xs">
                                    <span>Total</span><span>₹{parseFloat(rx.total_amount).toFixed(2)}</span>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </TabsContent>

                      {/* Bill sub-tab */}
                      <TabsContent value="bill" className="space-y-3 mt-3">
                        {billData ? (
                          <>
                            {/* Package banner if applied */}
                            {admissionPackage && billData.package && (
                              <div className="border-l-4 border-purple-500 bg-purple-50 p-3 rounded text-sm">
                                <div className="flex justify-between items-start">
                                  <div>
                                    <div className="font-semibold flex items-center gap-1.5"><Package className="h-4 w-4" /> {billData.package.package_name}</div>
                                    <p className="text-xs text-gray-600 mt-0.5">Agreed price ₹{billData.package.agreed_price.toFixed(2)} · {billData.package.included_stay_days} days included · Excess after that ₹{billData.package.excess_per_day_charge.toFixed(2)}/day</p>
                                    <p className="text-xs text-gray-600">Includes: {(billData.package.included_services || []).join(', ') || 'core only'}</p>
                                  </div>
                                  <Button variant="ghost" size="sm" onClick={() => setConfirmState({ open: true, title: 'Remove package?', description: 'Bill will revert to itemised mode.', onConfirm: () => { setConfirmState({ open: false }); handleRemovePackage(); } })}>
                                    <X className="h-4 w-4" />
                                  </Button>
                                </div>
                              </div>
                            )}

                            {/* Bills history */}
                            {admissionBills.length > 0 && (
                              <div className="border rounded p-3 text-sm">
                                <p className="font-semibold mb-2 flex items-center gap-1.5"><Receipt className="h-4 w-4" /> Bills issued ({admissionBills.length})</p>
                                <div className="space-y-1">
                                  {admissionBills.map(b => (
                                    <div key={b.id} className="flex items-center justify-between text-xs border-b last:border-0 pb-1">
                                      <div>
                                        <span className="font-mono">{b.bill_number}</span>
                                        <Badge variant="outline" className="ml-2 text-xs">{b.bill_subtype}</Badge>
                                        {b.status === 'cancelled' && <Badge variant="destructive" className="ml-1 text-xs">cancelled</Badge>}
                                        <span className="text-gray-500 ml-2">{b.bill_date && new Date(b.bill_date).toLocaleDateString()}</span>
                                      </div>
                                      <div className="flex items-center gap-2">
                                        <span className={`font-semibold ${b.status === 'cancelled' ? 'line-through text-gray-400' : ''}`}>₹{b.total_amount.toFixed(2)}</span>
                                        {b.status !== 'cancelled' && (
                                          <>
                                            <Button variant="ghost" size="sm" className="h-6 px-2 text-xs" onClick={() => openSplitDialog(b)}>Split</Button>
                                            <Button variant="ghost" size="sm" className="h-6 px-2 text-xs text-red-600 hover:text-red-700"
                                              onClick={() => setCancelBillDialog({ open: true, bill: b, reason: '' })}>Cancel</Button>
                                          </>
                                        )}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Current breakdown */}
                            <div className="border rounded-lg p-3 text-sm space-y-2">
                              <div className="flex items-center justify-between mb-1">
                                <p className="font-semibold">Current charges {billData.unbilled_only && <Badge variant="outline" className="ml-1 text-xs">unbilled only</Badge>}</p>
                                {!admissionPackage && (
                                  <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => { setApplyPackageForm({ package_id: '', agreed_price: '', notes: '' }); setShowApplyPackageDialog(true); }}>
                                    <Package className="h-3.5 w-3.5 mr-1" /> Apply Package
                                  </Button>
                                )}
                              </div>
                              <div className="flex justify-between"><span className="text-gray-500">Room ({billData.room?.room_number} - {billData.stay_days} days)</span><span>₹{billData.room_total?.toFixed(2)}</span></div>
                              {billData.visits && Object.entries(billData.visits).map(([type, data]) => (
                                <div key={type} className="flex justify-between">
                                  <span className="text-gray-500">{type.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())} (x{data.count})</span>
                                  <span>₹{data.total.toFixed(2)}</span>
                                </div>
                              ))}
                              {billData.ot_total > 0 && (
                                <div className="flex justify-between">
                                  <span className="text-gray-500">OT Procedures ({(billData.ot_entries || []).length})</span>
                                  <span>₹{billData.ot_total.toFixed(2)}</span>
                                </div>
                              )}
                              {billData.ancillary_total > 0 && (
                                <div className="flex justify-between">
                                  <span className="text-gray-500">Ancillary services ({(billData.ancillary_entries || []).length})</span>
                                  <span>₹{billData.ancillary_total.toFixed(2)}</span>
                                </div>
                              )}
                              {billData.pharmacy_total > 0 && (
                                <div className="flex justify-between">
                                  <span className="text-gray-500">Pharmacy / Medications</span>
                                  <span>₹{billData.pharmacy_total.toFixed(2)}</span>
                                </div>
                              )}
                              {billData.lab_total > 0 && (
                                <div className="flex justify-between">
                                  <span className="text-gray-500">Lab Tests</span>
                                  <span>₹{billData.lab_total.toFixed(2)}</span>
                                </div>
                              )}
                              <div className="border-t pt-2 flex justify-between font-semibold">
                                <span>{billData.package ? 'Excess + Package' : 'Subtotal'}</span><span>₹{billData.grand_total?.toFixed(2)}</span>
                              </div>
                              {billData.package && (
                                <p className="text-xs text-purple-700">Package ₹{billData.package.agreed_price.toFixed(2)} + Excess ₹{billData.package.excess_total.toFixed(2)}</p>
                              )}
                            </div>

                            {ip('manage_ancillary_charges') && (
                              <div className="flex gap-2 flex-wrap">
                                <Button size="sm" variant="outline" onClick={() => { setAncillaryForm({ service_id: '', quantity: 1, unit_price: '', notes: '' }); setShowAncillaryDialog(true); }}>
                                  <Plus className="h-4 w-4 mr-1" /> Add Service Charge
                                </Button>
                              </div>
                            )}

                            {/* Discount & Tax */}
                            <div className="border rounded-lg p-3 text-sm space-y-3">
                              <div className="flex items-center gap-2">
                                <Label className="text-xs w-16">Discount</Label>
                                <Select value={billDiscount.type} onValueChange={v => setBillDiscount(p => ({ ...p, type: v }))}>
                                  <SelectTrigger className="w-[110px] h-8 text-xs"><SelectValue /></SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="flat">Flat (₹)</SelectItem>
                                    <SelectItem value="percentage">Percent (%)</SelectItem>
                                  </SelectContent>
                                </Select>
                                <Input type="number" min="0" step="0.01" className="w-24 h-8 text-xs"
                                  value={billDiscount.value || ''} onChange={e => setBillDiscount(p => ({ ...p, value: parseFloat(e.target.value) || 0 }))} placeholder="0" />
                                {billDiscount.value > 0 && (
                                  <span className="text-xs text-green-600">
                                    -₹{(billDiscount.type === 'percentage' ? (billData.grand_total * billDiscount.value / 100) : Math.min(billDiscount.value, billData.grand_total)).toFixed(2)}
                                  </span>
                                )}
                              </div>
                              <div className="flex items-center gap-2">
                                <Label className="text-xs w-16">Tax %</Label>
                                <Input type="number" min="0" max="100" step="0.01" className="w-24 h-8 text-xs"
                                  value={billTaxPct || ''} onChange={e => setBillTaxPct(parseFloat(e.target.value) || 0)} placeholder="0" />
                                {billTaxPct > 0 && (() => {
                                  const disc = billDiscount.type === 'percentage' ? (billData.grand_total * billDiscount.value / 100) : Math.min(billDiscount.value || 0, billData.grand_total);
                                  const afterDisc = billData.grand_total - disc;
                                  return <span className="text-xs text-orange-600">+₹{(afterDisc * billTaxPct / 100).toFixed(2)}</span>;
                                })()}
                              </div>
                              {(billDiscount.value > 0 || billTaxPct > 0) && (() => {
                                const sub = billData.grand_total || 0;
                                const disc = billDiscount.type === 'percentage' ? (sub * (billDiscount.value || 0) / 100) : Math.min(billDiscount.value || 0, sub);
                                const afterDisc = sub - disc;
                                const tax = afterDisc * (billTaxPct || 0) / 100;
                                return (
                                  <div className="border-t pt-2 flex justify-between font-semibold">
                                    <span>Final Total</span><span>₹{(afterDisc + tax).toFixed(2)}</span>
                                  </div>
                                );
                              })()}
                            </div>

                            <div className="flex gap-2 flex-wrap">
                              {ip('finalize_bill') && (
                                <Button size="sm" onClick={openReviewBillDialog} disabled={loading}>
                                  <Receipt className="h-4 w-4 mr-1" /> Review & Generate Final Bill
                                </Button>
                              )}
                              {ip('finalize_bill') && (
                                <Button size="sm" variant="outline" onClick={handleFinalizeBill} disabled={loading} title="Finalize directly using the auto-computed breakdown without review">
                                  {loading ? 'Finalizing...' : 'Quick Finalize'}
                                </Button>
                              )}
                              {ip('generate_interim_bill') && (
                                <Button size="sm" variant="outline" onClick={handleGenerateInterim} disabled={loading}>
                                  <Receipt className="h-4 w-4 mr-1" /> Generate Interim
                                </Button>
                              )}
                              <Button size="sm" variant="outline" onClick={() => handlePrintBillPdf(activityAdmission.id)}>
                                <FileText className="h-4 w-4 mr-1" /> Print Bill
                              </Button>
                            </div>
                          </>
                        ) : (
                          <p className="text-sm text-gray-500 text-center py-4">Loading bill...</p>
                        )}
                      </TabsContent>

                      {/* Deposits sub-tab */}
                      <TabsContent value="deposits" className="space-y-3 mt-3">
                        {balance && (
                          <div className="border rounded p-3 bg-gray-50 text-sm">
                            <div className="grid grid-cols-2 gap-2">
                              <div><span className="text-gray-500">Collected:</span> <span className="font-semibold">₹{balance.total_collected.toFixed(2)}</span></div>
                              <div><span className="text-gray-500">Refunded:</span> <span className="font-semibold">₹{balance.total_refunded.toFixed(2)}</span></div>
                              <div><span className="text-gray-500">Net deposits:</span> <span className="font-semibold">₹{balance.net_deposits.toFixed(2)}</span></div>
                              <div><span className="text-gray-500">Total billed:</span> <span className="font-semibold">₹{balance.total_billed.toFixed(2)}</span></div>
                            </div>
                            <div className={`mt-2 pt-2 border-t font-semibold ${balance.balance > 0 ? 'text-green-700' : balance.balance < 0 ? 'text-red-700' : ''}`}>
                              Balance: ₹{balance.balance.toFixed(2)}
                              <span className="text-xs font-normal ml-2 text-gray-500">
                                {balance.balance > 0 ? '(patient credit / refund due)' :
                                 balance.balance < 0 ? '(patient owes)' : ''}
                              </span>
                            </div>
                          </div>
                        )}
                        <div className="flex gap-2">
                          {ip('receive_deposits') && (
                            <Button size="sm" onClick={() => { setDepositForm({ amount: '', payment_method: 'cash', deposit_type: deposits.length === 0 ? 'initial' : 'topup', reference_number: '', notes: '' }); setShowDepositDialog(true); }}>
                              <Plus className="h-4 w-4 mr-1" /> Receive Deposit
                            </Button>
                          )}
                          {balance && balance.balance > 0 && ip('issue_refunds') && (
                            <Button size="sm" variant="outline" onClick={() => { setRefundForm({ amount: balance.balance.toFixed(2), payment_method: 'cash', reference_number: '', notes: '' }); setShowRefundDialog(true); }}>
                              <Wallet className="h-4 w-4 mr-1" /> Issue Refund
                            </Button>
                          )}
                        </div>
                        {deposits.length === 0 ? (
                          <div className="text-center text-sm text-gray-500 py-8">No deposits recorded for this admission.</div>
                        ) : (
                          <div className="border rounded overflow-hidden">
                            <table className="w-full text-xs">
                              <thead className="bg-gray-50">
                                <tr className="text-left">
                                  <th className="px-2 py-2">Receipt</th>
                                  <th className="px-2 py-2">Date</th>
                                  <th className="px-2 py-2">Type</th>
                                  <th className="px-2 py-2">Method</th>
                                  <th className="px-2 py-2 text-right">Amount</th>
                                  <th className="px-2 py-2">By</th>
                                  <th className="px-2 py-2"></th>
                                </tr>
                              </thead>
                              <tbody>
                                {deposits.map(d => (
                                  <tr key={d.id} className={`border-t ${d.deposit_type === 'refund' ? 'bg-orange-50' : ''}`}>
                                    <td className="px-2 py-1.5 font-mono">{d.deposit_number}</td>
                                    <td className="px-2 py-1.5">{new Date(d.received_at).toLocaleString()}</td>
                                    <td className="px-2 py-1.5"><Badge variant="outline" className="text-xs">{d.deposit_type}</Badge></td>
                                    <td className="px-2 py-1.5">{d.payment_method}</td>
                                    <td className={`px-2 py-1.5 text-right font-semibold ${d.deposit_type === 'refund' ? 'text-orange-700' : ''}`}>
                                      {d.deposit_type === 'refund' ? '-' : ''}₹{d.amount.toFixed(2)}
                                    </td>
                                    <td className="px-2 py-1.5">{d.received_by_name || '–'}</td>
                                    <td className="px-2 py-1.5">
                                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => handlePrintDepositReceipt(d.id)}>
                                        <FileText className="h-3.5 w-3.5" />
                                      </Button>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </TabsContent>

                      {/* Consents sub-tab */}
                      <TabsContent value="consents" className="space-y-3 mt-3">
                        <div className="flex justify-between items-center">
                          <p className="text-sm text-gray-600">Signed consent forms for procedures, anaesthesia, blood transfusions, and more.</p>
                          <Button size="sm" onClick={() => { setConsentForm({ consent_type: 'surgical', template_id: '', procedure_name: '', doctor_id: '', risks_explained: '', patient_signature: '', signed_by: 'patient', guardian_name: '', guardian_relationship: '', witness_name: '', witness_signature: '', notes: '' }); setShowConsentDialog(true); }}>
                            <Plus className="h-4 w-4 mr-1" /> New Consent
                          </Button>
                        </div>
                        {consents.length === 0 ? (
                          <div className="text-center text-sm text-gray-500 py-8">No consents recorded.</div>
                        ) : (
                          <div className="space-y-2">
                            {consents.map(c => (
                              <div key={c.id} className={`border rounded p-3 ${c.withdrawn_at ? 'bg-orange-50 border-orange-300' : ''}`}>
                                <div className="flex justify-between items-start gap-2">
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                      <FileSignature className="h-4 w-4 text-gray-500" />
                                      <span className="font-medium text-sm">{c.consent_type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                                      {c.procedure_name && <span className="text-xs text-gray-500">— {c.procedure_name}</span>}
                                      {c.withdrawn_at && <Badge className="text-xs bg-orange-100 text-orange-800">withdrawn</Badge>}
                                      {!c.withdrawn_at && <Badge className="text-xs bg-green-100 text-green-800">active</Badge>}
                                    </div>
                                    <div className="text-xs text-gray-600 mt-1">
                                      Signed by {c.signed_by}
                                      {c.guardian_name && <> ({c.guardian_name} — {c.guardian_relationship})</>}
                                      {c.doctor_name && <> · Dr: {c.doctor_name}</>}
                                      {c.witness_name && <> · Witness: {c.witness_name}</>}
                                    </div>
                                    <p className="text-xs text-gray-400 mt-1">Signed {new Date(c.signed_at).toLocaleString()}</p>
                                    {c.withdrawn_at && (
                                      <p className="text-xs text-orange-700 mt-1">Withdrawn {new Date(c.withdrawn_at).toLocaleString()} — {c.withdrawal_reason}</p>
                                    )}
                                  </div>
                                  <div className="flex gap-1">
                                    <Button size="sm" variant="ghost" className="h-7" onClick={() => handlePrintConsent(c.id)}>
                                      <FileText className="h-4 w-4" />
                                    </Button>
                                    {!c.withdrawn_at && (
                                      <Button size="sm" variant="ghost" className="h-7 text-orange-600" onClick={() => { setWithdrawingConsent(c); setWithdrawReason(''); setShowWithdrawConsentDialog(true); }}>
                                        Withdraw
                                      </Button>
                                    )}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </TabsContent>

                      {/* Staff sub-tab — nurse assignments + transfer history + ward transfer */}
                      <TabsContent value="staff" className="space-y-4 mt-3">
                        {/* Nurse assignments */}
                        <div>
                          <div className="flex justify-between items-center mb-2">
                            <h3 className="text-sm font-semibold flex items-center gap-1.5"><UserPlus className="h-4 w-4" /> Nurse Assignments</h3>
                            {ip('assign_nurses') && (
                              <Button size="sm" onClick={() => { setNurseAssignForm({ nurse_id: '', shift: 'morning', assignment_date: new Date().toISOString().slice(0, 10), is_primary: false, notes: '' }); setShowNurseAssignDialog(true); }}>
                                <Plus className="h-4 w-4 mr-1" /> Assign Nurse
                              </Button>
                            )}
                          </div>
                          {nurseAssignments.length === 0 ? (
                            <div className="text-xs text-gray-500 text-center py-4 border rounded">No nurses assigned</div>
                          ) : (
                            <div className="space-y-1">
                              {nurseAssignments.map(a => (
                                <div key={a.id} className={`flex justify-between items-center border rounded p-2 ${a.is_primary ? 'bg-blue-50 border-blue-300' : ''}`}>
                                  <div className="text-sm">
                                    <span className="font-medium">{a.nurse_name}</span>
                                    <Badge variant="outline" className="ml-2 text-xs">{a.shift}</Badge>
                                    {a.is_primary && <Badge className="ml-1 text-xs bg-blue-100 text-blue-800">primary</Badge>}
                                    <span className="text-xs text-gray-500 ml-2">{a.assignment_date && new Date(a.assignment_date).toLocaleDateString()}</span>
                                    {a.notes && <p className="text-xs text-gray-500 mt-0.5">{a.notes}</p>}
                                  </div>
                                  <Button size="sm" variant="ghost" className="h-6 w-6 p-0" onClick={() => handleRemoveNurseAssignment(a.id)}>
                                    <Trash2 className="h-3.5 w-3.5 text-red-500" />
                                  </Button>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>

                        {/* Transfer history */}
                        <div>
                          <div className="flex justify-between items-center mb-2">
                            <h3 className="text-sm font-semibold flex items-center gap-1.5"><ArrowRightLeft className="h-4 w-4" /> Bed / Ward Transfers</h3>
                            {ip('initiate_ward_transfer') && (
                              <Button size="sm" variant="outline" onClick={() => { setWardTransferForm({ to_room_id: '', to_bed_id: '', reason: '', transfer_note: '' }); fetchAvailableRooms(); setShowWardTransferDialog(true); }}>
                                <Plus className="h-4 w-4 mr-1" /> Initiate Ward Transfer
                              </Button>
                            )}
                          </div>
                          {transferHistory.length === 0 ? (
                            <div className="text-xs text-gray-500 text-center py-4 border rounded">No transfers recorded</div>
                          ) : (
                            <div className="space-y-1">
                              {transferHistory.map(t => {
                                const statusColor = {
                                  completed: 'bg-gray-100 text-gray-700',
                                  pending: 'bg-yellow-100 text-yellow-800',
                                  accepted: 'bg-green-100 text-green-800',
                                  cancelled: 'bg-red-100 text-red-800',
                                }[t.status] || 'bg-gray-100 text-gray-700';
                                return (
                                  <div key={t.id} className={`border rounded p-2 text-sm ${t.status === 'pending' ? 'border-yellow-300 bg-yellow-50' : ''}`}>
                                    <div className="flex justify-between items-start">
                                      <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap">
                                          <Badge className={`text-xs ${statusColor}`}>{t.status}</Badge>
                                          <Badge variant="outline" className="text-xs">{t.transfer_type}</Badge>
                                          <span className="text-xs">
                                            {t.from_room_number || '—'}{t.from_bed_label ? `/${t.from_bed_label}` : ''} → {t.to_room_number}{t.to_bed_label ? `/${t.to_bed_label}` : ''}
                                          </span>
                                        </div>
                                        <p className="text-xs text-gray-600 mt-1"><b>Reason:</b> {t.reason}</p>
                                        {t.transfer_note && <p className="text-xs italic text-gray-600 mt-0.5">{t.transfer_note}</p>}
                                        <p className="text-xs text-gray-400 mt-1">{new Date(t.transferred_at).toLocaleString()} by {t.transferred_by_name || '—'}</p>
                                      </div>
                                      {t.status === 'pending' && (
                                        <div className="flex gap-1">
                                          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => handleAcceptTransfer(t.id)}>Accept</Button>
                                          <Button size="sm" variant="ghost" className="h-7 text-xs text-red-600" onClick={() => handleCancelPendingTransfer(t.id)}>Cancel</Button>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      </TabsContent>

                      {/* Insurance sub-tab */}
                      <TabsContent value="insurance" className="space-y-4 mt-3">
                        {(() => {
                          const adm = activityAdmission;
                          const cs = adm?.claim_status || 'none';
                          const nextActions = {
                            none: adm?.insurance_provider ? [{ status: 'draft', label: 'Create Draft Claim', variant: 'default' }] : [],
                            draft: [
                              { status: 'submitted', label: 'Submit Claim', variant: 'default' },
                              { status: 'none', label: 'Cancel Draft', variant: 'outline' },
                            ],
                            submitted: [
                              { status: 'approved', label: 'Mark Approved', variant: 'default' },
                              { status: 'rejected', label: 'Mark Rejected', variant: 'destructive' },
                              { status: 'draft', label: 'Revert to Draft', variant: 'outline' },
                            ],
                            approved: [],
                            rejected: [{ status: 'draft', label: 'Resubmit as Draft', variant: 'outline' }],
                          };

                          return (
                            <>
                              {/* Current Status */}
                              <div className="border rounded-lg p-4">
                                <div className="flex items-center justify-between mb-3">
                                  <div className="flex items-center gap-2">
                                    <Shield className="h-5 w-5 text-gray-500" />
                                    <h4 className="font-medium text-sm">Insurance Claim</h4>
                                  </div>
                                  <Badge className={claimStatusColor[cs]}>{claimStatusLabel[cs]}</Badge>
                                </div>

                                <div className="space-y-2 text-sm">
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Provider</span>
                                    <span>{adm?.insurance_provider || '—'}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Policy #</span>
                                    <span>{adm?.policy_number || '—'}</span>
                                  </div>
                                  <div className="flex justify-between">
                                    <span className="text-gray-500">Claim Ref</span>
                                    <span>{adm?.claim_reference || '—'}</span>
                                  </div>
                                  {adm?.claim_amount != null && adm.claim_amount > 0 && (
                                    <div className="flex justify-between">
                                      <span className="text-gray-500">Claim Amount</span>
                                      <span className="font-medium">₹{parseFloat(adm.claim_amount).toFixed(2)}</span>
                                    </div>
                                  )}
                                  {adm?.claim_submitted_at && (
                                    <div className="flex justify-between">
                                      <span className="text-gray-500">Submitted On</span>
                                      <span>{new Date(adm.claim_submitted_at).toLocaleDateString()}</span>
                                    </div>
                                  )}
                                  {adm?.claim_notes && (
                                    <div className="pt-2 border-t">
                                      <span className="text-gray-500 text-xs">Notes</span>
                                      <p className="text-xs mt-1">{adm.claim_notes}</p>
                                    </div>
                                  )}
                                </div>
                              </div>

                              {/* Workflow Progress */}
                              <div className="flex items-center gap-1 text-xs px-1">
                                {['draft', 'submitted', 'approved'].map((step, idx) => (
                                  <React.Fragment key={step}>
                                    <div className={`flex items-center gap-1 px-2 py-1 rounded ${
                                      cs === step ? 'bg-blue-100 text-blue-800 font-medium' :
                                      (cs === 'approved' || (cs === 'submitted' && idx < 2) || (cs === 'draft' && idx < 1) || (['submitted', 'approved'].includes(cs) && idx === 0) || (cs === 'approved' && idx <= 1))
                                        ? 'bg-green-50 text-green-700' : 'bg-gray-50 text-gray-400'
                                    }`}>
                                      {step.charAt(0).toUpperCase() + step.slice(1)}
                                    </div>
                                    {idx < 2 && <ChevronRight className="h-3 w-3 text-gray-300" />}
                                  </React.Fragment>
                                ))}
                                {cs === 'rejected' && (
                                  <>
                                    <ChevronRight className="h-3 w-3 text-gray-300" />
                                    <div className="px-2 py-1 rounded bg-red-100 text-red-800 font-medium">Rejected</div>
                                  </>
                                )}
                              </div>

                              {/* No insurance warning */}
                              {!adm?.insurance_provider && cs === 'none' && (
                                <p className="text-sm text-gray-500 text-center py-2">
                                  No insurance provider recorded. Update admission details to add insurance info before creating a claim.
                                </p>
                              )}

                              {/* Action Buttons */}
                              {(nextActions[cs] || []).length > 0 && (
                                <div className="space-y-3">
                                  {(cs === 'none' || cs === 'draft' || cs === 'rejected') && (
                                    <div className="space-y-2">
                                      <div className="grid grid-cols-2 gap-2">
                                        <div>
                                          <Label className="text-xs">Claim Amount (₹)</Label>
                                          <Input type="number" min="0" step="0.01" placeholder="0.00"
                                            defaultValue={adm?.claim_amount || ''}
                                            id={`claim-amount-${adm?.id}`} />
                                        </div>
                                        <div>
                                          <Label className="text-xs">Claim Reference</Label>
                                          <Input placeholder="Ref #" defaultValue={adm?.claim_reference || ''}
                                            id={`claim-ref-${adm?.id}`} />
                                        </div>
                                      </div>
                                      <div>
                                        <Label className="text-xs">Notes</Label>
                                        <Textarea placeholder="Claim notes..." rows={2}
                                          defaultValue={adm?.claim_notes || ''}
                                          id={`claim-notes-${adm?.id}`} />
                                      </div>
                                    </div>
                                  )}

                                  <div className="flex gap-2 flex-wrap">
                                    {(nextActions[cs] || []).map(action => (
                                      <Button key={action.status} size="sm" variant={action.variant} disabled={loading}
                                        onClick={() => {
                                          const amountEl = document.getElementById(`claim-amount-${adm?.id}`);
                                          const refEl = document.getElementById(`claim-ref-${adm?.id}`);
                                          const notesEl = document.getElementById(`claim-notes-${adm?.id}`);
                                          handleClaimStatusUpdate(adm.id, {
                                            claim_status: action.status,
                                            claim_amount: amountEl ? parseFloat(amountEl.value) || null : null,
                                            claim_reference: refEl ? refEl.value || null : null,
                                            claim_notes: notesEl ? notesEl.value || null : null,
                                          });
                                        }}>
                                        {action.label}
                                      </Button>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </>
                          );
                        })()}
                      </TabsContent>

                      {/* Documents sub-tab */}
                      <TabsContent value="docs" className="space-y-3 mt-3">
                        {/* Upload area */}
                        <div className="border-2 border-dashed rounded-lg p-4 text-center">
                          <input type="file" id="doc-upload-input" className="hidden"
                            accept=".pdf,.jpg,.jpeg,.png,.gif,.webp,.doc,.docx"
                            onChange={e => {
                              const file = e.target.files?.[0];
                              if (file && activityAdmission) {
                                const docType = prompt('Document type:\nconsent_form, referral_letter, insurance_doc, lab_report, other', 'other') || 'other';
                                handleDocUpload(activityAdmission.id, file, docType, file.name, '');
                              }
                              e.target.value = '';
                            }} />
                          <Button variant="outline" size="sm" disabled={docUploading}
                            onClick={() => document.getElementById('doc-upload-input')?.click()}>
                            <Upload className="h-4 w-4 mr-1" /> {docUploading ? 'Uploading...' : 'Upload Document'}
                          </Button>
                          <p className="text-xs text-gray-400 mt-1">PDF, images, Word docs (max 10MB)</p>
                        </div>

                        {admissionDocs.length === 0 ? (
                          <p className="text-sm text-gray-500 text-center py-4">No documents attached.</p>
                        ) : (
                          <div className="space-y-2">
                            {admissionDocs.map(doc => (
                              <div key={doc.id} className="border rounded-lg p-3 text-sm flex items-center justify-between">
                                <div className="flex items-center gap-2 min-w-0">
                                  <Paperclip className="h-4 w-4 text-gray-400 shrink-0" />
                                  <div className="min-w-0">
                                    <p className="font-medium truncate">{doc.document_name}</p>
                                    <div className="flex items-center gap-2 text-xs text-gray-500">
                                      <Badge className="bg-gray-100 text-gray-700 text-xs">{doc.document_type.replace('_', ' ')}</Badge>
                                      <span>{doc.file_size ? `${(doc.file_size / 1024).toFixed(0)} KB` : ''}</span>
                                      <span>{doc.uploaded_by_name || ''}</span>
                                      <span>{doc.created_at ? new Date(doc.created_at).toLocaleDateString() : ''}</span>
                                    </div>
                                    {doc.notes && <p className="text-xs text-gray-400 mt-1">{doc.notes}</p>}
                                  </div>
                                </div>
                                <div className="flex gap-1 shrink-0">
                                  <Button variant="ghost" size="sm" onClick={() => {
                                    window.open(`/api/inpatient/documents/${doc.id}/download`, '_blank');
                                  }} title="Download">
                                    <Download className="h-4 w-4" />
                                  </Button>
                                  <Button variant="ghost" size="sm" className="text-red-500"
                                    onClick={() => setConfirmState({
                                      open: true, title: 'Delete Document',
                                      message: `Delete "${doc.document_name}"?`,
                                      onConfirm: () => { setConfirmState({ open: false }); handleDocDelete(doc.id); }
                                    })} title="Delete">
                                    <Trash2 className="h-3 w-3" />
                                  </Button>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </TabsContent>

                      {/* Vitals sub-tab */}
                      <TabsContent value="vitals" className="space-y-3 mt-3">
                        <div className="flex justify-between items-center">
                          <div className="text-sm text-gray-600">
                            {latestVitals ? (
                              <>Latest: BP {latestVitals.bp_systolic || '–'}/{latestVitals.bp_diastolic || '–'} · HR {latestVitals.heart_rate || '–'} · SpO₂ {latestVitals.spo2 || '–'}% · Temp {latestVitals.temperature_c || '–'}°C{latestVitals.is_abnormal && <span className="ml-2 inline-flex items-center text-red-600 font-medium"><AlertTriangle className="h-3.5 w-3.5 mr-0.5" />Abnormal</span>}</>
                            ) : 'No vitals recorded yet'}
                          </div>
                          <Button size="sm" onClick={() => { setVitalsForm(VITALS_BLANK); setShowVitalsDialog(true); }}>
                            <Plus className="h-4 w-4 mr-1" /> Record Vitals
                          </Button>
                        </div>
                        {vitals.length === 0 ? (
                          <div className="text-center text-sm text-gray-500 py-8">No vital signs recorded</div>
                        ) : (
                          <div className="border rounded overflow-hidden">
                            <table className="w-full text-xs">
                              <thead className="bg-gray-50">
                                <tr className="text-left">
                                  <th className="px-2 py-2">Time</th>
                                  <th className="px-2 py-2">BP</th>
                                  <th className="px-2 py-2">HR</th>
                                  <th className="px-2 py-2">RR</th>
                                  <th className="px-2 py-2">Temp</th>
                                  <th className="px-2 py-2">SpO₂</th>
                                  <th className="px-2 py-2">Glu</th>
                                  <th className="px-2 py-2">Pain</th>
                                  <th className="px-2 py-2">By</th>
                                  <th className="px-2 py-2"></th>
                                </tr>
                              </thead>
                              <tbody>
                                {vitals.map(v => {
                                  const flags = v.abnormal_flags || [];
                                  const cell = (field, val, suffix = '') => (
                                    <td className={`px-2 py-1.5 ${flags.includes(field) ? 'text-red-600 font-semibold' : ''}`}>
                                      {val ?? '–'}{val != null ? suffix : ''}
                                    </td>
                                  );
                                  return (
                                    <tr key={v.id} className={`border-t ${v.is_abnormal ? 'bg-red-50' : ''}`}>
                                      <td className="px-2 py-1.5 whitespace-nowrap">{new Date(v.recorded_at).toLocaleString()}</td>
                                      <td className={`px-2 py-1.5 ${(flags.includes('bp_systolic') || flags.includes('bp_diastolic')) ? 'text-red-600 font-semibold' : ''}`}>
                                        {v.bp_systolic ?? '–'}/{v.bp_diastolic ?? '–'}
                                      </td>
                                      {cell('heart_rate', v.heart_rate)}
                                      {cell('respiratory_rate', v.respiratory_rate)}
                                      {cell('temperature_c', v.temperature_c, '°')}
                                      {cell('spo2', v.spo2, '%')}
                                      {cell('blood_glucose', v.blood_glucose)}
                                      {cell('pain_score', v.pain_score)}
                                      <td className="px-2 py-1.5">{v.recorded_by_name || '–'}</td>
                                      <td className="px-2 py-1.5">
                                        <Button variant="ghost" size="sm" className="h-6 w-6 p-0"
                                          onClick={() => setConfirmState({ open: true, title: 'Delete vitals?', description: 'This entry will be removed.', onConfirm: () => { setConfirmState({ open: false }); handleDeleteVitals(v.id); } })}>
                                          <Trash2 className="h-3.5 w-3.5 text-red-500" />
                                        </Button>
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </TabsContent>

                      {/* MAR sub-tab */}
                      <TabsContent value="mar" className="space-y-3 mt-3">
                        <div className="flex justify-between items-center gap-2 flex-wrap">
                          <div className="flex items-center gap-2">
                            <Label className="text-xs">Date</Label>
                            <Input type="date" value={marDate} onChange={(e) => setMarDate(e.target.value)} className="h-8 w-40" />
                          </div>
                          <div className="flex gap-2">
                            <Button size="sm" variant="outline" onClick={handleGenerateMAR} disabled={loading}>
                              <Clock className="h-4 w-4 mr-1" /> Generate Schedule (24h)
                            </Button>
                            <Button size="sm" onClick={() => { setPrnForm({ prescription_item_id: '', dose_given: '', route: '', site: '', prn_indication: '', notes: '' }); setShowPrnDialog(true); }}>
                              <Pill className="h-4 w-4 mr-1" /> Record PRN
                            </Button>
                          </div>
                        </div>
                        {mar.length === 0 ? (
                          <div className="text-center text-sm text-gray-500 py-8">
                            No scheduled doses. Click "Generate Schedule" after creating prescriptions with frequency set.
                          </div>
                        ) : (
                          <div className="space-y-2">
                            {mar.map(d => {
                              const statusColor = {
                                scheduled: 'bg-blue-100 text-blue-800',
                                given: 'bg-green-100 text-green-800',
                                missed: 'bg-red-100 text-red-800',
                                refused: 'bg-orange-100 text-orange-800',
                                held: 'bg-gray-100 text-gray-800',
                              }[d.status] || 'bg-gray-100 text-gray-800';
                              const overdue = d.status === 'scheduled' && d.scheduled_time && new Date(d.scheduled_time) < new Date();
                              return (
                                <div key={d.id} className={`p-3 border rounded ${overdue ? 'border-red-300 bg-red-50' : ''}`}>
                                  <div className="flex justify-between items-start gap-3">
                                    <div className="flex-1 min-w-0">
                                      <div className="flex items-center gap-2 flex-wrap">
                                        <Pill className="h-4 w-4 text-gray-500" />
                                        <span className="font-medium text-sm">{d.medicine_name || `Med #${d.medicine_id}`}</span>
                                        {d.dosage && <span className="text-xs text-gray-500">· {d.dosage}</span>}
                                        {d.route && <span className="text-xs text-gray-500">· {d.route}</span>}
                                        {d.is_prn && <Badge variant="outline" className="text-xs">PRN</Badge>}
                                        <Badge className={`text-xs ${statusColor}`}>{d.status}</Badge>
                                        {overdue && <Badge variant="outline" className="text-xs text-red-600 border-red-300">overdue</Badge>}
                                      </div>
                                      <div className="text-xs text-gray-600 mt-1">
                                        {d.scheduled_time && <>Scheduled: {new Date(d.scheduled_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</>}
                                        {d.administered_at && <> · Given: {new Date(d.administered_at).toLocaleString()}</>}
                                        {d.administered_by_name && <> · By: {d.administered_by_name}</>}
                                      </div>
                                      {d.prn_indication && <div className="text-xs italic text-gray-600 mt-1">Indication: {d.prn_indication}</div>}
                                      {d.reason_if_not_given && <div className="text-xs italic text-orange-700 mt-1">Reason: {d.reason_if_not_given}</div>}
                                      {d.notes && <div className="text-xs text-gray-600 mt-1">Notes: {d.notes}</div>}
                                    </div>
                                    {d.status === 'scheduled' && (
                                      <Button size="sm" onClick={() => openAdministerDialog(d)}>
                                        <Check className="h-4 w-4 mr-1" /> Administer
                                      </Button>
                                    )}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </TabsContent>

                      {/* I/O (Intake/Output) sub-tab */}
                      <TabsContent value="io" className="space-y-3 mt-3">
                        <div className="flex justify-between items-center gap-2 flex-wrap">
                          <div className="flex items-center gap-2">
                            <Label className="text-xs">Date</Label>
                            <Input type="date" value={ioDate} onChange={e => setIoDate(e.target.value)} className="h-8 w-40" />
                          </div>
                          <Button size="sm" onClick={() => { setIoForm({ io_type: 'intake', category: 'oral', amount_ml: '', shift: 'morning', notes: '' }); setShowIoDialog(true); }}>
                            <Plus className="h-4 w-4 mr-1" /> Record I/O
                          </Button>
                        </div>

                        {/* Balance summary */}
                        {ioBalance && (
                          <div className="border rounded p-3 bg-gray-50 space-y-2">
                            <div className="grid grid-cols-3 gap-2 text-sm">
                              <div>
                                <div className="text-xs text-gray-500">Total Intake</div>
                                <div className="text-lg font-semibold text-blue-700">{ioBalance.total_intake_ml.toFixed(0)} ml</div>
                              </div>
                              <div>
                                <div className="text-xs text-gray-500">Total Output</div>
                                <div className="text-lg font-semibold text-orange-700">{ioBalance.total_output_ml.toFixed(0)} ml</div>
                              </div>
                              <div>
                                <div className="text-xs text-gray-500">Net Balance</div>
                                <div className={`text-lg font-semibold ${ioBalance.net_balance_ml > 0 ? 'text-blue-700' : ioBalance.net_balance_ml < 0 ? 'text-orange-700' : ''}`}>
                                  {ioBalance.net_balance_ml > 0 ? '+' : ''}{ioBalance.net_balance_ml.toFixed(0)} ml
                                </div>
                              </div>
                            </div>
                            <div className="border-t pt-2">
                              <table className="w-full text-xs">
                                <thead><tr className="text-left text-gray-500">
                                  <th className="py-1">Shift</th><th className="py-1 text-right">Intake</th><th className="py-1 text-right">Output</th><th className="py-1 text-right">Balance</th>
                                </tr></thead>
                                <tbody>
                                  {['morning', 'afternoon', 'night'].map(s => (
                                    <tr key={s} className="border-t">
                                      <td className="py-1 capitalize">{s}</td>
                                      <td className="py-1 text-right">{ioBalance.by_shift[s].intake.toFixed(0)}</td>
                                      <td className="py-1 text-right">{ioBalance.by_shift[s].output.toFixed(0)}</td>
                                      <td className="py-1 text-right">{(ioBalance.by_shift[s].intake - ioBalance.by_shift[s].output).toFixed(0)}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}

                        {ioEntries.length === 0 ? (
                          <div className="text-center text-sm text-gray-500 py-8">No I/O entries for this date.</div>
                        ) : (
                          <div className="border rounded overflow-hidden">
                            <table className="w-full text-xs">
                              <thead className="bg-gray-50"><tr className="text-left">
                                <th className="px-2 py-2">Time</th><th className="px-2 py-2">Shift</th><th className="px-2 py-2">Type</th>
                                <th className="px-2 py-2">Category</th><th className="px-2 py-2 text-right">Amount (ml)</th>
                                <th className="px-2 py-2">Nurse</th><th className="px-2 py-2"></th>
                              </tr></thead>
                              <tbody>
                                {ioEntries.map(e => (
                                  <tr key={e.id} className="border-t">
                                    <td className="px-2 py-1.5 whitespace-nowrap">{new Date(e.recorded_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td>
                                    <td className="px-2 py-1.5 capitalize">{e.shift}</td>
                                    <td className="px-2 py-1.5">
                                      <Badge className={`text-xs ${e.io_type === 'intake' ? 'bg-blue-100 text-blue-800' : 'bg-orange-100 text-orange-800'}`}>
                                        {e.io_type}
                                      </Badge>
                                    </td>
                                    <td className="px-2 py-1.5 capitalize">{e.category.replace(/_/g, ' ')}</td>
                                    <td className="px-2 py-1.5 text-right font-semibold">{e.amount_ml}</td>
                                    <td className="px-2 py-1.5 text-xs">{e.recorded_by_name || '–'}</td>
                                    <td className="px-2 py-1.5">
                                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => handleDeleteIO(e.id)}>
                                        <Trash2 className="h-3.5 w-3.5 text-red-500" />
                                      </Button>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </TabsContent>

                      {/* Allergies sub-tab */}
                      <TabsContent value="allergies" className="space-y-3 mt-3">
                        <div className="flex justify-between items-center">
                          <p className="text-xs text-gray-500">Patient-level allergies — visible across all admissions and prescriptions.</p>
                          <Button size="sm" onClick={() => { setAllergyForm({ allergy_type: 'drug', allergen: '', severity: 'moderate', reaction: '', notes: '' }); setShowAllergyDialog(true); }}>
                            <Plus className="h-4 w-4 mr-1" /> Record Allergy
                          </Button>
                        </div>
                        {admissionAllergies.length === 0 ? (
                          <div className="text-center text-sm text-gray-500 py-8">No active allergies recorded for this patient.</div>
                        ) : (
                          <div className="space-y-2">
                            {admissionAllergies.map(a => (
                              <div key={a.id} className="p-3 border rounded flex justify-between items-start gap-3">
                                <div className="flex-1">
                                  <div className="flex items-center gap-2 flex-wrap">
                                    <span className="font-medium text-sm">{a.allergen}</span>
                                    <Badge variant="outline" className="text-xs">{a.allergy_type}</Badge>
                                    <Badge className={`text-xs ${
                                      a.severity === 'anaphylaxis' ? 'bg-red-200 text-red-900' :
                                      a.severity === 'severe' ? 'bg-red-100 text-red-800' :
                                      a.severity === 'moderate' ? 'bg-orange-100 text-orange-800' :
                                      'bg-yellow-100 text-yellow-800'
                                    }`}>{a.severity}</Badge>
                                  </div>
                                  {a.reaction && <p className="text-xs text-gray-700 mt-1">Reaction: {a.reaction}</p>}
                                  {a.notes && <p className="text-xs text-gray-500 mt-0.5">{a.notes}</p>}
                                  <p className="text-xs text-gray-400 mt-1">Recorded {a.recorded_at ? new Date(a.recorded_at).toLocaleDateString() : '–'} by {a.recorded_by_name || '–'}</p>
                                </div>
                                <Button variant="ghost" size="sm" className="h-7 w-7 p-0"
                                  onClick={() => setConfirmState({ open: true, title: 'Remove allergy?', description: 'This will mark the allergy inactive.', onConfirm: () => { setConfirmState({ open: false }); handleDeleteAllergy(a.id); } })}>
                                  <Trash2 className="h-4 w-4 text-red-500" />
                                </Button>
                              </div>
                            ))}
                          </div>
                        )}
                      </TabsContent>
                    </Tabs>
                      );
                    })()}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ============ ROOM MANAGEMENT ============ */}
          {activeTab === 'rooms' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Room Management</h2>
            <Button onClick={() => { setEditingRoom(null); resetRoomForm(); setShowRoomDialog(true); }}>
              <Plus className="h-4 w-4 mr-2" /> Add Room
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {rooms.map(room => (
              <Card key={room.id} className={!room.is_active ? 'opacity-50' : ''}>
                <CardContent className="pt-4">
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <h3 className="font-semibold">{room.room_number}</h3>
                      <Badge className="mt-1">{roomTypeLabel[room.room_type] || room.room_type}</Badge>
                    </div>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="sm" onClick={() => openBedManager(room)} title="Manage Beds"><Bed className="h-4 w-4" /></Button>
                      <Button variant="ghost" size="sm" onClick={() => handleEditRoom(room)}><Edit2 className="h-4 w-4" /></Button>
                      {room.is_active && (
                        <Button variant="ghost" size="sm" className="text-red-500" onClick={() => {
                          setConfirmState({ open: true, title: 'Deactivate Room', message: `Deactivate room ${room.room_number}?`,
                            onConfirm: () => { setConfirmState({ open: false }); handleDeleteRoom(room.id); } });
                        }}><Trash2 className="h-4 w-4" /></Button>
                      )}
                    </div>
                  </div>
                  <div className="text-sm text-gray-600 space-y-1">
                    {room.floor && <p>Floor: {room.floor}</p>}
                    {room.department && <p>Dept: {room.department}</p>}
                    <p>Beds: {room.available_beds}/{room.bed_count} available</p>
                    <p>Charge: ₹{room.room_charge_per_day}/day</p>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2 mt-2">
                    <div className={`h-2 rounded-full ${room.available_beds === 0 ? 'bg-red-500' : 'bg-green-500'}`}
                         style={{ width: `${room.bed_count > 0 ? ((room.bed_count - room.available_beds) / room.bed_count * 100) : 0}%` }} />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          </div>
          )}

          {/* ============ TRIAGE QUEUE ============ */}
          {activeTab === 'triage' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-semibold">ER Triage Queue</h2>
                  <p className="text-sm text-gray-500">Active emergency admissions, sorted by triage acuity then arrival time.</p>
                </div>
                <Button size="sm" variant="outline" onClick={fetchTriageQueue}>
                  <RotateCcw className="h-4 w-4 mr-1" /> Refresh
                </Button>
              </div>

              {triageLoading ? (
                <div className="text-center py-12 text-gray-400">Loading…</div>
              ) : triageQueue.length === 0 ? (
                <div className="text-center py-12 text-gray-400 border rounded">
                  No active emergency admissions.
                </div>
              ) : (
                <div className="space-y-2">
                  {triageQueue.map(p => {
                    const tColor = {
                      1: 'bg-red-600 text-white',
                      2: 'bg-orange-500 text-white',
                      3: 'bg-amber-400 text-black',
                      4: 'bg-green-400 text-black',
                      5: 'bg-blue-300 text-black',
                    }[p.triage_level] || 'bg-gray-200 text-gray-700';
                    const elapsed = p.elapsed_minutes;
                    const elapsedStr = elapsed != null
                      ? (elapsed < 60 ? `${elapsed}m` : `${Math.floor(elapsed / 60)}h ${elapsed % 60}m`)
                      : '—';
                    const slowThresh = {1: 5, 2: 15, 3: 30, 4: 60, 5: 120}[p.triage_level] || 60;
                    const slow = elapsed != null && p.triage_level && elapsed > slowThresh;
                    return (
                      <Card key={p.id} className={`${slow ? 'border-red-400' : ''} hover:shadow cursor-pointer`}
                        onClick={() => { setActiveTab('admissions'); setActivityAdmission(p); }}>
                        <CardContent className="p-3">
                          <div className="flex items-center gap-3">
                            <div className={`w-12 h-12 rounded ${tColor} flex flex-col items-center justify-center font-bold`}>
                              <span className="text-lg leading-none">T{p.triage_level || '?'}</span>
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="font-medium">{p.patient_name || '—'}</span>
                                <span className="text-xs text-gray-500">{p.admission_number}</span>
                                {p.is_mlc && <Badge className="bg-yellow-200 text-yellow-900 text-[10px]">MLC{p.mlc_type ? ' · ' + p.mlc_type : ''}</Badge>}
                                {p.is_observation && <Badge className="bg-blue-100 text-blue-800 text-[10px]">Obs</Badge>}
                                {p.deposit_waived && <Badge className="bg-amber-100 text-amber-800 text-[10px]">Waiver</Badge>}
                                {p.registration_complete === false && <Badge className="bg-orange-100 text-orange-800 text-[10px]">KYC Pending</Badge>}
                              </div>
                              <p className="text-xs text-gray-600 truncate">{p.chief_complaint || p.admission_reason || 'No complaint recorded'}</p>
                              <p className="text-[11px] text-gray-400">
                                Arrival: {p.arrival_mode ? p.arrival_mode.replace('_', ' ') : '—'}
                                {' · '}{p.room_number || 'no room'} {(p.bed_label || p.bed_number) ? `/ ${p.bed_label || p.bed_number}` : ''}
                                {' · '}Dr. {p.doctor_name || '—'}
                              </p>
                            </div>
                            <div className="text-right">
                              <div className={`text-sm font-semibold ${slow ? 'text-red-600' : 'text-gray-700'}`}>{elapsedStr}</div>
                              <div className="text-[10px] text-gray-400">in dept</div>
                              {p.is_mlc && (
                                <Button size="sm" variant="outline" className="mt-1 h-6 text-[10px] px-2"
                                  onClick={(e) => { e.stopPropagation(); printPdfFromUrl(`/api/inpatient/admissions/${p.id}/mlc/pdf`, `MLC_${p.admission_number}.pdf`); }}>
                                  <Printer className="h-3 w-3 mr-1" /> MLC
                                </Button>
                              )}
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ============ DISCHARGE HISTORY ============ */}
          {activeTab === 'discharge' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
          <div className="relative max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <Input placeholder="Search discharged patients..." value={dischargeSearch} onChange={e => setDischargeSearch(e.target.value)} className="pl-10" />
          </div>

          {filteredDischarged.length === 0 ? (
            <Card><CardContent className="py-12 text-center text-gray-500">No discharged patients found.</CardContent></Card>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 text-sm">Patient</th>
                    <th className="text-left py-2 text-sm">Admission #</th>
                    <th className="text-left py-2 text-sm">Admitted</th>
                    <th className="text-left py-2 text-sm">Doctor</th>
                    <th className="text-left py-2 text-sm">Status</th>
                    <th className="text-left py-2 text-sm">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDischarged.map(adm => (
                    <tr key={adm.id} className="border-b hover:bg-gray-50">
                      <td className="py-2 text-sm font-medium">{adm.patient_name || 'N/A'}</td>
                      <td className="py-2 text-sm">{adm.admission_number}</td>
                      <td className="py-2 text-sm">{adm.admission_date ? new Date(adm.admission_date).toLocaleDateString() : ''}</td>
                      <td className="py-2 text-sm">{adm.doctor_name || 'N/A'}</td>
                      <td className="py-2"><Badge className={admissionStatusColor[adm.status] || ''}>{adm.status}</Badge></td>
                      <td className="py-2">
                        <div className="flex gap-1">
                          <Button variant="ghost" size="sm" onClick={() => handlePrintDischargePdf(adm.id)} title="Discharge Summary PDF">
                            <FileText className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => handlePrintBillPdf(adm.id)} title="Bill PDF">
                            <DollarSign className="h-4 w-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {dischargeTotal > PAGE_SIZE && (
                <div className="flex items-center justify-between pt-4 border-t mt-2">
                  <span className="text-sm text-gray-500">
                    Showing {dischargePage * PAGE_SIZE + 1}–{Math.min((dischargePage + 1) * PAGE_SIZE, dischargeTotal)} of {dischargeTotal}
                  </span>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" disabled={dischargePage === 0}
                      onClick={() => setDischargePage(p => p - 1)}>
                      <ChevronLeft className="h-4 w-4 mr-1" /> Prev
                    </Button>
                    <Button variant="outline" size="sm" disabled={(dischargePage + 1) * PAGE_SIZE >= dischargeTotal}
                      onClick={() => setDischargePage(p => p + 1)}>
                      Next <ChevronRight className="h-4 w-4 ml-1" />
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
          </div>
          )}

          {/* ============ OT SCHEDULE ============ */}
          {activeTab === 'ot' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">OT Schedule</h2>
            <Button onClick={() => setShowOTDialog(true)}>
              <Plus className="h-4 w-4 mr-2" /> Schedule OT
            </Button>
          </div>

          {otSchedules.length === 0 ? (
            <Card><CardContent className="py-12 text-center text-gray-500">No OT schedules found.</CardContent></Card>
          ) : (
            <div className="space-y-3">
              {otSchedules.map(ot => (
                <Card key={ot.id}>
                  <CardContent className="py-4">
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-semibold text-sm">{ot.procedure_name}</h3>
                          <Badge className={otStatusColor[ot.status] || ''}>{ot.status.replace('_', ' ')}</Badge>
                        </div>
                        <p className="text-sm text-gray-600">
                          <User className="h-3 w-3 inline mr-1" /> {ot.patient_name || 'N/A'} &bull;
                          <Stethoscope className="h-3 w-3 inline mx-1" /> Dr. {ot.surgeon_name || 'N/A'} &bull;
                          <Clock className="h-3 w-3 inline mx-1" /> {ot.scheduled_date ? new Date(ot.scheduled_date).toLocaleString() : ''} &bull;
                          OT Room: {ot.ot_room_number}
                          {ot.estimated_duration_minutes && <span> &bull; ~{ot.estimated_duration_minutes} min</span>}
                        </p>
                      </div>
                      <div className="flex gap-1">
                        {ot.status === 'scheduled' && (
                          <>
                            <Button size="sm" variant="outline" onClick={() => handleUpdateOTStatus(ot.id, 'in_progress')}>Start</Button>
                            <Button size="sm" variant="ghost" className="text-red-500" onClick={() => handleUpdateOTStatus(ot.id, 'cancelled')}>Cancel</Button>
                          </>
                        )}
                        {ot.status === 'in_progress' && (
                          <Button size="sm" variant="outline" onClick={() => handleUpdateOTStatus(ot.id, 'completed')}>Complete</Button>
                        )}
                        {(ot.status === 'completed' || ot.status === 'in_progress') && (
                          <Button size="sm" variant="outline" onClick={() => openOTChargesDialog(ot)} disabled={ot.billed}>
                            <DollarSign className="h-3.5 w-3.5 mr-1" /> {ot.billed ? 'Billed' : `Charges${ot.total_charges ? ` ₹${ot.total_charges.toFixed(2)}` : ''}`}
                          </Button>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
          </div>
          )}

          {/* ============ PROCEDURES CATALOG ============ */}
          {activeTab === 'procedures' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold">Procedure Catalog</h2>
                  <p className="text-sm text-gray-500">Default rates auto-fill into OT schedules. Editable per-procedure during scheduling.</p>
                </div>
                <Button onClick={() => { resetProcedureForm(); setShowProcedureDialog(true); }}>
                  <Plus className="h-4 w-4 mr-2" /> Add Procedure
                </Button>
              </div>

              {proceduresList.length === 0 ? (
                <Card><CardContent className="py-12 text-center text-gray-500">No procedures in catalog yet.</CardContent></Card>
              ) : (
                <Card>
                  <CardContent className="p-0">
                    <div className="overflow-x-auto">
                      <table className="min-w-full text-sm">
                        <thead className="bg-gray-50 text-xs uppercase text-gray-600">
                          <tr>
                            <th className="px-4 py-2 text-left">Name</th>
                            <th className="px-4 py-2 text-right">Default Rate</th>
                            <th className="px-4 py-2 text-left">Description</th>
                            <th className="px-4 py-2 text-center">Status</th>
                            <th className="px-4 py-2 text-right">Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {proceduresList.map(p => (
                            <tr key={p.id} className="border-t">
                              <td className="px-4 py-2 font-medium">{p.name}</td>
                              <td className="px-4 py-2 text-right">₹{Number(p.default_rate || 0).toFixed(2)}</td>
                              <td className="px-4 py-2 text-gray-600">{p.description || '—'}</td>
                              <td className="px-4 py-2 text-center">
                                {p.is_active
                                  ? <Badge className="bg-green-100 text-green-800">Active</Badge>
                                  : <Badge className="bg-gray-200 text-gray-700">Inactive</Badge>}
                              </td>
                              <td className="px-4 py-2 text-right space-x-1">
                                <Button size="sm" variant="ghost" onClick={() => startEditProcedure(p)}>Edit</Button>
                                {p.is_active && (
                                  <Button size="sm" variant="ghost" className="text-red-500" onClick={() => handleProcedureDelete(p.id)}>Remove</Button>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {/* ============ PRE-AUTHORISATIONS ============ */}
          {activeTab === 'preauth' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Insurance Pre-Authorisations</h2>
                <Button onClick={() => { setPreauthForm({ patient_id: '', admission_id: '', insurance_provider: '', policy_number: '', tpa_id: '', requested_amount: '', notes: '' }); setPreauthSelectedPatient(null); setShowPreauthDialog(true); }}>
                  <Plus className="h-4 w-4 mr-2" /> New Request
                </Button>
              </div>
              <div className="flex gap-3">
                <Input className="max-w-xs" placeholder="Search by patient, provider, TPA..." value={preauthSearch} onChange={e => setPreauthSearch(e.target.value)} />
                <Select value={preauthStatusFilter || 'all'} onValueChange={v => setPreauthStatusFilter(v === 'all' ? '' : v)}>
                  <SelectTrigger className="max-w-[200px]"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All statuses</SelectItem>
                    <SelectItem value="requested">Requested</SelectItem>
                    <SelectItem value="approved">Approved</SelectItem>
                    <SelectItem value="rejected">Rejected</SelectItem>
                    <SelectItem value="expansion_requested">Expansion Requested</SelectItem>
                    <SelectItem value="expanded">Expanded</SelectItem>
                    <SelectItem value="expired">Expired</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {preauths.length === 0 ? (
                <Card><CardContent className="py-12 text-center text-gray-500">No pre-authorisation requests.</CardContent></Card>
              ) : (
                <div className="space-y-2">
                  {preauths.map(p => {
                    const statusColor = {
                      requested: 'bg-blue-100 text-blue-800',
                      approved: 'bg-green-100 text-green-800',
                      rejected: 'bg-red-100 text-red-800',
                      expansion_requested: 'bg-yellow-100 text-yellow-800',
                      expanded: 'bg-purple-100 text-purple-800',
                      expired: 'bg-gray-100 text-gray-800',
                    }[p.status] || 'bg-gray-100 text-gray-800';
                    return (
                      <Card key={p.id}>
                        <CardContent className="py-3">
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="font-semibold text-sm">{p.patient_name || '—'}</span>
                                <Badge className={`text-xs ${statusColor}`}>{p.status}</Badge>
                                <span className="text-xs text-gray-500">{p.insurance_provider}</span>
                                {p.tpa_name && <span className="text-xs text-gray-500">· TPA: {p.tpa_name}</span>}
                              </div>
                              <div className="text-xs text-gray-600 mt-1">
                                Requested ₹{p.requested_amount.toFixed(2)}
                                {p.approved_amount > 0 && <> · Approved ₹{p.approved_amount.toFixed(2)}</>}
                                {p.policy_number && <> · Policy {p.policy_number}</>}
                                · {new Date(p.request_date).toLocaleDateString()}
                              </div>
                              {p.admission_number && <div className="text-xs text-gray-500">Admission {p.admission_number}</div>}
                              {p.notes && <p className="text-xs italic text-gray-600 mt-1">{p.notes}</p>}
                            </div>
                            <div className="flex gap-1">
                              {(p.status === 'requested' || p.status === 'expansion_requested') && (
                                <Button size="sm" variant="outline" onClick={() => {
                                  setActivePreauth(p);
                                  setPreauthDecisionForm({ status: 'approved', approved_amount: String(p.requested_amount), validity_days: '', approval_reference: '', notes: '' });
                                  setShowPreauthDecisionDialog(true);
                                }}>Record Decision</Button>
                              )}
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ============ DUTY ROSTER ============ */}
          {activeTab === 'roster' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <h2 className="text-lg font-semibold flex items-center gap-2"><CalendarRange className="h-5 w-5" /> Nurse Duty Roster</h2>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => shiftWeek(-7)}>
                    <ChevronLeft className="h-4 w-4" /> Prev Week
                  </Button>
                  <span className="text-sm font-medium px-2">
                    {rosterWeekStart.toLocaleDateString()} – {(() => {
                      const e = new Date(rosterWeekStart); e.setDate(e.getDate() + 6); return e.toLocaleDateString();
                    })()}
                  </span>
                  <Button size="sm" variant="outline" onClick={() => shiftWeek(7)}>
                    Next Week <ChevronRight className="h-4 w-4" />
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => {
                    const today = new Date(); const dow = today.getDay();
                    const offset = dow === 0 ? -6 : 1 - dow;
                    today.setDate(today.getDate() + offset); today.setHours(0, 0, 0, 0);
                    setRosterWeekStart(today);
                  }}>This Week</Button>
                  <div className="flex items-center gap-1 ml-3">
                    <Label className="text-xs">Min/shift</Label>
                    <Input type="number" min="1" max="50" value={rosterMinPerShift} onChange={e => setRosterMinPerShift(parseInt(e.target.value) || 1)} className="h-8 w-16" />
                  </div>
                  <Button size="sm" onClick={() => {
                    const start = new Date(rosterWeekStart);
                    const end = new Date(rosterWeekStart); end.setDate(end.getDate() + 6);
                    setBulkRosterForm({
                      nurse_ids: [], from_date: _toIso(start), to_date: _toIso(end),
                      shifts: ['morning'], status: 'working', ward: '', notes: '', overwrite: false,
                    });
                    setShowBulkRosterDialog(true);
                  }}>
                    <Plus className="h-4 w-4 mr-1" /> Bulk Assign
                  </Button>
                </div>
              </div>

              <p className="text-xs text-gray-500">
                Click any cell to assign or edit. Status legend: <Badge className="bg-green-100 text-green-800 text-xs ml-1">working</Badge> <Badge className="bg-blue-100 text-blue-800 text-xs ml-1">on_call</Badge> <Badge className="bg-orange-100 text-orange-800 text-xs ml-1">leave</Badge> <Badge className="bg-gray-100 text-gray-700 text-xs ml-1">off</Badge>
              </p>

              {/* Roster grid */}
              {!rosterGrid ? (
                <Card><CardContent className="py-12 text-center text-gray-500">Loading roster…</CardContent></Card>
              ) : rosterGrid.nurses.length === 0 ? (
                <Card><CardContent className="py-12 text-center text-gray-500">No nurses on staff. Create users with the 'nurse' role first.</CardContent></Card>
              ) : (
                <div className="border rounded overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="px-2 py-2 text-left sticky left-0 bg-gray-50 border-r">Nurse</th>
                        {rosterGrid.dates.map(d => {
                          const dt = new Date(d);
                          return (
                            <th key={d} className="px-1 py-2 text-center border-r" colSpan={3}>
                              <div className="font-semibold">{dt.toLocaleDateString(undefined, { weekday: 'short' })}</div>
                              <div className="text-gray-500">{dt.toLocaleDateString(undefined, { day: '2-digit', month: 'short' })}</div>
                            </th>
                          );
                        })}
                      </tr>
                      <tr className="bg-gray-100">
                        <th className="px-2 py-1 text-left sticky left-0 bg-gray-100 border-r"></th>
                        {rosterGrid.dates.map(d => (
                          <React.Fragment key={d}>
                            <th className="px-1 py-1 text-center text-[10px]">M</th>
                            <th className="px-1 py-1 text-center text-[10px]">A</th>
                            <th className="px-1 py-1 text-center text-[10px] border-r">N</th>
                          </React.Fragment>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rosterGrid.nurses.map(nurse => (
                        <tr key={nurse.id} className="border-t">
                          <td className="px-2 py-1 sticky left-0 bg-white border-r font-medium">{nurse.name}</td>
                          {rosterGrid.dates.map(d => (
                            <React.Fragment key={d}>
                              {['morning', 'afternoon', 'night'].map(shift => {
                                const cell = rosterGrid.cells[nurse.id]?.[d]?.[shift];
                                const cellClass = cell ? {
                                  working: 'bg-green-100 hover:bg-green-200',
                                  on_call: 'bg-blue-100 hover:bg-blue-200',
                                  leave: 'bg-orange-100 hover:bg-orange-200',
                                  off: 'bg-gray-200 hover:bg-gray-300',
                                }[cell.status] : 'hover:bg-blue-50';
                                const label = cell ? {
                                  working: 'W', on_call: 'O', leave: 'L', off: '-',
                                }[cell.status] : '+';
                                const titleParts = cell ? [cell.status] : ['Click to assign'];
                                if (cell?.ward) titleParts.push(`Ward: ${cell.ward}`);
                                if (cell?.notes) titleParts.push(`Notes: ${cell.notes}`);
                                const isLastShift = shift === 'night';
                                return (
                                  <td
                                    key={shift}
                                    title={titleParts.join(' · ')}
                                    className={`px-1 py-1 text-center text-[11px] cursor-pointer ${cellClass} ${isLastShift ? 'border-r' : ''}`}
                                    onClick={() => openRosterCell(nurse, d, shift, cell)}
                                  >
                                    {label}
                                  </td>
                                );
                              })}
                            </React.Fragment>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                    {/* Coverage row */}
                    {rosterCoverage.length > 0 && (
                      <tfoot className="bg-yellow-50 border-t-2 border-yellow-300">
                        <tr>
                          <td className="px-2 py-1 sticky left-0 bg-yellow-50 border-r font-semibold text-[10px]">Working / shift</td>
                          {rosterGrid.dates.map(d => (
                            <React.Fragment key={d}>
                              {['morning', 'afternoon', 'night'].map(shift => {
                                const cov = rosterCoverage.find(c => c.date === d && c.shift === shift);
                                const isLastShift = shift === 'night';
                                return (
                                  <td
                                    key={shift}
                                    className={`px-1 py-1 text-center text-[10px] font-semibold ${isLastShift ? 'border-r' : ''} ${cov?.is_understaffed ? 'text-red-700 bg-red-50' : 'text-gray-700'}`}
                                    title={cov?.is_understaffed ? `Below minimum ${cov.min_required}` : ''}
                                  >
                                    {cov?.working ?? 0}
                                  </td>
                                );
                              })}
                            </React.Fragment>
                          ))}
                        </tr>
                      </tfoot>
                    )}
                  </table>
                </div>
              )}
            </div>
          )}

          {/* ============ HOUSEKEEPING ============ */}
          {activeTab === 'housekeeping' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
              <h2 className="text-lg font-semibold">Housekeeping & Bed Turnover</h2>

              {/* Pending ward transfers (receiving ward actions) */}
              {pendingTransfers.length > 0 && (
                <div className="border-l-4 border-yellow-500 bg-yellow-50 p-3 rounded">
                  <h3 className="text-sm font-semibold mb-2">Pending ward transfers ({pendingTransfers.length})</h3>
                  <div className="space-y-1">
                    {pendingTransfers.map(t => (
                      <div key={t.id} className="flex justify-between items-center text-sm bg-white p-2 rounded border">
                        <div>
                          Admission #{t.admission_id} — {t.from_room_number || '—'} → {t.to_room_number}
                          <span className="text-xs text-gray-500 ml-2">{t.reason}</span>
                        </div>
                        <div className="flex gap-1">
                          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => handleAcceptTransfer(t.id)}>Accept</Button>
                          <Button size="sm" variant="ghost" className="h-7 text-xs text-red-600" onClick={() => handleCancelPendingTransfer(t.id)}>Cancel</Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Turnover stats */}
              {turnoverStats && (
                <div className="grid grid-cols-4 gap-3">
                  <Card><CardContent className="py-4">
                    <div className="text-xs text-gray-500">Awaiting cleaning</div>
                    <div className="text-2xl font-semibold">{turnoverStats.beds_currently_dirty + turnoverStats.beds_currently_cleaning}</div>
                  </CardContent></Card>
                  <Card><CardContent className="py-4">
                    <div className="text-xs text-gray-500">Avg turnover time</div>
                    <div className="text-2xl font-semibold">{turnoverStats.avg_minutes} <span className="text-sm font-normal">min</span></div>
                  </CardContent></Card>
                  <Card><CardContent className="py-4">
                    <div className="text-xs text-gray-500">Turnovers logged</div>
                    <div className="text-2xl font-semibold">{turnoverStats.turnover_count}</div>
                  </CardContent></Card>
                  <Card><CardContent className="py-4">
                    <div className="text-xs text-gray-500">Pending transfers</div>
                    <div className="text-2xl font-semibold">{pendingTransfers.length}</div>
                  </CardContent></Card>
                </div>
              )}

              {/* Beds needing cleaning */}
              <Card>
                <CardHeader className="py-3"><CardTitle className="text-sm flex items-center gap-1.5"><Sparkles className="h-4 w-4" /> Beds needing attention</CardTitle></CardHeader>
                <CardContent>
                  {cleaningBeds.length === 0 ? (
                    <p className="text-sm text-gray-500 text-center py-6">All beds are ready.</p>
                  ) : (
                    <div className="space-y-2">
                      {cleaningBeds.map(b => (
                        <div key={b.bed_id} className="flex items-center justify-between border rounded p-2 text-sm">
                          <div>
                            <span className="font-medium">Room {b.room_number} — Bed {b.bed_label}</span>
                            <Badge className={`ml-2 text-xs ${b.status === 'dirty' ? 'bg-red-100 text-red-800' : 'bg-yellow-100 text-yellow-800'}`}>{b.status}</Badge>
                            {b.since && <span className="text-xs text-gray-500 ml-2">since {new Date(b.since).toLocaleString()}</span>}
                          </div>
                          <div className="flex gap-1">
                            {b.status === 'dirty' && (
                              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => handleMarkBedMaintenance(b.bed_id, 'cleaning')}>Start Cleaning</Button>
                            )}
                            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => handleMarkBedAvailable(b.bed_id)}>Mark Ready</Button>
                            <Button size="sm" variant="ghost" className="h-7 text-xs text-red-600" onClick={() => handleMarkBedMaintenance(b.bed_id, 'out_of_service')}>Out of Service</Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          )}

          {/* ============ RESERVATIONS ============ */}
          {activeTab === 'reservations' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Bed Reservations</h2>
                <Button onClick={() => { setReservationForm({ patient_id: '', bed_id: '', room_id: '', room_type: '', reserved_for_date: new Date().toISOString().slice(0, 16), reservation_reason: 'elective', notes: '' }); setReservationSelectedPatient(null); setShowReservationDialog(true); }}>
                  <Plus className="h-4 w-4 mr-2" /> New Reservation
                </Button>
              </div>

              {reservations.length === 0 ? (
                <Card><CardContent className="py-12 text-center text-gray-500">No active reservations.</CardContent></Card>
              ) : (
                <div className="space-y-2">
                  {reservations.map(r => (
                    <Card key={r.id}>
                      <CardContent className="py-3">
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-semibold text-sm">{r.patient_name || '—'}</span>
                              <Badge variant="outline" className="text-xs">{r.reservation_reason}</Badge>
                              <Badge className="text-xs bg-blue-100 text-blue-800">{r.status}</Badge>
                            </div>
                            <div className="text-xs text-gray-600 mt-1">
                              Reserved for {new Date(r.reserved_for_date).toLocaleString()}
                              {r.bed_label && <> · Bed {r.bed_label}</>}
                              {r.room_number && <> · Room {r.room_number}</>}
                              {r.room_type && !r.room_number && <> · Any {r.room_type} room</>}
                            </div>
                            {r.notes && <p className="text-xs italic text-gray-500 mt-1">{r.notes}</p>}
                            <p className="text-xs text-gray-400 mt-1">Created by {r.reserved_by_name || '—'}</p>
                          </div>
                          <div className="flex gap-1">
                            {r.patient_id && ip('admit_patients') && (
                              <Button size="sm" variant="outline" onClick={() => { setConvertingReservation(r); setConvertForm({ admitting_doctor_id: '', admission_type: 'elective', admission_reason: '', condition_on_admission: 'stable' }); setShowConvertReservationDialog(true); }}>Convert to Admission</Button>
                            )}
                            {ip('manage_reservations') && (
                              <Button size="sm" variant="ghost" onClick={() => setConfirmState({ open: true, title: 'Cancel reservation?', description: 'This cannot be undone.', onConfirm: () => { setConfirmState({ open: false }); handleCancelReservation(r.id); } })}>
                                <X className="h-4 w-4 text-red-500" />
                              </Button>
                            )}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ============ INCIDENTS ============ */}
          {activeTab === 'incidents' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold">Incident Reporting</h2>
                <Button onClick={() => { setIncidentForm({ incident_type: 'fall', severity: 'medium', incident_date: new Date().toISOString().slice(0, 16), admission_id: '', patient_id: '', location: '', description: '', immediate_action: '', witnessed_by: '' }); setShowIncidentDialog(true); }}>
                  <Plus className="h-4 w-4 mr-2" /> Report Incident
                </Button>
              </div>

              {/* Monthly stats */}
              {incidentReport && (
                <div className="grid grid-cols-4 gap-3">
                  <Card><CardContent className="py-4">
                    <div className="text-xs text-gray-500">Last 30 days</div>
                    <div className="text-2xl font-semibold">{incidentReport.total}</div>
                  </CardContent></Card>
                  {['low', 'medium', 'high', 'critical'].map(sev => (
                    <Card key={sev}><CardContent className="py-4">
                      <div className="text-xs text-gray-500 capitalize">{sev}</div>
                      <div className={`text-2xl font-semibold ${sev === 'critical' ? 'text-red-700' : sev === 'high' ? 'text-orange-700' : ''}`}>
                        {incidentReport.by_severity?.[sev] || 0}
                      </div>
                    </CardContent></Card>
                  ))}
                </div>
              )}

              {/* Filters */}
              <div className="flex gap-2 flex-wrap">
                <Select value={incidentFilter.status || 'all'} onValueChange={v => setIncidentFilter(p => ({ ...p, status: v === 'all' ? '' : v }))}>
                  <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All statuses</SelectItem>
                    <SelectItem value="reported">Reported</SelectItem>
                    <SelectItem value="investigating">Investigating</SelectItem>
                    <SelectItem value="resolved">Resolved</SelectItem>
                    <SelectItem value="closed">Closed</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={incidentFilter.severity || 'all'} onValueChange={v => setIncidentFilter(p => ({ ...p, severity: v === 'all' ? '' : v }))}>
                  <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All severities</SelectItem>
                    <SelectItem value="low">Low</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                    <SelectItem value="critical">Critical</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={incidentFilter.incident_type || 'all'} onValueChange={v => setIncidentFilter(p => ({ ...p, incident_type: v === 'all' ? '' : v }))}>
                  <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All types</SelectItem>
                    <SelectItem value="fall">Fall</SelectItem>
                    <SelectItem value="medication_error">Medication Error</SelectItem>
                    <SelectItem value="pressure_ulcer">Pressure Ulcer</SelectItem>
                    <SelectItem value="needle_stick">Needle Stick</SelectItem>
                    <SelectItem value="infection">Infection</SelectItem>
                    <SelectItem value="equipment_failure">Equipment Failure</SelectItem>
                    <SelectItem value="documentation_error">Documentation Error</SelectItem>
                    <SelectItem value="wrong_patient">Wrong Patient</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {incidents.length === 0 ? (
                <Card><CardContent className="py-12 text-center text-gray-500">No incidents match the filter.</CardContent></Card>
              ) : (
                <div className="space-y-2">
                  {incidents.map(i => {
                    const statusColor = { reported: 'bg-blue-100 text-blue-800', investigating: 'bg-yellow-100 text-yellow-800', resolved: 'bg-green-100 text-green-800', closed: 'bg-gray-100 text-gray-700' }[i.status] || 'bg-gray-100';
                    const sevColor = { low: 'bg-gray-100', medium: 'bg-yellow-100 text-yellow-800', high: 'bg-orange-100 text-orange-800', critical: 'bg-red-100 text-red-800' }[i.severity] || 'bg-gray-100';
                    return (
                      <Card key={i.id}>
                        <CardContent className="py-3">
                          <div className="flex justify-between items-start gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="font-semibold text-sm">{i.incident_type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                                <Badge className={`text-xs ${sevColor}`}>{i.severity}</Badge>
                                <Badge className={`text-xs ${statusColor}`}>{i.status}</Badge>
                                <span className="text-xs text-gray-500">{new Date(i.incident_date).toLocaleString()}</span>
                              </div>
                              {i.location && <p className="text-xs text-gray-500 mt-0.5">Location: {i.location}</p>}
                              {i.patient_name && <p className="text-xs text-gray-500">Patient: {i.patient_name} ({i.admission_number || '—'})</p>}
                              <p className="text-sm text-gray-700 mt-1">{i.description}</p>
                              {i.root_cause && <p className="text-xs text-gray-600 mt-1"><b>Root cause:</b> {i.root_cause}</p>}
                              {i.corrective_actions && <p className="text-xs text-gray-600"><b>Corrective actions:</b> {i.corrective_actions}</p>}
                              <p className="text-xs text-gray-400 mt-1">Reported by {i.reported_by_name}</p>
                            </div>
                            {i.status !== 'closed' && (
                              <Button size="sm" variant="outline" onClick={() => {
                                setInvestigatingIncident(i);
                                setInvestigateForm({ investigation_notes: i.investigation_notes || '', root_cause: i.root_cause || '', resolution: i.resolution || '', corrective_actions: i.corrective_actions || '', preventive_measures: i.preventive_measures || '', new_status: '' });
                                setShowInvestigateDialog(true);
                              }}>Investigate</Button>
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* ============ QUALITY REPORTS (Readmissions + Mortality) ============ */}
          {activeTab === 'quality' && (
            <div className="p-6 overflow-y-auto h-full space-y-6">
              <h2 className="text-lg font-semibold">Quality Reports</h2>

              {/* Readmissions */}
              <div>
                <h3 className="text-md font-semibold mb-2 flex items-center gap-1.5"><RotateCcw className="h-4 w-4" /> 30-Day Readmissions ({readmissions.length})</h3>
                {readmissions.length === 0 ? (
                  <Card><CardContent className="py-6 text-center text-sm text-gray-500">No readmissions in the last 30 days.</CardContent></Card>
                ) : (
                  <div className="border rounded overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-gray-50"><tr>
                        <th className="px-3 py-2 text-left">Admission</th>
                        <th className="px-3 py-2 text-left">Patient</th>
                        <th className="px-3 py-2 text-left">Admitted</th>
                        <th className="px-3 py-2 text-right">Days since prev discharge</th>
                        <th className="px-3 py-2 text-left">Reason</th>
                        <th className="px-3 py-2 text-left">Status</th>
                      </tr></thead>
                      <tbody>
                        {readmissions.map(r => (
                          <tr key={r.admission_id} className="border-t">
                            <td className="px-3 py-2 font-mono text-xs">{r.admission_number}</td>
                            <td className="px-3 py-2">{r.patient_name}</td>
                            <td className="px-3 py-2 text-xs">{r.admission_date && new Date(r.admission_date).toLocaleDateString()}</td>
                            <td className="px-3 py-2 text-right font-semibold">{r.days_since_last_discharge}</td>
                            <td className="px-3 py-2 text-xs">{r.admission_reason || '—'}</td>
                            <td className="px-3 py-2"><Badge variant="outline" className="text-xs">{r.status}</Badge></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Mortality */}
              <div>
                <h3 className="text-md font-semibold mb-2 flex items-center gap-1.5"><Skull className="h-4 w-4" /> Mortality Records ({mortalityList.length})</h3>
                {mortalityList.length === 0 ? (
                  <Card><CardContent className="py-6 text-center text-sm text-gray-500">No mortality records.</CardContent></Card>
                ) : (
                  <div className="space-y-2">
                    {mortalityList.map(m => (
                      <Card key={m.discharge_id}>
                        <CardContent className="py-3">
                          <div className="flex justify-between items-start gap-3">
                            <div className="flex-1 min-w-0">
                              <div className="font-semibold text-sm">{m.patient_name}</div>
                              <div className="text-xs text-gray-600 mt-0.5">
                                Admission {m.admission_number} · Discharged {m.discharge_date && new Date(m.discharge_date).toLocaleDateString()}
                                {m.time_of_death && <> · Time of death {new Date(m.time_of_death).toLocaleString()}</>}
                              </div>
                              {m.cause_of_death ? (
                                <p className="text-xs text-gray-700 mt-1"><b>Cause:</b> {m.cause_of_death}</p>
                              ) : (
                                <p className="text-xs text-orange-600 mt-1">⚠ Cause of death not recorded</p>
                              )}
                              <div className="flex gap-2 mt-1 flex-wrap">
                                {m.mlc_required && <Badge className="text-xs bg-red-100 text-red-800">MLC</Badge>}
                                {m.autopsy_done && <Badge variant="outline" className="text-xs">Autopsy done</Badge>}
                                {m.death_certificate_number && <Badge variant="outline" className="text-xs">Cert #{m.death_certificate_number}</Badge>}
                              </div>
                            </div>
                            <div className="flex gap-1 flex-wrap justify-end">
                              <Button size="sm" variant="outline" onClick={() => openMortalityDialog({ id: m.admission_id, discharge: m })}>Edit Details</Button>
                              <Button size="sm" variant="outline" onClick={() => openBodyRelease(m.admission_id)}>
                                Body Release
                              </Button>
                              <Button size="sm" variant="ghost" onClick={() => handlePrintDeathCertificate(m.admission_id)}>
                                <FileText className="h-4 w-4 mr-1" /> Certificate
                              </Button>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ============ MANAGEMENT REPORTS ============ */}
          {activeTab === 'reports' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
              <h2 className="text-lg font-semibold">Management Reports</h2>
              <Tabs value={reportSubTab} onValueChange={(v) => {
                setReportSubTab(v);
                if (v === 'outcomes') fetchMonthlyOutcomes(outcomesMonth);
                if (v === 'productivity') fetchDoctorProductivity(productivityRange);
              }}>
                <TabsList>
                  <TabsTrigger value="outcomes">Monthly Outcomes</TabsTrigger>
                  <TabsTrigger value="productivity">Doctor Productivity</TabsTrigger>
                </TabsList>

                {/* ----- E2: Monthly outcomes ----- */}
                <TabsContent value="outcomes" className="space-y-4 mt-4">
                  <div className="flex items-end gap-3 flex-wrap">
                    <div>
                      <Label className="text-xs">Month</Label>
                      <Input type="month" value={outcomesMonth}
                        onChange={e => setOutcomesMonth(e.target.value)} />
                    </div>
                    <Button size="sm" onClick={() => fetchMonthlyOutcomes(outcomesMonth)}>
                      Refresh
                    </Button>
                    <Button size="sm" variant="outline"
                      onClick={() => printPdfFromUrl('/api/inpatient/reports/monthly-outcomes/pdf',
                        { month: outcomesMonth, include_header: true })}>
                      <Printer className="h-4 w-4 mr-1" /> Print PDF
                    </Button>
                    {outcomesData && (
                      <span className="text-xs text-gray-500 ml-auto">Window: {outcomesData.month}</span>
                    )}
                  </div>

                  {!outcomesData ? (
                    <p className="text-sm text-gray-500">Loading…</p>
                  ) : (
                    <>
                      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
                        {[
                          ['Admissions', outcomesData.totals.admissions],
                          ['Discharges', outcomesData.totals.discharges],
                          ['Deaths', outcomesData.totals.deaths],
                          ['Mortality %', `${outcomesData.totals.mortality_rate_pct}%`],
                          ['Readmissions', outcomesData.totals.readmissions],
                          ['Readmit %', `${outcomesData.totals.readmission_rate_pct}%`],
                          ['Avg occupancy', `${outcomesData.totals.average_occupancy_pct}%`],
                        ].map(([label, val]) => (
                          <Card key={label}>
                            <CardContent className="pt-4">
                              <p className="text-xs text-gray-500">{label}</p>
                              <p className="text-xl font-bold">{val}</p>
                            </CardContent>
                          </Card>
                        ))}
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <Card>
                          <CardContent className="pt-4">
                            <p className="font-semibold mb-2">Mortality — by department</p>
                            {Object.keys(outcomesData.mortality.by_department).length === 0 ? (
                              <p className="text-xs text-gray-400">No deaths in this window.</p>
                            ) : (
                              <table className="w-full text-sm">
                                <tbody>
                                  {Object.entries(outcomesData.mortality.by_department).map(([k, v]) => (
                                    <tr key={k} className="border-b last:border-0">
                                      <td className="py-1">{k}</td>
                                      <td className="py-1 text-right font-medium">{v}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )}
                            <p className="text-xs text-gray-500 mt-2">
                              MLC: {outcomesData.mortality.mlc_count} · Autopsy: {outcomesData.mortality.autopsy_count}
                            </p>
                          </CardContent>
                        </Card>
                        <Card>
                          <CardContent className="pt-4">
                            <p className="font-semibold mb-2">Mortality — top diagnoses</p>
                            {Object.keys(outcomesData.mortality.by_diagnosis_top10).length === 0 ? (
                              <p className="text-xs text-gray-400">—</p>
                            ) : (
                              <table className="w-full text-sm">
                                <tbody>
                                  {Object.entries(outcomesData.mortality.by_diagnosis_top10).map(([k, v]) => (
                                    <tr key={k} className="border-b last:border-0">
                                      <td className="py-1 truncate max-w-md">{k}</td>
                                      <td className="py-1 text-right font-medium">{v}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )}
                          </CardContent>
                        </Card>
                        <Card>
                          <CardContent className="pt-4">
                            <p className="font-semibold mb-2">Readmissions — by days since discharge</p>
                            <table className="w-full text-sm">
                              <tbody>
                                {Object.entries(outcomesData.readmissions.by_window_days).map(([k, v]) => (
                                  <tr key={k} className="border-b last:border-0">
                                    <td className="py-1">{k} days</td>
                                    <td className="py-1 text-right font-medium">{v}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </CardContent>
                        </Card>
                        <Card>
                          <CardContent className="pt-4">
                            <p className="font-semibold mb-2">Length of stay (days)</p>
                            <table className="w-full text-sm">
                              <thead className="text-xs text-gray-500">
                                <tr><th className="text-left">Scope</th><th>Count</th><th>Mean</th><th>Median</th><th>Min</th><th>Max</th></tr>
                              </thead>
                              <tbody>
                                <tr className="border-b">
                                  <td className="py-1 font-medium">Overall</td>
                                  <td className="py-1 text-center">{outcomesData.length_of_stay.overall.count}</td>
                                  <td className="py-1 text-center">{outcomesData.length_of_stay.overall.mean ?? '—'}</td>
                                  <td className="py-1 text-center">{outcomesData.length_of_stay.overall.median ?? '—'}</td>
                                  <td className="py-1 text-center">{outcomesData.length_of_stay.overall.min ?? '—'}</td>
                                  <td className="py-1 text-center">{outcomesData.length_of_stay.overall.max ?? '—'}</td>
                                </tr>
                                {Object.entries(outcomesData.length_of_stay.by_department || {}).map(([dept, s]) => (
                                  <tr key={dept} className="border-b last:border-0">
                                    <td className="py-1">{dept}</td>
                                    <td className="py-1 text-center">{s.count}</td>
                                    <td className="py-1 text-center">{s.mean ?? '—'}</td>
                                    <td className="py-1 text-center">{s.median ?? '—'}</td>
                                    <td className="py-1 text-center">{s.min ?? '—'}</td>
                                    <td className="py-1 text-center">{s.max ?? '—'}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </CardContent>
                        </Card>
                      </div>
                    </>
                  )}
                </TabsContent>

                {/* ----- E3: Doctor productivity ----- */}
                <TabsContent value="productivity" className="space-y-4 mt-4">
                  <div className="flex items-end gap-3 flex-wrap">
                    <div>
                      <Label className="text-xs">From</Label>
                      <Input type="date" value={productivityRange.from}
                        onChange={e => setProductivityRange(p => ({ ...p, from: e.target.value }))} />
                    </div>
                    <div>
                      <Label className="text-xs">To</Label>
                      <Input type="date" value={productivityRange.to}
                        onChange={e => setProductivityRange(p => ({ ...p, to: e.target.value }))} />
                    </div>
                    <div className="min-w-[200px]">
                      <Label className="text-xs">Doctor (optional)</Label>
                      <Select value={productivityRange.doctor_id || 'all'}
                        onValueChange={v => setProductivityRange(p => ({ ...p, doctor_id: v === 'all' ? '' : v }))}>
                        <SelectTrigger><SelectValue placeholder="All doctors" /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All doctors</SelectItem>
                          {doctorsList.map(d => (
                            <SelectItem key={d.id} value={String(d.id)}>Dr. {d.first_name} {d.last_name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <Button size="sm" onClick={() => fetchDoctorProductivity(productivityRange)}>
                      Refresh
                    </Button>
                    <Button size="sm" variant="outline"
                      onClick={() => {
                        const params = { date_from: productivityRange.from, date_to: productivityRange.to, include_header: true };
                        if (productivityRange.doctor_id) params.doctor_id = productivityRange.doctor_id;
                        printPdfFromUrl('/api/inpatient/reports/doctor-productivity/pdf', params);
                      }}>
                      <Printer className="h-4 w-4 mr-1" /> Print PDF
                    </Button>
                    <Button size="sm" variant="outline"
                      onClick={() => {
                        const qs = new URLSearchParams({ date_from: productivityRange.from, date_to: productivityRange.to });
                        if (productivityRange.doctor_id) qs.append('doctor_id', productivityRange.doctor_id);
                        window.open(`/api/inpatient/reports/doctor-productivity/csv?${qs.toString()}`, '_blank');
                      }}>
                      <Download className="h-4 w-4 mr-1" /> CSV
                    </Button>
                  </div>

                  {!productivityData ? (
                    <p className="text-sm text-gray-500">Loading…</p>
                  ) : productivityData.rows.length === 0 ? (
                    <p className="text-sm text-gray-500">No activity in this date range.</p>
                  ) : (
                    <div className="border rounded overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="bg-gray-100 text-xs">
                          <tr>
                            <th className="p-2 text-left">Doctor</th>
                            <th className="p-2 text-right">Adm</th>
                            <th className="p-2 text-right">Dis</th>
                            <th className="p-2 text-right">Death</th>
                            <th className="p-2 text-right">Re-30d</th>
                            <th className="p-2 text-right">OT-Sur</th>
                            <th className="p-2 text-right">OT-An</th>
                            <th className="p-2 text-right">Visits</th>
                            <th className="p-2 text-right">Avg LOS</th>
                            <th className="p-2 text-right">Visit ₹</th>
                            <th className="p-2 text-right">OT-Sur ₹</th>
                            <th className="p-2 text-right">OT-An ₹</th>
                            <th className="p-2 text-right font-bold">Total ₹</th>
                          </tr>
                        </thead>
                        <tbody>
                          {productivityData.rows.map(r => (
                            <tr key={r.doctor_id} className="border-b last:border-0">
                              <td className="p-2">{r.doctor_name}</td>
                              <td className="p-2 text-right">{r.admissions}</td>
                              <td className="p-2 text-right">{r.discharges}</td>
                              <td className="p-2 text-right">{r.deaths}</td>
                              <td className="p-2 text-right">{r.readmissions_30d}</td>
                              <td className="p-2 text-right">{r.ot_as_surgeon}</td>
                              <td className="p-2 text-right">{r.ot_as_anaesthetist}</td>
                              <td className="p-2 text-right">{r.visits}</td>
                              <td className="p-2 text-right">{r.average_los_days ?? '—'}</td>
                              <td className="p-2 text-right">₹{Number(r.visit_fees_billed).toLocaleString()}</td>
                              <td className="p-2 text-right">₹{Number(r.ot_surgeon_fees).toLocaleString()}</td>
                              <td className="p-2 text-right">₹{Number(r.ot_anaesthetist_fees).toLocaleString()}</td>
                              <td className="p-2 text-right font-bold">₹{Number(r.total_billed_attributable).toLocaleString()}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  <p className="text-xs text-gray-500 italic">
                    Total ₹ = Visit fees + OT surgeon fees (for OTs led) + OT anaesthetist fees. Outpatient consultation fees not included.
                  </p>
                </TabsContent>
              </Tabs>
            </div>
          )}

          {/* ============ BILLING SETUP (catalogs) ============ */}
          {activeTab === 'setup' && (
            <div className="p-6 overflow-y-auto h-full space-y-4">
              <h2 className="text-lg font-semibold">Billing Setup</h2>
              <Tabs value={setupSubTab} onValueChange={(v) => { setSetupSubTab(v); if (v === 'consent-templates') fetchConsentTemplates(); }}>
                <TabsList>
                  <TabsTrigger value="ancillary">Ancillary Services</TabsTrigger>
                  <TabsTrigger value="packages">Surgery Packages</TabsTrigger>
                  <TabsTrigger value="tpa">TPA Companies</TabsTrigger>
                  <TabsTrigger value="consent-templates">Consent Templates</TabsTrigger>
                </TabsList>

                <TabsContent value="ancillary" className="space-y-3 mt-3">
                  <div className="flex justify-between items-center">
                    <p className="text-sm text-gray-500">Services billable against admissions (imaging, physiotherapy, dialysis, equipment, etc.)</p>
                    <Button size="sm" onClick={() => { setEditingService(null); setServiceForm({ service_name: '', service_code: '', category: 'imaging', default_charge: '', charge_unit: 'per_session', description: '' }); setShowServiceDialog(true); }}>
                      <Plus className="h-4 w-4 mr-1" /> New Service
                    </Button>
                  </div>
                  {ancillaryServices.length === 0 ? (
                    <Card><CardContent className="py-8 text-center text-gray-500 text-sm">No services configured.</CardContent></Card>
                  ) : (
                    <div className="border rounded overflow-hidden">
                      <table className="w-full text-sm">
                        <thead className="bg-gray-50"><tr>
                          <th className="px-3 py-2 text-left">Service</th>
                          <th className="px-3 py-2 text-left">Category</th>
                          <th className="px-3 py-2 text-left">Unit</th>
                          <th className="px-3 py-2 text-right">Default Charge</th>
                          <th className="px-3 py-2"></th>
                        </tr></thead>
                        <tbody>
                          {ancillaryServices.map(s => (
                            <tr key={s.id} className="border-t">
                              <td className="px-3 py-2"><div>{s.service_name}</div>{s.service_code && <div className="text-xs text-gray-500">{s.service_code}</div>}</td>
                              <td className="px-3 py-2"><Badge variant="outline">{s.category}</Badge></td>
                              <td className="px-3 py-2 text-xs text-gray-500">{s.charge_unit.replace('per_', '/')}</td>
                              <td className="px-3 py-2 text-right font-semibold">₹{s.default_charge.toFixed(2)}</td>
                              <td className="px-3 py-2 text-right">
                                <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => { setEditingService(s); setServiceForm({ service_name: s.service_name, service_code: s.service_code || '', category: s.category, default_charge: String(s.default_charge), charge_unit: s.charge_unit, description: s.description || '' }); setShowServiceDialog(true); }}><Edit2 className="h-3.5 w-3.5" /></Button>
                                <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setConfirmState({ open: true, title: 'Deactivate service?', description: `"${s.service_name}" will be hidden from new charges.`, onConfirm: () => { setConfirmState({ open: false }); handleDeleteService(s.id); } })}><Trash2 className="h-3.5 w-3.5 text-red-500" /></Button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="packages" className="space-y-3 mt-3">
                  <div className="flex justify-between items-center">
                    <p className="text-sm text-gray-500">Fixed-price surgery/treatment packages (e.g. cataract, LSCS, appendectomy).</p>
                    <Button size="sm" onClick={() => { setEditingPackage(null); setPackageForm({ package_name: '', package_code: '', base_price: '', included_room_type: '', included_stay_days: 0, included_services: [], excess_per_day_charge: 0, description: '' }); setShowPackageDialog(true); }}>
                      <Plus className="h-4 w-4 mr-1" /> New Package
                    </Button>
                  </div>
                  {packagesList.length === 0 ? (
                    <Card><CardContent className="py-8 text-center text-gray-500 text-sm">No packages configured.</CardContent></Card>
                  ) : (
                    <div className="space-y-2">
                      {packagesList.map(pkg => (
                        <Card key={pkg.id}>
                          <CardContent className="py-3">
                            <div className="flex justify-between items-start">
                              <div>
                                <div className="font-semibold text-sm">{pkg.package_name} {pkg.package_code && <span className="text-xs text-gray-400">· {pkg.package_code}</span>}</div>
                                <div className="text-xs text-gray-600 mt-1">₹{pkg.base_price.toFixed(2)} base · {pkg.included_stay_days} days · ₹{pkg.excess_per_day_charge}/excess day · Room: {pkg.included_room_type || 'any'}</div>
                                {pkg.included_services && pkg.included_services.length > 0 && (
                                  <div className="flex gap-1 flex-wrap mt-1">
                                    {pkg.included_services.map(s => <Badge key={s} variant="outline" className="text-xs">{s.replace('_', ' ')}</Badge>)}
                                  </div>
                                )}
                                {pkg.description && <p className="text-xs text-gray-500 mt-1">{pkg.description}</p>}
                              </div>
                              <div className="flex gap-1">
                                <Button size="sm" variant="ghost" onClick={() => { setEditingPackage(pkg); setPackageForm({ package_name: pkg.package_name, package_code: pkg.package_code || '', base_price: String(pkg.base_price), included_room_type: pkg.included_room_type || '', included_stay_days: pkg.included_stay_days, included_services: pkg.included_services || [], excess_per_day_charge: pkg.excess_per_day_charge, description: pkg.description || '' }); setShowPackageDialog(true); }}><Edit2 className="h-3.5 w-3.5" /></Button>
                                <Button size="sm" variant="ghost" onClick={() => setConfirmState({ open: true, title: 'Deactivate package?', description: `"${pkg.package_name}" will be hidden from new admissions.`, onConfirm: () => { setConfirmState({ open: false }); handleDeletePackage(pkg.id); } })}><Trash2 className="h-3.5 w-3.5 text-red-500" /></Button>
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="consent-templates" className="space-y-3 mt-3">
                  <div className="flex justify-between items-center">
                    <p className="text-sm text-gray-500">Reusable consent form templates by category (surgical, anaesthesia, blood transfusion, etc.)</p>
                    <Button size="sm" onClick={() => { setEditingConsentTemplate(null); setConsentTemplateForm({ consent_type: 'surgical', template_name: '', content: '', language: 'english' }); setShowConsentTemplateDialog(true); }}>
                      <Plus className="h-4 w-4 mr-1" /> New Template
                    </Button>
                  </div>
                  {consentTemplates.length === 0 ? (
                    <Card><CardContent className="py-8 text-center text-gray-500 text-sm">No templates configured.</CardContent></Card>
                  ) : (
                    <div className="space-y-2">
                      {consentTemplates.map(t => (
                        <Card key={t.id}>
                          <CardContent className="py-3">
                            <div className="flex justify-between items-start">
                              <div>
                                <div className="font-semibold text-sm flex items-center gap-1.5"><FileSignature className="h-4 w-4" /> {t.template_name}</div>
                                <div className="text-xs text-gray-500 mt-0.5">
                                  <Badge variant="outline" className="text-xs mr-1">{t.consent_type.replace(/_/g, ' ')}</Badge>
                                  Language: {t.language}
                                </div>
                                <p className="text-xs text-gray-600 mt-1 line-clamp-2">{t.content.substring(0, 150)}{t.content.length > 150 ? '...' : ''}</p>
                              </div>
                              <div className="flex gap-1">
                                <Button size="sm" variant="ghost" onClick={() => { setEditingConsentTemplate(t); setConsentTemplateForm({ consent_type: t.consent_type, template_name: t.template_name, content: t.content, language: t.language }); setShowConsentTemplateDialog(true); }}><Edit2 className="h-3.5 w-3.5" /></Button>
                                <Button size="sm" variant="ghost" onClick={() => setConfirmState({ open: true, title: 'Deactivate template?', description: `"${t.template_name}" will be hidden from new consents.`, onConfirm: () => { setConfirmState({ open: false }); handleDeleteConsentTemplate(t.id); } })}><Trash2 className="h-3.5 w-3.5 text-red-500" /></Button>
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="tpa" className="space-y-3 mt-3">
                  <div className="flex justify-between items-center">
                    <p className="text-sm text-gray-500">Third Party Administrators used when splitting bills or routing pre-auth requests.</p>
                    <Button size="sm" onClick={() => { setEditingTpa(null); setTpaForm({ tpa_name: '', tpa_code: '', address: '', phone: '', email: '', default_discount_percent: 0, contract_details: '' }); setShowTpaDialog(true); }}>
                      <Plus className="h-4 w-4 mr-1" /> New TPA
                    </Button>
                  </div>
                  {tpaList.length === 0 ? (
                    <Card><CardContent className="py-8 text-center text-gray-500 text-sm">No TPAs configured.</CardContent></Card>
                  ) : (
                    <div className="space-y-2">
                      {tpaList.map(t => (
                        <Card key={t.id}>
                          <CardContent className="py-3">
                            <div className="flex justify-between items-start">
                              <div>
                                <div className="font-semibold text-sm flex items-center gap-1.5"><Building2 className="h-4 w-4 text-gray-500" /> {t.tpa_name} {t.tpa_code && <span className="text-xs text-gray-400">· {t.tpa_code}</span>}</div>
                                <div className="text-xs text-gray-600 mt-1">{t.phone || '—'} · {t.email || '—'} · Discount {t.default_discount_percent}%</div>
                                {t.address && <p className="text-xs text-gray-500 mt-0.5">{t.address}</p>}
                              </div>
                              <div className="flex gap-1">
                                <Button size="sm" variant="ghost" onClick={() => { setEditingTpa(t); setTpaForm({ tpa_name: t.tpa_name, tpa_code: t.tpa_code || '', address: t.address || '', phone: t.phone || '', email: t.email || '', default_discount_percent: t.default_discount_percent, contract_details: t.contract_details || '' }); setShowTpaDialog(true); }}><Edit2 className="h-3.5 w-3.5" /></Button>
                                <Button size="sm" variant="ghost" onClick={() => setConfirmState({ open: true, title: 'Deactivate TPA?', description: `"${t.tpa_name}" will be hidden from new splits.`, onConfirm: () => { setConfirmState({ open: false }); handleDeleteTpa(t.id); } })}><Trash2 className="h-3.5 w-3.5 text-red-500" /></Button>
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  )}
                </TabsContent>
              </Tabs>
            </div>
          )}

        </div>
      </div>

      {/* ============================================================ */}
      {/* DIALOGS */}
      {/* ============================================================ */}

      {/* Admission Dialog */}
      <Dialog open={showAdmissionDialog} onOpenChange={setShowAdmissionDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>New Admission</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateAdmission} className="space-y-4">
            {/* Patient search */}
            <div>
              <Label>Patient *</Label>
              {selectedPatient && admissionForm.patient_id ? (
                <div className="flex items-center justify-between p-3 bg-green-50 border border-green-200 rounded-lg mt-1">
                  <div>
                    <p className="font-medium text-green-900">{selectedPatient.first_name} {selectedPatient.last_name}</p>
                    <p className="text-sm text-green-600">ID: {selectedPatient.patient_id} • Phone: {selectedPatient.primary_phone}</p>
                  </div>
                  <Button type="button" variant="ghost" size="sm" onClick={() => {
                    setSelectedPatient(null);
                    setSelectedPatientName('');
                    setAdmissionForm(p => ({ ...p, patient_id: '' }));
                    setPatientSearchQuery('');
                    setPatientSearchResults([]);
                  }}>
                    <XCircle className="h-4 w-4" />
                  </Button>
                </div>
              ) : (
                <>
                  <div className="relative mt-1">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                    <Input
                      className="pl-9"
                      placeholder="Type patient name, phone number, or ID..."
                      value={patientSearchQuery}
                      onChange={e => setPatientSearchQuery(e.target.value)}
                    />
                    {patientSearching && (
                      <div className="absolute right-3 top-1/2 transform -translate-y-1/2">
                        <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
                      </div>
                    )}
                  </div>
                  {!patientSearchQuery.trim() && (
                    <p className="text-gray-400 text-xs mt-1.5">Start typing to search patients...</p>
                  )}
                  {patientSearchQuery.trim() && (
                    <div className="mt-1 border rounded-lg max-h-48 overflow-y-auto">
                      {patientSearching ? (
                        <div className="flex items-center justify-center py-4 gap-2 text-gray-400">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          <span className="text-sm">Searching...</span>
                        </div>
                      ) : patientSearchResults.length === 0 ? (
                        <p className="text-gray-500 text-sm text-center py-4">No patients found. Please register the patient first.</p>
                      ) : (
                        patientSearchResults.map(p => (
                          <div
                            key={p.patient_id}
                            className="px-4 py-2.5 hover:bg-blue-50 cursor-pointer border-b last:border-b-0"
                            onClick={() => {
                              setAdmissionForm(prev => ({ ...prev, patient_id: p.id }));
                              setSelectedPatient(p);
                              setSelectedPatientName(`${p.first_name} ${p.last_name}`);
                              setPatientSearchQuery('');
                              setPatientSearchResults([]);
                            }}
                          >
                            <div className="flex justify-between items-center">
                              <div>
                                <p className="font-medium text-gray-900 text-sm">{p.first_name} {p.last_name}</p>
                                <p className="text-xs text-gray-500">{p.primary_phone} • ID: {p.patient_id?.slice(0, 8)}...</p>
                              </div>
                              <Badge variant="outline" className="text-xs">
                                {p.gender || 'N/A'}{p.age != null ? ` • ${p.age}y` : (p.date_of_birth ? ` • ${new Date().getFullYear() - new Date(p.date_of_birth).getFullYear()}y` : '')}
                              </Badge>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  )}
                </>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Admitting Doctor *</Label>
                <Select value={admissionForm.admitting_doctor_id ? String(admissionForm.admitting_doctor_id) : ''} onValueChange={v => setAdmissionForm(p => ({ ...p, admitting_doctor_id: v }))}>
                  <SelectTrigger><SelectValue placeholder="Select doctor" /></SelectTrigger>
                  <SelectContent>
                    {doctorsList.map(d => (
                      <SelectItem key={d.id} value={String(d.id)}>Dr. {d.first_name} {d.last_name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Room *</Label>
                <Select value={admissionForm.room_id ? String(admissionForm.room_id) : ''} onValueChange={v => {
                  setAdmissionForm(p => ({ ...p, room_id: v, bed_id: '' }));
                  // Fetch beds for selected room
                  axios.get(`/api/inpatient/rooms/${v}/beds`).then(res => setAdmissionBeds(res.data)).catch(() => setAdmissionBeds([]));
                }}>
                  <SelectTrigger><SelectValue placeholder="Select room" /></SelectTrigger>
                  <SelectContent>
                    {availableRooms.map(r => (
                      <SelectItem key={r.id} value={String(r.id)}>
                        {r.room_number} ({roomTypeLabel[r.room_type]}) - {r.available_beds} beds avail - ₹{r.room_charge_per_day}/day
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {admissionBeds.length > 0 && (
                <div>
                  <Label>Bed</Label>
                  <Select value={admissionForm.bed_id ? String(admissionForm.bed_id) : ''} onValueChange={v => setAdmissionForm(p => ({ ...p, bed_id: v }))}>
                    <SelectTrigger><SelectValue placeholder="Select bed" /></SelectTrigger>
                    <SelectContent>
                      {admissionBeds.filter(b => b.status === 'available').map(b => (
                        <SelectItem key={b.id} value={String(b.id)}>
                          Bed {b.bed_label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Admission Type *</Label>
                <Select value={admissionForm.admission_type} onValueChange={v => setAdmissionForm(p => ({ ...p, admission_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="elective">Elective</SelectItem>
                    <SelectItem value="emergency">Emergency</SelectItem>
                    <SelectItem value="transfer">Transfer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Condition</Label>
                <Select value={admissionForm.condition_on_admission} onValueChange={v => setAdmissionForm(p => ({ ...p, condition_on_admission: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="stable">Stable</SelectItem>
                    <SelectItem value="serious">Serious</SelectItem>
                    <SelectItem value="critical">Critical</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Estimated Stay (days)</Label>
                <Input type="number" min="1" value={admissionForm.estimated_stay_days} onChange={e => setAdmissionForm(p => ({ ...p, estimated_stay_days: e.target.value }))} />
              </div>
              <div>
                <Label>Bed Number</Label>
                <Input value={admissionForm.bed_number} onChange={e => setAdmissionForm(p => ({ ...p, bed_number: e.target.value }))} />
              </div>
            </div>

            <div>
              <Label>Admission Reason</Label>
              <Textarea value={admissionForm.admission_reason} onChange={e => setAdmissionForm(p => ({ ...p, admission_reason: e.target.value }))} rows={2} />
            </div>

            <div>
              <Label>Emergency Contact</Label>
              <Input value={admissionForm.emergency_contact} onChange={e => setAdmissionForm(p => ({ ...p, emergency_contact: e.target.value }))} />
            </div>

            {admissionForm.admission_type === 'emergency' && (
              <div className="border-t pt-4 bg-red-50 -mx-6 px-6 py-4">
                <h4 className="font-medium text-sm mb-3 text-red-700">Emergency / Casualty Details</h4>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <Label className="text-xs">Triage Level *</Label>
                    <Select value={admissionForm.triage_level} onValueChange={v => setAdmissionForm(p => ({ ...p, triage_level: v }))}>
                      <SelectTrigger className="h-9"><SelectValue placeholder="ESI 1-5" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="1">1 — Resuscitation</SelectItem>
                        <SelectItem value="2">2 — Emergent</SelectItem>
                        <SelectItem value="3">3 — Urgent</SelectItem>
                        <SelectItem value="4">4 — Less Urgent</SelectItem>
                        <SelectItem value="5">5 — Non-Urgent</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label className="text-xs">Arrival Mode</Label>
                    <Select value={admissionForm.arrival_mode} onValueChange={v => setAdmissionForm(p => ({ ...p, arrival_mode: v }))}>
                      <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="walk_in">Walk-in</SelectItem>
                        <SelectItem value="ambulance">Ambulance</SelectItem>
                        <SelectItem value="referred">Referred</SelectItem>
                        <SelectItem value="police">Police</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="flex items-center gap-2 pt-5">
                    <input type="checkbox" id="is_mlc" checked={admissionForm.is_mlc}
                      onChange={e => setAdmissionForm(p => ({ ...p, is_mlc: e.target.checked }))} />
                    <Label htmlFor="is_mlc" className="text-xs font-medium text-red-700">Medico-Legal Case (MLC)</Label>
                  </div>
                </div>
                <div className="mt-3">
                  <Label className="text-xs">Chief Complaint</Label>
                  <Input value={admissionForm.chief_complaint} placeholder="e.g. Chest pain, RTA, Burn 30%"
                    onChange={e => setAdmissionForm(p => ({ ...p, chief_complaint: e.target.value }))} className="h-9" />
                </div>
                {admissionForm.arrival_mode === 'ambulance' && (
                  <div className="mt-3">
                    <Label className="text-xs">Ambulance Details</Label>
                    <Input value={admissionForm.ambulance_details} placeholder="Vehicle no., paramedic name, vitals on arrival"
                      onChange={e => setAdmissionForm(p => ({ ...p, ambulance_details: e.target.value }))} className="h-9" />
                  </div>
                )}
                {admissionForm.is_mlc && (
                  <div className="mt-3 grid grid-cols-3 gap-3 border-t border-red-200 pt-3">
                    <div>
                      <Label className="text-xs">MLC Type *</Label>
                      <Select value={admissionForm.mlc_type} onValueChange={v => setAdmissionForm(p => ({ ...p, mlc_type: v }))}>
                        <SelectTrigger className="h-9"><SelectValue placeholder="Select" /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="rta">Road Traffic Accident</SelectItem>
                          <SelectItem value="assault">Assault</SelectItem>
                          <SelectItem value="poisoning">Poisoning</SelectItem>
                          <SelectItem value="burn">Burn</SelectItem>
                          <SelectItem value="sexual_assault">Sexual Assault</SelectItem>
                          <SelectItem value="attempted_suicide">Attempted Suicide</SelectItem>
                          <SelectItem value="other">Other</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="text-xs">MLC Number</Label>
                      <Input value={admissionForm.mlc_number}
                        onChange={e => setAdmissionForm(p => ({ ...p, mlc_number: e.target.value }))} className="h-9" />
                    </div>
                    <div>
                      <Label className="text-xs">Police Station Informed</Label>
                      <Input value={admissionForm.police_station_informed} placeholder="PS name"
                        onChange={e => setAdmissionForm(p => ({ ...p, police_station_informed: e.target.value }))} className="h-9" />
                    </div>
                  </div>
                )}

                <div className="mt-3 grid grid-cols-2 gap-3 border-t border-red-200 pt-3">
                  <label className="flex items-start gap-2 text-sm">
                    <input type="checkbox" className="mt-1" checked={admissionForm.is_observation}
                      onChange={e => setAdmissionForm(p => ({ ...p, is_observation: e.target.checked }))} />
                    <span><span className="font-medium">Observation case (≤24h)</span>
                      <span className="block text-[11px] text-gray-500">Skips room rent. Billable services (drugs/lab/visits) still apply.</span></span>
                  </label>
                  <label className="flex items-start gap-2 text-sm">
                    <input type="checkbox" className="mt-1" checked={admissionForm.deposit_waived}
                      onChange={e => setAdmissionForm(p => ({ ...p, deposit_waived: e.target.checked }))} />
                    <span><span className="font-medium">Waive admission deposit</span>
                      <span className="block text-[11px] text-gray-500">Per Supreme Court / CEA Act — cannot turn away emergency cases.</span></span>
                  </label>
                </div>
                {admissionForm.deposit_waived && (
                  <div className="mt-2">
                    <Label className="text-xs">Waiver Reason *</Label>
                    <Input value={admissionForm.deposit_waiver_reason} placeholder="e.g. Unconscious unidentified patient — RTA"
                      onChange={e => setAdmissionForm(p => ({ ...p, deposit_waiver_reason: e.target.value }))} className="h-9" />
                  </div>
                )}
              </div>
            )}

            <div className="border-t pt-4">
              <h4 className="font-medium text-sm mb-3">Insurance (Optional)</h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <Label className="text-xs">Insurance Provider</Label>
                  <Input placeholder="Provider name" value={admissionForm.insurance_provider}
                    onChange={e => setAdmissionForm(p => ({ ...p, insurance_provider: e.target.value }))} />
                </div>
                <div>
                  <Label className="text-xs">Policy Number</Label>
                  <Input placeholder="Policy #" value={admissionForm.policy_number}
                    onChange={e => setAdmissionForm(p => ({ ...p, policy_number: e.target.value }))} />
                </div>
                <div>
                  <Label className="text-xs">Claim Reference</Label>
                  <Input placeholder="Claim ref" value={admissionForm.claim_reference}
                    onChange={e => setAdmissionForm(p => ({ ...p, claim_reference: e.target.value }))} />
                </div>
              </div>
            </div>

            <div>
              <Label>Additional Notes</Label>
              <Textarea value={admissionForm.admission_notes} onChange={e => setAdmissionForm(p => ({ ...p, admission_notes: e.target.value }))} rows={2} />
            </div>

            <Button type="submit" className="w-full" disabled={loading || !admissionForm.patient_id || !admissionForm.admitting_doctor_id || !admissionForm.room_id}>
              {loading ? 'Admitting...' : 'Admit Patient'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Emergency Quick Admit Dialog */}
      <Dialog open={showQuickAdmitDialog} onOpenChange={setShowQuickAdmitDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-red-700">Emergency Quick Admit</DialogTitle>
            <p className="text-xs text-gray-500">For casualty arrivals — minimal info now, reception completes patient KYC later.</p>
          </DialogHeader>
          <form onSubmit={handleQuickAdmit} className="space-y-4">
            <div className="bg-red-50 -mx-6 px-6 py-3 border-b border-red-200">
              <h4 className="font-medium text-sm mb-2 text-red-700">Patient Identity (minimum)</h4>
              <div className="grid grid-cols-2 gap-3">
                <div><Label className="text-xs">First / Identifying Name *</Label>
                  <Input value={quickAdmitForm.first_name} placeholder="UNKNOWN MALE-1 if unidentified"
                    onChange={e => setQuickAdmitForm(p => ({ ...p, first_name: e.target.value }))} className="h-9" /></div>
                <div><Label className="text-xs">Last Name</Label>
                  <Input value={quickAdmitForm.last_name}
                    onChange={e => setQuickAdmitForm(p => ({ ...p, last_name: e.target.value }))} className="h-9" /></div>
                <div><Label className="text-xs">Approx Age</Label>
                  <Input type="number" value={quickAdmitForm.age}
                    onChange={e => setQuickAdmitForm(p => ({ ...p, age: e.target.value }))} className="h-9" /></div>
                <div><Label className="text-xs">Gender</Label>
                  <Select value={quickAdmitForm.gender} onValueChange={v => setQuickAdmitForm(p => ({ ...p, gender: v }))}>
                    <SelectTrigger className="h-9"><SelectValue placeholder="Select" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="male">Male</SelectItem>
                      <SelectItem value="female">Female</SelectItem>
                      <SelectItem value="other">Other</SelectItem>
                    </SelectContent>
                  </Select></div>
                <div><Label className="text-xs">Contact Phone</Label>
                  <Input value={quickAdmitForm.primary_phone} placeholder="If known"
                    onChange={e => setQuickAdmitForm(p => ({ ...p, primary_phone: e.target.value }))} className="h-9" /></div>
                <div><Label className="text-xs">Emergency Contact</Label>
                  <Input value={quickAdmitForm.emergency_contact}
                    onChange={e => setQuickAdmitForm(p => ({ ...p, emergency_contact: e.target.value }))} className="h-9" /></div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div><Label className="text-xs">Admitting Doctor *</Label>
                <Select value={quickAdmitForm.admitting_doctor_id} onValueChange={v => setQuickAdmitForm(p => ({ ...p, admitting_doctor_id: v }))}>
                  <SelectTrigger className="h-9"><SelectValue placeholder="Select doctor" /></SelectTrigger>
                  <SelectContent>
                    {doctorsList.map(d => <SelectItem key={d.id} value={String(d.id)}>{d.first_name} {d.last_name}</SelectItem>)}
                  </SelectContent>
                </Select></div>
              <div><Label className="text-xs">Room *</Label>
                <Select value={quickAdmitForm.room_id} onValueChange={v => setQuickAdmitForm(p => ({ ...p, room_id: v, bed_id: '' }))}>
                  <SelectTrigger className="h-9"><SelectValue placeholder="Select room" /></SelectTrigger>
                  <SelectContent>
                    {availableRooms.filter(r => r.available_beds > 0).map(r => (
                      <SelectItem key={r.id} value={String(r.id)}>
                        {r.room_number} ({roomTypeLabel[r.room_type] || r.room_type}) — {r.available_beds} free
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select></div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div><Label className="text-xs">Triage *</Label>
                <Select value={quickAdmitForm.triage_level} onValueChange={v => setQuickAdmitForm(p => ({ ...p, triage_level: v }))}>
                  <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">1 — Resuscitation</SelectItem>
                    <SelectItem value="2">2 — Emergent</SelectItem>
                    <SelectItem value="3">3 — Urgent</SelectItem>
                    <SelectItem value="4">4 — Less Urgent</SelectItem>
                    <SelectItem value="5">5 — Non-Urgent</SelectItem>
                  </SelectContent>
                </Select></div>
              <div><Label className="text-xs">Arrival Mode</Label>
                <Select value={quickAdmitForm.arrival_mode} onValueChange={v => setQuickAdmitForm(p => ({ ...p, arrival_mode: v }))}>
                  <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="walk_in">Walk-in</SelectItem>
                    <SelectItem value="ambulance">Ambulance</SelectItem>
                    <SelectItem value="referred">Referred</SelectItem>
                    <SelectItem value="police">Police</SelectItem>
                  </SelectContent>
                </Select></div>
              <div><Label className="text-xs">Condition</Label>
                <Select value={quickAdmitForm.condition_on_admission} onValueChange={v => setQuickAdmitForm(p => ({ ...p, condition_on_admission: v }))}>
                  <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="stable">Stable</SelectItem>
                    <SelectItem value="serious">Serious</SelectItem>
                    <SelectItem value="critical">Critical</SelectItem>
                  </SelectContent>
                </Select></div>
            </div>

            <div><Label className="text-xs">Chief Complaint</Label>
              <Input value={quickAdmitForm.chief_complaint} placeholder="e.g. Chest pain x 2hrs, RTA head injury"
                onChange={e => setQuickAdmitForm(p => ({ ...p, chief_complaint: e.target.value }))} className="h-9" /></div>

            {quickAdmitForm.arrival_mode === 'ambulance' && (
              <div><Label className="text-xs">Ambulance Details</Label>
                <Input value={quickAdmitForm.ambulance_details} placeholder="Vehicle no., paramedic, vitals on arrival"
                  onChange={e => setQuickAdmitForm(p => ({ ...p, ambulance_details: e.target.value }))} className="h-9" /></div>
            )}

            <div className="border-t pt-3">
              <label className="flex items-center gap-2 text-sm font-medium text-red-700">
                <input type="checkbox" checked={quickAdmitForm.is_mlc}
                  onChange={e => setQuickAdmitForm(p => ({ ...p, is_mlc: e.target.checked }))} />
                Medico-Legal Case (MLC)
              </label>
              {quickAdmitForm.is_mlc && (
                <div className="grid grid-cols-3 gap-3 mt-3">
                  <div><Label className="text-xs">MLC Type *</Label>
                    <Select value={quickAdmitForm.mlc_type} onValueChange={v => setQuickAdmitForm(p => ({ ...p, mlc_type: v }))}>
                      <SelectTrigger className="h-9"><SelectValue placeholder="Select" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="rta">Road Traffic Accident</SelectItem>
                        <SelectItem value="assault">Assault</SelectItem>
                        <SelectItem value="poisoning">Poisoning</SelectItem>
                        <SelectItem value="burn">Burn</SelectItem>
                        <SelectItem value="sexual_assault">Sexual Assault</SelectItem>
                        <SelectItem value="attempted_suicide">Attempted Suicide</SelectItem>
                        <SelectItem value="other">Other</SelectItem>
                      </SelectContent>
                    </Select></div>
                  <div><Label className="text-xs">MLC Number</Label>
                    <Input value={quickAdmitForm.mlc_number}
                      onChange={e => setQuickAdmitForm(p => ({ ...p, mlc_number: e.target.value }))} className="h-9" /></div>
                  <div><Label className="text-xs">Police Station</Label>
                    <Input value={quickAdmitForm.police_station_informed}
                      onChange={e => setQuickAdmitForm(p => ({ ...p, police_station_informed: e.target.value }))} className="h-9" /></div>
                </div>
              )}
            </div>

            <div className="border-t pt-3 grid grid-cols-2 gap-3">
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-1" checked={quickAdmitForm.is_observation}
                  onChange={e => setQuickAdmitForm(p => ({ ...p, is_observation: e.target.checked }))} />
                <span><span className="font-medium">Observation case (≤24h)</span>
                  <span className="block text-[11px] text-gray-500">No room rent.</span></span>
              </label>
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-1" checked={quickAdmitForm.deposit_waived}
                  onChange={e => setQuickAdmitForm(p => ({ ...p, deposit_waived: e.target.checked }))} />
                <span><span className="font-medium">Waive deposit</span>
                  <span className="block text-[11px] text-gray-500">Cannot-pay emergency.</span></span>
              </label>
            </div>
            {quickAdmitForm.deposit_waived && (
              <div><Label className="text-xs">Waiver Reason *</Label>
                <Input value={quickAdmitForm.deposit_waiver_reason} placeholder="e.g. RTA — unidentified patient"
                  onChange={e => setQuickAdmitForm(p => ({ ...p, deposit_waiver_reason: e.target.value }))} className="h-9" /></div>
            )}

            <div><Label className="text-xs">Admission Reason / Provisional Diagnosis</Label>
              <Textarea value={quickAdmitForm.admission_reason}
                onChange={e => setQuickAdmitForm(p => ({ ...p, admission_reason: e.target.value }))} rows={2} /></div>

            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button type="button" variant="outline" onClick={() => setShowQuickAdmitDialog(false)}>Cancel</Button>
              <Button type="submit" variant="destructive" disabled={loading}>
                {loading ? 'Admitting...' : 'Admit Now'}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Visit Dialog */}
      <Dialog open={showVisitDialog} onOpenChange={setShowVisitDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Record Visit</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateVisit} className="space-y-4">
            <div>
              <Label>Visit Type *</Label>
              <Select value={visitForm.visit_type} onValueChange={v => setVisitForm(p => ({ ...p, visit_type: v, visitor_id: '' }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {!isNurseOnly && <SelectItem value="doctor_visit">Doctor Visit</SelectItem>}
                  <SelectItem value="nurse_visit">Nurse Visit</SelectItem>
                  {!isNurseOnly && <SelectItem value="procedure">Procedure</SelectItem>}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Visitor (Staff) *</Label>
              <Select value={visitForm.visitor_id ? String(visitForm.visitor_id) : ''} onValueChange={v => setVisitForm(p => ({ ...p, visitor_id: v }))}>
                <SelectTrigger><SelectValue placeholder="Select staff" /></SelectTrigger>
                <SelectContent>
                  {(visitForm.visit_type === 'nurse_visit' ? nursesList : doctorsList).map(d => (
                    <SelectItem key={d.id} value={String(d.id)}>{d.first_name} {d.last_name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {visitForm.visitor_id && (visitForm.visit_type === 'doctor_visit' || visitForm.visit_type === 'nurse_visit') && (() => {
              const visitor = [...(doctorsList || []), ...(nursesList || [])]
                .find(u => String(u.id) === String(visitForm.visitor_id));
              const fee = visitor?.inpatient_fee_inr;
              return (
                <p className="text-xs text-gray-500">
                  Auto-charge: {fee ? `₹${Number(fee).toFixed(2)}` : 'no fee set on this user'} (from selected staff member's inpatient fee)
                </p>
              );
            })()}
            <div>
              <Label>Notes</Label>
              <Textarea value={visitForm.notes} onChange={e => setVisitForm(p => ({ ...p, notes: e.target.value }))} rows={3} />
            </div>
            {visitForm.visit_type === 'doctor_visit' && (
              <div className="border rounded p-2 space-y-1 bg-gray-50">
                <p className="text-xs font-semibold text-gray-700">Ward-round checklist (optional)</p>
                {[
                  ['vitals_reviewed', 'Vitals reviewed'],
                  ['labs_reviewed', 'Labs reviewed'],
                  ['pain_assessed', 'Pain assessed'],
                  ['mobility_checked', 'Mobility checked'],
                  ['family_updated', 'Family updated'],
                ].map(([key, lbl]) => (
                  <label key={key} className="flex items-center gap-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={!!visitForm[key]}
                      onChange={e => setVisitForm(p => ({ ...p, [key]: e.target.checked }))} />
                    {lbl}
                  </label>
                ))}
                <div>
                  <Label className="text-xs">Plan for today</Label>
                  <Textarea rows={2} value={visitForm.plan_for_today}
                    placeholder="e.g., 'Continue IV antibiotics; repeat CBC tomorrow.'"
                    onChange={e => setVisitForm(p => ({ ...p, plan_for_today: e.target.value }))} />
                </div>
              </div>
            )}
            <Button type="submit" className="w-full" disabled={loading || !visitForm.visitor_id}>
              {loading ? 'Saving...' : 'Record Visit'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Nursing Note Dialog */}
      <Dialog open={showNursingNoteDialog} onOpenChange={(open) => { setShowNursingNoteDialog(open); if (!open) setEditingNursingNote(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{editingNursingNote ? 'Edit Nursing Note' : 'Add Nursing Note'}</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateNursingNote} className="space-y-4">
            <div>
              <Label>Shift *</Label>
              <Select value={nursingNoteForm.shift} onValueChange={v => setNursingNoteForm(p => ({ ...p, shift: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="morning">Morning</SelectItem>
                  <SelectItem value="afternoon">Afternoon</SelectItem>
                  <SelectItem value="night">Night</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Note Type *</Label>
              <Select value={nursingNoteForm.note_type} onValueChange={v => setNursingNoteForm(p => ({ ...p, note_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="observation">Observation</SelectItem>
                  <SelectItem value="medication">Medication</SelectItem>
                  <SelectItem value="vitals">Vitals</SelectItem>
                  <SelectItem value="procedure">Procedure</SelectItem>
                  <SelectItem value="handover">Handover</SelectItem>
                  <SelectItem value="general">General</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Content *</Label>
              <Textarea value={nursingNoteForm.content} onChange={e => setNursingNoteForm(p => ({ ...p, content: e.target.value }))} rows={5} placeholder="Enter nursing note details..." />
            </div>
            <Button type="submit" className="w-full" disabled={loading || !nursingNoteForm.content.trim()}>
              {loading ? 'Saving...' : editingNursingNote ? 'Update Note' : 'Add Note'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Diet Order Dialog */}
      <Dialog open={showDietDialog} onOpenChange={setShowDietDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Diet Order</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateDietOrder} className="space-y-4">
            <div>
              <Label>Diet Type *</Label>
              <Select value={dietForm.diet_type} onValueChange={v => setDietForm(p => ({ ...p, diet_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="regular">Regular</SelectItem>
                  <SelectItem value="diabetic">Diabetic</SelectItem>
                  <SelectItem value="liquid">Liquid</SelectItem>
                  <SelectItem value="soft">Soft</SelectItem>
                  <SelectItem value="npo">NPO (Nothing by Mouth)</SelectItem>
                  <SelectItem value="low_salt">Low Salt</SelectItem>
                  <SelectItem value="renal">Renal</SelectItem>
                  <SelectItem value="cardiac">Cardiac</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Meal Instructions</Label>
              <Textarea value={dietForm.meal_instructions} onChange={e => setDietForm(p => ({ ...p, meal_instructions: e.target.value }))} rows={2} placeholder="e.g. Small frequent meals, no breakfast before surgery..." />
            </div>
            <div>
              <Label>Allergies</Label>
              <Input value={dietForm.allergies} onChange={e => setDietForm(p => ({ ...p, allergies: e.target.value }))} placeholder="e.g. Peanuts, shellfish, dairy..." />
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea value={dietForm.notes} onChange={e => setDietForm(p => ({ ...p, notes: e.target.value }))} rows={2} placeholder="Additional dietary notes..." />
            </div>
            <p className="text-xs text-gray-500">Creating a new diet order will deactivate any previous active order.</p>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? 'Saving...' : 'Create Diet Order'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Meal Log Dialog */}
      <Dialog open={mealLogDialog.open} onOpenChange={(o) => !o && setMealLogDialog(p => ({ ...p, open: false }))}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Log meal served</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Meal *</Label>
                <Select value={mealLogDialog.meal_time}
                  onValueChange={v => setMealLogDialog(p => ({ ...p, meal_time: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="breakfast">Breakfast</SelectItem>
                    <SelectItem value="snack_morning">Mid-morning snack</SelectItem>
                    <SelectItem value="lunch">Lunch</SelectItem>
                    <SelectItem value="snack_evening">Evening snack</SelectItem>
                    <SelectItem value="dinner">Dinner</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Status *</Label>
                <Select value={mealLogDialog.status}
                  onValueChange={v => setMealLogDialog(p => ({ ...p, status: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="served">Served (full)</SelectItem>
                    <SelectItem value="partial">Partial</SelectItem>
                    <SelectItem value="refused">Refused</SelectItem>
                    <SelectItem value="missed">Missed (NPO/asleep)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>Notes (optional)</Label>
              <Textarea rows={2} value={mealLogDialog.notes}
                onChange={e => setMealLogDialog(p => ({ ...p, notes: e.target.value }))} />
            </div>
            <p className="text-xs text-gray-500">If a log already exists for this meal slot today, it will be updated.</p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setMealLogDialog({ open: false, orderId: null, meal_time: 'lunch', status: 'served', notes: '' })}>Cancel</Button>
              <Button onClick={handleLogMeal} disabled={loading}>{loading ? 'Saving…' : 'Save'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* LOA Dialog */}
      <Dialog open={loaDialog.open} onOpenChange={(o) => !o && setLoaDialog(p => ({ ...p, open: false }))}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Leave of Absence (Pass-out)</DialogTitle></DialogHeader>
          <div className="space-y-3">
            {loaList.length > 0 && (
              <div className="border rounded p-2 text-sm space-y-1 max-h-48 overflow-y-auto">
                <p className="font-semibold mb-1">History ({loaList.length})</p>
                {loaList.map(l => (
                  <div key={l.id} className="flex items-center justify-between border-b last:border-0 pb-1">
                    <div className="flex flex-col">
                      <span className="text-xs">
                        <Badge variant="outline" className="mr-2 text-[10px]">{l.status}</Badge>
                        {l.start_datetime && new Date(l.start_datetime).toLocaleString()}
                        {' → '}
                        {(l.actual_return_datetime || l.expected_return_datetime) &&
                          new Date(l.actual_return_datetime || l.expected_return_datetime).toLocaleString()}
                      </span>
                      <span className="text-xs text-gray-500 truncate max-w-md">{l.reason}</span>
                    </div>
                    {l.status === 'active' && (
                      <div className="flex gap-1">
                        <Button size="sm" variant="outline" className="h-6 text-xs" onClick={() => handleLoaAction(l.id, 'return')}>Returned</Button>
                        <Button size="sm" variant="ghost" className="h-6 text-xs text-red-600" onClick={() => handleLoaAction(l.id, 'cancel')}>Cancel</Button>
                        <Button size="sm" variant="ghost" className="h-6 text-xs text-amber-600" onClick={() => handleLoaAction(l.id, 'no-show')}>No-show</Button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            <p className="text-xs text-gray-500 border-t pt-2 font-semibold">Start a new LOA</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Start *</Label>
                <Input type="datetime-local" value={loaDialog.start_datetime}
                  onChange={e => setLoaDialog(p => ({ ...p, start_datetime: e.target.value }))} />
              </div>
              <div>
                <Label>Expected return *</Label>
                <Input type="datetime-local" value={loaDialog.expected_return_datetime}
                  onChange={e => setLoaDialog(p => ({ ...p, expected_return_datetime: e.target.value }))} />
              </div>
            </div>
            <div>
              <Label>Reason *</Label>
              <Textarea rows={2} value={loaDialog.reason}
                placeholder="e.g., 'Family wedding; will return Monday morning.'"
                onChange={e => setLoaDialog(p => ({ ...p, reason: e.target.value }))} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Approving Doctor *</Label>
                <Select value={String(loaDialog.approved_by_doctor_id || '')}
                  onValueChange={v => setLoaDialog(p => ({ ...p, approved_by_doctor_id: v }))}>
                  <SelectTrigger><SelectValue placeholder="Select doctor" /></SelectTrigger>
                  <SelectContent>
                    {doctorsList.map(d => (
                      <SelectItem key={d.id} value={String(d.id)}>Dr. {d.first_name} {d.last_name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <label className="flex items-center gap-2 mt-6 text-sm cursor-pointer">
                <input type="checkbox" checked={loaDialog.bed_held}
                  onChange={e => setLoaDialog(p => ({ ...p, bed_held: e.target.checked }))} />
                Bed held during LOA
              </label>
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea rows={2} value={loaDialog.notes}
                onChange={e => setLoaDialog(p => ({ ...p, notes: e.target.value }))} />
            </div>
            <p className="text-xs text-gray-500">
              Whole calendar days fully covered by the LOA window will be excluded from room rent.
              The patient remains admitted; bed is held by default.
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setLoaDialog(p => ({ ...p, open: false }))}>Close</Button>
              <Button onClick={handleCreateLoa} disabled={loading}>{loading ? 'Saving…' : 'Start LOA'}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Kitchen Ticket Print Dialog */}
      <Dialog open={kitchenTicketDialog.open} onOpenChange={(o) => !o && setKitchenTicketDialog(p => ({ ...p, open: false }))}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Print kitchen ticket</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Meal *</Label>
              <Select value={kitchenTicketDialog.meal_time}
                onValueChange={v => setKitchenTicketDialog(p => ({ ...p, meal_time: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="breakfast">Breakfast</SelectItem>
                  <SelectItem value="snack_morning">Mid-morning snack</SelectItem>
                  <SelectItem value="lunch">Lunch</SelectItem>
                  <SelectItem value="snack_evening">Evening snack</SelectItem>
                  <SelectItem value="dinner">Dinner</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Department / Ward filter (optional)</Label>
              <Input value={kitchenTicketDialog.department}
                placeholder="e.g., Medical Ward A — leave blank for all wards"
                onChange={e => setKitchenTicketDialog(p => ({ ...p, department: e.target.value }))} />
            </div>
            <p className="text-xs text-gray-500">The ticket lists every patient currently admitted with an active diet order, sorted by ward → room → bed.</p>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setKitchenTicketDialog({ open: false, meal_time: 'lunch', department: '' })}>Cancel</Button>
              <Button onClick={handlePrintKitchenTicket}>
                <Printer className="h-4 w-4 mr-1" /> Print
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Vitals Dialog */}
      <Dialog open={showVitalsDialog} onOpenChange={setShowVitalsDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Record Vital Signs</DialogTitle></DialogHeader>
          <form onSubmit={handleRecordVitals} className="space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <div>
                <Label>Shift</Label>
                <Select value={vitalsForm.shift} onValueChange={v => setVitalsForm(p => ({ ...p, shift: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="morning">Morning</SelectItem>
                    <SelectItem value="afternoon">Afternoon</SelectItem>
                    <SelectItem value="night">Night</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>BP Systolic (mmHg)</Label>
                <Input type="number" value={vitalsForm.bp_systolic} onChange={e => setVitalsForm(p => ({ ...p, bp_systolic: e.target.value }))} placeholder="120" />
              </div>
              <div>
                <Label>BP Diastolic (mmHg)</Label>
                <Input type="number" value={vitalsForm.bp_diastolic} onChange={e => setVitalsForm(p => ({ ...p, bp_diastolic: e.target.value }))} placeholder="80" />
              </div>
              <div>
                <Label>Heart Rate (bpm)</Label>
                <Input type="number" value={vitalsForm.heart_rate} onChange={e => setVitalsForm(p => ({ ...p, heart_rate: e.target.value }))} placeholder="72" />
              </div>
              <div>
                <Label>Resp. Rate (/min)</Label>
                <Input type="number" value={vitalsForm.respiratory_rate} onChange={e => setVitalsForm(p => ({ ...p, respiratory_rate: e.target.value }))} placeholder="16" />
              </div>
              <div>
                <Label>SpO₂ (%)</Label>
                <Input type="number" value={vitalsForm.spo2} onChange={e => setVitalsForm(p => ({ ...p, spo2: e.target.value }))} placeholder="98" />
              </div>
              <div>
                <Label>Temperature (°C)</Label>
                <Input type="number" step="0.1" value={vitalsForm.temperature_c} onChange={e => setVitalsForm(p => ({ ...p, temperature_c: e.target.value }))} placeholder="36.8" />
              </div>
              <div>
                <Label>Blood Glucose (mg/dL)</Label>
                <Input type="number" step="0.1" value={vitalsForm.blood_glucose} onChange={e => setVitalsForm(p => ({ ...p, blood_glucose: e.target.value }))} placeholder="110" />
              </div>
              <div>
                <Label>Pain (0-10)</Label>
                <Input type="number" min="0" max="10" value={vitalsForm.pain_score} onChange={e => setVitalsForm(p => ({ ...p, pain_score: e.target.value }))} />
              </div>
              <div>
                <Label>GCS (3-15)</Label>
                <Input type="number" min="3" max="15" value={vitalsForm.gcs_score} onChange={e => setVitalsForm(p => ({ ...p, gcs_score: e.target.value }))} />
              </div>
              <div>
                <Label>Weight (kg)</Label>
                <Input type="number" step="0.1" value={vitalsForm.weight_kg} onChange={e => setVitalsForm(p => ({ ...p, weight_kg: e.target.value }))} />
              </div>
              <div>
                <Label>Height (cm)</Label>
                <Input type="number" step="0.1" value={vitalsForm.height_cm} onChange={e => setVitalsForm(p => ({ ...p, height_cm: e.target.value }))} />
              </div>
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea value={vitalsForm.notes} onChange={e => setVitalsForm(p => ({ ...p, notes: e.target.value }))} rows={2} placeholder="Patient position, observations..." />
            </div>
            <p className="text-xs text-gray-500">Leave fields blank if not measured. Out-of-range values will be flagged automatically.</p>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? 'Saving…' : 'Record Vitals'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Allergy Dialog */}
      <Dialog open={showAllergyDialog} onOpenChange={setShowAllergyDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Record Patient Allergy</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateAllergy} className="space-y-3">
            <div>
              <Label>Type *</Label>
              <Select value={allergyForm.allergy_type} onValueChange={v => setAllergyForm(p => ({ ...p, allergy_type: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="drug">Drug</SelectItem>
                  <SelectItem value="food">Food</SelectItem>
                  <SelectItem value="environmental">Environmental</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Allergen *</Label>
              <Input value={allergyForm.allergen} onChange={e => setAllergyForm(p => ({ ...p, allergen: e.target.value }))} required placeholder="e.g. Penicillin, Peanuts, Latex" />
            </div>
            <div>
              <Label>Severity *</Label>
              <Select value={allergyForm.severity} onValueChange={v => setAllergyForm(p => ({ ...p, severity: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="mild">Mild</SelectItem>
                  <SelectItem value="moderate">Moderate</SelectItem>
                  <SelectItem value="severe">Severe</SelectItem>
                  <SelectItem value="anaphylaxis">Anaphylaxis</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Reaction</Label>
              <Textarea value={allergyForm.reaction} onChange={e => setAllergyForm(p => ({ ...p, reaction: e.target.value }))} rows={2} placeholder="e.g. Rash, swelling, anaphylactic shock" />
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea value={allergyForm.notes} onChange={e => setAllergyForm(p => ({ ...p, notes: e.target.value }))} rows={2} />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? 'Saving…' : 'Record Allergy'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Administer Dose Dialog */}
      <Dialog open={showAdministerDialog} onOpenChange={setShowAdministerDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Administer Dose</DialogTitle></DialogHeader>
          {administeringDose && (
            <form onSubmit={handleAdminister} className="space-y-3">
              <div className="text-sm bg-gray-50 p-3 rounded">
                <div className="font-medium">{administeringDose.medicine_name}</div>
                <div className="text-xs text-gray-600 mt-0.5">
                  {administeringDose.dosage} · Scheduled {administeringDose.scheduled_time && new Date(administeringDose.scheduled_time).toLocaleString()}
                </div>
              </div>
              {admissionAllergies.filter(a => a.allergy_type === 'drug').some(a => administeringDose.medicine_name && (administeringDose.medicine_name.toLowerCase().includes(a.allergen.toLowerCase()) || a.allergen.toLowerCase().includes(administeringDose.medicine_name.toLowerCase()))) && (
                <div className="border-l-4 border-red-600 bg-red-50 p-3 rounded text-sm flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 text-red-600 mt-0.5" />
                  <div className="text-red-800">Possible drug allergy match — please verify before administering.</div>
                </div>
              )}
              <div>
                <Label>Status *</Label>
                <Select value={administerForm.status} onValueChange={v => setAdministerForm(p => ({ ...p, status: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="given">Given</SelectItem>
                    <SelectItem value="missed">Missed</SelectItem>
                    <SelectItem value="refused">Refused by patient</SelectItem>
                    <SelectItem value="held">Held (clinical decision)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {administerForm.status === 'given' && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label>Dose Given</Label>
                      <Input value={administerForm.dose_given} onChange={e => setAdministerForm(p => ({ ...p, dose_given: e.target.value }))} placeholder="e.g. 500mg" />
                    </div>
                    <div>
                      <Label>Route</Label>
                      <Input value={administerForm.route} onChange={e => setAdministerForm(p => ({ ...p, route: e.target.value }))} placeholder="oral / iv / im..." />
                    </div>
                  </div>
                  <div>
                    <Label>Site (for injections)</Label>
                    <Input value={administerForm.site} onChange={e => setAdministerForm(p => ({ ...p, site: e.target.value }))} placeholder="e.g. Left deltoid" />
                  </div>
                </>
              )}
              {administerForm.status !== 'given' && (
                <div>
                  <Label>Reason *</Label>
                  <Textarea value={administerForm.reason_if_not_given} onChange={e => setAdministerForm(p => ({ ...p, reason_if_not_given: e.target.value }))} rows={2} required placeholder="Why was the dose not given?" />
                </div>
              )}
              <div>
                <Label>Notes</Label>
                <Textarea value={administerForm.notes} onChange={e => setAdministerForm(p => ({ ...p, notes: e.target.value }))} rows={2} />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading ? 'Saving…' : 'Save'}
              </Button>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* PRN Dose Dialog */}
      <Dialog open={showPrnDialog} onOpenChange={setShowPrnDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Record PRN (As-Needed) Dose</DialogTitle></DialogHeader>
          <form onSubmit={handleRecordPRN} className="space-y-3">
            <div>
              <Label>Medication *</Label>
              <Select value={prnForm.prescription_item_id} onValueChange={v => setPrnForm(p => ({ ...p, prescription_item_id: v }))}>
                <SelectTrigger><SelectValue placeholder="Pick a prescribed medication" /></SelectTrigger>
                <SelectContent>
                  {admissionMedications.flatMap(rx => (rx.medicines || []).filter(m => m.id).map(m => (
                    <SelectItem key={m.id} value={String(m.id)}>{m.name} — {m.dosage || 'PRN'}</SelectItem>
                  )))}
                </SelectContent>
              </Select>
              <p className="text-xs text-gray-500 mt-1">PRN medication must be on the patient's prescription list.</p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Dose Given *</Label>
                <Input value={prnForm.dose_given} onChange={e => setPrnForm(p => ({ ...p, dose_given: e.target.value }))} required placeholder="e.g. 500mg" />
              </div>
              <div>
                <Label>Route</Label>
                <Input value={prnForm.route} onChange={e => setPrnForm(p => ({ ...p, route: e.target.value }))} placeholder="oral / iv / im..." />
              </div>
            </div>
            <div>
              <Label>Indication *</Label>
              <Input value={prnForm.prn_indication} onChange={e => setPrnForm(p => ({ ...p, prn_indication: e.target.value }))} required placeholder="e.g. Pain, fever, anxiety" />
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea value={prnForm.notes} onChange={e => setPrnForm(p => ({ ...p, notes: e.target.value }))} rows={2} />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? 'Saving…' : 'Record PRN Dose'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* I/O Dialog */}
      <Dialog open={showIoDialog} onOpenChange={setShowIoDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Record Intake / Output</DialogTitle></DialogHeader>
          <form onSubmit={handleRecordIO} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Type *</Label>
                <Select value={ioForm.io_type} onValueChange={v => {
                  const firstCat = v === 'intake' ? 'oral' : 'urine';
                  setIoForm(p => ({ ...p, io_type: v, category: firstCat }));
                }}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="intake">Intake</SelectItem>
                    <SelectItem value="output">Output</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Shift *</Label>
                <Select value={ioForm.shift} onValueChange={v => setIoForm(p => ({ ...p, shift: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="morning">Morning</SelectItem>
                    <SelectItem value="afternoon">Afternoon</SelectItem>
                    <SelectItem value="night">Night</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>Category *</Label>
              <Select value={ioForm.category} onValueChange={v => setIoForm(p => ({ ...p, category: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ioForm.io_type === 'intake' ? (
                    <>
                      <SelectItem value="oral">Oral</SelectItem>
                      <SelectItem value="iv">IV</SelectItem>
                      <SelectItem value="ng_tube">NG Tube</SelectItem>
                      <SelectItem value="blood_product">Blood Product</SelectItem>
                      <SelectItem value="irrigation">Irrigation</SelectItem>
                      <SelectItem value="other">Other</SelectItem>
                    </>
                  ) : (
                    <>
                      <SelectItem value="urine">Urine</SelectItem>
                      <SelectItem value="drain">Drain</SelectItem>
                      <SelectItem value="ng_aspirate">NG Aspirate</SelectItem>
                      <SelectItem value="vomitus">Vomitus</SelectItem>
                      <SelectItem value="stool">Stool</SelectItem>
                      <SelectItem value="blood_loss">Blood Loss</SelectItem>
                      <SelectItem value="other">Other</SelectItem>
                    </>
                  )}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Amount (ml) *</Label>
              <Input type="number" step="0.1" min="0.1" value={ioForm.amount_ml} onChange={e => setIoForm(p => ({ ...p, amount_ml: e.target.value }))} required />
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea value={ioForm.notes} onChange={e => setIoForm(p => ({ ...p, notes: e.target.value }))} rows={2} />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Record'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Deposit Dialog */}
      <Dialog open={showDepositDialog} onOpenChange={setShowDepositDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Receive Advance Deposit</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateDeposit} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Amount (₹) *</Label>
                <Input type="number" step="0.01" min="0.01" value={depositForm.amount} onChange={e => setDepositForm(p => ({ ...p, amount: e.target.value }))} required />
              </div>
              <div>
                <Label>Type</Label>
                <Select value={depositForm.deposit_type} onValueChange={v => setDepositForm(p => ({ ...p, deposit_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="initial">Initial</SelectItem>
                    <SelectItem value="topup">Top-up</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Payment Method</Label>
                <Select value={depositForm.payment_method} onValueChange={v => setDepositForm(p => ({ ...p, payment_method: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="card">Card</SelectItem>
                    <SelectItem value="upi">UPI</SelectItem>
                    <SelectItem value="cheque">Cheque</SelectItem>
                    <SelectItem value="online">Online</SelectItem>
                    <SelectItem value="bank_transfer">Bank Transfer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Reference #</Label>
                <Input value={depositForm.reference_number} onChange={e => setDepositForm(p => ({ ...p, reference_number: e.target.value }))} placeholder="Txn ref / cheque #" />
              </div>
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea value={depositForm.notes} onChange={e => setDepositForm(p => ({ ...p, notes: e.target.value }))} rows={2} />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Record Deposit'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Refund Dialog */}
      <Dialog open={showRefundDialog} onOpenChange={setShowRefundDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Issue Refund</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateRefund} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Amount (₹) *</Label>
                <Input type="number" step="0.01" min="0.01" value={refundForm.amount} onChange={e => setRefundForm(p => ({ ...p, amount: e.target.value }))} required />
              </div>
              <div>
                <Label>Method</Label>
                <Select value={refundForm.payment_method} onValueChange={v => setRefundForm(p => ({ ...p, payment_method: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="card">Card</SelectItem>
                    <SelectItem value="upi">UPI</SelectItem>
                    <SelectItem value="cheque">Cheque</SelectItem>
                    <SelectItem value="online">Online</SelectItem>
                    <SelectItem value="bank_transfer">Bank Transfer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>Reference #</Label>
              <Input value={refundForm.reference_number} onChange={e => setRefundForm(p => ({ ...p, reference_number: e.target.value }))} />
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea value={refundForm.notes} onChange={e => setRefundForm(p => ({ ...p, notes: e.target.value }))} rows={2} />
            </div>
            <p className="text-xs text-gray-500">Refund cannot exceed current credit balance.</p>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Issue Refund'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Ancillary Charge Dialog */}
      <Dialog open={showAncillaryDialog} onOpenChange={setShowAncillaryDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Add Ancillary Service Charge</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateAncillaryCharge} className="space-y-3">
            <div>
              <Label>Service *</Label>
              <Select value={ancillaryForm.service_id} onValueChange={v => {
                const svc = ancillaryServices.find(s => String(s.id) === v);
                setAncillaryForm(p => ({ ...p, service_id: v, unit_price: svc ? String(svc.default_charge) : '' }));
              }}>
                <SelectTrigger><SelectValue placeholder="Select service" /></SelectTrigger>
                <SelectContent>
                  {ancillaryServices.map(s => (
                    <SelectItem key={s.id} value={String(s.id)}>{s.service_name} ({s.category}) — ₹{s.default_charge}/{s.charge_unit.replace('per_', '')}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {ancillaryServices.length === 0 && <p className="text-xs text-gray-500 mt-1">No services in catalog. Add them under Billing Setup.</p>}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Quantity *</Label>
                <Input type="number" step="0.01" min="0.01" value={ancillaryForm.quantity} onChange={e => setAncillaryForm(p => ({ ...p, quantity: e.target.value }))} required />
              </div>
              <div>
                <Label>Unit Price (₹)</Label>
                <Input type="number" step="0.01" value={ancillaryForm.unit_price} onChange={e => setAncillaryForm(p => ({ ...p, unit_price: e.target.value }))} placeholder="Catalog default" />
              </div>
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea value={ancillaryForm.notes} onChange={e => setAncillaryForm(p => ({ ...p, notes: e.target.value }))} rows={2} />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Add Charge'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Apply Package Dialog */}
      <Dialog open={showApplyPackageDialog} onOpenChange={setShowApplyPackageDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Apply Surgery Package</DialogTitle></DialogHeader>
          <form onSubmit={handleApplyPackage} className="space-y-3">
            <div>
              <Label>Package *</Label>
              <Select value={applyPackageForm.package_id} onValueChange={v => {
                const pkg = packagesList.find(p => String(p.id) === v);
                setApplyPackageForm(p => ({ ...p, package_id: v, agreed_price: pkg ? String(pkg.base_price) : '' }));
              }}>
                <SelectTrigger><SelectValue placeholder="Select package" /></SelectTrigger>
                <SelectContent>
                  {packagesList.map(p => (
                    <SelectItem key={p.id} value={String(p.id)}>{p.package_name} — ₹{p.base_price} · {p.included_stay_days} days</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {packagesList.length === 0 && <p className="text-xs text-gray-500 mt-1">No packages configured. Add them under Billing Setup.</p>}
            </div>
            <div>
              <Label>Agreed Price (₹)</Label>
              <Input type="number" step="0.01" value={applyPackageForm.agreed_price} onChange={e => setApplyPackageForm(p => ({ ...p, agreed_price: e.target.value }))} placeholder="Defaults to package base price" />
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea value={applyPackageForm.notes} onChange={e => setApplyPackageForm(p => ({ ...p, notes: e.target.value }))} rows={2} />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Apply Package'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Bill Split Dialog */}
      <Dialog open={showSplitDialog} onOpenChange={setShowSplitDialog}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>Split Bill — {billForSplit?.bill_number}</DialogTitle></DialogHeader>
          {billForSplit && (
            <form onSubmit={handleSubmitSplit} className="space-y-3">
              <p className="text-sm text-gray-600">Bill total: <b>₹{billForSplit.total_amount.toFixed(2)}</b>. Split must sum to the total.</p>
              <div className="space-y-2">
                {splitRows.map((r, i) => (
                  <div key={i} className="grid grid-cols-12 gap-2 items-end">
                    <div className="col-span-3">
                      {i === 0 && <Label className="text-xs">Payer Type</Label>}
                      <Select value={r.payer_type} onValueChange={v => setSplitRows(rows => rows.map((x, j) => j === i ? { ...x, payer_type: v } : x))}>
                        <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="cash">Cash</SelectItem>
                          <SelectItem value="insurance">Insurance</SelectItem>
                          <SelectItem value="tpa">TPA</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="col-span-4">
                      {i === 0 && <Label className="text-xs">Payer Name</Label>}
                      <Input value={r.payer_name} onChange={e => setSplitRows(rows => rows.map((x, j) => j === i ? { ...x, payer_name: e.target.value } : x))} />
                    </div>
                    <div className="col-span-3">
                      {i === 0 && <Label className="text-xs">TPA (if any)</Label>}
                      <Select value={r.tpa_id ? String(r.tpa_id) : ''} onValueChange={v => setSplitRows(rows => rows.map((x, j) => j === i ? { ...x, tpa_id: v } : x))} disabled={r.payer_type !== 'tpa'}>
                        <SelectTrigger className="h-9"><SelectValue placeholder="–" /></SelectTrigger>
                        <SelectContent>
                          {tpaList.map(t => <SelectItem key={t.id} value={String(t.id)}>{t.tpa_name}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="col-span-1">
                      {i === 0 && <Label className="text-xs">Amount</Label>}
                      <Input type="number" step="0.01" value={r.amount} onChange={e => setSplitRows(rows => rows.map((x, j) => j === i ? { ...x, amount: e.target.value } : x))} />
                    </div>
                    <div className="col-span-1">
                      <Button type="button" variant="ghost" size="sm" onClick={() => setSplitRows(rows => rows.filter((_, j) => j !== i))}>
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex justify-between">
                <Button type="button" variant="outline" size="sm" onClick={() => setSplitRows(rows => [...rows, { payer_type: 'insurance', payer_name: '', tpa_id: '', amount: 0 }])}>
                  <Plus className="h-3.5 w-3.5 mr-1" /> Add Split
                </Button>
                <div className="text-sm">
                  Sum: <b>₹{splitRows.reduce((s, r) => s + (parseFloat(r.amount) || 0), 0).toFixed(2)}</b> / ₹{billForSplit.total_amount.toFixed(2)}
                </div>
              </div>
              <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Save Split'}</Button>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* Pre-auth Create Dialog */}
      <Dialog open={showPreauthDialog} onOpenChange={(open) => { setShowPreauthDialog(open); if (!open) { setPreauthSelectedPatient(null); setPreauthPatientSearch(''); } }}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>New Pre-Authorisation Request</DialogTitle></DialogHeader>
          <form onSubmit={handleCreatePreauth} className="space-y-3">
            <div>
              <Label>Patient *</Label>
              {preauthSelectedPatient ? (
                <div className="flex justify-between items-center p-2 border rounded text-sm">
                  <span>{preauthSelectedPatient.first_name} {preauthSelectedPatient.last_name} ({preauthSelectedPatient.patient_id?.slice(0, 8)}…)</span>
                  <Button type="button" variant="ghost" size="sm" onClick={() => { setPreauthSelectedPatient(null); setPreauthPatientSearch(''); }}><X className="h-4 w-4" /></Button>
                </div>
              ) : (
                <>
                  <Input value={preauthPatientSearch} onChange={e => setPreauthPatientSearch(e.target.value)} placeholder="Search by name or phone..." />
                  {preauthPatientResults.length > 0 && (
                    <div className="border rounded max-h-40 overflow-y-auto mt-1">
                      {preauthPatientResults.slice(0, 10).map(p => (
                        <div key={p.id} className="p-2 hover:bg-gray-50 cursor-pointer text-sm" onClick={() => { setPreauthSelectedPatient(p); setPreauthPatientSearch(''); setPreauthPatientResults([]); }}>
                          {p.first_name} {p.last_name} — {p.primary_phone}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Insurance Provider *</Label>
                <Input value={preauthForm.insurance_provider} onChange={e => setPreauthForm(p => ({ ...p, insurance_provider: e.target.value }))} required placeholder="e.g. Star Health" />
              </div>
              <div>
                <Label>Policy Number</Label>
                <Input value={preauthForm.policy_number} onChange={e => setPreauthForm(p => ({ ...p, policy_number: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>TPA</Label>
                <Select value={preauthForm.tpa_id} onValueChange={v => setPreauthForm(p => ({ ...p, tpa_id: v }))}>
                  <SelectTrigger><SelectValue placeholder="None" /></SelectTrigger>
                  <SelectContent>
                    {tpaList.map(t => <SelectItem key={t.id} value={String(t.id)}>{t.tpa_name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Requested Amount (₹) *</Label>
                <Input type="number" step="0.01" min="0.01" value={preauthForm.requested_amount} onChange={e => setPreauthForm(p => ({ ...p, requested_amount: e.target.value }))} required />
              </div>
            </div>
            <div>
              <Label>Admission (if any)</Label>
              <Input value={preauthForm.admission_id} onChange={e => setPreauthForm(p => ({ ...p, admission_id: e.target.value }))} placeholder="Admission ID (numeric)" />
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea value={preauthForm.notes} onChange={e => setPreauthForm(p => ({ ...p, notes: e.target.value }))} rows={2} />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Submit Request'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Pre-auth Decision Dialog */}
      <Dialog open={showPreauthDecisionDialog} onOpenChange={setShowPreauthDecisionDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Record Insurer Decision</DialogTitle></DialogHeader>
          {activePreauth && (
            <form onSubmit={handlePreauthDecision} className="space-y-3">
              <p className="text-sm">{activePreauth.insurance_provider} · Requested ₹{activePreauth.requested_amount.toFixed(2)}</p>
              <div>
                <Label>Decision *</Label>
                <Select value={preauthDecisionForm.status} onValueChange={v => setPreauthDecisionForm(p => ({ ...p, status: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="approved">Approved</SelectItem>
                    <SelectItem value="rejected">Rejected</SelectItem>
                    <SelectItem value="expired">Expired</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {preauthDecisionForm.status === 'approved' && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label>Approved Amount (₹) *</Label>
                      <Input type="number" step="0.01" value={preauthDecisionForm.approved_amount} onChange={e => setPreauthDecisionForm(p => ({ ...p, approved_amount: e.target.value }))} required />
                    </div>
                    <div>
                      <Label>Validity (days)</Label>
                      <Input type="number" value={preauthDecisionForm.validity_days} onChange={e => setPreauthDecisionForm(p => ({ ...p, validity_days: e.target.value }))} />
                    </div>
                  </div>
                  <div>
                    <Label>Approval Reference</Label>
                    <Input value={preauthDecisionForm.approval_reference} onChange={e => setPreauthDecisionForm(p => ({ ...p, approval_reference: e.target.value }))} />
                  </div>
                </>
              )}
              <div>
                <Label>Notes</Label>
                <Textarea value={preauthDecisionForm.notes} onChange={e => setPreauthDecisionForm(p => ({ ...p, notes: e.target.value }))} rows={2} />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Save Decision'}</Button>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* Ancillary Service Catalog Dialog */}
      <Dialog open={showServiceDialog} onOpenChange={(open) => { setShowServiceDialog(open); if (!open) setEditingService(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{editingService ? 'Edit' : 'New'} Ancillary Service</DialogTitle></DialogHeader>
          <form onSubmit={handleSubmitService} className="space-y-3">
            <div>
              <Label>Service Name *</Label>
              <Input value={serviceForm.service_name} onChange={e => setServiceForm(p => ({ ...p, service_name: e.target.value }))} required />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Code</Label>
                <Input value={serviceForm.service_code} onChange={e => setServiceForm(p => ({ ...p, service_code: e.target.value }))} />
              </div>
              <div>
                <Label>Category *</Label>
                <Select value={serviceForm.category} onValueChange={v => setServiceForm(p => ({ ...p, category: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="imaging">Imaging</SelectItem>
                    <SelectItem value="physiotherapy">Physiotherapy</SelectItem>
                    <SelectItem value="dialysis">Dialysis</SelectItem>
                    <SelectItem value="oxygen">Oxygen</SelectItem>
                    <SelectItem value="equipment">Equipment</SelectItem>
                    <SelectItem value="consumable">Consumable</SelectItem>
                    <SelectItem value="procedure">Procedure</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Default Charge (₹) *</Label>
                <Input type="number" step="0.01" value={serviceForm.default_charge} onChange={e => setServiceForm(p => ({ ...p, default_charge: e.target.value }))} required />
              </div>
              <div>
                <Label>Charge Unit</Label>
                <Select value={serviceForm.charge_unit} onValueChange={v => setServiceForm(p => ({ ...p, charge_unit: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="per_session">Per Session</SelectItem>
                    <SelectItem value="per_hour">Per Hour</SelectItem>
                    <SelectItem value="per_day">Per Day</SelectItem>
                    <SelectItem value="per_unit">Per Unit</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>Description</Label>
              <Textarea value={serviceForm.description} onChange={e => setServiceForm(p => ({ ...p, description: e.target.value }))} rows={2} />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Save Service'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Package Dialog */}
      <Dialog open={showPackageDialog} onOpenChange={(open) => { setShowPackageDialog(open); if (!open) setEditingPackage(null); }}>
        <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editingPackage ? 'Edit' : 'New'} Surgery Package</DialogTitle></DialogHeader>
          <form onSubmit={handleSubmitPackage} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Package Name *</Label>
                <Input value={packageForm.package_name} onChange={e => setPackageForm(p => ({ ...p, package_name: e.target.value }))} required />
              </div>
              <div>
                <Label>Code</Label>
                <Input value={packageForm.package_code} onChange={e => setPackageForm(p => ({ ...p, package_code: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Base Price (₹) *</Label>
                <Input type="number" step="0.01" value={packageForm.base_price} onChange={e => setPackageForm(p => ({ ...p, base_price: e.target.value }))} required />
              </div>
              <div>
                <Label>Included Room Type</Label>
                <Select value={packageForm.included_room_type} onValueChange={v => setPackageForm(p => ({ ...p, included_room_type: v }))}>
                  <SelectTrigger><SelectValue placeholder="Any" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="general">General</SelectItem>
                    <SelectItem value="private">Private</SelectItem>
                    <SelectItem value="icu">ICU</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Included Stay Days</Label>
                <Input type="number" min="0" value={packageForm.included_stay_days} onChange={e => setPackageForm(p => ({ ...p, included_stay_days: e.target.value }))} />
              </div>
              <div>
                <Label>Excess/day (₹)</Label>
                <Input type="number" step="0.01" value={packageForm.excess_per_day_charge} onChange={e => setPackageForm(p => ({ ...p, excess_per_day_charge: e.target.value }))} />
              </div>
            </div>
            <div>
              <Label>Included Services</Label>
              <div className="grid grid-cols-2 gap-1 text-xs">
                {['room', 'doctor_visit', 'nurse_visit', 'procedure', 'ot', 'pharmacy', 'lab', 'ancillary'].map(s => (
                  <label key={s} className="flex items-center gap-1">
                    <input type="checkbox" checked={(packageForm.included_services || []).includes(s)} onChange={e => {
                      setPackageForm(p => ({ ...p, included_services: e.target.checked ? [...(p.included_services || []), s] : (p.included_services || []).filter(x => x !== s) }));
                    }} />
                    {s.replace('_', ' ')}
                  </label>
                ))}
              </div>
            </div>
            <div>
              <Label>Description</Label>
              <Textarea value={packageForm.description} onChange={e => setPackageForm(p => ({ ...p, description: e.target.value }))} rows={2} />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Save Package'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Consent Dialog */}
      <Dialog open={showConsentDialog} onOpenChange={setShowConsentDialog}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Record Consent</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateConsent} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Type *</Label>
                <Select value={consentForm.consent_type} onValueChange={v => setConsentForm(p => ({ ...p, consent_type: v, template_id: '' }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="surgical">Surgical</SelectItem>
                    <SelectItem value="anaesthesia">Anaesthesia</SelectItem>
                    <SelectItem value="blood_transfusion">Blood Transfusion</SelectItem>
                    <SelectItem value="high_risk_procedure">High-risk Procedure</SelectItem>
                    <SelectItem value="general_treatment">General Treatment</SelectItem>
                    <SelectItem value="research">Research</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Template</Label>
                <Select value={consentForm.template_id || 'none'} onValueChange={v => setConsentForm(p => ({ ...p, template_id: v === 'none' ? '' : v }))}>
                  <SelectTrigger><SelectValue placeholder="No template" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No template</SelectItem>
                    {consentTemplates.filter(t => t.consent_type === consentForm.consent_type).map(t => (
                      <SelectItem key={t.id} value={String(t.id)}>{t.template_name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>Procedure Name</Label>
              <Input value={consentForm.procedure_name} onChange={e => setConsentForm(p => ({ ...p, procedure_name: e.target.value }))} placeholder="e.g. Cataract surgery (OD)" />
            </div>
            <div>
              <Label>Treating Doctor</Label>
              <Select value={consentForm.doctor_id || 'none'} onValueChange={v => setConsentForm(p => ({ ...p, doctor_id: v === 'none' ? '' : v }))}>
                <SelectTrigger><SelectValue placeholder="Optional" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">—</SelectItem>
                  {doctorsList.map(d => <SelectItem key={d.id} value={String(d.id)}>Dr. {d.first_name} {d.last_name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Risks Explained</Label>
              <Textarea value={consentForm.risks_explained} onChange={e => setConsentForm(p => ({ ...p, risks_explained: e.target.value }))} rows={3} placeholder="e.g. Infection, bleeding, anaesthesia reactions..." />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Signed By *</Label>
                <Select value={consentForm.signed_by} onValueChange={v => setConsentForm(p => ({ ...p, signed_by: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="patient">Patient</SelectItem>
                    <SelectItem value="guardian">Guardian</SelectItem>
                    <SelectItem value="proxy">Proxy</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Patient Signature (typed) *</Label>
                <Input value={consentForm.patient_signature} onChange={e => setConsentForm(p => ({ ...p, patient_signature: e.target.value }))} required placeholder="Type full name" />
              </div>
            </div>
            {consentForm.signed_by !== 'patient' && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Guardian Name *</Label>
                  <Input value={consentForm.guardian_name} onChange={e => setConsentForm(p => ({ ...p, guardian_name: e.target.value }))} required />
                </div>
                <div>
                  <Label>Relationship</Label>
                  <Input value={consentForm.guardian_relationship} onChange={e => setConsentForm(p => ({ ...p, guardian_relationship: e.target.value }))} placeholder="e.g. Father, Spouse" />
                </div>
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Witness Name</Label>
                <Input value={consentForm.witness_name} onChange={e => setConsentForm(p => ({ ...p, witness_name: e.target.value }))} />
              </div>
              <div>
                <Label>Witness Signature</Label>
                <Input value={consentForm.witness_signature} onChange={e => setConsentForm(p => ({ ...p, witness_signature: e.target.value }))} placeholder="Typed name" />
              </div>
            </div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Record Consent'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Consent Withdraw Dialog */}
      <Dialog open={showWithdrawConsentDialog} onOpenChange={setShowWithdrawConsentDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Withdraw Consent</DialogTitle></DialogHeader>
          <form onSubmit={handleWithdrawConsent} className="space-y-3">
            <p className="text-sm text-gray-600">Withdrawing this consent will mark it as no longer valid. The original record is preserved.</p>
            <div>
              <Label>Reason *</Label>
              <Textarea value={withdrawReason} onChange={e => setWithdrawReason(e.target.value)} rows={3} required />
            </div>
            <Button type="submit" className="w-full" variant="destructive" disabled={loading}>{loading ? 'Saving…' : 'Withdraw'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Consent Template Dialog */}
      <Dialog open={showConsentTemplateDialog} onOpenChange={(open) => { setShowConsentTemplateDialog(open); if (!open) setEditingConsentTemplate(null); }}>
        <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editingConsentTemplate ? 'Edit' : 'New'} Consent Template</DialogTitle></DialogHeader>
          <form onSubmit={handleSubmitConsentTemplate} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Type *</Label>
                <Select value={consentTemplateForm.consent_type} onValueChange={v => setConsentTemplateForm(p => ({ ...p, consent_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="surgical">Surgical</SelectItem>
                    <SelectItem value="anaesthesia">Anaesthesia</SelectItem>
                    <SelectItem value="blood_transfusion">Blood Transfusion</SelectItem>
                    <SelectItem value="high_risk_procedure">High-risk Procedure</SelectItem>
                    <SelectItem value="general_treatment">General Treatment</SelectItem>
                    <SelectItem value="research">Research</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Language</Label>
                <Input value={consentTemplateForm.language} onChange={e => setConsentTemplateForm(p => ({ ...p, language: e.target.value }))} />
              </div>
            </div>
            <div>
              <Label>Template Name *</Label>
              <Input value={consentTemplateForm.template_name} onChange={e => setConsentTemplateForm(p => ({ ...p, template_name: e.target.value }))} required />
            </div>
            <div>
              <Label>Content *</Label>
              <Textarea value={consentTemplateForm.content} onChange={e => setConsentTemplateForm(p => ({ ...p, content: e.target.value }))} rows={10} required placeholder="Full consent text — will appear on the printed PDF." />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Save Template'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Incident Report Dialog */}
      <Dialog open={showIncidentDialog} onOpenChange={setShowIncidentDialog}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Report Incident</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateIncident} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Type *</Label>
                <Select value={incidentForm.incident_type} onValueChange={v => setIncidentForm(p => ({ ...p, incident_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="fall">Fall</SelectItem>
                    <SelectItem value="medication_error">Medication Error</SelectItem>
                    <SelectItem value="pressure_ulcer">Pressure Ulcer</SelectItem>
                    <SelectItem value="needle_stick">Needle Stick</SelectItem>
                    <SelectItem value="infection">Infection</SelectItem>
                    <SelectItem value="equipment_failure">Equipment Failure</SelectItem>
                    <SelectItem value="documentation_error">Documentation Error</SelectItem>
                    <SelectItem value="wrong_patient">Wrong Patient</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Severity *</Label>
                <Select value={incidentForm.severity} onValueChange={v => setIncidentForm(p => ({ ...p, severity: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="low">Low</SelectItem>
                    <SelectItem value="medium">Medium</SelectItem>
                    <SelectItem value="high">High</SelectItem>
                    <SelectItem value="critical">Critical</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Date / Time *</Label>
                <Input type="datetime-local" value={incidentForm.incident_date} onChange={e => setIncidentForm(p => ({ ...p, incident_date: e.target.value }))} required />
              </div>
              <div>
                <Label>Location</Label>
                <Input value={incidentForm.location} onChange={e => setIncidentForm(p => ({ ...p, location: e.target.value }))} placeholder="e.g. Ward A, Bed 3" />
              </div>
              <div>
                <Label>Admission #</Label>
                <Input value={incidentForm.admission_id} onChange={e => setIncidentForm(p => ({ ...p, admission_id: e.target.value }))} placeholder="Optional (numeric ID)" />
              </div>
              <div>
                <Label>Witnessed By</Label>
                <Input value={incidentForm.witnessed_by} onChange={e => setIncidentForm(p => ({ ...p, witnessed_by: e.target.value }))} placeholder="Name(s)" />
              </div>
            </div>
            <div>
              <Label>Description *</Label>
              <Textarea value={incidentForm.description} onChange={e => setIncidentForm(p => ({ ...p, description: e.target.value }))} rows={4} required placeholder="What happened?" />
            </div>
            <div>
              <Label>Immediate Action</Label>
              <Textarea value={incidentForm.immediate_action} onChange={e => setIncidentForm(p => ({ ...p, immediate_action: e.target.value }))} rows={2} placeholder="Actions taken at the time" />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Submit Report'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Investigate Incident Dialog */}
      <Dialog open={showInvestigateDialog} onOpenChange={setShowInvestigateDialog}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Investigate Incident</DialogTitle></DialogHeader>
          {investigatingIncident && (
            <form onSubmit={handleInvestigateIncident} className="space-y-3">
              <div className="bg-gray-50 p-3 rounded text-sm">
                <div><b>{investigatingIncident.incident_type.replace(/_/g, ' ')}</b> ({investigatingIncident.severity}) · currently <b>{investigatingIncident.status}</b></div>
                <p className="text-xs text-gray-600 mt-1">{investigatingIncident.description}</p>
              </div>
              <div>
                <Label>Change status to</Label>
                <Select value={investigateForm.new_status || 'none'} onValueChange={v => setInvestigateForm(p => ({ ...p, new_status: v === 'none' ? '' : v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">(keep current)</SelectItem>
                    <SelectItem value="investigating">Investigating</SelectItem>
                    <SelectItem value="resolved">Resolved</SelectItem>
                    <SelectItem value="closed">Closed</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Investigation Notes</Label>
                <Textarea value={investigateForm.investigation_notes} onChange={e => setInvestigateForm(p => ({ ...p, investigation_notes: e.target.value }))} rows={3} />
              </div>
              <div>
                <Label>Root Cause</Label>
                <Textarea value={investigateForm.root_cause} onChange={e => setInvestigateForm(p => ({ ...p, root_cause: e.target.value }))} rows={2} />
              </div>
              <div>
                <Label>Resolution</Label>
                <Textarea value={investigateForm.resolution} onChange={e => setInvestigateForm(p => ({ ...p, resolution: e.target.value }))} rows={2} />
              </div>
              <div>
                <Label>Corrective Actions</Label>
                <Textarea value={investigateForm.corrective_actions} onChange={e => setInvestigateForm(p => ({ ...p, corrective_actions: e.target.value }))} rows={2} />
              </div>
              <div>
                <Label>Preventive Measures</Label>
                <Textarea value={investigateForm.preventive_measures} onChange={e => setInvestigateForm(p => ({ ...p, preventive_measures: e.target.value }))} rows={2} />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Update Investigation'}</Button>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* Mortality Details Dialog */}
      <Dialog open={showMortalityDialog} onOpenChange={setShowMortalityDialog}>
        <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Mortality Details</DialogTitle></DialogHeader>
          <form onSubmit={handleSaveMortality} className="space-y-3">
            <div>
              <Label>Cause of Death *</Label>
              <Textarea value={mortalityForm.cause_of_death} onChange={e => setMortalityForm(p => ({ ...p, cause_of_death: e.target.value }))} rows={3} required />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Time of Death</Label>
                <Input type="datetime-local" value={mortalityForm.time_of_death} onChange={e => setMortalityForm(p => ({ ...p, time_of_death: e.target.value }))} />
              </div>
              <div>
                <Label>Certificate #</Label>
                <Input value={mortalityForm.death_certificate_number} onChange={e => setMortalityForm(p => ({ ...p, death_certificate_number: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={mortalityForm.mlc_required} onChange={e => setMortalityForm(p => ({ ...p, mlc_required: e.target.checked }))} />
                <span className="text-sm">MLC Required</span>
              </label>
              {mortalityForm.mlc_required && (
                <div>
                  <Label className="text-xs">MLC Number</Label>
                  <Input value={mortalityForm.mlc_number} onChange={e => setMortalityForm(p => ({ ...p, mlc_number: e.target.value }))} />
                </div>
              )}
            </div>
            <div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={mortalityForm.autopsy_done} onChange={e => setMortalityForm(p => ({ ...p, autopsy_done: e.target.checked }))} />
                <span className="text-sm">Autopsy Done</span>
              </label>
              {mortalityForm.autopsy_done && (
                <Textarea className="mt-2" value={mortalityForm.autopsy_findings} onChange={e => setMortalityForm(p => ({ ...p, autopsy_findings: e.target.value }))} rows={2} placeholder="Autopsy findings..." />
              )}
            </div>
            <hr />
            <h4 className="text-sm font-semibold">Body Handover</h4>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Handed over to</Label>
                <Input value={mortalityForm.body_handed_over_to} onChange={e => setMortalityForm(p => ({ ...p, body_handed_over_to: e.target.value }))} />
              </div>
              <div>
                <Label>Relationship</Label>
                <Input value={mortalityForm.body_handover_relationship} onChange={e => setMortalityForm(p => ({ ...p, body_handover_relationship: e.target.value }))} placeholder="e.g. Son, Spouse" />
              </div>
              <div>
                <Label>Date / Time</Label>
                <Input type="datetime-local" value={mortalityForm.body_handover_time} onChange={e => setMortalityForm(p => ({ ...p, body_handover_time: e.target.value }))} />
              </div>
              <div>
                <Label>ID Proof</Label>
                <Input value={mortalityForm.body_handover_id_proof} onChange={e => setMortalityForm(p => ({ ...p, body_handover_id_proof: e.target.value }))} placeholder="e.g. Aadhaar XXXX-XXXX-1234" />
              </div>
            </div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Save Mortality Details'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* B6 — Body Release / Mortuary Tracking */}
      <Dialog open={showBodyReleaseDialog} onOpenChange={setShowBodyReleaseDialog}>
        <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Body Release & Mortuary Tracking</DialogTitle>
            {bodyReleaseRec?.body_released && (
              <Badge className="bg-green-100 text-green-800 w-fit">
                Released on {bodyReleaseRec.body_released_at && new Date(bodyReleaseRec.body_released_at).toLocaleString()}
              </Badge>
            )}
          </DialogHeader>

          <div className="space-y-5">
            {/* Section 1 — Mortuary */}
            <div className="border rounded p-3 space-y-3">
              <h4 className="font-semibold text-sm">Mortuary</h4>
              <div className="grid grid-cols-3 gap-3">
                <div><Label className="text-xs">Mortuary Slot</Label>
                  <Input value={bodyReleaseTrack.mortuary_slot} placeholder="e.g. M-3"
                    onChange={e => setBodyReleaseTrack(p => ({ ...p, mortuary_slot: e.target.value }))} className="h-9" /></div>
                <div><Label className="text-xs">Body In</Label>
                  <Input type="datetime-local" value={bodyReleaseTrack.body_in_mortuary_at}
                    onChange={e => setBodyReleaseTrack(p => ({ ...p, body_in_mortuary_at: e.target.value }))} className="h-9" /></div>
                <div><Label className="text-xs">Body Out</Label>
                  <Input type="datetime-local" value={bodyReleaseTrack.body_out_mortuary_at}
                    onChange={e => setBodyReleaseTrack(p => ({ ...p, body_out_mortuary_at: e.target.value }))} className="h-9" /></div>
              </div>
            </div>

            {/* Section 2 — Embalming */}
            <div className="border rounded p-3 space-y-3">
              <label className="flex items-center gap-2 text-sm font-semibold">
                <input type="checkbox" checked={bodyReleaseTrack.embalming_done}
                  onChange={e => setBodyReleaseTrack(p => ({ ...p, embalming_done: e.target.checked }))} />
                Embalming done
              </label>
              {bodyReleaseTrack.embalming_done && (
                <div className="grid grid-cols-2 gap-3">
                  <div><Label className="text-xs">Embalmed By</Label>
                    <Input value={bodyReleaseTrack.embalmed_by}
                      onChange={e => setBodyReleaseTrack(p => ({ ...p, embalmed_by: e.target.value }))} className="h-9" /></div>
                  <div><Label className="text-xs">Embalming At</Label>
                    <Input type="datetime-local" value={bodyReleaseTrack.embalming_at}
                      onChange={e => setBodyReleaseTrack(p => ({ ...p, embalming_at: e.target.value }))} className="h-9" /></div>
                </div>
              )}
            </div>

            {/* Section 3 — Post-mortem */}
            <div className="border rounded p-3 space-y-3">
              <label className="flex items-center gap-2 text-sm font-semibold">
                <input type="checkbox" checked={bodyReleaseTrack.post_mortem_required}
                  onChange={e => setBodyReleaseTrack(p => ({ ...p, post_mortem_required: e.target.checked }))} />
                Post-mortem required
              </label>
              {bodyReleaseTrack.post_mortem_required && (
                <div className="grid grid-cols-2 gap-3">
                  <div><Label className="text-xs">PM Hospital</Label>
                    <Input value={bodyReleaseTrack.pm_hospital}
                      onChange={e => setBodyReleaseTrack(p => ({ ...p, pm_hospital: e.target.value }))} className="h-9" /></div>
                  <div><Label className="text-xs">PM Doctor</Label>
                    <Input value={bodyReleaseTrack.pm_doctor}
                      onChange={e => setBodyReleaseTrack(p => ({ ...p, pm_doctor: e.target.value }))} className="h-9" /></div>
                  <div><Label className="text-xs">Referred At</Label>
                    <Input type="datetime-local" value={bodyReleaseTrack.pm_referred_at}
                      onChange={e => setBodyReleaseTrack(p => ({ ...p, pm_referred_at: e.target.value }))} className="h-9" /></div>
                  <div><Label className="text-xs">PM Completed At</Label>
                    <Input type="datetime-local" value={bodyReleaseTrack.pm_completed_at}
                      onChange={e => setBodyReleaseTrack(p => ({ ...p, pm_completed_at: e.target.value }))} className="h-9" /></div>
                  <div className="col-span-2 flex items-center gap-3">
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={bodyReleaseTrack.pm_report_received}
                        onChange={e => setBodyReleaseTrack(p => ({ ...p, pm_report_received: e.target.checked }))} />
                      PM report received
                    </label>
                    {bodyReleaseTrack.pm_report_received && (
                      <Input value={bodyReleaseTrack.pm_report_number} placeholder="PM report no."
                        onChange={e => setBodyReleaseTrack(p => ({ ...p, pm_report_number: e.target.value }))} className="h-9 max-w-xs" />
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Section 4 — Police NOC */}
            <div className="border rounded p-3 space-y-3">
              <div className="flex items-center justify-between">
                <label className="flex items-center gap-2 text-sm font-semibold">
                  <input type="checkbox" checked={bodyReleaseTrack.police_noc_required}
                    onChange={e => setBodyReleaseTrack(p => ({ ...p, police_noc_required: e.target.checked }))} />
                  Police NOC required (auto-set for MLC)
                </label>
                {bodyReleaseTrack.police_noc_required && bodyReleaseTrack.police_noc_received && (
                  <Badge className="bg-green-100 text-green-800 text-[10px]">NOC received</Badge>
                )}
              </div>
              {bodyReleaseTrack.police_noc_required && (
                <div className="grid grid-cols-3 gap-3">
                  <label className="flex items-center gap-2 text-sm pt-5">
                    <input type="checkbox" checked={bodyReleaseTrack.police_noc_received}
                      onChange={e => setBodyReleaseTrack(p => ({ ...p, police_noc_received: e.target.checked }))} />
                    Received
                  </label>
                  <div><Label className="text-xs">NOC Number</Label>
                    <Input value={bodyReleaseTrack.police_noc_number}
                      onChange={e => setBodyReleaseTrack(p => ({ ...p, police_noc_number: e.target.value }))} className="h-9" /></div>
                  <div><Label className="text-xs">Received At</Label>
                    <Input type="datetime-local" value={bodyReleaseTrack.police_noc_received_at}
                      onChange={e => setBodyReleaseTrack(p => ({ ...p, police_noc_received_at: e.target.value }))} className="h-9" /></div>
                </div>
              )}
            </div>

            {!bodyReleaseRec?.body_released && (
              <div className="flex justify-end">
                <Button size="sm" variant="outline" onClick={saveBodyReleaseTracking}>Save tracking</Button>
              </div>
            )}

            {/* Section 5 — Final release */}
            <div className={`border-2 rounded p-3 space-y-3 ${bodyReleaseRec?.body_released ? 'border-green-300 bg-green-50' : 'border-amber-300 bg-amber-50'}`}>
              <h4 className="font-semibold text-sm">Final release to family</h4>
              <div className="grid grid-cols-2 gap-3">
                <div><Label className="text-xs">Releasee Name *</Label>
                  <Input value={bodyReleaseAction.released_to_name} disabled={bodyReleaseRec?.body_released}
                    onChange={e => setBodyReleaseAction(p => ({ ...p, released_to_name: e.target.value }))} className="h-9" /></div>
                <div><Label className="text-xs">Relationship *</Label>
                  <Input value={bodyReleaseAction.released_to_relationship} disabled={bodyReleaseRec?.body_released} placeholder="son, wife, brother…"
                    onChange={e => setBodyReleaseAction(p => ({ ...p, released_to_relationship: e.target.value }))} className="h-9" /></div>
                <div><Label className="text-xs">Phone</Label>
                  <Input value={bodyReleaseAction.released_to_phone} disabled={bodyReleaseRec?.body_released}
                    onChange={e => setBodyReleaseAction(p => ({ ...p, released_to_phone: e.target.value }))} className="h-9" /></div>
                <div className="grid grid-cols-2 gap-2">
                  <div><Label className="text-xs">ID Type *</Label>
                    <Select value={bodyReleaseAction.released_to_id_proof_type} disabled={bodyReleaseRec?.body_released}
                      onValueChange={v => setBodyReleaseAction(p => ({ ...p, released_to_id_proof_type: v }))}>
                      <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="aadhar">Aadhaar</SelectItem>
                        <SelectItem value="voter">Voter ID</SelectItem>
                        <SelectItem value="license">Driving License</SelectItem>
                        <SelectItem value="passport">Passport</SelectItem>
                        <SelectItem value="other">Other</SelectItem>
                      </SelectContent>
                    </Select></div>
                  <div><Label className="text-xs">ID Number *</Label>
                    <Input value={bodyReleaseAction.released_to_id_proof_number} disabled={bodyReleaseRec?.body_released}
                      onChange={e => setBodyReleaseAction(p => ({ ...p, released_to_id_proof_number: e.target.value }))} className="h-9" /></div>
                </div>
              </div>
              <div><Label className="text-xs">Address</Label>
                <Textarea value={bodyReleaseAction.released_to_address} disabled={bodyReleaseRec?.body_released}
                  onChange={e => setBodyReleaseAction(p => ({ ...p, released_to_address: e.target.value }))} rows={2} /></div>
              <div className="grid grid-cols-3 gap-3">
                <div><Label className="text-xs">Witness Name *</Label>
                  <Input value={bodyReleaseAction.witness_name} disabled={bodyReleaseRec?.body_released}
                    onChange={e => setBodyReleaseAction(p => ({ ...p, witness_name: e.target.value }))} className="h-9" /></div>
                <div><Label className="text-xs">Witness Phone</Label>
                  <Input value={bodyReleaseAction.witness_phone} disabled={bodyReleaseRec?.body_released}
                    onChange={e => setBodyReleaseAction(p => ({ ...p, witness_phone: e.target.value }))} className="h-9" /></div>
                <div><Label className="text-xs">Witness ID</Label>
                  <Input value={bodyReleaseAction.witness_id_proof} disabled={bodyReleaseRec?.body_released}
                    onChange={e => setBodyReleaseAction(p => ({ ...p, witness_id_proof: e.target.value }))} className="h-9" /></div>
              </div>
              <div><Label className="text-xs">Transport Details</Label>
                <Input value={bodyReleaseAction.transport_details} disabled={bodyReleaseRec?.body_released}
                  placeholder="Vehicle no., ambulance, hearse"
                  onChange={e => setBodyReleaseAction(p => ({ ...p, transport_details: e.target.value }))} className="h-9" /></div>

              {!bodyReleaseRec?.body_released && (
                <>
                  {(bodyReleaseTrack.police_noc_required && !bodyReleaseTrack.police_noc_received) && (
                    <label className="flex items-center gap-2 text-xs text-red-700">
                      <input type="checkbox" checked={bodyReleaseAction.force_missing_noc}
                        onChange={e => setBodyReleaseAction(p => ({ ...p, force_missing_noc: e.target.checked }))} />
                      Force release without police NOC (audit-logged)
                    </label>
                  )}
                  {(bodyReleaseTrack.post_mortem_required && !bodyReleaseTrack.pm_completed_at) && (
                    <label className="flex items-center gap-2 text-xs text-red-700">
                      <input type="checkbox" checked={bodyReleaseAction.force_missing_pm}
                        onChange={e => setBodyReleaseAction(p => ({ ...p, force_missing_pm: e.target.checked }))} />
                      Force release without completed post-mortem (audit-logged)
                    </label>
                  )}
                  {(bodyReleaseAction.force_missing_noc || bodyReleaseAction.force_missing_pm) && (
                    <div><Label className="text-xs text-red-700">Override Reason *</Label>
                      <Textarea value={bodyReleaseAction.override_reason}
                        onChange={e => setBodyReleaseAction(p => ({ ...p, override_reason: e.target.value }))} rows={2} /></div>
                  )}
                  <div className="flex justify-end gap-2 pt-2">
                    <Button variant="outline" onClick={() => setShowBodyReleaseDialog(false)}>Close</Button>
                    <Button onClick={performBodyRelease} className="bg-amber-600 hover:bg-amber-700">
                      Release Body
                    </Button>
                  </div>
                </>
              )}

              {bodyReleaseRec?.body_released && (
                <div className="flex justify-end gap-2 pt-2">
                  <Button variant="outline" onClick={() => setShowBodyReleaseDialog(false)}>Close</Button>
                  <Button onClick={() => printBodyRelease(bodyReleaseAdmId)}>
                    <Printer className="h-4 w-4 mr-1" /> Print Release Form
                  </Button>
                </div>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* DAMA — Discharge Against Medical Advice */}
      <Dialog open={showDamaDialog} onOpenChange={setShowDamaDialog}>
        <DialogContent className="max-w-2xl max-h-[92vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Discharge Against Medical Advice (DAMA)</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSaveDama} className="space-y-3">
            <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
              This signed form is the legal record that the patient is leaving against medical advice.
              References Sections 88 &amp; 92 IPC. The form is mandatory and cannot be undone once filed.
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Attending Doctor *</Label>
                <Select value={String(damaForm.attending_doctor_id || '')}
                  onValueChange={v => setDamaForm(p => ({ ...p, attending_doctor_id: v }))}>
                  <SelectTrigger><SelectValue placeholder="Select doctor" /></SelectTrigger>
                  <SelectContent>
                    {doctorsList.map(d => (
                      <SelectItem key={d.id} value={String(d.id)}>Dr. {d.first_name} {d.last_name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Language Used</Label>
                <Select value={damaForm.language_used}
                  onValueChange={v => setDamaForm(p => ({ ...p, language_used: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="english">English</SelectItem>
                    <SelectItem value="hindi">Hindi</SelectItem>
                    <SelectItem value="telugu">Telugu</SelectItem>
                    <SelectItem value="tamil">Tamil</SelectItem>
                    <SelectItem value="kannada">Kannada</SelectItem>
                    <SelectItem value="malayalam">Malayalam</SelectItem>
                    <SelectItem value="marathi">Marathi</SelectItem>
                    <SelectItem value="bengali">Bengali</SelectItem>
                    <SelectItem value="gujarati">Gujarati</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>Medical Advice Given *</Label>
              <Textarea required rows={3}
                placeholder="What was the patient advised? (e.g., 'Continue IV antibiotics for 48 more hours')"
                value={damaForm.medical_advice_given}
                onChange={e => setDamaForm(p => ({ ...p, medical_advice_given: e.target.value }))} />
            </div>
            <div>
              <Label>Risks Explained *</Label>
              <Textarea required rows={3}
                placeholder="What risks were explained? (e.g., 'Sepsis, organ failure, possible death')"
                value={damaForm.risks_explained}
                onChange={e => setDamaForm(p => ({ ...p, risks_explained: e.target.value }))} />
            </div>

            <div className="border rounded p-2 space-y-2 bg-gray-50">
              <p className="text-sm font-semibold">Acknowledgements (both required)</p>
              <label className="flex items-start gap-2 cursor-pointer">
                <input type="checkbox" className="mt-1" checked={damaForm.patient_acknowledges_advice}
                  onChange={e => setDamaForm(p => ({ ...p, patient_acknowledges_advice: e.target.checked }))} />
                <span className="text-sm">Patient/guardian acknowledges that medical advice and risks were clearly explained in the language they understand.</span>
              </label>
              <label className="flex items-start gap-2 cursor-pointer">
                <input type="checkbox" className="mt-1" checked={damaForm.patient_absolves_hospital}
                  onChange={e => setDamaForm(p => ({ ...p, patient_absolves_hospital: e.target.checked }))} />
                <span className="text-sm">Patient/guardian absolves the hospital and its staff of any consequences resulting from this discharge against medical advice.</span>
              </label>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Signed By *</Label>
                <Select value={damaForm.signed_by}
                  onValueChange={v => setDamaForm(p => ({ ...p, signed_by: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="patient">Patient</SelectItem>
                    <SelectItem value="guardian">Guardian / Next of Kin</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Signature Type</Label>
                <Select value={damaForm.primary_signature_type}
                  onValueChange={v => setDamaForm(p => ({ ...p, primary_signature_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="typed">Typed name</SelectItem>
                    <SelectItem value="drawn">Drawn signature (paste base64)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {damaForm.signed_by === 'guardian' && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Guardian Name *</Label>
                  <Input required value={damaForm.guardian_name}
                    onChange={e => setDamaForm(p => ({ ...p, guardian_name: e.target.value }))} />
                </div>
                <div>
                  <Label>Relationship to Patient</Label>
                  <Input value={damaForm.guardian_relationship}
                    placeholder="e.g., spouse, parent, son"
                    onChange={e => setDamaForm(p => ({ ...p, guardian_relationship: e.target.value }))} />
                </div>
              </div>
            )}

            <div>
              <Label>{damaForm.signed_by === 'guardian' ? 'Guardian Signature *' : 'Patient Signature *'}</Label>
              <Input required value={damaForm.primary_signature}
                placeholder={damaForm.primary_signature_type === 'typed' ? 'Type full name' : 'Paste base64 signature image'}
                onChange={e => setDamaForm(p => ({ ...p, primary_signature: e.target.value }))} />
            </div>

            <div className="border-t pt-2">
              <p className="text-sm font-semibold mb-2">Witness</p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Witness Name *</Label>
                  <Input required value={damaForm.witness_name}
                    onChange={e => setDamaForm(p => ({ ...p, witness_name: e.target.value }))} />
                </div>
                <div>
                  <Label>Designation</Label>
                  <Input value={damaForm.witness_designation}
                    placeholder="e.g., Senior Nurse, Resident Doctor"
                    onChange={e => setDamaForm(p => ({ ...p, witness_designation: e.target.value }))} />
                </div>
              </div>
              <div className="mt-2">
                <Label>Witness Signature *</Label>
                <Input required value={damaForm.witness_signature}
                  placeholder="Type full name"
                  onChange={e => setDamaForm(p => ({ ...p, witness_signature: e.target.value }))} />
              </div>
            </div>

            <div>
              <Label>Notes (optional)</Label>
              <Textarea rows={2} value={damaForm.notes}
                placeholder="e.g., 'Patient was lucid and articulate at signing.'"
                onChange={e => setDamaForm(p => ({ ...p, notes: e.target.value }))} />
            </div>

            <Button type="submit" className="w-full" disabled={loading} variant="destructive">
              {loading ? 'Saving…' : 'Sign and Save DAMA Form'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Ward Transfer Dialog */}
      <Dialog open={showWardTransferDialog} onOpenChange={setShowWardTransferDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Initiate Ward Transfer</DialogTitle></DialogHeader>
          <form onSubmit={handleInitiateWardTransfer} className="space-y-3">
            <div>
              <Label>Target Room *</Label>
              <Select value={wardTransferForm.to_room_id} onValueChange={v => {
                setWardTransferForm(p => ({ ...p, to_room_id: v, to_bed_id: '' }));
                axios.get(`/api/inpatient/rooms/${v}/beds`).then(res => setWardTransferBeds(res.data)).catch(() => setWardTransferBeds([]));
              }}>
                <SelectTrigger><SelectValue placeholder="Select room" /></SelectTrigger>
                <SelectContent>
                  {availableRooms.map(r => (
                    <SelectItem key={r.id} value={String(r.id)}>{r.room_number} ({roomTypeLabel[r.room_type]}) · {r.available_beds} bed(s) available</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {wardTransferBeds.length > 0 && (
              <div>
                <Label>Bed (optional)</Label>
                <Select value={wardTransferForm.to_bed_id} onValueChange={v => setWardTransferForm(p => ({ ...p, to_bed_id: v }))}>
                  <SelectTrigger><SelectValue placeholder="Any available" /></SelectTrigger>
                  <SelectContent>
                    {wardTransferBeds.filter(b => b.status === 'available').map(b => (
                      <SelectItem key={b.id} value={String(b.id)}>Bed {b.bed_label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div>
              <Label>Reason *</Label>
              <Input value={wardTransferForm.reason} onChange={e => setWardTransferForm(p => ({ ...p, reason: e.target.value }))} required placeholder="e.g. Step-down from ICU, patient request..." />
            </div>
            <div>
              <Label>Clinical Handover Note *</Label>
              <Textarea value={wardTransferForm.transfer_note} onChange={e => setWardTransferForm(p => ({ ...p, transfer_note: e.target.value }))} rows={4} required placeholder="Current status, pending treatments, precautions..." />
            </div>
            <p className="text-xs text-gray-500">Transfer will be pending until accepted by a nurse or doctor on the receiving ward.</p>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Submitting…' : 'Initiate Transfer'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Roster Cell Dialog */}
      <Dialog open={showRosterCellDialog} onOpenChange={setShowRosterCellDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{rosterCellEdit?.existing ? 'Edit' : 'Assign'} Roster — {rosterCellEdit?.nurse?.name}</DialogTitle>
          </DialogHeader>
          {rosterCellEdit && (
            <form onSubmit={handleSaveRosterCell} className="space-y-3">
              <div className="bg-gray-50 p-2 rounded text-sm">
                <b>{rosterCellEdit.dateIso}</b> · {rosterCellEdit.shift} shift
              </div>
              <div>
                <Label>Status *</Label>
                <Select value={rosterCellForm.status} onValueChange={v => setRosterCellForm(p => ({ ...p, status: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="working">Working</SelectItem>
                    <SelectItem value="on_call">On Call</SelectItem>
                    <SelectItem value="leave">Leave</SelectItem>
                    <SelectItem value="off">Off (rest day)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Ward (optional)</Label>
                <Input value={rosterCellForm.ward} onChange={e => setRosterCellForm(p => ({ ...p, ward: e.target.value }))} placeholder="e.g. ICU, Ward A" />
              </div>
              <div>
                <Label>Notes</Label>
                <Textarea value={rosterCellForm.notes} onChange={e => setRosterCellForm(p => ({ ...p, notes: e.target.value }))} rows={2} />
              </div>
              <div className="flex justify-between gap-2">
                {rosterCellEdit.existing && (
                  <Button type="button" variant="ghost" className="text-red-600" onClick={handleDeleteRosterCell}>
                    <Trash2 className="h-4 w-4 mr-1" /> Remove
                  </Button>
                )}
                <Button type="submit" className="ml-auto" disabled={loading}>
                  {loading ? 'Saving…' : (rosterCellEdit.existing ? 'Save Changes' : 'Assign')}
                </Button>
              </div>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* Bulk Roster Dialog */}
      <Dialog open={showBulkRosterDialog} onOpenChange={setShowBulkRosterDialog}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Bulk Roster Assign</DialogTitle></DialogHeader>
          <form onSubmit={handleBulkRoster} className="space-y-3">
            <div>
              <Label>Nurses * <span className="text-xs text-gray-500">({bulkRosterForm.nurse_ids.length} selected)</span></Label>
              <div className="border rounded max-h-40 overflow-y-auto p-2 space-y-1">
                {nursesList.length === 0 ? (
                  <p className="text-xs text-gray-500">No nurses found. Create users with the 'nurse' role.</p>
                ) : (
                  nursesList.map(n => (
                    <label key={n.id} className="flex items-center gap-2 text-sm cursor-pointer hover:bg-gray-50 p-1 rounded">
                      <input
                        type="checkbox"
                        checked={bulkRosterForm.nurse_ids.includes(n.id)}
                        onChange={e => {
                          setBulkRosterForm(p => ({
                            ...p,
                            nurse_ids: e.target.checked
                              ? [...p.nurse_ids, n.id]
                              : p.nurse_ids.filter(x => x !== n.id),
                          }));
                        }}
                      />
                      {n.first_name} {n.last_name}
                    </label>
                  ))
                )}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>From Date *</Label>
                <Input type="date" value={bulkRosterForm.from_date} onChange={e => setBulkRosterForm(p => ({ ...p, from_date: e.target.value }))} required />
              </div>
              <div>
                <Label>To Date *</Label>
                <Input type="date" value={bulkRosterForm.to_date} onChange={e => setBulkRosterForm(p => ({ ...p, to_date: e.target.value }))} required />
              </div>
            </div>
            <div>
              <Label>Shifts *</Label>
              <div className="flex gap-3 mt-1">
                {['morning', 'afternoon', 'night'].map(s => (
                  <label key={s} className="flex items-center gap-1 text-sm capitalize cursor-pointer">
                    <input
                      type="checkbox"
                      checked={bulkRosterForm.shifts.includes(s)}
                      onChange={e => {
                        setBulkRosterForm(p => ({
                          ...p,
                          shifts: e.target.checked ? [...p.shifts, s] : p.shifts.filter(x => x !== s),
                        }));
                      }}
                    />
                    {s}
                  </label>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Status</Label>
                <Select value={bulkRosterForm.status} onValueChange={v => setBulkRosterForm(p => ({ ...p, status: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="working">Working</SelectItem>
                    <SelectItem value="on_call">On Call</SelectItem>
                    <SelectItem value="leave">Leave</SelectItem>
                    <SelectItem value="off">Off</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Ward (optional)</Label>
                <Input value={bulkRosterForm.ward} onChange={e => setBulkRosterForm(p => ({ ...p, ward: e.target.value }))} />
              </div>
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea value={bulkRosterForm.notes} onChange={e => setBulkRosterForm(p => ({ ...p, notes: e.target.value }))} rows={2} />
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input type="checkbox" checked={bulkRosterForm.overwrite} onChange={e => setBulkRosterForm(p => ({ ...p, overwrite: e.target.checked }))} />
              <span>Overwrite existing entries</span>
              <span className="text-xs text-gray-500">(replace any current grants in the date/shift range)</span>
            </label>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? 'Applying…' : `Apply to ${bulkRosterForm.nurse_ids.length} nurse(s) × ${bulkRosterForm.shifts.length} shift(s)`}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Nurse Assignment Dialog */}
      <Dialog open={showNurseAssignDialog} onOpenChange={setShowNurseAssignDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Assign Nurse</DialogTitle></DialogHeader>
          <form onSubmit={handleAssignNurse} className="space-y-3">
            <div>
              <div className="flex items-center justify-between mb-1">
                <Label>Nurse *</Label>
                <label className="flex items-center gap-1 text-xs cursor-pointer">
                  <input type="checkbox" checked={restrictToOnDuty} onChange={e => setRestrictToOnDuty(e.target.checked)} />
                  On-duty only
                </label>
              </div>
              <Select value={nurseAssignForm.nurse_id} onValueChange={v => setNurseAssignForm(p => ({ ...p, nurse_id: v }))}>
                <SelectTrigger><SelectValue placeholder={restrictToOnDuty ? `Select from ${onDutyNurses.length} on-duty nurse(s)` : "Select nurse"} /></SelectTrigger>
                <SelectContent>
                  {(restrictToOnDuty ? onDutyNurses.map(n => ({ id: n.nurse_id, first_name: n.nurse_name?.split(' ')[0] || '', last_name: n.nurse_name?.split(' ').slice(1).join(' ') || '', _on_duty_status: n.status })) : nursesList).map(n => (
                    <SelectItem key={n.id} value={String(n.id)}>
                      {n.first_name} {n.last_name}{n._on_duty_status === 'on_call' ? ' (on call)' : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {restrictToOnDuty && onDutyNurses.length === 0 && (
                <p className="text-xs text-orange-600 mt-1">No nurses rostered for {nurseAssignForm.shift} on {nurseAssignForm.assignment_date}. Uncheck "On-duty only" to override or update the duty roster first.</p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Shift *</Label>
                <Select value={nurseAssignForm.shift} onValueChange={v => setNurseAssignForm(p => ({ ...p, shift: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="morning">Morning</SelectItem>
                    <SelectItem value="afternoon">Afternoon</SelectItem>
                    <SelectItem value="night">Night</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Date *</Label>
                <Input type="date" value={nurseAssignForm.assignment_date} onChange={e => setNurseAssignForm(p => ({ ...p, assignment_date: e.target.value }))} required />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <input type="checkbox" id="is_primary" checked={nurseAssignForm.is_primary} onChange={e => setNurseAssignForm(p => ({ ...p, is_primary: e.target.checked }))} />
              <Label htmlFor="is_primary" className="cursor-pointer">Primary nurse for this shift</Label>
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea value={nurseAssignForm.notes} onChange={e => setNurseAssignForm(p => ({ ...p, notes: e.target.value }))} rows={2} />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Assign'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Reservation Dialog */}
      <Dialog open={showReservationDialog} onOpenChange={(open) => { setShowReservationDialog(open); if (!open) { setReservationSelectedPatient(null); setReservationPatientSearch(''); } }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>New Bed Reservation</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateReservation} className="space-y-3">
            <div>
              <Label>Patient *</Label>
              {reservationSelectedPatient ? (
                <div className="flex justify-between items-center p-2 border rounded text-sm">
                  <span>{reservationSelectedPatient.first_name} {reservationSelectedPatient.last_name}</span>
                  <Button type="button" variant="ghost" size="sm" onClick={() => { setReservationSelectedPatient(null); setReservationPatientSearch(''); }}><X className="h-4 w-4" /></Button>
                </div>
              ) : (
                <>
                  <Input value={reservationPatientSearch} onChange={e => setReservationPatientSearch(e.target.value)} placeholder="Search by name or phone..." />
                  {reservationPatientResults.length > 0 && (
                    <div className="border rounded max-h-40 overflow-y-auto mt-1">
                      {reservationPatientResults.slice(0, 10).map(p => (
                        <div key={p.id} className="p-2 hover:bg-gray-50 cursor-pointer text-sm" onClick={() => { setReservationSelectedPatient(p); setReservationPatientSearch(''); setReservationPatientResults([]); }}>
                          {p.first_name} {p.last_name} — {p.primary_phone}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
            <div>
              <Label>Reserved For *</Label>
              <Input type="datetime-local" value={reservationForm.reserved_for_date} onChange={e => setReservationForm(p => ({ ...p, reserved_for_date: e.target.value }))} required />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Reason</Label>
                <Select value={reservationForm.reservation_reason} onValueChange={v => setReservationForm(p => ({ ...p, reservation_reason: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="elective">Elective admission</SelectItem>
                    <SelectItem value="post_op">Post-op recovery</SelectItem>
                    <SelectItem value="transfer">Transfer in</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Room Type</Label>
                <Select value={reservationForm.room_type || 'any'} onValueChange={v => setReservationForm(p => ({ ...p, room_type: v === 'any' ? '' : v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">Any</SelectItem>
                    <SelectItem value="general">General</SelectItem>
                    <SelectItem value="private">Private</SelectItem>
                    <SelectItem value="icu">ICU</SelectItem>
                    <SelectItem value="emergency">Emergency</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>Specific Room (optional)</Label>
              <Select value={reservationForm.room_id || 'any'} onValueChange={v => setReservationForm(p => ({ ...p, room_id: v === 'any' ? '' : v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="any">Any room</SelectItem>
                  {availableRooms.map(r => (
                    <SelectItem key={r.id} value={String(r.id)}>{r.room_number} ({roomTypeLabel[r.room_type]})</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea value={reservationForm.notes} onChange={e => setReservationForm(p => ({ ...p, notes: e.target.value }))} rows={2} />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Reserve'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Convert Reservation Dialog */}
      <Dialog open={showConvertReservationDialog} onOpenChange={setShowConvertReservationDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Convert to Admission</DialogTitle></DialogHeader>
          {convertingReservation && (
            <form onSubmit={handleConvertReservation} className="space-y-3">
              <div className="bg-gray-50 p-3 rounded text-sm">
                <div><b>Patient:</b> {convertingReservation.patient_name}</div>
                <div><b>Target:</b> {convertingReservation.bed_label ? `Bed ${convertingReservation.bed_label} in Room ${convertingReservation.room_number}` : convertingReservation.room_number ? `Room ${convertingReservation.room_number}` : `Any ${convertingReservation.room_type} room`}</div>
              </div>
              <div>
                <Label>Admitting Doctor *</Label>
                <Select value={convertForm.admitting_doctor_id} onValueChange={v => setConvertForm(p => ({ ...p, admitting_doctor_id: v }))}>
                  <SelectTrigger><SelectValue placeholder="Select doctor" /></SelectTrigger>
                  <SelectContent>
                    {doctorsList.map(d => <SelectItem key={d.id} value={String(d.id)}>Dr. {d.first_name} {d.last_name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Admission Type</Label>
                  <Select value={convertForm.admission_type} onValueChange={v => setConvertForm(p => ({ ...p, admission_type: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="elective">Elective</SelectItem>
                      <SelectItem value="emergency">Emergency</SelectItem>
                      <SelectItem value="transfer">Transfer</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Condition</Label>
                  <Select value={convertForm.condition_on_admission} onValueChange={v => setConvertForm(p => ({ ...p, condition_on_admission: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="stable">Stable</SelectItem>
                      <SelectItem value="serious">Serious</SelectItem>
                      <SelectItem value="critical">Critical</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div>
                <Label>Admission Reason</Label>
                <Textarea value={convertForm.admission_reason} onChange={e => setConvertForm(p => ({ ...p, admission_reason: e.target.value }))} rows={2} />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Converting…' : 'Convert'}</Button>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* OT Charges Dialog */}
      <Dialog open={showOTChargesDialog} onOpenChange={setShowOTChargesDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>OT Charges</DialogTitle></DialogHeader>
          {editingOT && (
            <form onSubmit={handleSaveOTCharges} className="space-y-3">
              <p className="text-sm text-gray-600">{editingOT.procedure_name} · {editingOT.patient_name}</p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Surgeon Fee (₹)</Label>
                  <Input type="number" step="0.01" value={otChargesForm.surgeon_fee} onChange={e => setOtChargesForm(p => ({ ...p, surgeon_fee: e.target.value }))} />
                </div>
                <div>
                  <Label>Anaesthetist Fee (₹)</Label>
                  <Input type="number" step="0.01" value={otChargesForm.anaesthetist_fee} onChange={e => setOtChargesForm(p => ({ ...p, anaesthetist_fee: e.target.value }))} />
                </div>
                <div>
                  <Label>OT Room Charge (₹)</Label>
                  <Input type="number" step="0.01" value={otChargesForm.ot_room_charge} onChange={e => setOtChargesForm(p => ({ ...p, ot_room_charge: e.target.value }))} />
                </div>
                <div>
                  <Label>Equipment (₹)</Label>
                  <Input type="number" step="0.01" value={otChargesForm.equipment_charge} onChange={e => setOtChargesForm(p => ({ ...p, equipment_charge: e.target.value }))} />
                </div>
                <div>
                  <Label>Consumables (₹)</Label>
                  <Input type="number" step="0.01" value={otChargesForm.consumables_charge} onChange={e => setOtChargesForm(p => ({ ...p, consumables_charge: e.target.value }))} />
                </div>
                <div>
                  <Label>Procedure Charge (₹)</Label>
                  <Input type="number" step="0.01" value={otChargesForm.procedure_charge} onChange={e => setOtChargesForm(p => ({ ...p, procedure_charge: e.target.value }))} />
                </div>
                <div>
                  <Label>Other (₹)</Label>
                  <Input type="number" step="0.01" value={otChargesForm.other_charges} onChange={e => setOtChargesForm(p => ({ ...p, other_charges: e.target.value }))} />
                </div>
              </div>
              <div className="border-t pt-2 text-right font-semibold text-sm">
                Total: ₹{Object.values(otChargesForm).reduce((s, v) => s + (parseFloat(v) || 0), 0).toFixed(2)}
              </div>
              <p className="text-xs text-gray-500">Charges flow into the admission bill next time it is previewed or finalised.</p>
              <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Save Charges'}</Button>
            </form>
          )}
        </DialogContent>
      </Dialog>

      {/* TPA Dialog */}
      <Dialog open={showTpaDialog} onOpenChange={(open) => { setShowTpaDialog(open); if (!open) setEditingTpa(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{editingTpa ? 'Edit' : 'New'} TPA</DialogTitle></DialogHeader>
          <form onSubmit={handleSubmitTpa} className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>TPA Name *</Label>
                <Input value={tpaForm.tpa_name} onChange={e => setTpaForm(p => ({ ...p, tpa_name: e.target.value }))} required />
              </div>
              <div>
                <Label>Code</Label>
                <Input value={tpaForm.tpa_code} onChange={e => setTpaForm(p => ({ ...p, tpa_code: e.target.value }))} />
              </div>
              <div>
                <Label>Phone</Label>
                <Input value={tpaForm.phone} onChange={e => setTpaForm(p => ({ ...p, phone: e.target.value }))} />
              </div>
              <div>
                <Label>Email</Label>
                <Input type="email" value={tpaForm.email} onChange={e => setTpaForm(p => ({ ...p, email: e.target.value }))} />
              </div>
              <div className="col-span-2">
                <Label>Address</Label>
                <Textarea value={tpaForm.address} onChange={e => setTpaForm(p => ({ ...p, address: e.target.value }))} rows={2} />
              </div>
              <div>
                <Label>Default Discount %</Label>
                <Input type="number" step="0.01" min="0" max="100" value={tpaForm.default_discount_percent} onChange={e => setTpaForm(p => ({ ...p, default_discount_percent: e.target.value }))} />
              </div>
            </div>
            <div>
              <Label>Contract Details</Label>
              <Textarea value={tpaForm.contract_details} onChange={e => setTpaForm(p => ({ ...p, contract_details: e.target.value }))} rows={2} />
            </div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving…' : 'Save TPA'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Inpatient Prescription Dialog */}
      <Dialog open={showPrescriptionDialog} onOpenChange={(o) => { setShowPrescriptionDialog(o); if (!o) setMedicineSearchResults([]); }}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Add Prescription</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateInpatientPrescription} className="space-y-3">
            <div>
              <Label className="text-xs">Notes (optional)</Label>
              <Textarea
                rows={2}
                value={prescriptionForm.notes}
                onChange={e => setPrescriptionForm(p => ({ ...p, notes: e.target.value }))}
                placeholder="e.g., Take after meals; review in 3 days"
              />
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-xs">Medicines *</Label>
                <Button type="button" size="sm" variant="outline" onClick={() => setPrescriptionForm(p => ({ ...p, items: [...p.items, { ...BLANK_RX_ITEM }] }))}>
                  <Plus className="h-3 w-3 mr-1" /> Add Row
                </Button>
              </div>
              {prescriptionForm.items.map((it, idx) => (
                <div key={idx} className="border rounded p-2 space-y-2 bg-gray-50">
                  <div className="flex items-start gap-2">
                    <div className="flex-1 relative">
                      <Input
                        placeholder="Medicine name (search inventory or type free-text)"
                        value={it.medicine_name}
                        onChange={e => {
                          const v = e.target.value;
                          setPrescriptionForm(p => {
                            const next = [...p.items];
                            next[idx] = { ...next[idx], medicine_name: v, medicine_id: '' };
                            return { ...p, items: next };
                          });
                          searchMedicines(v, idx);
                        }}
                      />
                      {medicineSearchTargetIdx === idx && medicineSearchResults.length > 0 && !it.medicine_id && (
                        <div className="absolute z-20 w-full bg-white border rounded shadow-lg mt-1 max-h-40 overflow-y-auto">
                          {medicineSearchResults.map(m => (
                            <div
                              key={m.id}
                              className="px-3 py-1.5 hover:bg-blue-50 cursor-pointer text-xs"
                              onClick={() => {
                                setPrescriptionForm(p => {
                                  const next = [...p.items];
                                  next[idx] = {
                                    ...next[idx],
                                    medicine_id: m.id,
                                    medicine_name: `${m.name}${m.strength ? ' ' + m.strength : ''}${m.dosage_form ? ' (' + m.dosage_form + ')' : ''}`,
                                  };
                                  return { ...p, items: next };
                                });
                                setMedicineSearchResults([]);
                              }}
                            >
                              <span className="font-medium">{m.name}</span>
                              {m.strength && <span className="text-gray-500"> · {m.strength}</span>}
                              {m.dosage_form && <span className="text-gray-500"> · {m.dosage_form}</span>}
                              <span className="text-gray-400 ml-1">₹{Number(m.unit_price || 0).toFixed(2)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-9 w-9 p-0"
                      disabled={prescriptionForm.items.length === 1}
                      onClick={() => setPrescriptionForm(p => ({ ...p, items: p.items.filter((_, i) => i !== idx) }))}
                    >
                      <Trash2 className="h-4 w-4 text-red-500" />
                    </Button>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    <div>
                      <Label className="text-[10px] text-gray-500">Dosage *</Label>
                      <Input
                        placeholder="1 tab BD"
                        value={it.dosage}
                        onChange={e => setPrescriptionForm(p => {
                          const next = [...p.items]; next[idx] = { ...next[idx], dosage: e.target.value }; return { ...p, items: next };
                        })}
                      />
                    </div>
                    <div>
                      <Label className="text-[10px] text-gray-500">Duration *</Label>
                      <Input
                        placeholder="5 days"
                        value={it.duration}
                        onChange={e => setPrescriptionForm(p => {
                          const next = [...p.items]; next[idx] = { ...next[idx], duration: e.target.value }; return { ...p, items: next };
                        })}
                      />
                    </div>
                    <div>
                      <Label className="text-[10px] text-gray-500">Quantity</Label>
                      <Input
                        type="number"
                        min="1"
                        value={it.quantity_prescribed}
                        onChange={e => setPrescriptionForm(p => {
                          const next = [...p.items]; next[idx] = { ...next[idx], quantity_prescribed: e.target.value }; return { ...p, items: next };
                        })}
                      />
                    </div>
                  </div>
                  <div>
                    <Label className="text-[10px] text-gray-500">Instructions (optional)</Label>
                    <Input
                      placeholder="After food, with water, etc."
                      value={it.instructions}
                      onChange={e => setPrescriptionForm(p => {
                        const next = [...p.items]; next[idx] = { ...next[idx], instructions: e.target.value }; return { ...p, items: next };
                      })}
                    />
                  </div>
                </div>
              ))}
              <p className="text-[11px] text-gray-500">Linking a row to inventory (by clicking a search suggestion) bills it via pharmacy. Free-text rows are advisory only and won't be billed.</p>
            </div>
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? 'Saving…' : 'Create Prescription'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Lab Order Dialog */}
      <Dialog open={showLabOrderDialog} onOpenChange={setShowLabOrderDialog}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Order Lab Tests</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateLabOrder} className="space-y-4">
            <div>
              <Label>Priority</Label>
              <Select value={labOrderForm.priority} onValueChange={v => setLabOrderForm(p => ({ ...p, priority: v }))}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="normal">Normal</SelectItem>
                  <SelectItem value="urgent">Urgent</SelectItem>
                  <SelectItem value="stat">STAT</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Search Tests</Label>
              <Input placeholder="Search by test name or code..." value={labTestSearch}
                onChange={e => setLabTestSearch(e.target.value)} />
            </div>
            <div className="border rounded-lg max-h-48 overflow-y-auto">
              {availableLabTests
                .filter(t => !labTestSearch || t.name.toLowerCase().includes(labTestSearch.toLowerCase()) || (t.test_code && t.test_code.toLowerCase().includes(labTestSearch.toLowerCase())))
                .map(t => (
                  <label key={t.id} className={`flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-gray-50 border-b last:border-b-0 ${labOrderForm.test_ids.includes(t.id) ? 'bg-blue-50' : ''}`}>
                    <div className="flex items-center gap-2">
                      <input type="checkbox" checked={labOrderForm.test_ids.includes(t.id)} onChange={() => toggleLabTest(t.id)} className="rounded" />
                      <div>
                        <span className="text-sm font-medium">{t.name}</span>
                        {t.test_code && <span className="text-xs text-gray-400 ml-1">({t.test_code})</span>}
                      </div>
                    </div>
                    <span className="text-sm text-gray-600">₹{parseFloat(t.cost || 0).toFixed(2)}</span>
                  </label>
                ))}
              {availableLabTests.length === 0 && (
                <p className="text-sm text-gray-500 text-center py-4">No lab tests available</p>
              )}
            </div>
            {labOrderForm.test_ids.length > 0 && (
              <p className="text-sm font-medium">
                Selected: {labOrderForm.test_ids.length} test(s) — Total: ₹{availableLabTests
                  .filter(t => labOrderForm.test_ids.includes(t.id))
                  .reduce((sum, t) => sum + (t.cost || 0), 0).toFixed(2)}
              </p>
            )}
            <div>
              <Label>Notes</Label>
              <Textarea value={labOrderForm.notes} onChange={e => setLabOrderForm(p => ({ ...p, notes: e.target.value }))} rows={2} placeholder="Optional clinical notes..." />
            </div>
            <Button type="submit" className="w-full" disabled={loading || labOrderForm.test_ids.length === 0}>
              {loading ? 'Ordering...' : `Order ${labOrderForm.test_ids.length} Test(s)`}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Review & Edit Final Bill Dialog */}
      <Dialog open={showReviewBillDialog} onOpenChange={setShowReviewBillDialog}>
        <DialogContent className="max-w-4xl max-h-[92vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Review & Generate Final Bill — {activityAdmission?.patient_name || ''}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-xs text-gray-500">
              All currently unbilled charges are loaded below. Edit qty / unit price / item name, remove lines you don't want
              to bill, or add a custom line. Changes are recorded once you generate the final bill.
            </p>
            <div className="border rounded">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="text-left px-2 py-1.5">Item</th>
                    <th className="text-right px-2 py-1.5 w-16">Qty</th>
                    <th className="text-right px-2 py-1.5 w-28">Unit ₹</th>
                    <th className="text-right px-2 py-1.5 w-28">Total ₹</th>
                    <th className="w-8"></th>
                  </tr>
                </thead>
                <tbody>
                  {reviewBillItems.length === 0 ? (
                    <tr><td colSpan={5} className="text-center text-gray-500 py-3 italic">No bill lines. Click "Add Line" to start.</td></tr>
                  ) : reviewBillItems.map((it, idx) => (
                    <tr key={idx} className="border-b last:border-b-0">
                      <td className="px-2 py-1">
                        <Input
                          className="h-7 text-xs"
                          value={it.item_name}
                          onChange={e => setReviewBillItems(arr => { const n = [...arr]; n[idx] = { ...n[idx], item_name: e.target.value }; return n; })}
                        />
                        {it.source && it.source !== 'custom' && (
                          <span className="text-[10px] text-gray-400">{it.source}{it.source_id ? ` #${it.source_id}` : ''}</span>
                        )}
                      </td>
                      <td className="px-2 py-1">
                        <Input type="number" min="1" className="h-7 text-xs text-right"
                          value={it.quantity}
                          onChange={e => setReviewBillItems(arr => {
                            const n = [...arr];
                            const q = Math.max(1, parseInt(e.target.value) || 1);
                            const up = parseFloat(n[idx].unit_price) || 0;
                            n[idx] = { ...n[idx], quantity: q, total_price: +(q * up).toFixed(2) };
                            return n;
                          })} />
                      </td>
                      <td className="px-2 py-1">
                        <Input type="number" min="0" step="0.01" className="h-7 text-xs text-right"
                          value={it.unit_price}
                          onChange={e => setReviewBillItems(arr => {
                            const n = [...arr];
                            const up = parseFloat(e.target.value) || 0;
                            const q = parseInt(n[idx].quantity) || 1;
                            n[idx] = { ...n[idx], unit_price: up, total_price: +(q * up).toFixed(2) };
                            return n;
                          })} />
                      </td>
                      <td className="px-2 py-1">
                        <Input type="number" min="0" step="0.01" className="h-7 text-xs text-right"
                          value={it.total_price}
                          onChange={e => setReviewBillItems(arr => {
                            const n = [...arr];
                            n[idx] = { ...n[idx], total_price: parseFloat(e.target.value) || 0 };
                            return n;
                          })} />
                      </td>
                      <td className="px-1 py-1 text-center">
                        <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0"
                          onClick={() => setReviewBillItems(arr => arr.filter((_, i) => i !== idx))}>
                          <Trash2 className="h-3.5 w-3.5 text-red-500" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Button type="button" size="sm" variant="outline" onClick={() => setReviewBillItems(arr => [...arr, {
              source: 'custom', source_id: null, item_type: 'custom', item_name: '', quantity: 1, unit_price: 0, total_price: 0,
            }])}>
              <Plus className="h-3.5 w-3.5 mr-1" /> Add Custom Line
            </Button>

            {/* Discount + Tax */}
            <div className="border rounded p-3 bg-gray-50 space-y-2">
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <Label className="text-xs">Discount Type</Label>
                  <Select value={reviewBillDiscount.type} onValueChange={v => setReviewBillDiscount(p => ({ ...p, type: v }))}>
                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="flat">Flat ₹</SelectItem>
                      <SelectItem value="percentage">Percentage %</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Discount Value</Label>
                  <Input type="number" min="0" step="0.01" className="h-8 text-xs"
                    value={reviewBillDiscount.value}
                    onChange={e => setReviewBillDiscount(p => ({ ...p, value: e.target.value }))} />
                </div>
                <div>
                  <Label className="text-xs">Tax %</Label>
                  <Input type="number" min="0" max="100" step="0.01" className="h-8 text-xs"
                    value={reviewBillTaxPct}
                    onChange={e => setReviewBillTaxPct(e.target.value)} />
                </div>
              </div>
            </div>

            {/* Totals */}
            <div className="border-t pt-2 text-sm space-y-0.5">
              <div className="flex justify-between"><span>Subtotal</span><span>₹{reviewBillSubtotal.toFixed(2)}</span></div>
              {reviewBillDiscountAmount > 0 && (
                <div className="flex justify-between text-gray-600"><span>Discount{reviewBillDiscount.type === 'percentage' ? ` (${reviewBillDiscount.value}%)` : ''}</span><span>– ₹{reviewBillDiscountAmount.toFixed(2)}</span></div>
              )}
              {reviewBillTaxAmount > 0 && (
                <div className="flex justify-between text-gray-600"><span>Tax ({reviewBillTaxPct}%)</span><span>+ ₹{reviewBillTaxAmount.toFixed(2)}</span></div>
              )}
              <div className="flex justify-between font-semibold text-base pt-1 border-t mt-1"><span>Grand Total</span><span>₹{reviewBillGrandTotal.toFixed(2)}</span></div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => setShowReviewBillDialog(false)}>Cancel</Button>
              <Button type="button" onClick={handleSubmitReviewedBill} disabled={loading || reviewBillItems.length === 0}>
                {loading ? 'Generating…' : 'Generate Final Bill'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Discharge Dialog */}
      <Dialog open={showDischargeDialog} onOpenChange={setShowDischargeDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Discharge Patient - {dischargeAdmission?.patient_name}</DialogTitle></DialogHeader>
          <form onSubmit={handleDischarge} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Discharge Type *</Label>
                <Select value={dischargeForm.discharge_type} onValueChange={v => setDischargeForm(p => ({ ...p, discharge_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="normal">Normal</SelectItem>
                    <SelectItem value="against_advice">Against Advice</SelectItem>
                    <SelectItem value="transfer">Transfer</SelectItem>
                    <SelectItem value="death">Death</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Condition on Discharge</Label>
                <Select value={dischargeForm.condition_on_discharge} onValueChange={v => setDischargeForm(p => ({ ...p, condition_on_discharge: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="stable">Stable</SelectItem>
                    <SelectItem value="improved">Improved</SelectItem>
                    <SelectItem value="unchanged">Unchanged</SelectItem>
                    <SelectItem value="critical">Critical</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>Diagnosis on Discharge</Label>
              <Textarea value={dischargeForm.diagnosis_on_discharge} onChange={e => setDischargeForm(p => ({ ...p, diagnosis_on_discharge: e.target.value }))} rows={2} />
            </div>
            <div>
              <Label>Treatment Given</Label>
              <Textarea value={dischargeForm.treatment_given} onChange={e => setDischargeForm(p => ({ ...p, treatment_given: e.target.value }))} rows={2} />
            </div>
            <div>
              <Label>Discharge Summary</Label>
              <Textarea value={dischargeForm.discharge_summary} onChange={e => setDischargeForm(p => ({ ...p, discharge_summary: e.target.value }))} rows={2} />
            </div>
            <div className="border rounded p-3 bg-gray-50 space-y-2">
              <div className="flex items-center justify-between">
                <Label className="font-semibold">Take-Home Medications</Label>
                <Button type="button" size="sm" variant="outline" onClick={() => setDischargeForm(p => ({
                  ...p,
                  take_home_medications: [...(p.take_home_medications || []), { medicine_id: '', medicine_name: '', dosage: '', frequency: '', duration: '', quantity: '', instructions: '' }],
                }))}>
                  <Plus className="h-3 w-3 mr-1" /> Add Medicine
                </Button>
              </div>
              <p className="text-[11px] text-gray-500">List the prescription the patient takes home. This is separate from drugs given during the stay.</p>
              {(dischargeForm.take_home_medications || []).length === 0 ? (
                <p className="text-xs text-gray-500 italic">No take-home medications.</p>
              ) : (
                <div className="space-y-2">
                  {(dischargeForm.take_home_medications || []).map((m, idx) => (
                    <div key={idx} className="border rounded p-2 bg-white space-y-1">
                      <div className="flex items-start gap-2">
                        <Input
                          placeholder="Medicine name (e.g., Paracetamol 500mg)"
                          value={m.medicine_name}
                          onChange={e => setDischargeForm(p => {
                            const next = [...(p.take_home_medications || [])];
                            next[idx] = { ...next[idx], medicine_name: e.target.value };
                            return { ...p, take_home_medications: next };
                          })}
                          className="flex-1"
                        />
                        <Button type="button" size="sm" variant="ghost" className="h-9 w-9 p-0"
                          onClick={() => setDischargeForm(p => ({ ...p, take_home_medications: (p.take_home_medications || []).filter((_, i) => i !== idx) }))}>
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      </div>
                      <div className="grid grid-cols-4 gap-2">
                        <Input placeholder="Dosage" value={m.dosage}
                          onChange={e => setDischargeForm(p => { const next = [...(p.take_home_medications || [])]; next[idx] = { ...next[idx], dosage: e.target.value }; return { ...p, take_home_medications: next }; })} />
                        <Input placeholder="Frequency (BD/TID)" value={m.frequency}
                          onChange={e => setDischargeForm(p => { const next = [...(p.take_home_medications || [])]; next[idx] = { ...next[idx], frequency: e.target.value }; return { ...p, take_home_medications: next }; })} />
                        <Input placeholder="Duration (5 days)" value={m.duration}
                          onChange={e => setDischargeForm(p => { const next = [...(p.take_home_medications || [])]; next[idx] = { ...next[idx], duration: e.target.value }; return { ...p, take_home_medications: next }; })} />
                        <Input type="number" min="1" placeholder="Qty" value={m.quantity}
                          onChange={e => setDischargeForm(p => { const next = [...(p.take_home_medications || [])]; next[idx] = { ...next[idx], quantity: e.target.value }; return { ...p, take_home_medications: next }; })} />
                      </div>
                      <Input placeholder="Instructions (after meals, with water…)" value={m.instructions}
                        onChange={e => setDischargeForm(p => { const next = [...(p.take_home_medications || [])]; next[idx] = { ...next[idx], instructions: e.target.value }; return { ...p, take_home_medications: next }; })} />
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Follow-up Instructions</Label>
                <Textarea value={dischargeForm.follow_up_instructions} onChange={e => setDischargeForm(p => ({ ...p, follow_up_instructions: e.target.value }))} rows={2} />
              </div>
              <div>
                <Label>Follow-up Date</Label>
                <Input type="date" value={dischargeForm.follow_up_date} onChange={e => setDischargeForm(p => ({ ...p, follow_up_date: e.target.value }))} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Diet Instructions</Label>
                <Textarea value={dischargeForm.diet_instructions} onChange={e => setDischargeForm(p => ({ ...p, diet_instructions: e.target.value }))} rows={2} />
              </div>
              <div>
                <Label>Activity Restrictions</Label>
                <Textarea value={dischargeForm.activity_restrictions} onChange={e => setDischargeForm(p => ({ ...p, activity_restrictions: e.target.value }))} rows={2} />
              </div>
            </div>
            {dischargeBlockers.length > 0 && (
              <div className="border border-red-300 bg-red-50 rounded p-3 text-sm space-y-2">
                <p className="font-semibold text-red-800">Discharge blocked by safety gate{dischargeBlockers.length > 1 ? 's' : ''}:</p>
                <ul className="list-disc ml-5 space-y-1 text-red-700">
                  {dischargeBlockers.map(b => (
                    <li key={b.code}>
                      <span className="font-medium">{b.code.replace(/_/g, ' ')}</span>: {b.message}
                      {b.code === 'outstanding_balance' && typeof b.balance === 'number' && (
                        <span className="block text-xs">Balance: ₹{b.balance.toFixed(2)} (billed ₹{b.total_billed?.toFixed(2)}, deposited ₹{b.net_deposits?.toFixed(2)})</span>
                      )}
                      {b.code === 'unacknowledged_critical_alerts' && (
                        <span className="block text-xs">{b.alert_count} alert(s){b.parameters?.length ? ` — ${b.parameters.join(', ')}` : ''}</span>
                      )}
                      {b.code === 'missing_surgical_consent' && (
                        <span className="block text-xs">{b.completed_ot_count} completed OT procedure(s) without recorded consent.</span>
                      )}
                    </li>
                  ))}
                </ul>
                <div>
                  <Label className="text-red-800">Override reason (required) *</Label>
                  <Textarea required value={overrideReason} onChange={e => setOverrideReason(e.target.value)}
                    rows={2} placeholder="Explain why this discharge should proceed despite the gate(s)…" />
                </div>
                <p className="text-xs text-red-600">Submitting will record this override in the audit log against your account.</p>
              </div>
            )}
            <Button type="submit" className="w-full" disabled={loading} variant={dischargeBlockers.length > 0 ? 'destructive' : 'default'}>
              {loading ? 'Discharging...' : (dischargeBlockers.length > 0 ? 'Override and Confirm Discharge' : 'Confirm Discharge')}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Cancel Admission Bill Dialog */}
      <Dialog open={cancelBillDialog.open} onOpenChange={(o) => !o && setCancelBillDialog({ open: false, bill: null, reason: '' })}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Cancel bill {cancelBillDialog.bill?.bill_number}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <p className="text-gray-600">
              Cancelling releases every visit / OT / ancillary / prescription / lab order on this bill so they can be billed again. Bills with recorded payments cannot be cancelled — refund first.
            </p>
            <div>
              <Label>Reason *</Label>
              <Textarea required value={cancelBillDialog.reason}
                onChange={e => setCancelBillDialog(p => ({ ...p, reason: e.target.value }))}
                rows={2} placeholder="Why is this bill being cancelled?" />
            </div>
            <div className="flex gap-2 justify-end">
              <Button variant="outline" onClick={() => setCancelBillDialog({ open: false, bill: null, reason: '' })}>Keep bill</Button>
              <Button variant="destructive" onClick={handleCancelBill} disabled={loading || !cancelBillDialog.reason.trim()}>
                {loading ? 'Cancelling…' : 'Cancel bill'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Room Dialog */}
      <Dialog open={showRoomDialog} onOpenChange={setShowRoomDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{editingRoom ? 'Edit Room' : 'Add Room'}</DialogTitle></DialogHeader>
          <form onSubmit={handleSaveRoom} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Room Number *</Label>
                <Input required value={roomForm.room_number} onChange={e => setRoomForm(p => ({ ...p, room_number: e.target.value }))} />
              </div>
              <div>
                <Label>Room Type *</Label>
                <Select value={roomForm.room_type} onValueChange={v => setRoomForm(p => ({ ...p, room_type: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="general">General</SelectItem>
                    <SelectItem value="private">Private</SelectItem>
                    <SelectItem value="icu">ICU</SelectItem>
                    <SelectItem value="emergency">Emergency</SelectItem>
                    <SelectItem value="operation">Operation</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div><Label>Floor</Label><Input value={roomForm.floor} onChange={e => setRoomForm(p => ({ ...p, floor: e.target.value }))} /></div>
              <div><Label>Department</Label><Input value={roomForm.department} onChange={e => setRoomForm(p => ({ ...p, department: e.target.value }))} /></div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div><Label>Bed Count *</Label><Input type="number" min="1" required value={roomForm.bed_count} onChange={e => setRoomForm(p => ({ ...p, bed_count: e.target.value }))} /></div>
              <div><Label>Charge / Day (₹) *</Label><Input type="number" min="0" step="0.01" required value={roomForm.room_charge_per_day} onChange={e => setRoomForm(p => ({ ...p, room_charge_per_day: e.target.value }))} /></div>
            </div>
            <div><Label>Amenities</Label><Input value={roomForm.amenities} onChange={e => setRoomForm(p => ({ ...p, amenities: e.target.value }))} placeholder="AC, TV, Attached Bath..." /></div>
            <Button type="submit" className="w-full" disabled={loading}>{loading ? 'Saving...' : editingRoom ? 'Update Room' : 'Create Room'}</Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* OT Schedule Dialog */}
      <Dialog open={showOTDialog} onOpenChange={setShowOTDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Schedule OT</DialogTitle></DialogHeader>
          <form onSubmit={handleCreateOT} className="space-y-4">
            <div>
              <Label>Patient *</Label>
              <div className="relative">
                <Input placeholder="Search patient..." value={patientSearchQuery}
                  onChange={e => { setPatientSearchQuery(e.target.value); setOtForm(p => ({ ...p, patient_id: '' })); setSelectedPatientName(''); }} />
                {selectedPatientName && otForm.patient_id && <p className="text-sm text-green-600 mt-1">Selected: {selectedPatientName}</p>}
                {patientSearchResults.length > 0 && !otForm.patient_id && (
                  <div className="absolute z-10 w-full bg-white border rounded-lg shadow-lg mt-1 max-h-40 overflow-y-auto">
                    {patientSearchResults.map(p => (
                      <div key={p.id} className="px-3 py-2 hover:bg-gray-100 cursor-pointer text-sm"
                        onClick={() => { setOtForm(prev => ({ ...prev, patient_id: p.id })); setSelectedPatientName(`${p.first_name} ${p.last_name}`); setPatientSearchQuery(''); setPatientSearchResults([]); }}>
                        {p.first_name} {p.last_name} <span className="text-gray-400">{p.phone}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Surgeon *</Label>
                <Select value={otForm.surgeon_id ? String(otForm.surgeon_id) : ''} onValueChange={v => setOtForm(p => ({ ...p, surgeon_id: v }))}>
                  <SelectTrigger><SelectValue placeholder="Select surgeon" /></SelectTrigger>
                  <SelectContent>
                    {doctorsList.map(d => (<SelectItem key={d.id} value={String(d.id)}>Dr. {d.first_name} {d.last_name}</SelectItem>))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-gray-500 mt-1">Surgeon fee auto-fills from their inpatient fee.</p>
              </div>
              <div>
                <Label>Anaesthetist</Label>
                <Select value={otForm.anaesthetist_id ? String(otForm.anaesthetist_id) : ''} onValueChange={v => setOtForm(p => ({ ...p, anaesthetist_id: v }))}>
                  <SelectTrigger><SelectValue placeholder="Optional" /></SelectTrigger>
                  <SelectContent>
                    {doctorsList.map(d => (<SelectItem key={d.id} value={String(d.id)}>Dr. {d.first_name} {d.last_name}</SelectItem>))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-gray-500 mt-1">Anaesthetist fee auto-fills from their inpatient fee.</p>
              </div>
            </div>
            <div>
              <Label>Procedure *</Label>
              {proceduresList.length > 0 && (
                <Select
                  value={otForm.procedure_id ? String(otForm.procedure_id) : ''}
                  onValueChange={v => {
                    const proc = proceduresList.find(p => String(p.id) === v);
                    setOtForm(prev => ({
                      ...prev,
                      procedure_id: v,
                      procedure_name: proc ? proc.name : prev.procedure_name,
                    }));
                  }}
                >
                  <SelectTrigger><SelectValue placeholder="Pick from catalog (or type below for free-text)" /></SelectTrigger>
                  <SelectContent>
                    {proceduresList.map(p => (
                      <SelectItem key={p.id} value={String(p.id)}>
                        {p.name} — ₹{Number(p.default_rate || 0).toFixed(2)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              <Input
                required
                className="mt-2"
                placeholder={proceduresList.length > 0 ? "Or type a custom procedure name" : "Procedure name"}
                value={otForm.procedure_name}
                onChange={e => setOtForm(p => ({ ...p, procedure_name: e.target.value, procedure_id: '' }))}
              />
              {otForm.procedure_id && (
                <p className="text-xs text-green-600 mt-1">Procedure charge will auto-fill from catalog.</p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div><Label>OT Room *</Label><Input required value={otForm.ot_room_number} onChange={e => setOtForm(p => ({ ...p, ot_room_number: e.target.value }))} /></div>
              <div><Label>Duration (min)</Label><Input type="number" min="1" value={otForm.estimated_duration_minutes} onChange={e => setOtForm(p => ({ ...p, estimated_duration_minutes: e.target.value }))} /></div>
            </div>
            <div><Label>Scheduled Date & Time *</Label><Input type="datetime-local" required value={otForm.scheduled_date} onChange={e => setOtForm(p => ({ ...p, scheduled_date: e.target.value }))} /></div>
            <div><Label>Pre-Op Notes</Label><Textarea value={otForm.pre_op_notes} onChange={e => setOtForm(p => ({ ...p, pre_op_notes: e.target.value }))} rows={2} /></div>
            <Button type="submit" className="w-full" disabled={loading || !otForm.patient_id || !otForm.surgeon_id}>
              {loading ? 'Scheduling...' : 'Schedule OT'}
            </Button>
          </form>
        </DialogContent>
      </Dialog>

      {/* Procedure Catalog Dialog */}
      <Dialog open={showProcedureDialog} onOpenChange={(open) => { setShowProcedureDialog(open); if (!open) resetProcedureForm(); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editingProcedure ? 'Edit Procedure' : 'Add Procedure'}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleProcedureSubmit} className="space-y-3">
            <div>
              <Label>Name *</Label>
              <Input required value={procedureForm.name} onChange={e => setProcedureForm(p => ({ ...p, name: e.target.value }))} placeholder="e.g. Appendectomy" />
            </div>
            <div>
              <Label>Default Rate (INR) *</Label>
              <Input
                required
                type="number"
                step="0.01"
                min="0"
                value={procedureForm.default_rate}
                onChange={e => setProcedureForm(p => ({ ...p, default_rate: e.target.value }))}
                placeholder="₹15000"
              />
              <p className="text-xs text-gray-500 mt-1">Auto-fills as the procedure charge when this procedure is selected during OT scheduling. Editable per OT.</p>
            </div>
            <div>
              <Label>Description</Label>
              <Textarea
                rows={2}
                value={procedureForm.description}
                onChange={e => setProcedureForm(p => ({ ...p, description: e.target.value }))}
                placeholder="Optional notes"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button type="button" variant="outline" onClick={() => { setShowProcedureDialog(false); resetProcedureForm(); }}>Cancel</Button>
              <Button type="submit">{editingProcedure ? 'Update' : 'Add'}</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Bed Manager Dialog */}
      <Dialog open={showBedManager} onOpenChange={setShowBedManager}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Manage Beds — {selectedRoomForBeds?.room_number}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="flex gap-2">
              <Input placeholder="Bed label (e.g. A, B, 1, 2)" value={newBedLabel}
                onChange={e => setNewBedLabel(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleAddBed(); }} />
              <Button size="sm" onClick={handleAddBed} disabled={!newBedLabel.trim()}>
                <Plus className="h-4 w-4 mr-1" /> Add
              </Button>
            </div>
            {roomBeds.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-4">No beds configured. Add beds above.</p>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {roomBeds.map(bed => (
                  <div key={bed.id} className="flex items-center justify-between border rounded-lg px-3 py-2">
                    <div className="flex items-center gap-2">
                      <Bed className="h-4 w-4 text-gray-400" />
                      <span className="font-medium text-sm">{bed.bed_label}</span>
                      <Badge className={
                        bed.status === 'available' ? 'bg-green-100 text-green-800' :
                        bed.status === 'occupied' ? 'bg-red-100 text-red-800' :
                        'bg-yellow-100 text-yellow-800'
                      }>{bed.status}</Badge>
                    </div>
                    <div className="flex gap-1">
                      {bed.status === 'available' && (
                        <Button variant="ghost" size="sm" className="text-yellow-600 h-7 text-xs"
                          onClick={() => handleUpdateBedStatus(bed.id, 'maintenance')} title="Set Maintenance">
                          <Clock className="h-3 w-3" />
                        </Button>
                      )}
                      {bed.status === 'maintenance' && (
                        <Button variant="ghost" size="sm" className="text-green-600 h-7 text-xs"
                          onClick={() => handleUpdateBedStatus(bed.id, 'available')} title="Set Available">
                          <Activity className="h-3 w-3" />
                        </Button>
                      )}
                      {!bed.current_admission_id && (
                        <Button variant="ghost" size="sm" className="text-red-500 h-7"
                          onClick={() => handleDeleteBed(bed.id)} title="Delete">
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
            <p className="text-xs text-gray-400">
              {roomBeds.length} bed{roomBeds.length !== 1 ? 's' : ''} total, {roomBeds.filter(b => b.status === 'available').length} available
            </p>
          </div>
        </DialogContent>
      </Dialog>

      {/* Confirm Dialog */}
      <ConfirmDialog open={confirmState.open} title={confirmState.title} message={confirmState.message}
        onConfirm={confirmState.onConfirm} onCancel={() => setConfirmState({ open: false })} />
    </div>
  );
};

export default InpatientModule;
