#!/usr/bin/env python3
"""OpenDesk Demo Data Generator.

Populates the OpenDesk database with realistic enterprise data:
- Departments & Locations
- Employees across Engineering, Product, HR, Finance
- IT Assets (Laptops, Monitors, Servers, Switches, Printers)
- Active Assignments with history records
- ServiceDesk Incidents with varying SLA priorities and comments
- Software Licenses & Contracts
"""

import datetime
import os
import sys

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import (  # noqa: E402
    assign_svc,
    departments,
    devices,
    employees,
    incidents,
    licenses,
    locations,
)


def run_seed():
    print("🌱 Seeding OpenDesk demo dataset...")

    # 1. Locations
    locs = [
        {"LocationID": "LOC-HQ", "Name": "Global Headquarters", "Address": "Silicon Blvd 101, San Francisco"},
        {"LocationID": "LOC-EU", "Name": "European Tech Hub", "Address": "Alexanderplatz 4, Berlin"},
        {"LocationID": "LOC-MK", "Name": "Skopje Development Center", "Address": "Partizanski Odredi 12, Skopje"},
        {"LocationID": "LOC-DC", "Name": "Primary Data Center", "Address": "Equinix SV1, San Jose"},
    ]
    for loc in locs:
        if not locations.find("LocationID", loc["LocationID"]):
            locations.insert(loc)
    print(f"✓ Locations ready ({len(locs)})")

    # 2. Departments
    depts = [
        {"DepartmentID": "DEP-ENG", "Name": "Engineering & DevOps"},
        {"DepartmentID": "DEP-IT", "Name": "IT Infrastructure & Security"},
        {"DepartmentID": "DEP-HR", "Name": "People Operations (HR)"},
        {"DepartmentID": "DEP-FIN", "Name": "Finance & Legal"},
    ]
    for dept in depts:
        if not departments.find("DepartmentID", dept["DepartmentID"]):
            departments.insert(dept)
    print(f"✓ Departments ready ({len(depts)})")

    # 3. Employees
    emps = [
        {"EmployeeID": "EMP-001", "FullName": "Sarah Connor", "Email": "sarah.connor@example.com", "Department": "DEP-IT", "Position": "Lead Systems Engineer", "Location": "LOC-HQ", "Active": "YES"},
        {"EmployeeID": "EMP-002", "FullName": "Alex Murphy", "Email": "alex.murphy@example.com", "Department": "DEP-ENG", "Position": "Senior Backend Developer", "Location": "LOC-EU", "Active": "YES"},
        {"EmployeeID": "EMP-003", "FullName": "Elena Vance", "Email": "elena.vance@example.com", "Department": "DEP-ENG", "Position": "Site Reliability Engineer", "Location": "LOC-MK", "Active": "YES"},
        {"EmployeeID": "EMP-004", "FullName": "Gordon Freeman", "Email": "gordon.freeman@example.com", "Department": "DEP-IT", "Position": "Network Architect", "Location": "LOC-HQ", "Active": "YES"},
        {"EmployeeID": "EMP-005", "FullName": "Marcus Brody", "Email": "marcus.brody@example.com", "Department": "DEP-FIN", "Position": "Chief Financial Officer", "Location": "LOC-EU", "Active": "YES"},
        {"EmployeeID": "EMP-006", "FullName": "Ripley Ellen", "Email": "ripley.ellen@example.com", "Department": "DEP-HR", "Position": "VP of People Operations", "Location": "LOC-HQ", "Active": "YES"},
    ]
    for emp in emps:
        if not employees.find("EmployeeID", emp["EmployeeID"]):
            employees.insert(emp)
    print(f"✓ Employees ready ({len(emps)})")

    # 4. Hardware Devices
    today = datetime.date.today()
    dev_specs = [
        {"AssetID": "LAP-1001", "Type": "Laptop", "Manufacturer": "Apple", "Model": "MacBook Pro 16 M3 Max", "SerialNumber": "C02G1001M3X", "Status": "Available", "Location": "LOC-HQ", "WarrantyUntil": str(today + datetime.timedelta(days=730)), "PurchasePrice": "3499.00"},
        {"AssetID": "LAP-1002", "Type": "Laptop", "Manufacturer": "Apple", "Model": "MacBook Pro 14 M3 Pro", "SerialNumber": "C02G1002M3P", "Status": "Available", "Location": "LOC-EU", "WarrantyUntil": str(today + datetime.timedelta(days=540)), "PurchasePrice": "2399.00"},
        {"AssetID": "LAP-1003", "Type": "Laptop", "Manufacturer": "Lenovo", "Model": "ThinkPad P1 Gen 6", "SerialNumber": "PF3001THK", "Status": "Available", "Location": "LOC-MK", "WarrantyUntil": str(today + datetime.timedelta(days=400)), "PurchasePrice": "2150.00"},
        {"AssetID": "LAP-1004", "Type": "Laptop", "Manufacturer": "Dell", "Model": "XPS 15 9530", "SerialNumber": "DLXPS953001", "Status": "Available", "Location": "LOC-HQ", "WarrantyUntil": str(today + datetime.timedelta(days=120)), "PurchasePrice": "1999.00"},
        {"AssetID": "MON-2001", "Type": "Monitor", "Manufacturer": "Dell", "Model": "UltraSharp U2723QE 4K", "SerialNumber": "CN092001DL", "Status": "Available", "Location": "LOC-HQ", "WarrantyUntil": str(today + datetime.timedelta(days=600)), "PurchasePrice": "550.00"},
        {"AssetID": "MON-2002", "Type": "Monitor", "Manufacturer": "LG", "Model": "34WN80C-B UltraWide", "SerialNumber": "LG34WN8002", "Status": "Available", "Location": "LOC-EU", "WarrantyUntil": str(today + datetime.timedelta(days=450)), "PurchasePrice": "620.00"},
        {"AssetID": "SRV-3001", "Type": "Server", "Manufacturer": "HPE", "Model": "ProLiant DL380 Gen10", "SerialNumber": "HPEDL380G1001", "Status": "Available", "Location": "LOC-DC", "WarrantyUntil": str(today + datetime.timedelta(days=365)), "PurchasePrice": "8900.00"},
        {"AssetID": "NET-4001", "Type": "Switch", "Manufacturer": "Cisco", "Model": "Catalyst 9300 48P PoE+", "SerialNumber": "FOC22001CSC", "Status": "Available", "Location": "LOC-DC", "WarrantyUntil": str(today + datetime.timedelta(days=800)), "PurchasePrice": "4200.00"},
    ]
    for dev in dev_specs:
        if not devices.find("AssetID", dev["AssetID"]):
            devices.insert(dev)
    print(f"✓ Hardware devices catalog ready ({len(dev_specs)})")

    # 5. Assign Devices to Employees (Using official assignment service with audit logs)
    assignments = [
        ("LAP-1001", "EMP-001", "Primary Engineering Workstation"),
        ("LAP-1002", "EMP-002", "Developer Onboarding Kit"),
        ("LAP-1003", "EMP-003", "DevOps Machine"),
    ]
    for asset_id, emp_id, reason in assignments:
        d = devices.find("AssetID", asset_id)
        if d and d.get("Status") == "Available":
            try:
                assign_svc.confirm(asset_id, emp_id, reason, "Seeded demo assignment", "admin")
                print(f"  → Assigned {asset_id} to {emp_id}")
            except Exception as e:
                print(f"  Notice: could not assign {asset_id}: {e}")

    # 6. ServiceDesk Incidents
    incs = [
        {
            "IncidentID": "INC-0001",
            "Subject": "VPN connection drops after macOS Sonoma 14.4 upgrade",
            "Requester": "Alex Murphy",
            "Priority": "High",
            "Status": "In Progress",
            "Category": "Network / VPN",
            "Description": "Whenever connected to European Tech Hub VPN, WireGuard tunnel resets every 15 minutes.",
            "CreatedAt": str(today - datetime.timedelta(days=2)),
            "SlaHours": "8",
            "Assignee": "Sarah Connor",
        },
        {
            "IncidentID": "INC-0002",
            "Subject": "Request for second 4K monitor approval",
            "Requester": "Elena Vance",
            "Priority": "Low",
            "Status": "Open",
            "Category": "Hardware Request",
            "Description": "Requesting dual Dell UltraSharp setup for multi-cluster Kubernetes monitoring.",
            "CreatedAt": str(today - datetime.timedelta(days=1)),
            "SlaHours": "24",
            "Assignee": "Gordon Freeman",
        },
        {
            "IncidentID": "INC-0003",
            "Subject": "Data Center Core Switch B PSU Alert",
            "Requester": "System Agent",
            "Priority": "Urgent",
            "Status": "Resolved",
            "Category": "Infrastructure",
            "Description": "SNMP trap received: Redundant Power Supply 2 lost AC power. Unit swapped and operational.",
            "CreatedAt": str(today - datetime.timedelta(days=5)),
            "SlaHours": "2",
            "Assignee": "Gordon Freeman",
        },
    ]
    for inc in incs:
        if not incidents.find("IncidentID", inc["IncidentID"]):
            incidents.insert(inc)
    print(f"✓ ServiceDesk incidents ready ({len(incs)})")

    # 7. Software Licenses & Contracts
    lics = [
        {"LicenseID": "LIC-001", "Name": "JetBrains All Products Pack", "Vendor": "JetBrains", "Seats": "25", "SeatsUsed": "18", "ExpiresAt": str(today + datetime.timedelta(days=280))},
        {"LicenseID": "LIC-002", "Name": "1Password Business Enterprise", "Vendor": "AgileBits", "Seats": "100", "SeatsUsed": "84", "ExpiresAt": str(today + datetime.timedelta(days=180))},
        {"LicenseID": "LIC-003", "Name": "Microsoft 365 E5", "Vendor": "Microsoft", "Seats": "50", "SeatsUsed": "48", "ExpiresAt": str(today + datetime.timedelta(days=320))},
    ]
    for lic in lics:
        if not licenses.find("LicenseID", lic["LicenseID"]):
            licenses.insert(lic)
    print(f"✓ Software licenses catalog ready ({len(lics)})")

    print("\n🎉 Demo dataset successfully populated!")


if __name__ == "__main__":
    run_seed()
