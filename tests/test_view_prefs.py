"""Per-library view settings, shared with jellyfin-web.

The setting behind the Home Videos shape mismatch: a library remembers
which image type to draw its items with, and web skips its median-aspect
rule entirely when one is set.
"""

import sys
import unittest

sys.argv = ["test"]

from jellyfin_mpv_shim.mpvtk_browser import view_prefs  # noqa: E402


class KeyTest(unittest.TestCase):
    """The key is not fully knowable from web's source -- getSettingsKey
    appends a route type only when the route carried one, so the same
    library reached two ways has two keys. Hence candidates, not a guess."""

    def test_the_observed_key_is_a_candidate(self):
        """Seen in the wild on a Home Videos library:
        items-<parentId>-Folder-imageType."""
        keys = view_prefs.keys_for("PID", "homevideos")
        self.assertIn("items-PID-Folder-imageType", keys)

    def test_the_bare_key_is_last_not_first(self):
        """A typed key is more specific, and web writes one whenever the
        route had a type. Reading the bare key first would shadow it."""
        keys = view_prefs.keys_for("PID", "homevideos")
        self.assertEqual(keys[-1], "items-PID-imageType")
        self.assertGreater(len(keys), 1)

    def test_an_unknown_collection_type_still_gets_the_bare_key(self):
        self.assertEqual(view_prefs.keys_for("PID", "channels"),
                         ["items-PID-imageType"])

    def test_no_parent_means_no_keys(self):
        self.assertEqual(view_prefs.keys_for(None, "movies"), [])


class ResolveTest(unittest.TestCase):
    def test_an_untouched_library_is_auto(self):
        value, key = view_prefs.resolve_image_type({}, "PID", "movies")
        self.assertEqual(value, "primary")
        self.assertIsNone(key, "nothing stored, so nothing to write back to")

    def test_the_observed_setting_is_read(self):
        value, key = view_prefs.resolve_image_type(
            {"items-PID-Folder-imageType": "thumb"}, "PID", "homevideos")
        self.assertEqual(value, "thumb")
        self.assertEqual(key, "items-PID-Folder-imageType")

    def test_the_key_it_came_from_is_returned(self):
        """So a save lands where the reader looked -- writing elsewhere
        leaves the user's web client reading the old value."""
        _v, key = view_prefs.resolve_image_type(
            {"items-PID-imageType": "banner"}, "PID", "movies")
        self.assertEqual(key, "items-PID-imageType")

    def test_a_typed_key_wins_over_the_bare_one(self):
        value, _k = view_prefs.resolve_image_type(
            {"items-PID-Movie-imageType": "banner",
             "items-PID-imageType": "thumb"}, "PID", "movies")
        self.assertEqual(value, "banner")

    def test_junk_is_ignored_rather_than_applied(self):
        value, key = view_prefs.resolve_image_type(
            {"items-PID-Movie-imageType": "nonsense"}, "PID", "movies")
        self.assertEqual(value, "primary")
        self.assertIsNone(key)

    def test_case_and_space_do_not_matter(self):
        value, _k = view_prefs.resolve_image_type(
            {"items-PID-Movie-imageType": " Thumb "}, "PID", "movies")
        self.assertEqual(value, "thumb")


class ShapeTest(unittest.TestCase):
    def test_primary_means_no_override(self):
        """It is "auto": shape the grid by its artwork, which is what it
        does with no setting at all."""
        self.assertIsNone(view_prefs.shape_for("primary"))

    def test_thumb_is_landscape(self):
        self.assertEqual(view_prefs.shape_for("thumb"), ("geom_wide", "Thumb"))

    def test_banner_gets_a_banner(self):
        """Decided explicitly: if they ask for banner, give them banner --
        auto_geom folds its own >=3 bucket into landscape, but that one is
        inferred and this one is asked for."""
        self.assertEqual(view_prefs.shape_for("banner"),
                         ("geom_banner", "Banner"))

    def test_disc_is_square_and_logo_is_wide(self):
        self.assertEqual(view_prefs.shape_for("disc"), ("geom_square", "Disc"))
        self.assertEqual(view_prefs.shape_for("logo"), ("geom_wide", "Logo"))

    def test_poster_forces_what_auto_usually_infers(self):
        """Ours, not web's. Auto usually comes out as posters, but a Home
        Videos library with a few portrait clips among landscape ones has a
        median that says otherwise and no way to argue."""
        self.assertEqual(view_prefs.shape_for("poster"), ("geom", "Primary"))
        self.assertIsNone(view_prefs.shape_for("primary"),
                          "Auto must stay 'shape it from the artwork'")

    def test_poster_asks_the_server_for_what_auto_asks_for(self):
        """Only the shape is forced. If it asked for something else the two
        could disagree about which artwork exists."""
        from jellyfin_mpv_shim.mpvtk_browser.repository import (
            browse_image_types)
        self.assertEqual(browse_image_types(view_prefs.shape_for("poster")[1]),
                         browse_image_types(None))

    def test_a_stored_poster_is_read_back(self):
        value, _key = view_prefs.resolve_image_type(
            {"items-PID-imageType": "poster"}, "PID", "homevideos")
        self.assertEqual(value, "poster")

    def test_an_unknown_value_is_no_override(self):
        self.assertIsNone(view_prefs.shape_for("wat"))
        self.assertIsNone(view_prefs.shape_for(None))


