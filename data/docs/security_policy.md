# Information Security Policy

*Acme Outfitters — Effective January 1, 2025. Applies to all employees, contractors, and vendors with access to Acme systems or data.*

## Purpose and Scope

This policy defines Acme Outfitters' requirements for protecting company and customer data, securing systems and devices, and responding to security incidents. All employees, contractors, and third-party vendors with access to Acme Outfitters systems are required to comply with this policy.

Violations of this policy may result in disciplinary action up to and including termination, and may be reported to law enforcement in the case of criminal activity.

---

## Data Classification

Acme Outfitters classifies data into four tiers that determine handling, storage, and sharing requirements.

### Tier 1 — Public

Information intended for public consumption. No special handling required.

Examples: marketing copy, published product specs, public-facing pricing, press releases.

### Tier 2 — Internal

Information used in the normal course of business that is not intended for outside parties but whose disclosure would cause minimal harm.

Examples: employee directory, internal meeting notes, org chart, general process documentation.

### Tier 3 — Confidential

Sensitive business information whose unauthorized disclosure could cause material harm to Acme Outfitters or its partners.

Examples: customer PII (names, emails, phone numbers, addresses), order history, invoices, employee compensation data, contracts, financial forecasts, product roadmaps.

**Handling requirements:** Must be stored in approved systems only (see §Approved Systems); may not be sent via personal email; must be encrypted at rest and in transit; access requires a legitimate business need.

### Tier 4 — Restricted

Highly sensitive information whose disclosure could result in legal liability, fraud, or severe reputational damage.

Examples: payment card data (PAN, CVV), full social security numbers, authentication credentials (passwords, API keys, tokens), medical records, litigation materials.

**Handling requirements:** All Tier 3 requirements apply. Additionally: access is need-to-know only with manager approval; must not be stored in chat, email, or code repositories; PCI-DSS and applicable privacy regulations apply.

---

## Password and Authentication Requirements

### Password Policy

All Acme system passwords must meet the following requirements:
- Minimum 16 characters
- Contain at least one uppercase letter, one lowercase letter, one digit, and one special character
- Must not be a previously used password (last 12 passwords are blocked)
- Must not contain the user's name, email, or "acme" in any variation
- Must be changed every **180 days** for standard accounts; every **90 days** for privileged/admin accounts

Employees must use the company-approved password manager (**1Password Teams**) to store and generate passwords. Passwords must not be stored in plaintext (spreadsheets, text files, email, Slack).

### Multi-Factor Authentication (MFA)

MFA is required for all Acme Outfitters systems accessible outside the corporate network. Acceptable MFA methods, in order of preference:

1. **Hardware security key (YubiKey)** — required for Engineering, Finance, and IT roles; strongly recommended for all others
2. **TOTP authenticator app** (Google Authenticator, Duo, Authy) — acceptable for all roles
3. **SMS OTP** — permitted as a fallback only; not to be used as primary MFA method

Backup codes must be stored in 1Password, not in personal email or local files.

### Shared Credentials

Shared credentials (e.g., a service account used by a team) must be stored in a 1Password shared vault with access granted only to individuals with a business need. Shared credentials must not be distributed over Slack, email, or other communication channels.

---

## Device Security

### Company-Issued Devices

All company-issued laptops must have:
- **Full-disk encryption** enabled (FileVault on macOS; BitLocker on Windows). IT verifies this via Jamf MDM upon enrollment.
- **Jamf MDM enrollment** completed within 24 hours of receiving the device.
- **Automatic OS updates** enabled; major OS upgrades must be applied within 30 days of availability.
- **Screen lock** set to activate after no more than 5 minutes of inactivity; password required to unlock.
- **Antivirus/EDR** (CrowdStrike Falcon) installed and active; do not disable or quarantine the CrowdStrike agent.

### Personal Devices (BYOD)

Personal devices may be used to access Acme email and Slack only, subject to the following:
- Jamf MDM enrollment is required for access to Google Workspace on personal devices.
- Full-disk encryption must be enabled.
- Personal devices must not be used to access Tier 3 or Tier 4 data.
- Personal devices used for work may be subject to a remote wipe of the Acme-managed partition only (not personal data) if lost or stolen.

### Mobile Devices

Company-issued mobile phones follow the same policy as laptops. Employees using personal phones for Slack or email must have device PIN/biometric lock enabled and the Acme MDM profile installed.

---

## Network and Remote Access

### Corporate Network

When on a corporate network (Acme office or DC), employees may access all authorized internal systems directly. Do not connect personal devices to the corporate network without IT approval.

### Remote Access (VPN)

Remote access to internal systems that are not exposed to the internet requires connection through Acme's VPN (Tailscale). VPN client must be installed on all Acme-managed laptops. VPN is always-on for Engineering and IT access to production infrastructure.

### Public Wi-Fi

Employees must use the VPN when working on public Wi-Fi (coffee shops, airports, hotels). Do not access Tier 3 or Tier 4 data on public Wi-Fi without VPN active.

---

## Acceptable Use

### Approved Systems

Tier 3 and Tier 4 data may only be stored and processed in systems approved by IT Security. Approved systems include: Google Workspace (Drive with DLP enabled), Salesforce, Zendesk, NetSuite, and the Acme internal databases. Data must not be stored in personal cloud storage (personal Google Drive, Dropbox, iCloud) or in unapproved SaaS tools.

### Prohibited Actions

- Installing unapproved software on company devices (use the Jamf Self Service catalog or submit a software request to IT)
- Sharing Tier 3 or Tier 4 data via personal email accounts
- Using AI assistant tools (ChatGPT, external Claude.ai, etc.) to process customer PII or Tier 4 data — the company's approved AI tool is Querious, which processes data within the Acme environment
- Using company systems for personal commercial activity or for activities that violate the Code of Conduct

---

## Security Incident Reporting

### What to Report

Employees must report any of the following immediately:
- Lost or stolen company device or YubiKey
- Suspected phishing email (forward to phishing@acmeoutfitters.example before deleting)
- Accidental sharing of customer PII or payment data with an unauthorized party
- Unusual account activity (unexpected password-reset emails, logins from unknown locations)
- Discovery of credentials, API keys, or sensitive data in a public repository or communication channel

### How to Report

**Email:** security@acmeoutfitters.example (monitored 24/7)

**Slack:** #security-incidents (monitored during business hours; use email for after-hours emergencies)

**Phone:** For urgent after-hours incidents, call the IT on-call line at the number posted in the #security-incidents Slack channel topic.

Do not attempt to investigate or remediate a suspected breach on your own. Report it and follow the guidance of the Security team.

### Incident Response Timeline

Upon receiving an incident report, the Security team will:
1. Acknowledge receipt within **1 hour** (business hours) / **2 hours** (after-hours)
2. Begin triage and containment within **4 hours** of acknowledgement
3. Provide an initial status update to affected parties and senior leadership within **24 hours**
4. Complete a post-incident review and remediation report within **14 days** of resolution

---

## Third-Party and Vendor Security

Vendors with access to Acme systems or Tier 3/4 data must sign the Acme Vendor Security Addendum before receiving any access. The addendum requires: data-handling commitments consistent with this policy, prompt incident notification (within 24 hours of discovering a breach), and the right for Acme to audit compliance annually.

Vendor access must be provisioned with least-privilege principles; access must be revoked immediately upon contract termination.
