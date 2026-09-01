# Privacy and Data Governance Policy

Last updated: August 18, 2026

## Purpose and scope

SkillHub is open-source software for publishing, reviewing, discovering, and
installing agent skill packages. This document describes privacy and
data-governance expectations for people who operate SkillHub instances.

The upstream maintainers do not control every self-hosted instance. The operator
decides why and how data is processed and remains responsible for an
instance-specific privacy notice, lawful processing grounds, data-subject
requests, contracts, retention, and applicable law. This document is not legal
advice and does not certify any deployment as compliant.

## Data the software can process

Depending on enabled authentication, storage, email, observability, scanner, and
deployment options, an instance can process:

- account and identity data such as username, email, avatar, OAuth identifiers,
  account status, roles, and namespace membership;
- authentication/security data such as sessions, password hashes, token metadata,
  login events, IP addresses, browser information, and password-reset records;
- skill packages, including `SKILL.md`, scripts, documentation, images, examples,
  license files, archives, and version metadata;
- governance data such as namespaces, reviews, reports, ratings, stars,
  notifications, and audit records;
- operational data such as searches, downloads, request identifiers, timestamps,
  errors, metrics, traces, logs, and security findings; and
- connection configuration for storage, identity, email, monitoring, and optional
  scanning services.

Actual content determines sensitivity. A package, review comment, log, or report
can contain personal, confidential, or authentication data even when its field
name does not identify it as such.

## Operator responsibilities

Before processing personal data, each operator must identify applicable law and
its role, document purpose and lawful basis, complete required privacy/security/
transfer assessments, and reflect the result in notices, contracts, procedures,
and configuration.

Operators, administrators, and publishers should:

- avoid secrets and unnecessary personal data in packages, examples, profiles,
  namespace descriptions, reviews, or reports;
- use organization-scoped or pseudonymous identifiers where practical;
- configure the shortest retention and least visibility needed;
- redact sensitive values before sending packages/findings to an external
  scanner, model, log sink, or support channel;
- restrict privileged roles and review them regularly; and
- document source, purpose, recipients, lawful basis, and retention for each
  material data category.

## Storage, access, and isolation

Authentication, platform/namespace RBAC, visibility, audit logs, hashed API
tokens, PostgreSQL, Redis, and local/S3 storage are building blocks, not a secure
deployment by themselves. Operators are responsible for:

- disabling development authentication and replacing example credentials;
- using HTTPS externally and protected networks for internal services;
- applying least privilege to users, services, databases, caches, and storage;
- encrypting sensitive data and backups according to the threat model;
- storing secrets outside source code, packages, browser config, and logs;
- testing namespace and object-storage isolation;
- controlling access to packages, audit data, logs, traces, backups, and findings;
  and
- applying supported security updates and maintaining recovery procedures.

## External services and transfers

OAuth providers, object storage, email, monitoring, mirrors, and scanner
integrations can receive instance data. Operators must assess provider terms,
locations, retention, subprocessors, training-data rules, and cross-border
transfer mechanisms. An external or LLM-backed scanner must be disclosed in the
instance privacy notice and data-flow review.

## Retention, deletion, and portability

The project does not impose one retention period on independent instances. Each
operator must publish periods no longer than needed for documented purposes and
law. A deletion process should cover accounts, memberships, package objects,
reviews, reports, ratings, notifications, scan/outbox records, caches, audit
records, logs, traces, exports, and backups. Backup copies that cannot be removed
immediately should be isolated from normal use and expire on a documented schedule.

Operators should provide authenticated channels for access, correction, deletion,
restriction, objection, and portability where applicable. Skill archives and
public metadata can be exported through the API/CLI, but operators must document
which instance records are portable, their formats/version compatibility, and any
personal data excluded from exports.

## Security and incident handling

Report upstream vulnerabilities privately under the
[iFLYTEK security policy](https://github.com/iflytek/.github/blob/main/SECURITY.md)
to [security@iflytek.com](mailto:security@iflytek.com), not in a public issue.
Instance operators remain responsible for monitoring, incident response,
proportionate evidence, credential rotation, backups, recovery, and legally
required notifications.

Questions about this project policy can be sent to
[ifly_opensource@iflytek.com](mailto:ifly_opensource@iflytek.com). Requests about
a self-hosted instance must go to the operator identified in that instance's
privacy notice.

Privacy-impacting changes should be reviewed for minimization, access and
namespace boundaries, visibility, external disclosures, retention, logging,
deletion, and portability. File history records material project-policy changes.
