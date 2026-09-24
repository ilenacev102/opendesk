"""Single source of truth for all table schemas."""

EMP_COLS = [
    "EmployeeID",
    "FirstName",
    "LastName",
    "UserName",
    "Email",
    "Department",
    "Organization",
    "Location",
    "Active",
]
DEV_COLS = [
    "AssetID",
    "Type",
    "Manufacturer",
    "Model",
    "SerialNumber",
    "Status",
    "EmployeeID",
    "Location",
    "PurchaseDate",
    "WarrantyUntil",
    "PurchasePrice",
    "Supplier",
    "Notes",
]

OPTIONAL_DEV_COLS = {"PurchasePrice", "Supplier"}

CONS_COLS = [
    "ConsumableID",
    "Name",
    "Category",
    "Quantity",
    "MinLevel",
    "Location",
    "Notes",
]

LIC_COLS = [
    "LicenseID",
    "Software",
    "LicenseKey",
    "Seats",
    "SeatsUsed",
    "ExpiryDate",
    "Supplier",
    "Notes",
]

FIELD_DEF_COLS = [
    "FieldID",
    "FieldName",
]

FIELD_VAL_COLS = [
    "AssetID",
    "FieldID",
    "Value",
]

CONTRACT_COLS = [
    "ContractID",
    "Title",
    "Supplier",
    "ValidUntil",
    "Value",
    "Notes",
]

RESERV_COLS = [
    "ReservationID",
    "AssetID",
    "EmployeeID",
    "FromDate",
    "ToDate",
    "Status",
    "Notes",
]

REQUEST_COLS = [
    "RequestID",
    "EmployeeID",
    "NeedText",
    "Status",
    "Created",
    "DecidedBy",
]

INCIDENT_COLS = [
    "IncidentID",
    "AssetID",
    "EmployeeID",
    "Title",
    "Priority",
    "Status",
    "Assignee",
    "DueDate",
    "Created",
    "ClosedAt",
    "Notes",
]

STAGING_COLS = [
    "SerialNumber",
    "Manufacturer",
    "Model",
    "Hostname",
    "OS",
    "LastSeen",
    "Source",
]

LDAPMAP_COLS = [
    "UserName",
    "DN",
    "LastSync",
]
