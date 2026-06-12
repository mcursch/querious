# Security Policy

## Purpose

This policy protects Acme Outfitters' systems, data, and customers. All employees, contractors,
and vendors with access to company systems must comply. Violations may result in disciplinary
action up to and including termination and legal action.

## Data Classification

| Class | Description | Examples |
|---|---|---|
| **Public** | May be shared externally | Product descriptions, pricing (public), job postings |
| **Internal** | For employees only | Internal procedures, org charts, project plans |
| **Confidential** | Restricted; need-to-know | Customer PII, financial data, contract terms |
| **Restricted** | Highly sensitive; explicit authorization required | Payment card data, credentials, security configs |

Customer names, emails, phone numbers, addresses, and order history are **Confidential**.
Payment card numbers are **Restricted** and must never be stored in company systems (we use
Stripe tokenization exclusively).

## Password & Authentication Requirements

### Password Policy

- Minimum 12 characters
- Must include uppercase, lowercase, digits, and a special character
- Do not reuse the last 10 passwords
- Passwords expire every 180 days (critical systems: 90 days)
- No sharing of passwords under any circumstances

### Multi-Factor Authentication (MFA)

MFA via authenticator app (Google Authenticator, Authy) is required for:
- Google Workspace
- Salesforce
- AWS
- GitHub
- Any system accessible from outside the office network

SMS-based MFA is acceptable only where authenticator apps are not supported.

### Password Manager

Use 1Password for all work accounts. Contact IT for a license. Store all credentials
in 1Password — do not store in browser autofill, Slack, email, or spreadsheets.

## Device Security

- Company laptops must have full-disk encryption enabled (FileVault on Mac, BitLocker on Windows).
- Screen lock activates after 5 minutes of inactivity; password required to unlock.
- Do not install unauthorized software on company devices.
- Personal devices used for work (BYOD) must have MDM enrolled — contact IT.
- Lost or stolen devices must be reported to IT within 1 hour for remote wipe.

## Network Security

- Do not use public Wi-Fi for work without a VPN (use Tailscale; IT will provision).
- Do not connect unauthorized devices to the office network.
- Guest Wi-Fi (SSID: AcmeGuest) is for non-company devices only.

## Access Control

- Access follows the principle of least privilege — request only the access you need.
- All access is reviewed quarterly; unused access is revoked.
- Employees leaving the company have all access revoked on their last day.
- Do not share login credentials with colleagues — request separate accounts via IT.
- Do not access customer data beyond what is required for your role.

## Acceptable Use

Acceptable:
- Work tasks on company systems
- Incidental personal use during non-work hours (brief)
- Using approved SaaS tools from the approved software list

Not acceptable:
- Storing confidential company data on personal cloud drives (Google Drive personal, Dropbox)
- Forwarding company email to personal accounts
- Using AI tools (ChatGPT, etc.) for confidential or customer data without IT review
- Installing browser extensions that are not on the approved list
- Accessing inappropriate or illegal content on company networks or devices

## Incident Reporting

Report any suspected security incident immediately:

1. **If your device is lost or stolen:** Call IT at ext. 210 immediately (24/7 emergency line).
2. **If you suspect a phishing email:** Forward to phishing@acmeoutfitters.example and delete.
3. **If you see unusual account activity:** Email security@acmeoutfitters.example immediately.
4. **If customer data may have been exposed:** Email security@acmeoutfitters.example AND
   your manager. Do not attempt to investigate or remediate yourself.

Response SLA: IT/Security will acknowledge security incidents within 1 hour (business hours)
or 4 hours (after hours).

### What Not to Do

- Do not try to investigate or access systems to understand the scope of a breach.
- Do not contact affected customers yourself — this is handled by the Security and Legal teams.
- Do not post about security incidents on social media.

## Third-Party & Vendor Security

Before sharing customer data or confidential information with a third-party vendor:
1. Confirm the vendor is on the approved vendor list (maintained by Legal).
2. Ensure a Data Processing Agreement (DPA) is in place.
3. Contact security@acmeoutfitters.example if unsure.

## Compliance

Acme Outfitters is PCI-DSS compliant (Level 4 merchant). We do not store raw payment card
numbers. Employees must not attempt to store, log, or transmit cardholder data.

For privacy questions (CCPA, GDPR for EU customers): contact legal@acmeoutfitters.example.

## Contact

security@acmeoutfitters.example | IT ext. 210 (emergencies: 24/7)
