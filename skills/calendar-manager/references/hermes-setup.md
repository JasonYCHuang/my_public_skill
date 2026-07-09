# Setting up Google Calendar access for Hermes agent

Hermes doesn't bundle a named Google Calendar connector the way Claude
Code's claude.ai integration does, so this is a one-time setup step per
Hermes install. This walkthrough uses
[`@cocal/google-calendar-mcp`](https://github.com/nspady/google-calendar-mcp)
(package name `@cocal/google-calendar-mcp` on npm, source at
`nspady/google-calendar-mcp` on GitHub) — an actively maintained, open-source
MCP server that talks directly to the Google Calendar API over stdio, which
is exactly the transport Hermes's `mcp_servers` config expects. It exposes
`list-calendars`, `list-events`, `create-event`, `update-event`, `get-event`
— the same four-plus-one operations this skill needs.

This is a third-party package, not something this skill's author built or
maintains. Skim its README before trusting it with a real calendar, and
re-check this doc against the current upstream README if anything below
seems stale.

## 1. Get Google OAuth credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com), create or
   pick a project.
2. Enable the **Google Calendar API** for that project.
3. Under **Credentials → Create Credentials → OAuth client ID**:
   - Data type: "User data"
   - Application type: **Desktop app** (this specific type matters — other
     types won't work with this server)
   - Add scopes `https://www.googleapis.com/auth/calendar.events` and
     `https://www.googleapis.com/auth/calendar`
   - Add your own Google account as a test user
4. Download the resulting credentials JSON file. Save it somewhere stable,
   e.g. `~/.hermes/gcp-oauth.keys.json` — you'll reference its path in the
   config.

## 2. Add the MCP server to Hermes's config

Hermes reads MCP server definitions from `~/.hermes/config.yaml`, under a
`mcp_servers:` key. Merge the block from
`assets/hermes-mcp-config.example.yaml` (in this skill folder) into your
own `~/.hermes/config.yaml`, updating the credentials path:

```yaml
mcp_servers:
  google-calendar:
    command: "npx"
    args: ["-y", "@cocal/google-calendar-mcp"]
    env:
      GOOGLE_OAUTH_CREDENTIALS: "/absolute/path/to/gcp-oauth.keys.json"
    enabled: true
```

If `mcp_servers:` already exists in your config with other servers under
it, add `google-calendar:` as a sibling key — don't create a second
`mcp_servers:` block.

Alternatively, if your Hermes version's interactive picker
(`hermes mcp`, `hermes mcp add`) already lists `google-calendar-mcp` as a
catalog entry, that may be simpler than hand-editing YAML — check `hermes mcp`
first before assuming you need to do this by hand.

## 3. First-run authentication

The first time a tool call actually hits this server, it needs to complete
an OAuth flow (opens a browser, you approve access, it stores a token —
typically next to the credentials file unless you set
`GOOGLE_CALENDAR_MCP_TOKEN_PATH`). Ask your agent to list your calendars as
a first test; if it stalls or errors, that's usually this step needing to
complete interactively rather than a config problem.

## 4. Verify tool names

Hermes registers MCP tools as `mcp_<server_name>_<tool_name>` — for the
config above that should produce names like `mcp_google-calendar_list-events`,
but confirm the exact registered names with `hermes tools` (or by asking
your agent what Google-Calendar-related tools it currently has) before
relying on this skill's instructions, since exact naming/sanitization of the
hyphenated tool names wasn't something we could verify without a live
Hermes install to test against.

## 5. Point this skill at the right names

Once you know the real tool names, tell your agent (once, it should
remember for the session/going forward) something like: "for this calendar
skill, list-calendars is `mcp_google-calendar_list-calendars`, list-events
is `mcp_google-calendar_list-events`" etc. — `SKILL.md` is written in terms
of the four operations, not literal names, precisely so this mapping is a
one-time thing rather than something baked into the instructions.

## Known gap

The Claude Code version of this skill found that `create_event`'s
`location` field silently failed to persist and needed a follow-up
`update_event` call as a workaround (see `SKILL.md`). Whether
`@cocal/google-calendar-mcp`'s `create-event` has the same issue is
**unverified** — it's a completely different server implementation. Test
it once (create an event with a location, then `get-event` to check) before
assuming either way.
