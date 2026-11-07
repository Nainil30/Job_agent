"""Adapter parsing against recorded-shape payloads (mocked with respx — no network)."""

import json

import httpx
import pytest
import respx

from src.adapters.aggregator import JobSpyAdapter
from src.adapters.amazon import AmazonAdapter
from src.adapters.apple import AppleAdapter
from src.adapters.boards import AshbyAdapter, GreenhouseAdapter, LeverAdapter
from src.adapters.browser import parse_anchor
from src.adapters.eightfold import EightfoldAdapter
from src.adapters.google import GoogleAdapter
from src.adapters.jibe import JibeAdapter
from src.adapters.registry import build_adapters
from src.adapters.workday import WorkdayAdapter

WD = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/Site"


@respx.mock
async def test_workday_listing_and_enrich():
    respx.post(f"{WD}/jobs").mock(
        return_value=httpx.Response(
            200,
            json={
                "total": 1,
                "jobPostings": [
                    {
                        "title": "Senior Hardware TPM",
                        "externalPath": "/job/US-TX-Austin/Senior-Hardware-TPM_JR1001",
                        "locationsText": "Austin, TX",
                        "postedOn": "Posted Today",
                    }
                ],
            },
        )
    )
    respx.get(f"{WD}/job/US-TX-Austin/Senior-Hardware-TPM_JR1001").mock(
        return_value=httpx.Response(
            200,
            json={"jobPostingInfo": {"jobDescription": "<p>Lead <b>EVT</b> builds</p>", "location": "US, TX, Austin"}},
        )
    )
    adapter = WorkdayAdapter(
        {
            "name": "Nvidia",
            "url": f"{WD}/jobs",
            "site_url": "https://nvidia.wd5.myworkdayjobs.com/en-US/Site",
            "queries": ["TPM"],
        }
    )
    jobs = await adapter.run()
    assert len(jobs) == 1 and jobs[0].job_id == "JR1001" and jobs[0].posted_at
    assert jobs[0].url == "https://nvidia.wd5.myworkdayjobs.com/en-US/Site/job/US-TX-Austin/Senior-Hardware-TPM_JR1001"
    enriched = await adapter.enrich_many(jobs)
    assert enriched[0].description == "Lead EVT builds"


@respx.mock
async def test_workday_error_is_reported_not_raised_per_query():
    respx.post(f"{WD}/jobs").mock(return_value=httpx.Response(422, json={}))
    adapter = WorkdayAdapter({"name": "X", "url": f"{WD}/jobs", "queries": ["a"]})
    with pytest.raises(RuntimeError):
        await adapter.run()
    assert adapter.errors


@respx.mock
async def test_eightfold():
    respx.get("https://careers.qualcomm.com/api/pcsx/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "count": 1,
                    "positions": [
                        {
                            "id": 44,
                            "displayJobId": "309",
                            "name": "NPI Program Manager",
                            "standardizedLocations": ["San Diego, CA, US"],
                            "postedTs": 1793577600,
                            "positionUrl": "/careers/job/44",
                        }
                    ],
                }
            },
        )
    )
    respx.get("https://careers.qualcomm.com/api/pcsx/position_details").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {"jobDescription": "<p>Own NPI</p>", "publicUrl": "https://careers.qualcomm.com/careers/job/44"}
            },
        )
    )
    a = EightfoldAdapter(
        {"name": "Qualcomm", "url": "https://careers.qualcomm.com", "domain": "qualcomm.com", "queries": ["npi"]}
    )
    jobs = await a.run()
    assert jobs[0].job_id == "309" and jobs[0].location == "San Diego, CA, US" and jobs[0].posted_at == "2026-11-02"
    assert (await a.enrich_many(jobs))[0].description == "Own NPI"


@respx.mock
async def test_jibe():
    respx.get("https://careers.amd.com/api/jobs").mock(
        return_value=httpx.Response(
            200,
            json={
                "totalCount": 1,
                "jobs": [
                    {
                        "data": {
                            "slug": "92244",
                            "req_id": "92244",
                            "title": "Supply Chain Program Manager",
                            "full_location": "Austin, United States",
                            "description": "<p>Rack supply</p>",
                            "posted_date": "2026-09-11T20:50:00+0000",
                        }
                    }
                ],
            },
        )
    )
    jobs = await JibeAdapter({"name": "AMD", "url": "https://careers.amd.com", "queries": ["supply"]}).run()
    assert (
        jobs[0].url == "https://careers.amd.com/careers-home/jobs/92244?lang=en-us"
        and "Rack supply" in jobs[0].description
    )


@respx.mock
async def test_amazon():
    respx.get("https://www.amazon.jobs/en/search.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "hits": 1,
                "jobs": [
                    {
                        "id_icims": "10447878",
                        "title": "Sr. Supply Chain Program Manager, NPI",
                        "normalized_location": "Austin, Texas, USA",
                        "job_path": "/en/jobs/10447878/x",
                        "description": "AWS NPI",
                        "posted_date": "June 12, 2026",
                    }
                ],
            },
        )
    )
    jobs = await AmazonAdapter({"name": "Amazon", "location": "Austin, TX", "queries": ["npi"]}).run()
    assert jobs[0].job_id == "10447878" and jobs[0].posted_at == "2026-06-12"
    assert respx.calls.last.request.url.params["loc_query"] == "Austin, TX"


