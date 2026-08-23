import React from 'react';
import { Routes, Route } from 'react-router-dom';
import BillingModule from './BillingModule';
import SalesSummaryPage from './billing/SalesSummaryPage';
import PurchaseSummaryPage from './billing/PurchaseSummaryPage';
import GstReportsPage from './billing/GstReportsPage';
import GstAuditExportPage from './billing/GstAuditExportPage';

/**
 * Top-level Billing hub. Bills stay on the index route so existing
 * /dashboard/billing links keep working; reports live on nested paths.
 */
export default function BillingHub() {
  return (
    <Routes>
      <Route index element={<BillingModule />} />
      <Route path="sales-summary" element={<SalesSummaryPage />} />
      <Route path="purchase-summary" element={<PurchaseSummaryPage />} />
      <Route path="gst" element={<GstReportsPage />} />
      <Route path="gst-export" element={<GstAuditExportPage />} />
      <Route path="*" element={<BillingModule />} />
    </Routes>
  );
}
