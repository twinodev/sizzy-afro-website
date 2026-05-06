from app import app

PUBLIC_ROUTES = [
    "/",
    "/events",
    "/testimonials",
    "/videos",
    "/merchandise",
    "/sponsors",
    "/partnerships",
    "/posts",
    "/contact",
]

ADMIN_ROUTES = [
    "/admin",
    "/admin/events",
    "/admin/testimonials",
    "/admin/faqs",
    "/admin/merchandise",
    "/admin/videos",
    "/admin/merchandise/create",
    "/admin/videos/create",
]

with app.test_client() as c:
    print("PUBLIC")
    for route in PUBLIC_ROUTES:
        try:
            r = c.get(route)
            print(f"{route} -> {r.status_code}")
        except Exception as exc:
            print(f"{route} -> EXC: {exc}")

    with c.session_transaction() as sess:
        sess["admin_logged_in"] = True

    print("ADMIN")
    for route in ADMIN_ROUTES:
        try:
            r = c.get(route)
            print(f"{route} -> {r.status_code}")
        except Exception as exc:
            print(f"{route} -> EXC: {exc}")