@respx.mock
async def test_apple_hydration_parsing():
    state = {"loaderData": {"search": {"totalRecords": 1, "searchResults": [
        {"positionId": "200677521", "postingTitle": "NPI Program Manager", "transformedPostingTitle": "npi-program-manager",
         "locations": [{"name": "Austin", "countryName": "United States of America"}], "jobSummary": "Drive NPI", "postDateInGMT": "2026-11-01T00:00:00Z",
         "team": {"teamName": "Operations"}}]}}}  # fmt: skip
    html = f"<script>window.__staticRouterHydrationData = JSON.parse({json.dumps(json.dumps(state))});</script>"
    respx.get("https://jobs.apple.com/en-us/search").mock(return_value=httpx.Response(200, text=html))
    jobs = await AppleAdapter({"name": "Apple", "queries": ["npi"]}).run()
    assert jobs[0].location == "Austin, United States of America"
    assert jobs[0].url == "https://jobs.apple.com/en-us/details/200677521/npi-program-manager"


@respx.mock
async def test_google_ds1_parsing():
    row = ["8295", "NPI Product Operations Program Manager", "x", [None, "<li>Own NPI</li>"], [None, "<li>5 years</li>"], "p", None, "Google", "en",
           [["Sunnyvale, CA, USA", [], "Sunnyvale"]], [None, "<p>About</p>"], [2], [1791470345, 0]]  # fmt: skip
    html = f"<script>AF_initDataCallback({{key: 'ds:1', hash: '2', data:{json.dumps([[row], None, 1, 20])}, sideChannel: {{}}}});</script>"
    respx.get("https://www.google.com/about/careers/applications/jobs/results/").mock(
        return_value=httpx.Response(200, text=html)
    )
    jobs = await GoogleAdapter({"name": "Google", "queries": ["npi"]}).run()
    assert jobs[0].job_id == "8295" and jobs[0].location == "Sunnyvale, CA, USA"
    assert "Own NPI" in jobs[0].description and jobs[0].posted_at


@respx.mock
async def test_public_boards():
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs").mock(
        return_value=httpx.Response(
            200,
            json={
                "jobs": [
                    {"id": 7, "title": "NPI Manager", "location": {"name": "Austin, TX"}, "absolute_url": "https://x/7"}
                ]
            },
        )
    )
    respx.get("https://boards-api.greenhouse.io/v1/boards/acme/jobs/7").mock(
        return_value=httpx.Response(200, json={"content": "&lt;p&gt;Ramp &amp;amp; EVT&lt;/p&gt;"})
    )
    respx.get("https://api.lever.co/v0/postings/acme").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "l1",
                    "text": "Supply Chain PM",
                    "categories": {"location": "Remote"},
                    "hostedUrl": "https://l/1",
                    "descriptionPlain": "BOM",
                    "createdAt": 1793577600000,
                }
            ],
        )
    )
    respx.get("https://api.ashbyhq.com/posting-api/job-board/acme").mock(
        return_value=httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": "a1",
                        "title": "Hardware TPM",
                        "location": "SF",
                        "isRemote": True,
                        "jobUrl": "https://a/1",
                        "descriptionPlain": "ASIC",
                    },
                    {"id": "a2", "title": "Hidden", "isListed": False},
                ]
            },
        )  # fmt: skip
    )
    gh = GreenhouseAdapter({"name": "Acme", "board": "acme"})
    gh_jobs = await gh.run()
    assert (await gh.enrich_many(gh_jobs))[0].description == "Ramp & EVT"
    lever = await LeverAdapter({"name": "Acme", "board": "acme"}).run()
    assert lever[0].location == "Remote" and lever[0].posted_at == "2026-11-02"
    ashby = await AshbyAdapter({"name": "Acme", "board": "acme"}).run()
    assert [j.job_id for j in ashby] == ["a1"] and "Remote" in ashby[0].location


def test_board_adapter_requires_slug():
    with pytest.raises(ValueError):
        GreenhouseAdapter({"name": "Acme"})


def test_browser_anchor_parsing():
    job_id, title, location, extra = parse_anchor(
        "/profile/job_details/1981338825764645",
        "Supply Chain Capacity Engineer\nMenlo Park, CA\n⋅\nTaipei, Taiwan\nData Center\nInfrastructure",
    )
    assert (job_id, title) == ("1981338825764645", "Supply Chain Capacity Engineer")
    assert location == "Menlo Park, CA; Taipei, Taiwan" and extra == "Data Center | Infrastructure"


def test_jobspy_company_filter():
    a = JobSpyAdapter({"term": "Tesla npi", "companies": ["Tesla"]}, {}, {"Dell": "Secondary"})
    assert a._keep("Tesla") and a._keep("Tesla, Inc.") and not a._keep("Teslarati Media") and not a._keep("Rivian")


def test_registry_respects_tiers_and_only():
    companies = [
        {"name": "Nvidia", "source": "workday", "url": "u"},
        {"name": "Meta", "source": "browser", "url": "u"},
        {"name": "Old", "ats_type": "workday", "base_url": "u", "enabled": False},
        {"name": "Weird", "source": "nope"},
    ]
    aggs = {"jobspy": {"enabled": True, "searches": [{"term": "Tesla npi", "companies": ["Tesla"]}]}}
    names = lambda ads: sorted(a.label for a in ads)  # noqa: E731
    assert names(build_adapters(companies, aggs)) == ["JobSpy: Tesla npi", "Meta (browser)", "Nvidia (workday)"]
    assert names(build_adapters(companies, aggs, tiers=["api"])) == ["Nvidia (workday)"]
    assert names(build_adapters(companies, aggs, only=["tesla"])) == ["JobSpy: Tesla npi"]
