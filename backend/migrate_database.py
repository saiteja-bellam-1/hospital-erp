#!/usr/bin/env python3
"""
Database migration script to add new columns and tables for role permissions
"""

import sys
import os
import sqlite3

# Add the backend directory to Python path
sys.path.insert(0, '/Users/saiteja/Documents/GitHub/hospital-ERP/backend')

def migrate_database():
    """Add new columns to existing tables"""
    db_path = '/Users/saiteja/Documents/GitHub/hospital-ERP/backend/kthealth_erp.db'
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🔄 Starting database migration...")
        
        # Add is_system_role column to user_roles table
        try:
            cursor.execute("ALTER TABLE user_roles ADD COLUMN is_system_role BOOLEAN DEFAULT 0")
            print("✓ Added is_system_role column to user_roles")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print("✓ is_system_role column already exists")
            else:
                print(f"❌ Error adding is_system_role column: {e}")
        
        # Create module_permissions table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS module_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_name VARCHAR(50) NOT NULL,
                permission_name VARCHAR(100) NOT NULL,
                permission_description TEXT,
                category VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✓ Created module_permissions table")
        
        # Create role_module_permissions table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS role_module_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role_id INTEGER NOT NULL,
                module_name VARCHAR(50) NOT NULL,
                permissions TEXT,  -- JSON stored as text in SQLite
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (role_id) REFERENCES user_roles (id)
            )
        """)
        print("✓ Created role_module_permissions table")
        
        # Create hospital_settings table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hospital_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setting_category VARCHAR(50) NOT NULL,
                setting_key VARCHAR(100) NOT NULL,
                setting_value TEXT,
                setting_type VARCHAR(20) DEFAULT 'string',
                description TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users (id)
            )
        """)
        print("✓ Created hospital_settings table")
        
        # Create module_templates table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS module_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_name VARCHAR(50) NOT NULL,
                template_name VARCHAR(100) NOT NULL,
                template_type VARCHAR(50) NOT NULL,
                template_data TEXT,  -- JSON stored as text
                is_active BOOLEAN DEFAULT 1,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users (id)
            )
        """)
        print("✓ Created module_templates table")
        
        # Create module_rates table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS module_rates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_name VARCHAR(50) NOT NULL,
                service_name VARCHAR(100) NOT NULL,
                service_code VARCHAR(50),
                base_rate VARCHAR(20),
                discounted_rate VARCHAR(20),
                description TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (created_by) REFERENCES users (id)
            )
        """)
        print("✓ Created module_rates table")
        
        conn.commit()
        conn.close()
        
        print("✅ Database migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Migration error: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()

if __name__ == "__main__":
    migrate_database()