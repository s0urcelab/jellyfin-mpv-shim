"""Per-library view settings, shared with jellyfin-web.

The setting behind the Home Videos shape mismatch: a library remembers which
*image type* to draw its items with, and web skips its median-aspect rule
entirely when one is set. So two clients only agree for a user who has never
touched the control -- and the people who have are the ones who file issues.

Stored in the same DisplayPreferences ``CustomPrefs`` document as the home
layout, the guide settings and :mod:`user_prefs`.

**The key is not fully knowable from web's source.** ``getSettingsKey``
(``list.js:1265``) builds ``items-<type-or-parentId>-…`` and appends a route
type only when the route carried one, so the same library reached two ways
has two keys. A real setting observed in the wild was

    items-f4415c72cc16920fce19d78d636a3ce7-Folder-imageType: thumb

for a Home Videos library -- parent id *and* a ``Folder`` type. So rather
than pick one spelling and silently read nothing, :func:`keys_for` returns
the candidates in priority order and the reader takes the first that exists.
A write goes back to whichever key it was read from, so we never strand the
user's setting under a name their web client will not look at.

**Sort is two spellings, not one.** Modern jellyfin-web
(``userSettings.saveQuerySettings``) stores a JSON blob
``{"SortBy":"…","SortOrder":"…"}`` on the view key itself
(``items-<parentId>-Movie``). Legacy ``list.js`` stores two string keys
(``…-sortby`` / ``…-sortorder``). Both are server-side; filters are the
ones web kept in localStorage. The DTO's own ``SortBy`` field is a
different store -- one value for the whole ``usersettings`` document --
and is not how a library remembers its order.
"""

import json

#: Image types jellyfin-web offers per library view, and what each means for
#: the grid: ``(geometry attribute, image type requested)``.
#:
#: **This is one axis, and it carries the list view too.** web's own picker
#: (``viewSettings.template.html``) is a single dropdown of primary / banner
#: / disc / logo / thumb / **list**, all written to ``-imageType``; both
#: readers agree that ``primary`` means auto -- legacy ``list.js`` falls
#: through to ``shape: 'autoVertical'`` and the modern ``ItemsView`` to
#: ``CardShape.Auto``. Poster and PosterCard are NOT on this axis: they are
#: the legacy tabbed library screens' ``<key>-_view`` setting, a different
#: key on a different screen, where Poster means shape 'portrait' and
#: PosterCard means the same with the title in a box under the art.
IMAGE_TYPES = {
    "primary": None,
    "thumb": ("geom_wide", "Thumb"),
    "banner": ("geom_banner", "Banner"),
    "disc": ("geom_square", "Disc"),
    "logo": ("geom_wide", "Logo"),
    # OURS, and there is no value on this axis to borrow: "primary" already
    # means auto in both of web's readers, and the one place web does say
    # "poster" is a setting for a screen we have no equivalent of. Auto
    # usually comes out as posters -- but a Home Videos library holding a few
    # portrait clips among landscape ones has a median that says landscape
    # and no way to argue with it. This is that argument.
    #
    # It asks the server for exactly what Auto does, so the two never
    # disagree about which artwork exists; only the shape is forced. web does
    # not recognise the value and falls through to its own auto branch, which
    # is the closest thing it has -- so sharing the setting degrades rather
    # than breaks.
    "poster": ("geom", "Primary"),
    # Not a shape: the table renderer. Web's sixth dropdown entry, and the
    # reason the list view has to live on THIS key -- see is_list.
    "list": None,
}

#: Web's default for every view except Studios (``settings.ts:22``), which we
#: have no equivalent of -- our Networks screen is a list route, not a
#: configurable library view.
DEFAULT_IMAGE_TYPE = "primary"

#: The route ``type`` web appends to the key, by collection type. Best-effort:
#: it depends on how the user navigated, so these are candidates rather than
#: facts. ``Folder`` is the observed one for a Home Videos library.
_ROUTE_TYPES = {
    "homevideos": ("Folder",),
    "photos": ("Folder",),
    "musicvideos": ("MusicVideo", "Folder"),
    "movies": ("Movie",),
    "tvshows": ("Series",),
    "music": ("MusicAlbum",),
    "boxsets": ("BoxSet",),
}