class ViewKeyTest(unittest.TestCase):
    def test_the_typed_view_key_is_first(self):
        self.assertEqual(view_prefs.view_keys_for("PID", "movies")[0],
                         "items-PID-Movie")

    def test_keys_for_is_the_view_key_plus_the_setting(self):
        self.assertEqual(view_prefs.keys_for("PID", "movies", "imageType"),
                         ["items-PID-Movie-imageType", "items-PID-imageType"])


class ResolveSortTest(unittest.TestCase):
    """Per-library sort, shared with jellyfin-web.

    Two spellings: modern JSON on the view key, and legacy -sortby /
    -sortorder strings. JSON wins, because that is what current web reads.
    """

    def test_an_untouched_library_has_nothing_stored(self):
        pair, key = view_prefs.resolve_sort({}, "PID", "movies")
        self.assertEqual(pair, (None, None))
        self.assertIsNone(key)

    def test_modern_json_on_the_typed_key(self):
        pair, key = view_prefs.resolve_sort(
            {"items-PID-Movie":
             '{"SortBy":"DateCreated","SortOrder":"Descending"}'},
            "PID", "movies")
        self.assertEqual(pair, ("DateCreated", "Descending"))
        self.assertEqual(key, "items-PID-Movie")

    def test_a_typed_key_wins_over_the_bare_one(self):
        pair, _k = view_prefs.resolve_sort(
            {"items-PID-Movie":
             '{"SortBy":"DateCreated","SortOrder":"Descending"}',
             "items-PID":
             '{"SortBy":"SortName","SortOrder":"Ascending"}'},
            "PID", "movies")
        self.assertEqual(pair, ("DateCreated", "Descending"))

    def test_legacy_sortby_is_read(self):
        pair, key = view_prefs.resolve_sort(
            {"items-PID-Movie-sortby": "PremiereDate",
             "items-PID-Movie-sortorder": "Descending"},
            "PID", "movies")
        self.assertEqual(pair, ("PremiereDate", "Descending"))
        self.assertEqual(key, "items-PID-Movie-sortby")

    def test_json_wins_over_legacy_on_the_same_view(self):
        """Current web reads the JSON. Writing the leftover -sortby
        instead would leave web still showing the old order."""
        pair, key = view_prefs.resolve_sort(
            {"items-PID-Movie":
             '{"SortBy":"DateCreated","SortOrder":"Descending"}',
             "items-PID-Movie-sortby": "SortName",
             "items-PID-Movie-sortorder": "Ascending"},
            "PID", "movies")
        self.assertEqual(pair, ("DateCreated", "Descending"))
        self.assertEqual(key, "items-PID-Movie")

    def test_a_comma_list_keeps_the_first_field(self):
        pair, _k = view_prefs.resolve_sort(
            {"items-PID-Movie":
             '{"SortBy":"DateCreated,SortName","SortOrder":"Descending"}'},
            "PID", "movies")
        self.assertEqual(pair[0], "DateCreated")

    def test_junk_json_is_ignored(self):
        pair, key = view_prefs.resolve_sort(
            {"items-PID-Movie": "thumb"}, "PID", "movies")
        self.assertEqual(pair, (None, None))
        self.assertIsNone(key)

    def test_empty_sortby_is_ignored(self):
        pair, key = view_prefs.resolve_sort(
            {"items-PID-Movie-sortby": ""}, "PID", "movies")
        self.assertEqual(pair, (None, None))
        self.assertIsNone(key)

    def test_anything_but_descending_is_ascending(self):
        pair, _k = view_prefs.resolve_sort(
            {"items-PID-Movie-sortby": "SortName",
             "items-PID-Movie-sortorder": "Desending"},
            "PID", "movies")
        self.assertEqual(pair[1], "Ascending")

    def test_legacy_without_an_order_defaults_to_ascending(self):
        pair, _k = view_prefs.resolve_sort(
            {"items-PID-Movie-sortby": "SortName"}, "PID", "movies")
        self.assertEqual(pair, ("SortName", "Ascending"))


class EncodeSortTest(unittest.TestCase):
    def test_a_first_save_is_json_on_the_typed_view_key(self):
        """What current web writes. Inventing a -sortby key would leave
        web still reading nothing."""
        writes = view_prefs.encode_sort(
            ("DateCreated", "Descending"), None, "PID", "movies")
        self.assertEqual(writes, {
            "items-PID-Movie":
            '{"SortBy":"DateCreated","SortOrder":"Descending"}'})

    def test_a_legacy_key_is_written_as_two_strings(self):
        writes = view_prefs.encode_sort(
            ("PremiereDate", "Descending"),
            "items-PID-Movie-sortby", "PID", "movies")
        self.assertEqual(writes, {
            "items-PID-Movie-sortby": "PremiereDate",
            "items-PID-Movie-sortorder": "Descending"})

    def test_a_json_key_is_written_back_as_json(self):
        writes = view_prefs.encode_sort(
            ("CommunityRating", "Descending"),
            "items-PID-Movie", "PID", "movies")
        self.assertEqual(writes["items-PID-Movie"],
                         '{"SortBy":"CommunityRating","SortOrder":"Descending"}')

    def test_no_parent_writes_nothing(self):
        self.assertEqual(
            view_prefs.encode_sort(("SortName", "Ascending"), None,
                                   None, "movies"),
            {})


if __name__ == "__main__":
    unittest.main()
