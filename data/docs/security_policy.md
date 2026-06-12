# Acme Outfitters – Information Security Policy

**Version:** 1.0  
**Effective Date:** January 1, 2024  
**Owner:** Information Technology & Security Team  
**Review Cycle:** Annual

---

## 1. Purpose and Scope

This policy establishes the information security standards that govern how Acme Outfitters employees, contractors, and third-party vendors protect company data, systems, and customer information. It applies to all individuals who access Acme Outfitters networks, devices, applications, or data in any capacity.

---

## 2. Password Requirements

Strong authentication is the first line of defense against unauthorized access. All accounts used to access Acme Outfitters systems must adhere to the following password standards.

### 2.1 Minimum Password Requirements

- **Minimum length:** Passwords must be at least **14 characters** long.
- **Complexity:** Passwords must include characters from at least three of the following four categories:
  - Uppercase letters (A–Z)
  - Lowercase letters (a–z)
  - Digits (0–9)
  - Special characters (e.g., `!`, `@`, `#`, `$`, `%`, `^`, `&`, `*`)
- **Prohibited patterns:** Passwords must not contain the user's name, username, email address, or common dictionary words.
- **Reuse restriction:** Users may not reuse any of their last 12 passwords.

### 2.2 Password Rotation and Expiry

- Standard user accounts: passwords expire every **90 days**.
- Privileged/admin accounts: passwords expire every **60 days**.
- Service accounts: passwords expire every **180 days** and require written approval from the IT Security Manager to extend.

### 2.3 Multi-Factor Authentication (MFA)

MFA is mandatory for:
- All remote access (VPN, cloud portals, SaaS applications)
- All administrative and privileged accounts
- Any system that stores or processes Tier 1 or Tier 2 classified data (see Section 3)

Acceptable MFA factors include hardware security keys (FIDO2), authenticator app TOTP codes, or SMS one-time passwords (SMS is discouraged for high-privilege accounts).

### 2.4 Password Managers

Employees are strongly encouraged to use the company-approved password manager (currently **1Password Business**) for generating and storing unique credentials for every service. Sharing passwords via email, chat, or documents is strictly prohibited.

---

## 3. Data Classification

Acme Outfitters classifies all data into four tiers based on sensitivity and the potential impact of unauthorized disclosure.

| Tier | Label | Description | Examples |
|------|-------|-------------|---------|
| 1 | **Restricted** | Highest sensitivity; unauthorized disclosure causes severe legal, financial, or reputational harm. | Customer payment card data (PCI-DSS scope), employee SSNs, trade secrets, M&A information |
| 2 | **Confidential** | Significant business impact if disclosed without authorization. | Employee salaries, internal financial forecasts, supplier contracts, HR records |
| 3 | **Internal** | Low external risk but not intended for public distribution. | Internal memos, org charts, product roadmaps, inventory reports |
| 4 | **Public** | Approved for public distribution. | Marketing materials, press releases, published job postings |

### 3.1 Handling Requirements by Tier

- **Tier 1 (Restricted):** Encrypt at rest and in transit at all times. Access on a strict need-to-know basis with formal approval. No storage on personal devices or removable media.
- **Tier 2 (Confidential):** Encrypt in transit; encrypt at rest when stored outside company-managed systems. Share only with authorized colleagues and approved external partners under NDA.
- **Tier 3 (Internal):** Do not publish externally without manager approval. May be shared internally over standard channels.
- **Tier 4 (Public):** No special restrictions after final approval by Marketing or Communications.

---

## 4. Incident Reporting Procedures

Timely reporting of security incidents minimizes damage and enables a faster recovery.

### 4.1 What Constitutes a Security Incident

A security incident is any actual or suspected event that threatens the confidentiality, integrity, or availability of Acme Outfitters systems or data. Examples include:

- Phishing emails clicked or credentials entered on a fraudulent site
- Lost or stolen devices containing company data
- Unauthorized access attempts or successful account compromises
- Malware or ransomware infections
- Accidental disclosure of Tier 1 or Tier 2 data to unauthorized parties
- Anomalous system behavior suggesting an active intrusion

### 4.2 How to Report

All employees must report suspected or confirmed security incidents **immediately** — do not wait until the end of the business day.

**Primary contact:**  
Email: **security@acmeoutfitters.com**  
24/7 Security Hotline: **+1 (800) 555-0199**

**Steps to follow:**

1. **Do not attempt to investigate or remediate on your own.** Notify the Security team first.
2. **Preserve evidence.** Do not power off, reformat, or delete anything from the affected device unless instructed by the Security team.
3. **Isolate the affected system** from the network if it is safe to do so (e.g., disconnect the Ethernet cable or disable Wi-Fi).
4. **Submit an incident report** via the internal IT ticketing system (ServiceDesk portal) using the "Security Incident" category, or email the address above if the portal is inaccessible.
5. **Cooperate fully** with the Security team's investigation.

### 4.3 Response Timeline

| Severity | Definition | Initial Response Target |
|----------|------------|------------------------|
| Critical | Active breach or data exfiltration in progress | 15 minutes |
| High | Confirmed compromise of a Tier 1/2 system | 1 hour |
| Medium | Suspected compromise or policy violation | 4 hours |
| Low | Minor anomaly, no confirmed data at risk | 1 business day |

### 4.4 Non-Retaliation

Acme Outfitters strictly prohibits retaliation against any employee who in good faith reports a security incident or policy concern. Reports may also be made anonymously through the company's Ethics Hotline.

---

## 5. Policy Violations

Violations of this policy may result in disciplinary action up to and including termination of employment or contract, as well as potential civil or criminal liability. Violations should be reported to the employee's manager and the HR department in addition to the Security team.

---

## 6. Policy Review and Updates

This policy is reviewed annually by the IT Security Manager and approved by the Chief Information Officer (CIO). Significant changes are communicated to all employees via company-wide email and updated in the internal policy repository (SharePoint: Policies & Procedures).

---

*For questions about this policy, contact the IT Security team at security@acmeoutfitters.com.*
