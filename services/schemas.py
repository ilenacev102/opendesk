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
    "NextAuditDate",
]

OPTIONAL_DEV_COLS = {"PurchasePrice", "Supplier"}

TRANSIT_COLS = [
    "TransitID",
    "DateTime",
    "AssetID",
    "FromLoc",
    "ToLoc",
    "ByUser",
]

ONBOARD_COLS = [
    "RequestID",
    "FullName",
    "Position",
    "StartDate",
    "Package",
    "RequestedBy",
]

NOTIF_COLS = [
    "NotifID",
    "UserName",
    "Kind",
    "RefID",
    "Text",
    "Created",
    "ReadAt",
]

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
    "LinkedTo",
    "Satisfaction",
    "ProjectID",
    "TypeID",
    "EpicLink",
    "StoryPoints",
    "SprintID",
    "Rank",
    "FixVersion",
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

SLA_POLICY_COLS = [
    "PolicyID",
    "Priority",
    "WarnHours",
    "BreachHours",
    "Active",
]

KB_COLS = [
    "ArticleID",
    "Title",
    "Body",
    "Tags",
    "Created",
    "Updated",
]

COMMENT_COLS = [
    "CommentID",
    "IncidentID",
    "Author",
    "Body",
    "Created",
]

KB_LINK_COLS = [
    "ArticleID",
    "IncidentID",
]

PROJECT_COLS = [
    "ProjectID",
    "Name",
    "Key",
    "Lead",
    "Description",
    "Status",
    "Created",
    "Updated",
]

ISSUE_TYPE_COLS = [
    "TypeID",
    "ProjectID",
    "Name",
    "Icon",
    "DefaultPriority",
    "Workflow",
    "Active",
]


KB_RATING_COLS = ["ArticleID", "UserName", "Score"]

WATCHER_COLS = ["IncidentID", "UserName", "AddedAt"]

WORKLOG_COLS = [
    "WorklogID",
    "IncidentID",
    "UserName",
    "Minutes",
    "WorkedDate",
    "Note",
]

VERSION_COLS = ["VersionID", "ProjectID", "Name", "ReleasedAt", "Status"]

SPRINT_COLS = [
    "SprintID",
    "ProjectID",
    "Name",
    "Goal",
    "StartDate",
    "EndDate",
    "Status",
    "Created",
]