#: Boolean per-view settings and jellyfin-web's defaults for them
#: (``settings.ts:17-27``). Both on, which is what the shim did before any
#: of this existed -- so an untouched library looks exactly as it did.
BOOL_SETTINGS = {"showTitle": True, "showYear": True}

#: The list view, as web stores it: a value of ``imageType``, not a setting
#: of its own. ``viewSettings.js`` writes ``-imageType: list`` and
#: ``list.js`` renders a table for it (``settings.imageType === 'list'``).
LIST_IMAGE_TYPE = "list"

#: What ``imageType`` goes back to when the list view is switched off. Web's
#: dropdown has no "off" -- picking any other entry is how you leave the list
#: -- so this is the entry our checkbox picks on your behalf.
GRID_IMAGE_TYPE = DEFAULT_IMAGE_TYPE

#: Stored ``viewType`` values, which THIS CLIENT used to write and nothing in
#: jellyfin-web has ever read: its ``list.js`` reads ``-viewType`` with a
#: default of 'images' and no writer anywhere sets it. Kept as a read-only
#: fallback so a library someone put in list view before the setting moved
#: onto the shared key still comes up as a list.
LIST_VIEW = "List"
GRID_VIEW = "Poster"


def is_list_view(value):
    """The legacy read: our own ``viewType`` value. See :data:`LIST_VIEW`."""
    return str(value or "").strip().lower() == LIST_VIEW.lower()


def is_list(image_type, view_type=None):
    """Should this library be drawn as a table rather than a grid?

    The shared answer first -- ``imageType: list``, which is what web's own
    picker writes and reads -- then the value this client used to write to a
    key nothing else has ever read.
    """
    if str(image_type or "").strip().lower() == LIST_IMAGE_TYPE:
        return True
    return is_list_view(view_type)


def resolve_bool(custom_prefs, parent_id, collection_type, setting):
    """``(value, key)`` for one of :data:`BOOL_SETTINGS`.

    Written by web as the strings ``"true"``/``"false"``, same as every
    other CustomPrefs boolean -- see :mod:`user_prefs` for why that matters.
    """
    default = BOOL_SETTINGS[setting]
    prefs = custom_prefs or {}
    for key in keys_for(parent_id, collection_type, setting):
        raw = prefs.get(key)
        if raw is None or raw == "":
            continue
        return str(raw).strip().lower() == "true", key
    return default, None


def resolve_view_type(custom_prefs, parent_id, collection_type):
    """``(value, key)`` for the grid-or-list choice."""
    prefs = custom_prefs or {}
    for key in keys_for(parent_id, collection_type, "viewType"):
        raw = str(prefs.get(key) or "").strip()
        if raw:
            return raw, key
    return GRID_VIEW, None


def view_keys_for(parent_id, collection_type):
    """The view key with no setting suffix -- ``items-<parentId>-Movie``,
    then the bare ``items-<parentId>``.

    Modern web's sort JSON lives on this key. ``keys_for`` is this plus
    ``-<setting>``.
    """
    if not parent_id:
        return []
    out = ["items-%s-%s" % (parent_id, route_type)
           for route_type in _ROUTE_TYPES.get(collection_type or "", ())]
    out.append("items-%s" % parent_id)
    return out


def keys_for(parent_id, collection_type, setting="imageType"):
    """CustomPrefs keys that might hold ``setting`` for this library, best
    first.

    The bare ``items-<parentId>-<setting>`` is last rather than first: a
    typed key is more specific, and web writes one whenever the route it was
    on had a type. Reading the bare key first would shadow a real setting.
    """
    return ["%s-%s" % (base, setting)
            for base in view_keys_for(parent_id, collection_type)]


