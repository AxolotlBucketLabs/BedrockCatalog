#!/usr/bin/env python3
"""Export verified Minecraft Bedrock Marketplace persona metadata."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_TITLE_ID = "20ca2"
DEFAULT_SCID = "4fc10100-5f7a-4470-899b-280835760c07"
DEFAULT_PAGE_SIZE = 300
MAX_PAGE_SIZE = 300
MAX_PAGES = 10_000
RETRIES = 3
REQUEST_TIMEOUT_SECONDS = 30

class CatalogError(Exception):
    """An upstream or output error that should stop the update safely."""


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )

    for attempt in range(RETRIES + 1):
        try:
            with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                decoded = json.loads(response.read().decode("utf-8"))
            if not isinstance(decoded, dict):
                raise CatalogError("PlayFab returned a JSON value with an unexpected shape.")
            return decoded
        except HTTPError as error:
            retryable = error.code == 429 or 500 <= error.code < 600
            if retryable and attempt < RETRIES:
                time.sleep(2**attempt)
                continue
            raise CatalogError(f"PlayFab returned HTTP {error.code} for {url.rsplit('/', 1)[-1]}.") from None
        except URLError as error:
            if attempt < RETRIES:
                time.sleep(2**attempt)
                continue
            reason = getattr(error, "reason", "network error")
            raise CatalogError(f"Could not reach PlayFab: {reason}.") from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise CatalogError("PlayFab returned invalid JSON.") from None

    raise CatalogError("PlayFab request retries were exhausted.")


def entity_token(base_url: str, title_id: str) -> str:
    email = os.environ.get("PLAYFAB_EMAIL", "")
    password = os.environ.get("PLAYFAB_PASSWORD", "")
    if email or password:
        if not email or not password:
            raise CatalogError("Set both PLAYFAB_EMAIL and PLAYFAB_PASSWORD to sign in.")

        login = post_json(
            f"{base_url}/Client/LoginWithEmailAddress",
            {"Email": email, "Password": password, "TitleId": title_id},
        )
        login_data = response_data(login, "login")
        playfab_id = login_data.get("PlayFabId")
        login_entity = login_data.get("EntityToken")
        login_token = login_entity.get("EntityToken") if isinstance(login_entity, dict) else None
        if not isinstance(playfab_id, str) or not playfab_id:
            raise CatalogError("PlayFab login returned no player account ID.")
        if not isinstance(login_token, str) or not login_token:
            raise CatalogError("PlayFab login returned no entity token.")

        token_response = post_json(
            f"{base_url}/Authentication/GetEntityToken",
            {"Entity": {"Id": playfab_id, "Type": "master_player_account"}},
            {"X-EntityToken": login_token},
        )
        entity = response_data(token_response, "entity token request").get("EntityToken")
        if not isinstance(entity, str) or not entity:
            raise CatalogError("PlayFab returned no entity token.")
        return entity

    token = os.environ.get("PLAYFAB_ENTITY_TOKEN", "").strip()
    if token:
        return token
    raise CatalogError(
        "Set PLAYFAB_EMAIL and PLAYFAB_PASSWORD, or provide PLAYFAB_ENTITY_TOKEN through your secret store."
    )


def response_data(response: dict[str, Any], operation: str) -> dict[str, Any]:
    data = response.get("data")
    if not isinstance(data, dict):
        message = response.get("errorMessage") or response.get("error")
        if isinstance(message, str) and message:
            raise CatalogError(f"PlayFab {operation} failed: {message}")
        raise CatalogError(f"PlayFab {operation} returned no data object.")
    return data


def fetch_all_items(
    base_url: str,
    token: str,
    scid: str,
    filter_expression: str,
    page_size: int,
    allow_empty: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    skip = 0
    source_count: int | None = None
    page_number = 0

    while page_number < MAX_PAGES:
        payload = {
            "Filter": filter_expression,
            "OrderBy": "title/neutral asc",
            "scid": scid,
            "skip": skip,
            "top": page_size,
        }
        response = post_json(
            f"{base_url}/Catalog/Search",
            payload,
            {"X-EntityToken": token},
        )
        data = response_data(response, "catalog search")
        page_items = data.get("Items")
        page_count = data.get("Count")

        if not isinstance(page_items, list):
            raise CatalogError("PlayFab catalog response is missing the Items array.")
        if isinstance(page_count, bool) or not isinstance(page_count, int) or page_count < 0:
            raise CatalogError("PlayFab catalog response has an invalid Count value.")
        if source_count is None:
            source_count = page_count
            if source_count == 0:
                if allow_empty:
                    return [], 0
                raise CatalogError("PlayFab returned no items for a verified catalog filter.")
        elif page_count != source_count:
            raise CatalogError("PlayFab item count changed while the catalog was being paged.")

        for item in page_items:
            if not isinstance(item, dict):
                raise CatalogError("PlayFab catalog response contains a non-object item.")
            items.append(item)

        page_number += 1
        if skip + len(page_items) >= source_count:
            break
        if not page_items:
            raise CatalogError("PlayFab returned an empty page before the reported catalog count was reached.")
        skip += len(page_items)
    else:
        raise CatalogError(f"Catalog paging exceeded the safety limit of {MAX_PAGES} pages.")

    if source_count is None or len(items) != source_count:
        raise CatalogError(
            f"Catalog paging was incomplete. PlayFab reported {source_count} items and returned {len(items)}."
        )
    return items, source_count


def localized_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("neutral", "NEUTRAL", "Neutral"):
            text = value.get(key)
            if isinstance(text, str):
                return text
    return None


def neutral_keywords(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    for key in ("neutral", "NEUTRAL", "Neutral"):
        locale = value.get(key)
        if isinstance(locale, dict):
            values = locale.get("Values") or locale.get("values")
            if isinstance(values, list):
                return [entry for entry in values if isinstance(entry, str)]
    return []


def string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def normalize_item(raw: dict[str, Any], dataset: str, piece_types: frozenset[str]) -> dict[str, Any]:
    item_id = raw.get("Id")
    display = raw.get("DisplayProperties")
    if not isinstance(item_id, str) or not item_id:
        raise CatalogError("PlayFab returned a catalog item without a string Id.")
    if raw.get("ContentType") != "PersonaDurable":
        raise CatalogError(f"Catalog item {item_id} has an unexpected ContentType.")
    if not isinstance(display, dict):
        raise CatalogError(f"Catalog item {item_id} has no DisplayProperties object.")

    piece_type = display.get("pieceType")
    if not isinstance(piece_type, str) or not piece_type:
        raise CatalogError(f"Catalog item {item_id} has no persona pieceType.")
    if dataset == "persona_emotes" and piece_type not in piece_types:
        raise CatalogError(f"Catalog item {item_id} did not match the emote filter.")
    if dataset == "persona_pieces" and piece_type not in piece_types:
        raise CatalogError(f"Catalog item {item_id} has an unverified pieceType.")

    pack_identity = display.get("packIdentity")
    uuid = None
    if isinstance(pack_identity, list) and pack_identity and isinstance(pack_identity[0], dict):
        uuid = pack_identity[0].get("uuid") or pack_identity[0].get("Uuid")
    if not isinstance(uuid, str):
        uuid = display.get("uuid")
    if not isinstance(uuid, str):
        uuid = None

    title_value = raw.get("Title")
    description_value = raw.get("Description")
    keywords_value = raw.get("Keywords")
    images = raw.get("Images")
    tags = raw.get("Tags")
    references = raw.get("ItemReferences")
    alternate_ids = raw.get("AlternateIds")
    if images is not None and not isinstance(images, list):
        raise CatalogError(f"Catalog item {item_id} has an invalid Images value.")

    return {
        "id": item_id,
        "dataset": "persona_emote" if dataset == "persona_emotes" else "persona_piece",
        "title": localized_text(title_value),
        "description": localized_text(description_value),
        "contentType": "PersonaDurable",
        "pieceType": piece_type,
        "uuid": uuid,
        "creatorName": string_or_none(display.get("creatorName")),
        "offerId": string_or_none(display.get("offerId")),
        "price": display.get("price"),
        "rarity": string_or_none(display.get("rarity")),
        "keywords": neutral_keywords(keywords_value),
        "localized": {
            "title": title_value if isinstance(title_value, dict) else {},
            "description": description_value if isinstance(description_value, dict) else {},
            "keywords": keywords_value if isinstance(keywords_value, dict) else {},
        },
        "images": images if isinstance(images, list) else [],
        "tags": tags if isinstance(tags, list) else [],
        "creationDate": string_or_none(raw.get("CreationDate")),
        "lastModifiedDate": string_or_none(raw.get("LastModifiedDate")),
        "displayProperties": display,
        "itemReferences": references if isinstance(references, list) else [],
        "alternateIds": alternate_ids if isinstance(alternate_ids, list) else [],
    }


def newest_item(items_by_id: dict[str, dict[str, Any]], item: dict[str, Any]) -> None:
    current = items_by_id.get(item["id"])
    if current is None:
        items_by_id[item["id"]] = item
        return
    current_date = current.get("lastModifiedDate") or ""
    incoming_date = item.get("lastModifiedDate") or ""
    if incoming_date >= current_date:
        items_by_id[item["id"]] = item


def build_dataset(
    raw_items: list[dict[str, Any]],
    dataset: str,
    piece_types: frozenset[str],
    title_id: str,
    scid: str,
    endpoint: str,
    source_count: int,
) -> dict[str, Any]:
    deduplicated: dict[str, dict[str, Any]] = {}
    excluded = 0
    for raw in raw_items:
        display = raw.get("DisplayProperties")
        piece_type = display.get("pieceType") if isinstance(display, dict) else None
        if piece_type not in piece_types:
            excluded += 1
            continue
        normalized = normalize_item(raw, dataset, piece_types)
        newest_item(deduplicated, normalized)

    items = list(deduplicated.values())
    if not items:
        raise CatalogError(f"The verified {dataset} filter produced no exportable items.")

    items.sort(key=lambda item: ((item["title"] or "").casefold(), item["id"]))
    return {
        "schemaVersion": 1,
        "dataset": dataset,
        "updatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": {"endpoint": endpoint, "titleId": title_id, "scid": scid},
        "count": len(items),
        "sourceItemCount": source_count,
        "duplicatesRemoved": len(raw_items) - len(deduplicated) - excluded,
        "excludedUnconfirmedCount": excluded,
        "items": items,
    }


def write_outputs(output_dir: Path, outputs: dict[str, dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    staged: list[tuple[Path, Path]] = []
    try:
        for filename, payload in outputs.items():
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=output_dir,
                prefix=f".{filename}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                json.dump(payload, temporary, ensure_ascii=False, separators=(",", ":"))
                temporary.write("\n")
                temporary_path = Path(temporary.name)
            staged.append((temporary_path, output_dir / filename))
        for temporary_path, destination in staged:
            os.replace(temporary_path, destination)
    except OSError as error:
        raise CatalogError(f"Could not write catalog output: {error}") from None
    finally:
        for temporary_path, _ in staged:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def load_catalog_definitions() -> list[dict[str, Any]]:
    config_path = Path(__file__).resolve().parents[1] / "config" / "confirmed-types.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise CatalogError(f"Could not read catalog type definitions from {config_path}.") from None

    if not isinstance(config, dict) or config.get("schemaVersion") != 1:
        raise CatalogError("Catalog type definitions use an unsupported schema version.")
    datasets = config.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise CatalogError("Catalog type definitions must contain a non-empty datasets array.")

    seen_names: set[str] = set()
    for definition in datasets:
        if not isinstance(definition, dict):
            raise CatalogError("Catalog type definitions contain an invalid dataset entry.")
        name = definition.get("name")
        filename = definition.get("file")
        filter_expression = definition.get("filter")
        piece_types = definition.get("pieceTypes")
        if (
            name not in {"persona_emotes", "persona_pieces"}
            or name in seen_names
            or not isinstance(filename, str)
            or not filename.endswith(".json")
            or Path(filename).name != filename
            or not isinstance(filter_expression, str)
            or not isinstance(piece_types, list)
            or not piece_types
            or any(not isinstance(piece_type, str) or not piece_type for piece_type in piece_types)
            or len(set(piece_types)) != len(piece_types)
            or definition.get("contentType") != "PersonaDurable"
            or (name == "persona_pieces" and "{pieceType}" not in filter_expression)
            or (name == "persona_emotes" and "{pieceType}" in filter_expression)
        ):
            raise CatalogError("Catalog type definitions failed validation.")
        seen_names.add(name)

    if seen_names != {"persona_emotes", "persona_pieces"}:
        raise CatalogError("Catalog type definitions must include both confirmed persona datasets.")
    return datasets


def update(args: argparse.Namespace) -> None:
    title_id = os.environ.get("PLAYFAB_TITLE_ID", DEFAULT_TITLE_ID).strip()
    scid = os.environ.get("PLAYFAB_SCID", DEFAULT_SCID).strip()
    base_url = f"https://{title_id}.playfabapi.com"
    endpoint = f"{base_url}/Catalog/Search"
    token = entity_token(base_url, title_id)

    outputs: dict[str, dict[str, Any]] = {}

    for definition in load_catalog_definitions():
        dataset = definition["name"]
        if dataset == "persona_pieces":
            raw_items: list[dict[str, Any]] = []
            source_count = 0
            for piece_type in definition["pieceTypes"]:
                print(f"Fetching {dataset} for {piece_type}...")
                filter_expression = definition["filter"].replace("{pieceType}", piece_type)
                piece_items, piece_count = fetch_all_items(
                    base_url,
                    token,
                    scid,
                    filter_expression,
                    args.page_size,
                    allow_empty=True,
                )
                raw_items.extend(piece_items)
                source_count += piece_count
        else:
            print(f"Fetching {dataset}...")
            raw_items, source_count = fetch_all_items(
                base_url,
                token,
                scid,
                definition["filter"],
                args.page_size,
            )
        outputs[definition["file"]] = build_dataset(
            raw_items,
            dataset,
            frozenset(definition["pieceTypes"]),
            title_id,
            scid,
            endpoint,
            source_count,
        )

    write_outputs(Path(args.output_dir), outputs)
    for filename, payload in outputs.items():
        print(f"Wrote {payload['count']} unique items to {Path(args.output_dir) / filename}.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export verified Minecraft Bedrock Marketplace persona metadata.")
    parser.add_argument("--output-dir", default="data", help="Directory for generated JSON files. Default: data")
    parser.add_argument(
        "--page-size",
        type=int,
        default=DEFAULT_PAGE_SIZE,
        help=f"Items requested per page, from 1 to {MAX_PAGE_SIZE}. Default: {DEFAULT_PAGE_SIZE}",
    )
    args = parser.parse_args()
    if not 1 <= args.page_size <= MAX_PAGE_SIZE:
        parser.error(f"--page-size must be between 1 and {MAX_PAGE_SIZE}.")
    return args


def main() -> int:
    try:
        update(parse_args())
    except CatalogError as error:
        print(f"Bedrock Catalog update failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
