import papis.bibtex
from unittest.mock import patch
import tests
import papis.config
from papis.document import from_data
from papis.commands.browse import run, cli


@patch("papis.utils.general_open", lambda *x, **y: None)
def test_run() -> None:
    papis.config.set("browse-key", "url")
    assert run(from_data({"url": "hello.com"})) == "hello.com"

    papis.config.set("browse-key", "doi")
    assert run(from_data({"doi": "12312/1231"})) == "https://doi.org/12312/1231"

    papis.config.set("browse-key", "isbn")
    assert (
        run(from_data({"isbn": "12312/1231"}))
        == "https://isbnsearch.org/isbn/12312/1231")

    papis.config.set("browse-key", "nonexistentkey")
    assert (
        run(from_data({"title": "blih", "author": "me"}))
        == "https://duckduckgo.com/?q=blih+me")


class TestCli(tests.cli.TestCli):

    cli = cli

    def test_run_function_exists(self) -> None:
        self.assertIsNot(run, None)

    @patch("papis.utils.general_open", lambda *x, **y: None)
    def test_key_doi(self) -> None:
        result = self.invoke([
            "krishnamurti", "-k", "doi"
        ])
        self.assertEqual(result.exit_code, 0)

    def test_no_documents(self) -> None:
        result = self.invoke(["__no_document__"])
        self.assertEqual(result.exit_code, 0)

    @patch("papis.utils.general_open", lambda *x, **y: None)
    def test_key_doi_all(self) -> None:
        result = self.invoke([
            "-k", "doi", "--all"
        ])
        self.assertEqual(result.exit_code, 0)

    @patch("papis.utils.general_open", lambda *x, **y: None)
    @patch("papis.pick.pick_doc", lambda x: [])
    def test_key_doi_not_select(self) -> None:
        result = self.invoke([
            "krishnamurti", "-k", "doi"
        ])
        self.assertEqual(result.exit_code, 0)
