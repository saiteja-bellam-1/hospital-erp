# Pharmacy Module Requirements Document

## Overview
This document outlines the functional requirements for the Pharmacy Module to be integrated into the Hospital ERP system. The module handles item management, procurement, and sales processes within a pharmacy setting.

## 1. Item Creation
The system must support the configuration and management of pharmacy products with the following attributes:

### 1.1 Basic Information
* **Core Identifiers**: Item Status (Active/Inactive), Hide option, Barcode generation/scanning.
* **Product Details**: Product Name, Packaging information, Dosage, Unit of Measurement, Decimal support.
* **Organization**: Company, Rack Number, Salt/Composition, Category.

### 1.2 Pricing & Tax Configuration
* **Taxation**: SGST, CGST configuration.
* **Pricing**: Maximum Retail Price (MRP), Purchase Rate (P-Rate), Sale Rates (Rate-A, Rate-B).
* **Costing**: Cost calculation ($P_{CS}$), Strip conversion factors.

### 1.3 Inventory Control
* **Thresholds**: Minimum and Maximum quantity (Min-Max) settings.
* **Alerts**: Maximum Quantity (Max-Qty) tracking.

### 1.4 Regulatory & Special Classification
* **Discounts**: Item-specific discount settings.
* **Schedules**: Tracking for controlled substances (Narcotics, Schedule H, H1, Tramadol).

## 2. Procurement (Purchase)
The system must facilitate the purchase process with the following requirements:

* **Header Details**: Entry Date, Party Selection (Supplier), Invoice Number, Bill Date, Sales Type (Credit/Cash), Purchase Type.
* **Batch Details (via Batch-Details Window)**: 
    * Product Name.
    * Batch Number and Expiry Date.
    * MRP, Quantity, Free Quantity, Purchase Rate.
    * Discount application.
* **Compliance**: HSN code integration.

## 3. Sales
The system must handle pharmacy sales with the following requirements:

### 3.1 Patient & Transaction Details
* **Transaction Info**: Sale Date, Payment Type (Cash or Credit).
* **Patient Info**: Phone Number, IP-ID (In-Patient ID), Name, Address.
* **Doctor Info**: Doctor Number, Doctor Name.

### 3.2 Transaction Items & Batching
* **Product Selection**: Product Station, Batch Station (must support Batch-wise tracking and Barcode scanning).
* **Itemized Details**: Quantity, Free Quantity, Rate, Discount.
* **Pricing**: Dynamic selection between Rate-A and Rate-B.
