"""Introduction site stays off the ERP login port."""
from pathlib import Path

from app.utils.website_server import erp_origin, render_login_links

SITE_INDEX = Path(__file__).resolve().parents[2] / "frontend" / "website" / "index.html"


def test_erp_origin_keeps_login_on_port_3000():
    assert erp_origin("localhost:8080", 3000) == "http://localhost:3000"
    assert erp_origin("192.168.1.40:8080", 3000) == "http://192.168.1.40:3000"
    assert erp_origin("[::1]:8080", 3000) == "http://[::1]:3000"
    assert erp_origin("localhost", 3000) == "http://localhost:3000"


def test_login_links_are_rewritten_to_the_erp():
    html = '<a href="__ERP_ORIGIN__/login">Log in</a>'
    assert render_login_links(html, "10.0.0.5:8080", 3000) == (
        '<a href="http://10.0.0.5:3000/login">Log in</a>'
    )


def test_site_index_is_not_mounted_on_the_erp_app():
    text = SITE_INDEX.read_text(encoding="utf-8")
    assert text.count('href="__ERP_ORIGIN__/login"') == 3
    assert 'href="styles.css"' in text
    assert 'src="logo.jpg"' in text
    assert "/website/" not in text