def resolve_image_type(custom_prefs, parent_id, collection_type):
    """``(image_type, key)`` -- the stored value and the key it came from.

    ``key`` is returned so a save lands where the reader looked; writing to
    a different one would leave the user's web client still reading the old
    value. ``None`` for the key means nothing was stored, and a write should
    use the first candidate.
    """
    prefs = custom_prefs or {}
    for key in keys_for(parent_id, collection_type):
        value = str(prefs.get(key) or "").strip().lower()
        if value in IMAGE_TYPES:
            return value, key
    return DEFAULT_IMAGE_TYPE, None


def shape_for(image_type):
    """``(geometry attribute, image type)`` for a stored value, or ``None``
    to leave the grid shaped by its artwork."""
    return IMAGE_TYPES.get((image_type or "").strip().lower())


def primary_sort_by(sort_by):
    """The field a stored SortBy actually sorts on.

    Web sometimes writes a comma list (``DateCreated,SortName``) so ties
    fall back to name. Our dropdown is one field; matching must look at
    the first, or a stored Date Added would miss the menu entry and the
    grid would come up in name order with the setting still on the server.
    """
    return str(sort_by or "").split(",")[0].strip()


def _as_sort_order(raw):
    """Anything other than Descending is Ascending -- web's own rule
    (``getSortValuesLegacy``)."""
    return ("Descending" if str(raw or "").strip().lower() == "descending"
            else "Ascending")


def _parse_sort_json(raw):
    """``(sort_by, sort_order)`` from web's saveQuerySettings blob, or
    None if this is not that blob.

    The view key is also a place nothing else of ours writes, but a
    non-JSON string (or JSON without SortBy) must not be treated as a
    sort -- that would both apply nothing useful and later overwrite
    whatever the string actually was.
    """
    if raw is None or raw == "":
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    sort_by = primary_sort_by(data.get("SortBy"))
    if not sort_by:
        return None
    return sort_by, _as_sort_order(data.get("SortOrder"))


def _is_legacy_sortby_key(key):
    return str(key or "").lower().endswith("-sortby")


def _legacy_order_key(sortby_key):
    """``…-sortby`` -> ``…-sortorder``, preserving the suffix's case so a
    write lands next to the key we read."""
    key = sortby_key or ""
    lower = key.lower()
    if lower.endswith("-sortby"):
        return key[:-len("-sortby")] + (
            "-sortorder" if key.endswith("-sortby") else "-SortOrder")
    return key + "-sortorder"


def resolve_sort(custom_prefs, parent_id, collection_type):
    """``((sort_by, sort_order), key)`` for this library's saved sort.

    ``key`` is the CustomPrefs entry a later save should write -- the JSON
    view key, or the legacy ``-sortby`` key. ``None`` means nothing was
    stored, and a write should use the first view key as JSON (what current
    web writes).

    JSON on a typed view key wins over a leftover ``-sortby`` on the same
    view: that is the spelling current web reads, and writing the other
    one would leave web still showing the old order.
    """
    prefs = custom_prefs or {}
    for key in view_keys_for(parent_id, collection_type):
        parsed = _parse_sort_json(prefs.get(key))
        if parsed is not None:
            return parsed, key
    for key in keys_for(parent_id, collection_type, "sortby"):
        raw = prefs.get(key)
        if raw is None or raw == "":
            continue
        sort_by = primary_sort_by(raw)
        if not sort_by:
            continue
        order_raw = prefs.get(_legacy_order_key(key))
        return (sort_by, _as_sort_order(order_raw)), key
    return (None, None), None


def encode_sort(value, key, parent_id, collection_type):
    """CustomPrefs keys to write for a sort change.

    ``value`` is ``(sort_by, sort_order)``. A legacy ``-sortby`` key is
    written as two strings; everything else (including a first save) is
    web's JSON on the view key.
    """
    sort_by, sort_order = value
    sort_by = primary_sort_by(sort_by)
    sort_order = _as_sort_order(sort_order)
    if not sort_by:
        return {}
    if key and _is_legacy_sortby_key(key):
        return {key: sort_by, _legacy_order_key(key): sort_order}
    if not key:
        keys = view_keys_for(parent_id, collection_type)
        if not keys:
            return {}
        key = keys[0]
    return {key: json.dumps({"SortBy": sort_by, "SortOrder": sort_order},
                            separators=(",", ":"))}
