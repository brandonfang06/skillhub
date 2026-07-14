# Playground Context and Stream Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose all package files safely and prevent truncated model output from being presented as complete.

**Architecture:** SkillHub owns package file selection and UI disclosure. The independent sidecar owns OpenAI-compatible stream semantics, SSE delivery, and generation telemetry.

**Tech Stack:** FastAPI, Pydantic, OpenAI Python SDK, React, TypeScript, Vitest, pytest

---

### Task 1: Sidecar completion semantics

- [x] Add failing tests for finish reason propagation, truncation errors, SSE headers, and the 8192-token default.
- [x] Implement finish reason handling and generation telemetry.
- [x] Update example and Kubernetes configuration to 8192 tokens.

### Task 2: SkillHub context contract

- [x] Add failing backend tests for source-code inclusion and binary file descriptors.
- [x] Return all safe package paths with optional content and inclusion state.
- [x] Preserve byte limits and access revalidation.

### Task 3: Frontend disclosure and file browser

- [x] Add failing tests for the prompt-only/no-execution warning.
- [x] Show all package files and distinguish prompt context from listed-only files.
- [x] Add localized output-truncated feedback and prevent the install CTA.

### Task 4: Verification and delivery

- [x] Run complete backend, frontend, sidecar, isolation, build, and diff checks.
- [x] Commit and push both `dev` branches.
