# Bedrock Catalog

Bedrock Catalog collects Minecraft Bedrock Marketplace metadata from PlayFab and writes queryable JSON files.

This is an independent, unofficial project. It is not affiliated with, endorsed by, or sponsored by Mojang Studios or Microsoft.

## Confirmed catalog data

The current export includes only `PersonaDurable` items represented in the available Marketplace snapshots:

- `persona_emote` items in `data/persona-emotes.json`.
- Persona pieces in `data/persona-pieces.json`, limited to the piece types in [`config/confirmed-types.json`](config/confirmed-types.json).

The collector does not export other Marketplace categories until their response data and filters have been verified.

## Requirements

- Python 3.11 or newer.
- A valid PlayFab entity token or PlayFab account credentials authorized for Minecraft's PlayFab title.

Authentication uses `PLAYFAB_EMAIL` and `PLAYFAB_PASSWORD` when both are set. The collector signs in and obtains a fresh master-player entity token for each run, even if `PLAYFAB_ENTITY_TOKEN` is also set. Use a current `PLAYFAB_ENTITY_TOKEN` only when account credentials are unavailable. Run `scripts/register_playfab_account.ps1` in PowerShell to register a new account once or sign in to the existing account. It keeps credentials only in that PowerShell session and does not write them to a file. For scheduled automation, store credentials as CI secrets. Do not share or commit them.

## Update the catalog

Run the collector from the project directory:

```powershell
python scripts/update_catalog.py
```

After registering or signing in, run the collector in the same PowerShell window so it can use the session credentials.

The default page size is 300. To change it or choose another output directory, pass `--page-size` or `--output-dir`:

```powershell
python scripts/update_catalog.py --page-size 300 --output-dir data
```

The collector fetches and validates every page for both datasets before writing output. It follows the upstream `data.Count` and `skip`/`top` pagination fields, queries each confirmed persona piece type separately, removes duplicate records by item `Id`, and rejects incomplete or empty datasets. Output files are replaced atomically after a complete successful fetch. If an upstream request or validation fails, existing JSON files remain unchanged.

## JSON format

Each output file is a JSON object with the following top-level fields:

| Field | Meaning |
| --- | --- |
| `schemaVersion` | Version of this project's export format. |
| `dataset` | Stable dataset name. |
| `updatedAt` | UTC time when the complete export was generated. |
| `source` | PlayFab endpoint, title ID, and SCID used for the query. |
| `count` | Number of unique exported items. |
| `sourceItemCount` | Number of source records fetched across all pages. |
| `duplicatesRemoved` | Duplicate item IDs removed during export. |
| `excludedUnconfirmedCount` | Records omitted because their persona piece type is not in the verified allowlist. |
| `items` | Array of normalized Marketplace records. |

Each item contains a stable `id`, `title`, `description`, `contentType`, and `pieceType`, along with available UUID, creator, offer, price, rarity, keyword, image, tag, date, localized text, display property, reference, and alternate ID metadata. Missing upstream values are represented as `null` or empty arrays. The full export contract is in [`schemas/catalog.schema.json`](schemas/catalog.schema.json).

## API behavior

The collector uses the Minecraft title's observed `POST /Catalog/Search` endpoint with `X-EntityToken` authentication. Its request, master-player token exchange, and response shape follow the [Bedrock-Emotes updater](https://github.com/TwistedAsylumMC/Bedrock-Emotes/blob/main/update.sh). The request uses the Marketplace SCID, a category filter, and `skip`/`top` pagination. Responses must contain `data.Items` and `data.Count`. Available records and persona piece types were cross-checked against the public [Bedrock-Persona dataset](https://github.com/Daniel-Ric/Bedrock-Persona).

PlayFab documents `X-EntityToken` for Economy catalog APIs and documents the current [`Catalog/SearchItems`](https://learn.microsoft.com/en-us/rest/api/playfab/economy/catalog/search-items) route with `Items` and `ContinuationToken` pagination. The title-specific legacy `Catalog/Search` route and its `skip`/`top` response shape are different and are not covered by that contract. The legacy route is based on observed Minecraft Marketplace traffic and can change independently. A request without an entity token returned HTTP 401 during endpoint research. The collector fails without replacing current files if the response no longer matches the expected shape.

## Updating supported types

Add a catalog type only after inspecting authenticated PlayFab responses and confirming that its filter, fields, and pagination work. Add its normalized schema and a fixture or validation rule in the same change. Unknown persona piece types are skipped and counted until they are reviewed and added to the allowlist.
