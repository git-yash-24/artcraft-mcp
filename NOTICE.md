# Upstream acknowledgement

This standalone Python MCP adapter was informed by ArtCraft pull request [#1649, “\[BETA\] Desktop app MCP stdio layer”](https://github.com/storytold/artcraft/pull/1649), authored by [tanish2k09](https://github.com/tanish2k09).

The project independently implemented several patterns identified in that work:

- domain-aware selection of the `visitor` and `session` cookies for `api.storyteller.ai`;
- structured, sanitized errors with user-facing remediation;
- ArtCraft credit and subscription summaries; and
- batch-result expansion through ArtCraft’s subscription API.

PR #1649 is an upstream Rust MCP implementation coupled to the ArtCraft monorepo. This repository is a separate standalone Python adapter with additional image/video workflows, local task lookup, reference-token reuse, and resumable result retrieval.

ArtCraft is a product and trademark of its respective owners. This independent integration is not affiliated with or endorsed by ArtCraft.
