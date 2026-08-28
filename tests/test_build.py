# -*- coding: UTF-8 -*-
"""Tests for the built add-on package.

The first release of this add-on was rejected by NVDA with nothing more useful
than "missing package or invalid format". The cause was a single ";" comment in
manifest.ini: NVDA parses that file with configobj, which understands only "#".
Nothing checked the artefact we actually shipped, so nothing caught it. These
tests check it.

configobj ships inside NVDA. If it is not installed here, the tests that need it
are skipped rather than failing.

Written by CodedByGoose, with the help of Quill (Claude agent).
"""

import io
import os
import sys
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import build  # noqa: E402
import buildVars  # noqa: E402

try:
    import configobj
except ImportError:
    configobj = None

REQUIRED_KEYS = ("name", "summary", "version", "author", "minimumNVDAVersion", "lastTestedNVDAVersion")


class TestManifestGeneration(unittest.TestCase):
    def setUp(self):
        build.generateManifest()
        self.path = os.path.join(ROOT, "addon", "manifest.ini")
        with open(self.path, encoding="utf-8") as f:
            self.text = f.read()

    def test_noSemicolonComments(self):
        # The exact defect that made NVDA refuse the first build.
        offenders = [n for n, line in enumerate(self.text.splitlines(), 1) if line.lstrip().startswith(";")]
        self.assertEqual(offenders, [], "configobj only accepts '#' comments")

    @unittest.skipIf(configobj is None, "configobj is not installed")
    def test_nvdaCanParseTheManifest(self):
        parsed = configobj.ConfigObj(io.StringIO(self.text))
        for key in REQUIRED_KEYS:
            self.assertIn(key, parsed)

    @unittest.skipIf(configobj is None, "configobj is not installed")
    def test_multilineDescriptionSurvivesParsing(self):
        parsed = configobj.ConfigObj(io.StringIO(self.text))
        self.assertIn("\n", parsed["description"])
        self.assertTrue(parsed["description"].strip())

    def test_versionsMatchBuildVars(self):
        parsed = dict(
            line.split("=", 1) for line in self.text.splitlines() if "=" in line and not line.startswith("#")
        )
        parsed = {k.strip(): v.strip() for k, v in parsed.items()}
        self.assertEqual(parsed["version"], buildVars.addon_info["addon_version"])
        self.assertEqual(parsed["name"], buildVars.addon_info["addon_name"])

    def test_validationRejectsASemicolonComment(self):
        broken = os.path.join(ROOT, "addon", "manifest.broken.ini")
        with open(broken, "w", encoding="utf-8") as f:
            f.write("; a comment NVDA cannot read\nname = test\n")
        try:
            with self.assertRaises(SystemExit):
                build.validateManifest(broken)
        finally:
            os.remove(broken)


class TestPackageContents(unittest.TestCase):
    """Build a real package and look inside it."""

    @classmethod
    def setUpClass(cls):
        cls.path = build.build()

    def test_manifestIsAtTheArchiveRoot(self):
        with zipfile.ZipFile(self.path) as archive:
            self.assertIn("manifest.ini", archive.namelist())

    def test_pluginPackageIsPresent(self):
        with zipfile.ZipFile(self.path) as archive:
            names = archive.namelist()
        for module in ("__init__", "dialog", "sampler", "settings", "formatting", "rowmodel", "winprocinfo"):
            self.assertIn(f"globalPlugins/taskExplorer/{module}.py", names)

    def test_documentationIsRenderedToHtml(self):
        with zipfile.ZipFile(self.path) as archive:
            names = archive.namelist()
        self.assertIn("doc/en/readme.html", names)
        # The markdown source is the input to the build, not part of the package.
        self.assertNotIn("doc/en/readme.md", names)

    def test_noCompiledOrCacheFilesAreShipped(self):
        with zipfile.ZipFile(self.path) as archive:
            names = archive.namelist()
        self.assertEqual([n for n in names if n.endswith(".pyc") or "__pycache__" in n], [])

    def test_everyShippedPythonFileCompiles(self):
        import ast

        with zipfile.ZipFile(self.path) as archive:
            for name in archive.namelist():
                if name.endswith(".py"):
                    ast.parse(archive.read(name).decode("utf-8"), filename=name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
