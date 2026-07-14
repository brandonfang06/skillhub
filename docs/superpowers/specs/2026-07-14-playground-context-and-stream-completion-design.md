# Playground Context and Stream Completion Design

Date: 2026-07-14

## Goal

Show every package file in Playground, include bounded textual files as model
context without executing them, and distinguish complete model output from
token-limit truncation.

## Context Contract

SkillHub returns every safe package path. UTF-8-compatible text files, including
source code, may carry content and `includedInPrompt: true` while the configured
byte limit has room. Binary files and text files outside the budget remain
visible with empty content and `includedInPrompt: false`. Keeping `content` a
string preserves compatibility with an older sidecar during rolling deploys.

The sidecar stores this exact list and builds the system prompt only from files
marked as included. The UI lists every file and makes inclusion status visible.
It also states that Playground is prompt-only: scripts are read as text but are
never executed, and no sandbox, shell, tools, or network access is provided.

## Completion Contract

The sidecar requests streaming output and records the upstream finish reason.
Only an explicit normal `stop` emits `message.completed`. A `length` finish
emits `output_truncated`; any other or missing finish reason emits
`response_incomplete`. Both keep partial text visible and do not enable the
install CTA. Provider failures remain `provider_unavailable`.

The default model output budget is 8192 tokens. SSE responses use no-transform
and no-buffering headers. Generation logs record duration, first-token latency,
chunk count, output size, and finish category without logging prompt content.

## Boundaries

This change does not execute package code, add a sandbox, mount package files,
or grant model tools. Binary preview and token-aware prompt budgeting remain
future work.
