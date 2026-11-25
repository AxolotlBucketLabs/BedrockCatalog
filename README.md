# Bedrock Catalog

An unofficial, queryable catalog of Minecraft Bedrock Marketplace metadata from PlayFab. This project is not affiliated with Mojang Studios or Microsoft.

## Browse

- [Visual catalog](catalog/README.md).
- [Persona emote data](data/persona-emotes.json).
- [Persona piece data](data/persona-pieces.json).

The exports contain confirmed `PersonaDurable` items only. Supported piece types are listed in [`config/confirmed-types.json`](config/confirmed-types.json), and the export format is defined in [`schemas/catalog.schema.json`](schemas/catalog.schema.json).

## Update locally

Requires Python 3.11 and PlayFab authentication.

```powershell
python scripts/update_catalog.py
```

Set either `PLAYFAB_EMAIL` with `PLAYFAB_PASSWORD`, or `PLAYFAB_ENTITY_TOKEN`. Run `scripts/register_playfab_account.ps1` in PowerShell to register or sign in. Keep credentials out of the repository.

GitHub Actions refreshes the catalog daily. It uses the `PLAYFAB_EMAIL`, `PLAYFAB_PASSWORD`, and `CATALOG_APP_PRIVATE_KEY` secrets and the `CATALOG_APP_CLIENT_ID` variable.

The collector uses Minecraft's observed `/Catalog/Search` endpoint, which may change. It validates all pages before writing and leaves existing data untouched if a fetch fails.
