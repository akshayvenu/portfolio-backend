async def test_submit_contact_form_success(client):
    response = await client.post(
        "/api/v1/contact",
        json={"name": "Ada Lovelace", "email": "ada@example.com", "message": "Hello there!"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True


async def test_submit_contact_form_invalid_email(client):
    response = await client.post(
        "/api/v1/contact",
        json={"name": "Ada", "email": "not-an-email", "message": "Hello there!"},
    )
    assert response.status_code == 422


async def test_submit_contact_form_rate_limited(client):
    payload = {"name": "Ada", "email": "ada@example.com", "message": "Hello there!"}
    for _ in range(3):
        await client.post("/api/v1/contact", json=payload)

    response = await client.post("/api/v1/contact", json=payload)
    assert response.status_code == 429
