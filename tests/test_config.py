"""Tests for config module — footer loading."""

from __future__ import annotations

from unittest.mock import patch

from business_assistant_imap.config import load_email_settings


@patch.dict(
    "os.environ",
    {
        "IMAP_SERVER": "imap.example.com",
        "IMAP_USERNAME": "user@example.com",
        "IMAP_PASSWORD": "secret",
    },
)
class TestFooterLoading:
    def test_load_footer_from_file(self, tmp_path: object) -> None:
        footer_content = "<b>XIDA GmbH</b><br>09131 - 940 5 270"
        import pathlib

        tmp = pathlib.Path(str(tmp_path))
        footer_file = tmp / "footer.html"
        footer_file.write_text(footer_content, encoding="utf-8")

        with patch.dict("os.environ", {"EMAIL_FOOTER_PATH": str(footer_file)}):
            settings = load_email_settings()

        assert settings is not None
        assert settings.footer_html == footer_content

    def test_load_footer_missing_file(self) -> None:
        with patch.dict(
            "os.environ", {"EMAIL_FOOTER_PATH": "nonexistent/footer.html"}
        ):
            settings = load_email_settings()

        assert settings is not None
        assert settings.footer_html == ""

    def test_load_footer_default_path_missing(self) -> None:
        """When no EMAIL_FOOTER_PATH env var and default path doesn't exist."""
        settings = load_email_settings()

        assert settings is not None
        assert settings.footer_html == ""
