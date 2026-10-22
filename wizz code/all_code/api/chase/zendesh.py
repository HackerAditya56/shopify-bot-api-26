import asyncio, httpx

async def solve(k, u, w):
    b = "https://api.capmonster.cloud"
    async with httpx.AsyncClient() as c:
        p = {"clientKey": k, "task": {"type": "MTCaptchaTask", "websiteURL": u, "websiteKey": w}}
        t = (await c.post(f"{b}/createTask", json=p)).json().get("taskId")
        
        for _ in range(40):
            if not t: break
            await asyncio.sleep(1.5)
            s = (await c.post(f"{b}/getTaskResult", json={"clientKey": k, "taskId": t})).json()
            if s.get("status") == "ready": return (s.get('solution') or {}).get('token')
