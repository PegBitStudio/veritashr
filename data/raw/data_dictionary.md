# Emirates Group HR Data Quality Challenge - Data Dictionary

This document defines the fields, formats, systems of record, and valid reference code lists for the Emirates Group HR ecosystem.

---

## 1. Systems Overview

| System Name | System Role | Primary Identifier | Key Managed Attributes |
| :--- | :--- | :--- | :--- |
| **Core HR** | System of Record for master employment | `employee_id` (`EK#####`) | Master employment status, official grade, job title, department, hire/term dates, personal identity. |
| **Payroll** | Disbursement & UAE WPS Compliance | `payroll_id` (`PR-#####`) | Monthly basic salary, bank IBAN, cost centers, payment frequency, pay status. |
| **Learning (LMS)** | Training & Mandatory Certifications | `lms_user_id` (`LMS-#####`) | GCAA aviation safety certifications, recurrent flight crew training, learning tracks. |
| **Access Directory** | IT Identity & Access Management (IAM) | `samaccountname` | Corporate work email, active directory account status, security badge ID, last logon timestamp. |

---

## 2. Standard Reference Codes

### Departments (`department_code`)
- `EK-FLIGHT-OPS`: Flight Operations (Pilots & Flight Deck Crew)
- `EK-CABIN-CREW`: In-flight Service & Cabin Crew
- `EK-ENG`: Engineering, Line Maintenance & Fleet Airworthiness
- `EK-AIRPORT-SVCS`: Airport Operations, Passenger Terminal 3 Services
- `EK-COMMERCIAL`: Commercial Strategy, Revenue Optimization & Global Sales
- `EK-IT`: Group IT, Cloud Infrastructure & Digital Architecture
- `EK-HR`: Group Human Resources & Talent Management
- `DNATA-GROUND-SVCS`: Dnata Ground Operations, Ramp & Baggage
- `DNATA-CARGO`: Dnata Cargo Handling & Freight Logistics
- `DNATA-TRAVEL`: Dnata Retail, Corporate & Leisure Travel

### Job Grades (`job_grade`)
- Ground & Professional Staff: `G01` to `G12`
- Flight Deck & Cabin Technical: `CR01` to `CR06`
- Engineering & Aircraft Tech: `T01` to `T08`
- Executive Leadership: `E01` to `E05`

### Primary Work Locations (`work_location`)
- `DXB-HQ`: Emirates Group Headquarters, Dubai
- `DXB-T3`: Dubai International Airport Terminal 3
- `DWC-ALMAKTOUM`: Al Maktoum International Airport / Dubai South Hub
- `AUH-HUB`: Abu Dhabi International Hub
- `LHR-STATION`: London Heathrow Outstation
- `JFK-STATION`: New York JFK Outstation
- `SIN-STATION`: Singapore Changi Outstation

### Status Codes
- Core HR: `ACTIVE`, `ON_LEAVE`, `TERMINATED`, `RESIGNED`, `SUSPENDED`
- Payroll: `ACTIVE`, `INACTIVE`, `HOLD`
- Access Directory: `Active`, `Disabled`

### Format Standards
- Core HR Dates: `YYYY-MM-DD` (e.g. `2024-03-15`)
- Payroll Dates: `DD/MM/YYYY` (e.g. `15/03/2024`)
- Access Directory Timestamp: `YYYY-MM-DD HH:MM:SS`
- UAE IBAN: Standard 23-character format: `AE` + 2 check digits + 3 bank alphanumeric characters + 16 numeric digits.
