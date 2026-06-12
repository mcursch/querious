# Security Policy — Acme Outfitters

*Effective: January 2026. Owner: Engineering / IT Security. Review cycle: Annual.*
*Questions or to report a security incident: security@acmeoutfitters.example*

---

## Purpose & Scope

This policy establishes Acme Outfitters' requirements for protecting company data, customer information, and internal systems. It applies to all employees, contractors, and third parties with access to Acme systems, data, or facilities. Violation of this policy may result in disciplinary action up to and including termination and referral to law enforcement where applicable.

---

## 1. Data Classification

Acme Outfitters classifies data into four tiers:

| Classification | Definition | Examples |
|---|---|---|
| **Public** | Approved for unrestricted external use | Marketing materials, product catalog, published job postings |
| **Internal** | For employees only; not for external sharing without approval | Internal documentation, org charts, process guides, this policy |
| **Confidential** | Sensitive business data requiring access controls | Customer PII, financial records, contracts, pricing, source code |
| **Restricted** | Highest sensitivity; strict need-to-know | Payment card data, credentials, security audit reports, M&A data |

All customer data (names, emails, order history, billing addresses) is classified as **Confidential** at minimum. Payment card numbers and bank account details are **Restricted** and must never be stored in company systems other than the designated payment processor.

---

## 2. Password & Authentication Requirements

### Password Standards

All passwords used for Acme systems must meet these minimum requirements:

- **Minimum length: 14 characters**
- Must contain at least one uppercase letter, one lowercase letter, one number, and one special character
- Must not be a previously used password (last 12 passwords are blocked)
- Must not contain your name, username, or the word "Acme"
- Must be changed if there is any reason to believe it has been compromised

Do not reuse Acme passwords for personal accounts. Do not share passwords with colleagues under any circumstances — even temporarily.

### Multi-Factor Authentication (MFA)

MFA is **required** for:
- Google Workspace (email, Drive, Calendar)
- Salesforce
- GitHub
- AWS Console (Engineering staff)
- VPN access

Preferred MFA methods, in order of preference: hardware security key (YubiKey), authenticator app (Google Authenticator, Authy), and SMS (least preferred; avoid if possible due to SIM-swap risk).

### Password Manager

All employees are encouraged to use an approved password manager. Acme provides 1Password Business licenses to all employees at no cost — request via IT.

---

## 3. Device Policy

### Company-Issued Devices

Company-issued laptops and mobile devices are provided for business use. The following rules apply:

- Full-disk encryption must be enabled (FileVault on macOS, BitLocker on Windows). IT verifies this during device setup; employees may not disable it.
- The device must be configured to lock after **5 minutes** of inactivity.
- Operating system and security patches must be applied within **72 hours** of release.
- Do not install unauthorized software. Submit software requests to IT via the helpdesk portal.
- Do not connect company devices to unknown or public WiFi without using the Acme VPN.

### Personal Devices (BYOD)

Personal devices may be used to access Acme email and Slack in read-only capacity. Personal devices **must not** be used to download, store, or process Confidential or Restricted data. If your role requires access to customer data or source code, you must use a company-issued device.

### Lost or Stolen Devices

Report lost or stolen company devices to IT **immediately** — do not wait. IT will initiate a remote wipe. Delay in reporting may result in disciplinary action if a data breach results. To report: call IT emergency line (extension 5911) or email security@acmeoutfitters.example.

---

## 4. Data Handling

### Customer Data

Customer data (PII) may only be accessed for legitimate business purposes. Do not query, export, or share customer data beyond what is needed for your current task. Do not export customer lists for external purposes without written approval from your VP and the Security team.

Customer data may not be stored in personal Google Drive folders, Dropbox, personal USB drives, or any cloud service not approved by IT.

### Data Retention

Data must be retained for the following minimum periods and deleted or archived after:

| Data Type | Minimum Retention | Maximum Retention |
|---|---|---|
| Customer orders & invoices | 7 years (tax compliance) | 10 years |
| Employee HR records | Duration of employment + 7 years | — |
| Support tickets | 3 years | 5 years |
| Security logs | 1 year | 2 years |
| Marketing / analytics data | 2 years | 3 years |

Requests to delete customer data (e.g., per CCPA or GDPR right-to-erasure) must be routed to Engineering via the privacy@acmeoutfitters.example alias, who will coordinate with Finance and Legal to determine whether retention requirements override the deletion request.

### Secure Disposal

Before disposing of any device or media (hard drives, USB drives, printed documents), ensure:
- Devices: IT performs a certified wipe or physical destruction
- Printed documents: Shred in cross-cut shredder; shredding bins are available in all offices

---

## 5. Network & Access Control

### VPN

All employees accessing internal systems from outside the office must use the Acme VPN. VPN credentials are provisioned by IT during onboarding. Do not share VPN credentials.

### Principle of Least Privilege

Employees should only have access to the systems and data required for their specific role. Access requests are submitted through IT. Access is reviewed quarterly by IT and department heads; unused access is revoked.

### Vendor & Third-Party Access

Third-party vendors requiring access to Acme systems must sign the Acme Data Processing Agreement (DPA) before access is granted. Vendor access is time-limited, scoped to the minimum necessary systems, and revoked immediately upon engagement end.

---

## 6. Incident Reporting

### What to Report

Report any of the following immediately:
- Suspected or confirmed unauthorized access to Acme systems or data
- Lost or stolen device containing Acme data
- Phishing email (whether or not you clicked)
- Unusual system behavior suggesting malware or compromise
- Accidental data disclosure (e.g., email sent to wrong recipient containing customer data)

**When in doubt, report it.** False alarms are not penalized. Unreported incidents that later become breaches may result in disciplinary action.

### How to Report

1. **Email:** security@acmeoutfitters.example (monitored 24/7 by on-call rotation)
2. **Phone:** IT security hotline — extension 5911 (internal) or ask the receptionist (external)
3. **Slack:** #security-incidents channel — use @here for urgent issues outside business hours

### Incident Response

The Security team will acknowledge reports within **1 hour** and begin triage. Employees are expected to cooperate fully with any investigation, including preserving all potentially relevant communications and refraining from further use of compromised accounts or devices.

---

## 7. Acceptable Use

Company systems are provided for business purposes. Incidental personal use is acceptable provided it does not:
- Violate any law or Acme policy
- Consume excessive bandwidth or storage
- Expose the company to legal liability (e.g., downloading copyrighted content, accessing inappropriate sites)
- Interfere with your job responsibilities

Acme may monitor usage of company systems and networks for security purposes. Employees should have no expectation of privacy on company-owned devices or networks.

---

## 8. Physical Security

- Badge access is required to enter all Acme office and warehouse locations. Do not hold doors open for unknown individuals (tailgating).
- Visitor badges must be issued by reception and worn visibly. Escort all visitors at all times.
- Clear-desk policy applies in open office areas: do not leave printed confidential documents unattended at your desk.
- Lock your workstation screen when stepping away (keyboard shortcut: Windows+L on Windows, Control+Command+Q on Mac).
