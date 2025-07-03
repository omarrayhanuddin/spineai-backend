import asyncio
from httpx import AsyncClient
from app.core.config import settings


class AzureOCRService:
    def __init__(self, client: AsyncClient):
        self.client = client
        self.api_key = settings.DOCUMENT_INTELLIGENCE_API_KEY
        self.endpoint = settings.DOCUMENT_INTELLIGENCE_ENDPOINT

    async def extract_text(self, file_bytes: bytes):
        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Content-Type": "application/octet-stream",
        }

        # Step 1: Start analysis
        response = await self.client.post(
            self.endpoint,
            content=file_bytes,
            headers=headers,
            timeout=30.0,  # longer timeout if needed
        )

        if response.status_code != 202:
            return None, None

        operation_url = response.headers.get("Operation-Location")
        if not operation_url:
            return None, None

        poll_headers = {"Ocp-Apim-Subscription-Key": self.api_key}

        # Step 2: Poll with exponential backoff
        for attempt in range(30):
            poll_resp = await self.client.get(operation_url, headers=poll_headers)
            result = poll_resp.json()
            status = result.get("status")

            if status == "succeeded":
                pages = result["analyzeResult"]["readResults"]
                total_pages = len(pages)
                return [
                    line["text"] for page in pages for line in page["lines"]
                ], total_pages

            elif status == "failed":
                return None, None

            await asyncio.sleep(min(3, 0.5 * (2**attempt)))

        return None, None
