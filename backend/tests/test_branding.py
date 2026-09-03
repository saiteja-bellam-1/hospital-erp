"""Tests for hospital app branding API."""

from io import BytesIO

from PIL import Image


def _png_bytes(width, height):
    buf = BytesIO()
    Image.new("RGB", (width, height), (20, 80, 160)).save(buf, format="PNG")
    return buf.getvalue()


class TestBrandingApi:
    def test_branding_public_no_auth(self, client, seed_data):
        res = client.get("/api/hospital/branding/public")
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "Test Hospital"
        assert data["logo_url"] is None
        assert data["favicon_url"] is None

    def test_branding_get_authenticated(self, client, auth_headers, seed_data):
        res = client.get("/api/hospital/branding", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["name"] == "Test Hospital"

    def test_branding_put_super_admin(self, client, auth_headers, db_session, seed_data):
        res = client.put(
            "/api/hospital/branding",
            headers=auth_headers,
            json={
                "name": "Custom Hospital",
                "logo_url": "/uploads/module-config/logo.png",
                "favicon_url": "/uploads/module-config/favicon.png",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["name"] == "Custom Hospital"
        assert data["logo_url"] == "/uploads/module-config/logo.png"
        assert data["favicon_url"] == "/uploads/module-config/favicon.png"

        public = client.get("/api/hospital/branding/public")
        assert public.json()["name"] == "Custom Hospital"

    def test_branding_put_rejects_hospital_admin(self, client, db_session, seed_data):
        from app.models.user import User
        from app.utils.auth import create_access_token

        receptionist = db_session.query(User).filter_by(username="testreceptionist").first()
        token = create_access_token({"sub": receptionist.username})
        headers = {"Authorization": f"Bearer {token}"}

        res = client.put(
            "/api/hospital/branding",
            headers=headers,
            json={"name": "Blocked"},
        )
        assert res.status_code == 403

    def test_hospital_info_logo_ignored_for_hospital_admin(self, client, db_session, seed_data):
        from app.models.hospital import Hospital
        from app.models.user import User, UserRole
        from app.utils.auth import create_access_token, get_password_hash

        hospital_admin_role = db_session.query(UserRole).filter_by(name="hospital_admin").first()
        if hospital_admin_role is None:
            hospital_admin_role = UserRole(name="hospital_admin", is_system_role=True)
            db_session.add(hospital_admin_role)
            db_session.flush()

        ha_user = User(
            username="testhadmin",
            password_hash=get_password_hash("admin123"),
            email="hadmin@test.com",
            first_name="Hospital",
            last_name="Admin",
            role_id=hospital_admin_role.id,
            hospital_id=seed_data["hospital_id"],
            is_active=True,
        )
        db_session.add(ha_user)
        db_session.commit()

        token = create_access_token({"sub": ha_user.username})
        headers = {"Authorization": f"Bearer {token}"}

        res = client.put(
            "/api/hospital/info",
            headers=headers,
            json={"logo_url": "/uploads/module-config/should-not-apply.png"},
        )
        assert res.status_code == 200

        hospital = db_session.query(Hospital).first()
        assert hospital.logo_url != "/uploads/module-config/should-not-apply.png"

    def test_logo_upload_accepts_landscape_wordmark(self, client, auth_headers, seed_data):
        png = _png_bytes(800, 200)
        res = client.post(
            "/api/hospital/branding/upload?kind=logo",
            headers=auth_headers,
            files={"file": ("logo.png", png, "image/png")},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["width"] == 800
        assert data["height"] == 200
        assert data["url"].startswith("/uploads/module-config/")

    def test_logo_upload_rejects_portrait(self, client, auth_headers, seed_data):
        png = _png_bytes(200, 400)
        res = client.post(
            "/api/hospital/branding/upload?kind=logo",
            headers=auth_headers,
            files={"file": ("logo.png", png, "image/png")},
        )
        assert res.status_code == 400
        assert "200×400" in res.json()["detail"]

    def test_logo_upload_rejects_extreme_banner(self, client, auth_headers, seed_data):
        png = _png_bytes(2000, 80)
        res = client.post(
            "/api/hospital/branding/upload?kind=logo",
            headers=auth_headers,
            files={"file": ("logo.png", png, "image/png")},
        )
        assert res.status_code == 400

    def test_favicon_upload_accepts_square(self, client, auth_headers, seed_data):
        png = _png_bytes(64, 64)
        res = client.post(
            "/api/hospital/branding/upload?kind=favicon",
            headers=auth_headers,
            files={"file": ("icon.png", png, "image/png")},
        )
        assert res.status_code == 200
        assert res.json()["width"] == 64

    def test_favicon_upload_rejects_wide_image(self, client, auth_headers, seed_data):
        png = _png_bytes(200, 50)
        res = client.post(
            "/api/hospital/branding/upload?kind=favicon",
            headers=auth_headers,
            files={"file": ("icon.png", png, "image/png")},
        )
        assert res.status_code == 400
