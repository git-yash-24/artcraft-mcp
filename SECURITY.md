# Security

## Local credentials

This server reads ArtCraft’s signed-in desktop session from the local Tauri cookie store:

```text
~/Library/Caches/ai.artcraft.app/.cookies
```

Never commit, upload, paste, or share that file. Also keep ArtCraft task databases, debug logs, `.env` files, and local media manifests out of Git.

The server selects only `visitor` and `session` cookies belonging to `api.storyteller.ai`. Credential/status tools report presence and validity without returning cookie values.

## Paid operations

Image and video generation consume ArtCraft subscription credits. MCP clients and agents should:

1. discover live model capabilities;
2. call the spend-free cost-estimate tool;
3. show the estimate to the user;
4. require explicit approval for that render; and
5. call a generation tool only after approval.

Reference upload does not consume generation credits, but it writes media to the user’s ArtCraft account and also requires explicit approval. Reusing an existing `m_...` token performs no upload.

## Reporting

Do not include cookies, subscription tokens, private media URLs, or private prompts in a public issue. Contact the repository maintainer privately for security-sensitive reports.
