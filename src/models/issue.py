"""
Data models for VeritasHR: One Employee, One Truth.
Defines canonical schemas for Golden Records, Inconsistencies, Impact Scores, and Approvals.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class IssueCategory(str, Enum):
    GHOST_RECORD = "GHOST_RECORD"               # Terminated in HR, active in Payroll (cash leakage)
    SECURITY_EXPOSURE = "SECURITY_EXPOSURE"     # Terminated in HR, active in AD (data breach risk)
    DEPARTMENT_CONFLICT = "DEPARTMENT_CONFLICT" # Cost center / Org mismatch
    INVALID_CODE = "INVALID_CODE"               # Code not in standard dictionary
    DATE_MISMATCH = "DATE_MISMATCH"             # Temporal sequence or cross-system date conflict
    DUPLICATE_ENTITY = "DUPLICATE_ENTITY"       # Near/exact duplicate identity
    MISSING_VALUE = "MISSING_VALUE"             # Mandatory field absent (e.g. IBAN)
    REGULATORY_DEFICIT = "REGULATORY_DEFICIT"   # GCAA/WPS non-compliance
    JOB_CONFLICT = "JOB_CONFLICT"               # Job title / role code differs between systems
    STATUS_CONFLICT = "STATUS_CONFLICT"         # Active in HR but inactive/locked downstream
    NAME_CONFLICT = "NAME_CONFLICT"             # Same ID, materially different name across systems
    FIELD_CONFLICT = "FIELD_CONFLICT"           # Any other shared field differs from Core HR (extra sources)

class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MODIFIED = "MODIFIED"

@dataclass
class EvidenceItem:
    system_name: str
    field_name: str
    recorded_value: Any
    timestamp_or_version: Optional[str] = None
    is_authoritative: bool = False

@dataclass
class BlastRadiusNode:
    node_id: str
    node_type: str  # "SYSTEM_FEED" or "EXECUTIVE_REPORT"
    name: str
    impact_description: str
    current_status: str = "AFFECTED"

@dataclass
class QualityIssue:
    issue_id: str
    category: IssueCategory
    severity: Severity
    title: str
    description: str
    primary_entity_id: str
    entity_name: str
    source_systems: List[str]
    fields_in_conflict: List[str]
    evidence_trail: List[EvidenceItem]
    
    # AI-Recommended Fix
    suggested_fix: str
    recommended_target_system: str
    recommended_target_field: str
    recommended_target_value: Any
    confidence_score: float  # 0.0 to 1.0
    rationale: str
    
    # Business Impact & Blast Radius
    impact_score: float  # 0 to 100
    financial_risk_aed: float = 0.0
    security_risk_level: str = "NONE"
    affected_reports: List[str] = field(default_factory=list)
    downstream_nodes: List[BlastRadiusNode] = field(default_factory=list)
    
    # Governance & Human-in-the-Loop
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    reviewer_comments: Optional[str] = None
    approved_by: Optional[str] = None
    reviewed_at: Optional[str] = None

@dataclass
class GoldenEmployeeRecord:
    canonical_id: str
    core_hr_id: Optional[str] = None
    payroll_id: Optional[str] = None
    learning_id: Optional[str] = None
    directory_id: Optional[str] = None
    
    # Canonical Truth Fields
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None
    gender: Optional[str] = None
    nationality: Optional[str] = None
    national_id: Optional[str] = None
    passport_number: Optional[str] = None
    
    department_code: Optional[str] = None
    job_title: Optional[str] = None
    job_grade: Optional[str] = None
    work_location: Optional[str] = None
    employment_status: Optional[str] = None
    hire_date: Optional[str] = None
    termination_date: Optional[str] = None
    
    monthly_basic_aed: Optional[float] = None
    bank_iban: Optional[str] = None
    pay_status: Optional[str] = None
    
    work_email: Optional[str] = None
    ad_account_status: Optional[str] = None
    last_logon_timestamp: Optional[str] = None
    
    aviation_safety_cert: Optional[str] = None
    training_compliance_status: Optional[str] = None

    # Cross-system shadow values used for conflict checks
    payroll_cost_center: Optional[str] = None
    payroll_effective_start_date: Optional[str] = None
    payroll_effective_start_iso: Optional[str] = None
    learning_department: Optional[str] = None
    learning_job_role: Optional[str] = None
    source_names: Dict[str, str] = field(default_factory=dict)
    link_methods: Dict[str, str] = field(default_factory=dict)
    
    # Quality Metadata
    linkage_confidence: float = 1.0
    discrepancy_count: int = 0
    issues: List[QualityIssue] = field(default_factory=list)
