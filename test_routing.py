from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()

@app.get("/{catchall:path}")
def serve_spa(catchall: str):
    return {"catchall": catchall}

client = TestClient(app)

response = client.get("/")
print("Response for / :", response.status_code, response.json() if response.status_code == 200 else response.text)

response2 = client.get("/dashboard")
print("Response for /dashboard :", response2.status_code, response2.json() if response2.status_code == 200 else response2.text)
