"""Integration tests verifying ATS adapter payload parsing."""

import pytest
import respx
import httpx
from src.adapters.workday import WorkdayAdapter


@pytest.mark.asyncio
async def test_workday_adapter_parsing():
    config = {
        "name": "Nvidia",
        "base_url": "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/test/jobs",
        "site_domain": "https://nvidia.wd5.myworkdayjobs.com/en-US/test",
        "search_queries": ["Hardware TPM"],
    }
    mock_payload = {
        "jobPostings": [
            {
                "title": "Senior Hardware TPM - Datacenter",
                "externalPath": "/job/Austin-TX/Senior-Hardware-TPM_JR1001",
                "locationsText": "Austin, TX",
                "bulletFields": ["Experience with ASIC launch and datacenter rack deployment."],
            }
        ]
    }

    with respx.mock(base_url="https://nvidia.wd5.myworkdayjobs.com") as respx_mock:
        respx_mock.post("/wday/cxs/nvidia/test/jobs").mock(return_value=httpx.Response(200, json=mock_payload))
        adapter = WorkdayAdapter(config)
        jobs = await adapter.fetch_jobs()

        assert len(jobs) == 1
        assert jobs[0].company == "Nvidia"
        assert jobs[0].title == "Senior Hardware TPM - Datacenter"
        assert jobs[0].location == "Austin, TX"
        assert jobs[0].job_id == "JR1001"