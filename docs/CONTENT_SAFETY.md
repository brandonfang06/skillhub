# Content Safety Policy

Last updated: August 18, 2026

## Purpose and scope

SkillHub accepts, stores, reviews, and distributes agent skill packages. A
package can contain instructions, scripts, documentation, images, and other
files that influence an agent or execute on a user's computer. Profiles,
namespace descriptions, reviews, reports, ratings, and release notes are also
user-supplied content.

This policy describes baseline expectations, available controls, and the
responsibilities of publishers, reviewers, operators, and installers. The
upstream maintainers do not operate every self-hosted instance. Each operator
must assess its users, jurisdiction, deployment model, and risk, then publish
and staff its own enforceable reporting, review, appeal, and emergency process.

## Baseline rules

An instance should not knowingly publish or distribute packages or content that:

- violate applicable law or intellectual-property, privacy, or other rights;
- sexually exploit or endanger children;
- credibly threaten, harass, or promote violence or hateful abuse;
- expose personal, confidential, or authentication data without authorization;
- contain malware, credential theft, destructive payloads, unauthorized access,
  persistence, evasion, or instructions intended to defeat security controls;
- impersonate people or organizations, facilitate fraud, or intentionally make
  materially deceptive claims;
- secretly collect, transmit, or use data beyond the documented purpose;
- conceal external services, downloads, commands, permissions, or side effects;
  or
- bypass review, scanning, namespace, visibility, or access-control rules.

Legitimate security research, education, and defensive automation can discuss
or test risky behavior. Reviewers should consider purpose, provenance,
permissions, likely impact, and applicable law rather than keywords alone.

## Package risks and publisher duties

A skill can read or modify files, execute commands, call external services,
install dependencies, browse websites, or process sensitive inputs. A positive
rating or successful scan does not prove that it is safe, lawful, accurate, or
suitable for a specific environment.

Before submission, publishers should:

- inspect every file and remove secrets, personal data, build artifacts, and
  unrelated binaries;
- document commands, network destinations, downloads, permissions, persistent
  changes, and known limitations;
- pin or constrain dependencies where practical and retain license notices;
- test failure and rollback behavior in an isolated environment;
- avoid instructions designed to override system, user, or operator controls;
  and
- update, withdraw, or replace a package when a material risk is discovered.

Browser folder publishing performs the same path, file-count, extension, and
size checks as ZIP publishing before it creates an archive. Those checks reduce
accidental packaging mistakes; they are not a malware or content-safety verdict.

## Available controls and limitations

SkillHub provides controls that an operator can combine according to risk:

- archive size, file-count, path, extension, and selected signature checks;
- a configurable security scanner and durable scan-task delivery;
- namespace/platform review, approve, reject, withdraw, and promotion flows;
- user reports and administrator hide, archive, reject, or yank actions;
- platform and namespace RBAC, visibility controls, audit records, and
  notifications; and
- optional Redis-backed HTTP rate limits. The Python-only fork leaves these
  disabled by default for upgrade compatibility; operators must make an
  explicit enablement decision.

These controls reduce risk but do not certify content. Scanning can be disabled,
external/LLM scanners add privacy and reliability dependencies, and all scanning
modes can produce false positives or false negatives. Scanner failure must not
be treated as proof of safety.

See the [scanner guide](security-scanning.md),
[review guide](skillhub/en/guide/review.md), and
[privacy policy](PRIVACY_AND_DATA_GOVERNANCE.md).

## Operator safeguards

Before opening an instance to publishers or installers, an operator should:

- define permitted content, reviewers, escalation owners, emergency contacts,
  and an impartial appeal route;
- enable scanning and human review appropriate to exposure and package risk;
- restrict and audit direct-publish and governance roles;
- isolate package inspection from production secrets and sensitive networks;
- disclose which scanner, review, and rate-limit controls are active;
- preserve only necessary evidence and protect reporter identities; and
- train reviewers to handle malware, privacy, child-safety, fraud, and
  intellectual-property reports safely.

## Reporting, action, and appeals

Use the affected instance's report feature or private operator channel. Include
the package coordinate/version, time observed, reason for concern, and minimum
context required for investigation. Do not execute a suspected package or resend
illegal, exploitative, personal, or confidential material over an unprotected
channel.

Report upstream vulnerabilities privately to
[security@iflytek.com](mailto:security@iflytek.com) under the
[iFLYTEK security policy](https://github.com/iflytek/.github/blob/main/SECURITY.md).
Do not disclose vulnerabilities or personal data in a public issue.

Operators should triage imminent danger, child safety, active malware, exposed
credentials, and security incidents urgently; preserve proportionate evidence;
record the applicable rule and rationale; take proportionate action; notify
affected people when lawful and safe; and provide review by someone who did not
make the original decision. Temporary protective measures may remain while they
are necessary to protect people, systems, or evidence.

## Children and policy review

SkillHub is a general-purpose developer and enterprise collaboration tool, not a
child-directed service. An operator that permits child use or processes children's
data must perform the legally required assessment, consent, minimization,
restriction, notice, and escalation work. If those protections cannot be
provided, the instance should not be offered to children.

Package inspection, reports, logs, and investigations can expose sensitive data
and must follow the privacy policy and the operator's retention schedule.
Operators should periodically test controls, review incident trends, and update
their policies as the product, threat model, law, or operating context changes.
