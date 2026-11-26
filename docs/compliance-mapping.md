# Compliance mapping

> **Disclaimer.** NovaBank Digital is a synthetic portfolio project. The
> mappings below express design intent; they are not an assessment and no
> compliance, certification or regulatory approval is claimed. No cardholder
> data or nonpublic personal information is processed. Requirement
> identifiers must be re-verified against the authoritative publications
> before reuse.

Source: [`policies/compliance-mapping.yaml`](../policies/compliance-mapping.yaml).

| Control | NIST 800-53 r5 | PCI DSS 4.0.1 | CIS AWS 3.0 | SOC 2 TSC | OWASP API 2023 |
|---|---|---|---|---|---|
| 001 Authentication | IA-2, IA-5, IA-8 | 8.2, 8.3 | | CC6.1 | API2 |
| 002 MFA | IA-2(1), IA-2(2) | 8.4 | 1.10 | CC6.1 | |
| 003 API authorization | AC-3, AC-6 | 7.2 | | CC6.1, CC6.3 | API5 |
| 004 Object ownership | AC-3, AC-4 | 7.2 | | CC6.1 | API1, API3 |
| 005 Privileged ops / SoD | AC-5, AC-6 | 7.2 | | CC6.3 | API5, API6 |
| 006 Encryption at rest | SC-28, SC-12 | 3.5 | 2.1.1, 2.3.1 | CC6.1 | |
| 007 Transport security | SC-8, SC-13 | 4.2 | 2.1.1 | CC6.7 | |
| 008 Transaction integrity | SI-7, SI-10 | | | PI1.2, PI1.3 | API6 |
| 009 Duplicate prevention | SI-10 | | | PI1.3 | |
| 010 Fraud screening | SI-4, AC-5 | | | CC7.2 | API6 |
| 011 Secrets | IA-5, SC-12 | 8.3.2 | | CC6.1 | |
| 012 Audit evidence | AU-2, AU-9, AU-10, AU-12 | 10.2, 10.3 | | CC7.2 | |
| 013 Infrastructure security | CM-2, CM-6, RA-5 | 6.3, 11.3 | | CC7.1, CC8.1 | API8 |
| 014 Application security | SA-11, RA-5, SI-10 | 6.2, 6.3 | | CC8.1 | |
| 015 Supply chain | SR-3, SR-4, SR-11, CM-8 | 6.3.2 | | CC8.1 | API10 |
| 016 Deployment authorization | CM-3, CM-5 | 6.5 | | CC8.1 | |
| 017 Cloud identity | AC-2, AC-6, IA-5 | 7.2, 8.6 | 1.16 | CC6.2, CC6.3 | |
| 018 Data recovery | CP-9, CP-10 | 12.10 | | A1.2, A1.3 | |
| 019 Abuse prevention | SC-5 | | | A1.1 | API4 |
| 020 Security monitoring | SI-4, AU-6, IR-4 | 10.4, 10.7 | 3.1 | CC7.2, CC7.3 | API9 |

## Financial-sector considerations (not claims)
* **GLBA Safeguards Rule** themes — access control, encryption, monitoring, incident response,
  service-provider oversight — are reflected in the controls; no NPI is collected.
* **FFIEC IT Examination Handbook** themes — authentication, change management, business
  continuity, audit trails — informed the runbooks, ADRs and CI/CD controls.
