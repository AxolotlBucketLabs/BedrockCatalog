# Bedrock Catalog

An unofficial, queryable catalog of Minecraft Bedrock Marketplace metadata from PlayFab. This project is not affiliated with Mojang Studios or Microsoft.

[![CI](https://github.com/AxolotlBucketLabs/BedrockCatalog/actions/workflows/validate.yml/badge.svg)](https://github.com/AxolotlBucketLabs/BedrockCatalog/actions/workflows/validate.yml) [![License: MIT](https://img.shields.io/github/license/AxolotlBucketLabs/BedrockCatalog)](LICENSE) [![Discord](https://img.shields.io/discord/1568295845374206052?label=Discord&logo=discord&logoColor=white&color=5865F2)](https://discord.gg/Pk4FrNvHnM)

## Browse

- [Visual catalog](catalog/README.md).
- [Persona emote data](data/persona-emotes.json).
- [Persona piece data](data/persona-pieces.json).

The exports contain confirmed `PersonaDurable` items only. Supported piece types are listed in [`config/confirmed-types.json`](config/confirmed-types.json), and the export format is defined in [`schemas/catalog.schema.json`](schemas/catalog.schema.json).

The MIT License covers the collector, schemas, and project-authored documentation. It does not grant rights to Marketplace metadata in `data/` or third-party assets linked by the catalog. Those may remain subject to their respective owners' rights and terms.

## Update locally

Requires Python 3.11 and PlayFab authentication.

```powershell
python scripts/update_catalog.py
```

Set either `PLAYFAB_EMAIL` with `PLAYFAB_PASSWORD`, or `PLAYFAB_ENTITY_TOKEN`. Run `scripts/register_playfab_account.ps1` in PowerShell to register or sign in. Keep credentials out of the repository.

GitHub Actions refreshes the catalog daily. It uses the `PLAYFAB_EMAIL`, `PLAYFAB_PASSWORD`, and `CATALOG_APP_PRIVATE_KEY` secrets and the `CATALOG_APP_CLIENT_ID` variable.

The collector uses Minecraft's observed `/Catalog/Search` endpoint, which may change. It validates all pages before writing and leaves existing data untouched if a fetch fails.
