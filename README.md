# artcraft-mcp

An ArtCraft subscription MCP server built for [Hermes Agent](https://github.com/NousResearch/hermes-agent). It gives Hermes tools for live model discovery, cost estimation, reference ingestion, image/video generation, local task lookup, and resumable result retrieval.

It can also be used by any agent or client that supports local MCP servers over stdio.

Contributions are welcome. If you find an error, an outdated ArtCraft parameter, or a way to make the adapter safer or more useful, please open an issue or submit a pull request. Help testing and optimizing the tool across different setups is especially valuable.

This MCP does **not** control the ArtCraft desktop app or its interface. It reads the authenticated session saved by the installed ArtCraft app, optionally reads ArtCraft’s local task database, and calls ArtCraft’s Storyteller subscription API directly.

⚠ Image and video generation spend ArtCraft subscription credits. Discover live parameters, estimate cost, and obtain explicit approval before generation.

## Hermes quick start

### 1. Install the MCP

Clone the repository somewhere outside your Hermes profile directory:

```bash
git clone https://github.com/smoermeow/artcraft-mcp.git ~/src/artcraft-mcp
cd ~/src/artcraft-mcp
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest -v
```

### 2. Add it to a Hermes profile

```bash
./scripts/setup-hermes.sh PROFILE
```

Replace `PROFILE` with the Hermes profile that should receive the ArtCraft tools. The helper registers this clone’s absolute Python and server paths, sets a 300-second MCP timeout, and tests tool discovery.

### 3. Reload and verify

Run `/reload-mcp` in Hermes or restart that profile’s CLI/gateway process. From a terminal:

```bash
hermes --profile PROFILE mcp test artcraft
hermes --profile PROFILE mcp list
```

Hermes should discover 18 ArtCraft tools. Paste-ready Hermes prompts and model-call examples are in [docs/USAGE.md](docs/USAGE.md).

### Manual Hermes configuration

```bash
ROOT="$HOME/src/artcraft-mcp"

hermes --profile PROFILE mcp add artcraft \
  --command "$ROOT/.venv/bin/python" \
  --connect-timeout 30 \
  --args "$ROOT/server.py"

hermes --profile PROFILE config set mcp_servers.artcraft.timeout 300
hermes --profile PROFILE mcp test artcraft
```

Equivalent YAML is available at [examples/hermes-mcp.yaml](examples/hermes-mcp.yaml).

## How it works

ArtCraft stores its active subscription session here on macOS:

```text
~/Library/Caches/ai.artcraft.app/.cookies
```

The server reads only `visitor` and `session` cookies belonging to `api.storyteller.ai`. It never returns their values from MCP tools. It uses those credentials to call ArtCraft’s subscription API, not to operate the desktop UI. See [SECURITY.md](SECURITY.md).

Hermes starts `server.py` as a local subprocess and exchanges MCP messages through standard input/output (`stdio`). No local port or public web server is opened.

## Requirements

- macOS with ArtCraft installed and signed in.
- Python 3.11+.
- Hermes Agent, or another MCP client with local stdio support.

## Find models and parameters

Do not guess model options. Ask Hermes to call:

```text
artcraft_list_image_models
artcraft_list_video_models
```

The live records expose exact model IDs and model-specific resolutions, durations, aspect ratios, batch limits, reference limits, and audio/keyframe support. Next call the appropriate spend-free estimator:

```text
artcraft_estimate_image_cost
artcraft_estimate_video_cost
```

See [docs/USAGE.md](docs/USAGE.md) for complete Hermes prompts covering discovery, estimates, references, paid generation, and result retrieval.

## Tools

| Group | Tools |
| --- | --- |
| Health/account | `artcraft_check_connection`, `artcraft_detect_installation`, `artcraft_credential_status`, `artcraft_get_user_status` |
| Models/costs | `artcraft_list_image_models`, `artcraft_list_video_models`, `artcraft_estimate_image_cost`, `artcraft_estimate_video_cost` |
| Tasks/results | `artcraft_list_tasks`, `artcraft_get_task`, `artcraft_list_subscription_jobs`, `artcraft_get_task_result`, `artcraft_wait_for_result` |
| References | `artcraft_upload_reference_image`, `artcraft_upload_reference_audio`, `artcraft_upload_reference_video` |
| Paid generation | `artcraft_generate_image_subscription`, `artcraft_generate_video_subscription` |

## Other MCP clients

The server is standard MCP over stdio. Configure another compatible agent/client to run:

```text
/path/to/artcraft-mcp/.venv/bin/python /path/to/artcraft-mcp/server.py
```

Tool behavior and safety requirements are the same. Client-specific configuration formats differ.

## Safety boundary

- Read-only discovery and estimates do not spend credits.
- Uploading a new reference writes to the ArtCraft account and requires explicit approval.
- Paid generation requires explicit approval after cost estimation.
- Never commit cookies, ArtCraft databases, logs, `.env` files, subscription tokens, private media, or private prompts.

## Tests

```bash
.venv/bin/python -m unittest -v
```

GitHub Actions runs the same test suite for pushes and pull requests.

## Attribution

This adapter was informed by [ArtCraft PR #1649, “\[BETA\] Desktop app MCP stdio layer”](https://github.com/storytold/artcraft/pull/1649), authored by [tanish2k09](https://github.com/tanish2k09). See [NOTICE.md](NOTICE.md) for the specific patterns independently implemented here.

## License

[MIT](LICENSE). See [NOTICE.md](NOTICE.md) for upstream acknowledgement.
