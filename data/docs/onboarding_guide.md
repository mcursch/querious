# New Employee Onboarding Guide

*Acme Outfitters People Operations — Revised January 2025*

## Welcome

This guide walks you through your first 30 days at Acme Outfitters. It covers everything from day-one logistics to getting set up in our core systems, understanding how we work, and completing the mandatory training courses that every employee must finish within 30 days of hire.

If anything in this guide is unclear or out of date, contact hr@acmeoutfitters.example.

---

## Before Your First Day

### Offer Letter and I-9

You should have received your offer letter and an invitation to complete Form I-9 employment eligibility verification through our HR platform (Rippling). Please complete the I-9 remote verification at least **two business days before your start date**. You will need acceptable identity documents (list available at uscis.gov/i-9-central).

### Equipment Shipment

If you are a remote or hybrid employee, your Acme-issued equipment will ship to your home address 5–7 business days before your start date. This typically includes:
- MacBook Pro (Engineering / Marketing) or MacBook Air (other roles)
- 27-inch external monitor (if manager-approved)
- USB-C dock, keyboard, and mouse
- YubiKey hardware security token (required for all employees — see `security_policy.md`)

If your equipment has not arrived two days before your start date, contact it-helpdesk@acmeoutfitters.example.

---

## Day One Checklist

### Morning

- [ ] Join the all-hands Zoom welcome meeting at 10:00 AM PT (link in your calendar invite)
- [ ] Meet your onboarding buddy — assigned by HR and introduced via email before Day One
- [ ] Activate your Acme Google Workspace account (you@acmeoutfitters.example)
- [ ] Set up Google Authenticator or Duo for two-factor authentication
- [ ] Register your YubiKey in the Acme IT portal (portal.acmeoutfitters.example/yubikey)

### Afternoon

- [ ] Complete Rippling self-service setup: payroll direct deposit, benefits enrollment, emergency contacts
- [ ] Join the #welcome Slack channel and introduce yourself
- [ ] Review the Employee Handbook (see `employee_handbook.md`) and acknowledge receipt in Rippling
- [ ] Schedule a 30-minute 1:1 with your manager for later in the week

---

## Week One — Systems Access

Your manager will file a New Employee Access Request ticket in Jira Service Desk on your behalf. Access is typically provisioned within one business day. You should expect access to the following systems depending on your role:

### All Employees

| System | Purpose | Access Method |
|--------|---------|---------------|
| Google Workspace (Gmail, Calendar, Drive, Meet) | Email and collaboration | Auto-provisioned with your @acmeoutfitters.example account |
| Slack | Internal messaging | Google SSO login at acme.slack.com |
| Rippling | HR, payroll, time tracking | invite@rippling.com invitation |
| Jira | Project tracking (view + comment) | Google SSO |
| Confluence | Internal wiki and documentation | Google SSO |
| Expensify | Expense reporting | Invitation from Finance |

### Sales and Support Roles (Additional Access)

| System | Purpose |
|--------|---------|
| Salesforce CRM | Customer accounts, opportunities |
| Zendesk | Support tickets |
| Gong | Call recording and coaching |

### Engineering Roles (Additional Access)

| System | Purpose |
|--------|---------|
| GitHub (acmeoutfitters org) | Source code |
| AWS Console | Cloud infrastructure (read-only for most; full access for senior engineers with approval) |
| Datadog | Monitoring and alerting |
| 1Password Teams | Secrets management |

### Finance Roles (Additional Access)

| System | Purpose |
|--------|---------|
| NetSuite | ERP: GL, AP, AR, invoicing |
| Stripe Dashboard | Payment processing |
| Ramp | Corporate card management |

---

## Weeks Two and Three — Learning and Onboarding Projects

### Required Training (Complete Within 30 Days)

All employees must complete the following training courses in Rippling Learning:

1. **Code of Conduct and Ethics** (~30 min)
2. **Information Security Awareness** (~45 min) — covers phishing, password hygiene, device security; see also `security_policy.md`
3. **Privacy and Data Handling** (~30 min)
4. **Harassment-Free Workplace** (~45 min)
5. **OSHA Safety Basics** (~20 min) — all employees; warehouse employees also take the 10-hour OSHA General Industry course

Warehouse employees only:
6. **Forklift Safety Orientation** (~2 hours, in-person at your DC)
7. **Hazardous Materials Handling** (~30 min)

Completion is tracked automatically in Rippling. Employees who have not completed required training by Day 30 will receive an automated reminder and a follow-up from their manager.

### Meet the Teams

During weeks two and three, your onboarding buddy will schedule 30-minute introductory calls with stakeholders from other departments. These calls are intended to help you understand how your role fits into the broader organization, not to start projects. A suggested list of cross-functional partners is included in your Confluence onboarding page (link sent on Day One).

### 30-Day Onboarding Project

By the end of week three, you and your manager should have agreed on a **30-day onboarding project** — a concrete, scoped deliverable that lets you get hands-on with Acme's systems and workflows without high stakes. Examples by department:

- **Sales:** Complete a deal-stage audit for 10 CRM accounts in your assigned territory
- **Support:** Handle 20 tickets end-to-end with your onboarding buddy shadowing
- **Engineering:** Ship a well-scoped bug fix or small feature with a pull request that passes CI
- **Finance:** Reconcile one month's AR aging report and flag discrepancies for review
- **Warehouse:** Process a full shift's worth of receives and picks under DC supervisor guidance

---

## Day 30 — Onboarding Completion

At the end of your first 30 days, you will complete a brief onboarding survey in Rippling (5 minutes) so People Ops can improve the process for future employees. Your manager will also complete a 30-day check-in form.

By Day 30 you should have:
- [ ] All required training courses complete in Rippling
- [ ] All relevant systems access provisioned and working
- [ ] 30-day project delivered or in final review
- [ ] At least one 1:1 with your manager per week for the first month
- [ ] Connected with your assigned onboarding buddy at least three times

---

## Ongoing Resources

- **Internal wiki (Confluence):** All team runbooks, process docs, meeting notes, and project specs
- **#ask-people-ops Slack channel:** HR questions, policy clarifications
- **#ask-it Slack channel:** Technical issues, access requests
- **IT Help Desk:** it-helpdesk@acmeoutfitters.example | Jira Service Desk portal
- **Your onboarding buddy:** Assigned for your first 90 days; available to answer informal questions

---

## Frequently Asked Questions

### When do benefits start?

Health, dental, and vision coverage begins on the first day of the calendar month following your hire date. If you start on the first of the month, coverage begins on your start date. Benefits enrollment must be completed within 30 days of hire; late enrollment must wait until the next open enrollment period (October annually).

### How do I submit expenses?

Submit receipts in Expensify and tag them with your cost center and category. Expenses must be submitted within 30 days of purchase. See the Employee Handbook (§ Expenses) for limits and approval requirements.

### Where do I find the org chart?

The org chart is maintained in Rippling and is accessible to all employees. It is updated within one business day of role changes.
