# Hermes usage and parameter discovery

These examples are written as prompts you can paste directly into Hermes after installing the MCP. Other MCP-compatible agents can call the same tools using their own interface.

ArtCraft’s live model endpoints are the source of truth. Model identifiers, resolutions, durations, aspect ratios, batch limits, and reference capabilities can change independently of this repository.

## Check the connection in Hermes

```text
Call artcraft_check_connection.
Call artcraft_credential_status, but do not expose cookie values.
Call artcraft_get_user_status, but do not expose subscription tokens.
```

Verify MCP registration from a terminal:

```bash
hermes --profile PROFILE mcp test artcraft
hermes --profile PROFILE mcp list
```

## Find valid image parameters

Paste into Hermes:

```text
Call artcraft_list_image_models. For every model, show its exact model id, aspect ratios, resolutions, quality values, reference support, and batch limits.
```

Then ask Hermes for a spend-free estimate using exact values returned by the model list:

```text
Call artcraft_estimate_image_cost with:
- model: "gpt_image_2"
- aspect_ratio: "16:9"
- resolution: "2k"
- quality: "high"
- batch_size: 1
- reference_image_count: 4
```

## Find valid video parameters

```text
Call artcraft_list_video_models. For every model, show its exact model id, durations, resolutions, aspect ratios, batch limits, image/video/audio reference limits, start/end-frame support, and generated-audio support.
```

Example spend-free video estimate:

```text
Call artcraft_estimate_video_cost with:
- model: "seedance_2p0_fast"
- duration_seconds: 15
- aspect_ratio: "16:9"
- resolution: "480p"
- video_batch_count: 1
- generate_audio: false
```

Friendly inputs such as `16:9`, `9:16`, `480p`, `720p`, and `1080p` are translated to ArtCraft API enum values internally.

## References

Reuse an existing ArtCraft media token:

```text
Call artcraft_upload_reference_image with source="m_existing_token".
```

An existing `m_...` token is returned without uploading anything. Local files and public HTTPS URLs are uploaded to the ArtCraft account and therefore require explicit approval. Preserve token order because it defines `@image1`, `@image2`, and subsequent prompt references.

## Paid image generation

Never generate merely to test the connection. Hermes should estimate first, show the cost, and obtain explicit approval for the exact render.

After approval, paste or send:

```text
The user explicitly approved this paid render after reviewing the cost estimate.

Call artcraft_generate_image_subscription with:
- prompt: "YOUR PROMPT"
- model: "gpt_image_2"
- aspect_ratio: "16:9"
- resolution: "2k"
- quality: "high"
- batch_size: 1
- reference_image_media_tokens: "m_first,m_second"
```

## Paid video generation

After approval:

```text
The user explicitly approved this paid render after reviewing the cost estimate.

Call artcraft_generate_video_subscription with:
- prompt: "YOUR PROMPT"
- model: "seedance_2p0_fast"
- aspect_ratio: "16:9"
- resolution: "480p"
- duration_seconds: 15
- video_batch_count: 1
- generate_audio: false
- reference_image_media_tokens: "m_first,m_second"
```

Preserve the returned `task_...` or `jinf_...` identifier. Ask Hermes:

```text
Call artcraft_get_task_result with the returned task or provider job identifier. Report the status once; if complete, return every output exactly once.
```

A local wait timeout does not mean the server-side render failed.

## Inspect local tool signatures

From the repository root:

```bash
rg -n '^def artcraft_' server.py
```

This lists the local Python signatures. Live model discovery remains authoritative for model-specific options.
